"""
=============================================================================
WEB SERVER — FastAPI + WebSocket pour interface web temps réel
=============================================================================

ROLE:
    Expose l'état du système multi-agents (WorldState) à l'interface web
    via WebSocket. Le frontend (HTML/JS) se connecte et reçoit l'état
    complet toutes les 200 ms — animation fluide sans polling HTTP.

ARCHITECTURE:

    [Agents SPADE]──►[WorldState]──►[FastAPI WS]──►[Browser]
       (asyncio)      (thread-safe)     (asyncio)     (vanilla JS)

ENDPOINTS:
    GET  /                   → sert l'interface web (index.html)
    GET  /static/*           → assets CSS/JS
    WS   /ws                 → flux temps réel de l'état du monde
    GET  /api/state          → snapshot ponctuel (debug)
    GET  /api/geo            → métadonnées GPS (zone Fès)

FRAMEWORK: FastAPI
    - Asynchrone natif (compatible avec SPADE asyncio)
    - WebSocket simple et performant
    - Auto-documentation à /docs
=============================================================================
"""

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from utils.world_state import world_state
from utils.city_map import (
    grid_to_gps, gps_to_grid,
    LAT_MIN, LAT_MAX, LON_MIN, LON_MAX,
    UEMF_CENTER_LAT, UEMF_CENTER_LON,
    estimate_delivery_time_minutes, cells_to_km, euclidean_distance,
)
from utils.ontologies import Config
from data.restaurants import RESTAURANTS


# Chemins absolus vers les assets web
ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"

app = FastAPI(title="Drone Delivery SMA API", version="1.0.0")


# =============================================================================
# Helpers : convertir le WorldState en format JSON enrichi pour le frontend
# =============================================================================

def enrich_snapshot(snapshot: dict) -> dict:
    """
    Enrichit le snapshot du WorldState avec :
    - Coordonnées GPS (en plus des coordonnées grille)
    - Conversion des tuples en listes (JSON-compatible)
    """
    # Drones
    drones = {}
    for jid, info in snapshot["drones"].items():
        d = dict(info)
        if d.get("position"):
            lat, lon = grid_to_gps(d["position"])
            d["lat"] = lat
            d["lon"] = lon
            d["position"] = list(d["position"])
        if d.get("target"):
            t_lat, t_lon = grid_to_gps(d["target"])
            d["target_lat"] = t_lat
            d["target_lon"] = t_lon
            d["target"] = list(d["target"])
        # Format batterie
        if "battery" in d:
            d["battery"] = round(float(d["battery"]), 1)
        drones[jid] = d

    # Stations
    stations = {}
    for jid, info in snapshot["stations"].items():
        s = dict(info)
        lat, lon = grid_to_gps(s["position"])
        s["lat"] = lat
        s["lon"] = lon
        s["position"] = list(s["position"])
        stations[jid] = s

    # Customers
    customers = {}
    for jid, info in snapshot["customers"].items():
        c = dict(info)
        lat, lon = grid_to_gps(c["position"])
        c["lat"] = lat
        c["lon"] = lon
        c["position"] = list(c["position"])
        customers[jid] = c

    # Orders
    orders = {}
    for oid, info in snapshot["orders"].items():
        o = dict(info)
        p_lat, p_lon = grid_to_gps(o["pickup"])
        d_lat, d_lon = grid_to_gps(o["dropoff"])
        o["pickup"] = list(o["pickup"])
        o["dropoff"] = list(o["dropoff"])
        o["pickup_lat"] = p_lat
        o["pickup_lon"] = p_lon
        o["dropoff_lat"] = d_lat
        o["dropoff_lon"] = d_lon
        orders[oid] = o

    return {
        "drones": drones,
        "stations": stations,
        "customers": customers,
        "orders": orders,
        "weather": snapshot["weather"],
        "stats": snapshot["stats"],
        "events": snapshot["events"],
    }


# =============================================================================
# ENDPOINTS HTTP
# =============================================================================

@app.get("/")
async def serve_index():
    """Page principale : interface web."""
    return FileResponse(str(WEB_DIR / "index.html"))


@app.get("/api/geo")
async def geo_metadata():
    """Métadonnées GPS pour configurer la carte côté frontend."""
    return {
        "center": {"lat": UEMF_CENTER_LAT, "lon": UEMF_CENTER_LON},
        "bounds": {
            "south": LAT_MIN, "north": LAT_MAX,
            "west": LON_MIN, "east": LON_MAX,
        },
        "grid": {
            "width": Config.MAP_WIDTH,
            "height": Config.MAP_HEIGHT,
        },
        "campus_name": "Université Euromed de Fès (UEMF)",
    }


@app.get("/api/state")
async def get_state():
    """Snapshot ponctuel (debug / fallback si WebSocket KO)."""
    return enrich_snapshot(world_state.snapshot())


@app.get("/api/restaurants")
async def get_restaurants():
    """Liste de vrais restaurants de Fès (pour suggestions de pickup)."""
    return {"restaurants": RESTAURANTS}


# ============================================================================
# ENDPOINT — Création de commande manuelle (depuis le formulaire web)
# ============================================================================

class OrderRequest(BaseModel):
    """Schéma de validation pour POST /api/order."""
    customer_name: Optional[str] = Field(default="Client Web")
    pickup_lat: float
    pickup_lon: float
    dropoff_lat: float
    dropoff_lon: float
    description: Optional[str] = Field(default="Colis")


# Compteur global pour les JID uniques des clients web
_web_order_counter = 0


@app.post("/api/order")
async def create_order(req: OrderRequest):
    """
    Crée une commande manuelle depuis l'interface web.

    Flow :
        1. Le frontend envoie pickup (lat, lon) et dropoff (lat, lon)
        2. On convertit les GPS en coordonnées grille
        3. On ajoute la commande au WorldState
        4. Le simulation_loop (main.py) détecte la nouvelle commande
           et assigne automatiquement le drone le plus proche
        5. Le drone se met en route → l'utilisateur voit le mouvement en live

    Retourne : { order_id, message, drone_to_assign }
    """
    global _web_order_counter
    _web_order_counter += 1

    # Conversion des GPS en coordonnées grille (50×50)
    pickup_grid = gps_to_grid(req.pickup_lat, req.pickup_lon)
    dropoff_grid = gps_to_grid(req.dropoff_lat, req.dropoff_lon)

    # Identifiants uniques
    order_id = f"web_{_web_order_counter:04d}"
    customer_jid = f"webclient_{_web_order_counter}@localhost"

    # Enregistrement dans le WorldState
    world_state.register_customer(customer_jid, dropoff_grid)
    world_state.add_order(
        order_id=order_id,
        customer_jid=customer_jid,
        pickup=pickup_grid,
        dropoff=dropoff_grid,
    )

    # ===== Calcul de l'ETA basé sur le drone idle le plus proche =====
    snapshot = world_state.snapshot()
    idle_drones = {
        jid: tuple(d["position"])
        for jid, d in snapshot["drones"].items()
        if d.get("status") == "idle"
    }

    if idle_drones:
        # Drone le plus proche
        closest_jid, closest_pos = min(
            idle_drones.items(),
            key=lambda kv: euclidean_distance(kv[1], pickup_grid)
        )
        distance_km, time_min = estimate_delivery_time_minutes(
            start=closest_pos,
            pickup=pickup_grid,
            dropoff=dropoff_grid,
            drone_speed_kmh=Config.DRONE_SPEED_KMH,
        )
    else:
        distance_km = cells_to_km(
            euclidean_distance(pickup_grid, dropoff_grid)
        )
        time_min = (distance_km / Config.DRONE_SPEED_KMH) * 60
        closest_jid = None

    world_state.log_event(
        f"📩 {req.customer_name} → {order_id} ({req.description}) "
        f"≈ {distance_km:.2f}km / {time_min:.1f}min"
    )

    # Temps de simulation (accéléré)
    sim_time_seconds = (time_min * 60.0) / Config.SIMULATION_SPEEDUP

    return {
        "success": True,
        "order_id": order_id,
        "customer_name": req.customer_name,
        "pickup_grid": list(pickup_grid),
        "dropoff_grid": list(dropoff_grid),
        "distance_km": round(distance_km, 2),
        "estimated_time_min": round(time_min, 1),       # temps réel (vraie vie)
        "estimated_time_sim_s": round(sim_time_seconds, 1),   # temps à l'écran
        "simulation_speedup": Config.SIMULATION_SPEEDUP,
        "drone_speed_kmh": Config.DRONE_SPEED_KMH,
        "closest_drone": closest_jid,
        "message": (
            f"Commande {order_id} reçue ! "
            f"Distance ≈ {distance_km:.2f} km · "
            f"Livraison estimée en {time_min:.1f} min (réel)"
        ),
    }


# =============================================================================
# ENDPOINT WEBSOCKET — Push temps réel
# =============================================================================

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    WebSocket qui pousse l'état du monde toutes les 200 ms au client.
    Le frontend met à jour la carte et les graphiques à partir de ce flux.
    """
    await ws.accept()
    print("[WebServer] 🔌 Client WebSocket connecté")
    try:
        while True:
            snapshot = enrich_snapshot(world_state.snapshot())
            await ws.send_text(json.dumps(snapshot))
            await asyncio.sleep(0.2)   # 5 FPS d'update — fluide pour l'œil
    except WebSocketDisconnect:
        print("[WebServer] 🔌 Client WebSocket déconnecté")
    except Exception as e:
        print(f"[WebServer] ⚠️ Erreur WS : {e}")


# =============================================================================
# Assets statiques (CSS, JS, images)
# =============================================================================

# Sert /static/style.css, /static/app.js, /static/assets/*
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


# =============================================================================
# Lancement programmatique (depuis main.py)
# =============================================================================

async def run_web_server(host: str = "127.0.0.1", port: int = 8000):
    """Lance le serveur Uvicorn en mode programmatique (non-bloquant)."""
    import uvicorn
    config = uvicorn.Config(
        app, host=host, port=port,
        log_level="warning",   # silencieux (pas d'access log pour chaque WS)
    )
    server = uvicorn.Server(config)
    print(f"[WebServer] 🌐 Interface web disponible : http://{host}:{port}")
    await server.serve()

"""
=============================================================================
MAIN — Orchestrateur principal du système Drone Delivery SMA
=============================================================================

ARCHITECTURE :

    ┌──────────────────────────────────────────────────────────────┐
    │                                                                │
    │   [ 5 DroneAgents BDI ]  ── FIPA-ACL ─►  [ DispatcherAgent ]  │
    │   [ 3 StationAgents   ]  (Contract-Net) [ WeatherAgent ]      │
    │   [ N CustomerAgents  ]                                        │
    │           │                                                    │
    │           ▼                                                    │
    │    [ WorldState ]  (thread-safe)                              │
    │           │                                                    │
    │           ▼                                                    │
    │    [ FastAPI + WebSocket ]  (push 5 FPS)                      │
    │           │                                                    │
    │           ▼                                                    │
    │    [ Interface Web ]  (HTML/Tailwind/Leaflet + Chart.js)      │
    │                                                                │
    └──────────────────────────────────────────────────────────────┘

PREREQUIS :
    1) Modèle ML (auto-généré si absent)
    2) Serveur XMPP : terminal séparé → python server.py
    3) Dépendances  : pip install -r requirements.txt

LANCEMENT :
    python main.py
    → ouvre http://localhost:8000 dans le navigateur
=============================================================================
"""

import asyncio
import os
import random
import threading
import time
import webbrowser

import spade

from utils.ontologies import JID, Config
from utils.city_map import random_position, cells_to_km
from utils.world_state import world_state
from ml.delivery_predictor import get_predictor

from agents.dispatcher_agent import DispatcherAgent
from agents.weather_agent import WeatherAgent
from agents.station_agent import StationAgent
from agents.drone_agent import DroneAgent
from agents.customer_agent import CustomerAgent

from api.web_server import run_web_server


# ============================================================================
# Génération continue de commandes (simulation)
# ============================================================================
async def spawn_customers_loop(spawn_period: float):
    """Crée un nouveau CustomerAgent toutes les `spawn_period` secondes."""
    customer_counter = 0

    # Petit délai initial pour laisser les agents se connecter au XMPP
    await asyncio.sleep(Config.CUSTOMER_FIRST_DELAY)

    while True:
        customer_counter += 1
        customer_jid = JID.customer(customer_counter)

        pickup = random_position()
        dropoff = random_position()
        while dropoff == pickup:
            dropoff = random_position()

        customer = CustomerAgent(
            jid=customer_jid,
            password=JID.PASSWORD,
            position=pickup,
            dropoff=dropoff,
        )

        try:
            await customer.start(auto_register=True)
            print(f"[Main] 👤 Nouveau client : {customer_jid} ({pickup} → {dropoff})")
        except Exception as e:
            print(f"[Main] ⚠️ Échec démarrage client : {e}")

        # Attente avant la prochaine commande
        await asyncio.sleep(spawn_period)


# ============================================================================
# Vérification du modèle ML
# ============================================================================
def ensure_ml_model_exists():
    """Vérifie que le modèle ML est entraîné, sinon le génère automatiquement."""
    here = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(here, "ml", "delivery_model.joblib")

    if not os.path.exists(model_path):
        print("[Main] ⚠️ Modèle ML manquant — entraînement automatique...")
        from ml.train_model import train_and_save
        train_and_save(model_path)
    else:
        print(f"[Main] ✅ Modèle ML trouvé : {os.path.basename(model_path)}")


# ============================================================================
# Positions fixes des agents (utilisées pour pré-enregistrement + démarrage)
# ============================================================================
STATION_POSITIONS = [(10, 10), (40, 10), (25, 40)]

# Les 5 drones ont leur "parking" autour de l'UEMF (centre grille = 25, 25).
# Espacés pour ne PAS se chevaucher visuellement.
DRONE_HOME_POSITIONS = [
    (23, 24),    # drone1 — UEMF parking NW
    (27, 24),    # drone2 — UEMF parking NE
    (25, 23),    # drone3 — UEMF parking N
    (23, 27),    # drone4 — UEMF parking SW
    (27, 27),    # drone5 — UEMF parking SE
]
DRONE_POSITIONS = DRONE_HOME_POSITIONS   # positions initiales = parkings


# ============================================================================
# HÉTÉROGÉNÉITÉ DES DRONES — 5 PROFILS DISTINCTS
# ============================================================================
# Cœur de la valeur SMA : chaque drone a ses propres caractéristiques.
# Le Contract-Net devient COMPÉTITIF — chaque drone propose un coût
# différent selon ses capacités.
DRONE_PROFILES = {
    "drone1@localhost": {
        "name": "FALCON",
        "type": "Rapide & léger",
        "icon": "🦅",
        "cargo_max_kg": 2.0,         # petit cargo
        "speed_kmh": 65,             # rapide
        "battery_max": 80,           # batterie modeste
        "cost_per_km": 8.0,          # cher (drone premium)
        "color": "#22d3ee",          # cyan
    },
    "drone2@localhost": {
        "name": "VOYAGER",
        "type": "Polyvalent",
        "icon": "🚁",
        "cargo_max_kg": 5.0,
        "speed_kmh": 50,             # standard
        "battery_max": 100,
        "cost_per_km": 5.0,          # équilibré
        "color": "#34d399",          # green
    },
    "drone3@localhost": {
        "name": "HERCULES",
        "type": "Gros porteur",
        "icon": "🛩️",
        "cargo_max_kg": 12.0,        # GROS cargo
        "speed_kmh": 35,             # lent
        "battery_max": 120,
        "cost_per_km": 6.0,
        "color": "#fbbf24",          # amber
    },
    "drone4@localhost": {
        "name": "PHANTOM",
        "type": "VIP Express",
        "icon": "⚡",
        "cargo_max_kg": 3.0,
        "speed_kmh": 75,             # le plus rapide
        "battery_max": 85,
        "cost_per_km": 12.0,         # le plus cher
        "color": "#d946ef",          # fuchsia
    },
    "drone5@localhost": {
        "name": "ECOFLY",
        "type": "Éco-autonomie",
        "icon": "🌿",
        "cargo_max_kg": 4.0,
        "speed_kmh": 40,             # lent
        "battery_max": 150,          # batterie XXL
        "cost_per_km": 3.5,          # le moins cher
        "color": "#a78bfa",          # violet
    },
}


def preregister_agents_in_world_state():
    """
    Pré-enregistre les drones et stations dans le WorldState AVANT que les
    vrais agents SPADE soient connectés.

    Pourquoi ? → l'interface web affiche tout immédiatement (drones visibles
    sur la carte dès le démarrage), sans attendre l'enregistrement XMPP qui
    prend ~10-15 secondes.

    Quand les vrais agents se connecteront, ils mettront à jour ces entrées.
    """
    for jid, pos in zip(JID.STATIONS, STATION_POSITIONS):
        world_state.register_station(jid, pos)

    for jid, pos in zip(JID.DRONES, DRONE_POSITIONS):
        profile = DRONE_PROFILES.get(jid, {})
        world_state.register_drone(jid, pos, profile=profile)

    world_state.log_event("🚁 5 drones hétérogènes pré-enregistrés (Falcon/Voyager/Hercules/Phantom/EcoFly)")


# ============================================================================
# SIMULATEUR CONTINU (patrouille + gestion des missions visuelles)
# ============================================================================
def _step_toward(pos, target):
    """Avance d'1 cellule vers la cible (mouvement diagonal autorisé)."""
    new_x = pos[0] + (1 if target[0] > pos[0] else -1 if target[0] < pos[0] else 0)
    new_y = pos[1] + (1 if target[1] > pos[1] else -1 if target[1] < pos[1] else 0)
    return (new_x, new_y)


def _distance(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


async def simulation_loop():
    """
    Simulateur continu — Architecture inspirée du Contract-Net Protocol :

    Quand une nouvelle commande arrive (status="pending") :
      1. CFP simulé : chaque drone idle calcule son coût (distance + batterie)
      2. PROPOSE loggué dans les events (visible par l'utilisateur)
      3. Le drone au coût minimal est sélectionné → ACCEPT
      4. Les autres reçoivent un REJECT (loggué)
      5. Le drone gagnant part en mission

    Quand idle, les drones REVIENNENT à leur position de parking UEMF
    et y restent stationnaires (pas de patrouille aléatoire).

    Anti-collision : aucun drone ne peut se déplacer sur une case occupée.
    """
    drone_missions = {}      # {drone_jid: {order_id, pickup, dropoff, customer_jid}}
    drone_homes = dict(zip(JID.DRONES, DRONE_HOME_POSITIONS))

    # Système de "crédit de mouvement" : chaque drone accumule du crédit à chaque
    # tick. Quand crédit ≥ 1, il bouge d'une cellule. Le crédit est inversement
    # proportionnel à la vitesse → drones rapides bougent plus souvent.
    move_credits = {jid: 0.0 for jid in JID.DRONES}
    tick_seconds = Config.SIMULATION_TICK_SECONDS

    def credit_per_tick(jid: str) -> float:
        """Crédit gagné par tick selon la vitesse réelle du drone."""
        profile = DRONE_PROFILES.get(jid, {})
        speed = profile.get("speed_kmh", Config.REFERENCE_SPEED_KMH)
        # À 50 km/h → 1/5 = 0.2 cell/tick (5 ticks par cellule)
        # À 75 km/h → 0.3 cell/tick (3.33 ticks par cellule)
        # À 35 km/h → 0.14 cell/tick (7.14 ticks par cellule)
        return (speed / Config.REFERENCE_SPEED_KMH) / Config.REFERENCE_TICKS_PER_CELL

    while True:
        await asyncio.sleep(tick_seconds)
        snapshot = world_state.snapshot()

        # ===== ETAPE 1 : Contract-Net pour les nouvelles commandes =====
        pending_orders = [
            (oid, order) for oid, order in snapshot["orders"].items()
            if order.get("status") == "pending" and not order.get("drone")
        ]

        for oid, order in pending_orders:
            pickup = tuple(order["pickup"])
            dropoff = tuple(order["dropoff"])

            # Récupérer tous les drones idle (workers participants au CFP)
            idle_drones = {
                jid: tuple(d["position"])
                for jid, d in snapshot["drones"].items()
                if d.get("status") == "idle" and jid not in drone_missions
            }

            if not idle_drones:
                continue  # personne de dispo, on retentera au prochain tick

            # ===== CFP simulé : chaque drone calcule son coût SELON SON PROFIL =====
            # C'est ICI que la sociabilité SMA prend tout son sens : chaque drone
            # propose un coût différent en fonction de ses propres capacités.
            costs = {}        # {jid: cost_score}
            details = {}      # {jid: (time_min, price_eur, eligible)}

            for cand_jid, cand_pos in idle_drones.items():
                cand = snapshot["drones"][cand_jid]
                cand_battery = cand.get("battery", 100)
                profile = cand.get("profile", {}) or DRONE_PROFILES.get(cand_jid, {})

                # Caractéristiques du drone
                speed_kmh = profile.get("speed_kmh", 50)
                cost_per_km = profile.get("cost_per_km", 5.0)
                battery_max = profile.get("battery_max", 100)

                # Distance totale (drone → pickup → dropoff)
                d_pickup_cells = _distance(cand_pos, pickup)
                d_total_cells = d_pickup_cells + _distance(pickup, dropoff)
                d_km = cells_to_km(d_total_cells)

                # Temps réel basé sur la vitesse du drone
                time_min = (d_km / speed_kmh) * 60.0
                # Prix proposé par le drone
                price_eur = d_km * cost_per_km

                # Pénalité si batterie faible (refuse si critique)
                battery_pct = (cand_battery / battery_max) * 100
                eligible = battery_pct > 20  # 20% mini

                if not eligible:
                    world_state.log_event(
                        f"  ❌ {profile.get('name', cand_jid.split('@')[0])} "
                        f"REFUSE (batterie {battery_pct:.0f}%)"
                    )
                    continue

                # COÛT GLOBAL = combinaison de temps + prix (pondéré)
                cost = time_min * 1.0 + price_eur * 0.4
                # Bonus si batterie élevée
                cost *= (1.0 + 0.2 * (1.0 - battery_pct / 100))

                costs[cand_jid] = cost
                details[cand_jid] = (time_min, price_eur, d_km)

            if not costs:
                world_state.log_event(f"⚠️ {oid} : aucun drone disponible")
                continue

            # Logging du CFP
            world_state.log_event(
                f"📢 CFP {oid} → {len(costs)} drones soumissionnent"
            )

            # ===== Sélection du gagnant (coût minimum) =====
            winner_jid = min(costs, key=costs.get)
            winner_profile = DRONE_PROFILES.get(winner_jid, {})

            # Log détaillé de chaque proposition (style enchère)
            sorted_costs = sorted(costs.items(), key=lambda x: x[1])
            for rank, (cand_jid, cost) in enumerate(sorted_costs, 1):
                prof = DRONE_PROFILES.get(cand_jid, {})
                name = prof.get("name", cand_jid.split('@')[0])
                time_min, price, dist = details[cand_jid]
                if rank == 1:
                    world_state.log_event(
                        f"🏆 {prof.get('icon', '')} {name} GAGNE — "
                        f"{time_min:.1f}min / {price:.1f}€"
                    )
                elif rank <= 3:
                    world_state.log_event(
                        f"  ↳ {prof.get('icon', '')} {name} : "
                        f"{time_min:.1f}min / {price:.1f}€"
                    )

            # ===== Assignation =====
            drone_missions[winner_jid] = {
                "order_id": oid,
                "pickup": pickup,
                "dropoff": dropoff,
                "customer_jid": order.get("customer_jid"),
            }
            world_state.update_order(oid, drone=winner_jid, status="assigned")
            world_state.update_drone(
                winner_jid,
                status="moving_to_pickup",
                target=pickup,
            )

            # Met à jour le snapshot local pour les commandes suivantes
            snapshot["drones"][winner_jid]["status"] = "moving_to_pickup"

        # ===== ETAPE 2 : Faire bouger les drones (vitesse réelle !) =====
        # Positions actuelles (pour anti-collision)
        occupied_next = set()

        for jid in JID.DRONES:
            drone = snapshot["drones"].get(jid)
            if not drone:
                continue

            status = drone.get("status", "idle")
            pos = tuple(drone["position"])
            battery = drone.get("battery", 100)

            # === Système de CRÉDIT DE MOUVEMENT (vitesse réelle) ===
            # Le drone n'accumule du crédit QUE quand il doit bouger.
            # Quand crédit ≥ 1.0, il bouge d'une cellule.
            move_credits[jid] += credit_per_tick(jid)
            can_move = move_credits[jid] >= 1.0

            # ============= IDLE : retour à la base UEMF =============
            if status == "idle":
                # Recharge légère en idle
                if battery < 100:
                    world_state.update_drone(jid, battery=min(100, battery + 0.5))

                home = drone_homes.get(jid, (25, 25))
                if pos == home:
                    occupied_next.add(pos)   # stationnaire
                    # Reset crédit (drone à l'arrêt n'accumule pas)
                    move_credits[jid] = 0.0
                    continue

                # Retour à la base — seulement si crédit suffisant
                if not can_move:
                    occupied_next.add(pos)
                    continue

                candidate_next = _step_toward(pos, home)
                if candidate_next in occupied_next:
                    occupied_next.add(pos)   # attendre (crédit conservé)
                else:
                    occupied_next.add(candidate_next)
                    world_state.update_drone(jid, position=candidate_next)
                    move_credits[jid] -= 1.0   # consomme le crédit

            # ============= MOVING TO PICKUP =============
            elif status == "moving_to_pickup":
                mission = drone_missions.get(jid)
                target = tuple(mission["pickup"]) if mission else drone.get("target")
                if not target:
                    world_state.update_drone(jid, status="idle", target=None)
                    occupied_next.add(pos)
                    continue
                target = tuple(target)

                if pos == target:
                    # Arrivé au pickup → passe en carrying
                    next_target = tuple(mission["dropoff"]) if mission else None
                    world_state.update_drone(
                        jid,
                        status="carrying",
                        target=next_target,
                        payload=mission["order_id"] if mission else None,
                    )
                    world_state.log_event(
                        f"📦 {jid.split('@')[0]} a récupéré le colis"
                    )
                    occupied_next.add(pos)
                elif can_move:
                    candidate_next = _step_toward(pos, target)
                    if candidate_next in occupied_next:
                        occupied_next.add(pos)   # attendre (crédit conservé)
                    else:
                        occupied_next.add(candidate_next)
                        world_state.update_drone(
                            jid,
                            position=candidate_next,
                            battery=max(10, battery - 0.4),
                        )
                        move_credits[jid] -= 1.0
                else:
                    occupied_next.add(pos)   # pas encore assez de crédit

            # ============= CARRYING (vers dropoff) =============
            elif status == "carrying":
                mission = drone_missions.get(jid)
                target = tuple(mission["dropoff"]) if mission else drone.get("target")
                if not target:
                    world_state.update_drone(jid, status="idle", target=None, payload=None)
                    occupied_next.add(pos)
                    continue
                target = tuple(target)

                if pos == target:
                    # LIVRAISON RÉUSSIE !
                    if mission:
                        world_state.complete_order(mission["order_id"], success=True)
                        world_state.log_event(
                            f"✅ {jid.split('@')[0]} a livré {mission['order_id']}"
                        )
                        if mission.get("customer_jid"):
                            world_state.remove_customer(mission["customer_jid"])
                        drone_missions.pop(jid, None)
                    world_state.update_drone(
                        jid,
                        status="idle",
                        target=None,
                        payload=None,
                    )
                    occupied_next.add(pos)
                elif can_move:
                    candidate_next = _step_toward(pos, target)
                    if candidate_next in occupied_next:
                        occupied_next.add(pos)   # attendre (crédit conservé)
                    else:
                        occupied_next.add(candidate_next)
                        world_state.update_drone(
                            jid,
                            position=candidate_next,
                            battery=max(10, battery - 0.4),
                        )
                        move_credits[jid] -= 1.0
                else:
                    occupied_next.add(pos)   # pas encore assez de crédit


# ============================================================================
# Démarrage de tous les agents système — EN PARALLELE (asyncio.gather)
# ============================================================================
async def start_all_agents():
    """Démarre tous les agents en parallèle (3-5x plus rapide que séquentiel)."""
    print("[Main] ⏳ Démarrage des 10 agents en parallèle...")

    # Création des agents (instances Python, pas encore connectés à XMPP)
    dispatcher = DispatcherAgent(JID.DISPATCHER, JID.PASSWORD)
    weather = WeatherAgent(JID.WEATHER, JID.PASSWORD)
    stations = [
        StationAgent(jid, JID.PASSWORD, position=pos)
        for jid, pos in zip(JID.STATIONS, STATION_POSITIONS)
    ]
    drones = [
        DroneAgent(jid, JID.PASSWORD, position=pos)
        for jid, pos in zip(JID.DRONES, DRONE_POSITIONS)
    ]

    # Démarrage XMPP en parallèle (tous les start() lancés en même temps)
    all_agents = [dispatcher, weather] + stations + drones

    async def _start_one(agent):
        try:
            await agent.start(auto_register=True)
            print(f"[Main]   ✅ {agent.jid}")
        except Exception as e:
            print(f"[Main]   ❌ {agent.jid} : {e}")

    await asyncio.gather(*(_start_one(a) for a in all_agents))

    print(f"[Main] ✅ {len(all_agents)} agents actifs.")
    return dispatcher, weather, stations, drones


# ============================================================================
# MAIN
# ============================================================================
async def main():
    print("\n" + "═" * 64)
    print("  🚁  DRONE DELIVERY SMA  —  Université Euromed de Fès")
    print("═" * 64 + "\n")

    # 0. Modèle ML (auto-gen si absent)
    ensure_ml_model_exists()
    get_predictor()

    # 0.b — PRÉ-ENREGISTREMENT des drones et stations dans le WorldState
    # → l'interface web les affichera IMMÉDIATEMENT, sans attendre les agents.
    preregister_agents_in_world_state()

    # 0.c — Simulateur continu (patrouille + missions visuelles)
    # Tourne en arrière-plan tout le temps : fait bouger les drones idle en
    # patrouille, et assigne les commandes au drone le plus proche.
    sim_task = asyncio.create_task(simulation_loop())

    # 1. ⭐ DEMARRAGE DU SERVEUR WEB EN PREMIER ⭐
    # Comme ça l'interface est dispo IMMEDIATEMENT (vide au début, puis se remplit
    # au fur et à mesure que les agents démarrent).
    print("\n[Main] 🌐 Démarrage de l'interface web...")
    web_task = asyncio.create_task(run_web_server(host="127.0.0.1", port=8000))
    await asyncio.sleep(1.5)   # laisser uvicorn finir son binding sur :8000

    # 1.b — Ouverture AUTOMATIQUE du navigateur
    def _open_browser():
        time.sleep(1.0)
        url = "http://localhost:8000"
        try:
            webbrowser.open(url, new=2)
            print(f"[Main] 🌍 Navigateur ouvert sur {url}")
        except Exception as e:
            print(f"[Main] ⚠️ Impossible d'ouvrir le navigateur : {e}")
            print(f"[Main]    Ouvre manuellement : {url}")

    threading.Thread(target=_open_browser, daemon=True).start()

    print("\n" + "─" * 64)
    print("  ✅  Interface web prête : http://localhost:8000")
    print("  ⏳  Démarrage des agents... (les drones apparaîtront à l'écran)")
    print("─" * 64 + "\n")

    # 2. Démarrage des agents SMA (l'utilisatrice les voit apparaître en live)
    dispatcher, weather, stations, drones = await start_all_agents()

    # 3. Les commandes viennent maintenant uniquement de l'interface web
    # (formulaire "Passer une commande"). Le simulation_loop assigne les
    # drones automatiquement. Pas besoin de spawn auto.

    # On attend uniquement le web_task + sim_task (tournent indéfiniment)
    try:
        await asyncio.gather(web_task, sim_task)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass

    # 4. Arrêt propre
    print("\n[Main] 🛑 Arrêt du système...")
    await dispatcher.stop()
    await weather.stop()
    for s in stations:
        await s.stop()
    for d in drones:
        await d.stop()
    print("[Main] 👋 Système arrêté proprement.")


if __name__ == "__main__":
    spade.run(main())

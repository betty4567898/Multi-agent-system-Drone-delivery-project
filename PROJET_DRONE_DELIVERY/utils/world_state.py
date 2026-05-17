"""
=============================================================================
WORLD STATE — État partagé thread-safe
=============================================================================

POURQUOI CE FICHIER ?
    Les agents SPADE tournent en asyncio (boucle d'événements unique).
    Pygame, lui, a sa propre boucle de rendu (dans un thread séparé).

    Pour que Pygame puisse afficher l'état des agents EN TEMPS REEL sans
    bloquer les agents, on utilise un état partagé protégé par un verrou.

PATTERN UTILISE:
    Singleton + threading.Lock
    → Un seul WorldState global, accessible depuis n'importe quel agent
       ou depuis le dashboard Pygame.

USAGE:
    >>> from utils.world_state import world_state
    >>> world_state.update_drone("drone1@localhost", position=(10, 5), battery=85)
    >>> snapshot = world_state.snapshot()   # copie pour Pygame
=============================================================================
"""

import threading
import copy
from typing import Optional

from utils.city_map import Position


class WorldState:
    """
    État global du monde, partagé entre les agents (écrivains) et le dashboard
    Pygame (lecteur).
    """

    def __init__(self):
        self._lock = threading.RLock()   # réentrant (un même thread peut re-acquérir)

        # Entités du monde
        self.drones: dict = {}           # {jid: {position, battery, status, payload, mission}}
        self.stations: dict = {}         # {jid: {position, occupied_by}}
        self.customers: dict = {}        # {jid: {position}}
        self.orders: dict = {}           # {order_id: {customer_jid, pickup, dropoff, status, drone}}

        # Environnement
        self.weather: str = "clear"

        # Statistiques globales
        self.stats: dict = {
            "deliveries_completed": 0,
            "deliveries_failed": 0,
            "total_orders": 0,
            "active_orders": 0,
        }

        # Log d'événements (les 20 derniers) pour affichage Pygame
        self.events: list = []

    # ========== DRONES ==========

    def register_drone(self, jid: str, position: Position, profile: Optional[dict] = None):
        with self._lock:
            self.drones[jid] = {
                "position": position,
                "battery": (profile or {}).get("battery_max", 100.0),
                "status": "idle",
                "payload": None,
                "mission": None,
                "target": None,
                "profile": profile or {},   # caractéristiques (nom, vitesse, cargo...)
            }

    def update_drone(self, jid: str, **kwargs):
        with self._lock:
            if jid not in self.drones:
                return
            self.drones[jid].update(kwargs)

    def get_drone(self, jid: str) -> Optional[dict]:
        with self._lock:
            return copy.deepcopy(self.drones.get(jid))

    # ========== STATIONS ==========

    def register_station(self, jid: str, position: Position):
        with self._lock:
            self.stations[jid] = {
                "position": position,
                "occupied_by": None,
            }

    def occupy_station(self, jid: str, drone_jid: str) -> bool:
        """Tente d'occuper une station. Retourne True si réussi."""
        with self._lock:
            station = self.stations.get(jid)
            if station and station["occupied_by"] is None:
                station["occupied_by"] = drone_jid
                return True
            return False

    def release_station(self, jid: str):
        with self._lock:
            if jid in self.stations:
                self.stations[jid]["occupied_by"] = None

    # ========== CUSTOMERS ==========

    def register_customer(self, jid: str, position: Position):
        with self._lock:
            self.customers[jid] = {"position": position}

    def remove_customer(self, jid: str):
        with self._lock:
            self.customers.pop(jid, None)

    # ========== ORDERS ==========

    def add_order(self, order_id: str, customer_jid: str, pickup: Position, dropoff: Position):
        with self._lock:
            self.orders[order_id] = {
                "customer_jid": customer_jid,
                "pickup": pickup,
                "dropoff": dropoff,
                "status": "pending",
                "drone": None,
            }
            self.stats["total_orders"] += 1
            self.stats["active_orders"] += 1
            self.log_event(f"📦 Nouvelle commande {order_id}")

    def update_order(self, order_id: str, **kwargs):
        with self._lock:
            if order_id in self.orders:
                self.orders[order_id].update(kwargs)

    def complete_order(self, order_id: str, success: bool = True):
        with self._lock:
            if order_id in self.orders:
                self.orders[order_id]["status"] = "completed" if success else "failed"
                self.stats["active_orders"] = max(0, self.stats["active_orders"] - 1)
                if success:
                    self.stats["deliveries_completed"] += 1
                    self.log_event(f"✅ Commande {order_id} livrée !")
                else:
                    self.stats["deliveries_failed"] += 1
                    self.log_event(f"❌ Commande {order_id} échouée")

    # ========== WEATHER ==========

    def set_weather(self, weather: str):
        with self._lock:
            if weather != self.weather:
                self.log_event(f"🌤️ Météo: {weather}")
            self.weather = weather

    # ========== EVENTS LOG ==========

    def log_event(self, message: str):
        """Ajoute un événement au log (rolling buffer de 20 entrées)."""
        with self._lock:
            self.events.append(message)
            if len(self.events) > 20:
                self.events.pop(0)

    # ========== SNAPSHOT (pour Pygame) ==========

    def snapshot(self) -> dict:
        """
        Retourne une copie cohérente de l'état complet, pour rendu.
        Cette copie est sans risque pour Pygame (pas de verrou à acquérir pendant le rendu).
        """
        with self._lock:
            return {
                "drones": copy.deepcopy(self.drones),
                "stations": copy.deepcopy(self.stations),
                "customers": copy.deepcopy(self.customers),
                "orders": copy.deepcopy(self.orders),
                "weather": self.weather,
                "stats": copy.deepcopy(self.stats),
                "events": list(self.events),
            }


# Singleton global accessible à tous les agents et au dashboard
world_state = WorldState()

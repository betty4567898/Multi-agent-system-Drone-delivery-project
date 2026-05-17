"""
=============================================================================
ONTOLOGIES FIPA-ACL — Constantes du système Drone Delivery
=============================================================================

OBJECTIF:
    Définir le vocabulaire partagé entre tous les agents du système.
    En FIPA-ACL, l'ontologie est CRUCIALE : c'est ce qui permet aux agents
    de se comprendre malgré leur hétérogénéité.

RAPPEL DU COURS:
    "Si Agent A envoie 'Temperature = 30', est-ce 30°C ou 30°F ?"
    → L'ontologie résout cette ambiguïté en définissant le contexte.

UTILISATION:
    >>> from utils.ontologies import Ontology, Performative
    >>> msg.set_metadata("ontology", Ontology.DELIVERY_REQUEST)
    >>> msg.set_metadata("performative", Performative.CFP)
=============================================================================
"""


class Ontology:
    """Vocabulaires partagés entre agents."""

    # Cycle de vie d'une livraison (Contract-Net Protocol)
    DELIVERY_REQUEST = "delivery-request"        # Client → Dispatcher
    DELIVERY_CFP = "delivery-cfp"                # Dispatcher → Drones (appel d'offres)
    DELIVERY_PROPOSAL = "delivery-proposal"      # Drones → Dispatcher (coût)
    DELIVERY_AWARD = "delivery-award"            # Dispatcher → Drone gagnant
    DELIVERY_REJECT = "delivery-reject"          # Dispatcher → Drones perdants
    DELIVERY_STATUS = "delivery-status"          # Drone → Client (en route, livré)

    # Gestion énergétique (Station de recharge)
    CHARGING_REQUEST = "charging-request"        # Drone → Station
    CHARGING_GRANT = "charging-grant"            # Station → Drone (autorisation)
    CHARGING_DENY = "charging-deny"              # Station → Drone (station pleine)
    CHARGING_COMPLETE = "charging-complete"      # Drone → Station (fin recharge)

    # Diffusion d'environnement (Météo)
    WEATHER_UPDATE = "weather-update"            # WeatherAgent → tous

    # Heartbeat / supervision
    DRONE_STATUS = "drone-status"                # Drone → Dispatcher (état périodique)


class Performative:
    """Performatives FIPA-ACL utilisées (sous-ensemble des 22 standards)."""

    # Information
    INFORM = "inform"
    QUERY_IF = "query-if"

    # Action
    REQUEST = "request"
    AGREE = "agree"
    REFUSE = "refuse"

    # Négociation (Contract-Net)
    CFP = "cfp"                          # Call For Proposal
    PROPOSE = "propose"
    ACCEPT_PROPOSAL = "accept-proposal"
    REJECT_PROPOSAL = "reject-proposal"

    # Erreur
    FAILURE = "failure"
    NOT_UNDERSTOOD = "not-understood"


class JID:
    """Identifiants XMPP des agents (centralisé pour éviter les fautes de frappe)."""

    SERVER = "localhost"
    PASSWORD = "password"

    DISPATCHER = "dispatcher@localhost"
    WEATHER = "weather@localhost"

    # Drones (5 unités)
    DRONES = [f"drone{i}@localhost" for i in range(1, 6)]

    # Stations de recharge (3 unités)
    STATIONS = [f"station{i}@localhost" for i in range(1, 4)]

    # Customers (générés dynamiquement)
    @staticmethod
    def customer(idx: int) -> str:
        return f"customer{idx}@localhost"


# Constantes de simulation
class Config:
    """Paramètres globaux du système."""

    # Carte
    MAP_WIDTH = 50          # cellules
    MAP_HEIGHT = 50

    # Drones — caractéristiques RÉELLES
    BATTERY_MAX = 100.0
    BATTERY_LOW_THRESHOLD = 25.0     # déclenche recharge
    BATTERY_CRITICAL = 10.0          # urgence
    BATTERY_CONSUMPTION_PER_STEP = 0.5
    BATTERY_RECHARGE_RATE = 5.0      # par tick
    DRONE_SPEED = 1                  # cellules par tick (simulation)
    DRONE_TICK_DELAY = 0.3           # secondes entre 2 mouvements

    # Vitesse RÉELLE (pour calculs d'ETA)
    DRONE_SPEED_KMH = 50.0           # vitesse réaliste d'un drone de livraison

    # ===== Vitesse SIMULATION ↔ vitesse RÉELLE =====
    # Combien d'accélération entre temps réel et temps simulation.
    # SIMULATION_SPEEDUP = 15 → 1 minute réelle = 4 secondes à l'écran
    # Permet une démo observable sans être trop rapide.
    SIMULATION_SPEEDUP = 15.0

    # Référence : à 50 km/h, un drone met combien de TICKS pour traverser 1 cellule ?
    # 1 cellule = ~200m, donc à 50 km/h (13.9 m/s) = 14.4s réelles par cellule
    # En simulation accélérée 15x : 14.4 / 15 = 0.96s par cellule
    # Avec tick = 0.2s : 0.96 / 0.2 = ~5 ticks par cellule
    SIMULATION_TICK_SECONDS = 0.20
    REFERENCE_SPEED_KMH = 50.0
    REFERENCE_TICKS_PER_CELL = 5.0   # à 50 km/h

    # Météo (multiplicateur de consommation)
    WEATHER_MULTIPLIERS = {
        "clear": 1.0,
        "windy": 1.5,
        "rainy": 2.0,
        "stormy": 3.0,
    }

    # Génération clients (RAPIDE — démarrage instantané)
    CUSTOMER_SPAWN_PERIOD = 2.5      # secondes entre 2 commandes
    CUSTOMER_FIRST_DELAY = 0.5       # délai avant la 1ère commande (quasi immédiat)

    # Contract-Net
    CFP_TIMEOUT = 2.0                # secondes d'attente des propositions

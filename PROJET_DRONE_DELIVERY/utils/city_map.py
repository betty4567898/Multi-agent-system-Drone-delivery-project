"""
=============================================================================
CITY MAP — Représentation de la ville (grille 2D + projection GPS)
=============================================================================

ROLE:
    Fournir les fonctions géométriques pour la simulation :
    - Distance entre deux points (Manhattan ou Euclidienne)
    - Calcul du prochain pas pour rejoindre une cible
    - Génération de positions aléatoires
    - Conversion grille ↔ coordonnées GPS réelles (pour l'affichage web Leaflet)

CHOIX TECHNIQUE:
    Grille interne 50×50 pour les agents (simple, performant).
    Projection GPS sur la zone autour de l'Université Euromed de Fès (UEMF)
    pour l'affichage carte web (Leaflet/OpenStreetMap).
=============================================================================
"""

import math
import random
from typing import Tuple

from utils.ontologies import Config

Position = Tuple[int, int]

# =============================================================================
# Coordonnées GPS — Zone Université Euromed de Fès (UEMF)
# =============================================================================
# Centre : UEMF Eco-Campus — Rond-Point Bensouda, Route Nationale Fès-Meknès
# Coordonnées GPS officielles (sortie vers Moulay Yaacoub) :
UEMF_CENTER_LAT = 34.04501      # 34.04501° N
UEMF_CENTER_LON = -5.06529      # 5.06529° O

# Zone d'opération élargie pour couvrir UEMF + médina + zones commerciales
# de Fès (Borj Fez, Saiss, Bensouda, médina)
ZONE_HALF_LAT = 0.045           # ~5 km nord-sud
ZONE_HALF_LON = 0.055           # ~5 km est-ouest

# Conversion grille ↔ kilomètres réels
# Zone totale ≈ 10 km × 10 km, grille 50×50 → 1 cellule ≈ 200 m
KM_PER_DEGREE_LAT = 111.0                                # km par degré de latitude
GRID_KM_WIDTH = ZONE_HALF_LON * 2 * KM_PER_DEGREE_LAT * 0.83   # cos(34°) ≈ 0.83
GRID_KM_HEIGHT = ZONE_HALF_LAT * 2 * KM_PER_DEGREE_LAT

LAT_MIN = UEMF_CENTER_LAT - ZONE_HALF_LAT
LAT_MAX = UEMF_CENTER_LAT + ZONE_HALF_LAT
LON_MIN = UEMF_CENTER_LON - ZONE_HALF_LON
LON_MAX = UEMF_CENTER_LON + ZONE_HALF_LON


def grid_to_gps(pos: Position) -> Tuple[float, float]:
    """
    Convertit une position grille (x, y) en coordonnées GPS (lat, lon).
    La grille a son origine (0,0) en haut à gauche (nord-ouest).
    """
    x, y = pos
    lon = LON_MIN + (x / (Config.MAP_WIDTH - 1)) * (LON_MAX - LON_MIN)
    # y va du nord (0) au sud (MAP_HEIGHT-1) — inverser pour la latitude
    lat = LAT_MAX - (y / (Config.MAP_HEIGHT - 1)) * (LAT_MAX - LAT_MIN)
    return (lat, lon)


def gps_to_grid(lat: float, lon: float) -> Position:
    """Conversion inverse GPS → grille."""
    x = int(round((lon - LON_MIN) / (LON_MAX - LON_MIN) * (Config.MAP_WIDTH - 1)))
    y = int(round((LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * (Config.MAP_HEIGHT - 1)))
    return (max(0, min(Config.MAP_WIDTH - 1, x)),
            max(0, min(Config.MAP_HEIGHT - 1, y)))


def random_position() -> Position:
    """Génère une position aléatoire dans la carte."""
    return (
        random.randint(0, Config.MAP_WIDTH - 1),
        random.randint(0, Config.MAP_HEIGHT - 1),
    )


def euclidean_distance(p1: Position, p2: Position) -> float:
    """Distance euclidienne (à vol d'oiseau, plus réaliste pour un drone)."""
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def manhattan_distance(p1: Position, p2: Position) -> int:
    """Distance Manhattan (utile pour estimations rapides)."""
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


def next_step(current: Position, target: Position) -> Position:
    """
    Calcule le prochain pas pour rejoindre une cible (mouvement diagonal autorisé).

    Le drone avance d'1 case dans chaque direction (x et y) à la fois,
    sauf si déjà aligné sur un axe.
    """
    x, y = current
    tx, ty = target

    if x < tx:
        x += 1
    elif x > tx:
        x -= 1

    if y < ty:
        y += 1
    elif y > ty:
        y -= 1

    return (x, y)


def has_arrived(current: Position, target: Position) -> bool:
    """Vérifie si le drone a atteint la cible (case exacte)."""
    return current == target


def closest_point(origin: Position, candidates: list) -> Tuple[int, Position]:
    """
    Retourne (index, position) du point le plus proche parmi 'candidates'.
    Utile pour trouver la station de recharge la plus proche.
    """
    distances = [euclidean_distance(origin, p) for p in candidates]
    best_idx = distances.index(min(distances))
    return best_idx, candidates[best_idx]


def cells_to_km(cells: float) -> float:
    """Convertit une distance en cellules vers une distance réelle en kilomètres."""
    # Moyenne des dimensions x/y (la zone n'est pas parfaitement carrée)
    avg_km_per_cell = ((GRID_KM_WIDTH + GRID_KM_HEIGHT) / 2) / Config.MAP_WIDTH
    return cells * avg_km_per_cell


def estimate_delivery_time_minutes(
    start: Position, pickup: Position, dropoff: Position,
    drone_speed_kmh: float = 50.0,
) -> Tuple[float, float]:
    """
    Estime la distance et le temps réels d'une livraison.

    Returns:
        (distance_km, temps_minutes)
    """
    # Distance en cellules : start → pickup → dropoff
    distance_cells = (
        euclidean_distance(start, pickup) +
        euclidean_distance(pickup, dropoff)
    )
    distance_km = cells_to_km(distance_cells)
    time_hours = distance_km / drone_speed_kmh
    time_minutes = time_hours * 60.0
    return distance_km, time_minutes

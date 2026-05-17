"""
=============================================================================
RESTAURANTS — Liste de vrais restaurants/lieux de Fès
=============================================================================

Données utilisées comme suggestions de "points de retrait" dans l'interface.
Les coordonnées sont approximatives (Google Maps / OpenStreetMap).

Tous les restaurants sont dans la zone d'opération du système (~10 km × 10 km
autour de l'UEMF).
=============================================================================
"""

RESTAURANTS = [
    {
        "id": "mcdo_bensouda",
        "name": "McDonald's Bensouda",
        "cuisine": "Fast-food",
        "icon": "🍔",
        "lat": 34.0480,
        "lon": -5.0590,
        "address": "Rond-Point Bensouda, Fès",
    },
    {
        "id": "pizza_hut_borj",
        "name": "Pizza Hut",
        "cuisine": "Pizza",
        "icon": "🍕",
        "lat": 34.0345,
        "lon": -5.0060,
        "address": "Borj Fès Mall, Avenue Allal El Fassi",
    },
    {
        "id": "kfc_borj",
        "name": "KFC Borj Fès",
        "cuisine": "Fast-food",
        "icon": "🍗",
        "lat": 34.0338,
        "lon": -5.0030,
        "address": "Borj Fès Mall, Fès",
    },
    {
        "id": "dominos_saiss",
        "name": "Domino's Pizza Saiss",
        "cuisine": "Pizza",
        "icon": "🍕",
        "lat": 34.0230,
        "lon": -5.0040,
        "address": "Avenue Hassan II, Saiss",
    },
    {
        "id": "cafe_clock",
        "name": "Café Clock",
        "cuisine": "Café / Marocain",
        "icon": "☕",
        "lat": 34.0648,
        "lon": -4.9784,
        "address": "Derb el Magana, Médina",
    },
    {
        "id": "marjane_saiss",
        "name": "Marjane Saiss",
        "cuisine": "Hypermarché",
        "icon": "🛒",
        "lat": 34.0190,
        "lon": -5.0050,
        "address": "Quartier Saiss, Fès",
    },
    {
        "id": "carrefour_borj",
        "name": "Carrefour Borj Fès",
        "cuisine": "Hypermarché",
        "icon": "🛒",
        "lat": 34.0345,
        "lon": -5.0040,
        "address": "Borj Fès Mall",
    },
    {
        "id": "dar_hatim",
        "name": "Restaurant Dar Hatim",
        "cuisine": "Marocain traditionnel",
        "icon": "🥘",
        "lat": 34.0612,
        "lon": -4.9810,
        "address": "Médina, Fès",
    },
    {
        "id": "pharmacie_uemf",
        "name": "Pharmacie UEMF",
        "cuisine": "Pharmacie",
        "icon": "💊",
        "lat": 34.0455,
        "lon": -5.0640,
        "address": "Près de l'UEMF Eco-Campus",
    },
    {
        "id": "starbucks_borj",
        "name": "Starbucks Borj Fès",
        "cuisine": "Café",
        "icon": "☕",
        "lat": 34.0340,
        "lon": -5.0050,
        "address": "Borj Fès Mall",
    },
]

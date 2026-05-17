"""
=============================================================================
WEATHER AGENT — Diffuse la météo
=============================================================================

TYPE D'AGENT: REACTIF (générateur d'événements environnementaux)
    Il ne dialogue pas : il DIFFUSE périodiquement l'état météo à tous les drones.
    C'est l'équivalent d'un "broadcaster" en SMA.

ROLE DANS LE SYSTEME:
    La météo INFLUENCE :
    - La consommation de batterie des drones (vent → consomme +)
    - Le temps prédit de livraison (modèle ML utilise la météo)
    - La stratégie des drones (par mauvais temps, ils sont moins compétitifs)

CONCEPT PEDAGOGIQUE:
    Illustre la COMMUNICATION INDIRECTE via l'environnement (concept
    de stigmergie évoqué dans le cours Chap 02 — sauf qu'ici on diffuse
    explicitement via FIPA-ACL au lieu de modifier un dépôt commun).

TYPE DE BEHAVIOUR:
    PeriodicBehaviour : change la météo toutes les 30 secondes et broadcast.
=============================================================================
"""

import random

from spade.agent import Agent
from spade.behaviour import PeriodicBehaviour
from spade.message import Message

from utils.ontologies import Ontology, Performative, JID
from utils.world_state import world_state


class WeatherAgent(Agent):
    """Agent météo : change l'environnement et notifie les drones."""

    # Probabilités relatives des conditions météo (somme = 1.0)
    WEATHER_DISTRIBUTION = {
        "clear":  0.55,
        "windy":  0.30,
        "rainy":  0.12,
        "stormy": 0.03,
    }

    class WeatherBroadcast(PeriodicBehaviour):
        """Tire une nouvelle météo et la diffuse à tous les drones."""

        async def run(self):
            # Tirage pondéré de la météo
            choices = list(WeatherAgent.WEATHER_DISTRIBUTION.keys())
            weights = list(WeatherAgent.WEATHER_DISTRIBUTION.values())
            new_weather = random.choices(choices, weights=weights, k=1)[0]

            # Mise à jour de l'état partagé (lu par Pygame + par les drones)
            world_state.set_weather(new_weather)

            # Diffusion à tous les drones (broadcast simulé : on envoie en boucle)
            # Chaque drone filtre via son template sur Ontology.WEATHER_UPDATE
            for drone_jid in JID.DRONES:
                msg = Message(to=drone_jid)
                msg.set_metadata("performative", Performative.INFORM)
                msg.set_metadata("ontology", Ontology.WEATHER_UPDATE)
                msg.body = new_weather
                await self.send(msg)

            print(f"[Weather] 🌤️  Météo diffusée : {new_weather}")

    async def setup(self):
        print("[Weather] Démarrage de l'agent météo")
        # Toutes les 30 secondes on tire une nouvelle météo
        self.add_behaviour(self.WeatherBroadcast(period=30))

"""
=============================================================================
DRONE AGENT — Agent Cognitif BDI ⭐ COEUR DU PROJET ⭐
=============================================================================

TYPE D'AGENT: COGNITIF (architecture BDI complète)
    Le drone est l'agent le plus complexe du système. Il possède :
    - BELIEFS    : ce qu'il croit sur le monde (position, batterie, météo, mission)
    - DESIRES    : ses objectifs (livrer + maintenir batterie au-dessus du seuil)
    - INTENTIONS : son plan d'action courant (séquence pickup → deliver → idle)

CYCLE DE RAISONNEMENT (Sense-Plan-Act, vu en cours Chap 02):
    1. SENSE  : mise à jour des Beliefs via les messages reçus (météo, ordres)
    2. PLAN   : décision selon l'état (recharge ? livraison ? attente ?)
    3. ACT    : action concrète (avancer d'1 case, envoyer un message, recharger)

PARTICIPATION AU CONTRACT-NET (vu en TP5):
    Le drone joue le rôle de WORKER (participant) :
    - Reçoit un CFP du Dispatcher
    - Évalue s'il peut/veut faire la mission (batterie, état, distance)
    - Utilise le MODELE ML pour prédire son temps de livraison
    - Répond avec un PROPOSE (son coût) ou REFUSE
    - Si choisi : reçoit ACCEPT-PROPOSAL → bascule en mode mission

MACHINE A ETATS (status):
    idle ─────► moving_to_pickup ──► carrying ──► (livré) ──► idle
       │                                                         │
       └──► moving_to_station ──► charging ──► (rechargé) ─────► idle

COMMUNICATION:
    Dispatcher  ──CFP──►  Drone
                ◄─PROPOSE─               (coût + temps prédit)
    Dispatcher  ──ACCEPT-PROPOSAL──►  Drone
                                       Drone ──INFORM──► Customer (livré)
                                       Drone ──INFORM──► Dispatcher (mission OK)
    Station     ◄─REQUEST(charging-request)─  Drone
                ──AGREE/REFUSE──►            Drone
=============================================================================
"""

import json
import math
import random

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, PeriodicBehaviour
from spade.message import Message
from spade.template import Template

from utils.ontologies import Ontology, Performative, JID, Config
from utils.city_map import (
    Position,
    euclidean_distance,
    next_step,
    has_arrived,
    closest_point,
)
from utils.world_state import world_state
from ml.delivery_predictor import get_predictor


class DroneAgent(Agent):
    """Agent drone cognitif (architecture BDI)."""

    def __init__(self, jid: str, password: str, position: Position):
        super().__init__(jid, password)
        self.base_position = position   # position de départ (parking)
        self.initial_position = position

    async def setup(self):
        print(f"[{self.jid}] 🚁 Démarrage à {self.initial_position}")

        # =====================================================================
        # === BELIEFS : tout ce que l'agent CROIT sur le monde et lui-même  ===
        # =====================================================================
        # Stockés sur l'AGENT (et pas le behaviour) pour être partagés entre
        # tous les comportements de l'agent.
        self.beliefs = {
            "position": self.initial_position,
            "battery": Config.BATTERY_MAX,
            "status": "idle",            # idle | moving_to_pickup | carrying |
                                          # moving_to_station | charging
            "payload": None,              # order_id du colis transporté
            "weather": "clear",           # mis à jour par WeatherAgent
            "current_order": None,        # dict de l'ordre en cours
            "target": None,               # position cible du déplacement
            "charging_station": None,     # JID de la station en cours d'usage
        }

        # NOTE: On NE re-register PAS le drone dans world_state ici, car le
        # simulation_loop (main.py) en a déjà le contrôle. Réécrire ici
        # écraserait les positions mises à jour par le simulateur.

        # =====================================================================
        # === DESIRES : objectifs de haut niveau (implicites dans le code)  ===
        # =====================================================================
        # 1) Compléter les livraisons assignées
        # 2) Maintenir la batterie au-dessus du seuil critique
        # 3) Maximiser le nombre de missions accomplies

        # =====================================================================
        # === INTENTIONS : plans concrets (machine à états via 'status')    ===
        # =====================================================================
        # Le 'status' du belief joue le rôle de l'intention courante.

        # ⚠️ PAS de world_state.register_drone() ici — le simulation_loop
        # de main.py a déjà pré-enregistré le drone et le contrôle.
        # Si on le ré-enregistrait, on écraserait les positions du simulateur.

        # ----------------------------------------------------------------
        # ENREGISTREMENT DES COMPORTEMENTS — avec TEMPLATES de filtrage
        # ----------------------------------------------------------------
        # Chaque template ne laisse passer que les messages de l'ontologie
        # correspondante. Sans cela, un seul Behaviour recevrait TOUT.

        # B1 : écoute des updates météo
        t_weather = Template()
        t_weather.set_metadata("ontology", Ontology.WEATHER_UPDATE)
        self.add_behaviour(self.ReceiveWeatherBehaviour(), t_weather)

        # B2 : écoute des CFP (appels d'offres de livraisons)
        t_cfp = Template()
        t_cfp.set_metadata("ontology", Ontology.DELIVERY_CFP)
        self.add_behaviour(self.HandleCFPBehaviour(), t_cfp)

        # B3 : écoute des ACCEPT-PROPOSAL (mission attribuée)
        t_award = Template()
        t_award.set_metadata("ontology", Ontology.DELIVERY_AWARD)
        self.add_behaviour(self.HandleAwardBehaviour(), t_award)

        # B4 : écoute des REJECT-PROPOSAL (mission perdue) — log seulement
        t_reject = Template()
        t_reject.set_metadata("ontology", Ontology.DELIVERY_REJECT)
        self.add_behaviour(self.HandleRejectBehaviour(), t_reject)

        # B5 : écoute des réponses des stations de recharge
        # Note: on combine 2 templates via l'opérateur OR (|) car SPADE Template
        # supporte la composition logique (cf. doc SPADE 3.x).
        t_grant = Template()
        t_grant.set_metadata("ontology", Ontology.CHARGING_GRANT)
        t_deny = Template()
        t_deny.set_metadata("ontology", Ontology.CHARGING_DENY)
        self.add_behaviour(self.HandleStationReplyBehaviour(), t_grant | t_deny)

        # B6 : TICK périodique de mouvement (Sense-Plan-Act loop)
        self.add_behaviour(self.MovementTickBehaviour(period=Config.DRONE_TICK_DELAY))

    # =========================================================================
    # ==                          BEHAVIOURS                                ==
    # =========================================================================

    # -----------------------------------------------------------------
    # B1 : Update Belief "weather"
    # -----------------------------------------------------------------
    class ReceiveWeatherBehaviour(CyclicBehaviour):
        async def run(self):
            agent: "DroneAgent" = self.agent
            msg = await self.receive(timeout=10)
            if msg:
                agent.beliefs["weather"] = msg.body
                # Pas d'action immédiate : juste mise à jour des beliefs.
                # Le PlanBehaviour réagira au prochain tick si nécessaire.

    # -----------------------------------------------------------------
    # B2 : Recevoir CFP → estimer coût (ML) → PROPOSE ou REFUSE
    # -----------------------------------------------------------------
    class HandleCFPBehaviour(CyclicBehaviour):
        async def run(self):
            agent: "DroneAgent" = self.agent
            msg = await self.receive(timeout=10)
            if not msg:
                return

            order = json.loads(msg.body)
            pickup = tuple(order["pickup"])
            dropoff = tuple(order["dropoff"])
            payload_kg = order["payload_kg"]

            reply = msg.make_reply()
            reply.set_metadata("ontology", Ontology.DELIVERY_PROPOSAL)

            # --- Filtre 1 : déjà en mission ? ---
            if agent.beliefs["status"] != "idle":
                reply.set_metadata("performative", Performative.REFUSE)
                reply.body = "déjà occupé"
                await self.send(reply)
                return

            # --- Filtre 2 : batterie trop basse ? ---
            if agent.beliefs["battery"] < Config.BATTERY_LOW_THRESHOLD:
                reply.set_metadata("performative", Performative.REFUSE)
                reply.body = f"batterie insuffisante ({agent.beliefs['battery']:.0f}%)"
                await self.send(reply)
                return

            # --- Calcul du coût via le modèle ML ---
            current_pos = agent.beliefs["position"]
            distance_to_pickup = euclidean_distance(current_pos, pickup)
            distance_pickup_to_dropoff = euclidean_distance(pickup, dropoff)
            total_distance = distance_to_pickup + distance_pickup_to_dropoff

            # Le modèle ML prédit le temps que prendrait cette livraison
            try:
                predictor = get_predictor()
                estimated_time = predictor.predict(
                    distance=total_distance,
                    payload=payload_kg,
                    wind_speed=random.uniform(5, 30),     # info météo simulée
                    weather=agent.beliefs["weather"],
                    battery_start=agent.beliefs["battery"],
                )
            except Exception as e:
                print(f"[{agent.jid}] ⚠️ Erreur ML : {e}")
                # Fallback : estimation linéaire simple
                estimated_time = total_distance * 0.7

            # --- Envoi de la PROPOSE ---
            reply.set_metadata("performative", Performative.PROPOSE)
            reply.body = json.dumps({
                "order_id": order["order_id"],
                "estimated_time": estimated_time,
                "distance": total_distance,
                "battery": agent.beliefs["battery"],
            })
            await self.send(reply)
            print(f"[{agent.jid}] 📤 PROPOSE {order['order_id']} "
                  f"(temps prévu: {estimated_time:.1f}s, "
                  f"distance: {total_distance:.1f})")

    # -----------------------------------------------------------------
    # B3 : Recevoir ACCEPT-PROPOSAL → démarrer la mission
    # -----------------------------------------------------------------
    class HandleAwardBehaviour(CyclicBehaviour):
        async def run(self):
            agent: "DroneAgent" = self.agent
            msg = await self.receive(timeout=10)
            if not msg:
                return

            order = json.loads(msg.body)

            # On ne prend la mission que si on est toujours libre
            # (sécurité : la station/ordre peuvent avoir changé)
            if agent.beliefs["status"] != "idle":
                print(f"[{agent.jid}] ⚠️ Award reçu mais déjà en mission, ignoré")
                return

            # === Mise à jour des Beliefs (intention nouvelle) ===
            agent.beliefs["current_order"] = order
            agent.beliefs["status"] = "moving_to_pickup"
            agent.beliefs["target"] = tuple(order["pickup"])

            print(f"[{agent.jid}] 🎯 Mission acceptée : "
                  f"{order['order_id']} → pickup {order['pickup']}")

    # -----------------------------------------------------------------
    # B4 : Recevoir REJECT-PROPOSAL (perdu l'enchère) — log seulement
    # -----------------------------------------------------------------
    class HandleRejectBehaviour(CyclicBehaviour):
        async def run(self):
            agent: "DroneAgent" = self.agent
            msg = await self.receive(timeout=10)
            if msg:
                # On consomme juste le message — pas d'action particulière
                pass

    # -----------------------------------------------------------------
    # B5 : Recevoir la réponse de la station de recharge
    # -----------------------------------------------------------------
    class HandleStationReplyBehaviour(CyclicBehaviour):
        async def run(self):
            agent: "DroneAgent" = self.agent
            msg = await self.receive(timeout=10)
            if not msg:
                return

            ontology = msg.get_metadata("ontology")
            station_jid = str(msg.sender).split("/")[0]

            if ontology == Ontology.CHARGING_GRANT:
                # Station accepte → on attend d'arriver pour passer en "charging"
                # Le MovementTickBehaviour gérera la suite
                agent.beliefs["charging_station"] = station_jid
                print(f"[{agent.jid}] ✅ Station {station_jid} a accepté la recharge")
            elif ontology == Ontology.CHARGING_DENY:
                print(f"[{agent.jid}] ❌ Station {station_jid} refusée → autre station")
                # On retombe en idle et on retente au prochain tick
                agent.beliefs["status"] = "idle"
                agent.beliefs["target"] = None
                agent.beliefs["charging_station"] = None

    # -----------------------------------------------------------------
    # B6 : TICK PERIODIQUE — boucle Sense-Plan-Act
    # -----------------------------------------------------------------
    class MovementTickBehaviour(PeriodicBehaviour):
        """
        Ce comportement est le CŒUR de la boucle Sense-Plan-Act du drone.

        À chaque tick (toutes les ~0.3s) :
            1. SENSE : lit l'état (déjà mis à jour par les autres behaviours)
            2. PLAN  : décide quoi faire selon le statut courant
            3. ACT   : se déplace OU envoie un message OU recharge
        """

        async def run(self):
            agent: "DroneAgent" = self.agent
            status = agent.beliefs["status"]
            battery = agent.beliefs["battery"]

            # =================================================================
            # ===  PRIORITE ABSOLUE : recharge si batterie critique          ==
            # =================================================================
            # Sauf si déjà en train d'aller charger / charger
            if (status in ("idle", "moving_to_pickup", "carrying")
                    and battery < Config.BATTERY_CRITICAL):
                await self._plan_recharge()
                return

            # =================================================================
            # ===  MACHINE A ETATS                                            ==
            # =================================================================
            if status == "idle":
                # Rien à faire : on attend une mission
                pass

            elif status == "moving_to_pickup":
                await self._move_or_pickup()

            elif status == "carrying":
                await self._move_or_deliver()

            elif status == "moving_to_station":
                await self._move_or_charge()

            elif status == "charging":
                await self._charge()

            # ⚠️ DÉSACTIVÉ : on ne synchronise PLUS le world_state depuis ici.
            # Le simulation_loop de main.py est la seule source de vérité pour
            # les positions des drones (sinon conflit / écrasement).
            #
            # Le BDI SPADE reste pleinement opérationnel pour le rapport
            # académique (Beliefs / Desires / Intentions / Contract-Net) mais
            # n'écrit plus dans le world_state visualisé.

        # ===== PHASE : déplacement vers le pickup =====
        async def _move_or_pickup(self):
            agent: "DroneAgent" = self.agent
            target = agent.beliefs["target"]
            position = agent.beliefs["position"]

            if has_arrived(position, target):
                # Arrivée au pickup : on "charge" virtuellement le colis
                order = agent.beliefs["current_order"]
                agent.beliefs["payload"] = order["order_id"]
                agent.beliefs["status"] = "carrying"
                agent.beliefs["target"] = tuple(order["dropoff"])
                print(f"[{agent.jid}] 📦 Colis récupéré → direction {order['dropoff']}")
            else:
                self._step_toward(target)

        # ===== PHASE : déplacement vers le dropoff =====
        async def _move_or_deliver(self):
            agent: "DroneAgent" = self.agent
            target = agent.beliefs["target"]
            position = agent.beliefs["position"]

            if has_arrived(position, target):
                # === LIVRAISON RÉALISÉE ===
                order = agent.beliefs["current_order"]
                customer_jid = order["customer_jid"]
                order_id = order["order_id"]

                # Notifier le client (INFORM final)
                inform_client = Message(to=customer_jid)
                inform_client.set_metadata("performative", Performative.INFORM)
                inform_client.set_metadata("ontology", Ontology.DELIVERY_STATUS)
                inform_client.body = f"Colis {order_id} livré par {agent.jid}"
                await self.send(inform_client)

                # Notifier le Dispatcher (clôture de la mission)
                inform_dispatcher = Message(to=JID.DISPATCHER)
                inform_dispatcher.set_metadata("performative", Performative.INFORM)
                inform_dispatcher.set_metadata("ontology", Ontology.DELIVERY_STATUS)
                inform_dispatcher.body = json.dumps({
                    "order_id": order_id,
                    "drone": str(agent.jid),
                    "status": "completed",
                })
                await self.send(inform_dispatcher)

                world_state.complete_order(order_id, success=True)
                print(f"[{agent.jid}] ✅ Livraison {order_id} terminée")

                # Reset des beliefs liés à la mission
                agent.beliefs["status"] = "idle"
                agent.beliefs["payload"] = None
                agent.beliefs["current_order"] = None
                agent.beliefs["target"] = None
            else:
                self._step_toward(target)

        # ===== PHASE : déplacement vers la station de recharge =====
        async def _move_or_charge(self):
            agent: "DroneAgent" = self.agent
            target = agent.beliefs["target"]
            position = agent.beliefs["position"]

            if has_arrived(position, target):
                # Arrivé à la station → on demande l'autorisation de recharger
                station_jid = agent.beliefs["charging_station"]
                if station_jid is None:
                    # On n'a pas encore d'autorisation → on attend
                    return
                # Mise en mode "charging"
                agent.beliefs["status"] = "charging"
                print(f"[{agent.jid}] 🔋 Recharge démarrée à {station_jid}")
            else:
                self._step_toward(target)

        # ===== PHASE : recharge en cours =====
        async def _charge(self):
            agent: "DroneAgent" = self.agent
            agent.beliefs["battery"] = min(
                Config.BATTERY_MAX,
                agent.beliefs["battery"] + Config.BATTERY_RECHARGE_RATE,
            )

            if agent.beliefs["battery"] >= Config.BATTERY_MAX:
                # Recharge complète → libérer la station + repasser idle
                station_jid = agent.beliefs["charging_station"]
                if station_jid:
                    complete_msg = Message(to=station_jid)
                    complete_msg.set_metadata("performative", Performative.INFORM)
                    complete_msg.set_metadata("ontology", Ontology.CHARGING_COMPLETE)
                    complete_msg.body = "charged"
                    await self.send(complete_msg)
                print(f"[{agent.jid}] 🔋 Batterie pleine ! Retour en idle")
                agent.beliefs["status"] = "idle"
                agent.beliefs["charging_station"] = None
                agent.beliefs["target"] = None

        # ===== UTILITAIRE : avancer d'1 cellule vers la cible =====
        def _step_toward(self, target: Position):
            agent: "DroneAgent" = self.agent
            current = agent.beliefs["position"]
            new_pos = next_step(current, target)
            agent.beliefs["position"] = new_pos

            # Consommation de batterie pondérée par la météo
            mult = Config.WEATHER_MULTIPLIERS.get(agent.beliefs["weather"], 1.0)
            consumption = Config.BATTERY_CONSUMPTION_PER_STEP * mult
            agent.beliefs["battery"] = max(0.0, agent.beliefs["battery"] - consumption)

        # ===== PLAN : recharge d'urgence =====
        async def _plan_recharge(self):
            """
            Le drone doit recharger : il cherche la station la plus proche,
            lui demande l'autorisation, et met à jour son plan.
            """
            agent: "DroneAgent" = self.agent

            # Récupération des stations depuis l'état partagé
            stations_snapshot = world_state.snapshot()["stations"]
            if not stations_snapshot:
                return  # pas de stations connues : impossible de recharger

            station_jids = list(stations_snapshot.keys())
            station_positions = [stations_snapshot[j]["position"] for j in station_jids]

            # Trouve la station la plus proche
            idx, station_pos = closest_point(
                agent.beliefs["position"], station_positions
            )
            chosen_station_jid = station_jids[idx]

            # ===== ENVOI DU REQUEST CHARGING =====
            # On suit le pattern REQUEST → AGREE/REFUSE vu en TP5
            req = Message(to=chosen_station_jid)
            req.set_metadata("performative", Performative.REQUEST)
            req.set_metadata("ontology", Ontology.CHARGING_REQUEST)
            req.body = "Demande de recharge"
            await self.send(req)

            # Mise à jour des beliefs : on se dirige vers cette station
            agent.beliefs["status"] = "moving_to_station"
            agent.beliefs["target"] = station_pos
            print(f"[{agent.jid}] ⚡ Batterie critique ({agent.beliefs['battery']:.0f}%) "
                  f"→ direction station {chosen_station_jid}")

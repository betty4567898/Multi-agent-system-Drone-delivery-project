"""
=============================================================================
DISPATCHER AGENT — Orchestrateur Contract-Net ⭐
=============================================================================

TYPE D'AGENT: COGNITIF (manager / broker)
    Le Dispatcher orchestre TOUT le système. C'est l'initiateur du
    Contract-Net Protocol vu en TP5. Il :
        1. Reçoit les commandes des CustomerAgents
        2. Lance un appel d'offres (CFP) à TOUS les drones
        3. Collecte les propositions (PROPOSE) et choisit la meilleure
        4. Notifie le drone gagnant (ACCEPT-PROPOSAL) et les perdants (REJECT)

PROTOCOLE FIPA-ACL UTILISE: Contract-Net Protocol (CNP)
    Référence: FIPA00029 (standard officiel)

    Customer  ──REQUEST(commande)──►  Dispatcher
                                      │
                              ┌───────┴───────┐
                              ▼               │
              ┌─── CFP ───────► Drone 1       │  (broadcast)
    Dispatcher├─── CFP ───────► Drone 2       │
              ├─── CFP ───────► Drone 3       │
              └─── CFP ───────► Drone N       │
                              │               │
                              ▼               │
              ◄──PROPOSE──── Drone 1 (5s)    │
              ◄──PROPOSE──── Drone 2 (8s)    │
              ◄──REFUSE──── Drone 3 (occupé) │
                              │               │
                              ▼               │
                       (choix du min)         │
                              │               │
              ──ACCEPT───────► Drone 1 ⭐      │
              ──REJECT───────► Drone 2         │
                              ▼
                       Drone 1 effectue la livraison

CRITERE DE DECISION:
    On choisit la PROPOSE avec le PLUS PETIT temps prédit (issu du ML).
    → C'est l'optimisation classique d'un système d'enchère décroissante.

CHOIX D'ARCHITECTURE IMPORTANT:
    Le Dispatcher utilise UN SEUL Behaviour principal qui :
      - écoute toutes les ontologies pertinentes (request, proposal, status)
      - dispatch en fonction de l'ontologie reçue
    Pourquoi ? Parce que SPADE filtre par template au niveau du receive().
    Si on séparait en plusieurs behaviours, le receive() de la collecte des
    PROPOSE ne verrait PAS les PROPOSE (car son template est "request").
    → On centralise tout dans un Behaviour pour pouvoir collecter les PROPOSE
       APRES avoir reçu le REQUEST initial.
=============================================================================
"""

import asyncio
import json

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
from spade.template import Template

from utils.ontologies import Ontology, Performative, JID, Config
from utils.world_state import world_state


class DispatcherAgent(Agent):
    """Manager qui orchestre l'allocation des livraisons via Contract-Net."""

    async def setup(self):
        print(f"[Dispatcher] 🎯 Démarrage du broker Contract-Net")

        # Liste des drones actifs (cible des broadcasts CFP)
        self.active_drones = list(JID.DRONES)

        # File des commandes en attente (FIFO) — quand un nouveau REQUEST arrive
        # pendant qu'on traite une commande, on le bufferise ici.
        self.pending_requests = []

        # Stats internes
        self.processed_orders = 0

        # =====================================================================
        # TEMPLATE COMBINE : on accepte 3 ontologies sur le même behaviour
        # Cela évite que le receive() d'un behaviour rate les messages destinés
        # à un autre behaviour.
        # =====================================================================
        t_request = Template()
        t_request.set_metadata("ontology", Ontology.DELIVERY_REQUEST)
        t_proposal = Template()
        t_proposal.set_metadata("ontology", Ontology.DELIVERY_PROPOSAL)
        t_status = Template()
        t_status.set_metadata("ontology", Ontology.DELIVERY_STATUS)

        # Opérateur OR de Template : matche n'importe laquelle des 3 ontologies
        combined = t_request | t_proposal | t_status
        self.add_behaviour(self.MainBehaviour(), combined)

    # =========================================================================
    # Behaviour unique qui orchestre tout
    # =========================================================================
    class MainBehaviour(CyclicBehaviour):
        """
        Boucle principale du Dispatcher :
            1. Si un REQUEST est bufferisé → le traiter
            2. Sinon : attendre un nouveau message
            3. Selon l'ontologie : process_order / log_status / ignorer
        """

        async def run(self):
            agent: "DispatcherAgent" = self.agent

            # ===== 1) Y a-t-il un REQUEST bufferisé ? =====
            # Ces requests sont arrivés pendant qu'on traitait une commande
            # précédente — on les rattrape ici.
            if agent.pending_requests:
                buffered_msg = agent.pending_requests.pop(0)
                await self._process_order(buffered_msg)
                return

            # ===== 2) Attente d'un nouveau message =====
            msg = await self.receive(timeout=5)
            if not msg:
                return

            ontology = msg.get_metadata("ontology")

            # ===== 3) Dispatch selon l'ontologie =====
            if ontology == Ontology.DELIVERY_REQUEST:
                await self._process_order(msg)

            elif ontology == Ontology.DELIVERY_STATUS:
                # Confirmation de fin de mission d'un drone
                try:
                    data = json.loads(msg.body)
                    print(f"[Dispatcher] ✅ Confirmation : {data['order_id']} "
                          f"livré par {data['drone']}")
                except Exception:
                    print(f"[Dispatcher] (status) {msg.body}")

            elif ontology == Ontology.DELIVERY_PROPOSAL:
                # Proposition tardive (CFP déjà clos) — on ignore
                drone = str(msg.sender).split("/")[0]
                print(f"[Dispatcher] 🕓 Proposition tardive de {drone}, ignorée")

        # =====================================================================
        # Pipeline Contract-Net complet pour une commande
        # =====================================================================
        async def _process_order(self, request_msg):
            agent: "DispatcherAgent" = self.agent
            order = json.loads(request_msg.body)
            order_id = order["order_id"]
            print(f"\n[Dispatcher] 📩 Commande reçue : {order_id}")

            # Enregistrement dans l'état partagé (Pygame)
            world_state.add_order(
                order_id,
                order["customer_jid"],
                tuple(order["pickup"]),
                tuple(order["dropoff"]),
            )

            # ============= ETAPE 1 : CFP (broadcast) =============
            cfp_body = json.dumps(order)
            for drone_jid in agent.active_drones:
                cfp = Message(to=drone_jid)
                cfp.set_metadata("performative", Performative.CFP)
                cfp.set_metadata("ontology", Ontology.DELIVERY_CFP)
                cfp.body = cfp_body
                await self.send(cfp)

            print(f"[Dispatcher] 📢 CFP diffusé à {len(agent.active_drones)} drones")
            world_state.log_event(
                f"📢 CFP {order_id} → {len(agent.active_drones)} drones"
            )

            # ============= ETAPE 2 : Collecte des PROPOSE/REFUSE =============
            proposals = []          # liste de tuples (drone_jid, body_dict)
            refusals = []
            deadline = asyncio.get_event_loop().time() + Config.CFP_TIMEOUT

            while asyncio.get_event_loop().time() < deadline:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break

                reply = await self.receive(timeout=min(1.0, remaining))
                if not reply:
                    continue

                reply_ontology = reply.get_metadata("ontology")
                reply_perf = reply.get_metadata("performative")

                # --- Si c'est une PROPOSE (ou REFUSE sur cette ontologie) ---
                if reply_ontology == Ontology.DELIVERY_PROPOSAL:
                    drone_jid = str(reply.sender).split("/")[0]
                    if reply_perf == Performative.PROPOSE:
                        try:
                            body = json.loads(reply.body)
                            if body.get("order_id") == order_id:
                                proposals.append((drone_jid, body))
                        except Exception as e:
                            print(f"[Dispatcher] ⚠️ PROPOSE mal formée: {e}")
                    elif reply_perf == Performative.REFUSE:
                        refusals.append((drone_jid, reply.body))

                # --- Si c'est un nouveau REQUEST : on bufferise pour plus tard ---
                elif reply_ontology == Ontology.DELIVERY_REQUEST:
                    agent.pending_requests.append(reply)
                    print(f"[Dispatcher] 📥 Nouveau REQUEST bufferisé "
                          f"(traitement après commande courante)")

                # --- Si c'est un STATUS : on log directement ---
                elif reply_ontology == Ontology.DELIVERY_STATUS:
                    try:
                        data = json.loads(reply.body)
                        print(f"[Dispatcher] ✅ Confirmation pendant CFP : "
                              f"{data['order_id']}")
                    except Exception:
                        pass

                # Si tous les drones ont répondu, on accélère la suite
                if len(proposals) + len(refusals) >= len(agent.active_drones):
                    break

            print(f"[Dispatcher] 📊 Résultats CFP : "
                  f"{len(proposals)} propositions, {len(refusals)} refus")

            # ============= ETAPE 3 : Décision (choix du meilleur) =============
            if not proposals:
                # Aucun drone disponible : mission échouée
                print(f"[Dispatcher] ❌ Aucune proposition pour {order_id}")
                world_state.complete_order(order_id, success=False)
                fail_msg = Message(to=order["customer_jid"])
                fail_msg.set_metadata("performative", Performative.FAILURE)
                fail_msg.set_metadata("ontology", Ontology.DELIVERY_STATUS)
                fail_msg.body = "Aucun drone disponible"
                await self.send(fail_msg)
                return

            # Critère : on choisit le drone avec le plus petit estimated_time
            best_drone, best_body = min(
                proposals, key=lambda p: p[1]["estimated_time"]
            )
            print(f"[Dispatcher] 🏆 Gagnant : {best_drone} "
                  f"(temps prévu: {best_body['estimated_time']:.1f}s)")
            world_state.log_event(
                f"🏆 {order_id} → {best_drone.split('@')[0]} "
                f"({best_body['estimated_time']:.1f}s)"
            )
            world_state.update_order(order_id, drone=best_drone, status="assigned")

            # ============= ETAPE 4 : ACCEPT-PROPOSAL + REJECT-PROPOSAL =============
            for drone_jid, _ in proposals:
                response = Message(to=drone_jid)
                if drone_jid == best_drone:
                    response.set_metadata("performative", Performative.ACCEPT_PROPOSAL)
                    response.set_metadata("ontology", Ontology.DELIVERY_AWARD)
                    response.body = json.dumps(order)
                else:
                    response.set_metadata("performative", Performative.REJECT_PROPOSAL)
                    response.set_metadata("ontology", Ontology.DELIVERY_REJECT)
                    response.body = json.dumps({"order_id": order_id})
                await self.send(response)

            agent.processed_orders += 1

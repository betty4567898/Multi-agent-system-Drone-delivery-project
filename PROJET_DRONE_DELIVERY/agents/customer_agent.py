"""
=============================================================================
CUSTOMER AGENT — Le client passe commande
=============================================================================

TYPE D'AGENT: REACTIF (simple, peu de raisonnement)
    Le client a un seul "désir" : que sa commande soit livrée.
    Il n'a pas besoin de planifier ou négocier — il EMET une demande
    et attend l'INFORM final du drone qui livre.

ROLE DANS LE SYSTEME:
    Génère une commande, l'envoie au Dispatcher (REQUEST), et attend
    qu'un drone vienne livrer (INFORM "delivered").

COMMUNICATION:
    Customer  ──REQUEST(commande)──►  Dispatcher
    Drone     ──INFORM(livré)─────►   Customer  (notification finale)

TYPE DE BEHAVIOUR:
    OneShotBehaviour : un client passe UNE commande et attend sa livraison.
    Une fois livré, l'agent peut s'arrêter (simulation).
=============================================================================
"""

import json
import uuid

from spade.agent import Agent
from spade.behaviour import OneShotBehaviour
from spade.message import Message

from utils.ontologies import Ontology, Performative, JID
from utils.world_state import world_state


class CustomerAgent(Agent):
    """Client qui passe une commande de livraison."""

    def __init__(self, jid: str, password: str, position, dropoff):
        super().__init__(jid, password)
        # Position du point de retrait (où le drone récupère le colis)
        self.pickup_position = position
        # Position du point de livraison (où le client veut le colis)
        self.dropoff_position = dropoff
        # Identifiant unique de la commande (UUID court)
        self.order_id = f"order_{uuid.uuid4().hex[:8]}"

    # -----------------------------------------------------------------
    # Behaviour : OneShotBehaviour (un client = une commande)
    # -----------------------------------------------------------------
    class OrderBehaviour(OneShotBehaviour):
        async def run(self):
            agent: "CustomerAgent" = self.agent

            # ===== ETAPE 1 : Construction du REQUEST =====
            # Performative REQUEST : "Je te demande de réaliser une action"
            # Ici, l'action est : "livrer mon colis"
            msg = Message(to=JID.DISPATCHER)
            msg.set_metadata("performative", Performative.REQUEST)
            msg.set_metadata("ontology", Ontology.DELIVERY_REQUEST)
            # Body au format JSON : structure claire et déserialisable
            msg.body = json.dumps({
                "order_id": agent.order_id,
                "customer_jid": str(agent.jid),
                "pickup": list(agent.pickup_position),
                "dropoff": list(agent.dropoff_position),
                "payload_kg": 1.5,        # poids fictif (entre 0.1 et 5 kg)
                "priority": "normal",
            })

            await self.send(msg)
            print(f"[Customer {agent.order_id}] 📦 REQUEST envoyé au Dispatcher")

            # Mise à jour de l'état partagé (pour Pygame)
            world_state.register_customer(
                str(agent.jid), tuple(agent.dropoff_position)
            )

            # ===== ETAPE 2 : Attente de l'INFORM final (livraison réalisée) =====
            # Timeout long : le drone peut prendre du temps (livraison, météo...)
            reply = await self.receive(timeout=120)

            if reply:
                perf = reply.get_metadata("performative")
                if perf == Performative.INFORM:
                    print(f"[Customer {agent.order_id}] ✅ Colis reçu : {reply.body}")
                else:
                    print(f"[Customer {agent.order_id}] ⚠️ Réponse inattendue : {perf}")
            else:
                print(f"[Customer {agent.order_id}] ⏱️ Aucune livraison reçue (timeout)")

            # Nettoyage : on retire le client de la carte
            world_state.remove_customer(str(agent.jid))

    async def setup(self):
        print(f"[Customer] Démarrage — order_id={self.order_id}")

        # On enregistre la position du client dans l'état partagé
        world_state.register_customer(str(self.jid), self.dropoff_position)

        self.add_behaviour(self.OrderBehaviour())

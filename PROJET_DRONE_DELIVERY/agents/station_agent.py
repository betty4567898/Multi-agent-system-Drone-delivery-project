"""
=============================================================================
STATION AGENT — Station de recharge
=============================================================================

TYPE D'AGENT: REACTIF
    La station ne raisonne pas : elle accepte une recharge si elle est libre,
    sinon elle refuse. C'est un agent de service simple.

ROLE DANS LE SYSTEME:
    Permet aux drones de recharger leur batterie quand ils sont bas.
    UNE seule station = UN seul drone à la fois (resource exclusive).

PATTERN DE COMMUNICATION:
    Drone     ──REQUEST(charging-request)──►  Station
    Station   ◄─AGREE (charging-grant)─────  ou REFUSE (charging-deny)
    Drone     ──INFORM(charging-complete)──►  Station   (fin de recharge)

CONCEPT PEDAGOGIQUE:
    Cela illustre la GESTION DE RESSOURCES PARTAGEES en SMA :
    les stations sont des biens limités → les drones doivent négocier
    l'accès (autonomie + protocole d'allocation).
=============================================================================
"""

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.template import Template

from utils.ontologies import Ontology, Performative
from utils.world_state import world_state


class StationAgent(Agent):
    """Station de recharge — accès exclusif (1 drone à la fois)."""

    def __init__(self, jid: str, password: str, position):
        super().__init__(jid, password)
        self.position = position

    # -----------------------------------------------------------------
    # Behaviour 1 : Gérer les demandes de recharge
    # -----------------------------------------------------------------
    class HandleChargingRequest(CyclicBehaviour):
        async def run(self):
            agent: "StationAgent" = self.agent
            msg = await self.receive(timeout=10)
            if not msg:
                return

            drone_jid = str(msg.sender).split("/")[0]   # on retire la ressource XMPP
            reply = msg.make_reply()

            # On tente d'occuper la station via world_state (atomic / thread-safe)
            granted = world_state.occupy_station(str(agent.jid), drone_jid)

            if granted:
                # Station libre → AGREE (autorisation)
                reply.set_metadata("performative", Performative.AGREE)
                reply.set_metadata("ontology", Ontology.CHARGING_GRANT)
                reply.body = f"Station prête en {agent.position}"
                print(f"[Station {agent.jid}] ✅ Recharge accordée à {drone_jid}")
            else:
                # Station occupée → REFUSE
                reply.set_metadata("performative", Performative.REFUSE)
                reply.set_metadata("ontology", Ontology.CHARGING_DENY)
                reply.body = "Station occupée"
                print(f"[Station {agent.jid}] ❌ Recharge refusée à {drone_jid}")

            await self.send(reply)

    # -----------------------------------------------------------------
    # Behaviour 2 : Gérer la fin de recharge
    # -----------------------------------------------------------------
    class HandleChargingComplete(CyclicBehaviour):
        async def run(self):
            agent: "StationAgent" = self.agent
            msg = await self.receive(timeout=10)
            if not msg:
                return

            drone_jid = str(msg.sender).split("/")[0]
            # Libération de la station pour le prochain drone
            world_state.release_station(str(agent.jid))
            print(f"[Station {agent.jid}] 🔌 Recharge terminée pour {drone_jid}")

    async def setup(self):
        print(f"[Station {self.jid}] Démarrage à la position {self.position}")
        # Enregistrement dans l'état partagé (pour affichage Pygame)
        world_state.register_station(str(self.jid), self.position)

        # Template 1 : on filtre les demandes de recharge
        t1 = Template()
        t1.set_metadata("ontology", Ontology.CHARGING_REQUEST)
        self.add_behaviour(self.HandleChargingRequest(), t1)

        # Template 2 : on filtre les fins de recharge
        t2 = Template()
        t2.set_metadata("ontology", Ontology.CHARGING_COMPLETE)
        self.add_behaviour(self.HandleChargingComplete(), t2)

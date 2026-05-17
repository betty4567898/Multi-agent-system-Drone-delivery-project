"""
=============================================================================
SERVEUR XMPP (PyJabber) — Infrastructure de messagerie
=============================================================================

ROLE:
    SPADE s'appuie sur XMPP pour la communication entre agents.
    PyJabber est un serveur XMPP léger en Python qui tourne en local.

A LANCER EN PREMIER, dans un terminal séparé :
    python server.py

Puis dans un autre terminal :
    python main.py

Le serveur écoute sur le port 5222 (standard XMPP).
=============================================================================
"""

import asyncio
import logging
from pyjabber.server import Server


async def main():
    # Logs basiques pour voir les connexions des agents
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    print("=" * 60)
    print("🌐 Démarrage du serveur XMPP (PyJabber) sur localhost:5222")
    print("=" * 60)

    server = Server()
    await server.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Serveur arrêté manuellement.")

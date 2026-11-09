# Drone Delivery — Multi-Agent System

Autonomous drone delivery simulation built as a multi-agent system on a real map of Fès (Morocco), with machine-learning delivery-time prediction and a live web dashboard.

The full project lives in [`PROJET_DRONE_DELIVERY/`](PROJET_DRONE_DELIVERY/) (detailed documentation in French in its README).

## Highlights
- **Multi-agent system (SPADE 4, FIPA-ACL):** customer, dispatcher, drone, weather and charging-station agents communicating over XMPP.
- **Contract-Net Protocol:** the dispatcher broadcasts calls for proposals; drones bid, and the best bid wins the delivery.
- **BDI drones:** each drone keeps beliefs (position, battery, weather, mission) and runs a sense–plan–act loop.
- **Machine learning:** a scikit-learn RandomForest predicts delivery time; drones use it when bidding.
- **Live dashboard:** FastAPI + WebSocket backend, Leaflet map and Chart.js charts in the browser.

## Tech stack
Python · SPADE · PyJabber (XMPP) · scikit-learn · FastAPI · WebSocket · Leaflet · Chart.js

## Run it
```bash
cd PROJET_DRONE_DELIVERY
pip install -r requirements.txt
python server.py   # terminal 1: local XMPP server
python main.py     # terminal 2: agents + web interface
```
Then open http://localhost:8000

## Roadmap
- [ ] Unit tests (pytest) for the ML predictor and the Contract-Net logic
- [ ] Collision avoidance between drones
- [ ] Better ML model: real-world features and proper evaluation metrics
- [ ] Docker setup to run everything with one command
- [ ] English translation of the detailed documentation

## Author
Ibtissam El Hichou — AI Engineering student, Université Euromed de Fès

# 🚁 Drone Delivery — Système Multi-Agents

> **Projet de fin de module** — *Systèmes Multi-Agents et Intelligence Artificielle Distribuée*
> Université Euromed de Fès · Année universitaire 2025-2026
> Auteur : **Ibtissam EL HICHOU** · 2ᵉ année IA

![Stack](https://img.shields.io/badge/SPADE-4.x-cyan) ![Stack](https://img.shields.io/badge/FastAPI-WebSocket-fuchsia) ![Stack](https://img.shields.io/badge/Tailwind-CSS-emerald) ![Stack](https://img.shields.io/badge/ML-RandomForest-amber)

---

## 🎯 Aperçu

Plateforme de **livraison par drones autonomes** modélisée comme **système multi-agents** complet, déployée sur une **carte réelle de Fès** centrée sur l'**Université Euromed**.

### Pile technologique
| Couche | Technologie |
|--------|-------------|
| Agents SMA | **SPADE 4.x** (Python, asyncio, FIPA-ACL) |
| Serveur de messagerie | **PyJabber** (XMPP local) |
| Machine Learning | **scikit-learn** RandomForestRegressor |
| API / WebSocket | **FastAPI + uvicorn** |
| Frontend | **HTML + Tailwind CSS + Vanilla JS** |
| Carte interactive | **Leaflet** + tuiles CartoDB Dark Matter |
| Graphiques | **Chart.js** |
| Typo / Icons | **Inter + JetBrains Mono + Lucide** |

### Effet wow
- 🗺️ **Vrais drones qui volent** sur une **vraie carte de Fès**
- 🎨 Design **glassmorphism cyberpunk** (Linear/Vercel inspired)
- 📊 **Graphiques temps réel** (taux de réussite, performance)
- ⚡ **WebSocket** push 5 FPS (animations fluides)
- 🌧️ **Météo dynamique** qui affecte la consommation et les prédictions ML

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                       │
│   CustomerAgents ──REQUEST──►  DispatcherAgent  (broker Contract-Net) │
│         ▲                            │                                │
│         │                            │ CFP (broadcast)                │
│         │ INFORM (livré)             ▼                                │
│         │                    5 × DroneAgent BDI                       │
│         │                   (workers, ML predictor)                   │
│         │                            │                                │
│         └────────────────────────────┘                                │
│                                                                       │
│   WeatherAgent  ──INFORM──►  Drones (Beliefs: weather)               │
│   3 × StationAgent  ◄──REQUEST──   Drones (charging)                 │
│                                                                       │
│                          ▼                                            │
│                   WorldState (shared)                                 │
│                          ▼                                            │
│                  FastAPI + WebSocket                                  │
│                          ▼                                            │
│              Interface Web (Leaflet + Tailwind)                       │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 📂 Structure du projet

```
PROJET_DRONE_DELIVERY/
├── server.py                      # Serveur XMPP PyJabber
├── main.py                        # Orchestrateur (lance agents + web)
│
├── agents/                        # 🤖 Agents SPADE
│   ├── customer_agent.py          # Réactif — passe une commande
│   ├── drone_agent.py             # ⭐ BDI cognitif (cœur du projet)
│   ├── dispatcher_agent.py        # ⭐ Contract-Net broker
│   ├── weather_agent.py           # Diffuse la météo
│   └── station_agent.py           # Recharge (ressource exclusive)
│
├── ml/                            # 🧠 Machine Learning
│   ├── train_model.py             # Génère dataset + entraîne RF
│   ├── delivery_predictor.py      # Wrapper d'inférence
│   └── delivery_model.joblib      # Modèle entraîné (auto-généré)
│
├── api/                           # 🌐 Bridge backend ↔ frontend
│   └── web_server.py              # FastAPI + WebSocket
│
├── web/                           # 🎨 Interface web
│   ├── index.html                 # Structure Tailwind
│   ├── style.css                  # Glassmorphism + animations
│   └── app.js                     # Leaflet + Chart.js + WS client
│
├── utils/                         # 🛠️ Utilitaires partagés
│   ├── city_map.py                # Grille 2D + GPS (Fès)
│   ├── world_state.py             # État partagé thread-safe
│   └── ontologies.py              # Vocabulaire FIPA-ACL
│
├── dashboard/                     # (archivé — version Pygame initiale)
├── requirements.txt
├── README.md
└── RAPPORT.md                     # Rapport académique complet
```

---

## 🚀 Installation & Lancement

### 1️⃣ Installer les dépendances

```bash
pip install -r requirements.txt
```

### 2️⃣ Démarrer le serveur XMPP (terminal 1)

```bash
python server.py
```

> ✅ Tu dois voir : `🌐 Démarrage du serveur XMPP (PyJabber) sur localhost:5222`
> ⏳ **Laisse ce terminal ouvert.**

### 3️⃣ Démarrer le système SMA + Web (terminal 2)

```bash
python main.py
```

Tu verras :
```
═══════════════════════════════════════════════════════════════
  🚁  DRONE DELIVERY SMA  —  Université Euromed de Fès
═══════════════════════════════════════════════════════════════

[Main] ✅ Modèle ML trouvé : delivery_model.joblib
[Main] ⏳ Démarrage du Dispatcher...
[Main]   ✅ Dispatcher connecté
[Main] ⏳ Démarrage du WeatherAgent...
[Main]   ✅ Weather connecté
[Main] ⏳ Démarrage de 3 stations...
[Main]   ✅ station1@localhost
[Main]   ✅ station2@localhost
[Main]   ✅ station3@localhost
[Main] ⏳ Démarrage de 5 drones...
[Main]   ✅ drone1@localhost  ...
[Main] 🌐 Démarrage de l'interface web...
[WebServer] 🌐 Interface web disponible : http://127.0.0.1:8000
```

### 4️⃣ Ouvrir l'interface web

Ouvre **http://localhost:8000** dans ton navigateur (Chrome / Edge / Firefox).

Tu verras la carte de Fès avec les **drones qui volent en temps réel**, les commandes qui apparaissent, et les graphiques qui se mettent à jour.

---

## 🎨 Aperçu de l'interface

| Élément | Description |
|--------|-------------|
| 🗺️ **Carte centrale** | OpenStreetMap dark theme centrée sur l'UEMF, avec drones (icônes animées + hélices tournantes), stations (hexagones), commandes (pickup/dropoff), routes pointillées |
| 📊 **Stats cards** | 4 cards en haut à gauche : Total / En cours / Livrées / Échecs |
| 🥧 **Donut Success rate** | Camembert taux de réussite (Livrées vs Échecs) |
| 📈 **Performance** | Graphique en aires temps réel (30 dernières secondes) |
| 🤖 **Fleet panel** | Liste des 5 drones avec statut + barre de batterie animée |
| 📦 **Commandes actives** | Liste des commandes en cours avec drone assigné |
| 📡 **Events log** | Log temps réel des messages FIPA-ACL |
| 🧬 **Protocol diagram** | Schéma visuel des 5 étapes du Contract-Net |

---

## 🔑 Concepts SMA implémentés

| Concept du cours | Implémentation |
|------------------|----------------|
| **Modèle BDI** | `drone_agent.py` — `beliefs={position, battery, status, weather, mission}` |
| **Boucle Sense-Plan-Act** | `MovementTickBehaviour` (PeriodicBehaviour) du drone |
| **Architecture cognitive** | `DroneAgent`, `DispatcherAgent` |
| **Architecture réactive** | `StationAgent`, `WeatherAgent`, `CustomerAgent` |
| **Contract-Net Protocol** | `DispatcherAgent` — 4 étapes complètes (CFP → PROPOSE → ACCEPT/REJECT → INFORM) |
| **FIPA-ACL** | 9 performatives : INFORM, REQUEST, CFP, PROPOSE, ACCEPT-PROPOSAL, REJECT-PROPOSAL, AGREE, REFUSE, FAILURE |
| **Ontologies** | 7 ontologies dans `utils/ontologies.py` |
| **Templates SPADE** | Filtrage des messages par metadata + opérateur OR (`t1 | t2`) |
| **Intégration ML** | RandomForest sur 5000 samples synthétiques, utilisé dans `HandleCFPBehaviour` |
| **Ressource partagée** | Stations (1 drone à la fois) via verrou thread-safe |

---

## 🐛 Dépannage

| Problème | Solution |
|----------|----------|
| `ConnectionRefusedError` au démarrage | Le serveur XMPP n'est pas lancé → `python server.py` dans un autre terminal |
| `ModuleNotFoundError: fastapi` | `pip install -r requirements.txt` |
| Carte vide dans le navigateur | Vérifie que main.py a démarré sans erreur (regarde le terminal) |
| Drones ne bougent pas | Attends ~10 secondes (le temps que les agents s'enregistrent et les commandes apparaissent) |


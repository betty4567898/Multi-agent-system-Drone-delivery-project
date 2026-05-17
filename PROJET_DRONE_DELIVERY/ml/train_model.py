"""
=============================================================================
ML — Entraînement du modèle de prédiction du temps de livraison
=============================================================================

OBJECTIF:
    Entraîner un modèle de régression qui prédit le TEMPS DE LIVRAISON
    en fonction de :
        - distance à parcourir (cells)
        - charge utile (kg)
        - vitesse du vent (km/h)
        - condition météo (clear/windy/rainy/stormy)
        - batterie initiale du drone (%)

ROLE DANS LE SMA:
    Chaque DroneAgent utilise ce modèle pour ESTIMER son coût (temps prévu)
    avant de répondre à un CFP (Call For Proposal) du Dispatcher.
    → C'est le composant "intelligence prédictive" de l'agent.

CHOIX TECHNIQUE:
    RandomForestRegressor :
    - Robuste, peu de tuning
    - Gère les variables catégorielles (météo)
    - Prédictions rapides (essentiel : on prédit ~1x par seconde par drone)

DONNEES:
    Synthétiques, basées sur une formule physique réaliste + bruit aléatoire.
    → Pas besoin d'aller chercher un dataset externe.

USAGE:
    $ python -m ml.train_model
    → génère ml/delivery_model.joblib
=============================================================================
"""

import os
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
import joblib


# --- Constantes physiques de simulation ---
BASE_SPEED = 1.5            # cellules/seconde (à vide, météo claire)
PAYLOAD_PENALTY = 0.15      # +15% de temps par kg
WIND_PENALTY = {            # multiplicateur de temps selon météo
    "clear":  1.0,
    "windy":  1.3,
    "rainy":  1.6,
    "stormy": 2.2,
}
LOW_BATTERY_PENALTY = 1.4   # +40% si batterie < 30% (mode économie)


def generate_dataset(n_samples: int = 5000) -> pd.DataFrame:
    """
    Génère un dataset synthétique réaliste pour l'entraînement.

    Chaque ligne = une livraison passée avec ses caractéristiques + son temps réel.
    """
    rows = []
    weather_options = list(WIND_PENALTY.keys())

    for _ in range(n_samples):
        distance = np.random.randint(2, 60)
        payload = np.random.uniform(0.1, 5.0)       # entre 100g et 5kg
        wind_speed = np.random.uniform(0, 50)
        weather = np.random.choice(weather_options)
        battery_start = np.random.uniform(15, 100)

        # Calcul du temps "vrai" selon la physique simulée + bruit
        base_time = distance / BASE_SPEED                     # temps de base
        time_with_payload = base_time * (1 + PAYLOAD_PENALTY * payload)
        time_with_weather = time_with_payload * WIND_PENALTY[weather]

        if battery_start < 30:
            time_with_weather *= LOW_BATTERY_PENALTY

        # Bruit gaussien pour simuler imprécisions du monde réel
        noise = np.random.normal(0, 1.5)
        total_time = max(1.0, time_with_weather + noise)

        rows.append({
            "distance": distance,
            "payload": payload,
            "wind_speed": wind_speed,
            "weather": weather,
            "battery_start": battery_start,
            "delivery_time": total_time,
        })

    df = pd.DataFrame(rows)
    # Encodage one-hot de la météo (catégorielle)
    df = pd.get_dummies(df, columns=["weather"], prefix="weather")
    return df


def train_and_save(model_path: str):
    """Entraîne le modèle et le sauvegarde sur disque."""
    print("[ML] Génération du dataset synthétique (5000 livraisons)...")
    df = generate_dataset(5000)

    # Séparation features / cible
    y = df["delivery_time"]
    X = df.drop(columns=["delivery_time"])

    # On garde les noms des colonnes pour prédire dans le bon ordre plus tard
    feature_columns = list(X.columns)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    print(f"[ML] Entraînement RandomForestRegressor sur {len(X_train)} échantillons...")
    model = RandomForestRegressor(
        n_estimators=100,
        max_depth=12,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    # Evaluation
    preds = model.predict(X_test)
    mae = mean_absolute_error(y_test, preds)
    r2 = r2_score(y_test, preds)
    print(f"[ML] Performance — MAE: {mae:.2f}s | R²: {r2:.3f}")

    # Sauvegarde (modèle + ordre des features pour reproductibilité)
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    joblib.dump({"model": model, "features": feature_columns}, model_path)
    print(f"[ML] ✅ Modèle sauvegardé : {model_path}")


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    train_and_save(os.path.join(here, "delivery_model.joblib"))

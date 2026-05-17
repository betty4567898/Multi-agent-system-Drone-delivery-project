"""
=============================================================================
ML — Prédicteur de temps de livraison (interface d'utilisation)
=============================================================================

ROLE:
    Charger le modèle entraîné et fournir une API simple pour les agents :
        predictor.predict(distance, payload, weather, ...) → temps estimé

UTILISATION DANS LES AGENTS:
    Le DroneAgent appelle cette classe lors de la phase PROPOSE du Contract-Net
    pour estimer le temps qu'il prendrait pour effectuer la livraison.
    Plus le temps prédit est court, plus le drone est "compétitif" dans l'enchère.
=============================================================================
"""

import os
import joblib
import pandas as pd
from typing import Optional


# Instance unique chargée au démarrage (pattern singleton léger)
_predictor_instance: Optional["DeliveryPredictor"] = None


class DeliveryPredictor:
    """Wrapper autour du modèle sklearn entraîné."""

    def __init__(self, model_path: str):
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Modèle introuvable : {model_path}\n"
                f"Lance d'abord : python -m ml.train_model"
            )

        bundle = joblib.load(model_path)
        self.model = bundle["model"]
        self.feature_columns = bundle["features"]
        print(f"[Predictor] ✅ Modèle chargé ({len(self.feature_columns)} features)")

    def predict(
        self,
        distance: float,
        payload: float,
        wind_speed: float,
        weather: str,
        battery_start: float,
    ) -> float:
        """
        Prédit le temps de livraison (en secondes simulées).

        Args:
            distance: distance en cellules
            payload: charge en kg
            wind_speed: vitesse du vent en km/h
            weather: 'clear' / 'windy' / 'rainy' / 'stormy'
            battery_start: niveau de batterie au départ (0-100)

        Returns:
            Temps estimé en secondes (toujours > 0)
        """
        # Construction d'une ligne au format attendu par sklearn
        row = {
            "distance": distance,
            "payload": payload,
            "wind_speed": wind_speed,
            "battery_start": battery_start,
            "weather_clear": 1.0 if weather == "clear" else 0.0,
            "weather_windy": 1.0 if weather == "windy" else 0.0,
            "weather_rainy": 1.0 if weather == "rainy" else 0.0,
            "weather_stormy": 1.0 if weather == "stormy" else 0.0,
        }

        # On ordonne les colonnes EXACTEMENT comme à l'entraînement
        ordered = {col: row.get(col, 0.0) for col in self.feature_columns}
        X = pd.DataFrame([ordered])

        prediction = float(self.model.predict(X)[0])
        return max(1.0, prediction)  # garde-fou : pas de temps négatif


def get_predictor() -> DeliveryPredictor:
    """
    Retourne l'instance singleton du prédicteur.
    Charge le modèle à la première invocation seulement.
    """
    global _predictor_instance
    if _predictor_instance is None:
        here = os.path.dirname(os.path.abspath(__file__))
        model_path = os.path.join(here, "delivery_model.joblib")
        _predictor_instance = DeliveryPredictor(model_path)
    return _predictor_instance

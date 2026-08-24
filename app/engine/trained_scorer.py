"""
Trains a classical ML regressor (RandomForest) to predict a competency
score from extracted transcript features, using a labeled dataset.
Dataset-agnostic: train_from_dataset() takes [(transcript, score), ...].
Uses Leave-One-Out CV since realistic dataset sizes here are small
(likely under 1000 examples) — a single train/test split would be
unstable and easy to challenge.
"""
import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import LeaveOneOut, cross_val_predict
from scipy.stats import pearsonr
import joblib

from app.engine.feature_extraction import extract_features, features_to_vector, FEATURE_ORDER

MODEL_DIR = Path(__file__).parent.parent.parent / "data" / "models"
MODEL_PATH = MODEL_DIR / "trained_scorer.joblib"
METRICS_PATH = MODEL_DIR / "trained_scorer_metrics.json"


def train_from_dataset(dataset: list, n_estimators: int = 100, random_state: int = 42) -> dict:
    if len(dataset) < 5:
        raise ValueError(f"Need at least 5 labeled examples, got {len(dataset)}.")

    X = np.array([features_to_vector(extract_features(t)) for t, _ in dataset])
    y = np.array([score for _, score in dataset])

    model = RandomForestRegressor(n_estimators=n_estimators, random_state=random_state)

    loo = LeaveOneOut()
    predictions = cross_val_predict(model, X, y, cv=loo)

    r, p_value = pearsonr(y, predictions)
    mae = float(np.mean(np.abs(y - predictions)))
    rmse = float(np.sqrt(np.mean((y - predictions) ** 2)))

    model.fit(X, y)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)

    metrics = {
        "n_samples": len(dataset), "pearson_r": float(r), "p_value": float(p_value),
        "mae": mae, "rmse": rmse, "feature_order": FEATURE_ORDER, "cv_method": "leave_one_out",
    }
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)
    return metrics


def predict_score(transcript: str) -> float:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"No trained model at {MODEL_PATH}. Run train_from_dataset() first.")
    model = joblib.load(MODEL_PATH)
    vec = np.array([features_to_vector(extract_features(transcript))])
    return float(model.predict(vec)[0])


def get_last_training_metrics() -> dict:
    if not METRICS_PATH.exists():
        return {}
    with open(METRICS_PATH) as f:
        return json.load(f)

import os
import json
from typing import Tuple, Optional
from joblib import load
import numpy as np

MODEL_DIR_TEMPLATE = "/data/models/{household_id}/"
MODEL_FILE = "model.joblib"
META_FILE = "metadata.json"


def load_model(household_id: int):
    model_dir = MODEL_DIR_TEMPLATE.format(household_id=household_id)
    model_path = os.path.join(model_dir, MODEL_FILE)
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found for household {household_id}")
    return load(model_path)


def load_metadata(household_id: int) -> Optional[dict]:
    meta_path = os.path.join(MODEL_DIR_TEMPLATE.format(household_id=household_id), META_FILE)
    if not os.path.exists(meta_path):
        return None
    with open(meta_path, "r") as f:
        return json.load(f)


def predict_category(household_id: int, text: str) -> Tuple[Optional[int], float]:
    """
    Predict top category and confidence for given text.
    Returns (category_id, confidence_score)
    """
    model = load_model(household_id)
    if hasattr(model.named_steps["clf"], "predict_proba"):
        probs = model.predict_proba([text])[0]
        idx = int(np.argmax(probs))
        category = model.classes_[idx]
        confidence = float(probs[idx])
    else:
        # SVM: use decision_function
        pred = model.predict([text])[0]
        if hasattr(model.named_steps["clf"], "decision_function"):
            decision = model.decision_function([text])[0]
            confidence = float(np.max(decision)) if hasattr(decision, "__iter__") else float(decision)
        else:
            confidence = 1.0
        category = pred
    return category, confidence

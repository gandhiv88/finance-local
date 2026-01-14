import os
import joblib
import json
from typing import Any

MODEL_DIR_TEMPLATE = os.path.join("/data/models/{household_id}")
MODEL_FILE = "model.joblib"
META_FILE = "metadata.json"

def get_model_dir(household_id):
    return MODEL_DIR_TEMPLATE.format(household_id=household_id)

def get_model_path(household_id):
    d = get_model_dir(household_id)
    return os.path.join(d, MODEL_FILE)

def get_meta_path(household_id):
    d = get_model_dir(household_id)
    return os.path.join(d, META_FILE)

def save_model(household_id, model):
    d = get_model_dir(household_id)
    os.makedirs(d, exist_ok=True)
    joblib.dump(model, get_model_path(household_id))

def load_model(household_id):
    return joblib.load(get_model_path(household_id))

def save_metadata(household_id, meta: dict):
    d = get_model_dir(household_id)
    os.makedirs(d, exist_ok=True)
    with open(get_meta_path(household_id), "w") as f:
        json.dump(meta, f)

def load_metadata(household_id) -> Any:
    try:
        with open(get_meta_path(household_id), "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

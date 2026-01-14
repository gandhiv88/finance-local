from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import numpy as np
from datetime import datetime

from ..db import get_db
from ..auth.deps import require_roles
from ..models import User
from ..ingest.service import get_training_examples
from ..ml.trainer import train_classifier
from ..ml.predictor import predict_category, load_model

router = APIRouter(prefix="/ml", tags=["ml"])

class TrainRequest(BaseModel):
    household_id: Optional[int] = None
    model_type: Optional[str] = "svm"
    min_count: Optional[int] = 5
    exclude_income: Optional[bool] = True

class TrainResponse(BaseModel):
    n_examples: int
    n_train: int
    n_test: int
    accuracy: float
    per_class: dict
    model_type: str
    categories: list
    saved: bool

class PredictRequest(BaseModel):
    text: str
    household_id: int = None  # Optional, default to current user
    top_k: int = 3

class PredictResult(BaseModel):
    category_id: int
    confidence: float
    top_k: List[dict]

class RetrainIfNeededRequest(BaseModel):
    household_id: int = None
    min_new_examples: int = 50
    min_count: int = 5
    exclude_income: bool = True

class RetrainIfNeededResponse(BaseModel):
    retrained: bool
    n_new_examples: int
    last_trained_at: str = None
    last_example_count: int = None
    model_type: str = None
    categories: list = None
    saved: bool = False

@router.post("/train", response_model=TrainResponse)
def train_ml_model(
    req: TrainRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
):
    household_id = req.household_id or current_user.household_id
    examples = get_training_examples(db, household_id, exclude_income=req.exclude_income, min_count=req.min_count)
    if not examples:
        raise HTTPException(status_code=400, detail="Not enough training examples")
    texts, labels = zip(*examples)
    # Split train/test
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            texts, labels, test_size=0.2, stratify=labels, random_state=42
        )
    except Exception:
        # Fallback: no stratification
        X_train, X_test, y_train, y_test = train_test_split(
            texts, labels, test_size=0.2, random_state=42
        )
    # Train model
    metadata = train_classifier(household_id, list(zip(X_train, y_train)), model_type=req.model_type)
    # Evaluate
    from joblib import load
    import os
    model_path = f"/data/models/{household_id}/model.joblib"
    if not os.path.exists(model_path):
        raise HTTPException(status_code=500, detail="Model not saved")
    model = load(model_path)
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, output_dict=True)
    per_class = {str(k): v["support"] for k, v in report.items() if k not in ("accuracy", "macro avg", "weighted avg")}
    return TrainResponse(
        n_examples=len(examples),
        n_train=len(X_train),
        n_test=len(X_test),
        accuracy=acc,
        per_class=per_class,
        model_type=req.model_type,
        categories=metadata["categories"],
        saved=True,
    )

@router.post("/predict", response_model=PredictResult)
def predict_ml(
    req: PredictRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
):
    household_id = req.household_id or current_user.household_id
    try:
        model = load_model(household_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No model found for household {household_id}. Train one with /ml/train.")
    # Predict top category and confidence
    text = req.text
    if hasattr(model.named_steps["clf"], "predict_proba"):
        probs = model.predict_proba([text])[0]
        classes = model.classes_
        idx = int(np.argmax(probs))
        category_id = int(classes[idx])
        confidence = float(probs[idx])
        # Top K
        top_indices = np.argsort(probs)[::-1][:req.top_k]
        top_k = [
            {"category_id": int(classes[i]), "score": float(probs[i])}
            for i in top_indices
        ]
    else:
        # SVM: use decision_function
        pred = model.predict([text])[0]
        category_id = int(pred)
        confidence = 1.0
        top_k = [{"category_id": category_id, "score": 1.0}]
    return PredictResult(category_id=category_id, confidence=confidence, top_k=top_k)

@router.post("/retrain-if-needed", response_model=RetrainIfNeededResponse)
def retrain_if_needed(
    req: RetrainIfNeededRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
):
    household_id = req.household_id or current_user.household_id
    examples = get_training_examples(db, household_id, exclude_income=req.exclude_income, min_count=req.min_count)
    n_examples = len(examples)
    # Load metadata
    from ..ml.trainer import MODEL_DIR_TEMPLATE, META_FILE, train_classifier
    import os, json
    meta_path = os.path.join(MODEL_DIR_TEMPLATE.format(household_id=household_id), META_FILE)
    last_trained_at = None
    last_example_count = None
    if os.path.exists(meta_path):
        with open(meta_path, "r") as f:
            meta = json.load(f)
            last_trained_at = meta.get("last_trained_at")
            last_example_count = meta.get("last_example_count")
    else:
        meta = {}
    n_new = n_examples - (last_example_count or 0)
    if n_new >= req.min_new_examples:
        # Retrain
        metadata = train_classifier(household_id, examples)
        metadata["last_trained_at"] = datetime.utcnow().isoformat()
        metadata["last_example_count"] = n_examples
        with open(meta_path, "w") as f:
            json.dump(metadata, f)
        return RetrainIfNeededResponse(
            retrained=True,
            n_new_examples=n_new,
            last_trained_at=metadata["last_trained_at"],
            last_example_count=n_examples,
            model_type=metadata.get("model_type"),
            categories=metadata.get("categories"),
            saved=True,
        )
    else:
        return RetrainIfNeededResponse(
            retrained=False,
            n_new_examples=n_new,
            last_trained_at=last_trained_at,
            last_example_count=last_example_count,
            model_type=meta.get("model_type"),
            categories=meta.get("categories"),
            saved=os.path.exists(meta_path),
        )

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..auth.deps import get_db, require_roles
from ..models import User
from .schemas import TrainResponse, PredictResponse
from .trainer import get_training_examples
from .service import save_model, save_metadata, load_model
from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
import numpy as np
import os

router = APIRouter(prefix="/ml", tags=["ml"])

@router.post("/train", response_model=TrainResponse)
def train_ml(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"]))
):
    household_id = current_user.household_id
    examples = get_training_examples(db, household_id)
    if len(examples) < 50:
        raise HTTPException(status_code=400, detail="Not enough training examples (min 50 required)")
    categories = sorted(set(ex["category_id"] for ex in examples))
    if len(categories) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 unique categories to train")
    X = [ex["text"] for ex in examples]
    y = [ex["category_id"] for ex in examples]
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
    except ValueError:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2)),
        ("clf", LogisticRegression(max_iter=2000))
    ])
    model = pipeline.fit(X_train, y_train)
    accuracy = float(model.score(X_test, y_test))
    label_dist = dict(zip(*np.unique(y, return_counts=True)))
    # Save model and metadata
    model_dir = f"/data/models/{household_id}/"
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, "model.joblib")
    save_model(household_id, model)
    metadata = {
        "household_id": household_id,
        "categories": categories,
        "n_examples": len(examples),
        "label_distribution": label_dist,
        "accuracy": accuracy,
        "trained_at": datetime.utcnow().isoformat(),
    }
    save_metadata(household_id, metadata)
    return TrainResponse(
        examples=len(examples),
        categories=categories,
        accuracy=accuracy,
        model_path=model_path,
        trained_at=metadata["trained_at"]
    )

@router.post("/predict", response_model=PredictResponse)
def predict_ml(
    text: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"]))
):
    household_id = current_user.household_id
    try:
        model = load_model(household_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No model found for household {household_id}. Train one with /ml/train.")
    # Predict top 3
    proba = model.predict_proba([text])[0]
    classes = model.classes_
    topk_idx = np.argsort(proba)[::-1][:3]
    top_k = [{"category_id": int(classes[i]), "confidence": float(proba[i])} for i in topk_idx]
    category_id = int(classes[topk_idx[0]])
    confidence = float(proba[topk_idx[0]])
    return PredictResponse(category_id=category_id, confidence=confidence, top_k=top_k)

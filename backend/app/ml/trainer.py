import os
import json
from typing import List, Tuple
from joblib import dump
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
import numpy as np

MODEL_DIR_TEMPLATE = "/data/models/{household_id}/"
MODEL_FILE = "model.joblib"
META_FILE = "metadata.json"


def train_classifier(
    household_id: int,
    examples: List[Tuple[str, int]],
    model_type: str = "logreg"
) -> dict:
    """
    Train a text classifier and persist model + metadata.
    model_type: "logreg" or "svm"
    Returns metadata dict.
    """
    if not examples:
        raise ValueError("No training examples provided")
    texts, labels = zip(*examples)
    labels = list(labels)

    if model_type == "svm":
        clf = LinearSVC()
    else:
        clf = LogisticRegression(max_iter=2000)

    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2)),
        ("clf", clf)
    ])
    pipe.fit(texts, labels)

    # Save model and metadata
    model_dir = MODEL_DIR_TEMPLATE.format(household_id=household_id)
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, MODEL_FILE)
    dump(pipe, model_path)

    metadata = {
        "household_id": household_id,
        "model_type": model_type,
        "n_examples": len(examples),
        "categories": sorted(set(labels)),
    }
    meta_path = os.path.join(model_dir, META_FILE)
    with open(meta_path, "w") as f:
        json.dump(metadata, f)
    return metadata


def train_text_model(examples):
    X = [ex["text"] for ex in examples]
    y = [ex["category_id"] for ex in examples]
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2)),
        ("clf", LogisticRegression(max_iter=2000))
    ])
    model = pipeline.fit(X, y)
    y_pred = model.predict(X)
    report = classification_report(y, y_pred, output_dict=True)
    categories = list(np.unique(y))
    metrics = {
        "accuracy": report["accuracy"],
        "per_class": {str(k): v["f1-score"] for k, v in report.items() if k not in ("accuracy", "macro avg", "weighted avg")}
    }
    return model, metrics, categories


def get_training_examples(db, household_id: int, months: int = 24):
    """
    Return list of dicts: {"text": "<merchant> <description>", "category_id": <int>}
    Only include transactions with category_id not null and is_active true (if present).
    Scopes by household_id via bank_accounts join. Optionally limits to last N months.
    """
    from sqlalchemy import and_, or_, func
    from datetime import datetime, timedelta
    from ..models import Transaction, BankAccount

    query = db.query(Transaction).join(BankAccount, Transaction.account_id == BankAccount.id)
    query = query.filter(BankAccount.household_id == household_id)
    query = query.filter(Transaction.category_id != None)
    if hasattr(Transaction, "is_active"):
        query = query.filter(Transaction.is_active == True)
    if months:
        since = datetime.utcnow() - timedelta(days=30 * months)
        query = query.filter(Transaction.date >= since)
    results = query.all()
    examples = []
    for tx in results:
        merchant = getattr(tx, "merchant", None)
        desc = tx.description or ""
        text = f"{merchant} {desc}".strip() if merchant else desc
        examples.append({"text": text, "category_id": tx.category_id})
    return examples

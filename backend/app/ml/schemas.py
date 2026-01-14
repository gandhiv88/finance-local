from pydantic import BaseModel
from typing import List, Optional

class TrainRequest(BaseModel):
    household_id: int
    examples: List[dict]  # {"text": str, "category_id": int}
    model_type: Optional[str] = "logreg"

class TrainResponse(BaseModel):
    model_path: str
    metrics: dict
    categories: List[int]
    model_type: str

class PredictRequest(BaseModel):
    household_id: int
    text: str
    k: int = 3

class PredictResponse(BaseModel):
    category_id: Optional[int]
    confidence: Optional[float]
    top_k: List[dict]  # [{"category_id": int, "confidence": float}]

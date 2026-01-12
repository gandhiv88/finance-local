from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Household, User
from ..auth.security import hash_password

router = APIRouter(tags=["bootstrap"])


# Request/Response schemas
class BootstrapRequest(BaseModel):
    household_name: str
    name: str
    email: EmailStr
    password: str


class BootstrapUserResponse(BaseModel):
    id: int
    name: Optional[str]
    email: str
    role: str
    household_id: int
    household_name: str

    class Config:
        from_attributes = True


@router.post("/bootstrap", response_model=BootstrapUserResponse)
def bootstrap(
    body: BootstrapRequest,
    db: Session = Depends(get_db),
) -> BootstrapUserResponse:
    """
    Bootstrap the application with the first household and admin user.

    This endpoint can only be called once - when there are no users in the database.
    It creates the initial household and an admin user.
    """
    # Check if any users exist
    existing_user_count = db.query(User).count()
    if existing_user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bootstrap already completed",
        )

    # Create household
    household = Household(name=body.household_name)
    db.add(household)
    db.flush()  # Get the household ID

    # Create admin user
    user = User(
        household_id=household.id,
        name=body.name,
        email=body.email,
        password_hash=hash_password(body.password),
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return BootstrapUserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        household_id=user.household_id,
        household_name=household.name,
    )

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import UserOut
from ..auth.security import verify_password, hash_password
from ..auth.deps import get_current_user

router = APIRouter(prefix="/me", tags=["me"])


# Request schemas
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class MeUpdateRequest(BaseModel):
    name: Optional[str] = None


# Response schema
class StatusResponse(BaseModel):
    status: str


@router.post("/change-password", response_model=StatusResponse)
def change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StatusResponse:
    """
    Change the current user's password.
    Requires verification of current password.
    """
    # Verify current password
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password incorrect",
        )

    # Hash and update password
    current_user.password_hash = hash_password(body.new_password)
    db.commit()

    return StatusResponse(status="ok")


@router.patch("", response_model=UserOut)
def update_me(
    body: MeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserOut:
    """
    Update the current user's profile (name).
    """
    # Update name if provided
    if body.name is not None:
        current_user.name = body.name

    db.commit()
    db.refresh(current_user)

    return current_user

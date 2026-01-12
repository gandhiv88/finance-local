from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import UserCreate, UserOut
from ..auth.security import hash_password
from ..auth.deps import require_roles

router = APIRouter(prefix="/admin", tags=["admin"])


# Request schema for role update
class RoleUpdate(BaseModel):
    role: Literal["admin", "member", "viewer"]


# Request schema for user profile update
class AdminUserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None


# Request schema for password reset
class AdminResetPasswordRequest(BaseModel):
    new_password: str


# Response schema for password reset
class StatusResponse(BaseModel):
    status: str


@router.post("/users", response_model=UserOut)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"])),
) -> UserOut:
    """
    Create a new user in the same household as the current admin.
    """
    # Check email uniqueness
    existing_user = db.query(User).filter(User.email == body.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create user in admin's household
    user = User(
        household_id=current_user.household_id,
        name=body.name,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.get("/users", response_model=List[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"])),
) -> List[UserOut]:
    """
    List all users in the admin's household.
    """
    users = (
        db.query(User)
        .filter(User.household_id == current_user.household_id)
        .all()
    )
    return users


@router.patch("/users/{user_id}/disable", response_model=UserOut)
def disable_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"])),
) -> UserOut:
    """
    Disable a user (set is_active=False). Cannot disable self.
    """
    # Cannot disable self
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot disable your own account",
        )

    # Find user in same household
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.household_id == current_user.household_id,
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.is_active = False
    db.commit()
    db.refresh(user)

    return user


@router.patch("/users/{user_id}/role", response_model=UserOut)
def update_user_role(
    user_id: int,
    body: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"])),
) -> UserOut:
    """
    Update a user's role. Cannot change own role.
    """
    # Cannot change own role
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role",
        )

    # Find user in same household
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.household_id == current_user.household_id,
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.role = body.role
    db.commit()
    db.refresh(user)

    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user_profile(
    user_id: int,
    body: AdminUserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"])),
) -> UserOut:
    """
    Update a user's basic profile fields (name, email).
    """
    # Find user in same household
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.household_id == current_user.household_id,
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Update email if provided
    if body.email is not None:
        normalized_email = body.email.strip().lower()

        # Check email uniqueness (exclude current user)
        existing_user = (
            db.query(User)
            .filter(User.email == normalized_email, User.id != user_id)
            .first()
        )
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already in use by another user",
            )
        user.email = normalized_email

    # Update name if provided
    if body.name is not None:
        user.name = body.name

    db.commit()
    db.refresh(user)

    return user


@router.post("/users/{user_id}/reset-password", response_model=StatusResponse)
def reset_user_password(
    user_id: int,
    body: AdminResetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"])),
) -> StatusResponse:
    """
    Reset a user's password (admin-assisted recovery).
    Cannot reset own password through this endpoint.
    """
    # Cannot reset own password through admin endpoint
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot reset your own password through this endpoint",
        )

    # Find user in same household
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.household_id == current_user.household_id,
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Hash and update password
    user.password_hash = hash_password(body.new_password)
    db.commit()

    return StatusResponse(status="ok")

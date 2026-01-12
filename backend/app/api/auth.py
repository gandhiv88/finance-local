from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..auth.security import verify_password, create_access_token
from ..auth.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


# Request/Response schemas
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    name: Optional[str]
    email: str
    role: Optional[str]
    household_id: int

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    message: str


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """
    Authenticate user and return JWT access token.
    """
    # Find user by email
    user = db.query(User).filter(User.email == body.email).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify password
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    # Create access token
    token_data = {
        "user_id": user.id,
        "household_id": user.household_id,
        "role": user.role,
    }
    access_token = create_access_token(token_data)

    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """
    Get current authenticated user's information.
    """
    return UserResponse(
        id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        role=current_user.role,
        household_id=current_user.household_id,
    )


@router.post("/logout", response_model=MessageResponse)
def logout(current_user: User = Depends(get_current_user)) -> MessageResponse:
    """
    Logout endpoint. For MVP, just returns success.
    Client is responsible for deleting the token.
    """
    return MessageResponse(message="Successfully logged out")

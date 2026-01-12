from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from .security import decode_access_token

# HTTP Bearer token scheme
bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency to get the current authenticated user.

    Reads JWT from Authorization header, decodes it, fetches user from DB,
    and validates the user is active and token data matches.

    Args:
        credentials: Bearer token from Authorization header
        db: Database session

    Returns:
        User: The authenticated user object

    Raises:
        HTTPException: 401 if token invalid or user not found
        HTTPException: 403 if user inactive or household mismatch
    """
    token = credentials.credentials
    payload = decode_access_token(token)

    user_id = payload.get("user_id")
    token_household_id = payload.get("household_id")

    # Fetch user from database
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    # Verify token household matches user's household
    if user.household_id != token_household_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token household mismatch",
        )

    return user


def require_roles(allowed_roles: list[str]):
    """
    Factory function that returns a dependency to check user roles.

    Args:
        allowed_roles: List of allowed role strings (e.g., ["admin", "member"])

    Returns:
        A FastAPI dependency function that validates user role

    Usage:
        @app.get("/admin-only")
        def admin_endpoint(user: User = Depends(require_roles(["admin"]))):
            ...
    """
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' not authorized. "
                       f"Required: {allowed_roles}",
            )
        return current_user

    return role_checker

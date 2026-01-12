from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Category, User
from ..auth.deps import require_roles
from ..schemas import CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])

# Default categories to seed
DEFAULT_CATEGORIES = [
    "Income",
    "Transfer",
    "Groceries",
    "Dining",
    "Utilities",
    "Rent/Mortgage",
    "Transport",
    "Shopping",
    "Subscriptions",
    "Health",
    "Kids",
    "Entertainment",
    "Travel",
    "Fees",
]


class SeedResponse(BaseModel):
    created: int


def _check_for_cycle(
    db: Session,
    household_id: int,
    category_id: int,
    new_parent_id: int,
) -> bool:
    """
    Check if setting new_parent_id would create a cycle.
    Returns True if a cycle would be created.
    """
    if new_parent_id == category_id:
        return True

    # Walk up the parent chain from new_parent_id
    current_id = new_parent_id
    visited = {category_id}  # Include self to detect cycles

    while current_id is not None:
        if current_id in visited:
            return True
        visited.add(current_id)

        parent = (
            db.query(Category)
            .filter(
                Category.id == current_id,
                Category.household_id == household_id,
            )
            .first()
        )
        if not parent:
            break
        current_id = parent.parent_id

    return False


@router.post(
    "",
    response_model=CategoryOut,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    body: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
) -> CategoryOut:
    """
    Create a new category for the household.
    """
    # Check for duplicate name
    existing = (
        db.query(Category)
        .filter(
            Category.household_id == current_user.household_id,
            Category.name == body.name,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category with this name already exists",
        )

    # Validate parent_id if provided
    if body.parent_id:
        parent = (
            db.query(Category)
            .filter(
                Category.id == body.parent_id,
                Category.household_id == current_user.household_id,
            )
            .first()
        )
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent category not found",
            )

    category = Category(
        household_id=current_user.household_id,
        name=body.name,
        parent_id=body.parent_id,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.get("", response_model=List[CategoryOut])
def list_categories(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
) -> List[CategoryOut]:
    """
    List all categories for the household.
    Ordered by parent_id nulls first, then by name.
    """
    query = db.query(Category).filter(
        Category.household_id == current_user.household_id
    )

    if not include_inactive:
        query = query.filter(Category.is_active.is_(True))

    # Order by parent_id nulls first, then name
    categories = query.order_by(
        Category.parent_id.is_(None).desc(),
        Category.parent_id,
        Category.name,
    ).all()
    return categories


@router.get("/{category_id}", response_model=CategoryOut)
def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
) -> CategoryOut:
    """
    Get a single category by ID.
    """
    category = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.household_id == current_user.household_id,
        )
        .first()
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    return category


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    body: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
) -> CategoryOut:
    """
    Update a category.
    """
    category = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.household_id == current_user.household_id,
        )
        .first()
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    # Update name if provided
    if body.name is not None:
        # Check for duplicate
        existing = (
            db.query(Category)
            .filter(
                Category.household_id == current_user.household_id,
                Category.name == body.name,
                Category.id != category_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category with this name already exists",
            )
        category.name = body.name

    # Update parent_id if provided
    if body.parent_id is not None:
        if body.parent_id != 0:  # 0 means remove parent
            # Validate parent exists in same household
            parent = (
                db.query(Category)
                .filter(
                    Category.id == body.parent_id,
                    Category.household_id == current_user.household_id,
                )
                .first()
            )
            if not parent:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Parent category not found",
                )
            # Check for cycles
            if _check_for_cycle(
                db,
                current_user.household_id,
                category_id,
                body.parent_id,
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot set parent: would create a cycle",
                )
            category.parent_id = body.parent_id
        else:
            category.parent_id = None

    # Update is_active if provided
    if body.is_active is not None:
        category.is_active = body.is_active

    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}", response_model=CategoryOut)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
) -> CategoryOut:
    """
    Soft delete a category by setting is_active=False.
    Returns the updated category.
    """
    category = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.household_id == current_user.household_id,
        )
        .first()
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    # Soft delete - just mark as inactive
    category.is_active = False
    db.commit()
    db.refresh(category)
    return category


@router.post("/seed-defaults", response_model=SeedResponse)
def seed_default_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
) -> SeedResponse:
    """
    Seed default categories for the household.
    Idempotent: if household already has categories, do nothing.
    """
    # Check if household already has any categories
    existing_count = (
        db.query(Category)
        .filter(Category.household_id == current_user.household_id)
        .count()
    )

    if existing_count > 0:
        return SeedResponse(created=0)

    # Create default categories
    created = 0
    for name in DEFAULT_CATEGORIES:
        category = Category(
            household_id=current_user.household_id,
            name=name,
        )
        db.add(category)
        created += 1

    db.commit()
    return SeedResponse(created=created)

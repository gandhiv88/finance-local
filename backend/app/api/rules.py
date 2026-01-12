from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from ..db import get_db
from ..models import Category, CategoryRule, MerchantOverride, User
from ..auth.deps import require_roles
from ..categorize.engine import normalize_merchant_key
from ..schemas import CategoryOut

router = APIRouter(prefix="/rules", tags=["rules"])


# Merchant Override schemas
class MerchantOverrideCreate(BaseModel):
    merchant: str
    category_id: int


class MerchantOverrideOut(BaseModel):
    id: int
    merchant_key: str
    category_id: Optional[int]
    category: Optional[CategoryOut] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Category Rule schemas
class CategoryRuleCreate(BaseModel):
    pattern: str
    category_id: int
    priority: int = 100
    enabled: bool = True


class CategoryRuleUpdate(BaseModel):
    pattern: Optional[str] = None
    category_id: Optional[int] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None


class CategoryRuleOut(BaseModel):
    id: int
    pattern: str
    category_id: Optional[int]
    category: Optional[CategoryOut] = None
    priority: int
    enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


def _validate_category(
    db: Session,
    household_id: int,
    category_id: int,
) -> Category:
    """Validate that category exists and belongs to household."""
    category = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.household_id == household_id,
        )
        .first()
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category not found or does not belong to household",
        )
    return category


# Merchant Override endpoints
@router.post("/merchant-overrides", response_model=MerchantOverrideOut)
def create_or_update_merchant_override(
    body: MerchantOverrideCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
) -> MerchantOverrideOut:
    """
    Create or update a merchant override (upsert).
    """
    # Validate category belongs to household
    _validate_category(db, current_user.household_id, body.category_id)

    merchant_key = normalize_merchant_key(body.merchant)

    if not merchant_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid merchant name",
        )

    # Check if override exists
    existing = (
        db.query(MerchantOverride)
        .filter(
            MerchantOverride.household_id == current_user.household_id,
            MerchantOverride.merchant_key == merchant_key,
        )
        .first()
    )

    if existing:
        # Update existing
        existing.category_id = body.category_id
        db.commit()
        db.refresh(existing)
        override = existing
    else:
        # Create new
        override = MerchantOverride(
            household_id=current_user.household_id,
            merchant_key=merchant_key,
            category_id=body.category_id,
        )
        db.add(override)
        db.commit()
        db.refresh(override)

    # Reload with category relationship
    override = (
        db.query(MerchantOverride)
        .options(joinedload(MerchantOverride.category))
        .filter(MerchantOverride.id == override.id)
        .first()
    )
    return override


@router.get("/merchant-overrides", response_model=List[MerchantOverrideOut])
def list_merchant_overrides(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
) -> List[MerchantOverrideOut]:
    """
    List all merchant overrides for the household.
    """
    overrides = (
        db.query(MerchantOverride)
        .options(joinedload(MerchantOverride.category))
        .filter(MerchantOverride.household_id == current_user.household_id)
        .order_by(MerchantOverride.merchant_key)
        .all()
    )
    return overrides


@router.delete(
    "/merchant-overrides/{override_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_merchant_override(
    override_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
):
    """
    Delete a merchant override.
    """
    override = (
        db.query(MerchantOverride)
        .filter(
            MerchantOverride.id == override_id,
            MerchantOverride.household_id == current_user.household_id,
        )
        .first()
    )

    if not override:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant override not found",
        )

    db.delete(override)
    db.commit()
    return None


# Category Rule endpoints
@router.post("/category-rules", response_model=CategoryRuleOut)
def create_category_rule(
    body: CategoryRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
) -> CategoryRuleOut:
    """
    Create a new category rule.
    """
    # Validate category belongs to household
    _validate_category(db, current_user.household_id, body.category_id)

    rule = CategoryRule(
        household_id=current_user.household_id,
        pattern=body.pattern,
        category_id=body.category_id,
        priority=body.priority,
        enabled=body.enabled,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    # Reload with category relationship
    rule = (
        db.query(CategoryRule)
        .options(joinedload(CategoryRule.category))
        .filter(CategoryRule.id == rule.id)
        .first()
    )
    return rule


@router.get("/category-rules", response_model=List[CategoryRuleOut])
def list_category_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
) -> List[CategoryRuleOut]:
    """
    List all category rules for the household.
    """
    rules = (
        db.query(CategoryRule)
        .options(joinedload(CategoryRule.category))
        .filter(CategoryRule.household_id == current_user.household_id)
        .order_by(CategoryRule.priority.asc())
        .all()
    )
    return rules


@router.patch("/category-rules/{rule_id}", response_model=CategoryRuleOut)
def update_category_rule(
    rule_id: int,
    body: CategoryRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
) -> CategoryRuleOut:
    """
    Update a category rule.
    """
    rule = (
        db.query(CategoryRule)
        .filter(
            CategoryRule.id == rule_id,
            CategoryRule.household_id == current_user.household_id,
        )
        .first()
    )

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category rule not found",
        )

    # Update fields if provided
    if body.pattern is not None:
        rule.pattern = body.pattern
    if body.category_id is not None:
        # Validate category belongs to household
        _validate_category(db, current_user.household_id, body.category_id)
        rule.category_id = body.category_id
    if body.priority is not None:
        rule.priority = body.priority
    if body.enabled is not None:
        rule.enabled = body.enabled

    db.commit()
    db.refresh(rule)

    # Reload with category relationship
    rule = (
        db.query(CategoryRule)
        .options(joinedload(CategoryRule.category))
        .filter(CategoryRule.id == rule.id)
        .first()
    )
    return rule


@router.delete(
    "/category-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_category_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
):
    """
    Delete a category rule.
    """
    rule = (
        db.query(CategoryRule)
        .filter(
            CategoryRule.id == rule_id,
            CategoryRule.household_id == current_user.household_id,
        )
        .first()
    )

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category rule not found",
        )

    db.delete(rule)
    db.commit()
    return None

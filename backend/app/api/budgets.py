from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth.deps import require_roles
from ..db import get_db
from ..models import Budget, Category, User
from ..schemas import BudgetCreate, BudgetOut

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _parse_month(month_str: str) -> date:
    """Parse YYYY-MM string to first day of month date."""
    try:
        year, month = month_str.split("-")
        return date(int(year), int(month), 1)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail="Invalid month format. Expected YYYY-MM.",
        )


@router.post("", response_model=BudgetOut)
def create_or_update_budget(
    body: BudgetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
) -> BudgetOut:
    """
    Create or update a budget for a category in a given month.
    Upserts by (household_id, month, category_id).
    """
    household_id = current_user.household_id

    # Parse month
    month_date = _parse_month(body.month)

    # Validate category belongs to household
    category = (
        db.query(Category)
        .filter(
            Category.id == body.category_id,
            Category.household_id == household_id,
        )
        .first()
    )
    if not category:
        raise HTTPException(
            status_code=404,
            detail="Category not found.",
        )

    # Check for existing budget (upsert)
    existing = (
        db.query(Budget)
        .filter(
            Budget.household_id == household_id,
            Budget.month == month_date,
            Budget.category_id == body.category_id,
        )
        .first()
    )

    if existing:
        # Update existing budget
        existing.limit_amount = body.limit_amount
        db.commit()
        db.refresh(existing)
        return existing
    else:
        # Create new budget
        budget = Budget(
            household_id=household_id,
            month=month_date,
            category_id=body.category_id,
            limit_amount=body.limit_amount,
        )
        db.add(budget)
        db.commit()
        db.refresh(budget)
        return budget


@router.get("", response_model=List[BudgetOut])
def list_budgets(
    month: Optional[str] = Query(None, description="Filter by month (YYYY-MM)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
) -> List[BudgetOut]:
    """
    List budgets for the household, optionally filtered by month.
    """
    household_id = current_user.household_id

    query = db.query(Budget).filter(Budget.household_id == household_id)

    if month:
        month_date = _parse_month(month)
        query = query.filter(Budget.month == month_date)

    budgets = query.order_by(Budget.month.desc(), Budget.category_id).all()
    return budgets


@router.delete("/{budget_id}", status_code=204)
def delete_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
) -> None:
    """
    Delete a budget by ID (household scoped).
    """
    household_id = current_user.household_id

    budget = (
        db.query(Budget)
        .filter(
            Budget.id == budget_id,
            Budget.household_id == household_id,
        )
        .first()
    )

    if not budget:
        raise HTTPException(
            status_code=404,
            detail="Budget not found.",
        )

    db.delete(budget)
    db.commit()

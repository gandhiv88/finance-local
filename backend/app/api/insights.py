from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import get_db
from ..models import BankAccount, Budget, Category, Merchant, Transaction, User
from ..schemas import InsightOut

router = APIRouter(prefix="/insights", tags=["insights"])


def _parse_month(month_str: str) -> date:
    """Parse YYYY-MM string to first day of month date."""
    try:
        year, month = month_str.split("-")
        return date(int(year), int(month), 1)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid month format '{month_str}'. Expected YYYY-MM.",
        )


def _get_next_month(d: date) -> date:
    """Get first day of next month."""
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _get_prev_month(d: date) -> date:
    """Get first day of previous month."""
    if d.month == 1:
        return date(d.year - 1, 12, 1)
    return date(d.year, d.month - 1, 1)


def _get_category_expenses(
    db: Session,
    account_ids: List[int],
    month_start: date,
    month_end: date,
) -> dict[Optional[int], Decimal]:
    """Get expense totals by category for a date range."""
    expense_expr = func.abs(
        func.sum(case((Transaction.amount < 0, Transaction.amount), else_=0))
    )

    results = (
        db.query(Transaction.category_id, expense_expr.label("expense"))
        .filter(
            Transaction.bank_account_id.in_(account_ids),
            Transaction.posted_date >= month_start,
            Transaction.posted_date < month_end,
        )
        .group_by(Transaction.category_id)
        .all()
    )

    return {
        row.category_id: Decimal(str(row.expense)) if row.expense else Decimal("0")
        for row in results
    }


@router.get("/monthly", response_model=List[InsightOut])
def get_monthly_insights(
    month: str = Query(..., description="Month to analyze (YYYY-MM)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[InsightOut]:
    """
    Generate insights for a given month based on transaction and budget data.
    """
    household_id = current_user.household_id
    month_start = _parse_month(month)
    month_end = _get_next_month(month_start)

    # Get household's bank account IDs
    account_ids = [
        a[0] for a in db.query(BankAccount.id)
        .filter(BankAccount.household_id == household_id)
        .all()
    ]

    if not account_ids:
        return []

    insights: List[InsightOut] = []

    # Get current month expenses by category
    current_expenses = _get_category_expenses(
        db, account_ids, month_start, month_end
    )

    # Get category names
    category_names: dict[int, str] = {
        c.id: c.name
        for c in db.query(Category)
        .filter(Category.household_id == household_id)
        .all()
    }

    # =========================================================================
    # 1) Overspent categories
    # =========================================================================
    budgets = (
        db.query(Budget)
        .filter(
            Budget.household_id == household_id,
            Budget.month == month_start,
        )
        .all()
    )

    for budget in budgets:
        cat_id = budget.category_id
        limit_amt = Decimal(str(budget.limit_amount))
        expense = current_expenses.get(cat_id, Decimal("0"))

        if expense > limit_amt and limit_amt > 0:
            cat_name = category_names.get(cat_id, "Unknown")
            overspend = expense - limit_amt
            pct = float(expense / limit_amt * 100)
            insights.append(
                InsightOut(
                    type="overspend",
                    title=f"Over budget: {cat_name}",
                    detail=f"Spent ${expense:.2f} of ${limit_amt:.2f} "
                           f"budget ({pct:.0f}%). Over by ${overspend:.2f}.",
                    severity="warning",
                    category_id=cat_id,
                )
            )

    # =========================================================================
    # 2) Top spend categories
    # =========================================================================
    sorted_expenses = sorted(
        [
            (cat_id, exp)
            for cat_id, exp in current_expenses.items()
            if exp > 0
        ],
        key=lambda x: x[1],
        reverse=True,
    )[:3]

    if sorted_expenses:
        top_cats = []
        for cat_id, exp in sorted_expenses:
            name = category_names.get(cat_id, "Uncategorized") if cat_id else "Uncategorized"
            top_cats.append(f"{name} (${exp:.2f})")

        insights.append(
            InsightOut(
                type="top_spend",
                title="Top spending categories",
                detail=", ".join(top_cats),
                severity="info",
            )
        )

    # =========================================================================
    # 3) Subscription candidates
    # =========================================================================
    # Look for merchants with 2+ charges in last 60 days with similar amounts
    sixty_days_ago = month_end - timedelta(days=60)

    merchant_charges = (
        db.query(
            Transaction.merchant_id,
            Transaction.merchant_key,
            func.count(Transaction.id).label("charge_count"),
            func.avg(Transaction.amount).label("avg_amount"),
            func.min(Transaction.amount).label("min_amount"),
            func.max(Transaction.amount).label("max_amount"),
        )
        .filter(
            Transaction.bank_account_id.in_(account_ids),
            Transaction.posted_date >= sixty_days_ago,
            Transaction.posted_date < month_end,
            Transaction.amount < 0,  # Only expenses
            (Transaction.merchant_id.isnot(None)) |
            (Transaction.merchant_key.isnot(None)),
        )
        .group_by(Transaction.merchant_id, Transaction.merchant_key)
        .having(func.count(Transaction.id) >= 2)
        .all()
    )

    for row in merchant_charges:
        if row.avg_amount is None:
            continue

        avg = abs(float(row.avg_amount))
        min_amt = abs(float(row.min_amount))
        max_amt = abs(float(row.max_amount))

        # Check if amounts are within 10% of average
        if avg > 0 and max_amt <= avg * 1.1 and min_amt >= avg * 0.9:
            # Get merchant name
            merchant_name = None
            if row.merchant_id:
                merchant = db.query(Merchant).filter(
                    Merchant.id == row.merchant_id
                ).first()
                if merchant:
                    merchant_name = merchant.display_name
            if not merchant_name:
                merchant_name = row.merchant_key or "Unknown"

            insights.append(
                InsightOut(
                    type="subscription_candidate",
                    title=f"Possible subscription: {merchant_name}",
                    detail=f"{row.charge_count} charges averaging ${avg:.2f} "
                           f"in the last 60 days.",
                    severity="info",
                    merchant_id=row.merchant_id,
                )
            )

    # =========================================================================
    # 4) Unusual spike detection
    # =========================================================================
    # Compare this month vs average of previous 3 months
    prev_months_expenses: List[dict[Optional[int], Decimal]] = []

    prev_month = _get_prev_month(month_start)
    for _ in range(3):
        prev_end = _get_next_month(prev_month)
        prev_expenses = _get_category_expenses(
            db, account_ids, prev_month, prev_end
        )
        prev_months_expenses.append(prev_expenses)
        prev_month = _get_prev_month(prev_month)

    # Calculate 3-month average per category
    all_cat_ids = set(current_expenses.keys())
    for prev_exp in prev_months_expenses:
        all_cat_ids.update(prev_exp.keys())

    for cat_id in all_cat_ids:
        current = current_expenses.get(cat_id, Decimal("0"))

        # Get previous months' values
        prev_values = [
            prev_exp.get(cat_id, Decimal("0"))
            for prev_exp in prev_months_expenses
        ]
        non_zero_prev = [v for v in prev_values if v > 0]

        if len(non_zero_prev) < 2:
            # Not enough history to compare
            continue

        avg_prev = Decimal(str(sum(non_zero_prev) / len(non_zero_prev)))

        if avg_prev > 0:
            delta = current - avg_prev

            # Check for spike: > 1.5x and delta > $50
            if current > avg_prev * Decimal("1.5") and delta > Decimal("50"):
                cat_name = (
                    category_names.get(cat_id, "Uncategorized")
                    if cat_id else "Uncategorized"
                )
                pct_increase = float((current / avg_prev - 1) * 100)

                insights.append(
                    InsightOut(
                        type="unusual_spike",
                        title=f"Spending spike: {cat_name}",
                        detail=f"${current:.2f} this month vs ${avg_prev:.2f} "
                               f"avg (up {pct_increase:.0f}%, +${delta:.2f}).",
                        severity="warning",
                        category_id=cat_id,
                    )
                )

    return insights

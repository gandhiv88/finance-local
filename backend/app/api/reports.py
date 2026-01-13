from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, Date
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import get_db
from ..models import BankAccount, Budget, Category, Transaction, User
from ..schemas import MonthlySummaryRow

router = APIRouter(prefix="/reports", tags=["reports"])


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


@router.get("/monthly", response_model=List[MonthlySummaryRow])
def get_monthly_report(
    month_from: str = Query(..., description="Start month (YYYY-MM)"),
    month_to: str = Query(..., description="End month (YYYY-MM)"),
    account_id: Optional[int] = Query(None, description="Filter by account ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[MonthlySummaryRow]:
    """
    Get monthly summary report grouped by month and category.

    Returns income, expense, and net totals per category per month,
    along with budget information if available.
    """
    household_id = current_user.household_id

    # Parse month range
    from_date = _parse_month(month_from)
    to_date = _parse_month(month_to)

    if from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="month_from must be before or equal to month_to.",
        )

    # Get household's bank account IDs
    account_query = db.query(BankAccount.id).filter(
        BankAccount.household_id == household_id
    )
    if account_id:
        account_query = account_query.filter(BankAccount.id == account_id)
    account_ids = [a[0] for a in account_query.all()]

    if not account_ids:
        return []

    # Build the aggregation query
    # PostgreSQL: use date_trunc to get first day of month
    month_expr = func.date_trunc('month', Transaction.posted_date).cast(Date)

    # Income: sum of positive amounts
    income_expr = func.coalesce(
        func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)),
        0
    )

    # Expense: absolute value of sum of negative amounts
    expense_expr = func.coalesce(
        func.abs(func.sum(case((Transaction.amount < 0, Transaction.amount), else_=0))),
        0
    )

    # Build query with grouping
    query = (
        db.query(
            month_expr.label("month"),
            Transaction.category_id,
            Category.name.label("category_name"),
            income_expr.label("income_total"),
            expense_expr.label("expense_total"),
            func.count(Transaction.id).label("tx_count"),
        )
        .outerjoin(Category, Transaction.category_id == Category.id)
        .filter(
            Transaction.bank_account_id.in_(account_ids),
            Transaction.posted_date >= from_date,
            # End of month_to: we need transactions up to end of that month
            Transaction.posted_date < date(
                to_date.year + (1 if to_date.month == 12 else 0),
                (to_date.month % 12) + 1,
                1
            ),
        )
        .group_by(month_expr, Transaction.category_id, Category.name)
    )

    results = query.all()

    # Build response with budget data
    rows: List[MonthlySummaryRow] = []

    for row in results:
        # Parse month from string result
        if isinstance(row.month, str):
            month_date = date.fromisoformat(row.month)
        else:
            month_date = row.month

        income = Decimal(str(row.income_total)) if row.income_total else Decimal("0")
        expense = Decimal(str(row.expense_total)) if row.expense_total else Decimal("0")
        net = income - expense

        # Look up budget for this month/category
        budget_limit: Optional[Decimal] = None
        budget_used_pct: Optional[float] = None

        if row.category_id is not None:
            budget = (
                db.query(Budget)
                .filter(
                    Budget.household_id == household_id,
                    Budget.month == month_date,
                    Budget.category_id == row.category_id,
                )
                .first()
            )
            if budget and budget.limit_amount:
                budget_limit = Decimal(str(budget.limit_amount))
                if budget_limit > 0:
                    budget_used_pct = float(expense / budget_limit * 100)

        rows.append(
            MonthlySummaryRow(
                month=month_date,
                category_id=row.category_id,
                category_name=row.category_name or "Uncategorized",
                income_total=income,
                expense_total=expense,
                net_total=net,
                tx_count=row.tx_count,
                budget_limit=budget_limit,
                budget_used_pct=budget_used_pct,
            )
        )

    # Sort by month ascending, then expense descending
    rows.sort(key=lambda r: (r.month, -r.expense_total))

    return rows

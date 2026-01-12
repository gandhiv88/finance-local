from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from ..db import get_db
from ..models import BankAccount, Category, MerchantOverride, Transaction, User
from ..auth.deps import get_current_user
from ..categorize.engine import normalize_merchant_key
from ..schemas import TransactionOut, TransactionUpdate

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=List[TransactionOut])
def list_transactions(
    account_id: Optional[int] = Query(None),
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    category_id: Optional[int] = Query(None),
    uncategorized: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[TransactionOut]:
    """
    List transactions for the user's household.
    Supports filtering by account_id, month (YYYY-MM), category_id.
    Use uncategorized=true to get only transactions without a category.
    """
    # Start with transactions from household's bank accounts
    query = (
        db.query(Transaction)
        .options(joinedload(Transaction.category))
        .join(BankAccount, Transaction.bank_account_id == BankAccount.id)
        .filter(BankAccount.household_id == current_user.household_id)
    )

    # Filter by account_id if provided
    if account_id is not None:
        query = query.filter(Transaction.bank_account_id == account_id)

    # Filter by month if provided (YYYY-MM format)
    if month:
        try:
            year, month_num = map(int, month.split("-"))
            start_date = date(year, month_num, 1)
            # Calculate end of month
            if month_num == 12:
                end_date = date(year + 1, 1, 1)
            else:
                end_date = date(year, month_num + 1, 1)
            query = query.filter(
                Transaction.posted_date >= start_date,
                Transaction.posted_date < end_date,
            )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid month format. Use YYYY-MM.",
            )

    # Filter by category_id if provided
    if category_id is not None:
        query = query.filter(Transaction.category_id == category_id)

    # Filter for uncategorized transactions
    if uncategorized:
        query = query.filter(Transaction.category_id.is_(None))

    # Order by posted_date descending
    transactions = query.order_by(Transaction.posted_date.desc()).all()

    return transactions


@router.patch("/{transaction_id}", response_model=TransactionOut)
def update_transaction(
    transaction_id: int,
    body: TransactionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TransactionOut:
    """
    Update a transaction's category and mark as reviewed.
    """
    # Find transaction and verify household ownership
    transaction = (
        db.query(Transaction)
        .options(joinedload(Transaction.category))
        .join(BankAccount, Transaction.bank_account_id == BankAccount.id)
        .filter(
            Transaction.id == transaction_id,
            BankAccount.household_id == current_user.household_id,
        )
        .first()
    )

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    # Validate category_id belongs to household if provided
    if body.category_id is not None:
        category = (
            db.query(Category)
            .filter(
                Category.id == body.category_id,
                Category.household_id == current_user.household_id,
            )
            .first()
        )
        if not category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category not found or does not belong to household",
            )
        transaction.category_id = body.category_id

    # Update is_reviewed if provided
    if body.is_reviewed is not None:
        transaction.is_reviewed = body.is_reviewed

    # Create merchant override if requested
    if (
        body.create_merchant_override
        and transaction.merchant
        and body.category_id
    ):
        merchant_key = normalize_merchant_key(transaction.merchant)
        if merchant_key:
            # Upsert merchant override
            existing_override = (
                db.query(MerchantOverride)
                .filter(
                    MerchantOverride.household_id == current_user.household_id,
                    MerchantOverride.merchant_key == merchant_key,
                )
                .first()
            )
            if existing_override:
                existing_override.category_id = body.category_id
            else:
                override = MerchantOverride(
                    household_id=current_user.household_id,
                    merchant_key=merchant_key,
                    category_id=body.category_id,
                )
                db.add(override)

    db.commit()
    db.refresh(transaction)

    return transaction

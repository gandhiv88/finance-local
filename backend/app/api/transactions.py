from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..db import get_db
from ..models import BankAccount, Category, Merchant, Transaction, User
from ..auth.deps import get_current_user, require_roles
from ..categorize.merchant import extract_merchant_key
from ..schemas import (
    BulkTransactionUpdateRequest,
    BulkTransactionUpdateResponse,
    TransactionOut,
    TransactionsPage,
    TransactionUpdate,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=TransactionsPage)
def list_transactions(
    account_id: Optional[int] = Query(None),
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    category_id: Optional[int] = Query(None),
    uncategorized: bool = Query(False),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page (max 200)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TransactionsPage:
    """
    List transactions for the user's household with pagination.

    Supports filtering by:
    - account_id: Filter by specific bank account
    - month: Filter by month (YYYY-MM format)
    - category_id: Filter by category
    - uncategorized: If true, only show transactions without a category

    Pagination:
    - page: Page number, starting from 1 (default: 1)
    - page_size: Number of items per page (default: 50, max: 200)

    Returns paginated results with total count.
    """
    household_id = current_user.household_id

    # Subquery for household's bank account IDs (avoids join inflation)
    household_account_ids = (
        db.query(BankAccount.id)
        .filter(BankAccount.household_id == household_id)
        .subquery()
    )

    # Base query without joins (for accurate COUNT)
    base_query = db.query(Transaction).filter(
        Transaction.bank_account_id.in_(household_account_ids)
    )

    # Filter by account_id if provided
    if account_id is not None:
        base_query = base_query.filter(Transaction.bank_account_id == account_id)

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
            base_query = base_query.filter(
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
        base_query = base_query.filter(Transaction.category_id == category_id)

    # Filter for uncategorized transactions
    if uncategorized:
        base_query = base_query.filter(Transaction.category_id.is_(None))

    # Get total count (no joins, accurate count)
    total = base_query.with_entities(func.count(Transaction.id)).scalar() or 0

    # Data query with eager loading for category and merchant
    offset = (page - 1) * page_size
    transactions = (
        base_query
        .options(
            joinedload(Transaction.category),
            joinedload(Transaction.merchant_ref),
        )
        .order_by(Transaction.posted_date.desc(), Transaction.id.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return TransactionsPage(
        items=transactions,
        total=total,
        page=page,
        page_size=page_size,
    )


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
        .options(
            joinedload(Transaction.category),
            joinedload(Transaction.merchant_ref),
        )
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
    if body.create_merchant_override and body.category_id:
        # Ensure transaction has a merchant_id
        if not transaction.merchant_id:
            # Compute merchant_key and upsert Merchant
            merchant_key = extract_merchant_key(transaction.description)
            if merchant_key and merchant_key != "UNKNOWN":
                # Check if merchant already exists
                merchant = (
                    db.query(Merchant)
                    .filter(
                        Merchant.household_id == current_user.household_id,
                        Merchant.merchant_key == merchant_key,
                    )
                    .first()
                )
                if not merchant:
                    # Create new merchant
                    merchant = Merchant(
                        household_id=current_user.household_id,
                        merchant_key=merchant_key,
                        display_name=merchant_key,
                    )
                    db.add(merchant)
                    db.flush()

                # Link transaction to merchant
                transaction.merchant_id = merchant.id
                transaction.merchant_key = merchant_key

        # Now set the merchant's default category
        if transaction.merchant_id:
            merchant = (
                db.query(Merchant)
                .filter(Merchant.id == transaction.merchant_id)
                .first()
            )
            if merchant:
                merchant.default_category_id = body.category_id

        # Set transaction category
        transaction.category_id = body.category_id

        # Default is_reviewed to true for this action unless explicitly set to false
        if body.is_reviewed is None:
            transaction.is_reviewed = True

    db.commit()
    db.refresh(transaction)

    return transaction


@router.post("/bulk-update", response_model=BulkTransactionUpdateResponse)
def bulk_update_transactions(
    body: BulkTransactionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
) -> BulkTransactionUpdateResponse:
    """
    Bulk update transactions' category and/or reviewed status.
    Optionally apply category to merchants for future auto-categorization.
    """
    # Validate request
    if not body.transaction_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="transaction_ids cannot be empty",
        )

    if len(body.transaction_ids) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update more than 500 transactions at once",
        )

    household_id = current_user.household_id

    # Validate category_id belongs to household if provided
    if body.category_id is not None:
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
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category not found or does not belong to household",
            )

    # Fetch all transactions by ids, scoped to household
    transactions = (
        db.query(Transaction)
        .join(BankAccount, Transaction.bank_account_id == BankAccount.id)
        .filter(
            Transaction.id.in_(body.transaction_ids),
            BankAccount.household_id == household_id,
        )
        .all()
    )

    # Track counts
    updated_transactions = 0
    updated_merchant_ids: set[int] = set()
    found_ids = {tx.id for tx in transactions}
    skipped = len(body.transaction_ids) - len(found_ids)

    # Cache for merchants we've looked up/created
    merchant_cache: dict[str, Merchant] = {}

    for tx in transactions:
        changed = False

        # Update category_id if provided
        if body.category_id is not None:
            if tx.category_id != body.category_id:
                tx.category_id = body.category_id
                changed = True

        # Update is_reviewed if provided
        if body.is_reviewed is not None:
            if tx.is_reviewed != body.is_reviewed:
                tx.is_reviewed = body.is_reviewed
                changed = True

        # Apply to merchant if requested
        if body.apply_to_merchant and body.category_id is not None:
            # Ensure tx has merchant_id
            if not tx.merchant_id:
                merchant_key = extract_merchant_key(tx.description)
                if merchant_key and merchant_key != "UNKNOWN":
                    # Check cache first
                    if merchant_key in merchant_cache:
                        merchant = merchant_cache[merchant_key]
                    else:
                        # Look up or create merchant
                        merchant = (
                            db.query(Merchant)
                            .filter(
                                Merchant.household_id == household_id,
                                Merchant.merchant_key == merchant_key,
                            )
                            .first()
                        )
                        if not merchant:
                            merchant = Merchant(
                                household_id=household_id,
                                merchant_key=merchant_key,
                                display_name=merchant_key,
                            )
                            db.add(merchant)
                            db.flush()
                        merchant_cache[merchant_key] = merchant

                    tx.merchant_id = merchant.id
                    tx.merchant_key = merchant_key
                    changed = True

            # Set merchant's default category
            if tx.merchant_id and tx.merchant_id not in updated_merchant_ids:
                merchant = (
                    db.query(Merchant)
                    .filter(Merchant.id == tx.merchant_id)
                    .first()
                )
                if merchant:
                    merchant.default_category_id = body.category_id
                    updated_merchant_ids.add(tx.merchant_id)

        if changed:
            updated_transactions += 1

    db.commit()

    return BulkTransactionUpdateResponse(
        updated_transactions=updated_transactions,
        updated_merchants=len(updated_merchant_ids),
        skipped=skipped,
    )

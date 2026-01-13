from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import BankAccount, Merchant, Transaction, User
from ..auth.deps import require_roles
from ..categorize.engine import categorize_transaction
from ..categorize.merchant import extract_merchant_key, extract_display_name

router = APIRouter(prefix="/maintenance", tags=["maintenance"])

BATCH_SIZE = 500


class RecategorizeResponse(BaseModel):
    updated: int


@router.post("/recategorize", response_model=RecategorizeResponse)
def recategorize_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"])),
) -> RecategorizeResponse:
    """
    Recompute categories for uncategorized or unreviewed transactions.
    Processes in batches to avoid memory issues.
    """
    # Get household's bank account IDs
    account_ids = (
        db.query(BankAccount.id)
        .filter(BankAccount.household_id == current_user.household_id)
        .all()
    )
    account_ids = [a[0] for a in account_ids]

    if not account_ids:
        return RecategorizeResponse(updated=0)

    total_updated = 0
    offset = 0

    while True:
        # Fetch batch of transactions to recategorize
        # Target: uncategorized (category_id is None) or unreviewed
        transactions = (
            db.query(Transaction)
            .filter(
                Transaction.bank_account_id.in_(account_ids),
                (Transaction.category_id.is_(None)) |
                (Transaction.is_reviewed.is_(False)),
            )
            .limit(BATCH_SIZE)
            .offset(offset)
            .all()
        )

        if not transactions:
            break

        batch_updated = 0
        for txn in transactions:
            new_category_id = categorize_transaction(
                db,
                current_user.household_id,
                txn.description,
                txn.merchant,
            )
            if new_category_id != txn.category_id:
                txn.category_id = new_category_id
                batch_updated += 1

        db.commit()
        total_updated += batch_updated

        # If we got fewer than batch size, we're done
        if len(transactions) < BATCH_SIZE:
            break

        offset += BATCH_SIZE

    return RecategorizeResponse(updated=total_updated)


class BackfillMerchantsResponse(BaseModel):
    created_merchants: int
    updated_transactions: int


@router.post("/backfill-merchants", response_model=BackfillMerchantsResponse)
def backfill_merchants(
    force: bool = Query(
        False,
        description="If false, only process transactions with null merchant_id or merchant_key. "
        "If true, recompute for all transactions (useful after normalization upgrades).",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"])),
) -> BackfillMerchantsResponse:
    """
    Backfill merchant_key and merchant_id for household transactions.

    Recomputes merchant_key using the current normalization logic,
    upserts Merchant records, and links transactions to merchants.
    """
    household_id = current_user.household_id

    # Get household's bank account IDs
    account_ids = (
        db.query(BankAccount.id)
        .filter(BankAccount.household_id == household_id)
        .all()
    )
    account_ids = [a[0] for a in account_ids]

    if not account_ids:
        return BackfillMerchantsResponse(created_merchants=0, updated_transactions=0)

    created_merchants = 0
    updated_transactions = 0
    offset = 0

    # Cache for merchants we've already looked up/created this run
    merchant_cache: dict[str, int] = {}  # merchant_key -> merchant.id

    while True:
        # Build base query
        query = db.query(Transaction).filter(
            Transaction.bank_account_id.in_(account_ids)
        )

        # If not force, only process rows needing backfill
        if not force:
            query = query.filter(
                (Transaction.merchant_id.is_(None)) |
                (Transaction.merchant_key.is_(None))
            )

        transactions = query.limit(BATCH_SIZE).offset(offset).all()

        if not transactions:
            break

        for txn in transactions:
            # Compute merchant_key from description
            computed_key = extract_merchant_key(txn.description)

            # Check if merchant_key changed
            key_changed = txn.merchant_key != computed_key

            if key_changed:
                txn.merchant_key = computed_key

            # Skip UNKNOWN merchants - don't create merchant records for them
            if computed_key == "UNKNOWN":
                if txn.merchant_id is not None:
                    txn.merchant_id = None
                    updated_transactions += 1
                elif key_changed:
                    updated_transactions += 1
                continue

            # Get or create Merchant
            if computed_key in merchant_cache:
                merchant_id = merchant_cache[computed_key]
            else:
                # Try to find existing merchant
                merchant = (
                    db.query(Merchant)
                    .filter(
                        Merchant.household_id == household_id,
                        Merchant.merchant_key == computed_key,
                    )
                    .first()
                )

                if not merchant:
                    # Create new merchant
                    display_name = extract_display_name(txn.description)
                    merchant = Merchant(
                        household_id=household_id,
                        merchant_key=computed_key,
                        display_name=display_name,
                    )
                    db.add(merchant)
                    db.flush()  # Get the ID
                    created_merchants += 1

                merchant_id = merchant.id
                merchant_cache[computed_key] = merchant_id

            # Update transaction if needed
            if txn.merchant_id != merchant_id or key_changed:
                txn.merchant_id = merchant_id
                updated_transactions += 1

        db.commit()

        # If we got fewer than batch size, we're done
        if len(transactions) < BATCH_SIZE:
            break

        offset += BATCH_SIZE

    return BackfillMerchantsResponse(
        created_merchants=created_merchants,
        updated_transactions=updated_transactions,
    )


class RecategorizeMerchantResponse(BaseModel):
    updated: int


@router.post("/recategorize-merchant", response_model=RecategorizeMerchantResponse)
def recategorize_merchant_transactions(
    merchant_id: int = Query(..., description="The merchant ID to recategorize transactions for"),
    only_uncategorized: bool = Query(True, description="If true, only recategorize transactions without a category"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "member"])),
) -> RecategorizeMerchantResponse:
    """
    Recategorize transactions for a specific merchant.
    
    Uses the categorization engine which checks:
    1. Merchant.default_category_id
    2. MerchantOverride
    3. CategoryRules
    """
    household_id = current_user.household_id

    # Ensure merchant belongs to current user's household
    merchant = (
        db.query(Merchant)
        .filter(
            Merchant.id == merchant_id,
            Merchant.household_id == household_id,
        )
        .first()
    )

    if not merchant:
        raise HTTPException(
            status_code=404,
            detail="Merchant not found or does not belong to your household",
        )

    # Build query for transactions with this merchant
    query = db.query(Transaction).filter(Transaction.merchant_id == merchant_id)

    # Filter to only uncategorized if requested
    if only_uncategorized:
        query = query.filter(Transaction.category_id.is_(None))

    transactions = query.all()

    updated = 0
    for txn in transactions:
        new_category_id = categorize_transaction(
            db,
            household_id,
            txn.description,
            merchant=txn.merchant,
            merchant_id=txn.merchant_id,
            merchant_key=txn.merchant_key,
        )

        if new_category_id is not None and txn.category_id != new_category_id:
            txn.category_id = new_category_id
            updated += 1

    db.commit()

    return RecategorizeMerchantResponse(updated=updated)

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import BankAccount, Transaction, User
from ..auth.deps import require_roles
from ..categorize.engine import categorize_transaction

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

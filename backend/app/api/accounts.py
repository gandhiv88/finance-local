from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import BankAccount, Transaction
from ..schemas import BankAccountCreate, BankAccountOut
from ..auth.deps import get_current_user, require_roles

router = APIRouter(prefix="/accounts", tags=["accounts"])


# Request schema for account update
class BankAccountUpdate(BaseModel):
    display_name: Optional[str] = None
    currency: Optional[str] = None


@router.post("", response_model=BankAccountOut)
def create_account(
    body: BankAccountCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(["admin"])),
) -> BankAccountOut:
    """
    Create a new bank account in the admin's household.
    """
    account = BankAccount(
        household_id=current_user.household_id,
        bank_code=body.bank_code,
        display_name=body.display_name,
        currency=body.currency,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    return account


@router.get("", response_model=List[BankAccountOut])
def list_accounts(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> List[BankAccountOut]:
    """
    List all bank accounts in the user's household.
    """
    accounts = (
        db.query(BankAccount)
        .filter(BankAccount.household_id == current_user.household_id)
        .all()
    )
    return accounts


@router.patch("/{account_id}", response_model=BankAccountOut)
def update_account(
    account_id: int,
    body: BankAccountUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(["admin"])),
) -> BankAccountOut:
    """
    Update a bank account's display_name and/or currency.
    """
    # Find account in same household
    account = (
        db.query(BankAccount)
        .filter(
            BankAccount.id == account_id,
            BankAccount.household_id == current_user.household_id,
        )
        .first()
    )

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bank account not found",
        )

    # Update fields if provided
    if body.display_name is not None:
        account.display_name = body.display_name
    if body.currency is not None:
        account.currency = body.currency

    db.commit()
    db.refresh(account)

    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(["admin"])),
):
    """
    Delete a bank account. Blocked if transactions exist.
    """
    # Find account in same household
    account = (
        db.query(BankAccount)
        .filter(
            BankAccount.id == account_id,
            BankAccount.household_id == current_user.household_id,
        )
        .first()
    )

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bank account not found",
        )

    # Check for existing transactions
    transaction_count = (
        db.query(Transaction)
        .filter(Transaction.bank_account_id == account_id)
        .count()
    )

    if transaction_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete account with {transaction_count} transactions",
        )

    db.delete(account)
    db.commit()

    return None

import hashlib
import re
from typing import Dict

from sqlalchemy.orm import Session

from ..models import BankAccount, Import, Transaction
from ..categorize.engine import categorize_transaction
from .registry import get_parser


def _normalize_description(description: str) -> str:
    """Normalize description for fingerprint computation."""
    # Collapse multiple spaces, strip, lowercase
    normalized = re.sub(r"\s+", " ", description.strip().lower())
    return normalized


def _compute_fingerprint(posted_date, amount, description: str) -> str:
    """Compute SHA256 fingerprint for deduplication."""
    normalized_desc = _normalize_description(description)
    fingerprint_input = f"{posted_date.isoformat()}|{amount}|{normalized_desc}"
    return hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()


def ingest_import(db: Session, import_id: int) -> Dict:
    """
    Process an import: parse PDF and insert transactions.

    Args:
        db: Database session
        import_id: ID of the Import record to process

    Returns:
        Dict with imported_count, skipped_count, warning_count

    Raises:
        ValueError: If import not found or bank code unsupported
    """
    # Load Import record
    import_record = db.query(Import).filter(Import.id == import_id).first()
    if not import_record:
        raise ValueError(f"Import not found: {import_id}")

    if not import_record.stored_path:
        raise ValueError(f"Import {import_id} has no stored file")

    if not import_record.bank_code:
        raise ValueError(f"Import {import_id} has no bank_code")

    # Get household_id from bank account for categorization
    bank_account = (
        db.query(BankAccount)
        .filter(BankAccount.id == import_record.bank_account_id)
        .first()
    )
    household_id = bank_account.household_id if bank_account else None

    # Read PDF file
    with open(import_record.stored_path, "rb") as f:
        pdf_bytes = f.read()

    # Get parser and parse
    parser = get_parser(import_record.bank_code)
    result = parser.parse(pdf_bytes)

    # Track counts
    imported_count = 0
    skipped_count = 0
    
    # Track fingerprints in current batch to avoid duplicates within same import
    seen_fingerprints = set()

    # Process transactions
    for txn in result.transactions:
        fingerprint = _compute_fingerprint(
            txn.posted_date, txn.amount, txn.description
        )

        # Check for duplicate in current batch
        if fingerprint in seen_fingerprints:
            skipped_count += 1
            continue

        # Check for duplicate in database
        existing = (
            db.query(Transaction)
            .filter(Transaction.fingerprint == fingerprint)
            .first()
        )

        if existing:
            skipped_count += 1
            seen_fingerprints.add(fingerprint)
            continue

        # Insert new transaction with auto-categorization
        category_id = None
        if household_id:
            category_id = categorize_transaction(
                db=db,
                household_id=household_id,
                description=txn.description,
                merchant=txn.merchant if hasattr(txn, "merchant") else None,
            )

        transaction = Transaction(
            bank_account_id=import_record.bank_account_id,
            import_id=import_record.id,
            posted_date=txn.posted_date,
            description=txn.description,
            amount=txn.amount,
            fingerprint=fingerprint,
            category_id=category_id,
            is_reviewed=False,
        )
        db.add(transaction)
        seen_fingerprints.add(fingerprint)
        imported_count += 1

    # Update Import record
    import_record.imported_count = imported_count
    import_record.skipped_count = skipped_count
    import_record.warning_count = len(result.warnings)

    db.commit()

    return {
        "imported_count": imported_count,
        "skipped_count": skipped_count,
        "warning_count": len(result.warnings),
        "warnings": result.warnings,
    }

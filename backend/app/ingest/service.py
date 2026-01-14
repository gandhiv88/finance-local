import hashlib
import re
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from ..models import BankAccount, Import, Merchant, Transaction
from ..categorize.engine import categorize_transaction
from ..categorize.merchant import extract_merchant_key
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


def _get_or_create_merchant(
    db: Session,
    household_id: int,
    merchant_key: str,
) -> Optional[Merchant]:
    """
    Get existing merchant or create a new one.
    Upserts by (household_id, merchant_key).
    """
    if not merchant_key or merchant_key == "UNKNOWN":
        return None

    merchant = (
        db.query(Merchant)
        .filter(
            Merchant.household_id == household_id,
            Merchant.merchant_key == merchant_key,
        )
        .first()
    )

    if merchant:
        return merchant

    # Create new merchant
    merchant = Merchant(
        household_id=household_id,
        merchant_key=merchant_key,
        display_name=merchant_key,  # Start with key as display name
    )
    db.add(merchant)
    db.flush()  # Get the ID without committing
    return merchant


def ingest_import(db: Session, import_id: int) -> Dict:
    """
    Process an import: parse PDF and insert transactions.
    After commit, recategorize all newly inserted uncategorized transactions.
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
        merchant_key = None
        merchant_id = None
        merchant_record = None

        if household_id:
            # Extract and normalize merchant
            merchant_key = extract_merchant_key(txn.description)

            # Get or create merchant record
            merchant_record = _get_or_create_merchant(
                db, household_id, merchant_key
            )
            if merchant_record:
                merchant_id = merchant_record.id

            # Determine category_id:
            # 1) Use merchant's default_category_id if set
            # 2) Otherwise, apply category rules via categorize_transaction
            if merchant_record and merchant_record.default_category_id:
                category_id = merchant_record.default_category_id
            else:
                category_id = categorize_transaction(
                    db=db,
                    household_id=household_id,
                    description=txn.description,
                    merchant=merchant_record.display_name if merchant_record else merchant_key,
                    merchant_id=merchant_id,
                    merchant_key=merchant_key,
                )

        transaction = Transaction(
            bank_account_id=import_record.bank_account_id,
            import_id=import_record.id,
            posted_date=txn.posted_date,
            description=txn.description,
            merchant=merchant_record.display_name if merchant_record else (
                txn.merchant if hasattr(txn, "merchant") else None
            ),
            merchant_key=merchant_key,
            merchant_id=merchant_id,
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

    # --- Automatic recategorization of uncategorized transactions ---
    # Find all uncategorized transactions from this import
    uncategorized = db.query(Transaction).filter(
        Transaction.import_id == import_id,
        Transaction.category_id.is_(None)
    ).all()
    updated = 0
    # Apply rules/overrides as before
    for txn in uncategorized:
        new_category_id = categorize_transaction(
            db,
            household_id,
            txn.description,
            merchant=txn.merchant,
            merchant_id=txn.merchant_id,
            merchant_key=txn.merchant_key,
        )
        if new_category_id is not None:
            txn.category_id = new_category_id
            updated += 1
    # ML categorization for remaining uncategorized
    ml_applied = 0
    try:
        from app.categorize.engine import categorize_transactions_with_ml
        ml_result = categorize_transactions_with_ml(db, household_id, uncategorized, min_confidence=0.75)
        ml_applied = ml_result.get("ml_applied", 0)
    except Exception as e:
        print(f"[ingest_import] ML categorization skipped: {e}")
    if updated or ml_applied:
        db.commit()
    if updated > 0 or ml_applied > 0:
        print(f"[ingest_import] Recategorized {updated} (rules) + {ml_applied} (ML) transactions after import {import_id}")

    return {
        "imported_count": imported_count,
        "skipped_count": skipped_count,
        "warning_count": len(result.warnings),
        "warnings": result.warnings,
        "recategorized_count": updated,
        "ml_applied": ml_applied,
    }


def get_training_examples(db: Session, household_id: int, exclude_income: bool = True, min_count: int = 5) -> List[tuple]:
    """
    Return list of (text, category_id) for ML training.
    - text: merchant name (if present) + description
    - category_id: must not be null
    - exclude Income category (if requested)
    - filter out categories with < min_count examples
    """
    from sqlalchemy import func
    from ..models import Transaction, Category

    # Get Income category id(s) for household
    income_category_ids = []
    if exclude_income:
        income_cats = db.query(Category.id).filter(
            Category.household_id == household_id,
            func.lower(Category.name) == "income"
        ).all()
        income_category_ids = [row[0] for row in income_cats]

    # Query transactions with category
    query = db.query(
        Transaction.description,
        Transaction.merchant,
        Transaction.category_id
    ).filter(
        Transaction.category_id.isnot(None),
        Transaction.bank_account.has(household_id=household_id)
    )
    if income_category_ids:
        query = query.filter(~Transaction.category_id.in_(income_category_ids))

    rows = query.all()

    # Build (text, category_id) pairs
    examples = []
    for desc, merchant, cat_id in rows:
        text = f"{merchant} {desc}".strip() if merchant else desc
        examples.append((text, cat_id))

    # Filter out rare categories
    from collections import Counter
    cat_counts = Counter(cat_id for _, cat_id in examples)
    filtered = [(text, cat_id) for text, cat_id in examples if cat_counts[cat_id] >= min_count]
    return filtered

import re
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Category, CategoryRule, Merchant, MerchantOverride


# Common prefixes to strip from merchant names
STRIP_PREFIXES = [
    "POS PURCHASE",
    "POS PUR",
    "POS DEBIT",
    "DEBIT CARD PURCHASE",
    "DEBIT CARD",
    "CHECKCARD",
    "CHECK CARD",
    "VISA DEBIT",
    "MASTERCARD DEBIT",
    "RECURRING PAYMENT",
    "RECURRING",
    "PREAUTHORIZED",
    "PRE-AUTHORIZED",
    "PURCHASE",
    "WITHDRAWAL",
    "ACH DEBIT",
    "ACH CREDIT",
    "WIRE TRANSFER",
    "ONLINE TRANSFER",
    "MOBILE PAYMENT",
    "ZELLE PAYMENT",
    "ZELLE",
]


def normalize_merchant_key(s: str) -> str:
    """
    Normalize a merchant string for consistent matching.
    
    - Uppercase
    - Collapse whitespace
    - Strip common transaction prefixes
    """
    if not s:
        return ""
    
    # Uppercase and collapse whitespace
    normalized = " ".join(s.upper().split())
    
    # Strip common prefixes
    for prefix in STRIP_PREFIXES:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):].strip()
            break
    
    # Remove leading/trailing special characters
    normalized = re.sub(r"^[^A-Z0-9]+|[^A-Z0-9]+$", "", normalized)
    
    return normalized


def categorize_transaction(
    db: Session,
    household_id: int,
    description: str,
    merchant: Optional[str] = None,
    merchant_id: Optional[int] = None,
    merchant_key: Optional[str] = None,
) -> Optional[int]:
    """
    Categorize a transaction based on household rules.
    
    Returns category_id or None if no match found.
    
    Order of precedence:
    1. Merchant default_category_id (by merchant_id or merchant_key lookup)
    2. MerchantOverride (backward compatibility, exact match on merchant_key)
    3. Category rules (enabled, ordered by priority ascending)
    4. None (no match)
    """
    # 1. Check Merchant default_category_id
    if merchant_id:
        # Direct lookup by merchant_id
        merchant_record = (
            db.query(Merchant)
            .filter(Merchant.id == merchant_id)
            .first()
        )
        if merchant_record and merchant_record.default_category_id:
            return merchant_record.default_category_id
    
    # Compute merchant_key if not provided
    if not merchant_key:
        merchant_key = normalize_merchant_key(merchant or description)
    
    # Lookup by merchant_key
    if merchant_key:
        merchant_record = (
            db.query(Merchant)
            .filter(
                Merchant.household_id == household_id,
                Merchant.merchant_key == merchant_key,
            )
            .first()
        )
        if merchant_record and merchant_record.default_category_id:
            return merchant_record.default_category_id
    
    # 2. Check MerchantOverride (backward compatibility)
    if merchant_key:
        override = (
            db.query(MerchantOverride)
            .filter(
                MerchantOverride.household_id == household_id,
                MerchantOverride.merchant_key == merchant_key,
            )
            .first()
        )
        if override and override.category_id:
            return override.category_id
    
    # 3. Check household category rules
    rules = (
        db.query(CategoryRule)
        .filter(
            CategoryRule.household_id == household_id,
            CategoryRule.enabled.is_(True),
        )
        .order_by(CategoryRule.priority.asc())
        .all()
    )
    
    search_text = description.upper()
    
    for rule in rules:
        try:
            if re.search(rule.pattern, search_text, re.IGNORECASE):
                if rule.category_id:
                    return rule.category_id
        except re.error:
            # Invalid regex, skip this rule
            continue
    
    # 4. No match found
    return None


def get_or_create_category(
    db: Session,
    household_id: int,
    name: str,
) -> Category:
    """
    Get existing category by name or create a new one.
    Useful for seeding default categories.
    """
    existing = (
        db.query(Category)
        .filter(
            Category.household_id == household_id,
            Category.name == name,
        )
        .first()
    )
    
    if existing:
        return existing
    
    category = Category(
        household_id=household_id,
        name=name,
    )
    db.add(category)
    db.flush()  # Get the ID without committing
    return category

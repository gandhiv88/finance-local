"""
Learning router for auto-generating category rules from reviewed transactions.
"""

import re
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import BankAccount, CategoryRule, Transaction, User
from ..auth.deps import require_roles

router = APIRouter(prefix="/learning", tags=["learning"])

# Minimum thresholds for rule generation
MIN_SUPPORT = 5  # Minimum occurrences of a token
MIN_PRECISION = 0.90  # Minimum precision (token in category / total)

# Stopwords to ignore during tokenization
STOPWORDS: Set[str] = {
    "THE",
    "AND",
    "FOR",
    "FROM",
    "WITH",
    "POS",
    "PURCHASE",
    "DEBIT",
    "CREDIT",
    "CARD",
    "ONLINE",
    "PAYMENT",
    "TRANSFER",
    "TRANSACTION",
    "ACH",
    "WITHDRAWAL",
    "DEPOSIT",
    "CHECK",
    "WIRE",
    "MOBILE",
    "RECURRING",
    "AUTHORIZED",
    "REF",
    "CONF",
    "TXN",
    "INC",
    "LLC",
    "CORP",
    "LTD",
}


class GenerateRulesResponse(BaseModel):
    created: int
    updated: int
    candidates: int


def _tokenize(text: str) -> List[str]:
    """
    Tokenize text for rule generation.
    - Split on non-alphanumerics
    - Uppercase
    - Discard tokens shorter than 3 characters
    - Discard stopwords
    """
    if not text:
        return []

    # Split on non-alphanumeric characters
    tokens = re.split(r"[^A-Za-z0-9]+", text.upper())

    # Filter tokens
    result = []
    for token in tokens:
        if len(token) < 3:
            continue
        if token in STOPWORDS:
            continue
        # Skip pure numbers
        if token.isdigit():
            continue
        result.append(token)

    return result


def _escape_for_regex(token: str) -> str:
    """Escape a token to be used safely in a regex pattern."""
    return re.escape(token)


def _compute_priority(precision: float, support: int) -> int:
    """
    Compute rule priority based on precision and support.
    Higher confidence -> lower priority number (runs first).
    Range: 10-100
    """
    # Base priority from precision (0.90 -> 50, 1.0 -> 10)
    precision_score = int((1.0 - precision) * 400)  # 0 to 40

    # Adjust by support (more support -> lower priority)
    support_score = max(0, 50 - min(support, 50))  # 0 to 50

    priority = 10 + precision_score + support_score // 2
    return min(max(priority, 10), 100)


@router.post("/generate-rules", response_model=GenerateRulesResponse)
def generate_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"])),
) -> GenerateRulesResponse:
    """
    Auto-generate category rules from reviewed transactions.

    Analyzes reviewed transactions to find token patterns that
    consistently map to specific categories, then creates rules
    for high-confidence patterns.
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
        return GenerateRulesResponse(created=0, updated=0, candidates=0)

    # Query reviewed transactions with category_id set
    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.bank_account_id.in_(account_ids),
            Transaction.is_reviewed.is_(True),
            Transaction.category_id.isnot(None),
        )
        .all()
    )

    if not transactions:
        return GenerateRulesResponse(created=0, updated=0, candidates=0)

    # Build token statistics
    # token -> category_id -> count
    token_category_counts: Dict[str, Dict[int, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    # token -> total count
    token_total_counts: Dict[str, int] = defaultdict(int)

    for txn in transactions:
        # Combine description and merchant_key for tokenization
        text_parts = [txn.description or ""]
        if txn.merchant_key:
            text_parts.append(txn.merchant_key)
        combined_text = " ".join(text_parts)

        tokens = _tokenize(combined_text)
        # Use set to count each token once per transaction
        unique_tokens = set(tokens)

        for token in unique_tokens:
            token_category_counts[token][txn.category_id] += 1
            token_total_counts[token] += 1

    # Generate candidate rules
    candidates: List[Tuple[str, int, float, int]] = []  # (token, cat_id, prec, sup)

    for token, total_count in token_total_counts.items():
        if total_count < MIN_SUPPORT:
            continue

        # Find majority category
        category_counts = token_category_counts[token]
        best_category_id = max(category_counts, key=category_counts.get)
        best_count = category_counts[best_category_id]

        # Calculate precision
        precision = best_count / total_count

        if precision >= MIN_PRECISION:
            candidates.append((token, best_category_id, precision, total_count))

    # Sort candidates by precision (desc), then support (desc)
    candidates.sort(key=lambda x: (-x[2], -x[3]))

    # Upsert rules
    created = 0
    updated = 0

    for token, category_id, precision, support in candidates:
        # Create regex pattern (word boundary match)
        pattern = r"\b" + _escape_for_regex(token) + r"\b"
        priority = _compute_priority(precision, support)

        # Check if rule already exists
        existing_rule = (
            db.query(CategoryRule)
            .filter(
                CategoryRule.household_id == household_id,
                CategoryRule.pattern == pattern,
            )
            .first()
        )

        if existing_rule:
            # Update existing rule
            existing_rule.category_id = category_id
            existing_rule.priority = priority
            existing_rule.enabled = True
            updated += 1
        else:
            # Create new rule
            rule = CategoryRule(
                household_id=household_id,
                pattern=pattern,
                category_id=category_id,
                priority=priority,
                enabled=True,
            )
            db.add(rule)
            created += 1

    db.commit()

    return GenerateRulesResponse(
        created=created,
        updated=updated,
        candidates=len(candidates),
    )

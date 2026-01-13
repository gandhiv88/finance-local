"""
Merchant normalization for bank transaction descriptions.

Extracts stable merchant keys from raw transaction descriptions
using deterministic, offline heuristics.
"""

import re
from typing import List, Optional, Tuple

# Common transaction prefixes to strip
STRIP_PREFIXES = [
    "POS PURCHASE",
    "POS PUR",
    "POS DEBIT",
    "POS REFUND",
    "DEBIT CARD PURCHASE",
    "DEBIT CARD REFUND",
    "DEBIT CARD",
    "CREDIT CARD",
    "CHECKCARD",
    "CHECK CARD",
    "VISA DEBIT",
    "VISA CREDIT",
    "MASTERCARD DEBIT",
    "MASTERCARD CREDIT",
    "RECURRING PAYMENT",
    "RECURRING",
    "PREAUTHORIZED",
    "PRE-AUTHORIZED",
    "AUTHORIZED",
    "PURCHASE",
    "WITHDRAWAL",
    "ACH DEBIT",
    "ACH CREDIT",
    "ACH PAYMENT",
    "ACH",
    "WIRE TRANSFER",
    "WIRE",
    "ONLINE TRANSFER",
    "ONLINE PAYMENT",
    "ONLINE",
    "MOBILE PAYMENT",
    "MOBILE TRANSFER",
    "MOBILE",
    "ZELLE PAYMENT",
    "ZELLE TO",
    "ZELLE FROM",
    "ZELLE",
    "VENMO PAYMENT",
    "VENMO CASHOUT",
    "VENMO",
    "PAYPAL TRANSFER",
    "PAYPAL PAYMENT",
    "PAYPAL",
    "SQUARE PAYMENT",
    "SQUARE",
    "CASH APP",
    "ATM WITHDRAWAL",
    "ATM DEPOSIT",
    "ATM",
    "DEPOSIT",
    "REFUND",
    "RETURN",
]

# Generic tokens to filter out (not useful for merchant identification)
GENERIC_TOKENS = {
    "PAYMENT",
    "TRANSFER",
    "CHECK",
    "WITHDRAWAL",
    "DEPOSIT",
    "ONLINE",
    "CARD",
    "DEBIT",
    "CREDIT",
    "PURCHASE",
    "TRANSACTION",
    "TXN",
    "REF",
    "REFERENCE",
    "CONF",
    "CONFIRMATION",
    "AUTH",
    "AUTHORIZED",
    "PENDING",
    "POSTED",
    "PROCESSED",
    "COMPLETED",
    "FROM",
    "TO",
    "FOR",
    "THE",
    "AND",
    "INC",
    "LLC",
    "CORP",
    "LTD",
    "CO",
    "POS",
}

# Special merchant mappings (prefix/contains -> canonical name)
MERCHANT_MAPPINGS: List[Tuple[str, str, str]] = [
    # (match_type, pattern, canonical_name)
    # match_type: "startswith", "contains", "equals"
    ("startswith", "COSTCO", "COSTCO"),
    ("startswith", "AMZN", "AMAZON"),
    ("contains", "AMAZON", "AMAZON"),
    ("startswith", "AMAZN", "AMAZON"),
    ("equals", "WAL-MART", "WALMART"),
    ("startswith", "WALMART", "WALMART"),
    ("startswith", "WAL MART", "WALMART"),
    ("startswith", "TARGET", "TARGET"),
    ("startswith", "STARBUCKS", "STARBUCKS"),
    ("startswith", "SBUX", "STARBUCKS"),
    ("startswith", "MCDONALD", "MCDONALDS"),
    ("startswith", "NETFLIX", "NETFLIX"),
    ("startswith", "SPOTIFY", "SPOTIFY"),
    ("startswith", "UBER EATS", "UBER EATS"),
    ("startswith", "UBEREATS", "UBER EATS"),
    ("startswith", "UBER", "UBER"),
    ("startswith", "LYFT", "LYFT"),
    ("startswith", "DOORDASH", "DOORDASH"),
    ("startswith", "GRUBHUB", "GRUBHUB"),
    ("startswith", "CHIPOTLE", "CHIPOTLE"),
    ("startswith", "CHEVRON", "CHEVRON"),
    ("startswith", "SHELL", "SHELL"),
    ("startswith", "EXXON", "EXXON"),
    ("startswith", "CVS", "CVS"),
    ("startswith", "WALGREENS", "WALGREENS"),
    ("startswith", "TRADER JOE", "TRADER JOES"),
    ("startswith", "WHOLE FOODS", "WHOLE FOODS"),
    ("startswith", "WHOLEFOODS", "WHOLE FOODS"),
    ("startswith", "HOME DEPOT", "HOME DEPOT"),
    ("startswith", "HOMEDEPOT", "HOME DEPOT"),
    ("startswith", "LOWES", "LOWES"),
    ("startswith", "LOWE'S", "LOWES"),
    ("startswith", "BESTBUY", "BEST BUY"),
    ("startswith", "BEST BUY", "BEST BUY"),
]

# Regex patterns
DATE_PATTERN = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
LONG_NUMBER_PATTERN = re.compile(r"\b\d{5,}\b")
STORE_NUMBER_PATTERN = re.compile(r"#\d+")
TRAILING_DIGITS_PATTERN = re.compile(r"\s+\d+$")
# Separators to normalize to space
SEPARATOR_PATTERN = re.compile(r"[*.\-—_]+")
# City/state pattern: 2-letter state code at end, optionally preceded by city
CITY_STATE_PATTERN = re.compile(
    r"\s+[A-Z]{2,}\s+[A-Z]{2}\s*$"  # e.g., "SAN FRANCISCO CA"
)
STATE_ONLY_PATTERN = re.compile(r"\s+[A-Z]{2}\s*$")  # e.g., "CA" at end
# Token patterns
VALID_TOKEN_PATTERN = re.compile(r"^[A-Z0-9&.'\-]+$")
LETTERS_ONLY_PATTERN = re.compile(r"^[A-Z]+$")


def normalize_text(s: str) -> str:
    """
    Basic text normalization: uppercase, strip, collapse whitespace.
    """
    if not s:
        return ""
    return " ".join(s.upper().split())


def _normalize_separators(text: str) -> str:
    """Normalize common separators to spaces."""
    return SEPARATOR_PATTERN.sub(" ", text)


def _strip_prefixes(text: str) -> str:
    """Remove common transaction prefixes."""
    for prefix in STRIP_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            # Check again in case of compound prefixes
            break
    return text


def _remove_dates(text: str) -> str:
    """Remove date patterns like 01/12 or 01/12/26."""
    return DATE_PATTERN.sub("", text)


def _remove_long_numbers(text: str) -> str:
    """Remove reference/trace numbers (5+ digit sequences)."""
    return LONG_NUMBER_PATTERN.sub("", text)


def _remove_store_numbers(text: str) -> str:
    """Remove store numbers like #1234."""
    return STORE_NUMBER_PATTERN.sub("", text)


def _remove_trailing_digits(text: str) -> str:
    """Remove trailing digit sequences."""
    return TRAILING_DIGITS_PATTERN.sub("", text)


def _remove_location_suffix(text: str) -> str:
    """
    Remove trailing city/state patterns.
    Simple heuristic: remove 2-letter state codes at end.
    """
    # First try city + state pattern
    text = CITY_STATE_PATTERN.sub("", text)
    # Then try state only (be careful not to remove merchant names)
    # Only remove if there's substantial text before it
    if len(text) > 5:
        text = STATE_ONLY_PATTERN.sub("", text)
    return text.strip()


def _check_special_merchants(text: str) -> Optional[str]:
    """
    Check for special merchant patterns and return canonical name.
    Returns None if no match found.
    """
    for match_type, pattern, canonical in MERCHANT_MAPPINGS:
        if match_type == "startswith":
            if text.startswith(pattern):
                return canonical
        elif match_type == "contains":
            if pattern in text:
                return canonical
        elif match_type == "equals":
            if text == pattern:
                return canonical
    return None


def _is_valid_token(token: str) -> bool:
    """Check if token is valid for merchant key."""
    if not token or len(token) < 2:
        return False
    if token in GENERIC_TOKENS:
        return False
    if not VALID_TOKEN_PATTERN.match(token):
        return False
    # Reject tokens that are all digits
    if token.isdigit():
        return False
    return True


def _is_strong_token(token: str) -> bool:
    """Check if token is a strong (letters-only) token."""
    return bool(LETTERS_ONLY_PATTERN.match(token)) and len(token) >= 3


def _extract_tokens(text: str, max_tokens: int = 2) -> List[str]:
    """
    Extract meaningful tokens from text.
    Returns up to max_tokens valid tokens, preferring letters-only tokens.
    """
    tokens = text.split()
    strong_tokens = []
    other_tokens = []

    for token in tokens:
        # Clean token of trailing punctuation
        token = token.strip(".,;:!?*")
        if not _is_valid_token(token):
            continue

        if _is_strong_token(token):
            strong_tokens.append(token)
        else:
            other_tokens.append(token)

    # Prefer strong tokens, fall back to others
    result = []
    for token in strong_tokens:
        result.append(token)
        if len(result) >= max_tokens:
            break

    # If we don't have enough, add other tokens
    if len(result) < max_tokens:
        for token in other_tokens:
            result.append(token)
            if len(result) >= max_tokens:
                break

    return result


def extract_merchant_key(description: str) -> str:
    """
    Extract a stable merchant key from a transaction description.

    Returns a normalized key like "COSTCO", "AMAZON", "NETFLIX".
    Returns "UNKNOWN" if no meaningful merchant can be extracted.
    """
    if not description:
        return "UNKNOWN"

    # Step 1: Normalize
    text = normalize_text(description)

    # Step 2: Strip common prefixes
    text = _strip_prefixes(text)

    # Step 3: Normalize separators to spaces
    text = _normalize_separators(text)

    # Step 4: Remove dates
    text = _remove_dates(text)

    # Step 5: Remove long numbers (reference/trace numbers)
    text = _remove_long_numbers(text)

    # Step 6: Remove store numbers
    text = _remove_store_numbers(text)

    # Step 7: Remove trailing digits
    text = _remove_trailing_digits(text)

    # Step 8: Collapse whitespace again
    text = " ".join(text.split())

    # Step 9: Check for special merchant patterns FIRST
    # (before removing location suffix which might remove useful info)
    special_match = _check_special_merchants(text)
    if special_match:
        return special_match

    # Step 10: Remove location suffix
    text = _remove_location_suffix(text)

    # Step 11: Check special merchants again after cleanup
    special_match = _check_special_merchants(text)
    if special_match:
        return special_match

    # Step 12: Extract meaningful tokens (1-2 strong tokens)
    tokens = _extract_tokens(text, max_tokens=2)

    if not tokens:
        return "UNKNOWN"

    # Join tokens to form merchant key
    merchant_key = " ".join(tokens)

    # Final cleanup
    merchant_key = merchant_key.strip()

    return merchant_key if merchant_key else "UNKNOWN"


def extract_display_name(description: str) -> str:
    """
    Extract a human-friendly display name from a transaction description.

    Currently returns the same as merchant_key but could be enhanced
    to provide nicer formatting (title case, etc.).
    """
    key = extract_merchant_key(description)

    if key == "UNKNOWN":
        return key

    # Title case for display, but keep certain words uppercase
    # For now, just return the key as-is (uppercase)
    return key

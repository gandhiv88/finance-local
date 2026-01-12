import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple

import pdfplumber

from .base import BankParser, ParsedTransaction, ParseResult


class BofAParser(BankParser):
    """Parser for Bank of America PDF statements."""

    bank_code = "bofa"

    # Section markers (lowercase for matching)
    DEPOSIT_MARKERS = [
        "deposits and other additions",
        "deposits",
    ]
    WITHDRAWAL_MARKERS = [
        "withdrawals and other subtractions",
        "other subtractions",
        "withdrawals",
        "checks paid",
    ]
    SECTION_END_MARKERS = [
        "total deposits",
        "total withdrawals",
        "total other",
        "ending balance",
        "total checks",
    ]
    
    # Patterns
    DATE_PATTERN = re.compile(r"^(\d{1,2}/\d{1,2}(?:/\d{2,4})?)$")
    AMOUNT_PATTERN = re.compile(r"^-?\$?[\d,]+\.\d{2}$|^\([\d,]+\.\d{2}\)$")
    SKIP_KEYWORDS = [
        "ending balance", "beginning balance", "subtotal",
        "continued", "page", "statement period",
    ]

    def parse(self, pdf_bytes: bytes) -> ParseResult:
        """Parse a Bank of America PDF statement."""
        transactions: List[ParsedTransaction] = []
        warnings: List[str] = []

        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    page_txns, page_warnings = self._parse_page(page, page_num)
                    transactions.extend(page_txns)
                    warnings.extend(page_warnings)
        except Exception as e:
            warnings.append(f"Failed to parse PDF: {str(e)}")

        return ParseResult(transactions=transactions, warnings=warnings)

    def _parse_page(
        self, page, page_num: int
    ) -> Tuple[List[ParsedTransaction], List[str]]:
        """Parse a single page of the statement."""
        transactions: List[ParsedTransaction] = []
        warnings: List[str] = []

        # Extract words with positions
        words = page.extract_words(keep_blank_chars=True)
        if not words:
            return transactions, warnings

        # Group words into lines by Y position (with tolerance)
        lines = self._group_into_lines(words)

        # Track current section
        current_section: Optional[str] = None
        current_row: List[str] = []
        current_date: Optional[date] = None

        for line_words in lines:
            line_text = " ".join(line_words).strip()
            line_lower = line_text.lower()

            # Detect section changes
            if any(marker in line_lower for marker in self.DEPOSIT_MARKERS):
                # Process previous row before section change
                if current_row and current_date and current_section:
                    txn = self._parse_row(
                        current_date, current_row, current_section,
                        page_num, warnings
                    )
                    if txn:
                        transactions.append(txn)
                    current_row = []
                    current_date = None
                current_section = "deposits"
                continue
            elif any(marker in line_lower for marker in self.WITHDRAWAL_MARKERS):
                # Process previous row before section change
                if current_row and current_date and current_section:
                    txn = self._parse_row(
                        current_date, current_row, current_section,
                        page_num, warnings
                    )
                    if txn:
                        transactions.append(txn)
                    current_row = []
                    current_date = None
                current_section = "withdrawals"
                continue
            elif any(marker in line_lower for marker in self.SECTION_END_MARKERS):
                # Process previous row before section ends
                if current_row and current_date and current_section:
                    txn = self._parse_row(
                        current_date, current_row, current_section,
                        page_num, warnings
                    )
                    if txn:
                        transactions.append(txn)
                    current_row = []
                    current_date = None
                current_section = None
                continue

            # Skip if not in a relevant section
            if current_section is None:
                continue

            # Skip header/footer lines
            if any(kw in line_lower for kw in self.SKIP_KEYWORDS):
                continue

            # Check if line starts with a date (new transaction)
            first_word = line_words[0] if line_words else ""
            date_match = self.DATE_PATTERN.match(first_word)

            if date_match:
                # Process previous row if exists
                if current_row and current_date:
                    txn = self._parse_row(
                        current_date, current_row, current_section, page_num, warnings
                    )
                    if txn:
                        transactions.append(txn)

                # Start new row
                current_date = self._parse_date(date_match.group(1), warnings)
                current_row = line_words[1:]  # Exclude date
            else:
                # Continuation of previous row (wrapped description)
                current_row.extend(line_words)

        # Process last row
        if current_row and current_date:
            txn = self._parse_row(
                current_date, current_row, current_section, page_num, warnings
            )
            if txn:
                transactions.append(txn)

        return transactions, warnings

    def _group_into_lines(self, words: List[dict], tolerance: float = 3) -> List[List[str]]:
        """Group words into lines based on Y position."""
        if not words:
            return []

        # Sort by top position, then by left position
        sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))

        lines: List[List[dict]] = []
        current_line: List[dict] = [sorted_words[0]]
        current_top = sorted_words[0]["top"]

        for word in sorted_words[1:]:
            if abs(word["top"] - current_top) <= tolerance:
                current_line.append(word)
            else:
                # Sort current line by x position and save
                current_line.sort(key=lambda w: w["x0"])
                lines.append(current_line)
                current_line = [word]
                current_top = word["top"]

        # Don't forget last line
        if current_line:
            current_line.sort(key=lambda w: w["x0"])
            lines.append(current_line)

        # Convert to list of text strings
        return [[w["text"] for w in line] for line in lines]

    def _parse_date(self, date_str: str, warnings: List[str]) -> Optional[date]:
        """Parse a date string into a date object."""
        try:
            # Try MM/DD/YYYY or MM/DD/YY
            if len(date_str) > 5:
                if len(date_str.split("/")[-1]) == 4:
                    return datetime.strptime(date_str, "%m/%d/%Y").date()
                else:
                    return datetime.strptime(date_str, "%m/%d/%y").date()
            else:
                # MM/DD format - assume current year
                parsed = datetime.strptime(date_str, "%m/%d")
                return parsed.replace(year=datetime.now().year).date()
        except ValueError:
            warnings.append(f"Could not parse date: {date_str}")
            return None

    def _parse_row(
        self,
        posted_date: date,
        row_words: List[str],
        section: str,
        page_num: int,
        warnings: List[str],
    ) -> Optional[ParsedTransaction]:
        """Parse a transaction row into a ParsedTransaction."""
        if not row_words:
            return None

        # Find amount (rightmost numeric value)
        amount: Optional[Decimal] = None
        amount_idx: Optional[int] = None

        for i in range(len(row_words) - 1, -1, -1):
            word = row_words[i].strip()
            if self.AMOUNT_PATTERN.match(word):
                amount = self._parse_amount(word)
                amount_idx = i
                break

        if amount is None:
            warnings.append(
                f"Page {page_num}: Could not find amount in row: {' '.join(row_words[:5])}..."
            )
            return None

        # Description is everything before the amount
        description_words = row_words[:amount_idx] if amount_idx else row_words[:-1]
        description = " ".join(description_words).strip()

        if not description:
            warnings.append(f"Page {page_num}: Empty description for amount {amount}")
            return None

        # Apply sign based on section
        if section == "deposits":
            amount = abs(amount)
        elif section == "withdrawals":
            # Make negative unless already negative
            if amount > 0:
                amount = -amount

        return ParsedTransaction(
            posted_date=posted_date,
            description=description,
            amount=amount,
        )

    def _parse_amount(self, amount_str: str) -> Optional[Decimal]:
        """Parse an amount string into a Decimal."""
        try:
            # Remove $ and commas
            cleaned = amount_str.replace("$", "").replace(",", "")
            
            # Handle parentheses (negative)
            if cleaned.startswith("(") and cleaned.endswith(")"):
                cleaned = "-" + cleaned[1:-1]

            return Decimal(cleaned)
        except InvalidOperation:
            return None

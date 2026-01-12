from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List


@dataclass
class ParsedTransaction:
    """A single parsed transaction from a bank statement."""
    posted_date: date
    description: str
    amount: Decimal


@dataclass
class ParseResult:
    """Result of parsing a bank statement."""
    transactions: List[ParsedTransaction] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class BankParser(ABC):
    """Abstract base class for bank statement parsers."""
    
    bank_code: str

    @abstractmethod
    def parse(self, pdf_bytes: bytes) -> ParseResult:
        """
        Parse a PDF bank statement and extract transactions.

        Args:
            pdf_bytes: Raw PDF file content

        Returns:
            ParseResult containing transactions and any warnings
        """
        pass

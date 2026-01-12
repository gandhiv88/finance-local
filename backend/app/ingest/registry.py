from typing import Dict, Type

from .parsers.base import BankParser
from .parsers.bofa import BofAParser


# Registry of bank code -> parser class
_PARSER_REGISTRY: Dict[str, Type[BankParser]] = {
    "bofa": BofAParser,
}


def get_parser(bank_code: str) -> BankParser:
    """
    Get a parser instance for the given bank code.

    Args:
        bank_code: Bank identifier (e.g., "bofa")

    Returns:
        BankParser instance for the bank

    Raises:
        ValueError: If bank code is not supported
    """
    parser_class = _PARSER_REGISTRY.get(bank_code)
    
    if parser_class is None:
        supported = ", ".join(sorted(_PARSER_REGISTRY.keys()))
        raise ValueError(
            f"Unsupported bank code: '{bank_code}'. "
            f"Supported: {supported}"
        )
    
    return parser_class()

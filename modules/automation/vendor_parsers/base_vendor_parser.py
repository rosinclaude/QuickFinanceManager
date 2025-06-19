# modules/automation/vendor_parsers/base_vendor_parser.py

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class BaseVendorParser(ABC):
    """
    Abstract base class for vendor-specific invoice parsers.
    All custom vendor parsers should inherit from this class.
    """
    def __init__(self, currency_symbol: str, currency_code: str):
        self.currency_symbol = currency_symbol
        self.currency_code = currency_code

    @abstractmethod
    def parse(self, text: str) -> Dict[str, Any]:
        """
        Parses raw text from a specific vendor's invoice.

        Args:
            text (str): The raw OCR text of the invoice.

        Returns:
            Dict[str, Any]: A dictionary containing extracted transaction details,
                            following the same structure as InvoiceParser.parse_invoice_text.
                            Crucially, 'payee' should be set here definitively.
        """
        pass

    def _extract_amount(self, s: str) -> Optional[float]:
        """Helper to extract a numerical amount from a string."""
        # This can be common utility or overridden by vendor if needed
        amount_match = re.search(r'[-+]?[\$€£]?\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2}))', s)
        if amount_match:
            amount_str = amount_match.group(1).replace('.', '').replace(',', '.')
            try:
                return float(amount_str)
            except ValueError:
                pass
        return None
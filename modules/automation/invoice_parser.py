# modules/automation/invoice_parser.py

import re
import datetime
import importlib
from typing import Dict, List, Any, Optional, Tuple

from modules.managers.finance_config_manager import FinanceConfigManager
from modules.managers.vendor_config_manager import VendorConfigManager
from modules.automation.vendor_parsers.base_vendor_parser import BaseVendorParser


class InvoiceParser:
    def __init__(self, config_manager: FinanceConfigManager,
                 vendor_config_manager: VendorConfigManager):
        """
        Initializes the InvoiceParser.

        Args:
            config_manager (FinanceConfigManager): An instance of FinanceConfigManager.
            vendor_config_manager (VendorConfigManager): An instance of VendorConfigManager.
        """
        self.config_manager = config_manager
        self.vendor_config_manager = vendor_config_manager
        self.currency_symbol = self.config_manager.get_currency_symbol()
        self.currency_code = self.config_manager.get_currency()
        # self.vendor_patterns was removed as VendorConfigManager now manages vendor patterns.

    def parse_invoice_text(self, text: str) -> Dict[str, Any]:
        """
        Parses raw text extracted from an invoice image, attempting to identify the vendor
        and dispatch to a vendor-specific parser if available, otherwise uses generic logic.

        Args:
            text (str): The raw text string from OCR.

        Returns:
            Dict[str, Any]: A dictionary containing extracted transaction details.
                            Keys will include: 'date', 'total_amount', 'payee', 'account',
                            'splits' (list of dicts), 'taxes' (list of dicts), 'metadata' (dict).
        """
        # 1. Attempt to identify the vendor and get its conform name and parser module
        raw_detected_vendor_name, potential_conform_vendor_name = self._identify_raw_vendor(text)

        # Get conform name (either a known one or the raw one if not found)
        conform_vendor_name = self.vendor_config_manager.get_conform_vendor_name(potential_conform_vendor_name)

        # Get custom parser module name based on the conform name
        custom_parser_module_name = self.vendor_config_manager.get_custom_parser_module(conform_vendor_name)

        # 2. If a custom parser is specified and exists, use it
        if custom_parser_module_name:
            try:
                module = importlib.import_module(f"modules.automation.vendor_parsers.{custom_parser_module_name}")
                class_name = ''.join(word.capitalize() for word in custom_parser_module_name.split('_'))

                vendor_parser_class = getattr(module, class_name)
                if issubclass(vendor_parser_class, BaseVendorParser):
                    vendor_parser: BaseVendorParser = vendor_parser_class(self.currency_symbol, self.currency_code)
                    print(f"Detected vendor '{conform_vendor_name}'. Using custom parser: {custom_parser_module_name}")
                    parsed_data = vendor_parser.parse(text)
                    parsed_data['payee'] = conform_vendor_name  # Ensure conform name is used
                    return parsed_data
                else:
                    print(
                        f"Error: Custom parser '{custom_parser_module_name}' does not inherit from BaseVendorParser. Falling back to generic.")
            except (ImportError, AttributeError) as e:
                print(
                    f"Warning: Could not load or find custom parser '{custom_parser_module_name}': {e}. Falling back to generic parsing.")
            except Exception as e:
                print(
                    f"Error executing custom parser '{custom_parser_module_name}': {e}. Falling back to generic parsing.")

        # 3. Fallback to generic parsing if no specific parser was found or if it failed
        print(f"No specific parser for '{conform_vendor_name}' or parsing failed. Using generic parser.")
        parsed_data = self._generic_parse_invoice_text(text, conform_vendor_name)

        # If the vendor was not found in our config, add it (and its raw name as a pattern)
        # This condition ensures we only add if it was truly a *new* raw name that didn't conform
        if raw_detected_vendor_name != conform_vendor_name and conform_vendor_name == potential_conform_vendor_name:
            print(f"Adding new vendor '{conform_vendor_name}' with pattern '{raw_detected_vendor_name}' to config.")
            self.vendor_config_manager.add_new_vendor(conform_vendor_name, [raw_detected_vendor_name])

        return parsed_data

    def _identify_raw_vendor(self, text: str) -> Tuple[str, str]:
        """
        Identifies a raw vendor name from the invoice text.
        This method is for initial identification before conforming.

        Returns:
            Tuple[str, str]: (raw_detected_vendor_name, potential_conform_vendor_name)
            The second element is a preliminary conform name based on matching patterns,
            which will then be resolved by VendorConfigManager.get_conform_vendor_name.
        """
        text_upper = text.upper()

        # First, try to match against known patterns from VendorConfigManager
        for vendor_info in self.vendor_config_manager.get_all_vendor_info():
            vendor_name_from_config = vendor_info['name']  # This is the conform name
            patterns = [p.upper() for p in vendor_info.get('patterns', [])]
            for pattern in patterns:
                if pattern in text_upper:
                    # Return the raw text segment that matched, and the conform name from config
                    match = re.search(re.escape(pattern), text, re.IGNORECASE)
                    if match:
                        return match.group(0).strip(), vendor_name_from_config
                    return pattern, vendor_name_from_config  # Fallback if regex match fails

        # Fallback if no configured vendor is matched, infer a generic payee
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        common_company_suffixes = ["INC", "LTD", "LLC", "CORP", "CO", "GMBH", "SA", "SAS", "AG"]

        for i, line in enumerate(lines[:10]):  # Check first 10 lines
            line_upper = line.upper()
            # If a line contains a company suffix and is not too short
            if any(suffix in line_upper for suffix in common_company_suffixes) and len(line) > 5:
                raw_name = line.strip()
                return raw_name, raw_name  # Use the line as both raw and potential conform name

            # Another heuristic: first non-numeric, non-date line that looks like a name
            if i < 5 and not re.search(r'^\d+$', line) and not re.search(r'[-]?[\d,.]+$', line) \
                    and len(line) > 5 and not re.search(r'\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}', line):
                raw_name = line.strip()
                return raw_name, raw_name

        # If still no match, return a generic placeholder
        return "Unknown Vendor", "Unknown Vendor"

    def _generic_parse_invoice_text(self, text: str, conform_payee: str) -> Dict[str, Any]:
        """
        Performs generic parsing for invoices where no specific vendor parser is used.
        """
        parsed_data = {
            'date': None,
            'total_amount': None,
            'payee': conform_payee,  # Use the conform payee here
            'account': None,
            'description': '',
            'notes': 'Extracted from invoice via OCR (generic parser).',
            'splits': [],
            'taxes': [],
            'currency': self.currency_code,
            'metadata': {}
        }

        lines = [line.strip() for line in text.split('\n') if line.strip()]

        # --- Helper for amount extraction ---
        def extract_amount(s: str) -> Optional[float]:
            amount_match = re.search(r'[-+]?[\$€£]?\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2}))', s)
            if amount_match:
                amount_str = amount_match.group(1).replace('.', '').replace(',', '.')
                try:
                    return float(amount_str)
                except ValueError:
                    pass
            return None

        # --- 1. Extract Date ---
        date_patterns = [
            r'(\d{4}[-/]\d{2}[-/]\d{2})',  # YYYY-MM-DD
            r'(\d{2}[-/]\d{2}[-/]\d{4})',  # DD-MM-YYYY or MM-DD-YYYY
            r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})',  # DD Mon YYYY
            r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4})',  # Mon DD, YYYY
            r'(\d{1,2}\/\d{1,2}\/\d{2,4})',  # D/M/YY or DD/MM/YYYY
            r'(\d{1,2}\.\d{1,2}\.\d{2,4})'  # D.M.YY or DD.MM.YYYY
        ]

        for line in lines:
            for pattern in date_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    date_str = match.group(1)
                    for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%m-%d-%Y',
                                '%Y/%m/%d', '%d/%m/%Y', '%m/%d/%Y',
                                '%d %b %Y', '%b %d, %Y',
                                '%Y.%m.%d', '%d.%m.%Y', '%m.%d.%Y']:
                        try:
                            parsed_date = datetime.datetime.strptime(date_str, fmt).date()
                            if parsed_date <= datetime.date.today() + datetime.timedelta(
                                    days=30):  # Date should not be too far in future
                                parsed_data['date'] = parsed_date
                                break
                        except ValueError:
                            continue
                    if parsed_data['date']:
                        break
            if parsed_data['date']:
                break

        if parsed_data['date'] is None:
            print("Warning (Generic Parser): Could not extract date from invoice text.")

        # --- 2. Extract Account (If specified on invoice, e.g., credit card type) ---
        known_accounts = self.config_manager.get_all_account_names()
        for account_name in known_accounts:
            if account_name.lower() in text.lower():
                parsed_data['account'] = account_name
                break

        # --- 3. Extract Total Amount and Taxes ---
        subtotal_keywords = ['SUBTOTAL', 'SOUS-TOTAL']
        total_keywords = ['TOTAL', 'GRAND TOTAL', 'AMOUNT DUE', 'BALANCE', 'MONTANT TOTAL', 'NET À PAYER',
                          'NET A PAYER']
        tax_keywords = ['TAX', 'TAXE', 'TVQ', 'TPS', 'VAT', 'GST']
        payment_keywords = ['PAID', 'PAYMENT', 'COMPTANT', 'MONNAIE', 'C-CREDIT', 'DEBIT', 'CARTE', 'CASH']
        change_keywords = ['CHANGE', 'MONNAIE À RENDRE']

        potential_amounts: List[Tuple[str, float, str]] = []  # (line_text, amount, type_tag)

        for i, line in enumerate(lines):
            amount = extract_amount(line)
            if amount is not None:
                line_upper = line.upper()
                if any(kw in line_upper for kw in total_keywords):
                    potential_amounts.append((line, amount, 'total'))
                elif any(kw in line_upper for kw in subtotal_keywords):
                    potential_amounts.append((line, amount, 'subtotal'))
                elif any(kw in line_upper for kw in tax_keywords):
                    potential_amounts.append((line, amount, 'tax'))
                    tax_name_match = re.search(r'(TPS|TVQ|VAT|GST|TAXE|TAX)\s*(\d{1,2}\.\d{1,3})?%', line_upper)
                    tax_name = tax_name_match.group(1) if tax_name_match else "Tax"
                    parsed_data['taxes'].append({'name': tax_name, 'amount': amount})
                elif any(kw in line_upper for kw in payment_keywords):
                    potential_amounts.append((line, amount, 'payment'))
                elif any(kw in line_upper for kw in change_keywords):
                    parsed_data['metadata']['change_due'] = amount
                    potential_amounts.append((line, amount, 'change'))
                else:
                    potential_amounts.append((line, amount, 'generic'))

        final_total_candidate = None
        for line_text, amount, tag in reversed(potential_amounts):
            if tag == 'total':
                final_total_candidate = amount
                break

        if final_total_candidate is None:
            for line_text, amount, tag in reversed(potential_amounts):
                # Consider generic or payment amounts as total candidates if it's the last significant number
                if tag in ['generic', 'payment'] and amount > 0:
                    if amount == potential_amounts[-1][1]:  # Check if it's the absolute last amount found
                        final_total_candidate = amount
                        break
            if final_total_candidate is None and potential_amounts:
                # If no clear total, take the largest non-tax/non-change amount
                largest_amount_found = 0.0
                for line_text, amount, tag in potential_amounts:
                    if tag not in ['tax', 'change'] and amount > largest_amount_found:
                        largest_amount_found = amount
                if largest_amount_found > 0:
                    final_total_candidate = largest_amount_found

        parsed_data['total_amount'] = final_total_candidate
        if parsed_data['total_amount'] is None:
            print("Warning (Generic Parser): Final total amount could not be confidently extracted.")

        # --- 4. Splits Logic (Generic) ---
        parsed_data['splits'] = self._extract_line_items_from_text(lines,
                                                                   parsed_data['payee'])  # Use parsed_data['payee']

        if not parsed_data['splits'] and parsed_data['total_amount'] is not None:
            # If no detailed splits but total amount is found, create a single split for the total
            parsed_data['splits'].append({
                'description': f"{parsed_data['payee']} - Invoice Total",
                'amount': parsed_data['total_amount'],
                'budget_scope': None,  # Will be filled by categorizer later
                'category': None,
                'sub_category': None,
                'full_budget_path': None
            })
            parsed_data['notes'] += "\nNo detailed splits found; generated single split from total."

        if not parsed_data['splits'] and parsed_data['total_amount'] is None:
            # If neither splits nor total amount can be extracted, indicate manual input is needed
            parsed_data['splits'] = []  # Ensure splits list is empty
            parsed_data['description'] = "Invoice processed, but amount/splits could not be extracted (generic)."
            parsed_data['notes'] += "\nRequires manual amount and split input."

        if not parsed_data['description']:
            parsed_data['description'] = f"{parsed_data['payee']} - Automatic Parse (Generic)"

        # --- 5. Extract Other Metadata (Generic) ---
        for line in lines:
            line_upper = line.upper()
            loyalty_match = re.search(r'(MEMBER|LOYALTY|CARD|CARTE)\s*#?\s*(\d{8,})', line_upper)
            if loyalty_match:
                parsed_data['metadata']['loyalty_number'] = loyalty_match.group(2)
            address_match = re.search(r'\d{1,5}\s+[\w\s]+\s+(?:Rd|St|Ave|Blvd|Rue|Chemin)', line, re.IGNORECASE)
            phone_match = re.search(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', line)
            if address_match or phone_match:
                if 'address' not in parsed_data['metadata']:
                    parsed_data['metadata']['address'] = line.strip()

        return parsed_data

    def _extract_line_items_from_text(self, lines: List[str], default_payee: str) -> List[Dict[str, Any]]:
        """
        Helper for generic parsing to extract individual line items.
        """
        extracted_items = []
        item_line_pattern = re.compile(
            r'(.+?)'  # Description (capture group 1)
            r'(?:\s+x\s*\d+)?'  # Optional quantity (e.g., "x 2")
            r'(?:\s+@\s*[\$€£]?\s*[\d,]+\.\d{2})?'  # Optional unit price (e.g., "@ $5.00")
            r'\s+[\$€£]?\s*([\d,]+\.\d{2})'  # Amount (capture group 2)
            r'\s*(?:[A-Z]+)?$'  # Optional trailing code (e.g., "TX" for tax code)
        )

        summary_keywords = ['SUBTOTAL', 'SOUS-TOTAL', 'TOTAL', 'TAX', 'TAXE', 'TVQ', 'TPS',
                            'COMPTANT', 'MONNAIE', 'CHANGE', 'PAYMENT', 'PAID', 'C-CREDIT', 'DEBIT',
                            'AMOUNT DUE', 'BALANCE', 'TOTAL PAID', 'MONTANT PAYE']  # Added more summary keywords

        # Consider a window of lines around the potential line item to avoid parsing headers/footers as items
        # A simple approach: filter out lines that are too short or too long, or contain only numbers/dates

        for line in lines:
            line_upper = line.upper()
            # Skip lines that are likely headers, footers, or just numbers/dates
            if any(kw in line_upper for kw in summary_keywords) or \
                    re.match(r'^\s*[\d\s\/\.-]+\s*$', line.strip()) or \
                    len(line.strip()) < 5:  # Skip very short lines that are unlikely items
                continue

            match = item_line_pattern.search(line)
            if match:
                description = match.group(1).strip()
                amount_str = match.group(2).replace(',', '')  # Remove thousands separator
                try:
                    amount = float(amount_str)
                    if amount > 0:  # Only add positive amounts as line items
                        extracted_items.append({
                            'description': f"{default_payee} - {description}",  # Prepend payee for clarity
                            'amount': round(amount, 2),
                            'budget_scope': None,  # These will be filled by categorizer later
                            'category': None,
                            'sub_category': None,
                            'full_budget_path': None
                        })
                except ValueError:
                    pass  # Skip if amount cannot be parsed
        return extracted_items

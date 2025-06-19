# modules/automation/vendor_parsers/costco_parser.py

import re
import datetime
from typing import Dict, Any, List, Optional, Tuple

from .base_vendor_parser import BaseVendorParser


class CostcoParser(BaseVendorParser):
    def __init__(self, currency_symbol: str, currency_code: str):
        super().__init__(currency_symbol, currency_code)
        self.vendor_name = "COSTCO"  # Define the specific vendor name

    def parse(self, text: str) -> Dict[str, Any]:
        """
        Parses Costco-specific invoice text, handling cumulative subtotals.
        """
        parsed_data = {
            'date': None,
            'total_amount': None,
            'payee': self.vendor_name,  # Set payee definitively
            'account': None,
            'description': '',
            'notes': 'Extracted from Costco invoice via OCR.',
            'splits': [],
            'taxes': [],
            'currency': self.currency_code,
            'metadata': {}
        }

        lines = [line.strip() for line in text.split('\n') if line.strip()]

        # Reuse common parsing utilities if needed, or override if Costco has unique date formats etc.
        # For simplicity, we'll re-implement some extraction here, but you could centralize.

        # --- Date Extraction (similar to generic) ---
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
                            if parsed_date <= datetime.date.today() + datetime.timedelta(days=30):
                                parsed_data['date'] = parsed_date
                                break
                        except ValueError:
                            continue
                    if parsed_data['date']:
                        break
            if parsed_data['date']:
                break

        # --- Total Amount and Subtotals (Crucial for Costco) ---
        subtotal_keywords = ['SUBTOTAL', 'SOUS-TOTAL', 'SOUS TOTAL']
        total_keywords = ['TOTAL', 'GRAND TOTAL', 'AMOUNT DUE', 'BALANCE', 'MONTANT TOTAL', 'NET À PAYER',
                          'NET A PAYER']
        tax_keywords = ['TAX', 'TAXE', 'TVQ', 'TPS', 'VAT', 'GST']
        payment_keywords = ['PAID', 'PAYMENT', 'COMPTANT', 'MONNAIE', 'C-CREDIT', 'DEBIT', 'CARTE', 'CASH']
        change_keywords = ['CHANGE', 'MONNAIE À RENDRE']

        potential_amounts: List[Tuple[int, str, float, str]] = []  # (line_idx, line_text, amount, type_tag)

        for i, line in enumerate(lines):
            amount = self._extract_amount(line)
            if amount is not None:
                line_upper = line.upper()
                tag = 'generic'  # Default tag
                if any(kw in line_upper for kw in total_keywords):
                    tag = 'total'
                elif any(kw in line_upper for kw in subtotal_keywords):
                    tag = 'subtotal'
                elif any(kw in line_upper for kw in tax_keywords):
                    tag = 'tax'
                    tax_name_match = re.search(r'(TPS|TVQ|VAT|GST|TAXE|TAX)\s*(\d{1,2}\.\d{1,3})?%', line_upper)
                    tax_name = tax_name_match.group(1) if tax_name_match else "Tax"
                    parsed_data['taxes'].append({'name': tax_name, 'amount': amount})
                elif any(kw in line_upper for kw in payment_keywords):
                    tag = 'payment'
                elif any(kw in line_upper for kw in change_keywords):
                    parsed_data['metadata']['change_due'] = amount
                    tag = 'change'

                potential_amounts.append((i, line, amount, tag))

        # Identify final total amount
        final_total_candidate = None
        for _, _, amount, tag in reversed(potential_amounts):
            if tag == 'total':
                final_total_candidate = amount
                break
        if final_total_candidate is None and potential_amounts:
            # Fallback: largest non-tax/change amount near the end
            for _, _, amount, tag in reversed(potential_amounts):
                if tag not in ['tax', 'change'] and amount > 0:
                    final_total_candidate = amount
                    break
        parsed_data['total_amount'] = final_total_candidate

        # --- Cumulative Splits Logic (The core Costco logic) ---
        subtotal_lines: List[Tuple[int, float]] = []  # (line_index, amount)
        for idx, line_text, amount, tag in potential_amounts:
            if tag == 'subtotal':
                subtotal_lines.append((idx, amount))

        subtotal_lines.sort(key=lambda x: x[0])  # Ensure they are in order of appearance

        if len(subtotal_lines) > 0 and parsed_data['total_amount'] is not None:
            cumulative_splits_detected = True
            if len(subtotal_lines) > 1:
                # Check if subtotals are generally increasing and the last one is near total
                if not (subtotal_lines[-1][1] >= parsed_data['total_amount'] - 0.05 and \
                        all(subtotal_lines[i][1] <= subtotal_lines[i + 1][1] for i in range(len(subtotal_lines) - 1))):
                    cumulative_splits_detected = False

            if cumulative_splits_detected:
                print("Costco: Cumulative subtotals detected, creating splits based on differences.")
                previous_subtotal_amount = 0.0
                for i, (idx, current_subtotal_amount) in enumerate(subtotal_lines):
                    split_amount = round(current_subtotal_amount - previous_subtotal_amount, 2)

                    if split_amount > 0.0:
                        # Attempt to get a description for this split
                        # Look for lines between previous subtotal (or start) and current subtotal
                        search_start_idx = (subtotal_lines[i - 1][0] + 1) if i > 0 else 0
                        search_end_idx = idx

                        split_item_descriptions = []
                        # Regex to capture description of an item line (e.g., "APPLE" 2.99)
                        item_line_pattern = re.compile(
                            r'(.+?)\s+[\$€£]?\s*([\d,]+\.\d{2})\s*(?:[A-Z]+)?$'
                        )
                        # Keywords to avoid as item descriptions (summaries, etc.)
                        noise_keywords = ['SUBTOTAL', 'SOUS-TOTAL', 'TOTAL', 'TAX', 'TAXE', 'TVQ', 'TPS',
                                          'COMPTANT', 'MONNAIE', 'CHANGE', 'PAYMENT', 'PAID', 'C-CREDIT', 'DEBIT']

                        for j in range(search_start_idx, search_end_idx):
                            line = lines[j]
                            item_match = item_line_pattern.search(line)
                            if item_match:
                                desc = item_match.group(1).strip()
                                # Filter out noise
                                if not any(kw in desc.upper() for kw in noise_keywords) and len(desc) > 2:
                                    split_item_descriptions.append(desc)

                        split_description_summary = f"Section {i + 1}"
                        if split_item_descriptions:
                            # Use the last few significant items, or first few if more relevant for section title
                            split_description_summary = "; ".join(split_item_descriptions[-3:])
                            if len(split_item_descriptions) > 3:
                                split_description_summary += "..."  # Indicate more items

                        parsed_data['splits'].append({
                            'description': f"{self.vendor_name} - {split_description_summary}",
                            'amount': split_amount,
                            'category_suggestion': None,
                            'budget_scope_suggestion': None,
                            'original_subtotal_line': lines[idx]  # For debugging/audit
                        })
                    previous_subtotal_amount = current_subtotal_amount

                parsed_data['description'] = f"{self.vendor_name} - Multi-section Purchase"
                parsed_data['notes'] += "\nSplits derived from cumulative subtotals."
            else:
                print("Costco: Single subtotal or non-cumulative, falling back to generic item extraction if possible.")
                # Fallback to generic item extraction if not cumulative
                parsed_data['splits'] = self._extract_basic_line_items(lines, self.vendor_name)
                if not parsed_data['splits'] and parsed_data['total_amount'] is not None:
                    parsed_data['splits'].append({
                        'description': parsed_data['payee'] + " - Invoice Total",
                        'amount': parsed_data['total_amount'],
                        'category_suggestion': None,
                        'budget_scope_suggestion': None
                    })
                    parsed_data['notes'] += "\nNo detailed splits found; generated single split from total."

        elif parsed_data['total_amount'] is not None:  # No subtotals or only one
            # Try extracting general line items if total is found
            parsed_data['splits'] = self._extract_basic_line_items(lines, self.vendor_name)
            if not parsed_data['splits']:
                parsed_data['splits'].append({
                    'description': parsed_data['payee'] + " - Invoice Total",
                    'amount': parsed_data['total_amount'],
                    'category_suggestion': None,
                    'budget_scope_suggestion': None
                })
                parsed_data['notes'] += "\nNo detailed splits found; generated single split from total."

        # Handle cases where no splits were identified, but a total amount was.
        if not parsed_data['splits'] and parsed_data['total_amount'] is not None:
            parsed_data['splits'].append({
                'description': parsed_data['payee'] + " - Invoice Total",
                'amount': parsed_data['total_amount'],
                'category_suggestion': None,
                'budget_scope_suggestion': None
            })
            parsed_data['notes'] += "\nFallback: Single split created from total amount."

        # Final description fallback
        if not parsed_data['description']:
            parsed_data['description'] = f"{self.vendor_name} - Purchase"

        # --- Metadata Extraction (Loyalty, etc.) ---
        for line in lines:
            line_upper = line.upper()
            loyalty_match = re.search(r'(MEMBER|LOYALTY|CARD|CARTE)\s*#?\s*(\d{8,})', line_upper)
            if loyalty_match:
                parsed_data['metadata']['loyalty_number'] = loyalty_match.group(2)

            # Example: Capturing store address/phone
            address_match = re.search(r'\d{1,5}\s+[\w\s]+\s+(?:Rd|St|Ave|Blvd|Rue|Chemin)', line, re.IGNORECASE)
            phone_match = re.search(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', line)
            if address_match or phone_match:
                if 'address' not in parsed_data['metadata']:
                    parsed_data['metadata']['address'] = line.strip()

        return parsed_data

    def _extract_basic_line_items(self, lines: List[str], default_payee: str) -> List[Dict[str, Any]]:
        """
        Helper to extract individual line items for non-cumulative or simple receipts.
        Similar to the generic parser's method.
        """
        extracted_items = []
        item_line_pattern = re.compile(
            r'(.+?)'
            r'(?:\s+x\s*\d+)?'
            r'(?:\s+@\s*[\$€£]?\s*[\d,]+\.\d{2})?'
            r'\s+[\$€£]?\s*([\d,]+\.\d{2})'
            r'\s*(?:[A-Z]+)?$'
        )

        summary_keywords = ['SUBTOTAL', 'SOUS-TOTAL', 'TOTAL', 'TAX', 'TAXE', 'TVQ', 'TPS',
                            'COMPTANT', 'MONNAIE', 'CHANGE', 'PAYMENT', 'PAID', 'C-CREDIT', 'DEBIT',
                            'AMOUNT DUE', 'BALANCE']

        for line in lines:
            line_upper = line.upper()
            if any(kw in line_upper for kw in summary_keywords):
                continue

            match = item_line_pattern.search(line)
            if match:
                description = match.group(1).strip()
                amount_str = match.group(2).replace(',', '')
                try:
                    amount = float(amount_str)
                    if amount > 0:
                        extracted_items.append({
                            'description': f"{default_payee} - {description}",
                            'amount': round(amount, 2),
                            'category_suggestion': None,
                            'budget_scope_suggestion': None
                        })
                except ValueError:
                    pass
        return extracted_items
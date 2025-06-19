# statement_matcher.py
import uuid

import pandas as pd
import datetime

#TODO: Match transactions from the statements to the one existing in the database. Extract additional infos.
# Also, match identical transaction but from two different statements: I Pay my credit card, one bank state payment emitted
# The other mention payment received. Or even in a broader sense, add a module transaction matching for a more general one than just statement, if
# necessary.


# Placeholder for future imports like OCRProcessor, LLMCategorizer, utils
# from ocr_processor import OCRProcessor
# from llm_categorizer import LLMCategorizer
# from utils import extract_amount_date_payer_payee, match_payee_data

class StatementMatcher:
    """
    Manages the processing of bank statements to identify new transactions
    and match existing ones.
    """

    def __init__(self, config: dict, payees_df: pd.DataFrame):
        """
        Initializes the StatementMatcher.

        Args:
            config (dict): The current monthly configuration.
            payees_df (pd.DataFrame): DataFrame of known payees for lookup.
        """
        self.config = config
        self.payees_df = payees_df
        # Initialize sub-processors if they were real
        # self.ocr_processor = OCRProcessor(config.get('ocr_confidence_threshold', 0.75))
        # self.llm_categorizer = LLMCategorizer(...)

    def process_statement(self, statement_file_path: str, existing_transactions_df: pd.DataFrame) -> tuple[
        list[dict], list[dict]]:
        """
        Processes a bank statement (e.g., PDF, CSV) to extract transactions,
        match them against existing ones, and categorize new ones.

        Args:
            statement_file_path (str): Path to the uploaded bank statement file.
            existing_transactions_df (pd.DataFrame): DataFrame of transactions already in the system.

        Returns:
            tuple[list[dict], list[dict]]: A tuple containing two lists:
                - List of new transactions (dictionaries) to be added.
                - List of matched existing transactions (dictionaries) with updated info.
        """
        # --- Placeholder: Simulate extraction from statement ---
        # In a real scenario, this would parse a CSV statement or OCR a PDF statement
        # to get a list of raw transactions from the statement.
        st.info(f"Simulating processing for bank statement: {statement_file_path}")
        raw_statement_transactions = [
            {"Date": "2025-06-01", "Description": "AMAZON.COM", "Amount": -55.20},
            {"Date": "2025-06-02", "Description": "GROCERY MART", "Amount": -120.50},
            {"Date": "2025-06-03", "Description": "PAYCHECK DEPOSIT", "Amount": 1500.00},
            # This one should match an existing one
            {"Date": "2025-06-04", "Description": "EXAMPLE STORE", "Amount": -12.34},
            # Another one for splitting later
            {"Date": "2025-06-05", "Description": "COSTCO GASFOOD", "Amount": -200.00},
        ]

        new_transactions = []
        matched_transactions = []

        for raw_txn in raw_statement_transactions:
            # --- Attempt to match against existing transactions ---
            # This is where the core matching logic would go.
            # For simplicity, we'll just check if a similar transaction exists by Payer/Payee, Date, and Amount

            # Convert raw_txn['Date'] to datetime.date for comparison
            txn_date = datetime.datetime.strptime(raw_txn['Date'], "%Y-%m-%d").date()

            # Find potential matches in existing transactions
            potential_matches = existing_transactions_df[
                (existing_transactions_df['Date'].dt.date == txn_date) &
                (existing_transactions_df['Amount'].abs() == abs(raw_txn['Amount']))
                ]

            is_matched = False
            # Basic matching: if exact date and amount match, consider it a match
            # In a real app, this would be more sophisticated (fuzzy matching, payee aliases, etc.)
            if not potential_matches.empty:
                # Assuming the first match is sufficient for this prototype
                matched_transactions.append({
                    "original_statement_data": raw_txn,
                    "matched_transaction_id": potential_matches.iloc[0]['TransactionID'],
                    "status": "Matched"
                })
                is_matched = True

            if not is_matched:
                # If no match, treat as a new transaction and attempt to categorize/enrich
                # This would typically involve calling LLM/Payee matching

                # --- Placeholder for categorization/enrichment ---
                # Default values for new transactions
                llm_prediction = {
                    'category': 'Miscellaneous', 'sub_category': '', 'account': 'Chequing',
                    'transaction_type': 'Expense', 'related_debt_account': '',
                    'related_savings_account': '', 'is_subscription': False,
                    'subscription_auto_identified': False, 'confidence': 0.0  # Low confidence without LLM
                }

                # Attempt payee lookup for categorization (requires utils.py:match_payee_data)
                # This part is still placeholder for now.
                # if callable(match_payee_data):
                #     matched_payee_defaults = match_payee_data(raw_txn['Description'], self.payees_df)
                #     if matched_payee_defaults:
                #         llm_prediction.update({
                #             'category': matched_payee_defaults.get('DefaultCategory', llm_prediction['category']),
                #             'sub_category': matched_payee_defaults.get('DefaultSubCategory', llm_prediction['sub_category']),
                #             'account': matched_payee_defaults.get('DefaultAccount', llm_prediction['account']),
                #             'transaction_type': matched_payee_defaults.get('DefaultTransactionType', llm_prediction['transaction_type']),
                #             'related_debt_account': matched_payee_defaults.get('RelatedDebtAccount', llm_prediction['related_debt_account']),
                #             'related_savings_account': matched_payee_defaults.get('RelatedSavingsAccount', llm_prediction['related_savings_account']),
                #             'is_subscription': matched_payee_defaults.get('IsSubscription', llm_prediction['is_subscription']),
                #             'subscription_auto_identified': matched_payee_defaults.get('IsSubscription', llm_prediction['subscription_auto_identified']),
                #             'confidence': 1.0 # High confidence for rule-based match
                #         })
                #         payer_payee_final = matched_payee_defaults.get('Name', raw_txn['Description'])
                #     else:
                #         # If no payee match, then call LLM (once llm_categorizer.py is ready)
                #         # llm_prediction = self.llm_categorizer.categorize_transaction(raw_txn['Description'], ...)
                #         payer_payee_final = raw_txn['Description']
                # else:
                payer_payee_final = raw_txn['Description']  # Fallback if utils not ready

                # Prepare the new transaction dictionary
                new_transactions.append({
                    "TransactionID": str(uuid.uuid4()),  # Each statement transaction gets a new ID
                    "SplitIndex": 0,  # Default to 0 for initial entry, can be split later manually
                    "Date": txn_date,
                    "Time": "",  # Bank statements often don't have time
                    "Payer/Payee": payer_payee_final,
                    "Account": llm_prediction['account'],  # Placeholder for account
                    "Description": raw_txn['Description'],
                    "Amount": raw_txn['Amount'],
                    "Currency": self.config.get('currency', '$'),
                    "Category": llm_prediction['category'],
                    "SubCategory": llm_prediction['sub_category'],
                    "TransactionType": llm_prediction['transaction_type'],
                    "RelatedDebtAccount": llm_prediction['related_debt_account'],
                    "RelatedSavingsAccount": llm_prediction['related_savings_account'],
                    "IsSubscription": llm_prediction['is_subscription'],
                    "SubscriptionAutoIdentified": llm_prediction['subscription_auto_identified'],
                    "InputSource": "Bank Statement",
                    "FilePath": statement_file_path,  # Link to original statement file
                    "LLMConfidence": llm_prediction['confidence'],
                    "IsVerified": False,
                    "Notes": "Auto-extracted from bank statement.",
                    "TimestampAdded": datetime.datetime.now()
                })

        return new_transactions, matched_transactions
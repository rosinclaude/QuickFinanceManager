# modules/managers/transaction_manager.py
from typing import Optional, List, Dict, Any

import pandas as pd
import datetime
import uuid
import os

from .csv_manager import CSVManager
from .finance_config_manager import MonthlyFinanceConfigManager
from .payee_manager import PayeeManager
from .metadata_manager import MetadataManager
from modules.automation.ocr_processor import OCRProcessor
from modules.automation.invoice_parser import InvoiceParser
from modules.automation.hybrid_categorizer import HybridCategorizer
from modules.ml.ml_categorizer_trainer import MLCategorizerTrainer
from modules.managers.vendor_config_manager import VendorConfigManager


class TransactionManager:
    """
    Handles the business logic for adding and managing transactions.
    It uses the CSVManager for data storage operations,
    and integrates with other managers for configuration, payees, and automation.
    """

    def __init__(self, csv_manager: CSVManager, monthly_finance_config_manager: MonthlyFinanceConfigManager,
                 payee_manager: PayeeManager, metadata_manager: MetadataManager,
                 app_config: Dict[str, Any]):  # Accept app_config here
        """
        Initializes the TransactionManager.
        Args:
            csv_manager (CSVManager): An instance of CSVManager to handle data I/O.
            monthly_finance_config_manager (MonthlyFinanceConfigManager): An instance of FinanceConfigManager to access financial configuration.
            payee_manager (PayeeManager): An instance of PayeeManager to manage payee data.
            metadata_manager (MetadataManager): An instance of MetadataManager to store extra transaction details.
            app_config (Dict[str, Any]): The loaded application configuration dictionary.
        """
        self.csv_manager = csv_manager
        self.monthly_finance_config_manager = monthly_finance_config_manager  # Renamed for consistency with self.config_manager
        self.payee_manager = payee_manager
        self.metadata_manager = metadata_manager
        self.app_config = app_config  # Store app_config

        # Paths from app_config for I/O operations
        self.input_raw_dir = self.app_config['paths']['invoice_input_dir']
        self.input_processed_dir = self.app_config['paths']['invoice_processed_dir']
        self.input_failed_dir = self.app_config['paths']['invoice_failed_dir']

        # VendorConfigManager initialization, passing relevant app_config parts including new ambiguity threshold
        llm_config = self.app_config.get('llm_config', {})
        self.vendor_config_manager = VendorConfigManager(
            vendor_patterns_file=self.app_config['paths']['vendor_patterns_file'],
            llm_model_name=llm_config.get('vendor_fuzzy_match_model', 'all-MiniLM-L6-v2'),
            llm_similarity_threshold=llm_config.get('vendor_fuzzy_match_threshold', 0.85),
            llm_ambiguity_threshold=llm_config.get('vendor_fuzzy_match_ambiguity_threshold', 0.65), # NEW
            payee_manager=self.payee_manager, # NEW
        )

        # OCRProcessor initialization, passing relevant app_config parts
        ocr_config = self.app_config.get('ocr_config', {})
        self.ocr_processor = OCRProcessor(
            languages=ocr_config.get('languages', ['en', 'fr']),
            gpu=ocr_config.get('use_gpu', False)
        )

        # InvoiceParser initialization (already takes config_manager and vendor_config_manager)
        self.invoice_parser = InvoiceParser(monthly_finance_config_manager=self.monthly_finance_config_manager,
                                            vendor_config_manager=self.vendor_config_manager)

        # HybridCategorizer initialization, passing finance_config_manager and app_config
        self.hybrid_categorizer = HybridCategorizer(monthly_finance_config_manager=self.monthly_finance_config_manager,
                                                    app_config=self.app_config)

        # MLCategorizerTrainer initialization, passing app_config
        self.ml_trainer = MLCategorizerTrainer(app_config=self.app_config)

        print("TransactionManager initialized.")

    def _get_transactions_for_training(self) -> pd.DataFrame:
        """
        Loads all transactions from CSV that have a BudgetPath assigned,
        for use in ML model training.
        """
        transactions_df = self.csv_manager.load_transactions()
        # Filter for completed transactions that have a budget path
        return transactions_df[transactions_df['BudgetPath'].notna() & (transactions_df['BudgetPath'] != '')]

    def retrain_ml_model(self):
        """
        Triggers a retraining of the ML categorization model using all available
        historical transaction data.
        """
        print("Initiating ML model retraining...")
        historical_data = self._get_transactions_for_training()
        if not historical_data.empty:
            training_metrics = self.ml_trainer.train_model(historical_data)
            if training_metrics:
                print(f"ML model retraining complete. Accuracy: {training_metrics.get('accuracy', 'N/A'):.4f}")
            else:
                print("ML model retraining could not be completed.")
        else:
            print("No sufficient historical data for ML model retraining.")

    def add_manual_transaction(self,
                               transaction_id: str,
                               transaction_type: str,
                               date: datetime.date,
                               payee: str, # This payee is now assumed to be the final, conformed name
                               account: str,
                               uploaded_file=None,
                               splits: list = None,
                               related_transaction_id: str = "",
                               manual_metadata: Optional[List[Dict[str, Any]]] = None
                               ):
        """
        Creates, validates, and saves one or more split transactions.
        Integrates with PayeeManager and MetadataManager.
        The 'payee' argument is expected to be the final, conformed name,
        determined by the UI's interaction with VendorConfigManager.
        """
        if splits is None or not splits:
            raise ValueError("Transactions must have at least one split defined.")

        try:
            file_path = ""
            if uploaded_file is not None:
                # Use configured path from app_config
                save_dir = self.input_raw_dir
                os.makedirs(save_dir, exist_ok=True)

                file_extension = os.path.splitext(uploaded_file.name)[1]
                unique_filename = f"{transaction_id}{file_extension}"
                file_path = os.path.join(save_dir, unique_filename)

                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                print(f"Saved uploaded file to: {file_path}")

            transactions_to_add = []

            # The 'payee' received here is already the conformed/user-confirmed name from the UI.
            # Just ensure it exists in the payee database.
            if payee:
                self.payee_manager.add_payee(payee) # Add this confirmed payee to the database

            transaction_metadata_entries = []
            if manual_metadata:
                transaction_metadata_entries.extend(manual_metadata)

            # For each split, create a transaction record
            for i, split in enumerate(splits):
                split_description = split.get('description', '')
                split_notes = split.get('notes', '')
                split_amount = split.get('amount', 0.0)
                # These might come from UI, or be empty if categorizer should suggest
                split_budget_scope = split.get('budget_scope', '')
                split_category = split.get('category', '')
                split_sub_category = split.get('sub_category', '')
                split_full_budget_path = split.get('full_budget_path', '')

                # Effective payee for the split is also expected to be conformed.
                # It can default to the overall transaction payee if not specified in the split data.
                effective_payee = split.get('payee', payee)
                if effective_payee:
                    # Ensure this effective_payee for the split is also added to the payee DB.
                    # No fuzzy matching here, as this is the result of UI conformation.
                    effective_payee_uuid = self.payee_manager.add_payee(effective_payee)

                # TODO: update this part to get the account uuid, so that it will be easier to move to databases.
                effective_account = split.get('account', account)
                currency = self.monthly_finance_config_manager.get_currency(effective_account)

                # If category is not explicitly provided (e.g., from manual input UI), categorize
                if not split_full_budget_path or split_full_budget_path == 'Uncategorized:Unassigned':
                    category_suggestions = self.hybrid_categorizer.suggest_category(
                        description=split_description,
                        current_notes=split_notes,
                        payee=effective_payee, # Use the conformed/effective payee uuid
                        account=effective_account,
                        transaction_type=transaction_type  # Pass transaction type
                    )
                    split_budget_scope = category_suggestions.get('BudgetScope', '')
                    split_category = category_suggestions.get('Category', '')
                    split_sub_category = category_suggestions.get('SubCategory', '')
                    split_full_budget_path = category_suggestions.get('BudgetPath', '')

                    if split_full_budget_path and split_full_budget_path != 'Uncategorized:Unassigned':
                        source = category_suggestions.get('Source', 'Auto')
                        confidence = category_suggestions.get('Confidence', 0.0)
                        # Prepend source and confidence to notes if auto-categorized
                        split_notes = f"[{source} - Conf: {confidence:.2f}] {split_notes}".strip()
                else:  # If a full_budget_path was provided manually, set confidence to high and source to Manual
                    category_suggestions = {
                        'Confidence': 1.0,
                        'Source': 'Manual'
                    }
                # TODO: Update this part to get data from the budget database ?
                new_transaction = {
                    "TransactionID": transaction_id,
                    "SplitIndex": i,
                    "Date": date,
                    "Time": datetime.datetime.now().strftime("%H:%M:%S"),
                    "Payer/Payee": effective_payee_uuid,
                    "Account": effective_account,
                    "Description": split_description,
                    "Amount": split_amount,
                    "Currency": currency,
                    "BudgetScope": split_budget_scope,
                    "Category": split_category,
                    "SubCategory": split_sub_category,
                    "BudgetPath": split_full_budget_path,
                    "TransactionType": transaction_type,
                    "RelatedTransactionID": related_transaction_id,
                    "RelatedDebtAccount": "",
                    "RelatedSavingsAccount": "",
                    "IsSubscription": False,
                    "SubscriptionAutoIdentified": False,
                    "InputSource": "Manual",
                    "FilePath": file_path,
                    "LLMConfidence": category_suggestions.get('Confidence', 0.0),
                    # Use actual confidence from categorizer
                    "IsVerified": True,  # Manual entries are implicitly verified by user input
                    "Notes": split_notes,
                    "TimestampAdded": datetime.datetime.now()
                }
                transactions_to_add.append(new_transaction)
            # TODO: Update these parts below to do the save in database.
            transactions_df = self.csv_manager.load_transactions()
            new_df = pd.DataFrame(transactions_to_add)
            updated_df = pd.concat([transactions_df, new_df], ignore_index=True)
            self.csv_manager.save_transactions(updated_df)

            if transaction_metadata_entries:
                self.metadata_manager.add_metadata_entries(
                    transaction_id=transaction_id,
                    metadata_entries=transaction_metadata_entries,
                    source="Manual_Input_With_Invoice_Parse",  # This source might need refinement if not from invoice
                    split_index=-1
                )

            print(f"Successfully added transaction {transaction_id} with {len(splits)} splits.")
            return transaction_id

        except Exception as e:
            print(f"Error in add_manual_transaction: {e}")
            raise

    def process_uploaded_invoice(self, uploaded_file) -> Dict[str, Any]:
        """
        Processes an uploaded invoice image, performs OCR, parses data,
        and returns structured transaction suggestions and metadata.
        Does NOT save to CSV yet; it prepares data for manual review/input.
        """
        if uploaded_file is None:
            raise ValueError("No file uploaded for invoice processing.")

        # Use configured path from app_config
        input_raw_dir = self.input_raw_dir
        os.makedirs(input_raw_dir, exist_ok=True)

        file_extension = os.path.splitext(uploaded_file.name)[1]
        temp_file_name = f"uploaded_invoice_{uuid.uuid4()}{file_extension}"
        temp_file_path = os.path.join(input_raw_dir, temp_file_name)

        try:
            with open(temp_file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            print(f"Temporary invoice file saved to: {temp_file_path}")

            ocr_text = self.ocr_processor.process_image(temp_file_path)

            # Get the suggestion result for the payee from InvoiceParser
            # InvoiceParser will use vendor_config_manager.suggest_conformed_payee
            # and return the best suggestion. The UI will then verify this suggestion.
            parsed_invoice_data = self.invoice_parser.parse_invoice_text(ocr_text)

            # The payee from parsed_invoice_data is already the conformed name
            conform_payee = parsed_invoice_data['payee']
            if conform_payee:
                # Ensure this conformed payee is in the payee database
                self.payee_manager.add_payee(conform_payee)

            # Determine main transaction type (usually Expense for invoices, but can be customized)
            main_transaction_type = "Expense"  # TODO: Update to match the given invoice

            # Auto-Categorize Splits using the HybridCategorizer
            for split in parsed_invoice_data['splits']:
                categorization = self.hybrid_categorizer.suggest_category(
                    description=split['description'],
                    current_notes=parsed_invoice_data['notes'],
                    payee=conform_payee, # Use the conformed payee from invoice parsing
                    account=parsed_invoice_data['account'],
                    transaction_type=main_transaction_type
                )
                split['budget_scope'] = categorization['BudgetScope']
                split['category'] = categorization['Category']
                split['sub_category'] = categorization['SubCategory']
                split['full_budget_path'] = categorization['BudgetPath']
                split['llm_confidence'] = categorization['Confidence']
                split['categorization_source'] = categorization['Source']
                if split['full_budget_path'] != 'Uncategorized:Unassigned':
                    split[
                        'notes'] = f"[{categorization['Source']} - Conf: {categorization['Confidence']:.2f}] {split['notes'] or ''}".strip()

            metadata_from_invoice = []
            for tax in parsed_invoice_data.get('taxes', []):
                metadata_from_invoice.append(
                    {'key': f"Tax - {tax['name']}", 'value': tax['amount'], 'source': 'Invoice OCR'})

            for key, value in parsed_invoice_data.get('metadata', {}).items():
                metadata_from_invoice.append({'key': key, 'value': value, 'source': 'Invoice OCR'})

            return {
                "transaction_id": str(uuid.uuid4()),
                "payee": conform_payee,
                "date": parsed_invoice_data['date'],
                "account": parsed_invoice_data['account'],
                "total_amount": parsed_invoice_data['total_amount'],
                "splits": parsed_invoice_data['splits'],
                "notes": parsed_invoice_data['notes'],
                "file_path": temp_file_path,
                "metadata": metadata_from_invoice,
                "transaction_type": main_transaction_type  # Return transaction type for UI
            }

        except Exception as e:
            print(f"Error processing uploaded invoice: {e}")
            failed_dir = self.input_failed_dir  # Use path from app_config
            os.makedirs(failed_dir, exist_ok=True)
            failed_file_path = os.path.join(failed_dir, os.path.basename(temp_file_path))
            if os.path.exists(temp_file_path):
                os.rename(temp_file_path, failed_file_path)
            raise

        finally:
            # Ensure proper file movement after processing
            if os.path.exists(temp_file_path) and "Error" not in locals().get('e', ''):
                processed_dir = self.input_processed_dir  # Use path from app_config
                os.makedirs(processed_dir, exist_ok=True)
                processed_file_path = os.path.join(processed_dir, os.path.basename(temp_file_path))
                # Only move if it hasn't already been moved to failed_dir due to an error
                if os.path.exists(temp_file_path):  # Check again if file still exists before moving
                    os.rename(temp_file_path, processed_file_path)
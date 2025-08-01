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
from .photo_manager import PhotoManager  # NEW: Import PhotoManager
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
                 photo_manager: PhotoManager,  # NEW: Accept PhotoManager
                 app_config: Dict[str, Any]):
        """
        Initializes the TransactionManager.
        Args:
            csv_manager (CSVManager): An instance of CSVManager to handle data I/O.
            monthly_finance_config_manager (MonthlyFinanceConfigManager): An instance of FinanceConfigManager to access financial configuration.
            payee_manager (PayeeManager): An instance of PayeeManager to manage payee data.
            metadata_manager (MetadataManager): An instance of MetadataManager to store extra transaction details.
            photo_manager (PhotoManager): An instance of PhotoManager to manage associated photos. # NEW
            app_config (Dict[str, Any]): The loaded application configuration dictionary.
        """
        self.csv_manager = csv_manager
        self.monthly_finance_config_manager = monthly_finance_config_manager
        self.payee_manager = payee_manager
        self.metadata_manager = metadata_manager
        self.photo_manager = photo_manager  # NEW: Store PhotoManager
        self.app_config = app_config

        # Paths from app_config for I/O operations (these are now primarily for OCR/parsing temp, or legacy)
        self.input_raw_dir = self.app_config.get('paths', {}).get('invoice_input_dir', 'data/invoices/input')
        self.input_processed_dir = self.app_config.get('paths', {}).get('invoice_processed_dir', 'data/invoices/processed')
        self.input_failed_dir = self.app_config.get('paths', {}).get('invoice_failed_dir', 'data/invoices/failed')

        # VendorConfigManager initialization, passing relevant app_config parts including new ambiguity threshold
        llm_config = self.app_config.get('llm_config', {})
        self.vendor_config_manager = VendorConfigManager(
            vendor_patterns_file=self.app_config['paths']['vendor_patterns_file'],
            llm_model_name=llm_config.get('vendor_fuzzy_match_model', 'all-MiniLM-L6-v2'),
            llm_similarity_threshold=llm_config.get('vendor_fuzzy_match_threshold', 0.85),
            llm_ambiguity_threshold=llm_config.get('vendor_fuzzy_match_ambiguity_threshold', 0.65),
            payee_manager=self.payee_manager,
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
                               uploaded_files: List[Any] = None, # Corrected: Expect a list of files
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
            # For manual transactions, if file(s) are uploaded, save them via PhotoManager
            if uploaded_files: # Corrected: Check if the list is not empty
                saved_paths = self.photo_manager.save_photos_for_transaction(transaction_id, uploaded_files) # Corrected: Pass list directly
                if saved_paths:
                    file_path = saved_paths[0] # Store the path of the first saved photo
                else:
                    print("No photo was saved for this manual transaction.")


            transactions_to_add = []

            # The 'payee' received here is already the conformed/user-confirmed name from the UI.
            # Just ensure it exists in the payee database.
            if payee:
                # Get the UUID for the payee (add if new)
                payee_uuid = self.payee_manager.add_payee(payee)
            else:
                payee_uuid = None # Or handle error if payee is mandatory

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
                effective_payee_uuid = None
                if effective_payee:
                    # Ensure this effective_payee for the split is also added to the payee DB.
                    # No fuzzy matching here, as this is the result of UI conformation.
                    effective_payee_uuid = self.payee_manager.add_payee(effective_payee)
                else:
                    effective_payee_uuid = payee_uuid # Fallback to main transaction payee UUID

                # TODO: update this part to get the account uuid, so that it will be easier to move to databases.
                effective_account = split.get('account', account)
                currency = self.monthly_finance_config_manager.get_currency(effective_account)

                # If category is not explicitly provided (e.g., from manual input UI), categorize
                if not split_full_budget_path or split_full_budget_path == 'Uncategorized:Unassigned':
                    category_suggestions = self.hybrid_categorizer.suggest_category(
                        description=split_description,
                        current_notes=split_notes, # Use split's notes for categorization
                        payee=effective_payee, # Use the conformed/effective payee name
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
                    "FilePath": file_path, # Use the saved file path from PhotoManager
                    "LLMConfidence": category_suggestions.get('Confidence', 0.0),
                    "IsVerified": True,
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
                    source="Manual_Input",
                    split_index=-1
                )
            print(f"Successfully added transaction {transaction_id} with {len(splits)} splits.")
            return transaction_id

        except Exception as e:
            print(f"Error in add_manual_transaction: {e}")
            raise

    def get_all_transactions(self, include_payee_names: bool = True) -> pd.DataFrame:
        """
        Retrieves all transactions from the CSV. Optionally enriches the DataFrame by replacing PayeeId with Payee Name.
        """
        transactions_df = self.csv_manager.load_transactions()
        if transactions_df.empty:
            return pd.DataFrame()

        if include_payee_names:
            # Map Payer/Payee (which contains PayeeId) to Payee Name
            payee_id_to_name_map = {
                payee['PayeeId']: payee['Name']
                for _, payee in self.payee_manager.get_all_payees_payers().iterrows()
            }
            transactions_df.loc[:, 'PayeeName'] = transactions_df['Payer/Payee'].map(payee_id_to_name_map).fillna(transactions_df['Payer/Payee'])

        return transactions_df

    def get_transactions_by_month_year(self, month: int, year: int, include_payee_names: bool = True) -> pd.DataFrame:
        """
        Retrieves transactions for a specific month and year.
        Args:
            month (int): The month (1-12).
            year (int): The year.
            include_payee_names (bool): Whether to replace PayeeId with PayeeName.
        Returns:
            pd.DataFrame: DataFrame of transactions for the specified month/year.
        """
        all_transactions_df = self.get_all_transactions(include_payee_names=include_payee_names)
        if all_transactions_df.empty:
            return pd.DataFrame()

        # Ensure 'Date' column is datetime objects for filtering
        all_transactions_df['Date'] = pd.to_datetime(all_transactions_df['Date'], errors='coerce')

        # Filter by month and year
        # filtered_df = pd.DataFrame()
        filtered_df = all_transactions_df[
            (all_transactions_df['Date'].dt.month == month) &
            (all_transactions_df['Date'].dt.year == year)
        ].copy() # Use .copy() to prevent SettingWithCopyWarning

        return filtered_df

    def get_transaction_by_id(self, transaction_id: str) -> Optional[pd.DataFrame]:
        """Retrieves all splits for a given transaction ID."""
        df = self.get_all_transactions(include_payee_names=True)
        filtered_df = df[df['TransactionID'] == transaction_id].copy()
        if not filtered_df.empty:
            # Also get associated metadata # WRONG. Metadata returned are a dict key, value, source,
            # and we can have multiple rows for a single split.
            filtered_df['Metadata'] = filtered_df.apply(
                lambda row: self.metadata_manager.get_metadata_for_transaction(
                    transaction_id=row['TransactionID'],
                    split_index=row['SplitIndex']
                ), axis=1
            )
            return filtered_df
        return None

    def update_transaction_status(self, transaction_id: str, is_verified: bool):
        """Updates the 'IsVerified' status of a transaction."""
        df = self.csv_manager.load_transactions()
        if transaction_id in df['TransactionID'].values:
            df.loc[df['TransactionID'] == transaction_id, 'IsVerified'] = is_verified
            self.csv_manager.save_transactions(df)
            print(f"Transaction {transaction_id} 'IsVerified' status updated to {is_verified}.")
        else:
            print(f"Transaction {transaction_id} not found for status update.")

    def update_transaction(self,
                           transaction_id: str,
                           date: Optional[datetime.date] = None,
                           payee_name: Optional[str] = None, # Changed to payee_name for easier use with UI
                           account: Optional[str] = None,
                           transaction_type: Optional[str] = None,
                           # total_amount is derived from splits, or should be checked for consistency
                           splits: Optional[List[Dict[str, Any]]] = None, # Updated splits format
                           notes: Optional[str] = None,
                           file_path: Optional[str] = None,
                           metadata: Optional[List[Dict[str, str]]] = None, # Assuming dicts of {'key': 'value'}
                           related_transaction_id: Optional[str] = None,
                           original_transaction_id: Optional[str] = None):
        """
        Updates an existing transaction, including its main fields and/or splits.
        This function will delete existing splits for the given transaction_id and re-add them
        if 'splits' is provided, ensuring data integrity.
        It uses the add_manual_transaction method for re-insertion, ensuring consistency.
        """
        # Load all transactions
        transactions_df = self.csv_manager.load_transactions()

        # Find all rows related to this transaction_id
        transaction_rows_indices = transactions_df[transactions_df['TransactionID'] == transaction_id].index.tolist()

        if not transaction_rows_indices:
            print(f"Transaction ID {transaction_id} not found for update.")
            return

        # Get existing values for fields not provided in update
        # This requires getting at least one existing row's data
        # Ensure we get the *original* transaction data to fill missing fields
        original_transaction_df = self.csv_manager.load_transactions()
        first_existing_row = original_transaction_df[original_transaction_df['TransactionID'] == transaction_id].iloc[0]

        _date = date if date is not None else pd.to_datetime(first_existing_row['Date']).date()
        _payee_name = payee_name if payee_name is not None else self.payee_manager.get_payee_name_by_id(first_existing_row['Payer/Payee'])
        _account = account if account is not None else first_existing_row['Account']
        _transaction_type = transaction_type if transaction_type is not None else first_existing_row['TransactionType']
        _notes = notes if notes is not None else first_existing_row['Notes']
        _file_path = file_path if file_path is not None else (first_existing_row['FilePath'] if 'FilePath' in first_existing_row else '')
        _related_transaction_id = related_transaction_id if related_transaction_id is not None else (first_existing_row['RelatedTransactionID'] if 'RelatedTransactionID' in first_existing_row else '')
        _original_transaction_id = original_transaction_id if original_transaction_id is not None else (first_existing_row['OriginalTransactionID'] if 'OriginalTransactionID' in first_existing_row else '')

        # Get existing transaction-level metadata if not provided
        _metadata = metadata if metadata is not None else self.metadata_manager.get_metadata_for_transaction(transaction_id, split_index=-1)
        # Convert metadata list of objects to {'key': 'value'} dicts if needed
        # Assuming metadata_manager.get_metadata_for_transaction returns list of dicts like {'Key': 'value', ...}
        # We need {'key': 'value'} for add_manual_transaction
        _formatted_metadata = []
        if _metadata:
            _formatted_metadata = [{'key': entry['Key'], 'value': entry['Value']} for entry in _metadata]


        # If splits are provided, it means we are replacing all existing splits for this transaction.
        if splits is not None:
            # Delete existing transaction rows (all splits) and associated metadata
            transactions_df = transactions_df.drop(transaction_rows_indices).reset_index(drop=True)
            self.csv_manager.save_transactions(transactions_df) # Save interim state to remove old rows
            self.metadata_manager.delete_metadata_for_transaction(transaction_id) # Delete all related metadata

            # Recalculate total_amount from new splits, if not explicitly provided
            # Note: total_amount is not directly passed to add_manual_transaction; it's derived/handled within splits.
            # We will pass the sum of new splits' amounts in this context
            if splits:
                calculated_total_amount = sum(s.get('amount', 0.0) for s in splits)
            else:
                calculated_total_amount = 0.0 # No splits provided, effectively a zero amount transaction if allowed

            # Prepare splits for add_manual_transaction based on the new splits provided
            # We need to map the incoming simplified 'splits' (BudgetPath, Amount, Notes)
            # to the more detailed format expected by add_manual_transaction (description, budget_scope etc.)
            # Assuming incoming splits are: List[Dict[str, Any]] with 'full_budget_path', 'amount', 'notes', 'description'
            # If any of budget_scope, category, sub_category are missing, add_manual_transaction will re-categorize.
            splits_for_add_manual = []
            for split in splits:
                # Attempt to parse full_budget_path into its components if available
                budget_path_parts = split.get('full_budget_path', '').split('::')
                budget_scope = budget_path_parts[0] if len(budget_path_parts) > 0 else ''
                category = budget_path_parts[1] if len(budget_path_parts) > 1 else ''
                sub_category = budget_path_parts[2] if len(budget_path_parts) > 2 else ''

                splits_for_add_manual.append({
                    'description': split.get('description', ''), # If description is missing, it will be blank
                    'notes': split.get('notes', ''),
                    'amount': split.get('amount', 0.0),
                    'budget_scope': split.get('budget_scope', budget_scope), # Prefer provided, else derived
                    'category': split.get('category', category),
                    'sub_category': split.get('sub_category', sub_category),
                    'full_budget_path': split.get('full_budget_path', ''),
                    'payee': split.get('payee', _payee_name), # Split-specific payee
                    'account': split.get('account', _account) # Split-specific account
                })

            # Re-add the transaction with new/updated splits and metadata using add_manual_transaction
            self.add_manual_transaction(
                transaction_id=transaction_id,
                transaction_type=_transaction_type,
                date=_date,
                payee=_payee_name, # Pass the conformed payee name
                account=_account,
                uploaded_file=(_file_path if os.path.exists(_file_path) else None), # Re-attach file if exists
                splits=splits_for_add_manual,
                related_transaction_id=_related_transaction_id,
                manual_metadata=_formatted_metadata
            )
        else:
            # If no splits are provided, update only the main transaction fields for all splits.
            # This requires direct DataFrame manipulation and then saving.
            for idx in transaction_rows_indices:
                if date is not None:
                    transactions_df.loc[idx, 'Date'] = date.isoformat()
                if payee_name is not None:
                    # Need to get payee_id from payee_name
                    updated_payee_id = self.payee_manager.add_payee(payee_name) # Ensure payee exists and get its ID
                    transactions_df.loc[idx, 'Payer/Payee'] = updated_payee_id # Update the Payer/Payee column
                if account is not None:
                    transactions_df.loc[idx, 'Account'] = account
                if transaction_type is not None:
                    transactions_df.loc[idx, 'TransactionType'] = transaction_type
                if notes is not None:
                    transactions_df.loc[idx, 'Notes'] = notes
                if file_path is not None: # Update only the first split's file_path, or manage carefully
                    if transactions_df.loc[idx, 'SplitIndex'] == 0: # Assuming file_path is only on primary split
                        transactions_df.loc[idx, 'FilePath'] = file_path
                if related_transaction_id is not None: # Update only the first split's related_id
                     if transactions_df.loc[idx, 'SplitIndex'] == 0:
                        transactions_df.loc[idx, 'RelatedTransactionID'] = related_transaction_id
                if original_transaction_id is not None: # Update only the first split's original_id
                     if transactions_df.loc[idx, 'SplitIndex'] == 0:
                        transactions_df.loc[idx, 'OriginalTransactionID'] = original_transaction_id

            # Update transaction-level metadata
            if metadata is not None:
                self.metadata_manager.delete_metadata_for_transaction(transaction_id, split_index=-1) # Delete general metadata
                _formatted_metadata = [{'key': meta['Key'], 'value': meta['Value']} for meta in metadata] # Assuming metadata is list of {'Key': 'Value'}
                self.metadata_manager.add_metadata_entries(
                    transaction_id=transaction_id,
                    metadata_entries=_formatted_metadata,
                    source="Manual_Update_General",
                    split_index=-1
                )

            self.csv_manager.save_transactions(transactions_df)
            print(f"Transaction {transaction_id} main fields updated successfully.")

    def process_uploaded_invoice(self, uploaded_files: List[Any]) -> Dict[str, Any]:
        """
        Processes an uploaded invoice image using OCR and LLM to extract transaction details.
        Saves the image(s) via PhotoManager, then performs OCR and parsing.
        Moves the processed file(s) to a processed or failed directory.

        Args:
            uploaded_files (List[Any]): A list of Streamlit UploadedFile objects (or similar file-like objects).

        Returns:
            Dict[str, Any]: A dictionary containing extracted transaction data and parsed splits.
                            Returns an empty dictionary if processing fails.
        """
        if not uploaded_files:
            raise ValueError("No uploaded files provided for invoice processing.")

        # Generate a single transaction ID for all files in this logical invoice
        transaction_id = f"TRN-{int(datetime.datetime.now().timestamp())}-{uuid.uuid4().hex[:6].upper()}"
        print(f"Processing invoice(s) for new transaction ID: {transaction_id}")

        saved_file_paths = []
        try:
            # 1. Save uploaded files to the permanent storage via PhotoManager
            saved_file_paths = self.photo_manager.save_photos_for_transaction(transaction_id, uploaded_files)
            if not saved_file_paths:
                raise Exception("No files were successfully saved by PhotoManager.")

            # For OCR processing, use all saved file paths
            # Assuming OCRProcessor.process_image can handle a list of paths
            extracted_text = self.ocr_processor.process_image(saved_file_paths)
            if not extracted_text:
                raise Exception("OCR failed to extract text from the invoice images.")

            # 3. Parse the extracted text using the InvoiceParser
            parsed_invoice_data = self.invoice_parser.parse_invoice_text(extracted_text)

            if not parsed_invoice_data or not parsed_invoice_data.get('total_amount'):
                raise Exception("Invoice parsing failed to extract essential data (e.g., total amount).")

            # 4. Determine main transaction type (Expense, Income, Transfer)
            main_transaction_type = parsed_invoice_data.get('transaction_type', 'Expense') # Default to Expense

            # 5. Categorize each split (or the main transaction if no splits)
            processed_splits = []
            metadata_from_invoice = []

            # If parser provides explicit splits, process them
            if parsed_invoice_data.get('splits'):
                for split in parsed_invoice_data['splits']:
                    category_suggestions = self.hybrid_categorizer.suggest_category(
                        description=split.get('description', ''),
                        current_notes=split.get('notes', ''),
                        payee=parsed_invoice_data.get('payee_conformed_name', ''),
                        account=parsed_invoice_data.get('account', ''),
                        transaction_type=main_transaction_type
                    )
                    split['budget_scope'] = category_suggestions.get('BudgetScope', '')
                    split['category'] = category_suggestions.get('Category', '')
                    split['sub_category'] = category_suggestions.get('SubCategory', '')
                    split['full_budget_path'] = category_suggestions.get('BudgetPath', '')
                    split['llm_confidence'] = category_suggestions.get('Confidence', 0.0)
                    split['notes'] = f"[{category_suggestions.get('Source', 'Auto')} - Conf: {category_suggestions.get('Confidence', 0.0):.2f}] {split.get('notes', '')}".strip()
                    processed_splits.append(split)
            else:
                # If no explicit splits, categorize the whole transaction as one split
                category_suggestions = self.hybrid_categorizer.suggest_category(
                    description=parsed_invoice_data.get('description', ''),
                    current_notes=parsed_invoice_data.get('notes', ''),
                    payee=parsed_invoice_data.get('payee_conformed_name', ''),
                    account=parsed_invoice_data.get('account', ''),
                    transaction_type=main_transaction_type
                )
                processed_splits.append({
                    "description": parsed_invoice_data.get('description', ''),
                    "amount": parsed_invoice_data['total_amount'],
                    "budget_scope": category_suggestions.get('BudgetScope', ''),
                    "category": category_suggestions.get('Category', ''),
                    "sub_category": category_suggestions.get('SubCategory', ''),
                    "full_budget_path": category_suggestions.get('BudgetPath', ''),
                    "llm_confidence": category_suggestions.get('Confidence', 0.0),
                    "notes": f"[{category_suggestions.get('Source', 'Auto')} - Conf: {category_suggestions.get('Confidence', 0.0):.2f}] {parsed_invoice_data.get('notes', '')}".strip()
                })

            # Extract any general metadata from the invoice parsing
            if parsed_invoice_data.get('metadata'):
                metadata_from_invoice.extend(parsed_invoice_data['metadata'])

            # Return a structured dictionary for the UI to review and save
            return {
                "transaction_id": transaction_id,
                "date": parsed_invoice_data['date'],
                "payee_raw": parsed_invoice_data['payee_raw'],
                "payee_conformed_name": parsed_invoice_data['payee_conformed_name'],
                "account": parsed_invoice_data['account'],
                "total_amount": parsed_invoice_data['total_amount'],
                "splits": processed_splits,
                "notes": parsed_invoice_data['notes'],
                "file_path": saved_file_paths[0] if saved_file_paths else '', # Store the path of the first saved file
                "metadata": metadata_from_invoice,
                "transaction_type": main_transaction_type
            }

        except Exception as e:
            print(f"Error processing uploaded invoice: {e}")
            # If an error occurs, PhotoManager should ideally handle cleanup if files were saved.
            # Here, we only clean up if we manually created temp files (which we no longer do).
            # The files are already saved by PhotoManager, so they persist for debugging/review.
            # TODO: Update photomanager to move processed or error files in the correct directory.
            raise

    def delete_transaction(self, transaction_id: str) -> bool:
        """
        Deletes a transaction and all its associated splits and metadata from the CSVs.
        Also deletes any associated photo files.
        """
        # Load current transactions and metadata
        transactions_df = self.csv_manager.load_transactions()
        metadata_df = self.csv_manager.load_metadata()

        # Check if transaction exists
        if transaction_id not in transactions_df['TransactionID'].values:
            print(f"Transaction {transaction_id} not found for deletion.")
            return False

        # 1. Delete associated photos using PhotoManager
        self.photo_manager.delete_photos_for_transaction(transaction_id)
        print(f"Associated photos for transaction {transaction_id} deleted.")

        # 2. Remove transaction entries from transactions.csv
        initial_transactions_count = len(transactions_df)
        transactions_df = transactions_df[transactions_df['TransactionID'] != transaction_id].reset_index(drop=True)
        self.csv_manager.save_transactions(transactions_df)
        print(f"Removed {initial_transactions_count - len(transactions_df)} splits for transaction {transaction_id} from transactions.csv.")

        # 3. Remove associated metadata entries from metadata.csv
        self.metadata_manager.delete_metadata_for_transaction(transaction_id)  # Delete associated metadata
        print(f"Transaction {transaction_id} and all its associated data successfully deleted.")

        return True
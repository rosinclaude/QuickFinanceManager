# modules/managers/transaction_manager.py

import pandas as pd
import datetime
import uuid
import os
from .csv_manager import CSVManager
from .finance_config_manager import FinanceConfigManager
from .payee_manager import PayeeManager  # Import the new manager


class TransactionManager:
    """
    Handles the business logic for adding and managing transactions.
    It uses the CSVManager for data storage operations.
    """

    def __init__(self, csv_manager: CSVManager, config_manager: FinanceConfigManager, payee_manager: PayeeManager):
        """
        Initializes the TransactionManager.
        Args:
            csv_manager (CSVManager): An instance of CSVManager to handle data I/O.
            config_manager (FinanceConfigManager): An instance of FinanceConfigManager to access app configuration.
            payee_manager (PayeeManager): An instance of PayeeManager to manage payee data.
        """
        self.csv_manager = csv_manager
        self.config_manager = config_manager
        self.payee_manager = payee_manager  # Store the payee manager

    def add_manual_transaction(self,
                               transaction_id: str,  # Main ID for a conceptual transaction (can have splits)
                               transaction_type: str,
                               date: datetime.date,
                               payee: str,  # Global Payer/Payee for the overall transaction
                               account: str,
                               # Global Account for the overall transaction (empty for transfers if accounts differ)
                               uploaded_file=None,
                               splits: list = None,  # List of dictionaries for each split
                               related_transaction_id: str = ""  # For linking transfers
                               ):
        """
        Creates, validates, and saves one or more split transactions.

        Args:
            transaction_id (str): A unique ID for the entire conceptual transaction (e.g., a single receipt).
            transaction_type (str): Type of transaction (Expense, Income, Transfer).
            date (datetime.date): Date of the transaction(s).
            payee (str): The overall Payer/Payee for this transaction (e.g., "Grocery Store").
            account (str): The overall Account from which this transaction originates or is received.
                           For transfers, this will be empty, as account is split-specific.
            uploaded_file (UploadedFile, optional): A file uploaded via Streamlit. Defaults to None.
            splits (list): A list of dictionaries, where each dictionary represents a split:
                            {
                                'amount': float,
                                'description': str,  # Split-specific description
                                'notes': str,        # Split-specific notes
                                'budget_scope': str,
                                'category': str,
                                'sub_category': str,
                                'full_budget_path': str,
                                'account': str,      # Only for transfers to override the global account
                                'payee': str         # Only for transfers to override the global payee
                            }
            related_transaction_id (str, optional): ID of a related transaction (e.g., for transfers). Defaults to "".

        Returns:
            str: The TransactionID of the overall transaction.
        """
        if splits is None or not splits:
            raise ValueError("Transactions must have at least one split defined.")

        try:
            # Handle the uploaded file (placeholder logic)
            file_path = ""
            if uploaded_file is not None:
                save_dir = "input_raw"
                os.makedirs(save_dir, exist_ok=True)

                file_extension = os.path.splitext(uploaded_file.name)[1]
                unique_filename = f"{transaction_id}{file_extension}"
                file_path = os.path.join(save_dir, unique_filename)

                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                print(f"Saved uploaded file to: {file_path}")

            transactions_to_add = []
            currency = self.config_manager.get_currency()

            # Add the main payee to the payee manager
            if payee:
                self.payee_manager.add_payee(payee)

            for i, split in enumerate(splits):
                split_description = split.get('description', '')
                split_notes = split.get('notes', '')
                split_amount = split.get('amount', 0.0)
                split_budget_scope = split.get('budget_scope', '')
                split_category = split.get('category', '')
                split_sub_category = split.get('sub_category', '')
                split_full_budget_path = split.get('full_budget_path', '')

                effective_payee = split.get('payee', payee)
                effective_account = split.get('account', account)

                # Ensure effective_payee is added to the manager, even for splits if it's different
                if effective_payee:
                    self.payee_manager.add_payee(effective_payee)

                new_transaction = {
                    "TransactionID": transaction_id,
                    "SplitIndex": i,
                    "Date": date,
                    "Time": datetime.datetime.now().strftime("%H:%M:%S"),
                    "Payer/Payee": effective_payee,
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
                    "LLMConfidence": 1.0,
                    "IsVerified": True,
                    "Notes": split_notes,
                    "TimestampAdded": datetime.datetime.now()
                }
                transactions_to_add.append(new_transaction)

            transactions_df = self.csv_manager.load_transactions()
            new_df = pd.DataFrame(transactions_to_add)
            updated_df = pd.concat([transactions_df, new_df], ignore_index=True)
            self.csv_manager.save_transactions(updated_df)

            print(f"Successfully added transaction {transaction_id} with {len(splits)} splits.")
            return transaction_id

        except Exception as e:
            print(f"Error in add_manual_transaction: {e}")
            raise
# modules/managers/transaction_manager.py

import pandas as pd
import datetime
import uuid
import os
from .csv_manager import CSVManager
from .finance_config_manager import FinanceConfigManager


class TransactionManager:
    """
    Handles the business logic for adding and managing transactions.
    It uses the CSVManager for data storage operations.
    """

    def __init__(self, csv_manager: CSVManager, config_manager: FinanceConfigManager):
        """
        Initializes the TransactionManager.
        Args:
            csv_manager (CSVManager): An instance of CSVManager to handle data I/O.
            config_manager (FinanceConfigManager): An instance of FinanceConfigManager to access app configuration.
        """
        self.csv_manager = csv_manager
        self.config_manager = config_manager

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

            for i, split in enumerate(splits):
                # Use split-specific description and notes
                split_description = split.get('description', '')
                split_notes = split.get('notes', '')
                split_amount = split.get('amount', 0.0)
                split_budget_scope = split.get('budget_scope', '')
                split_category = split.get('category', '')
                split_sub_category = split.get('sub_category', '')
                split_full_budget_path = split.get('full_budget_path', '')

                # For transfers, split might have its own payee and account
                # For non-transfers, use the global payee and account
                effective_payee = split.get('payee',
                                            payee)  # Use split-specific payee if provided (e.g., for transfers)
                effective_account = split.get('account',
                                              account)  # Use split-specific account if provided (e.g., for transfers)

                # Create a new transaction record for each split
                new_transaction = {
                    "TransactionID": transaction_id,
                    "SplitIndex": i,  # Assign a unique index for each split
                    "Date": date,
                    "Time": datetime.datetime.now().strftime("%H:%M:%S"),
                    "Payer/Payee": effective_payee,  # Use effective payee
                    "Account": effective_account,  # Use effective account
                    "Description": split_description,  # Split-specific description
                    "Amount": split_amount,
                    "Currency": currency,
                    "BudgetScope": split_budget_scope,
                    "Category": split_category,
                    "SubCategory": split_sub_category,
                    "BudgetPath": split_full_budget_path,
                    "TransactionType": transaction_type,
                    "RelatedTransactionID": related_transaction_id,  # Link related transactions
                    "RelatedDebtAccount": "",
                    "RelatedSavingsAccount": "",
                    "IsSubscription": False,  # Will be set via payee mapping or explicit UI
                    "SubscriptionAutoIdentified": False,
                    "InputSource": "Manual",
                    "FilePath": file_path,
                    "LLMConfidence": 1.0,
                    "IsVerified": True,
                    "Notes": split_notes,  # Split-specific notes
                    "TimestampAdded": datetime.datetime.now()
                }
                transactions_to_add.append(new_transaction)

                # Save payee for non-transfer/internal type transactions, using the effective payee
                if transaction_type not in ["Transfer"]:
                    self.csv_manager.save_payee_data(effective_payee)
                # For transfers, the effective_payee is set by the UI (e.g., "Transfer to X"),
                # and the _save_payee_data function already has logic to ignore internal accounts.
                # So we can call it for transfers too, it will just likely be skipped.
                elif transaction_type == "Transfer":
                    self.csv_manager.save_payee_data(effective_payee)

            # Load existing transactions to append the new ones
            transactions_df = self.csv_manager.load_transactions()
            new_df = pd.DataFrame(transactions_to_add)
            updated_df = pd.concat([transactions_df, new_df], ignore_index=True)
            self.csv_manager.save_transactions(updated_df)

            print(f"Successfully added transaction {transaction_id} with {len(splits)} splits.")
            return transaction_id

        except Exception as e:
            print(f"Error in add_manual_transaction: {e}")
            raise


    def get_transactions_with_parsed_budget_path(self):
        """
        Loads transactions and parses the 'BudgetPath' into individual level columns.
        Caches the result for performance.

        Returns:
            pd.DataFrame: DataFrame with transactions and parsed budget levels.
        """
        df = self.csv_manager.load_transactions()

        # Ensure 'BudgetPath' column exists, fill NaN with empty string
        if 'BudgetPath' not in df.columns:
            df['BudgetPath'] = ""
        else:
            df['BudgetPath'] = df['BudgetPath'].fillna("")

        # Parse BudgetPath into multiple columns
        # Split the path string by '/' and expand into separate columns
        # Use .apply(lambda x: pd.Series(x)) to handle paths of different lengths
        parsed_paths = df['BudgetPath'].apply(lambda x: pd.Series(x.split('/')) if x else pd.Series(['']))

        # Rename columns to BudgetLevel_0, BudgetLevel_1, etc.
        # Handle cases where 'BudgetPath' might be empty, resulting in a single empty string series
        if not parsed_paths.empty and not (parsed_paths.iloc[:, 0] == '').all():  # Check if actual paths were parsed
            parsed_paths.columns = [f"BudgetLevel_{i}" for i in range(parsed_paths.shape[1])]
            # Drop the initial empty string if the path was genuinely empty, and not "Level_0"
            if "BudgetLevel_0" in parsed_paths.columns and (parsed_paths["BudgetLevel_0"] == '').all():
                parsed_paths = parsed_paths.drop(columns=["BudgetLevel_0"])
                parsed_paths.columns = [f"BudgetLevel_{i}" for i in range(parsed_paths.shape[1])]

        # Concatenate the original DataFrame with the new parsed columns
        df_with_levels = pd.concat([df, parsed_paths], axis=1)

        return df_with_levels


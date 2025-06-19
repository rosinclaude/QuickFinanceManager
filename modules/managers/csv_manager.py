# modules/managers/csv_manager.py

import os
import pandas as pd
import datetime


class CSVManager:
    """
    Manages loading and saving data for both transaction and payee CSV files.
    Ensures default files with headers are created if they don't exist.
    """

    def __init__(self, transactions_csv_path: str, payees_csv_path: str, metadata_csv_path: str):
        """
        Initializes the CSVManager.
        Args:
            transactions_csv_path (str): Full path to the transactions CSV file.
            payees_csv_path (str): Full path to the payees CSV file.
            metadata_csv_path (str): Full path to the metadata CSV file.
        """
        self.transactions_csv_path = transactions_csv_path
        self.payees_csv_path = payees_csv_path
        self.metadata_csv_path = metadata_csv_path # NEW

        # Ensure the data directory exists where CSVs will be stored
        os.makedirs(os.path.dirname(transactions_csv_path), exist_ok=True)

        # Ensure default CSV files exist with proper headers
        self._ensure_transactions_csv_exists()
        self._ensure_payees_csv_exists()
        self._ensure_metadata_csv_exists() # NEW

    def _ensure_transactions_csv_exists(self):
        """
        Creates the transactions CSV file with defined headers if it does not exist.
        This includes 'SplitIndex' to support splitting transactions across multiple categories,
        'RelatedTransactionID' for linking, and 'BudgetPath' for hierarchy.
        """
        if not os.path.exists(self.transactions_csv_path):
            print(f"Creating default transactions CSV at: {self.transactions_csv_path}")
            # Define all transaction columns, including new ones
            columns = [
                "TransactionID", "SplitIndex", "Date", "Time", "Payer/Payee", "Account",
                "Description", "Amount", "Currency", "BudgetScope", "Category", "SubCategory",
                "BudgetPath", "TransactionType", "RelatedTransactionID",  # NEW: RelatedTransactionID
                "RelatedDebtAccount", "RelatedSavingsAccount",
                "IsSubscription", "SubscriptionAutoIdentified",
                "InputSource", "FilePath", "LLMConfidence", "IsVerified", "Notes", "TimestampAdded"
            ]
            df = pd.DataFrame(columns=columns)
            df.to_csv(self.transactions_csv_path, index=False)

    def _ensure_payees_csv_exists(self):
        """Creates the payees CSV file with headers if it does not exist."""
        if not os.path.exists(self.payees_csv_path):
            print(f"Creating default payees CSV at: {self.payees_csv_path}")
            # Define all payee columns
            columns = [
                "Name", "Aliases", "DefaultCategory", "DefaultSubCategory",
                "DefaultAccount", "DefaultTransactionType", "RelatedDebtAccount",
                "RelatedSavingsAccount", "IsSubscription", "Notes", "LastUpdated"
            ]
            df = pd.DataFrame(columns=columns)
            df.to_csv(self.payees_csv_path, index=False)

    def _ensure_metadata_csv_exists(self):  # NEW METHOD
        """Creates the metadata CSV file with headers if it does not exist."""
        if not os.path.exists(self.metadata_csv_path):
            print(f"Creating default metadata CSV at: {self.metadata_csv_path}")
            columns = [
                "MetadataID", "TransactionID", "SplitIndex", "Key", "Value", "Source", "TimestampAdded"
            ]
            df = pd.DataFrame(columns=columns)
            df.to_csv(self.metadata_csv_path, index=False)

    def load_transactions(self) -> pd.DataFrame:
        """Loads transaction data from the CSV file.
        Includes type casting for robust data handling and fills NaN values.
        """
        try:
            # Define a dictionary for column types to ensure consistency
            column_types = {
                'TransactionID': str,
                'SplitIndex': int,
                'Date': str,  # Read as string and parse later if needed
                'Time': str,
                'Payer/Payee': str,
                'Account': str,
                'Description': str,
                'Amount': float,
                'Currency': str,
                'BudgetScope': str,
                'Category': str,
                'SubCategory': str,
                'BudgetPath': str,  # NEW: BudgetPath
                'TransactionType': str,
                'RelatedTransactionID': str,  # NEW: RelatedTransactionID
                'RelatedDebtAccount': str,
                'RelatedSavingsAccount': str,
                'IsSubscription': bool,
                'SubscriptionAutoIdentified': bool,
                'InputSource': str,
                'FilePath': str,
                'LLMConfidence': float,
                'IsVerified': bool,
                'Notes': str,
                'TimestampAdded': str  # Read as string and parse later if needed
            }

            df = pd.read_csv(self.transactions_csv_path, dtype=column_types)

            # Ensure all expected columns are present, add if missing with default values
            for col, d_type in column_types.items():
                if col not in df.columns:
                    print(f"Column '{col}' not found in transactions CSV. Adding with default values.")
                    if d_type == str:
                        df[col] = ''
                    elif d_type == int:
                        df[col] = 0
                    elif d_type == float:
                        df[col] = 0.0
                    elif d_type == bool:
                        df[col] = False

            # Convert date columns using errors='coerce' to turn unparseable dates into NaT
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
            df['TimestampAdded'] = pd.to_datetime(df['TimestampAdded'], errors='coerce')

            # Fill NaN values after type conversion for consistency
            for col in ['Time', 'Payer/Payee', 'Account', 'Description', 'Currency', 'BudgetScope', 'Category',
                        'SubCategory', 'BudgetPath', 'TransactionType', 'RelatedTransactionID',
                        'RelatedDebtAccount', 'RelatedSavingsAccount', 'InputSource', 'FilePath', 'Notes']:
                if col in df.columns:
                    df[col] = df[col].fillna('')

            for col in ['IsSubscription', 'SubscriptionAutoIdentified', 'IsVerified']:
                if col in df.columns:
                    df[col] = df[col].fillna(False)

            # Fill NaT for date/datetime columns to prevent errors in operations
            df['Date'] = df['Date'].apply(lambda x: x if pd.notna(x) else None)
            df['TimestampAdded'] = df['TimestampAdded'].apply(lambda x: x if pd.notna(x) else None)

            return df
        except pd.errors.EmptyDataError:
            print(f"Transactions CSV is empty. Returning empty DataFrame with headers.")
            self._ensure_transactions_csv_exists()  # Re-ensure headers if empty
            return pd.DataFrame(columns=list(column_types.keys()))  # Return a new DataFrame with all expected columns
        except Exception as e:
            print(f"Error loading transactions CSV: {e}")
            raise

    def save_transactions(self, df: pd.DataFrame):
        """Saves transaction data to the CSV file."""
        # Convert datetime.date objects in 'Date' column to string for saving
        # and datetime objects in 'TimestampAdded' to string
        df['Date'] = df['Date'].apply(lambda x: x.isoformat() if x is not None else '')
        df['TimestampAdded'] = df['TimestampAdded'].apply(lambda x: x.isoformat() if x is not None else '')

        try:
            df.to_csv(self.transactions_csv_path, index=False)
            print(f"Transactions saved to {self.transactions_csv_path}")
        except Exception as e:
            print(f"Error saving transactions CSV: {e}")
            raise

    def load_payees(self) -> pd.DataFrame:
        """Loads payee data from the CSV file."""
        try:
            payee_column_types = {
                'Name': str,
                'Aliases': str,
                'DefaultCategory': str,
                'DefaultSubCategory': str,
                'DefaultAccount': str,
                'DefaultTransactionType': str,
                'RelatedDebtAccount': str,
                'RelatedSavingsAccount': str,
                'IsSubscription': bool,
                'Notes': str,
                'LastUpdated': str  # Read as string and parse later
            }
            df = pd.read_csv(self.payees_csv_path, dtype=payee_column_types)

            # Ensure all expected columns are present, add if missing with default values
            for col, d_type in payee_column_types.items():
                if col not in df.columns:
                    print(f"Column '{col}' not found in payees CSV. Adding with default values.")
                    if d_type == str:
                        df[col] = ''
                    elif d_type == bool:
                        df[col] = False

            df['LastUpdated'] = pd.to_datetime(df['LastUpdated'], errors='coerce')

            for col in ['Name', 'Aliases', 'DefaultCategory', 'DefaultSubCategory',
                        'DefaultAccount', 'DefaultTransactionType', 'RelatedDebtAccount',
                        'RelatedSavingsAccount', 'Notes']:
                if col in df.columns:
                    df[col] = df[col].fillna('')

            if 'IsSubscription' in df.columns:
                df['IsSubscription'] = df['IsSubscription'].fillna(False)

            df['LastUpdated'] = df['LastUpdated'].apply(lambda x: x if pd.notna(x) else None)

            return df
        except pd.errors.EmptyDataError:
            print(f"Payees CSV is empty. Returning empty DataFrame.")
            self._ensure_payees_csv_exists()
            return pd.DataFrame(columns=list(payee_column_types.keys()))
        except Exception as e:
            print(f"Error loading payees CSV: {e}")
            raise

    def save_payees(self, df: pd.DataFrame):
        """Saves payee data to the CSV file."""
        # Ensure 'LastUpdated' column is always up-to-date and in string format
        if 'LastUpdated' in df.columns:
            df['LastUpdated'] = datetime.datetime.now().isoformat()
        else:
            df['LastUpdated'] = datetime.datetime.now().isoformat()

        try:
            df.to_csv(self.payees_csv_path, index=False)
            print(f"Payees saved to {self.payees_csv_path}")
        except Exception as e:
            print(f"Error saving payees CSV: {e}")
            raise

    def load_metadata(self) -> pd.DataFrame:  # NEW METHOD
        """Loads metadata from the CSV file."""
        try:
            metadata_column_types = {
                "MetadataID": str,
                "TransactionID": str,
                "SplitIndex": int,
                "Key": str,
                "Value": str,
                "Source": str,
                "TimestampAdded": str
            }
            df = pd.read_csv(self.metadata_csv_path, dtype=metadata_column_types)
            for col, d_type in metadata_column_types.items():
                if col not in df.columns:
                    print(f"Column '{col}' not found in metadata CSV. Adding with default values.")
                    df[col] = '' if d_type == str else (0 if d_type == int else '')  # int for SplitIndex
            df['TimestampAdded'] = pd.to_datetime(df['TimestampAdded'], errors='coerce')
            df['TimestampAdded'] = df['TimestampAdded'].apply(lambda x: x if pd.notna(x) else None)
            for col in ['TransactionID', 'Key', 'Value', 'Source']:
                if col in df.columns: df[col] = df[col].fillna('')
            return df
        except pd.errors.EmptyDataError:
            print(f"Metadata CSV is empty. Returning empty DataFrame.")
            self._ensure_metadata_csv_exists()
            return pd.DataFrame(columns=list(metadata_column_types.keys()))
        except Exception as e:
            print(f"Error loading metadata CSV: {e}")
            raise

    def save_metadata(self, df: pd.DataFrame):  # NEW METHOD
        """Saves metadata to the CSV file."""
        df['TimestampAdded'] = df['TimestampAdded'].apply(lambda x: x.isoformat() if x is not None else '')
        try:
            df.to_csv(self.metadata_csv_path, index=False)
            print(f"Metadata saved to {self.metadata_csv_path}")
        except Exception as e:
            print(f"Error saving metadata CSV: {e}")
            raise
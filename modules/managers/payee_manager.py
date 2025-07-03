# modules/managers/payee_manager.py
import uuid
from typing import Optional

import pandas as pd
import datetime
from .csv_manager import CSVManager  # Import CSVManager


class PayeeManager:
    def __init__(self, csv_manager: CSVManager):
        """
        Initializes the PayeeManager.
        Args:
            csv_manager (CSVManager): An instance of CSVManager to handle data I/O.
        """
        self.csv_manager = csv_manager
        self._payees_df = self._load_payees_from_csv()
        self._unique_payee_names = sorted(self._payees_df['Name'].tolist())

    def _load_payees_from_csv(self) -> pd.DataFrame:
        """
        Loads payee data from the CSV using CSVManager.
        """
        return self.csv_manager.load_payees()

    def get_all_payee_names(self) -> list[str]:
        """
        Returns a sorted list of all unique payee names currently known.
        """
        return self._unique_payee_names

    def get_payee_name_by_id(self, payee_id: str) -> Optional[str]:
        """
        Retrieves the payee name given its UUID.
        Returns None if the payee ID is not found.
        """
        if self._payees_df.empty:
            return None

        result = self._payees_df[self._payees_df['PayeeId'] == payee_id]
        if not result.empty:
            return result['Name'].iloc[0]
        return None

    def add_payee(self, new_payee_name: str, is_subscription: bool = False, notes: str = ""):
        """
        Adds a new payee to the internal DataFrame and persists it to CSV if it's not already present
        and not identified as an internal account.
        """
        # TODO: save and extract from databases.
        if not new_payee_name:
            print("Attempted to add empty payee name. Skipping.")
            return

        # Heuristic to check if payee_name is likely an internal account for transfers
        # This will need to be refined based on your actual account naming conventions
        # For example, if your accounts are always in ALL_CAPS or contain specific prefixes
        internal_account_keywords = [
            "Transfer to", "Transfer from", "deposit to", "withdrawal from",
            "from", "to"
        ]

        # Get current account names from transactions (might be slow if transactions.csv is huge)
        # Consider caching account names or passing them from FinanceConfigManager if available
        current_accounts_df = self.csv_manager.load_transactions()
        existing_account_names = current_accounts_df['Account'].dropna().unique().tolist()

        is_internal_account_payee = any(
            keyword.lower() in new_payee_name.lower() for keyword in internal_account_keywords
        ) or (new_payee_name in existing_account_names)

        if is_internal_account_payee:
            print(f"'{new_payee_name}' identified as internal account payee. Not saving to payees.csv.")
            return

        if new_payee_name not in self._payees_df['Name'].values:
            payee_id = f"PRN-{int(datetime.datetime.now().timestamp())}-{uuid.uuid4().hex[:6].upper()}"
            print(f"Adding new payee: {new_payee_name}")
            new_payee_data = {
                "PayeeId": payee_id,
                "Name": new_payee_name,
                "Aliases": "",
                "DefaultCategory": "",
                "DefaultSubCategory": "",
                "DefaultAccount": "",
                "DefaultTransactionType": "",
                "RelatedDebtAccount": "",
                "RelatedSavingsAccount": "",
                "IsSubscription": is_subscription,
                "Notes": notes,
                "LastUpdated": datetime.datetime.now().isoformat()
            }
            # Append new payee to the DataFrame
            new_df_row = pd.DataFrame([new_payee_data])
            self._payees_df = pd.concat([self._payees_df, new_df_row], ignore_index=True)

            # Update the in-memory list of unique payee names
            self._unique_payee_names.append(new_payee_name)
            self._unique_payee_names.sort()

            # Persist the updated DataFrame to CSV
            self.csv_manager.save_payees(self._payees_df)
        else:
            print(f"Payee '{new_payee_name}' already exists. Not adding.")
            payee_id = self._payees_df.loc[self._payees_df['Name'] == new_payee_name]['PayeeId'].values[0]

        return payee_id # GET the uuid and return it.
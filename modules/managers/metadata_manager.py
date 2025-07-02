# modules/managers/metadata_manager.py

import pandas as pd
import datetime
import uuid
from typing import Dict, Any, List, Optional
from .csv_manager import CSVManager


class MetadataManager:
    """
    Manages additional metadata associated with transactions or splits.
    This data is stored in metadata.csv and can include taxes, loyalty info,
    change due, or any other dynamic key-value pairs.
    """

    def __init__(self, csv_manager: CSVManager):
        """
        Initializes the MetadataManager.
        Args:
            csv_manager (CSVManager): An instance of CSVManager to handle data I/O for metadata.csv.
        """
        self.csv_manager = csv_manager
        self._metadata_df = self._load_metadata_from_csv()

    def _load_metadata_from_csv(self) -> pd.DataFrame:
        """Loads metadata from the CSV using CSVManager."""
        return self.csv_manager.load_metadata()

    def get_metadata_for_transaction(self, transaction_id: str, split_index: Optional[int] = None) -> List[
        Dict[str, str]]:
        """
        Retrieves all metadata entries for a given transaction ID, optionally filtered by split index.
        Returns a list of dictionaries with 'Key', 'Value', and 'Source'.
        """
        filtered_df = self._metadata_df[self._metadata_df['TransactionID'] == transaction_id]
        if split_index is not None:
            filtered_df = filtered_df[filtered_df['SplitIndex'] == split_index]

        return filtered_df[['Key', 'Value', 'Source']].to_dict(orient='records')

    def add_metadata_entries(self,
                             transaction_id: str,
                             metadata_entries: List[Dict[str, Any]],
                             source: str = "Manual",
                             split_index: int = -1  # -1 for transaction-level metadata, specific index for split-level
                             ):
        """
        Adds multiple metadata entries associated with a transaction or a specific split.

        Args:
            transaction_id (str): The ID of the transaction this metadata belongs to.
            metadata_entries (List[Dict[str, Any]]): A list of dictionaries, each containing
                                                     'key', 'value', and optional 'source'.
            source (str): The default source if not specified in individual entries.
            split_index (int): The split index this metadata applies to. Use -1 for transaction-level.
        """
        new_records = []
        current_timestamp = datetime.datetime.now().isoformat()

        for entry in metadata_entries:
            # Ensure key and value are present
            if 'key' not in entry or 'value' not in entry:
                print(f"Skipping malformed metadata entry: {entry}")
                continue

            new_records.append({
                "MetadataID": str(uuid.uuid4()),
                "TransactionID": transaction_id,
                "SplitIndex": split_index,
                "Key": entry['key'],
                "Value": str(entry['value']),  # Ensure value is string for CSV
                "Source": entry.get('source', source),
                "TimestampAdded": current_timestamp
            })

        if new_records:
            new_df = pd.DataFrame(new_records)
            self._metadata_df = pd.concat([self._metadata_df, new_df], ignore_index=True)
            self.csv_manager.save_metadata(self._metadata_df)
            print(
                f"Added {len(new_records)} metadata entries for TransactionID: {transaction_id}, SplitIndex: {split_index}")
        else:
            print("No valid metadata entries to add.")

    def delete_metadata_entry(self, metadata_id: str):
        """Deletes a metadata entry by its MetadataID."""
        initial_len = len(self._metadata_df)
        self._metadata_df = self._metadata_df[self._metadata_df['MetadataID'] != metadata_id].reset_index(drop=True)
        if len(self._metadata_df) < initial_len:
            self.csv_manager.save_metadata(self._metadata_df)
            print(f"Metadata ID {metadata_id} deleted.")
        else:
            print(f"Metadata ID {metadata_id} not found.")

    def delete_metadata_for_transaction(self, transaction_id: str):
        """
        Deletes all metadata entries associated with a given TransactionID.
        """
        initial_len = len(self._metadata_df)
        self._metadata_df = self._metadata_df[self._metadata_df['TransactionID'] != transaction_id].reset_index(
            drop=True)
        if len(self._metadata_df) < initial_len:
            self.csv_manager.save_metadata(self._metadata_df)
            print(f"All metadata for Transaction {transaction_id} deleted.")
        else:
            print(f"No metadata found for Transaction {transaction_id} to delete.")

    def delete_metadata_for_transaction_split(self, transaction_id: str, split_index: int):
        """
        Deletes metadata entries for a specific transaction split.
        """
        initial_len = len(self._metadata_df)
        self._metadata_df = self._metadata_df[
            ~((self._metadata_df['TransactionID'] == transaction_id) & (self._metadata_df['SplitIndex'] == split_index))
        ].reset_index(drop=True)

        if len(self._metadata_df) < initial_len:
            self.csv_manager.save_metadata(self._metadata_df)
            print(f"Metadata for Transaction {transaction_id} Split {split_index} deleted.")
        else:
            print(f"No metadata found for Transaction {transaction_id} Split {split_index} to delete.")

    def update_metadata_entry(self, metadata_id: str, new_value: Any):
        """Updates the value of an existing metadata entry by its MetadataID."""
        idx = self._metadata_df[self._metadata_df['MetadataID'] == metadata_id].index
        if not idx.empty:
            self._metadata_df.loc[idx, 'Value'] = str(new_value)
            self._metadata_df.loc[idx, 'TimestampAdded'] = datetime.datetime.now().isoformat()
            self.csv_manager.save_metadata(self._metadata_df)
            print(f"Metadata ID {metadata_id} updated.")
        else:
            print(f"Metadata ID {metadata_id} not found.")

    def delete_metadata_entry(self, metadata_id: str):
        """Deletes a metadata entry by its MetadataID."""
        initial_len = len(self._metadata_df)
        self._metadata_df = self._metadata_df[self._metadata_df['MetadataID'] != metadata_id].reset_index(drop=True)
        if len(self._metadata_df) < initial_len:
            self.csv_manager.save_metadata(self._metadata_df)
            print(f"Metadata ID {metadata_id} deleted.")
        else:
            print(f"Metadata ID {metadata_id} not found.")

    def get_all_unique_metadata_keys(self) -> List[str]:
        """
        Retrieves all unique metadata keys from the metadata.csv file.
        This function is cached to avoid re-reading the CSV on every rerun.
        """
        if not self._metadata_df.empty and 'Key' in self._metadata_df.columns:
            return sorted(self._metadata_df['Key'].dropna().unique().tolist())
        return []

    def get_all_metadata(self) -> pd.DataFrame:
        """
        Retrieves all metadata entries.
        Returns:
            pd.DataFrame: A DataFrame containing all metadata.
        """
        return self._metadata_df.copy()
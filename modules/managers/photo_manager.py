# modules/managers/photo_manager.py

"""
Purpose: This file defines the PhotoManager class, which is responsible for
managing the storage and retrieval of image files (e.g., invoices, receipts)
associated with transactions. It handles saving uploaded files to a designated
directory, recording their paths in photo_references.csv, and retrieving/deleting
them as needed.

Interactions:
- Initialized by `app.py` or `pages/1_Add_Transaction.py` (via `get_managers`)
  with instances of `CSVManager` and `AppConfigManager`.
- Used by `TransactionManager` to save, retrieve, and delete image file paths
  when processing invoices or managing transaction attachments.
"""

import os
import uuid
import datetime
import pandas as pd
from typing import List, Optional, Any, Dict

# Assuming these imports based on typical Streamlit UploadedFile structure
# If 'st' is not available in this context, the type hint can be kept,
# but file handling will rely on standard file operations.
# from streamlit.runtime.uploaded_file_manager import UploadedFile

# Local imports for managers
from .csv_manager import CSVManager
from .app_config_manager import AppConfigManager


class PhotoManager:
    """
    Manages the storage, retrieval, and deletion of photo files related to transactions.
    It uses CSVManager for metadata persistence and AppConfigManager for directory paths.
    """

    def __init__(self, csv_manager: CSVManager, photo_storage_dir: str = 'invoices_input_dir'):
        """
        Initializes the PhotoManager.

        Args:
            csv_manager (CSVManager): An instance of CSVManager to handle photo reference CSV I/O.
            app_config_manager (AppConfigManager): An instance of AppConfigManager to get file storage paths.
        """
        self.csv_manager = csv_manager
        # Use the existing 'invoices_input_dir' for storing photos as per requirement.
        self.photo_storage_dir = photo_storage_dir

        os.makedirs(self.photo_storage_dir, exist_ok=True)
        self._photo_references_df = self.csv_manager.load_photo_references()

    def _generate_unique_filename(self, original_filename: str) -> str:
        """Generates a unique filename using UUID and preserves the original file extension."""
        ext = os.path.splitext(original_filename)[1]
        unique_id = uuid.uuid4().hex[:12].upper()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"invoice_{timestamp}_{unique_id}{ext}"

    def save_photos_for_transaction(self, transaction_id: str, uploaded_files: List[Any]) -> List[str]:
        """
        Saves a list of uploaded file objects to disk and records their paths.

        Args:
            transaction_id (str): The ID of the transaction to associate photos with.
            uploaded_files (List[Any]): A list of file-like objects (e.g., Streamlit UploadedFile).
                                        Each object must have a 'name' and a 'read()' method.

        Returns:
            List[str]: A list of full file paths where the photos were saved.
        """
        saved_file_paths = []
        new_photo_references = []

        for uploaded_file in uploaded_files:
            if uploaded_file is None:
                continue

            unique_filename = self._generate_unique_filename(uploaded_file.name)
            file_path = os.path.join(self.photo_storage_dir, unique_filename)

            try:
                # Write the uploaded file content to the new path
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.read())
                saved_file_paths.append(file_path)

                # Prepare data for photo_references.csv
                photo_ref_id = f"PHR-{int(datetime.datetime.now().timestamp())}-{uuid.uuid4().hex[:6].upper()}"
                new_photo_references.append({
                    "PhotoReferenceID": photo_ref_id,
                    "TransactionID": transaction_id,
                    "FilePath": file_path,
                    "TimestampAdded": datetime.datetime.now().isoformat()
                })
                print(f"Saved photo: {file_path}")
            except Exception as e:
                print(f"Error saving file {uploaded_file.name}: {e}")
                # Decide on error handling: continue or raise
                continue # Continue to try saving other files

        if new_photo_references:
            new_df = pd.DataFrame(new_photo_references)
            self._photo_references_df = pd.concat([self._photo_references_df, new_df], ignore_index=True)
            self.csv_manager.save_photo_references(self._photo_references_df)
            print(f"Recorded {len(new_photo_references)} photo references for transaction {transaction_id}")

        return saved_file_paths

    def get_photos_for_transaction(self, transaction_id: str) -> List[str]:
        """
        Retrieves all associated file paths for a given transaction ID from the photo references.

        Args:
            transaction_id (str): The ID of the transaction.

        Returns:
            List[str]: A list of full file paths associated with the transaction.
        """
        # Reload to ensure freshest data in case other processes modified it
        self._photo_references_df = self.csv_manager.load_photo_references()
        filtered_df = self._photo_references_df[
            self._photo_references_df['TransactionID'] == transaction_id
        ]
        # Filter out paths that might no longer exist on disk (e.g., manually deleted)
        existing_paths = [
            path for path in filtered_df['FilePath'].tolist() if os.path.exists(path)
        ]
        return existing_paths

    def delete_photos_for_transaction(self, transaction_id: str):
        """
        Deletes all photos associated with a given transaction ID from disk
        and removes their entries from the photo references CSV.

        Args:
            transaction_id (str): The ID of the transaction whose photos are to be deleted.
        """
        # Get paths associated with the transaction
        photo_paths_to_delete = self.get_photos_for_transaction(transaction_id)

        # Delete physical files
        for file_path in photo_paths_to_delete:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"Deleted photo file: {file_path}")
                else:
                    print(f"Photo file not found (already deleted?): {file_path}")
            except OSError as e:
                print(f"Error deleting file {file_path}: {e}")

        # Remove entries from DataFrame and save
        initial_len = len(self._photo_references_df)
        self._photo_references_df = self._photo_references_df[
            self._photo_references_df['TransactionID'] != transaction_id
        ].reset_index(drop=True)

        if len(self._photo_references_df) < initial_len:
            self.csv_manager.save_photo_references(self._photo_references_df)
            print(f"Removed photo references for transaction {transaction_id} from CSV.")
        else:
            print(f"No photo references found for transaction {transaction_id} to delete from CSV.")
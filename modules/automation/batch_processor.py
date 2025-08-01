# modules/automation/batch_processor.py

import streamlit as st
from typing import List, Dict, Any, Optional
from modules.managers.transaction_manager import TransactionManager

def process_uploaded_invoices_batch(
    uploaded_files: List[Any], # Streamlit uploaded file objects
    transaction_manager: TransactionManager
) -> List[Dict[str, Any]]:
    """
    Processes a batch of uploaded invoice files.
    For each file, it calls transaction_manager.process_uploaded_invoice
    and collects the results.
    """
    processed_results = []
    if not uploaded_files:
        return []

    for i, uploaded_file in enumerate(uploaded_files):
        try:
            st.info(f"Processing file {i+1}/{len(uploaded_files)}: {uploaded_file.name}...")
            # transaction_manager.process_uploaded_invoice expects a single file object
            result = transaction_manager.process_uploaded_invoice(uploaded_file)
            processed_results.append(result)
            st.success(f"Successfully processed {uploaded_file.name}.")
        except Exception as e:
            st.error(f"Failed to process {uploaded_file.name}: {e}")
            # You might want to log this error more formally
    return processed_results
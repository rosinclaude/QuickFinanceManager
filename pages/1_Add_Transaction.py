# pages/1_Add_Transaction.py

import streamlit as st
import datetime
from modules.managers.csv_manager import CSVManager
from modules.managers.payee_manager import PayeeManager
from modules.managers.transaction_manager import TransactionManager
from modules.managers.finance_config_manager import MonthlyFinanceConfigManager
from modules.managers.app_config_manager import AppConfigManager
from modules.managers.metadata_manager import MetadataManager
from modules.ui_tabs.manual_entry_tab import display_single_transaction_tab  # Renamed function
from modules.automation.batch_processor import process_uploaded_invoices_batch  # NEW: For batch processing

# --- Page Configuration ---
st.set_page_config(
    page_title="Add Transaction",
    page_icon="💸",
    layout="centered"
)

st.title("Add a New Transaction")
st.write("Use the tabs below to add transactions manually, from an invoice, or by importing a bank statement.")


# --- Manager Retrieval (UPDATED) ---
# Check if managers are already in session state
if 'managers' not in st.session_state:
    st.error("Application managers not initialized. Please run the main app.py first.")
    st.stop() # Stop execution if managers are not found

# Retrieve managers from session state
managers = st.session_state.managers
transaction_manager = managers["transaction_manager"]
monthly_finance_config_manager = managers["monthly_finance_config_manager"]
payee_manager = managers["payee_manager"]
app_config_manager = managers["app_config_manager"]


# --- Display Budget Validation Messages ---
validation_messages = monthly_finance_config_manager.get_validation_messages()
if validation_messages:
    st.subheader("Budget Configuration Alerts")
    for msg in validation_messages:
        msg_type = msg.get('type')
        msg_content = msg.get('message')
        if msg_type == 'alarm':
            st.error(msg_content, icon="🚨")
        elif msg_type == 'warning':
            st.warning(msg_content, icon="⚠️")
        elif msg_type == 'note':
            st.info(msg_content, icon="💡")

# --- Tab-based UI ---
tab_single_entry, tab_batch_processing, tab_statement_entry = st.tabs(
    ["Add Single Transaction", "Batch Process Invoices", "From Bank Statement"])

with tab_single_entry:
    # This tab now handles both manual and invoice-assisted entry
    display_single_transaction_tab(transaction_manager, monthly_finance_config_manager, app_config_manager)

with tab_batch_processing:
    st.header("Batch Process Invoices")
    st.write("Upload multiple invoices here to process them in the background. You can review them later.")

    uploaded_batch_files = st.file_uploader(
        "Upload Multiple Image or PDF Invoices",
        type=['png', 'jpg', 'jpeg', 'pdf'],
        accept_multiple_files=True,
        key="batch_invoice_uploader"
    )

    if uploaded_batch_files:
        if st.button("Process Batch Invoices", key="process_batch_btn"):
            with st.spinner("Processing batch invoices... This may take a while."):
                # Assuming process_uploaded_invoices_batch can handle a list of file objects
                # or you'll modify it to iterate and call transaction_manager.process_uploaded_invoice for each
                processed_results = process_uploaded_invoices_batch(
                    uploaded_batch_files,
                    transaction_manager  # Pass transaction_manager for processing
                )

            if processed_results:
                st.success(f"Successfully processed {len(processed_results)} invoices in batch.")
                st.session_state['batch_processed_invoices'] = processed_results
                # Optionally, display a summary or link to a review page
                st.json(processed_results)  # For debugging, remove in production
            else:
                st.warning("No invoices were successfully processed in the batch.")

    # Placeholder for review UI (future work)
    if 'batch_processed_invoices' in st.session_state and st.session_state['batch_processed_invoices']:
        st.subheader("Review Processed Batch Invoices (Coming Soon!)")
        # Here you would typically loop through st.session_state['batch_processed_invoices']
        # and allow the user to review and individually save or reject them.

with tab_statement_entry:
    st.header("Import a Bank Statement")
    st.info("This feature is coming soon! Bank statements will be parsed and matched with existing transactions.")
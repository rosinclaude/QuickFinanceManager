# pages/2_View_Transactions.py

import streamlit as st
import pandas as pd
import datetime
from typing import Dict, Any, List, Optional, Set

# Import managers
# Ensure these imports match the actual structure of your project
from modules.managers.csv_manager import CSVManager
from modules.managers.payee_manager import PayeeManager
from modules.managers.transaction_manager import TransactionManager
from modules.managers.finance_config_manager import MonthlyFinanceConfigManager
from modules.managers.app_config_manager import AppConfigManager
from modules.managers.metadata_manager import MetadataManager

# --- Page Configuration ---
st.set_page_config(
    page_title="View Transactions",
    page_icon="📊",
    layout="wide"
)

st.title("View and Manage Transactions")
st.write("Review, filter, and edit your financial transactions.")

# --- Manager Initialization (Retrieve from session state) ---
if 'managers' not in st.session_state:
    st.error("Managers not found in session state. Please ensure you start the application from the main page (app.py) where managers are initialized.")
    st.stop() # Stop execution if managers are not available

managers = st.session_state.managers
transaction_manager: TransactionManager = managers["transaction_manager"]
monthly_finance_config_manager: MonthlyFinanceConfigManager = managers["monthly_finance_config_manager"]
payee_manager: PayeeManager = managers["payee_manager"]
app_config_manager: AppConfigManager = managers["app_config_manager"]
csv_manager: CSVManager = managers["csv_manager"]
metadata_manager: MetadataManager = managers["metadata_manager"]

# --- Session State Initialization for UI elements ---
if 'transactions_df_display' not in st.session_state:
    st.session_state.transactions_df_display = pd.DataFrame()
if 'transactions_df_original_loaded' not in st.session_state:
    st.session_state.transactions_df_original_loaded = pd.DataFrame() # To store original state of loaded data before filtering
if 'current_month' not in st.session_state:
    st.session_state.current_month = datetime.date.today().month
if 'current_year' not in st.session_state:
    st.session_state.current_year = datetime.date.today().year
if 'editing_enabled' not in st.session_state:
    st.session_state.editing_enabled = False
if 'selected_payees' not in st.session_state:
    st.session_state.selected_payees = []
if 'selected_accounts' not in st.session_state:
    st.session_state.selected_accounts = []
if 'selected_transaction_types' not in st.session_state:
    st.session_state.selected_transaction_types = []
if 'selected_budget_paths' not in st.session_state:
    st.session_state.selected_budget_paths = []
if 'search_term' not in st.session_state:
    st.session_state.search_term = ""

# --- Helper Functions ---

def _data_editor_on_change_callback():
    """A dummy callback for st.data_editor to force a rerun and update session state,
    especially for selection changes."""
    pass

def _load_base_transactions_for_period():
    """Loads transactions for the selected month/year into original_loaded, without applying filters."""
    with st.spinner(f"Loading transactions for {datetime.date(st.session_state.current_year, st.session_state.current_month, 1).strftime('%B %Y')}..."):
        df = transaction_manager.get_transactions_by_month_year(
            st.session_state.current_month,
            st.session_state.current_year,
            include_payee_names=True
        )

        if df.empty:
            st.session_state.transactions_df_original_loaded = pd.DataFrame(columns=[
                "TransactionID", "SplitIndex", "Date", "PayeeName", "Account",
                "TransactionType", "Amount", "Currency", "BudgetPath",
                "Description", "Notes", "InputSource", "FilePath", "IsVerified",
                "RelatedTransactionID", "LLMConfidence", "TimestampAdded"
            ])
            st.warning("No transactions found for the selected period.")
            return

        # Prepare for display, e.g., convert Date to date object
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        st.session_state.transactions_df_original_loaded = df.copy()

def _apply_filters_to_display_df():
    """Applies current filter selections to the loaded data and updates the display DataFrame."""
    if st.session_state.transactions_df_original_loaded.empty:
        st.session_state.transactions_df_display = pd.DataFrame()
        return

    filtered_df = st.session_state.transactions_df_original_loaded.copy()

    if st.session_state.selected_payees:
        filtered_df = filtered_df[filtered_df['PayeeName'].isin(st.session_state.selected_payees)]
    if st.session_state.selected_accounts:
        filtered_df = filtered_df[filtered_df['Account'].isin(st.session_state.selected_accounts)]
    if st.session_state.selected_transaction_types:
        filtered_df = filtered_df[filtered_df['TransactionType'].isin(st.session_state.selected_transaction_types)]
    if st.session_state.selected_budget_paths:
        filtered_df = filtered_df[filtered_df['BudgetPath'].isin(st.session_state.selected_budget_paths)]
    if st.session_state.search_term:
        search_lower = st.session_state.search_term.lower()
        filtered_df = filtered_df[
            filtered_df['Description'].fillna('').str.lower().str.contains(search_lower) |
            filtered_df['Notes'].fillna('').str.lower().str.contains(search_lower)
        ]

    if filtered_df.empty and not st.session_state.transactions_df_original_loaded.empty:
        st.warning("No transactions match the selected filters.")
        st.session_state.transactions_df_display = pd.DataFrame()
    else:
        display_columns = [
            "TransactionID", "SplitIndex", "Date", "PayeeName", "Account",
            "TransactionType", "Amount", "Currency", "BudgetPath",
            "Description", "Notes", "InputSource", "FilePath", "IsVerified",
            "RelatedTransactionID", "LLMConfidence", "TimestampAdded"
        ]
        # Ensure all columns expected by the editor are present
        for col in display_columns:
            if col not in filtered_df.columns:
                filtered_df[col] = '' if filtered_df.empty else None # Set default if column is missing

        st.session_state.transactions_df_display = filtered_df[display_columns].copy()


def apply_changes_to_transactions(edited_data: Dict[str, Dict[str, Any]], deleted_rows: List[int], added_rows: List[Dict[str, Any]]):
    """
    Applies changes from the data editor to the underlying transactions,
    calling update_transaction for modified rows and delete_transaction for deleted rows.
    """
    success_count = 0
    fail_count = 0

    # --- Step 1: Handle Deletions ---
    if deleted_rows:
        st.subheader("Processing Deletions...")
        deleted_transaction_ids = set()
        # Collect unique TransactionIDs to delete, as deleting any split deletes the whole transaction
        for idx in deleted_rows:
            if idx < len(st.session_state.transactions_df_display): # Ensure index is valid
                transaction_id_to_delete = st.session_state.transactions_df_display.loc[idx, 'TransactionID']
                deleted_transaction_ids.add(transaction_id_to_delete)
            else:
                st.error(f"Attempted to delete invalid row index: {idx}")

        for txn_id in deleted_transaction_ids:
            try:
                if transaction_manager.delete_transaction(txn_id):
                    st.success(f"Deleted TransactionID: {txn_id}")
                    success_count += 1
                else:
                    st.error(f"Failed to delete TransactionID: {txn_id}")
                    fail_count += 1
            except Exception as e:
                st.error(f"Error deleting TransactionID {txn_id}: {e}")
                fail_count += 1
        st.info(f"Deletion Summary: {success_count} successful, {fail_count} failed.")

    # --- Step 2: Handle Edits ---
    if edited_data:
        st.subheader("Processing Edits...")
        # Get unique TransactionIDs that were affected by edits
        edited_transaction_ids = set(st.session_state.transactions_df_display.loc[list(edited_data.keys()), 'TransactionID'].tolist())

        edit_success_count = 0
        edit_fail_count = 0

        for txn_id in edited_transaction_ids:
            try:
                # Get all original splits for this transaction_id from the *loaded* dataframe (before any edits)
                original_splits_for_txn_df = st.session_state.transactions_df_original_loaded[
                    st.session_state.transactions_df_original_loaded['TransactionID'] == txn_id
                ].copy()
                original_splits_for_txn = original_splits_for_txn_df.to_dict(orient='records')


                # Determine the main transaction fields (Date, PayeeName, Account, Type, Notes, etc.)
                # These should be consistent across all splits of a transaction.
                # Prioritize edited values if present, otherwise use original.
                _date = original_splits_for_txn[0]['Date'] if original_splits_for_txn else None
                _payee_name = original_splits_for_txn[0]['PayeeName'] if original_splits_for_txn else None
                _account = original_splits_for_txn[0]['Account'] if original_splits_for_txn else None
                _transaction_type = original_splits_for_txn[0]['TransactionType'] if original_splits_for_txn else None
                _notes = original_splits_for_txn[0]['Notes'] if original_splits_for_txn else None
                _file_path = original_splits_for_txn[0]['FilePath'] if 'FilePath' in original_splits_for_txn[0] else None
                _related_transaction_id = original_splits_for_txn[0]['RelatedTransactionID'] if 'RelatedTransactionID' in original_splits_for_txn[0] else None

                # Fetch metadata for the transaction (not split-specific for now)
                _metadata = metadata_manager.get_metadata_for_transaction(txn_id, split_index=-1)


                updated_splits_list_for_txn = []
                for split_record in original_splits_for_txn:
                    # Check if this specific split (identified by TransactionID and SplitIndex) was edited
                    found_edit_for_split = False
                    for edited_idx, changes in edited_data.items():
                        current_row_in_editor = st.session_state.transactions_df_display.loc[edited_idx]
                        if current_row_in_editor['TransactionID'] == split_record['TransactionID'] and \
                           current_row_in_editor['SplitIndex'] == split_record['SplitIndex']:
                            # Apply changes from data_editor to this specific split record
                            # Update main transaction fields if they were edited on this row
                            if 'Date' in changes: _date = changes['Date']
                            if 'PayeeName' in changes: _payee_name = changes['PayeeName']
                            if 'Account' in changes: _account = changes['Account']
                            if 'TransactionType' in changes: _transaction_type = changes['TransactionType']
                            if 'Notes' in changes: _notes = changes['Notes'] # Main notes updated by any split's notes edit for now

                            # Update split-specific fields
                            if 'Amount' in changes: split_record['Amount'] = changes['Amount']
                            if 'BudgetPath' in changes:
                                split_record['BudgetPath'] = changes['BudgetPath']
                                parts = changes['BudgetPath'].split('::')
                                split_record['BudgetScope'] = parts[0] if len(parts) > 0 else ''
                                split_record['Category'] = parts[1] if len(parts) > 1 else ''
                                split_record['SubCategory'] = parts[2] if len(parts) > 2 else ''
                            if 'Description' in changes: split_record['Description'] = changes['Description']
                            # If Notes can be split-specific, changes['Notes'] here would be specific to split.
                            # For simplicity, if Notes column is edited, it updates the main transaction notes.
                            # If split-specific notes are needed, a separate column in editor is required.

                            found_edit_for_split = True
                            break # Found and applied edit for this split_record

                    # After checking for edits, format the split for `update_transaction`
                    updated_splits_list_for_txn.append({
                        'description': split_record.get('Description', ''),
                        'notes': split_record.get('Notes', ''),
                        'amount': float(split_record.get('Amount', 0.0)),
                        'budget_scope': split_record.get('BudgetScope', ''),
                        'category': split_record.get('Category', ''),
                        'sub_category': split_record.get('SubCategory', ''),
                        'full_budget_path': split_record.get('BudgetPath', ''),
                        'payee': payee_manager.get_payee_name_by_id(split_record.get('Payer/Payee', '')), # Use PayeeName from the original_splits_for_txn_df (which is derived from Payer/Payee ID)
                        'account': split_record.get('Account', '')
                    })

                # Call update_transaction with the collected main fields and the fully updated splits list
                transaction_manager.update_transaction(
                    transaction_id=txn_id,
                    date=_date,
                    payee_name=_payee_name,
                    account=_account,
                    transaction_type=_transaction_type,
                    splits=updated_splits_list_for_txn,
                    notes=_notes,
                    file_path=_file_path,
                    metadata=_metadata,
                    related_transaction_id=_related_transaction_id
                )
                st.success(f"Updated TransactionID: {txn_id}")
                edit_success_count += 1

            except Exception as e:
                st.error(f"Failed to update TransactionID {txn_id}: {e}")
                edit_fail_count += 1
        st.info(f"Edit Summary: {edit_success_count} successful, {edit_fail_count} failed.")

    # --- Step 3: Handle Additions (Discouraged for complex split transactions) ---
    if added_rows:
        st.subheader("Processing Additions (Not recommended here)")
        st.warning("Adding new rows directly via `st.data_editor` is not recommended for new transactions with multiple splits or complex logic. Please use the 'Add Transaction' page for new entries.")


    # After changes, reload base data and re-apply filters to refresh display
    _load_base_transactions_for_period()
    _apply_filters_to_display_df()
    st.session_state.editing_enabled = False # Disable editing after save

# --- Main Logic Flow ---

# Initial load of base data if not already loaded
if st.session_state.transactions_df_original_loaded.empty:
    _load_base_transactions_for_period()

# --- UI Layout ---

# Filters section
st.sidebar.header("Filter Transactions")
with st.sidebar.expander("Date Range & Load"):
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.current_month = st.selectbox(
            "Month",
            options=range(1, 13),
            index=st.session_state.current_month - 1,
            format_func=lambda x: datetime.date(1, x, 1).strftime('%B'),
            key="month_select"
        )
    with col2:
        current_year = datetime.date.today().year
        st.session_state.current_year = st.selectbox(
            "Year",
            options=range(current_year - 5, current_year + 2), # 5 years back, 1 year forward
            index=5, # Default to current year in the example range
            key="year_select"
        )
    if st.button("Load Transactions", key="load_transactions_btn_sidebar"):
        _load_base_transactions_for_period()
        # _apply_filters_to_display_df() will be called below as part of the normal rerun
        st.session_state.editing_enabled = False # Reset editing state

with st.sidebar.expander("Column Filters"):
    all_payees = payee_manager.get_all_payee_names()
    st.session_state.selected_payees = st.multiselect(
        "Filter by Payee",
        options=all_payees,
        default=st.session_state.selected_payees,
        # Removed on_change here; filtering happens automatically on re-run
        key="payee_filter"
    )

    all_accounts = monthly_finance_config_manager.get_all_account_names()
    st.session_state.selected_accounts = st.multiselect(
        "Filter by Account",
        options=all_accounts,
        default=st.session_state.selected_accounts,
        # Removed on_change here
        key="account_filter"
    )

    all_transaction_types = ["Expense", "Income", "Transfer"] # Fixed options
    st.session_state.selected_transaction_types = st.multiselect(
        "Filter by Type",
        options=all_transaction_types,
        default=st.session_state.selected_transaction_types,
        # Removed on_change here
        key="type_filter"
    )

    # Get all unique budget paths from the loaded data for filtering
    if not st.session_state.transactions_df_original_loaded.empty and 'BudgetPath' in st.session_state.transactions_df_original_loaded.columns:
        all_budget_paths = st.session_state.transactions_df_original_loaded['BudgetPath'].dropna().unique().tolist()
    else:
        all_budget_paths = []

    st.session_state.selected_budget_paths = st.multiselect(
        "Filter by Budget Path",
        options=sorted(all_budget_paths),
        default=st.session_state.selected_budget_paths,
        # Removed on_change here
        key="budget_path_filter"
    )

    st.session_state.search_term = st.text_input(
        "Search Description/Notes",
        value=st.session_state.search_term,
        # Removed on_change here
        key="search_input",
        placeholder="Type to search..."
    )

# Apply filters to the display DataFrame on every rerun, after filter widgets update session state
_apply_filters_to_display_df()


if not st.session_state.transactions_df_display.empty:
    st.subheader("Transactions Overview")

    # Toggle for editing
    edit_mode_toggle = st.toggle("Enable Editing", value=st.session_state.editing_enabled, key="enable_editing_toggle")
    st.session_state.editing_enabled = edit_mode_toggle

    # Define column configuration for st.data_editor
    # Dynamically set 'disabled' property for editable columns based on editing_enabled state
    column_config = {
        "TransactionID": st.column_config.Column("Transaction ID", help="Unique ID for the transaction", disabled=True),
        "SplitIndex": st.column_config.NumberColumn("Split Index", help="Index for transaction splits", disabled=True),
        "Date": st.column_config.DateColumn("Date", help="Transaction Date", format="YYYY-MM-DD", required=True, disabled=not st.session_state.editing_enabled),
        "PayeeName": st.column_config.TextColumn("Payee Name", help="Name of the payee/payer", required=True, disabled=not st.session_state.editing_enabled),
        "Account": st.column_config.TextColumn("Account", help="Account where transaction occurred", required=True, disabled=not st.session_state.editing_enabled),
        "TransactionType": st.column_config.SelectboxColumn(
            "Type",
            options=["Expense", "Income", "Transfer"],
            help="Type of transaction",
            required=True,
            disabled=not st.session_state.editing_enabled
        ),
        "Amount": st.column_config.NumberColumn("Amount", help="Amount of this split", format=f"{monthly_finance_config_manager.get_currency_symbol()}%.2f", required=True, disabled=not st.session_state.editing_enabled),
        "Currency": st.column_config.TextColumn("Currency", help="Transaction Currency", disabled=True),
        "BudgetPath": st.column_config.TextColumn("Budget Path", help="Categorized budget path (Scope::Category::SubCategory)", required=True, disabled=not st.session_state.editing_enabled),
        "Description": st.column_config.TextColumn("Description", help="Short description of the split", disabled=not st.session_state.editing_enabled),
        "Notes": st.column_config.TextColumn("Notes", help="Any additional notes", disabled=not st.session_state.editing_enabled),
        "InputSource": st.column_config.TextColumn("Source", help="How the transaction was entered (e.g., Manual, OCR)", disabled=True),
        "FilePath": st.column_config.TextColumn("File", help="Path to associated file", disabled=True),
        "IsVerified": st.column_config.CheckboxColumn("Verified", help="Indicates if the transaction is verified", disabled=True),
        "RelatedTransactionID": st.column_config.Column("Related Txn ID", help="ID of a related transaction (e.g., transfer pair)", disabled=True),
        "LLMConfidence": st.column_config.NumberColumn("AI Confidence", help="Confidence of AI categorization", format="%.2f", disabled=True),
        "TimestampAdded": st.column_config.DatetimeColumn("Added On", help="Timestamp when transaction was added", format="YYYY-MM-DD HH:mm:ss", disabled=True)
    }

    edited_df = st.data_editor(
        st.session_state.transactions_df_display,
        key="transactions_data_editor",
        column_config=column_config,
        num_rows="dynamic",
        hide_index=True,
        on_change=_data_editor_on_change_callback # Add on_change to force rerun on selection/edit
    )

    # Check for changes and display save button
    if st.session_state.editing_enabled and "transactions_data_editor" in st.session_state:
        if st.session_state["transactions_data_editor"]["edited_rows"] or \
           st.session_state["transactions_data_editor"]["deleted_rows"] or \
           st.session_state["transactions_data_editor"]["added_rows"]:

            st.button("Save Changes", on_click=apply_changes_to_transactions, args=(
                st.session_state["transactions_data_editor"]["edited_rows"],
                st.session_state["transactions_data_editor"]["deleted_rows"],
                st.session_state["transactions_data_editor"]["added_rows"]
            ))
            st.warning("Note: Saving changes will overwrite selected transactions. Deleting a row deletes all splits for that Transaction ID.")
        else:
            st.info("No changes detected. Edit rows to enable 'Save Changes' button.")
    elif st.session_state.editing_enabled: # If editing is enabled but no data editor state yet
        st.info("No changes detected. Edit rows to enable 'Save Changes' button.")


    # --- Metadata Display Section ---
    st.subheader("Metadata Details for Selected Row")
    # Check if 'transactions_data_editor' key exists and 'selected_rows' is present and not empty
    if "transactions_data_editor" in st.session_state and \
       "selected_rows" in st.session_state["transactions_data_editor"] and \
       st.session_state["transactions_data_editor"]["selected_rows"]:

        selected_row_indices = st.session_state["transactions_data_editor"]["selected_rows"]
        # Get the first selected row's data
        selected_row_data = st.session_state.transactions_df_display.iloc[selected_row_indices[0]]
        selected_txn_id = selected_row_data['TransactionID']
        selected_split_index = selected_row_data['SplitIndex']

        # Retrieve metadata for the selected transaction/split
        # Get transaction-level metadata (split_index=-1)
        transaction_metadata = metadata_manager.get_metadata_for_transaction(selected_txn_id, split_index=-1)
        # Get split-specific metadata
        split_metadata = metadata_manager.get_metadata_for_transaction(selected_txn_id, split_index=selected_split_index)

        if transaction_metadata or split_metadata:
            st.write(f"Metadata for Transaction ID: `{selected_txn_id}`, Split Index: `{selected_split_index}`")
            if transaction_metadata:
                with st.expander("Transaction-Level Metadata"):
                    for entry in transaction_metadata:
                        st.write(f"**{entry['Key']}**: {entry['Value']} (Source: {entry['Source']})")
            if split_metadata:
                with st.expander("Split-Specific Metadata"):
                    for entry in split_metadata:
                        st.write(f"**{entry['Key']}**: {entry['Value']} (Source: {entry['Source']})")
        else:
            st.info("No metadata found for the selected transaction/split.")
    else:
        st.info("Select a row in the table above to view its associated metadata.")

else:
    st.info("Please select a month/year and click 'Load Transactions' to view data.")
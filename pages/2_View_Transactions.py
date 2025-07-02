# pages/2_View_Transactions.py

import streamlit as st
import pandas as pd
import datetime
from typing import Dict, Any, List, Optional

# Import necessary managers (though they are loaded from session_state,
# keeping imports is good practice for type hinting and clarity if using IDE)
from modules.managers.csv_manager import CSVManager
from modules.managers.payee_manager import PayeeManager
from modules.managers.transaction_manager import TransactionManager
from modules.managers.finance_config_manager import MonthlyFinanceConfigManager  # Renamed here
from modules.managers.app_config_manager import AppConfigManager
from modules.managers.metadata_manager import MetadataManager

# --- Page Configuration ---
st.set_page_config(
    page_title="View Transactions",
    page_icon="📊",
    layout="wide"  # Use 'wide' layout for better data display
)

st.title("View, Edit, and Delete Transactions")
st.write("Browse your financial transactions, apply filters, and manage individual entries.")

# --- Manager Retrieval from Session State ---
if 'managers' not in st.session_state:
    st.error("Application managers not initialized. Please run the main app.py first.")
    st.stop()  # Stop execution if managers are not found

# Retrieve managers from session state
managers = st.session_state.managers
transaction_manager: TransactionManager = managers["transaction_manager"]
monthly_finance_config_manager: MonthlyFinanceConfigManager = managers[
    "monthly_finance_config_manager"]  # Renamed variable and type hint
payee_manager: PayeeManager = managers["payee_manager"]
app_config_manager: AppConfigManager = managers["app_config_manager"]
csv_manager: CSVManager = managers["csv_manager"]  # Access csv_manager if directly needed
metadata_manager: MetadataManager = managers["metadata_manager"]  # Access metadata_manager if directly needed


# --- Helper Functions ---
def _get_account_options(config_manager: MonthlyFinanceConfigManager) -> list:  # Renamed type hint
    """Returns a list of account display strings for selectboxes."""
    all_accounts_with_types = config_manager.get_all_accounts_with_types()
    return [f"{name} ({type})" for name, type in all_accounts_with_types]


def _get_account_name_from_display(display_string: str) -> str | None:
    """Extracts account name from the display string (e.g., 'Account Name (Type)' -> 'Account Name')."""
    return display_string.split(' (')[0] if display_string else None


def _get_budget_path_options(config_manager: MonthlyFinanceConfigManager) -> list[str]:  # Renamed type hint
    """Returns a flat list of all budget paths (Income & Expense) for selection."""
    income_paths = config_manager.get_income_budget_paths()
    expense_paths = config_manager.get_expense_budget_paths()
    return sorted(list(set(income_paths + expense_paths)))


@st.cache_data(ttl=3600)  # Cache data for 1 hour, adjust as needed
def _load_and_prepare_transactions_cached() -> pd.DataFrame:
    """Loads transactions and prepares them for display, including metadata.
    This function is cached to avoid reloading on every widget interaction."""
    df = transaction_manager.get_all_transactions()
    if df.empty:
        return pd.DataFrame()

    # Convert 'Date' column to datetime objects for proper sorting and filtering
    # Use .dt.date to get just the date part, which is better for date inputs
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date

    # Join with metadata
    metadata_df = metadata_manager.get_all_metadata()
    if not metadata_df.empty:
        # Ensure 'SplitIndex' is numeric for merging
        metadata_df['SplitIndex'] = pd.to_numeric(metadata_df['SplitIndex'], errors='coerce').fillna(-1).astype(int)
        df['SplitIndex'] = pd.to_numeric(df['SplitIndex'], errors='coerce').fillna(-1).astype(int)

        # Create a simplified metadata string for display in the main dataframe
        metadata_grouped_str = metadata_df.groupby(['TransactionID', 'SplitIndex']).apply(
            lambda x: "; ".join([f"{row['Key']}: {row['Value']}" for idx, row in x.iterrows()])
        ).reset_index(name='MetadataDisplay')

        df = pd.merge(df, metadata_grouped_str, on=['TransactionID', 'SplitIndex'], how='left')
        df['MetadataDisplay'] = df['MetadataDisplay'].fillna('')  # Fill NaN with empty string

        # Also keep original metadata structure in a temporary column if needed for editing
        metadata_grouped_raw = metadata_df.groupby(['TransactionID', 'SplitIndex']).apply(
            lambda x: x[['Key', 'Value', 'Source']].to_dict(orient='records')
        ).reset_index(name='_RawMetadata')
        df = pd.merge(df, metadata_grouped_raw, on=['TransactionID', 'SplitIndex'], how='left')
        df['_RawMetadata'] = df['_RawMetadata'].apply(lambda x: x if isinstance(x, list) else [])

    # The 'BudgetPathDisplay' column is expected to be loaded directly from the CSV
    # or prepared by the TransactionManager.
    # Removed the conditional creation of BudgetPathDisplay here as per request.
    if 'BudgetPathDisplay' not in df.columns:
        # Fallback if BudgetPathDisplay is truly missing (e.g., old CSVs)
        # This part ensures the column exists even if it's empty
        df['BudgetPathDisplay'] = 'Uncategorized'
    df['BudgetPathDisplay'] = df['BudgetPathDisplay'].fillna('Uncategorized')

    # Ensure all expected columns are present, even if empty, to prevent errors during display
    expected_cols = [
        "TransactionID", "SplitIndex", "Date", "Payee", "Description", "Amount",
        "Currency", "Account", "TransactionType", "BudgetScope", "BudgetCategory",
        "BudgetSubCategory", "BudgetPathDisplay", "RelatedTransactionID", "Notes",
        "OriginalFilename", "TimestampAdded", "LastModified", "MetadataDisplay", "_RawMetadata"  # Added _RawMetadata
    ]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = None  # Add missing columns as None

    # Reorder columns for better readability if needed
    display_cols_order = [
        "Date", "Payee", "Description", "Amount", "Currency", "Account",
        "TransactionType", "BudgetPathDisplay", "Notes", "MetadataDisplay", "OriginalFilename",
        "TransactionID", "SplitIndex", "RelatedTransactionID", "TimestampAdded", "LastModified", "_RawMetadata"
    ]
    # Filter out columns that don't exist in df to avoid error
    display_cols_order = [col for col in display_cols_order if col in df.columns]

    df = df[display_cols_order]

    return df


# Load transactions using the cached function
all_transactions_df = _load_and_prepare_transactions_cached()

# --- Filtering and Sorting ---
st.sidebar.header("Filter & Sort Transactions")

# Filters
with st.sidebar.expander("Date Range"):
    col1, col2 = st.columns(2)
    # Ensure min/max dates are actual date objects for comparison
    min_date_val = all_transactions_df['Date'].min() if not all_transactions_df.empty else datetime.date(2000, 1, 1)
    max_date_val = all_transactions_df['Date'].max() if not all_transactions_df.empty else datetime.date.today()

    # Handle case where min_date_val or max_date_val might be NaT or invalid
    if pd.isna(min_date_val): min_date_val = datetime.date(2000, 1, 1)
    if pd.isna(max_date_val): max_date_val = datetime.date.today()

    start_date_filter = col1.date_input("Start Date", value=min_date_val)
    end_date_filter = col2.date_input("End Date", value=max_date_val)

with st.sidebar.expander("General Filters"):
    payee_filter_options = payee_manager.get_all_payee_names()
    payee_filter = st.multiselect("Filter by Payee", options=payee_filter_options)

    account_options = _get_account_options(monthly_finance_config_manager)  # Renamed variable
    account_filter_display = st.multiselect("Filter by Account", options=account_options)
    account_filter = [_get_account_name_from_display(acc) for acc in account_filter_display if
                      _get_account_name_from_display(acc)]

    transaction_type_filter = st.multiselect("Filter by Type", options=["Expense", "Income", "Transfer"])
    budget_path_filter_options = _get_budget_path_options(monthly_finance_config_manager)  # Renamed variable
    budget_path_filter = st.multiselect("Filter by Category", options=budget_path_filter_options)

    description_text_filter = st.text_input("Search in Description")

    # Safely get min/max amount for slider
    min_amount_val = float(all_transactions_df['Amount'].min()) if not all_transactions_df.empty and pd.notna(
        all_transactions_df['Amount'].min()) else 0.0
    max_amount_val = float(all_transactions_df['Amount'].max()) if not all_transactions_df.empty and pd.notna(
        all_transactions_df['Amount'].max()) else 1000.0

    # Adjust default slider values if max < min (e.g., if only one transaction or all amounts are zero)
    if min_amount_val > max_amount_val:
        min_amount_val = 0.0
        max_amount_val = 100.0  # Provide a sensible default range

    amount_range = st.slider(
        "Filter by Amount Range",
        min_value=min_amount_val,
        max_value=max_amount_val,
        value=(min_amount_val, max_amount_val),
        step=0.01  # Allow for cents
    )

# Apply filters
filtered_df = all_transactions_df.copy()

if not filtered_df.empty:
    if start_date_filter and end_date_filter:
        filtered_df = filtered_df[
            (filtered_df['Date'] >= start_date_filter) & (filtered_df['Date'] <= end_date_filter)
            ]
    if payee_filter:
        filtered_df = filtered_df[filtered_df['Payee'].isin(payee_filter)]
    if account_filter:
        filtered_df = filtered_df[filtered_df['Account'].isin(account_filter)]
    if transaction_type_filter:
        filtered_df = filtered_df[filtered_df['TransactionType'].isin(transaction_type_filter)]
    if budget_path_filter:
        filtered_df = filtered_df[filtered_df['BudgetPathDisplay'].isin(budget_path_filter)]
    if description_text_filter:
        filtered_df = filtered_df[
            filtered_df['Description'].str.contains(description_text_filter, case=False, na=False)]
    if amount_range:
        filtered_df = filtered_df[
            (filtered_df['Amount'] >= amount_range[0]) & (filtered_df['Amount'] <= amount_range[1])
            ]

# Sorting
st.sidebar.header("Sorting Options")
sort_by_options = ["Date", "Amount", "Payee", "Account", "TransactionType", "BudgetPathDisplay"]
sort_by = st.sidebar.selectbox("Sort by", options=sort_by_options, index=0)
sort_order = st.sidebar.radio("Sort Order", options=["Ascending", "Descending"])

if not filtered_df.empty:
    # Ensure the sort_by column exists before attempting to sort
    if sort_by in filtered_df.columns:
        filtered_df = filtered_df.sort_values(by=sort_by, ascending=(sort_order == "Ascending"))
    else:
        st.warning(f"Sort column '{sort_by}' not found in data. Sorting by 'Date' instead.")
        filtered_df = filtered_df.sort_values(by="Date", ascending=(sort_order == "Ascending"))

st.subheader(f"Displaying {len(filtered_df)} Transactions")

# --- Display Transactions (Editable) ---

if not filtered_df.empty:
    # Columns to hide from direct display but keep for editing logic (e.g., TransactionID, SplitIndex)
    hidden_cols = ["TransactionID", "SplitIndex", "RelatedTransactionID", "TimestampAdded", "LastModified",
                   "_RawMetadata"]
    display_df = filtered_df[[col for col in filtered_df.columns if col not in hidden_cols]]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        # 'key' is important if you intend to use st.data_editor or other stateful widgets
        # but for simple display, it's not strictly necessary unless you have multiple dataframes
        key="transactions_data_viewer"
    )

    # --- Edit and Delete Functionality ---
    st.markdown("---")
    st.subheader("Edit or Delete a Transaction")

    # Use a unique identifier for selection, like TransactionID + SplitIndex
    # Ensure this column is available in filtered_df
    if 'SelectionID' not in filtered_df.columns:
        filtered_df['SelectionID'] = filtered_df['TransactionID'] + " (Split " + filtered_df['SplitIndex'].astype(
            str) + ")"

    if 'selected_selection_id' not in st.session_state:
        st.session_state.selected_selection_id = ""  # Default empty
    if 'selected_transaction_id_to_edit' not in st.session_state:
        st.session_state.selected_transaction_id_to_edit = None
    if 'selected_transaction_split_index_to_edit' not in st.session_state:
        st.session_state.selected_transaction_split_index_to_edit = None

    selected_selection_id_options = [""] + filtered_df['SelectionID'].tolist()
    # Find the index of the previously selected item to maintain state
    try:
        current_selection_index = selected_selection_id_options.index(st.session_state.selected_selection_id)
    except ValueError:
        current_selection_index = 0  # Not found, reset to default

    selected_selection_id = st.selectbox(
        "Select a transaction to edit or delete:",
        options=selected_selection_id_options,
        index=current_selection_index,
        key="transaction_selector"
    )

    # Update session state with the newly selected ID
    st.session_state.selected_selection_id = selected_selection_id

    selected_row = None
    if selected_selection_id:
        selected_row = filtered_df[filtered_df['SelectionID'] == selected_selection_id].iloc[0]
        st.session_state.selected_transaction_id_to_edit = selected_row['TransactionID']
        st.session_state.selected_transaction_split_index_to_edit = selected_row['SplitIndex']
    else:
        st.session_state.selected_transaction_id_to_edit = None
        st.session_state.selected_transaction_split_index_to_edit = None

    if st.session_state.selected_transaction_id_to_edit and st.session_state.selected_transaction_split_index_to_edit is not None:
        st.markdown(f"**Selected Transaction:** `{selected_selection_id}`")

        # --- Edit Form ---
        with st.form("edit_transaction_form", clear_on_submit=False):
            st.write("Edit Transaction Details:")

            # Pre-fill with selected transaction's data
            edit_date = st.date_input("Date", value=selected_row['Date'], key="edit_date")
            edit_payee = st.text_input("Payee", value=selected_row['Payee'], key="edit_payee")
            edit_description = st.text_area("Description", value=selected_row['Description'], key="edit_description")
            edit_amount = st.number_input("Amount", value=float(selected_row['Amount']), format="%.2f",
                                          key="edit_amount")

            # Account dropdown
            current_account_display = f"{selected_row['Account']} ({monthly_finance_config_manager.get_account_type(selected_row['Account'])})" if \
            selected_row['Account'] else ""  # Renamed variable
            try:
                account_index = _get_account_options(monthly_finance_config_manager).index(
                    current_account_display)  # Renamed variable
            except ValueError:
                account_index = 0  # Default to first if not found, or handle more gracefully
            edit_account_display = st.selectbox("Account", options=_get_account_options(monthly_finance_config_manager),
                                                index=account_index, key="edit_account")  # Renamed variable
            edit_account = _get_account_name_from_display(edit_account_display)

            # Transaction Type
            try:
                type_index = ["Expense", "Income", "Transfer"].index(selected_row['TransactionType'])
            except ValueError:
                type_index = 0  # Default to Expense if not found
            edit_transaction_type = st.selectbox("Transaction Type", options=["Expense", "Income", "Transfer"],
                                                 index=type_index, key="edit_type")

            # Budget Path
            current_budget_path = selected_row['BudgetPathDisplay']
            try:
                budget_path_index = _get_budget_path_options(monthly_finance_config_manager).index(
                    current_budget_path)  # Renamed variable
            except ValueError:
                budget_path_index = 0  # Default to first if not found, or handle more gracefully
            edit_budget_path_display = st.selectbox("Category (Budget Path)",
                                                    options=_get_budget_path_options(monthly_finance_config_manager),
                                                    index=budget_path_index, key="edit_budget_path")  # Renamed variable

            edit_notes = st.text_area("Notes", value=selected_row['Notes'], key="edit_notes")

            # Metadata editor
            st.subheader("Transaction Metadata (Key-Value pairs)")
            # Initialize or retrieve metadata for editing
            # Use the raw metadata column we prepared
            current_metadata = selected_row['_RawMetadata']

            edited_metadata_df = pd.DataFrame(current_metadata)
            if edited_metadata_df.empty:
                edited_metadata_df = pd.DataFrame(columns=['Key', 'Value', 'Source'])

            edited_metadata_df = st.data_editor(
                edited_metadata_df,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Key": st.column_config.TextColumn("Key", required=True),
                    "Value": st.column_config.TextColumn("Value", required=True),
                    "Source": st.column_config.TextColumn("Source", default="Manual Edit", disabled=True),
                },
                key="metadata_editor"
            )

            col_update, col_delete_btn = st.columns([1, 1])
            with col_update:
                update_submitted = st.form_submit_button("Update Transaction")
            with col_delete_btn:
                # Add a conditional confirmation step for deletion
                delete_clicked = st.form_submit_button("Delete Transaction (All Splits)", type="danger")

            if update_submitted:
                # Prepare updated data for the transaction manager
                updated_data = {
                    "date": edit_date,
                    "payee": edit_payee,
                    "description": edit_description,
                    "amount": edit_amount,
                    "account": edit_account,
                    "transaction_type": edit_transaction_type,
                    "budget_path_display": edit_budget_path_display,  # This will be parsed in manager
                    "notes": edit_notes,
                }

                # Prepare updated metadata
                updated_metadata_list = edited_metadata_df.to_dict(orient='records')

                if transaction_manager.update_transaction(
                        transaction_id=st.session_state.selected_transaction_id_to_edit,
                        split_index=st.session_state.selected_transaction_split_index_to_edit,
                        updated_data=updated_data,
                        updated_metadata_entries=updated_metadata_list
                ):
                    st.success(
                        f"Transaction `{st.session_state.selected_transaction_id_to_edit}` (Split {st.session_state.selected_transaction_split_index_to_edit}) updated successfully!")
                    # Clear selection after successful update
                    st.session_state.selected_selection_id = ""
                    st.session_state.selected_transaction_id_to_edit = None
                    st.session_state.selected_transaction_split_index_to_edit = None
                    # Clear cache to force reload of data after update
                    _load_and_prepare_transactions_cached.clear()
                    st.rerun()  # Refresh page to show updated data
                else:
                    st.error("Failed to update transaction.")

            if delete_clicked:
                # Use a confirmation dialog pattern
                st.session_state['confirm_delete_transaction_id'] = st.session_state.selected_transaction_id_to_edit
                st.session_state[
                    'confirm_delete_split_index'] = st.session_state.selected_transaction_split_index_to_edit
                st.session_state['show_delete_confirmation'] = True  # Set flag to show confirmation below

        # Separate confirmation logic outside the form to avoid nested forms
        if st.session_state.get('show_delete_confirmation', False):
            st.warning(
                f"Are you sure you want to delete Transaction `{st.session_state.confirm_delete_transaction_id}` (including all its splits)? This action cannot be undone.")
            col_confirm, col_cancel = st.columns(2)
            with col_confirm:
                if st.button("Yes, Delete Permanently", type="danger", key="final_confirm_delete_btn"):
                    if transaction_manager.delete_transaction(st.session_state.confirm_delete_transaction_id):
                        st.success(
                            f"Transaction `{st.session_state.confirm_delete_transaction_id}` and all its splits deleted successfully.")
                        # Clear selection and confirmation state
                        st.session_state.selected_selection_id = ""
                        st.session_state.selected_transaction_id_to_edit = None
                        st.session_state.selected_transaction_split_index_to_edit = None
                        st.session_state['show_delete_confirmation'] = False
                        # Clear cache to force reload of data after deletion
                        _load_and_prepare_transactions_cached.clear()
                        st.rerun()  # Refresh page
                    else:
                        st.error("Failed to delete transaction.")
            with col_cancel:
                if st.button("Cancel Delete", key="cancel_delete_btn"):
                    st.info("Deletion cancelled.")
                    st.session_state['show_delete_confirmation'] = False  # Hide confirmation
                    st.rerun()
    else:
        st.info("Select a transaction from the dropdown above to enable editing or deletion.")
else:
    st.info("No transactions to display. Add some transactions using the 'Add Transaction' page!")
# modules/ui_tabs/manual_entry_tab.py

import streamlit as st
import datetime
import uuid
from typing import Dict, List, Any, Optional

from modules.managers.transaction_manager import TransactionManager
from modules.managers.finance_config_manager import FinanceConfigManager
from modules.managers.payee_manager import PayeeManager
from modules.managers.app_config_manager import AppConfigManager  # NEW: For app settings


# --- Helper Functions for UI Reusability ---

def _get_account_options(config_manager: FinanceConfigManager) -> list:
    """Returns a list of account display strings for selectboxes."""
    all_accounts_with_types = config_manager.get_all_accounts_with_types()
    return [f"{name} ({type})" for name, type in all_accounts_with_types]


def _get_account_name_from_display(display_string: str) -> str | None:
    """Extracts account name from the display string (e.g., 'Account Name (Type)' -> 'Account Name')."""
    return display_string.split(' (')[0] if display_string else None


def _get_account_type_for_display(account_name: str, config_manager: FinanceConfigManager) -> str:
    """Helper to get the type of an account for display purposes."""
    all_accounts = config_manager.get_all_accounts_with_types()
    for name, type_name in all_accounts:
        if name == account_name:
            return type_name
    return "Unknown Type"


# --- Dynamic Category Selection Helper (Outside any st.form) ---
def _display_dynamic_category_selector_ui(
        structured_categories: Dict[str, Any],  # Now expects the recursive structure
        scope_options: List[str],
        session_state_key_prefix: str,  # Unique prefix for session state keys
        is_transfer: bool = False  # Flag for transfer-specific path handling
) -> None:
    """
    Displays dynamic category selection UI elements (scope, main, sub)
    and stores their state in st.session_state using the given prefix.
    This function should be called OUTSIDE of st.form.
    """
    # Initialize session state for this selector if not present
    if f'{session_state_key_prefix}_budget_scope' not in st.session_state:
        st.session_state[f'{session_state_key_prefix}_budget_scope'] = ''
    if f'{session_state_key_prefix}_category_path_elements' not in st.session_state:  # Renamed from categories_in_path
        st.session_state[f'{session_state_key_prefix}_category_path_elements'] = []
    # No longer need a separate subcategory field, as full_budget_path covers it
    # if f'{session_state_key_prefix}_subcategory' not in st.session_state:
    #     st.session_state[f'{session_state_key_prefix}_subcategory'] = ''
    if f'{session_state_key_prefix}_full_budget_path' not in st.session_state:
        st.session_state[f'{session_state_key_prefix}_full_budget_path'] = ''

    # Get current values from session state for pre-selection
    current_scope = st.session_state[f'{session_state_key_prefix}_budget_scope']
    current_path_elements = st.session_state[f'{session_state_key_prefix}_category_path_elements']

    # Add an empty string for "Choose a scope..."
    display_scope_options = [''] + sorted(scope_options)
    initial_scope_idx = display_scope_options.index(current_scope) if current_scope in display_scope_options else 0

    selected_scope_ui = st.selectbox(
        "Budget Scope",
        display_scope_options,
        index=initial_scope_idx,
        placeholder="Choose a budget scope...",
        key=f"{session_state_key_prefix}_scope_selection"
    )

    # If scope changes, reset deeper levels and update session state
    if selected_scope_ui != current_scope:
        st.session_state[f'{session_state_key_prefix}_category_path_elements'] = []
        st.session_state[
            f'{session_state_key_prefix}_full_budget_path'] = selected_scope_ui if selected_scope_ui else ''
        st.session_state[f'{session_state_key_prefix}_budget_scope'] = selected_scope_ui
        st.rerun()  # Rerun to update subsequent selectboxes based on new scope

    # Update session state for the selected scope
    st.session_state[f'{session_state_key_prefix}_budget_scope'] = selected_scope_ui
    full_budget_path_accumulator = selected_scope_ui

    current_level_dict = structured_categories.get(selected_scope_ui, {})

    selected_category_path_list_temp = []  # Temp list for current selection in this rerun

    level_num = 1
    # Loop to dynamically create selectboxes for nested categories
    while True:
        if isinstance(current_level_dict, dict) and current_level_dict:  # If there are more levels
            level_options = [''] + sorted(list(current_level_dict.keys()))

            prev_level_val = ""
            if len(current_path_elements) >= level_num:
                prev_level_val = current_path_elements[level_num - 1]

            initial_level_idx = level_options.index(prev_level_val) if prev_level_val in level_options else 0

            selected_category_at_level = st.selectbox(
                f"Category Level {level_num}",
                level_options,
                index=initial_level_idx,
                placeholder=f"Choose a category for level {level_num}...",
                key=f"{session_state_key_prefix}_cat_level_{level_num}_selection"
            )

            # If selection changes at this level, reset deeper levels and rerun
            current_category_at_level_in_path = current_path_elements[level_num - 1] if len(
                current_path_elements) >= level_num else None
            if selected_category_at_level != current_category_at_level_in_path:
                # Update current_path_elements up to this level
                st.session_state[
                    f'{session_state_key_prefix}_category_path_elements'] = selected_category_path_list_temp + (
                    [selected_category_at_level] if selected_category_at_level else [])
                st.session_state[f'{session_state_key_prefix}_full_budget_path'] = ":".join(
                    st.session_state[f'{session_state_key_prefix}_category_path_elements']) if st.session_state[
                    f'{session_state_key_prefix}_category_path_elements'] else selected_scope_ui  # Join with ':'
                if selected_category_at_level:
                    st.rerun()  # Rerun to update the next level's selectbox
                else:  # User cleared selection at this level
                    break  # Stop going deeper

            if selected_category_at_level:
                selected_category_path_list_temp.append(selected_category_at_level)
                # Prepare for next iteration: move to the sub-dictionary
                current_level_dict = current_level_dict.get(selected_category_at_level, {})
                level_num += 1
            else:  # No selection at this level
                break  # Stop iterating, no more categories to select
        else:  # Current level is not a dictionary (e.g., it's a leaf node {}) or it's an empty dictionary
            break

    # Final update of session state values for the full budget path
    st.session_state[f'{session_state_key_prefix}_category_path_elements'] = selected_category_path_list_temp
    # Reconstruct full budget path using ':' as separator
    st.session_state[f'{session_state_key_prefix}_full_budget_path'] = ":".join(
        st.session_state[f'{session_state_key_prefix}_category_path_elements']) if st.session_state[
        f'{session_state_key_prefix}_category_path_elements'] else selected_scope_ui

    # Handle initial state for transfers or income if nothing selected
    if is_transfer and not st.session_state[f'{session_state_key_prefix}_budget_scope']:
        st.session_state[f'{session_state_key_prefix}_budget_scope'] = "Transfer"
        st.session_state[f'{session_state_key_prefix}_category_path_elements'] = ["Transfer"]
        st.session_state[f'{session_state_key_prefix}_full_budget_path'] = "Transfer"
    elif st.session_state[f'{session_state_key_prefix}_budget_scope'] == "Income" and not st.session_state[
        f'{session_state_key_prefix}_category_path_elements']:
        # If Income scope is chosen but no specific category, set a default
        st.session_state[f'{session_state_key_prefix}_category_path_elements'] = [
            "Income:Uncategorized_Income"]  # Example placeholder
        st.session_state[f'{session_state_key_prefix}_full_budget_path'] = "Income:Uncategorized_Income"

    st.markdown(
        f"**Selected Budget Path:** `{st.session_state[f'{session_state_key_prefix}_full_budget_path'] if st.session_state[f'{session_state_key_prefix}_full_budget_path'] else 'None'}`"
    )


# --- Main Display Function ---

def display_manual_entry_tab(transaction_manager: TransactionManager, config_manager: FinanceConfigManager,
                             app_config_manager: AppConfigManager):  # Added app_config_manager
    """
    Displays the UI for manually entering a transaction with dynamic fields
    based on transaction type (Expense, Income, Transfer).
    """
    st.header("Enter Transaction Details Manually")

    display_currency_symbol = app_config_manager.get_app_settings().get('display_currency_symbol_on_amount', True)
    currency_symbol = config_manager.get_currency_symbol() if display_currency_symbol else ""

    account_options = _get_account_options(config_manager)
    # Get the new recursive category structure for UI
    structured_categories = config_manager.get_all_categories_recursive()

    transaction_types = ["Expense", "Income", "Transfer"]

    existing_payee_names = transaction_manager.payee_manager.get_all_payee_names()
    payee_options = [''] + sorted(existing_payee_names)  # Sort for better UX

    # --- Step 1: Select Transaction Type (outside any form for immediate reactivity) ---
    selected_transaction_type = st.radio(
        "Select Transaction Type",
        transaction_types,
        horizontal=True,
        key="selected_transaction_type_radio"
    )

    # --- Global Transaction Details (outside any form to preserve values) ---
    st.markdown("---")
    st.subheader("General Transaction Information")

    # Initialize global transaction data in session state if not present
    if 'global_transaction_data' not in st.session_state:
        st.session_state.global_transaction_data = {
            'date': datetime.date.today(),
            'payee': '',
            'account': '',
            'uploaded_file': None
        }

    # Reset general transaction data if transaction type changes for Expense/Income/Transfer
    if st.session_state.get('last_selected_transaction_type_general_reset') != selected_transaction_type:
        st.session_state.global_transaction_data = {
            'date': datetime.date.today(),
            'payee': '',
            'account': '',
            'uploaded_file': None
        }
        st.session_state['last_selected_transaction_type_general_reset'] = selected_transaction_type
        # Also clear split data if exists for other types
        for key in ['expense_splits', 'income_splits', 'transfer_data']:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()  # Rerun to apply resets

    st.session_state.global_transaction_data['date'] = st.date_input(
        "Date",
        st.session_state.global_transaction_data['date'],
        key="general_date"
    )

    current_payee_value = st.session_state.global_transaction_data['payee']
    initial_payee_idx = payee_options.index(current_payee_value) if current_payee_value in payee_options else 0

    selected_payee = st.selectbox(
        "Payer/Payee (Overall)",
        payee_options,
        index=initial_payee_idx,
        placeholder="Type or select a payee (e.g., Supermarket, Monthly Salary)",
        key="general_payee_selectbox",
        # Custom logic needed to handle new options (add to payee_manager on save)
        # accept_new_options=True # Removed this to manage new payee addition explicitly on form submission
    )
    st.session_state.global_transaction_data['payee'] = selected_payee

    initial_account_display = f"{st.session_state.global_transaction_data['account']} ({_get_account_type_for_display(st.session_state.global_transaction_data['account'], config_manager)})" if \
        st.session_state.global_transaction_data['account'] else None

    # Find index for initial selection, handling cases where account_options might change
    account_idx = next((i for i, opt in enumerate(account_options) if
                        _get_account_name_from_display(opt) == st.session_state.global_transaction_data['account']), 0)

    account_display = st.selectbox(
        "Account (Overall)",
        account_options,
        index=account_idx,
        placeholder="Choose the main account for this transaction...",
        key="general_account"
    )
    st.session_state.global_transaction_data['account'] = _get_account_name_from_display(account_display)

    uploaded_file = st.file_uploader("Attach Invoice/Receipt (Optional)", type=['png', 'jpg', 'jpeg', 'pdf'],
                                     key="general_file_uploader")

    if 'current_transaction_id' not in st.session_state:
        st.session_state.current_transaction_id = f"TRN-{int(datetime.datetime.now().timestamp())}-{uuid.uuid4().hex[:6].upper()}"

    # --- Dynamic UI based on Transaction Type (OUTSIDE THE SUBMISSION FORM) ---
    if selected_transaction_type in ["Expense", "Income"]:
        st.markdown("---")
        st.subheader(f"Splits for {selected_transaction_type}")

        split_key = f'{selected_transaction_type.lower()}_splits'

        # Initialize splits or reset if transaction type changed
        if split_key not in st.session_state or \
                st.session_state.get('last_selected_transaction_type_split_init') != selected_transaction_type:
            st.session_state[split_key] = [{
                'amount': 0.0,
                'description': '',
                'notes': '',
                'budget_scope': '', 'category': '', 'sub_category': '',
                # category and sub_category are now parts of path
                'full_budget_path': ''
            }]
            st.session_state['last_selected_transaction_type_split_init'] = selected_transaction_type
            # Clear all category selection state variables for each split to ensure a clean start
            for i in range(len(st.session_state[split_key])):
                prefix_to_clear = f"{selected_transaction_type}_split_{i}_cat_ui"
                if f'{prefix_to_clear}_budget_scope' in st.session_state:
                    del st.session_state[f'{prefix_to_clear}_budget_scope']
                if f'{prefix_to_clear}_category_path_elements' in st.session_state:
                    del st.session_state[f'{prefix_to_clear}_category_path_elements']
                if f'{prefix_to_clear}_full_budget_path' in st.session_state:
                    del st.session_state[f'{prefix_to_clear}_full_budget_path']
            st.rerun()

        col_split_btns = st.columns([1, 1, 3])
        with col_split_btns[0]:
            if st.button("Add Another Split", key=f"{selected_transaction_type}_add_split_btn_outside"):
                st.session_state[split_key].append({
                    'amount': 0.0, 'description': '', 'notes': '',
                    'budget_scope': '', 'category': '', 'sub_category': '',
                    'full_budget_path': ''
                })
                # No rerun here if we manage the keys correctly, but rerunning is simplest
                st.rerun()
        with col_split_btns[1]:
            if len(st.session_state[split_key]) > 1:
                if st.button("Remove Last Split", key=f"{selected_transaction_type}_remove_split_btn_outside"):
                    # Clear session state for the removed split's category UI to prevent conflicts
                    prefix_to_clear = f"{selected_transaction_type}_split_{len(st.session_state[split_key]) - 1}_cat_ui"
                    if f'{prefix_to_clear}_budget_scope' in st.session_state:
                        del st.session_state[f'{prefix_to_clear}_budget_scope']
                    if f'{prefix_to_clear}_category_path_elements' in st.session_state:
                        del st.session_state[f'{prefix_to_clear}_category_path_elements']
                    if f'{prefix_to_clear}_full_budget_path' in st.session_state:
                        del st.session_state[f'{prefix_to_clear}_full_budget_path']

                    st.session_state[split_key].pop()
                    st.rerun()

        total_amount_sum = 0.0
        # Initialize or update a temporary list to hold current split values before form submission
        # This is for internal use within this display function, not for session_state persistence of final values
        # The actual split_data in st.session_state[split_key] is what gets updated directly.
        # st.session_state[f'{selected_transaction_type.lower()}_current_split_values'] = []

        for i, split_data in enumerate(st.session_state[split_key]):
            st.markdown(f"**Split {i + 1}**")

            split_data['amount'] = st.number_input(
                "Amount",
                min_value=0.0,
                format="%.2f",
                value=split_data['amount'],
                key=f"{selected_transaction_type}_split_amount_{i}_outside"
            )
            total_amount_sum += split_data['amount']

            cols_desc_notes = st.columns(2)
            with cols_desc_notes[0]:
                split_data['description'] = st.text_input(
                    "Description (Split)",
                    value=split_data['description'],
                    key=f"{selected_transaction_type}_split_description_{i}_outside",
                    placeholder="e.g., Specific item, reason for this part of the transaction"
                )
            with cols_desc_notes[1]:
                split_data['notes'] = st.text_area(
                    "Notes (Split)",
                    value=split_data['notes'],
                    key=f"{selected_transaction_type}_split_notes_{i}_outside",
                    placeholder="Additional notes for this split."
                )

            st.write("Category for this split:")

            # Determine scope options based on transaction type
            if selected_transaction_type == "Expense":
                # Exclude 'Income' from expense scopes
                scope_opts = [s for s in config_manager.get_all_budget_scopes() if s != 'Income']
            elif selected_transaction_type == "Income":
                # Only 'Income' scope for income transactions
                scope_opts = ['Income']
            else:
                scope_opts = []  # Should not happen with Expense/Income check

            _display_dynamic_category_selector_ui(
                structured_categories,
                scope_opts,
                session_state_key_prefix=f"{selected_transaction_type}_split_{i}_cat_ui",
                is_transfer=False  # Not a transfer
            )

            # Update split_data with values from the category selector's session state
            split_data['budget_scope'] = st.session_state[f"{selected_transaction_type}_split_{i}_cat_ui_budget_scope"]

            # Category and SubCategory are now derived from the full_budget_path
            full_path_parts = st.session_state[f"{selected_transaction_type}_split_{i}_cat_ui_full_budget_path"].split(
                ':')
            split_data['full_budget_path'] = st.session_state[
                f"{selected_transaction_type}_split_{i}_cat_ui_full_budget_path"]

            split_data['category'] = full_path_parts[1] if len(full_path_parts) > 1 else ""
            split_data['sub_category'] = full_path_parts[2] if len(full_path_parts) > 2 else ""

            st.markdown("---")

        st.markdown(f"**Calculated Total Amount for Splits: {currency_symbol}{total_amount_sum:.2f}**")

        with st.form(key=f"{selected_transaction_type.lower()}_submission_form"):
            st.write("Click 'Save Transaction' to finalize your entry.")
            submitted = st.form_submit_button(f"Save {selected_transaction_type} Transaction")

            if submitted:
                is_valid = True

                if not st.session_state.global_transaction_data['payee']:
                    st.error("Overall Payer/Payee is required.")
                    is_valid = False
                if not st.session_state.global_transaction_data['account']:
                    st.error("Overall Account is required.")
                    is_valid = False

                if total_amount_sum <= 0:
                    st.error("Total amount of splits must be positive.")
                    is_valid = False

                for i, split_data in enumerate(st.session_state[split_key]):  # Use the actual session state splits
                    if split_data['amount'] <= 0:
                        st.error(f"Split {i + 1}: Amount must be positive.")
                        is_valid = False
                    if not split_data['description']:
                        st.error(f"Split {i + 1}: Description is required.")
                        is_valid = False
                    if not split_data['full_budget_path'] or split_data['full_budget_path'] == split_data[
                        'budget_scope']:
                        st.error(
                            f"Split {i + 1}: A specific category must be selected. Only '{split_data['budget_scope']}' is not a full path.")
                        is_valid = False

                    # Ensure income transactions are categorized under 'Income' scope
                    if selected_transaction_type == "Income" and not split_data['full_budget_path'].startswith(
                            "Income:"):
                        st.error(f"Split {i + 1}: Income transactions must be categorized under an 'Income' path.")
                        is_valid = False
                    # Ensure expense transactions are NOT categorized under 'Income' scope
                    elif selected_transaction_type == "Expense" and split_data['full_budget_path'].startswith(
                            "Income:"):
                        st.error(f"Split {i + 1}: Expense transactions cannot be categorized under an 'Income' path.")
                        is_valid = False

                if is_valid:
                    try:
                        splits_for_manager = []
                        for split_data in st.session_state[split_key]:
                            # Ensure the full_budget_path is passed correctly
                            splits_for_manager.append({
                                'amount': split_data['amount'],
                                'description': split_data['description'],
                                'notes': split_data['notes'],
                                'payee': st.session_state.global_transaction_data['payee'],
                                # Each split defaults to overall payee
                                'account': st.session_state.global_transaction_data['account'],
                                # Each split defaults to overall account
                                'budget_scope': split_data['budget_scope'],
                                'category': split_data['category'],
                                'sub_category': split_data['sub_category'],
                                'full_budget_path': split_data['full_budget_path']
                            })

                        # Manual metadata (currently only for invoice processing, but can be passed for general manual entry if UI expanded)
                        manual_metadata_entries = []

                        transaction_manager.add_manual_transaction(
                            transaction_id=st.session_state.current_transaction_id,
                            transaction_type=selected_transaction_type,
                            date=st.session_state.global_transaction_data['date'],
                            payee=st.session_state.global_transaction_data['payee'],
                            account=st.session_state.global_transaction_data['account'],
                            uploaded_file=uploaded_file,
                            splits=splits_for_manager,
                            manual_metadata=manual_metadata_entries
                        )
                        st.success(
                            f"{selected_transaction_type} transaction saved successfully with ID: **{st.session_state.current_transaction_id}**")

                        # Reset form fields and session state after successful submission
                        st.session_state[split_key] = [{
                            'amount': 0.0, 'description': '', 'notes': '',
                            'budget_scope': '', 'category': '', 'sub_category': '',
                            'full_budget_path': ''
                        }]
                        st.session_state.global_transaction_data = {
                            'date': datetime.date.today(), 'payee': '', 'account': '', 'uploaded_file': None
                        }
                        # Clear specific category selector session state for all splits
                        for i in range(
                                len(st.session_state[split_key])):  # Loop through number of splits that *were* there
                            prefix_to_clear = f"{selected_transaction_type}_split_{i}_cat_ui"
                            if f'{prefix_to_clear}_budget_scope' in st.session_state:
                                del st.session_state[f'{prefix_to_clear}_budget_scope']
                                del st.session_state[f'{prefix_to_clear}_category_path_elements']
                                del st.session_state[f'{prefix_to_clear}_full_budget_path']

                        # Clear transfer specific state if it exists
                        if 'transfer_data' in st.session_state:
                            del st.session_state['transfer_data']
                        if 'transfer_cat_ui_budget_scope' in st.session_state:  # Clear transfer category UI state
                            del st.session_state['transfer_cat_ui_budget_scope']
                            del st.session_state['transfer_cat_ui_category_path_elements']
                            del st.session_state['transfer_cat_ui_full_budget_path']

                        # Generate new transaction ID
                        st.session_state.current_transaction_id = f"TRN-{int(datetime.datetime.now().timestamp())}-{uuid.uuid4().hex[:6].upper()}"
                        st.rerun()  # Rerun to clear the form and show success message

                    except Exception as e:
                        st.error(f"Failed to save {selected_transaction_type} transaction: {e}")

    elif selected_transaction_type == "Transfer":
        st.markdown("---")
        st.subheader("Transfer Details")

        if 'transfer_data' not in st.session_state or st.session_state.get(
                'last_selected_transaction_type_split_init') != selected_transaction_type:
            st.session_state.transfer_data = {
                'amount': 0.0,
                'source_account': '',
                'destination_account': '',
                'description': '',
                'notes': '',
                'budget_scope': 'Transfer',  # Default for transfers
                'category': 'Transfer',  # Default for transfers
                'sub_category': '',
                'full_budget_path': 'Transfer:Transfer'  # Default for transfers
            }
            st.session_state['last_selected_transaction_type_split_init'] = selected_transaction_type
            # Clear category selector state for transfer
            if 'transfer_cat_ui_budget_scope' in st.session_state:
                del st.session_state['transfer_cat_ui_budget_scope']
                del st.session_state['transfer_cat_ui_category_path_elements']
                del st.session_state['transfer_cat_ui_full_budget_path']
            st.rerun()  # Rerun to apply resets

        col1, col2 = st.columns(2)
        with col1:
            st.session_state.transfer_data['amount'] = st.number_input(
                "Amount",
                min_value=0.0,
                format="%.2f",
                value=st.session_state.transfer_data['amount'],
                key="transfer_amount_outside"
            )

            initial_source_acc_display = f"{st.session_state.transfer_data['source_account']} ({_get_account_type_for_display(st.session_state.transfer_data['source_account'], config_manager)})" if \
                st.session_state.transfer_data['source_account'] else None

            # Find index for initial selection
            source_acc_idx = next((i for i, opt in enumerate(account_options) if
                                   _get_account_name_from_display(opt) == st.session_state.transfer_data[
                                       'source_account']), 0)

            source_account_display = st.selectbox(
                "From Account",
                account_options,
                index=source_acc_idx,
                placeholder="Choose source account...",
                key="transfer_source_acc_outside"
            )
            st.session_state.transfer_data['source_account'] = _get_account_name_from_display(source_account_display)

            st.session_state.transfer_data['description'] = st.text_input(
                "Description (Transfer)",
                value=st.session_state.transfer_data['description'],
                key="transfer_description_outside",
                placeholder="e.g., Transfer to savings for vacation"
            )

        with col2:
            # For transfers, we usually have a "Transfer" category and don't need the full budget tree.
            # However, if you want to allow transfers to be categorized within the budget (e.g., as 'Savings Contribution'),
            # you would offer the full scope options. For a strict 'Transfer' type, we can simplify.

            # If "Transfer" is a top-level scope in your financial_config.yaml, this will work.
            # Otherwise, you might need to hardcode it or adjust FinanceConfigManager.
            # For now, assuming "Transfer" is a distinct 'scope' from a conceptual perspective.
            transfer_scope_opts = ['Transfer']  # Force 'Transfer' as the only scope for transfers

            _display_dynamic_category_selector_ui(
                # Pass a simplified structured_categories for "Transfer" if needed,
                # or just let it select 'Transfer:Transfer'
                {"Transfer": {"Transfer": {}}},  # A mock structure just for this selector to work
                transfer_scope_opts,
                session_state_key_prefix="transfer_cat_ui",
                is_transfer=True
            )
            # Override budget path for transfers if the selector changes it to something else unintended
            st.session_state.transfer_data['budget_scope'] = st.session_state["transfer_cat_ui_budget_scope"]

            full_path_parts = st.session_state["transfer_cat_ui_full_budget_path"].split(':')
            st.session_state.transfer_data['full_budget_path'] = st.session_state["transfer_cat_ui_full_budget_path"]

            st.session_state.transfer_data['category'] = full_path_parts[1] if len(full_path_parts) > 1 else ""
            st.session_state.transfer_data['sub_category'] = full_path_parts[2] if len(full_path_parts) > 2 else ""

            initial_dest_acc_display = f"{st.session_state.transfer_data['destination_account']} ({_get_account_type_for_display(st.session_state.transfer_data['destination_account'], config_manager)})" if \
                st.session_state.transfer_data['destination_account'] else None

            dest_acc_idx = next((i for i, opt in enumerate(account_options) if
                                 _get_account_name_from_display(opt) == st.session_state.transfer_data[
                                     'destination_account']), 0)

            destination_account_display = st.selectbox(
                "To Account",
                account_options,
                index=dest_acc_idx,
                placeholder="Choose destination account...",
                key="transfer_dest_acc_outside"
            )
            st.session_state.transfer_data['destination_account'] = _get_account_name_from_display(
                destination_account_display)

            st.session_state.transfer_data['notes'] = st.text_area(
                "Notes (Transfer)",
                value=st.session_state.transfer_data['notes'],
                key="transfer_notes_outside",
                placeholder="Any additional notes about this transfer."
            )

        with st.form(key="transfer_submission_form"):
            st.write("Click 'Save Transfer' to finalize your entry.")
            submitted = st.form_submit_button("Save Transfer")

            if submitted:
                amount = st.session_state.transfer_data['amount']
                source_account_name = st.session_state.transfer_data['source_account']
                destination_account_name = st.session_state.transfer_data['destination_account']
                description = st.session_state.transfer_data['description']
                notes = st.session_state.transfer_data['notes']
                # The payee for a transfer is typically a pseudo-payee like 'Transfer' or the destination account
                transfer_payee = f"Transfer to {destination_account_name}" if destination_account_name else "Transfer"

                is_valid = True
                if amount <= 0 or not source_account_name or not destination_account_name:
                    st.error("A positive Amount, 'From Account', and 'To Account' are required for Transfer.")
                    is_valid = False
                elif source_account_name == destination_account_name:
                    st.error("Source and Destination accounts cannot be the same for Transfer.")
                    is_valid = False
                elif not st.session_state.transfer_data['full_budget_path']:
                    st.error("A budget path (e.g., 'Transfer:Transfer') is required for transfers.")
                    is_valid = False

                if is_valid:
                    try:
                        related_transaction_id_for_transfer = st.session_state.current_transaction_id

                        # Create two splits for a transfer: one debit from source, one credit to destination
                        # Both splits share the same transaction_id to link them
                        transfer_splits = [
                            {
                                'description': description or f"Transfer from {source_account_name} to {destination_account_name}",
                                'amount': -amount,  # Debit from source account
                                'payee': transfer_payee,
                                'account': source_account_name,
                                'notes': notes,
                                'budget_scope': st.session_state.transfer_data['budget_scope'],
                                'category': st.session_state.transfer_data['category'],
                                'sub_category': st.session_state.transfer_data['sub_category'],
                                'full_budget_path': st.session_state.transfer_data['full_budget_path']
                            },
                            {
                                'description': description or f"Transfer to {destination_account_name} from {source_account_name}",
                                'amount': amount,  # Credit to destination account
                                'payee': transfer_payee,
                                'account': destination_account_name,
                                'notes': notes,
                                'budget_scope': st.session_state.transfer_data['budget_scope'],
                                'category': st.session_state.transfer_data['category'],
                                'sub_category': st.session_state.transfer_data['sub_category'],
                                'full_budget_path': st.session_state.transfer_data['full_budget_path']
                            }
                        ]

                        transaction_manager.add_manual_transaction(
                            transaction_id=related_transaction_id_for_transfer,
                            transaction_type="Transfer",
                            date=st.session_state.global_transaction_data['date'],
                            payee=transfer_payee,  # Overall payee for the transfer
                            account=source_account_name,  # The main account (source) for the overall transaction
                            uploaded_file=uploaded_file,  # Attach file if any
                            splits=transfer_splits,
                            manual_metadata=[]  # No specific metadata for transfers typically
                        )
                        st.success(
                            f"Transfer transaction saved successfully with ID: **{related_transaction_id_for_transfer}**")

                        # Reset form fields and session state after successful submission
                        st.session_state.transfer_data = {
                            'amount': 0.0, 'source_account': '', 'destination_account': '',
                            'description': '', 'notes': '',
                            'budget_scope': 'Transfer', 'category': 'Transfer', 'sub_category': '',
                            'full_budget_path': 'Transfer:Transfer'
                        }
                        st.session_state.global_transaction_data = {
                            'date': datetime.date.today(), 'payee': '', 'account': '', 'uploaded_file': None
                        }
                        # Clear category selector state for transfer
                        if 'transfer_cat_ui_budget_scope' in st.session_state:
                            del st.session_state['transfer_cat_ui_budget_scope']
                            del st.session_state['transfer_cat_ui_category_path_elements']
                            del st.session_state['transfer_cat_ui_full_budget_path']

                        st.session_state.current_transaction_id = f"TRN-{int(datetime.datetime.now().timestamp())}-{uuid.uuid4().hex[:6].upper()}"
                        st.rerun()

                    except Exception as e:
                        st.error(f"Failed to save Transfer transaction: {e}")


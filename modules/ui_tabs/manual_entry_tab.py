# modules/ui_tabs/manual_entry_tab.py

import streamlit as st
import datetime
import uuid
from typing import Dict, List, Any, Optional

from modules.managers.transaction_manager import TransactionManager
from modules.managers.finance_config_manager import FinanceConfigManager
from modules.managers.payee_manager import PayeeManager
from modules.managers.app_config_manager import AppConfigManager
from modules.managers.metadata_manager import MetadataManager  # Import MetadataManager for getting existing keys


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
) -> None:
    """
    Displays dynamic category selection UI elements (scope, main, sub)
    and stores their state in st.session_state using the given prefix.
    This function should be called OUTSIDE of st.form.
    """
    # Initialize session state for this selector if not present
    if f'{session_state_key_prefix}_budget_scope' not in st.session_state:
        st.session_state[f'{session_state_key_prefix}_budget_scope'] = ''
    if f'{session_state_key_prefix}_category_path_elements' not in st.session_state:
        st.session_state[f'{session_state_key_prefix}_category_path_elements'] = []
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
    # full_budget_path_accumulator = selected_scope_ui # No longer directly needed

    current_level_dict = structured_categories.get(selected_scope_ui, {})

    selected_category_path_list_temp = [
        selected_scope_ui] if selected_scope_ui else []  # Start with scope for path elements

    level_num = 1
    # Loop to dynamically create selectboxes for nested categories
    while True:
        if isinstance(current_level_dict, dict) and current_level_dict:  # If there are more levels
            level_options = [''] + sorted(list(current_level_dict.keys()))

            # Determine the value to pre-select for this level
            prev_level_val = ""
            # current_path_elements will now include the scope as the first element if selected
            # So, current_path_elements[level_num] corresponds to category level `level_num`
            if len(current_path_elements) > level_num:  # > to account for scope being at index 0
                prev_level_val = current_path_elements[level_num]

            initial_level_idx = level_options.index(prev_level_val) if prev_level_val in level_options else 0

            selected_category_at_level = st.selectbox(
                f"Category Level {level_num}",
                level_options,
                index=initial_level_idx,
                placeholder=f"Choose a category for level {level_num}...",
                key=f"{session_state_key_prefix}_cat_level_{level_num}_selection"
            )

            # Check if selection changed from the previous state for this level
            # Compare with the current_path_elements (which holds previous state including scope)
            is_level_changed = (len(current_path_elements) <= level_num or
                                selected_category_at_level != current_path_elements[level_num])

            if is_level_changed:
                # Update current_path_elements up to this level
                new_path_elements = selected_category_path_list_temp[:level_num]  # Truncate to current level
                if selected_category_at_level:
                    new_path_elements.append(selected_category_at_level)

                st.session_state[f'{session_state_key_prefix}_category_path_elements'] = new_path_elements
                st.session_state[f'{session_state_key_prefix}_full_budget_path'] = ":".join(new_path_elements)

                if selected_category_at_level:  # Only rerun if a selection was made (not cleared)
                    st.rerun()
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

    # Final update of session state values for the full budget path based on current selections
    # This ensures accuracy if user clears a lower-level selection or no deeper levels exist.
    st.session_state[f'{session_state_key_prefix}_category_path_elements'] = selected_category_path_list_temp
    st.session_state[f'{session_state_key_prefix}_full_budget_path'] = ":".join(selected_category_path_list_temp)

    st.markdown(
        f"**Selected Budget Path:** `{st.session_state[f'{session_state_key_prefix}_full_budget_path'] if st.session_state[f'{session_state_key_prefix}_full_budget_path'] else 'None'}`"
    )


@st.cache_data
def _get_all_unique_metadata_keys(_metadata_manager: MetadataManager) -> List[str]:
    """
    Retrieves all unique metadata keys from the metadata.csv file.
    This function is cached to avoid re-reading the CSV on every rerun.
    """
    try:
        metadata_keys = _metadata_manager.get_all_unique_metadata_keys()
        if len(metadata_keys) > 0:
            return [''] + metadata_keys
        return ['']
    except Exception as e:
        st.warning(f"Could not load existing metadata keys: {e}. Starting with empty list.")
        return ['']


# --- Main Display Function ---

def display_manual_entry_tab(transaction_manager: TransactionManager, config_manager: FinanceConfigManager,
                             app_config_manager: AppConfigManager):
    """
    Displays the UI for manually entering a transaction with dynamic fields
    based on transaction type (Expense, Income, Transfer).
    """
    st.header("Enter Transaction Details Manually")

    display_currency_symbol = app_config_manager.get_app_settings().get('display_currency_symbol_on_amount', True)
    currency_symbol = config_manager.get_currency_symbol() if display_currency_symbol else ""

    account_options = _get_account_options(config_manager)
    structured_categories = config_manager.get_all_categories_recursive()

    transaction_types = ["Expense", "Income", "Transfer"]

    existing_payee_names = transaction_manager.payee_manager.get_all_payee_names()
    payee_options = [''] + sorted(existing_payee_names)  # Sort for better UX

    all_unique_metadata_keys = _get_all_unique_metadata_keys(transaction_manager.metadata_manager)

    # --- Step 1: Select Transaction Type (outside any form for immediate reactivity) ---
    selected_transaction_type = st.radio(
        "Select Transaction Type",
        transaction_types,
        horizontal=True,
        key="selected_transaction_type_radio"
    )

    # --- Initialize/Reset Global Transaction Data ---
    # This data is used by all transaction types unless overridden by specific sections (like Transfer)
    if 'global_transaction_data' not in st.session_state:
        st.session_state.global_transaction_data = {
            'date': datetime.date.today(),
            'payee': '',
            'account': '',
            'uploaded_file': None,
            'manual_metadata': []  # Initialize manual metadata list
        }

    # Reset general transaction data if transaction type changes
    if st.session_state.get('last_selected_transaction_type_general_reset') != selected_transaction_type:
        # Preserve date, as it's common. Clear payee and account.
        st.session_state.global_transaction_data = {
            'date': st.session_state.global_transaction_data['date'],  # Keep the current date
            'payee': '',  # Reset payee
            'account': '',  # Reset account
            'uploaded_file': None,
            'manual_metadata': []  # Reset metadata on type change
        }
        st.session_state['last_selected_transaction_type_general_reset'] = selected_transaction_type

        # Clear split/transfer data
        for key in ['expense_splits', 'income_splits', 'transfer_data']:
            if key in st.session_state:
                del st.session_state[key]
        # Also clear all category selection states
        for key in list(st.session_state.keys()):
            if '_cat_ui' in key:
                del st.session_state[key]
        # Ensure metadata input fields also reset
        if 'manual_metadata_entries' in st.session_state:
            del st.session_state['manual_metadata_entries']

        st.rerun()  # Rerun to apply resets

    # --- Overall File Uploader (Always visible) ---
    uploaded_file = st.file_uploader("Attach Invoice/Receipt (Optional)", type=['png', 'jpg', 'jpeg', 'pdf'],
                                     key="general_file_uploader")

    # --- Transaction ID (Always visible) ---
    if 'current_transaction_id' not in st.session_state:
        st.session_state.current_transaction_id = f"TRN-{int(datetime.datetime.now().timestamp())}-{uuid.uuid4().hex[:6].upper()}"

    # --- Dynamic UI based on Transaction Type ---
    if selected_transaction_type in ["Expense", "Income"]:
        st.markdown("---")
        st.subheader("General Transaction Information")

        st.session_state.global_transaction_data['date'] = st.date_input(
            "Date",
            st.session_state.global_transaction_data['date'],
            key="general_date"
        )

        # Payee Selection/Entry
        selected_payee_from_list = st.selectbox(
            "Select an existing Payer/Payee (Optional)",
            payee_options,
            index=0,  # Default to empty string
            placeholder="Choose from recent payees...",
            key="general_payee_list_selectbox"
        )
        st.info(
            "If you select an existing payee, it will appear in the text input below. You can then edit or add a new payee directly in the text input. The **text input value** will be used for the transaction.")

        # If an existing payee is selected from the list, pre-fill the text input
        # only if the text input is currently empty or matches the previously selected list item.
        # This prevents overwriting user's manual input if they start typing.
        if selected_payee_from_list and selected_payee_from_list != st.session_state.global_transaction_data['payee']:
            st.session_state.global_transaction_data['payee'] = selected_payee_from_list
            st.rerun()  # Rerun to update the text input

        st.session_state.global_transaction_data['payee'] = st.text_input(
            "Payer/Payee (Type a new one or confirm selection)",
            value=st.session_state.global_transaction_data['payee'],
            key="general_payee_text_input",
            placeholder="Type payee name or select from above..."
        )

        # Account Selection
        account_idx = next((i for i, opt in enumerate(account_options) if
                            _get_account_name_from_display(opt) == st.session_state.global_transaction_data['account']),
                           0)
        account_display = st.selectbox(
            "Account (Overall)",
            account_options,
            index=account_idx,
            placeholder="Choose the main account for this transaction...",
            key="general_account"
        )
        st.session_state.global_transaction_data['account'] = _get_account_name_from_display(account_display)

        st.markdown("---")
        st.subheader(f"Splits for {selected_transaction_type}")

        split_key = f'{selected_transaction_type.lower()}_splits'

        # Initialize splits or reset if transaction type changed
        if split_key not in st.session_state:  # No need for 'last_selected_transaction_type_split_init' as it's handled above
            st.session_state[split_key] = [{
                'amount': 0.0,
                'description': '',
                'notes': '',
                'budget_scope': '', 'category': '', 'sub_category': '',
                'full_budget_path': ''
            }]

        col_split_btns = st.columns([1, 1, 3])
        with col_split_btns[0]:
            if st.button("Add Another Split", key=f"{selected_transaction_type}_add_split_btn_outside"):
                st.session_state[split_key].append({
                    'amount': 0.0, 'description': '', 'notes': '',
                    'budget_scope': '', 'category': '', 'sub_category': '',
                    'full_budget_path': ''
                })
                st.rerun()
        with col_split_btns[1]:
            if len(st.session_state[split_key]) > 1:
                if st.button("Remove Last Split", key=f"{selected_transaction_type}_remove_split_btn_outside"):
                    # Clear session state for the removed split's category UI to prevent conflicts
                    prefix_to_clear = f"{selected_transaction_type}_split_{len(st.session_state[split_key]) - 1}_cat_ui"
                    for k in list(st.session_state.keys()):  # Iterate over a copy of keys
                        if k.startswith(prefix_to_clear):
                            del st.session_state[k]

                    st.session_state[split_key].pop()
                    st.rerun()

        total_amount_sum = 0.0

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
                scope_opts = [s for s in config_manager.get_all_budget_scopes() if s != 'Income']
            elif selected_transaction_type == "Income":
                scope_opts = ['Income']
            else:
                scope_opts = []

            _display_dynamic_category_selector_ui(
                structured_categories,
                scope_opts,
                session_state_key_prefix=f"{selected_transaction_type}_split_{i}_cat_ui",
            )

            # Update split_data with values from the category selector's session state
            # Ensure the session state key for full_budget_path is accessed safely
            current_full_path = st.session_state.get(f"{selected_transaction_type}_split_{i}_cat_ui_full_budget_path",
                                                     "")
            split_data['full_budget_path'] = current_full_path

            full_path_parts = current_full_path.split(':')
            split_data['budget_scope'] = full_path_parts[0] if len(full_path_parts) > 0 else ""
            split_data['category'] = full_path_parts[1] if len(full_path_parts) > 1 else ""
            split_data['sub_category'] = full_path_parts[2] if len(full_path_parts) > 2 else ""

            st.markdown("---")

        st.markdown(f"**Calculated Total Amount for Splits: {currency_symbol}{total_amount_sum:.2f}**")

        # --- Additional Metadata Section ---
        # Initialize manual_metadata_entries if not present, including a placeholder for selected key
        if 'manual_metadata_entries' not in st.session_state:
            st.session_state.manual_metadata_entries = [{'key': '', 'value': '', '_selected_from_list_key': ''}]

        with st.expander("Additional Metadata (Optional)"):
            # Buttons to add/remove metadata rows
            col_meta_btns = st.columns([1, 1, 3])
            with col_meta_btns[0]:
                if st.button("Add Metadata Field", key=f"{selected_transaction_type}_add_meta_btn"):
                    st.session_state.manual_metadata_entries.append(
                        {'key': '', 'value': '', '_selected_from_list_key': ''})
                    st.rerun()
            with col_meta_btns[1]:
                if len(st.session_state.manual_metadata_entries) > 1:
                    if st.button("Remove Last Metadata Field", key=f"{selected_transaction_type}_remove_meta_btn"):
                        st.session_state.manual_metadata_entries.pop()
                        st.rerun()

            # Display key-value input fields for metadata
            for i, meta_entry in enumerate(st.session_state.manual_metadata_entries):
                cols_meta = st.columns([1, 1])
                with cols_meta[0]:
                    # Selectbox for existing keys
                    selected_key_from_list = st.selectbox(
                        "Metadata Key (Select existing)",
                        all_unique_metadata_keys,
                        index=all_unique_metadata_keys.index(meta_entry['_selected_from_list_key']) if meta_entry[
                                                                                                           '_selected_from_list_key'] in all_unique_metadata_keys else 0,
                        placeholder="Choose from existing keys...",
                        key=f"{selected_transaction_type}_meta_key_selectbox_{i}"
                    )
                    # If selection from box changes AND it's different from current text input, update text input
                    if selected_key_from_list and selected_key_from_list != meta_entry['_selected_from_list_key']:
                        meta_entry['_selected_from_list_key'] = selected_key_from_list  # Update internal tracker
                        meta_entry['key'] = selected_key_from_list  # Set the actual key to selected value
                        st.rerun()  # Rerun to update the text input

                    # Text input for new/edited key (takes precedence)
                    meta_entry['key'] = st.text_input(
                        "Metadata Key (Enter new or edit)",
                        value=meta_entry['key'],
                        key=f"{selected_transaction_type}_meta_key_textinput_{i}",
                        placeholder="e.g., Tax Amount, Payment Method"
                    )
                    st.markdown(
                        "<small style='color: gray;'>The value in the 'Enter new or edit' box will be used.</small>",
                        unsafe_allow_html=True
                    )

                with cols_meta[1]:
                    meta_entry['value'] = st.text_input(
                        "Metadata Value",
                        value=meta_entry['value'],
                        key=f"{selected_transaction_type}_meta_value_{i}",
                        placeholder="e.g., 5.25, Credit Card"
                    )
        # End of Additional Metadata Section

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

                # Validate metadata entries
                cleaned_metadata = []
                for meta_entry in st.session_state.manual_metadata_entries:
                    key = meta_entry['key'].strip()  # Use the text input value for the key
                    value = meta_entry['value'].strip()
                    if key and value:  # Only add if both key and value are non-empty
                        cleaned_metadata.append({'key': key, 'value': value})
                    elif key or value:  # If one is present but not the other
                        st.warning(
                            f"Metadata field found with only a key or a value (Key: '{key}', Value: '{value}'). Ignoring incomplete entry.")

                # Assign cleaned metadata back to session state to reflect what will be saved
                st.session_state.global_transaction_data['manual_metadata'] = cleaned_metadata

                for i, split_data in enumerate(st.session_state[split_key]):
                    if split_data['amount'] <= 0:
                        st.error(f"Split {i + 1}: Amount must be positive.")
                        is_valid = False
                    if not split_data['description']:
                        st.error(f"Split {i + 1}: Description is required.")
                        is_valid = False
                    # Check if full_budget_path is not just the scope
                    if not split_data['full_budget_path'] or split_data['full_budget_path'].count(
                            ':') < 1:  # Ensure at least Scope:Category
                        st.error(f"Split {i + 1}: A specific category path (e.g., Scope:Category) is required.")
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
                            splits_for_manager.append({
                                'amount': split_data['amount'],
                                'description': split_data['description'],
                                'notes': split_data['notes'],
                                'payee': st.session_state.global_transaction_data['payee'],
                                'account': st.session_state.global_transaction_data['account'],
                                'budget_scope': split_data['budget_scope'],
                                'category': split_data['category'],
                                'sub_category': split_data['sub_category'],
                                'full_budget_path': split_data['full_budget_path']
                            })

                        # Pass the collected metadata to the transaction manager
                        transaction_manager.add_manual_transaction(
                            transaction_id=st.session_state.current_transaction_id,
                            transaction_type=selected_transaction_type,
                            date=st.session_state.global_transaction_data['date'],
                            payee=st.session_state.global_transaction_data['payee'],
                            account=st.session_state.global_transaction_data['account'],
                            uploaded_file=uploaded_file,
                            splits=splits_for_manager,
                            manual_metadata=st.session_state.global_transaction_data['manual_metadata']
                            # Pass the validated list
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
                            'date': datetime.date.today(), 'payee': '', 'account': '', 'uploaded_file': None,
                            'manual_metadata': []  # Reset metadata after successful submission
                        }
                        # Clear category selector state for transfer
                        for key in list(st.session_state.keys()):
                            if '_cat_ui' in key:
                                del st.session_state[key]
                        # Reset the metadata input fields by clearing their session state
                        if 'manual_metadata_entries' in st.session_state:
                            del st.session_state['manual_metadata_entries']

                        st.session_state.current_transaction_id = f"TRN-{int(datetime.datetime.now().timestamp())}-{uuid.uuid4().hex[:6].upper()}"
                        st.rerun()

                    except Exception as e:
                        st.error(f"Failed to save {selected_transaction_type} transaction: {e}")

    elif selected_transaction_type == "Transfer":
        st.markdown("---")
        st.subheader("Transfer Details")

        if 'transfer_data' not in st.session_state:
            st.session_state.transfer_data = {
                'date': datetime.date.today(),
                'amount': 0.0,
                'source_account': '',
                'destination_account': '',
                'description': '',
                'notes': '',
                'budget_scope': '',
                'category': '',
                'sub_category': '',
                'full_budget_path': ''
            }
            # Initialize transfer category UI session state with a default if 'Transfer' scope exists
            # This ensures a default path like 'Transfer:Transfer' is pre-selected if available
            if 'Transfer' in structured_categories:
                st.session_state['transfer_cat_ui_budget_scope'] = "Transfer"
                st.session_state['transfer_cat_ui_category_path_elements'] = ["Transfer",
                                                                              "Transfer"]  # Default to Transfer:Transfer
                st.session_state['transfer_cat_ui_full_budget_path'] = "Transfer:Transfer"
            else:  # Fallback if 'Transfer' scope is not defined in financial_config
                st.session_state['transfer_cat_ui_budget_scope'] = ""
                st.session_state['transfer_cat_ui_category_path_elements'] = []
                st.session_state['transfer_cat_ui_full_budget_path'] = ""

            st.rerun()

        st.session_state.transfer_data['date'] = st.date_input(
            "Date",
            st.session_state.transfer_data['date'],
            key="transfer_date_input"
        )

        col1, col2 = st.columns(2)
        with col1:
            st.session_state.transfer_data['amount'] = st.number_input(
                "Amount",
                min_value=0.0,
                format="%.2f",
                value=st.session_state.transfer_data['amount'],
                key="transfer_amount_outside"
            )

            # Source Account Selector
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
            # Destination Account Selector
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

            st.write("Category for this transfer:")
            # Use full structured_categories for transfers
            # Allow selection from all available scopes, user can choose 'Transfer' or another relevant category
            _display_dynamic_category_selector_ui(
                structured_categories,
                config_manager.get_all_budget_scopes(),  # Pass all top-level scopes
                session_state_key_prefix="transfer_cat_ui",
            )
            # Update transfer_data with values from the category selector's session state
            current_full_path_transfer = st.session_state.get("transfer_cat_ui_full_budget_path", "")
            st.session_state.transfer_data['full_budget_path'] = current_full_path_transfer

            full_path_parts_transfer = current_full_path_transfer.split(':')
            st.session_state.transfer_data['budget_scope'] = full_path_parts_transfer[0] if len(
                full_path_parts_transfer) > 0 else ""
            st.session_state.transfer_data['category'] = full_path_parts_transfer[1] if len(
                full_path_parts_transfer) > 1 else ""
            st.session_state.transfer_data['sub_category'] = full_path_parts_transfer[2] if len(
                full_path_parts_transfer) > 2 else ""

        # --- Additional Metadata Section for Transfers ---
        # Initialize manual_metadata_entries if not present, including a placeholder for selected key
        if 'manual_metadata_entries' not in st.session_state:  # Use the same metadata state as for splits
            st.session_state.manual_metadata_entries = [{'key': '', 'value': '', '_selected_from_list_key': ''}]

        with st.expander("Additional Metadata (Optional)"):
            col_meta_btns = st.columns([1, 1, 3])
            with col_meta_btns[0]:
                if st.button("Add Metadata Field", key="transfer_add_meta_btn"):
                    st.session_state.manual_metadata_entries.append(
                        {'key': '', 'value': '', '_selected_from_list_key': ''})
                    st.rerun()
            with col_meta_btns[1]:
                if len(st.session_state.manual_metadata_entries) > 1:
                    if st.button("Remove Last Metadata Field", key="transfer_remove_meta_btn"):
                        st.session_state.manual_metadata_entries.pop()
                        st.rerun()

            for i, meta_entry in enumerate(st.session_state.manual_metadata_entries):
                cols_meta = st.columns([1, 1])
                with cols_meta[0]:
                    # Selectbox for existing keys
                    selected_key_from_list = st.selectbox(
                        "Metadata Key (Select existing)",
                        all_unique_metadata_keys,
                        index=all_unique_metadata_keys.index(meta_entry['_selected_from_list_key']) if meta_entry[
                                                                                                           '_selected_from_list_key'] in all_unique_metadata_keys else 0,
                        placeholder="Choose from existing keys...",
                        key=f"transfer_meta_key_selectbox_{i}"
                    )
                    # If selection from box changes AND it's different from current text input, update text input
                    if selected_key_from_list and selected_key_from_list != meta_entry['_selected_from_list_key']:
                        meta_entry['_selected_from_list_key'] = selected_key_from_list  # Update internal tracker
                        meta_entry['key'] = selected_key_from_list  # Set the actual key to selected value
                        st.rerun()  # Rerun to update the text input

                    # Text input for new/edited key (takes precedence)
                    meta_entry['key'] = st.text_input(
                        "Metadata Key (Enter new or edit)",
                        value=meta_entry['key'],
                        key=f"transfer_meta_key_textinput_{i}",
                        placeholder="e.g., Transfer Fee, Reason"
                    )
                    st.markdown(
                        "<small style='color: gray;'>The value in the 'Enter new or edit' box will be used.</small>",
                        unsafe_allow_html=True
                    )
                with cols_meta[1]:
                    meta_entry['value'] = st.text_input(
                        "Metadata Value",
                        value=meta_entry['value'],
                        key=f"transfer_meta_value_{i}",
                        placeholder="e.g., 0.50, Investment"
                    )
        # End of Additional Metadata Section

        with st.form(key="transfer_submission_form"):
            st.write("Click 'Save Transfer' to finalize your entry.")
            submitted = st.form_submit_button("Save Transfer")

            if submitted:
                amount = st.session_state.transfer_data['amount']
                source_account_name = st.session_state.transfer_data['source_account']
                destination_account_name = st.session_state.transfer_data['destination_account']
                description = st.session_state.transfer_data['description']
                notes = st.session_state.transfer_data['notes']
                # The payee for a transfer can be set to the overall payee or a default
                transfer_payee = st.session_state.global_transaction_data['payee']
                if not transfer_payee:  # If overall payee was not entered for transfer, use a generic one
                    transfer_payee = f"Transfer to {destination_account_name}" if destination_account_name else "Transfer"

                is_valid = True
                if amount <= 0 or not source_account_name or not destination_account_name:
                    st.error("A positive Amount, 'From Account', and 'To Account' are required for Transfer.")
                    is_valid = False
                elif source_account_name == destination_account_name:
                    st.error("Source and Destination accounts cannot be the same for Transfer.")
                    is_valid = False
                # Validate the selected transfer path
                elif not st.session_state.transfer_data['full_budget_path'] or \
                        st.session_state.transfer_data['full_budget_path'].count(
                            ':') < 1:  # Ensure at least Scope:Category
                    st.error(
                        "A valid budget path (e.g., 'Transfer:Transfer' or 'Personal:Savings') is required for transfers.")
                    is_valid = False

                # Validate metadata entries
                cleaned_metadata = []
                for meta_entry in st.session_state.manual_metadata_entries:
                    key = meta_entry['key'].strip()
                    value = meta_entry['value'].strip()
                    if key and value:  # Only add if both key and value are non-empty
                        cleaned_metadata.append({'key': key, 'value': value})
                    elif key or value:  # If one is present but not the other
                        st.warning(
                            f"Metadata field found with only a key or a value (Key: '{key}', Value: '{value}'). Ignoring incomplete entry.")

                # Assign cleaned metadata back to session state to reflect what will be saved
                st.session_state.global_transaction_data['manual_metadata'] = cleaned_metadata

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
                            date=st.session_state.transfer_data['date'],
                            payee=transfer_payee,
                            account=source_account_name,
                            uploaded_file=uploaded_file,
                            splits=transfer_splits,
                            manual_metadata=st.session_state.global_transaction_data['manual_metadata']
                            # Pass the validated list
                        )
                        st.success(
                            f"Transfer transaction saved successfully with ID: **{related_transaction_id_for_transfer}**")

                        # Reset form fields and session state after successful submission
                        st.session_state.transfer_data = {
                            'date': datetime.date.today(), 'amount': 0.0, 'source_account': '',
                            'destination_account': '',
                            'description': '', 'notes': '',
                            'budget_scope': '', 'category': '', 'sub_category': '',
                            'full_budget_path': ''
                        }
                        st.session_state.global_transaction_data = {
                            'date': datetime.date.today(), 'payee': '', 'account': '', 'uploaded_file': None,
                            'manual_metadata': []  # Reset metadata after successful submission
                        }
                        # Clear category selector state for transfer
                        for key in list(st.session_state.keys()):
                            if 'transfer_cat_ui' in key:
                                del st.session_state[key]
                        # Reset the metadata input fields by clearing their session state
                        if 'manual_metadata_entries' in st.session_state:
                            del st.session_state['manual_metadata_entries']

                        st.session_state.current_transaction_id = f"TRN-{int(datetime.datetime.now().timestamp())}-{uuid.uuid4().hex[:6].upper()}"
                        st.rerun()

                    except Exception as e:
                        st.error(f"Failed to save Transfer transaction: {e}")

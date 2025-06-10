# modules/ui_tabs/manual_entry_tab.py

import streamlit as st
import datetime
import uuid
from modules.managers.transaction_manager import TransactionManager
from modules.managers.finance_config_manager import FinanceConfigManager
from modules.managers.payee_manager import PayeeManager  # Import the new manager


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
        structured_categories: dict,
        scope_options: list,
        session_state_key_prefix: str,  # Unique prefix for session state keys
        is_transfer: bool = False
) -> None:
    """
    Displays dynamic category selection UI elements (scope, main, sub)
    and stores their state in st.session_state using the given prefix.
    This function should be called OUTSIDE of st.form.
    """
    # Initialize session state for this selector if not present
    if f'{session_state_key_prefix}_budget_scope' not in st.session_state:
        st.session_state[f'{session_state_key_prefix}_budget_scope'] = ''
    if f'{session_state_key_prefix}_categories_in_path' not in st.session_state:
        st.session_state[f'{session_state_key_prefix}_categories_in_path'] = []
    if f'{session_state_key_prefix}_subcategory' not in st.session_state:
        st.session_state[f'{session_state_key_prefix}_subcategory'] = ''
    if f'{session_state_key_prefix}_full_budget_path' not in st.session_state:
        st.session_state[f'{session_state_key_prefix}_full_budget_path'] = ''

    # Get current values from session state for pre-selection
    current_scope = st.session_state[f'{session_state_key_prefix}_budget_scope']
    current_path = st.session_state[f'{session_state_key_prefix}_categories_in_path']
    current_sub = st.session_state[f'{session_state_key_prefix}_subcategory']

    display_scope_options = [''] + scope_options
    initial_scope_idx = display_scope_options.index(current_scope) if current_scope in display_scope_options else 0

    selected_scope_ui = st.selectbox(
        "Budget Scope",
        display_scope_options,
        index=initial_scope_idx,
        placeholder="Choose a budget scope...",
        key=f"{session_state_key_prefix}_scope_selection"
    )

    # Reset subsequent selections if scope changes (Streamlit handles this naturally with new value)
    if selected_scope_ui != current_scope:
        st.session_state[f'{session_state_key_prefix}_categories_in_path'] = []
        st.session_state[f'{session_state_key_prefix}_subcategory'] = ''
        st.session_state[f'{session_state_key_prefix}_full_budget_path'] = selected_scope_ui  # Update path start
        st.session_state[f'{session_state_key_prefix}_budget_scope'] = selected_scope_ui
        st.rerun()  # Rerun to update subsequent selectboxes

    st.session_state[f'{session_state_key_prefix}_budget_scope'] = selected_scope_ui
    full_budget_path_accumulator = selected_scope_ui

    current_level_dict = structured_categories.get(selected_scope_ui, {})

    selected_categories_path_list_temp = []  # Temp list for current selection in this rerun

    level_num = 1
    while True:
        if isinstance(current_level_dict, dict) and current_level_dict.keys():
            level_options = list(current_level_dict.keys())

            # Try to pre-select if value exists in current_path (from session state)
            prev_level_val = ""
            if len(current_path) >= level_num:
                prev_level_val = current_path[level_num - 1]

            initial_level_idx = level_options.index(prev_level_val) if prev_level_val in level_options else 0

            selected_category_at_level = st.selectbox(
                f"Category Level {level_num}",
                level_options,
                index=initial_level_idx,
                placeholder=f"Choose a category for level {level_num}...",
                key=f"{session_state_key_prefix}_cat_level_{level_num}_selection"
            )

            # If selection changes, reset deeper levels and rerun
            current_category_at_level_in_path = current_path[level_num - 1] if len(current_path) >= level_num else None
            if selected_category_at_level != current_category_at_level_in_path:
                # Update current_path up to this level
                st.session_state[
                    f'{session_state_key_prefix}_categories_in_path'] = selected_categories_path_list_temp + (
                    [selected_category_at_level] if selected_category_at_level else [])
                st.session_state[f'{session_state_key_prefix}_subcategory'] = ''  # Clear subcategory
                st.session_state[f'{session_state_key_prefix}_full_budget_path'] = full_budget_path_accumulator + (
                    f"/{selected_category_at_level}" if selected_category_at_level else "")
                if selected_category_at_level:
                    st.rerun()  # Rerun to update next level selectbox
                else:
                    break  # User cleared selection, stop going deeper

            if selected_category_at_level:
                selected_categories_path_list_temp.append(selected_category_at_level)
                full_budget_path_accumulator += f"/{selected_category_at_level}"
                current_level_dict = current_level_dict.get(selected_category_at_level, {})
                level_num += 1
            else:
                break  # User stopped selecting at this level
        elif isinstance(current_level_dict, list) and current_level_dict:
            # If it's a list, these are the subcategories (leaf nodes in the config)
            initial_sub_idx = current_level_dict.index(current_sub) if current_sub in current_level_dict else 0

            selected_subcategory = st.selectbox(
                "SubCategory",
                current_level_dict,
                index=initial_sub_idx,
                placeholder="Choose a subcategory (optional)...",
                key=f"{session_state_key_prefix}_sub_cat_selection"
            )
            # Update session state if subcategory changes
            if selected_subcategory != current_sub:
                st.session_state[f'{session_state_key_prefix}_subcategory'] = selected_subcategory
                st.session_state[f'{session_state_key_prefix}_full_budget_path'] = full_budget_path_accumulator + (
                    f"/{selected_subcategory}" if selected_subcategory else "")
                st.rerun()  # Rerun to update full path display

            if selected_subcategory:
                full_budget_path_accumulator += f"/{selected_subcategory}"
            break
        else:
            break

    # Final update of session state values after all selections for this rerun
    st.session_state[f'{session_state_key_prefix}_categories_in_path'] = selected_categories_path_list_temp
    st.session_state[f'{session_state_key_prefix}_full_budget_path'] = full_budget_path_accumulator

    # Set default values for transfer/income if nothing else was picked
    if is_transfer and not st.session_state[f'{session_state_key_prefix}_budget_scope']:
        st.session_state[f'{session_state_key_prefix}_budget_scope'] = "Transfer"
        st.session_state[f'{session_state_key_prefix}_categories_in_path'] = ["Transfer"]
        st.session_state[f'{session_state_key_prefix}_subcategory'] = ""
        st.session_state[f'{session_state_key_prefix}_full_budget_path'] = "Transfer"
    elif st.session_state[f'{session_state_key_prefix}_budget_scope'] == "Income" and not st.session_state[
        f'{session_state_key_prefix}_categories_in_path']:
        st.session_state[f'{session_state_key_prefix}_categories_in_path'] = ["Uncategorized Income"]
        st.session_state[f'{session_state_key_prefix}_full_budget_path'] = "Income/Uncategorized Income"

    st.markdown(
        f"**Selected Budget Path:** `{st.session_state[f'{session_state_key_prefix}_full_budget_path'] if st.session_state[f'{session_state_key_prefix}_full_budget_path'] else 'None'}`")


# --- Main Display Function ---

def display_manual_entry_tab(transaction_manager: TransactionManager, config_manager: FinanceConfigManager):
    """
    Displays the UI for manually entering a transaction with dynamic fields
    based on transaction type (Expense, Income, Transfer).
    """
    st.header("Enter Transaction Details Manually")

    account_options = _get_account_options(config_manager)
    structured_categories = config_manager.get_category_structure_for_ui()
    transaction_types = ["Expense", "Income", "Transfer"]

    # Get existing payee names from the transaction_manager's payee_manager
    existing_payee_names = transaction_manager.payee_manager.get_all_payee_names()
    # Add an empty string to options to allow for no initial selection/placeholder
    payee_options = [''] + existing_payee_names

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

    st.session_state.global_transaction_data['date'] = st.date_input(
        "Date",
        st.session_state.global_transaction_data['date'],
        key="general_date"
    )

    # --- Payee field using st.selectbox with accept_new_options ---
    current_payee_value = st.session_state.global_transaction_data['payee']
    # Ensure current_payee_value is in payee_options to set the index correctly, or default to 0
    initial_payee_idx = payee_options.index(current_payee_value) if current_payee_value in payee_options else 0

    selected_payee = st.selectbox(
        "Payer/Payee (Overall)",
        payee_options,
        index=initial_payee_idx,
        placeholder="Type or select a payee (e.g., Supermarket, Monthly Salary)",
        key="general_payee_selectbox",
        accept_new_options=True  # Allows typing new options
    )
    st.session_state.global_transaction_data['payee'] = selected_payee

    # Account field for the overall transaction
    initial_account_display = f"{st.session_state.global_transaction_data['account']} ({_get_account_type_for_display(st.session_state.global_transaction_data['account'], config_manager)})" if \
    st.session_state.global_transaction_data['account'] else None
    account_idx = account_options.index(initial_account_display) if initial_account_display in account_options else None

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

        if split_key not in st.session_state or st.session_state.get(
                'last_selected_transaction_type') != selected_transaction_type:
            st.session_state[split_key] = [{
                'amount': 0.0,
                'description': '',
                'notes': '',
                'budget_scope': '', 'category': '', 'sub_category': '',
                'full_budget_path': '', 'categories_in_path': []
            }]
            st.session_state['last_selected_transaction_type'] = selected_transaction_type

        col_split_btns = st.columns([1, 1, 3])
        with col_split_btns[0]:
            if st.button("Add Another Split", key=f"{selected_transaction_type}_add_split_btn_outside"):
                st.session_state[split_key].append({
                    'amount': 0.0, 'description': '', 'notes': '',
                    'budget_scope': '', 'category': '', 'sub_category': '',
                    'full_budget_path': '', 'categories_in_path': []
                })
                st.rerun()
        with col_split_btns[1]:
            if len(st.session_state[split_key]) > 1:
                if st.button("Remove Last Split", key=f"{selected_transaction_type}_remove_split_btn_outside"):
                    prefix_to_clear = f"{selected_transaction_type}_split_{len(st.session_state[split_key]) - 1}_cat_ui"
                    if f'{prefix_to_clear}_budget_scope' in st.session_state:
                        del st.session_state[f'{prefix_to_clear}_budget_scope']
                        del st.session_state[f'{prefix_to_clear}_categories_in_path']
                        del st.session_state[f'{prefix_to_clear}_subcategory']
                        del st.session_state[f'{prefix_to_clear}_full_budget_path']

                    st.session_state[split_key].pop()
                    st.rerun()

        total_amount_sum = 0.0
        st.session_state[f'{selected_transaction_type.lower()}_current_split_values'] = []

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
            scope_opts = config_manager.get_budget_scopes() if selected_transaction_type == "Expense" else ["Income"]

            _display_dynamic_category_selector_ui(
                structured_categories,
                scope_opts,
                session_state_key_prefix=f"{selected_transaction_type}_split_{i}_cat_ui",
                is_transfer=False
            )
            split_data['budget_scope'] = st.session_state[f"{selected_transaction_type}_split_{i}_cat_ui_budget_scope"]
            split_data['category'] = \
            st.session_state[f"{selected_transaction_type}_split_{i}_cat_ui_categories_in_path"][0] if st.session_state[
                f"{selected_transaction_type}_split_{i}_cat_ui_categories_in_path"] else ""
            split_data['sub_category'] = st.session_state[f"{selected_transaction_type}_split_{i}_cat_ui_subcategory"]
            split_data['full_budget_path'] = st.session_state[
                f"{selected_transaction_type}_split_{i}_cat_ui_full_budget_path"]

            st.session_state[f'{selected_transaction_type.lower()}_current_split_values'].append(split_data)
            st.markdown("---")

        st.markdown(f"**Calculated Total Amount for Splits: ${total_amount_sum:.2f}**")

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

                for i, split_data in enumerate(
                        st.session_state[f'{selected_transaction_type.lower()}_current_split_values']):
                    if split_data['amount'] <= 0 or not split_data['category'] or not split_data['description']:
                        st.error(f"Split {i + 1}: positive Amount, Description, and Category are required.")
                        is_valid = False

                if is_valid:
                    try:
                        splits_for_manager = []
                        for split_data in st.session_state[f'{selected_transaction_type.lower()}_current_split_values']:
                            splits_for_manager.append({
                                'amount': split_data['amount'],
                                'description': split_data['description'],
                                'notes': split_data['notes'],
                                'budget_scope': split_data['budget_scope'],
                                'category': split_data['category'],
                                'sub_category': split_data['sub_category'],
                                'full_budget_path': split_data['full_budget_path']
                            })

                        transaction_manager.add_manual_transaction(
                            transaction_id=st.session_state.current_transaction_id,
                            transaction_type=selected_transaction_type,
                            date=st.session_state.global_transaction_data['date'],
                            payee=st.session_state.global_transaction_data['payee'],
                            account=st.session_state.global_transaction_data['account'],
                            uploaded_file=uploaded_file,
                            splits=splits_for_manager
                        )
                        st.success(
                            f"{selected_transaction_type} transaction saved successfully with ID: **{st.session_state.current_transaction_id}**")

                        st.session_state[split_key] = [{
                            'amount': 0.0, 'description': '', 'notes': '',
                            'budget_scope': '', 'category': '', 'sub_category': '',
                            'full_budget_path': '', 'categories_in_path': []
                        }]
                        st.session_state.global_transaction_data = {
                            'date': datetime.date.today(), 'payee': '', 'account': '', 'uploaded_file': None
                        }
                        for i in range(
                                len(st.session_state[f'{selected_transaction_type.lower()}_current_split_values'])):
                            prefix_to_clear = f"{selected_transaction_type}_split_{i}_cat_ui"
                            if f'{prefix_to_clear}_budget_scope' in st.session_state:
                                del st.session_state[f'{prefix_to_clear}_budget_scope']
                                del st.session_state[f'{prefix_to_clear}_categories_in_path']
                                del st.session_state[f'{prefix_to_clear}_subcategory']
                                del st.session_state[f'{prefix_to_clear}_full_budget_path']

                        st.session_state.current_transaction_id = f"TRN-{int(datetime.datetime.now().timestamp())}-{uuid.uuid4().hex[:6].upper()}"
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save {selected_transaction_type} transaction: {e}")

    elif selected_transaction_type == "Transfer":
        st.markdown("---")
        st.subheader("Transfer Details")

        if 'transfer_data' not in st.session_state or st.session_state.get(
                'last_selected_transaction_type') != selected_transaction_type:
            st.session_state.transfer_data = {
                'amount': 0.0,
                'source_account': '',
                'destination_account': '',
                'description': '',
                'notes': '',
                'budget_scope': '',
                'main_category': '',
                'sub_category': '',
                'full_budget_path': '',
                'categories_in_path': []
            }
            st.session_state['last_selected_transaction_type'] = selected_transaction_type

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
            source_acc_idx = account_options.index(
                initial_source_acc_display) if initial_source_acc_display in account_options else None

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
            transfer_scope_opts = [''] + config_manager.get_budget_scopes()

            _display_dynamic_category_selector_ui(
                structured_categories,
                transfer_scope_opts,
                session_state_key_prefix="transfer_cat_ui",
                is_transfer=True
            )
            st.session_state.transfer_data['budget_scope'] = st.session_state["transfer_cat_ui_budget_scope"]
            st.session_state.transfer_data['main_category'] = st.session_state["transfer_cat_ui_categories_in_path"][
                0] if st.session_state["transfer_cat_ui_categories_in_path"] else ""
            st.session_state.transfer_data['sub_category'] = st.session_state["transfer_cat_ui_subcategory"]
            st.session_state.transfer_data['full_budget_path'] = st.session_state["transfer_cat_ui_full_budget_path"]

            initial_dest_acc_display = f"{st.session_state.transfer_data['destination_account']} ({_get_account_type_for_display(st.session_state.transfer_data['destination_account'], config_manager)})" if \
            st.session_state.transfer_data['destination_account'] else None
            dest_acc_idx = account_options.index(
                initial_dest_acc_display) if initial_dest_acc_display in account_options else None

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

                is_valid = True
                if amount <= 0 or not source_account_name or not destination_account_name:
                    st.error("A positive Amount, From Account, and To Account are required for Transfer.")
                    is_valid = False
                elif source_account_name == destination_account_name:
                    st.error("Source and Destination accounts cannot be the same for Transfer.")
                    is_valid = False

                if is_valid:
                    try:
                        related_transaction_id_for_transfer = st.session_state.current_transaction_id

                        overall_payee = st.session_state.global_transaction_data['payee']

                        transfer_splits = [
                            {
                                'payee': overall_payee,
                                'amount': -amount,
                                'account': source_account_name,
                                'description': st.session_state.transfer_data['description'],
                                'notes': st.session_state.transfer_data['notes'],
                                'budget_scope': st.session_state.transfer_data['budget_scope'],
                                'category': st.session_state.transfer_data['main_category'] if
                                st.session_state.transfer_data['main_category'] else "Transfer Out",
                                'sub_category': st.session_state.transfer_data['sub_category'],
                                'full_budget_path': st.session_state.transfer_data['full_budget_path'] if
                                st.session_state.transfer_data['full_budget_path'] else "Transfer/Transfer Out"
                            },
                            {
                                'payee': overall_payee,
                                'amount': amount,
                                'account': destination_account_name,
                                'description': st.session_state.transfer_data['description'],
                                'notes': st.session_state.transfer_data['notes'],
                                'budget_scope': st.session_state.transfer_data['budget_scope'],
                                'category': st.session_state.transfer_data['main_category'] if
                                st.session_state.transfer_data['main_category'] else "Transfer In",
                                'sub_category': st.session_state.transfer_data['sub_category'],
                                'full_budget_path': st.session_state.transfer_data['full_budget_path'] if
                                st.session_state.transfer_data['full_budget_path'] else "Transfer/Transfer In"
                            }
                        ]

                        transaction_manager.add_manual_transaction(
                            transaction_id=related_transaction_id_for_transfer,
                            transaction_type="Transfer",
                            date=st.session_state.global_transaction_data['date'],
                            payee=st.session_state.global_transaction_data['payee'],
                            account="",  # Account is split-specific for transfers
                            uploaded_file=uploaded_file,
                            splits=transfer_splits,
                            related_transaction_id=related_transaction_id_for_transfer
                        )
                        st.success(
                            f"Transfer of ${amount:.2f} from {source_account_name} to {destination_account_name} saved successfully!")

                        st.session_state.transfer_data = {
                            'amount': 0.0, 'source_account': '', 'destination_account': '',
                            'description': '', 'notes': '',
                            'budget_scope': '', 'main_category': '', 'sub_category': '',
                            'full_budget_path': '', 'categories_in_path': []
                        }
                        st.session_state.global_transaction_data = {
                            'date': datetime.date.today(), 'payee': '', 'account': '', 'uploaded_file': None
                        }
                        if 'transfer_cat_ui_budget_scope' in st.session_state:
                            del st.session_state['transfer_cat_ui_budget_scope']
                            del st.session_state['transfer_cat_ui_categories_in_path']
                            del st.session_state['transfer_cat_ui_subcategory']
                            del st.session_state['transfer_cat_ui_full_budget_path']

                        st.session_state.current_transaction_id = f"TRN-{int(datetime.datetime.now().timestamp())}-{uuid.uuid4().hex[:6].upper()}"
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save transfer: {e}")

# TODO: Try to save income and transfer. Seems Good. Expense works
# TODO: Add streamlit-textcomplete or steamlit-searchbox to add autocompletion to the payee/payer field.
# TODO: Add workaround for payee/payer field that does not show the user the keyboard.
#  Gemini propose using a radio button for add new payee and select payee, which will display relavant fields

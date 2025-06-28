# modules/ui_tabs/manual_entry_tab.py

import streamlit as st
import datetime
import uuid
from typing import Dict, List, Any, Optional
import pandas as pd

from modules.managers.transaction_manager import TransactionManager
from modules.managers.finance_config_manager import FinanceConfigManager
from modules.managers.payee_manager import PayeeManager
from modules.managers.app_config_manager import AppConfigManager
from modules.managers.csv_manager import CSVManager
from modules.managers.metadata_manager import MetadataManager


# No longer directly import VendorConfigManager, it's accessed via transaction_manager


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

    current_level_dict = structured_categories.get(selected_scope_ui, {})

    # Start with scope for path elements. This will be built up as user selects deeper categories.
    selected_category_path_list_temp = [selected_scope_ui] if selected_scope_ui else []

    level_num = 1
    # Loop to dynamically create selectboxes for nested categories
    while True:
        if isinstance(current_level_dict, dict) and current_level_dict:  # If there are more levels
            level_options = [''] + sorted(list(current_level_dict.keys()))

            # Determine the value to pre-select for this level
            prev_level_val = ""
            # current_path_elements now includes the scope as the first element if selected
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
                # Construct new_path_elements from the beginning up to the current level.
                # Take the path elements BEFORE the current level's original selection from current_path_elements.
                new_path_elements = current_path_elements[:level_num]
                if selected_category_at_level:
                    new_path_elements.append(selected_category_at_level)

                st.session_state[f'{session_state_key_prefix}_category_path_elements'] = new_path_elements
                st.session_state[f'{session_state_key_prefix}_full_budget_path'] = ":".join(new_path_elements)

                if selected_category_at_level:  # Only rerun if a selection was made (not cleared)
                    st.rerun()
                else:  # User cleared selection at this level
                    # If cleared, the path elements should be truncated at the previous level
                    st.session_state[f'{session_state_key_prefix}_category_path_elements'] = new_path_elements
                    st.session_state[f'{session_state_key_prefix}_full_budget_path'] = ":".join(new_path_elements)
                    break  # Stop going deeper

            if selected_category_at_level:
                selected_category_path_list_temp.append(selected_category_at_level)
                # Prepare for next iteration: move to the sub-dictionary
                current_level_dict = current_level_dict.get(selected_category_at_level, {})
                level_num += 1
            else:  # No selection at this level, or current level is not a dictionary (e.g., it's a leaf node {})
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


# --- Caching the metadata keys loading directly from CSV path or via manager ---
@st.cache_data
def _get_all_unique_metadata_keys(_metadata_manager: MetadataManager) -> List[str]:
    """
    Retrieves all unique metadata keys from the metadata.csv file via the MetadataManager.
    This function is cached to avoid re-reading the CSV on every rerun.
    It takes the MetadataManager instance, but its internal hashability
    depends on Streamlit's ability to hash the manager or the manager's
    dependency on the underlying file being monitored by Streamlit.
    """
    try:
        metadata_keys = _metadata_manager.get_all_unique_metadata_keys()
        if len(metadata_keys) > 0:
            return [''] + metadata_keys
        return ['']
    except Exception as e:
        st.warning(f"Could not load existing metadata keys: {e}. Starting with empty list.")
        return ['']


# --- Callback for Payee text input changes ---
def _handle_payee_input_change(transaction_manager: TransactionManager):
    """
    Callback function triggered when the payee text input's value changes due to user typing.
    Performs fuzzy matching and stores suggestion in session state.
    """
    # Get the raw input directly from the widget's key, not from global_transaction_data['payee']
    raw_payee_input = st.session_state.get("general_payee_text_input", "").strip()

    # Store the raw input separately, this will be used for displaying the original text
    st.session_state.raw_payee_input_original = raw_payee_input

    if not raw_payee_input:
        st.session_state.payee_suggestion_result = None
        st.session_state.payee_decision_made = True  # No decision needed if input is empty
        # If input is empty, also clear the current payee so it doesn't hold old value
        st.session_state.global_transaction_data['payee'] = ''
        return

    # Get config thresholds from app_config
    # llm_config = app_config_manager.get_app_settings().get('llm_config', {})
    # # Using the new threshold names from app_config.yaml
    # llm_similarity_threshold = llm_config.get('vendor_fuzzy_match_threshold', 0.85)
    # llm_ambiguity_threshold = llm_config.get('vendor_fuzzy_match_ambiguity_threshold', 0.65)

    vendor_config_manager = transaction_manager.vendor_config_manager

    # Call the new suggestion method from vendor_config_manager
    suggestion_result = vendor_config_manager.suggest_conformed_payee(raw_payee_input)

    st.session_state.payee_suggestion_result = suggestion_result
    st.session_state.payee_decision_made = False  # Reset decision on new input, assume user needs to confirm

    # Determine what to do based on the suggestion status
    if suggestion_result['status'] in ['HIGH_CONFIDENCE', 'EXACT_MATCH']:
        # If high confidence or exact match, auto-accept and set the conformed name
        st.session_state.payee_decision_made = True
        st.session_state.global_transaction_data['payee'] = suggestion_result['suggested_conformed_name']
        print(f"Auto-conformed '{raw_payee_input}' to '{suggestion_result['suggested_conformed_name']}'.")
    elif suggestion_result['status'] == 'AMBIGUOUS':
        # For ambiguous, set the suggested name as the current payee (for pre-filling if accepted)
        # but keep payee_decision_made = False to prompt user interaction.
        st.session_state.global_transaction_data['payee'] = suggestion_result['suggested_conformed_name']
        st.session_state.payee_decision_made = False
        print(
            f"Ambiguous match for '{raw_payee_input}'. Suggested: '{suggestion_result['suggested_conformed_name']}'. User decision required.")
    else:  # NO_MATCH
        # No high-confidence or ambiguous match, use raw input, consider it decided (as a new payee)
        st.session_state.payee_decision_made = True
        st.session_state.global_transaction_data['payee'] = raw_payee_input
        print(f"No strong match for '{raw_payee_input}'. Will use as new payee.")


def _handle_payee_selection_from_list(transaction_manager: TransactionManager, app_config_manager: AppConfigManager):
    """
    Callback function triggered when a payee is selected from the selectbox.
    Updates the text input value and triggers fuzzy matching logic.
    """
    selected_payee_from_list = st.session_state.general_payee_list_selectbox

    if selected_payee_from_list:
        st.session_state.global_transaction_data['payee'] = selected_payee_from_list
        st.session_state['general_payee_text_input'] = selected_payee_from_list
        st.session_state.payee_decision_made = True
        st.session_state.raw_payee_input_original = selected_payee_from_list
        st.session_state.payee_suggestion_result = None
    else:
        st.session_state.global_transaction_data['payee'] = ''
        st.session_state['general_payee_text_input'] = ''
        st.session_state.payee_suggestion_result = None
        st.session_state.payee_decision_made = True
        st.session_state.raw_payee_input_original = ''

    st.rerun()


def _populate_form_from_extracted_data(extracted_data: Dict[str, Any]):
    """
    Populates the Streamlit form fields with data extracted from an invoice,
    respecting user-prefilled fields where appropriate.
    """
    # Preserve current state before populating from extracted data
    current_global_data = st.session_state.global_transaction_data
    current_splits = st.session_state.get('expense_splits') or st.session_state.get('income_splits')
    current_metadata_entries = st.session_state.get('manual_metadata_entries', [])

    # Date
    if extracted_data.get('date') and not current_global_data.get('date') == extracted_data['date']:
        st.session_state.global_transaction_data['date'] = extracted_data['date']

    # Payee: Prioritize user's manual input if it exists, otherwise use extracted
    extracted_payee = extracted_data.get('payee', '')
    if not current_global_data.get('payee') and extracted_payee:  # If user's payee is empty
        st.session_state.global_transaction_data['payee'] = extracted_payee
        st.session_state['general_payee_text_input'] = extracted_payee  # Also set text input's key
        st.session_state.raw_payee_input_original = extracted_payee  # Treat extracted as original input
        st.session_state.payee_suggestion_result = None  # Clear any previous suggestions
        st.session_state.payee_decision_made = True  # Assume extracted is decided, can be re-ambiguous by typing
    elif current_global_data.get('payee'):  # If user has pre-filled, run fuzzy match on their input
        # No change to global_transaction_data['payee'] or general_payee_text_input here,
        # rely on the main loop's fuzzy matching trigger.
        pass  # The central fuzzy matching logic will handle this comparison on the next rerun

    # Account
    if extracted_data.get('account') and not current_global_data.get('account'):
        st.session_state.global_transaction_data['account'] = extracted_data['account']

    # Splits: Only overwrite if no splits were manually added by the user
    if not current_splits or (
            len(current_splits) == 1 and current_splits[0]['amount'] == 0.0 and not current_splits[0]['description']):
        extracted_splits = extracted_data.get('splits', [])
        if extracted_splits:
            formatted_splits = []
            for split in extracted_splits:
                formatted_splits.append({
                    'amount': split.get('amount', 0.0),
                    'description': split.get('description', ''),
                    'notes': split.get('notes', ''),
                    'budget_scope': split.get('budget_scope', ''),
                    'category': split.get('category', ''),
                    'sub_category': split.get('sub_category', ''),
                    'full_budget_path': split.get('full_budget_path', '')
                })
            # Determine which split key to use (expense_splits or income_splits)
            transaction_type = extracted_data.get('transaction_type', 'Expense')
            split_key_to_use = f'{transaction_type.lower()}_splits'
            st.session_state[split_key_to_use] = formatted_splits
            # Also reset category UI state for these newly populated splits
            for i in range(len(formatted_splits)):
                prefix = f"{transaction_type.lower()}_split_{i}_cat_ui"
                full_path_parts = formatted_splits[i]['full_budget_path'].split(':')
                st.session_state[f'{prefix}_budget_scope'] = full_path_parts[0] if len(full_path_parts) > 0 else ''
                st.session_state[f'{prefix}_category_path_elements'] = full_path_parts
                st.session_state[f'{prefix}_full_budget_path'] = formatted_splits[i]['full_budget_path']
    else:
        st.info("Splits were pre-filled by the user and will not be overwritten by automation.")

    # Metadata: Merge extracted with manual, prioritizing manual
    extracted_metadata = extracted_data.get('metadata', [])
    if extracted_metadata:
        merged_metadata = []
        existing_manual_keys = {entry['key'].strip().lower() for entry in current_metadata_entries if entry.get('key')}

        # Add manual entries first
        merged_metadata.extend(current_metadata_entries)

        # Add extracted entries only if their keys don't conflict with manual entries
        for ext_meta in extracted_metadata:
            if ext_meta.get('key', '').strip().lower() not in existing_manual_keys:
                merged_metadata.append(
                    {'key': ext_meta.get('key', ''), 'value': ext_meta.get('value', ''), '_selected_from_list_key': ''})

        # Ensure we have at least one empty row if no metadata exists after merge
        if not merged_metadata:
            merged_metadata.append({'key': '', 'value': '', '_selected_from_list_key': ''})

        st.session_state.manual_metadata_entries = merged_metadata

    st.rerun()  # Trigger a rerun to display the pre-filled data


def display_single_transaction_tab(transaction_manager: TransactionManager, config_manager: FinanceConfigManager,
                                   app_config_manager: AppConfigManager):
    """
    Displays the UI for entering a single transaction, with optional invoice automation.
    """
    st.header("Enter Transaction Details")

    display_currency_symbol = app_config_manager.get_app_settings().get('display_currency_symbol_on_amount', True)
    currency_symbol = config_manager.get_currency_symbol() if display_currency_symbol else ""

    account_options = _get_account_options(config_manager)
    structured_categories = config_manager.get_all_categories_recursive()

    transaction_types = ["Expense", "Income", "Transfer"]

    existing_payee_names = transaction_manager.payee_manager.get_all_payee_names()
    payee_options = [''] + sorted(existing_payee_names)  # Sort for better UX

    all_unique_metadata_keys = _get_all_unique_metadata_keys(transaction_manager.metadata_manager)

    # --- Initialize/Reset Global Transaction Data ---
    if 'global_transaction_data' not in st.session_state:
        st.session_state.global_transaction_data = {
            'date': datetime.date.today(),
            'payee': '',
            'account': '',
            'uploaded_file': None,  # This will be the single uploaded file for this form
            'manual_metadata': []
        }
    # Initialize payee decision state and raw input tracker on first load
    if 'payee_suggestion_result' not in st.session_state:
        st.session_state.payee_suggestion_result = None
    if 'payee_decision_made' not in st.session_state:
        st.session_state.payee_decision_made = True  # Default to True, assume no decision needed until input changes
    if 'raw_payee_input_original' not in st.session_state:
        st.session_state.raw_payee_input_original = ''

    # State to hold extracted data temporarily
    if 'extracted_invoice_data' not in st.session_state:
        st.session_state.extracted_invoice_data = None

    # Reset all relevant states if the tab is re-entered or transaction type changes
    # This ensures a clean slate if user switches from batch processing or just wants to start fresh
    if st.session_state.get('last_selected_transaction_type_single_entry') != st.session_state.get(
            'selected_transaction_type_radio', 'Expense'):
        st.session_state.global_transaction_data = {
            'date': datetime.date.today(),
            'payee': '',
            'account': '',
            'uploaded_file': None,
            'manual_metadata': []
        }
        st.session_state.payee_suggestion_result = None
        st.session_state.payee_decision_made = True
        st.session_state.raw_payee_input_original = ''
        st.session_state.extracted_invoice_data = None  # Clear extracted data

        # Clear specific split and category UI states
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
        if 'general_payee_text_input' in st.session_state:
            del st.session_state['general_payee_text_input']
        if 'current_transaction_id' in st.session_state:
            del st.session_state['current_transaction_id']

        # Set the current transaction type for next session reset check
        st.session_state['last_selected_transaction_type_single_entry'] = st.session_state.get(
            'selected_transaction_type_radio', 'Expense')
        st.rerun()  # Rerun to apply these resets

    # --- Top-level controls for automation and file upload ---
    st.session_state.enable_automation = st.toggle(
        "Enable Automatic Filling from Invoice/Receipt",
        value=st.session_state.get('enable_automation', False),
        key="enable_automation_toggle"
    )

    # Use the 'uploaded_file' in global_transaction_data as the primary holder for the attached file
    # This ensures it's part of the main transaction state
    st.session_state.global_transaction_data['uploaded_file'] = st.file_uploader(
        "Attach Invoice/Receipt (Optional)",
        type=['png', 'jpg', 'jpeg', 'pdf'],
        key="single_transaction_file_uploader"
    )

    col_process, col_save = st.columns([1, 1])

    with col_process:
        # Process button
        if st.button("Process Invoice", key="process_invoice_btn", disabled=not (
                st.session_state.enable_automation and st.session_state.global_transaction_data['uploaded_file'])):
            if st.session_state.global_transaction_data['uploaded_file']:
                with st.spinner("Processing invoice... This may take a moment."):
                    try:
                        # Process the uploaded file
                        suggested_data = transaction_manager.process_uploaded_invoice(
                            st.session_state.global_transaction_data['uploaded_file'])
                        st.session_state.extracted_invoice_data = suggested_data  # Store for pre-filling
                        st.success("Invoice processed successfully! Review and modify the suggested transaction below.")
                        _populate_form_from_extracted_data(suggested_data)  # Populate fields
                    except Exception as e:
                        st.error(f"Error processing invoice: {e}")
                        st.warning("Please try another file or proceed with manual entry.")
                        st.session_state.extracted_invoice_data = None  # Clear extracted data on error
            else:
                st.warning("Please upload an invoice/receipt to process.")

    with col_save:
        # Placeholder for Save button (will be in the form below)
        pass

    # --- Transaction ID (Always visible) ---
    if 'current_transaction_id' not in st.session_state:
        st.session_state.current_transaction_id = f"TRN-{int(datetime.datetime.now().timestamp())}-{uuid.uuid4().hex[:6].upper()}"

    # --- Dynamic UI based on Transaction Type ---
    selected_transaction_type = st.radio(  # Moved this here as it's part of form inputs now
        "Select Transaction Type",
        transaction_types,
        horizontal=True,
        index=transaction_types.index(st.session_state.get('selected_transaction_type_radio', 'Expense')),
        # Default to Expense
        key="selected_transaction_type_radio"
    )

    st.session_state.global_transaction_data['date'] = st.date_input(
        "Date",
        st.session_state.global_transaction_data['date'],
        key="general_date"
    )

    # Payee Selection/Entry
    st.selectbox(
        "Select an existing Payer/Payee (Optional)",
        payee_options,
        index=payee_options.index(st.session_state.global_transaction_data['payee']) if
        st.session_state.global_transaction_data['payee'] in payee_options else 0,
        placeholder="Choose from recent payees...",
        key="general_payee_list_selectbox",
        on_change=lambda: _handle_payee_selection_from_list(transaction_manager, app_config_manager)
        # Use lambda to call function
    )
    st.info(
        "If you select an existing payee, it will appear in the text input below. You can then edit or add a new payee directly in the text input. The **text input value** will be used for the transaction.")

    # The text input for manual entry or confirming selection
    st.text_input(
        "Payer/Payee (Enter new or confirm suggestion)",
        value=st.session_state.global_transaction_data['payee'],
        key="general_payee_text_input",
        placeholder="Type payee name or select from above..."
    )

    # Trigger fuzzy matching if the current text input value differs from the conformed payee
    # This handles both initial manual typing and edits after pre-filling.
    current_text_input_value_for_payee = st.session_state.get('general_payee_text_input', '')
    if current_text_input_value_for_payee != st.session_state.global_transaction_data['payee']:
        _handle_payee_input_change(transaction_manager)
        st.rerun()  # Rerun to display suggestion/conformed name

    # Display Payee Suggestion/Confirmation UI
    suggestion_result = st.session_state.payee_suggestion_result
    original_payee_typed = st.session_state.raw_payee_input_original

    if suggestion_result and not st.session_state.payee_decision_made:
        status = suggestion_result['status']
        suggested_name = suggestion_result['suggested_conformed_name']

        if status == 'AMBIGUOUS':
            st.warning(
                f"Is '{original_payee_typed}' the same as **'{suggested_name}'** (Similarity: {suggestion_result['similarity_score']:.2f})?")
            col_confirm, col_new = st.columns(2)
            with col_confirm:
                if st.button(f"Yes, use '{suggested_name}'", key="confirm_payee_suggestion"):
                    st.session_state.global_transaction_data['payee'] = suggested_name
                    st.session_state.payee_decision_made = True
                    st.rerun()
            with col_new:
                if st.button(f"No, use '{original_payee_typed}' as new payee", key="reject_payee_suggestion"):
                    st.session_state.global_transaction_data['payee'] = original_payee_typed
                    st.session_state.payee_decision_made = True
                    st.rerun()

            if suggestion_result['alternatives']:
                alternative_names_for_display = [
                    alt['name'] for alt in suggestion_result['alternatives']
                    if alt['name'] != suggested_name
                ]
                if alternative_names_for_display:
                    selected_alt_from_options = st.selectbox(
                        "Or choose from other similar payees:",
                        [''] + sorted(alternative_names_for_display),
                        key="select_alternative_payee"
                    )
                    if selected_alt_from_options:
                        st.session_state.global_transaction_data['payee'] = selected_alt_from_options
                        st.session_state.payee_decision_made = True
                        st.rerun()

        elif status in ['NO_MATCH']:
            st.info(f"No high-confidence match found for '{original_payee_typed}'. This will be added as a new payee.")
            st.session_state.payee_decision_made = True
            st.session_state.global_transaction_data['payee'] = original_payee_typed

        elif status in ['EXACT_MATCH', 'HIGH_CONFIDENCE'] and st.session_state.payee_decision_made:
            st.success(f"Payee conformed to: **{st.session_state.global_transaction_data['payee']}**")

    # Account Selection
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

    st.markdown("---")
    st.subheader(f"Splits for {selected_transaction_type}")

    split_key = f'{selected_transaction_type.lower()}_splits'

    if split_key not in st.session_state:
        st.session_state[split_key] = [{
            'amount': 0.0, 'description': '', 'notes': '',
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
                prefix_to_clear = f"{selected_transaction_type}_split_{len(st.session_state[split_key]) - 1}_cat_ui"
                for k in list(st.session_state.keys()):
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

        current_full_path = st.session_state.get(f"{selected_transaction_type}_split_{i}_cat_ui_full_budget_path", "")
        split_data['full_budget_path'] = current_full_path

        full_path_parts = current_full_path.split(':')
        split_data['budget_scope'] = full_path_parts[0] if len(full_path_parts) > 0 else ""
        split_data['category'] = full_path_parts[1] if len(full_path_parts) > 1 else ""
        split_data['sub_category'] = full_path_parts[2] if len(full_path_parts) > 2 else ""

        st.markdown("---")

    st.markdown(f"**Calculated Total Amount for Splits: {currency_symbol}{total_amount_sum:.2f}**")

    # --- Additional Metadata Section ---
    if 'manual_metadata_entries' not in st.session_state:
        st.session_state.manual_metadata_entries = [{'key': '', 'value': '', '_selected_from_list_key': ''}]

    with st.expander("Additional Metadata (Optional)"):
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

        # TODO: Verify that the manual input takes precedence over the selected from list.
        # TODO: Verify that you cannot use the same metadata key multiple times. No need....
        # TODO: Warn the user in case they have the same metadata in multiple splits. The last will be used. ...
        #  No need. If they want to enter many time the same, we will save many time the same and it will their pb to sort all out.
        for i, meta_entry in enumerate(st.session_state.manual_metadata_entries):
            cols_meta = st.columns([1, 1])
            with cols_meta[0]:
                selected_key_from_list = st.selectbox(
                    "Metadata Key (Select existing)",
                    all_unique_metadata_keys,
                    index=all_unique_metadata_keys.index(
                        meta_entry['_selected_from_list_key']) if meta_entry[
                                                                      '_selected_from_list_key'] in all_unique_metadata_keys else 0,
                    placeholder="Choose from existing keys...",
                    key=f"{selected_transaction_type}_meta_key_selectbox_{i}"
                )
                if selected_key_from_list and selected_key_from_list != meta_entry['_selected_from_list_key']:
                    meta_entry['_selected_from_list_key'] = selected_key_from_list
                    meta_entry['key'] = selected_key_from_list
                    st.rerun()

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

    with st.form(key=f"single_transaction_submission_form"):  # Unified form
        st.write("Click 'Save Transaction' to finalize your entry.")
        submitted = st.form_submit_button("Save Transaction", use_container_width=True)

        if submitted:
            is_valid = True

            if selected_transaction_type in ["Expense", "Income"] and st.session_state.get('payee_suggestion_result'):
                if st.session_state.payee_suggestion_result[
                    'status'] == 'AMBIGUOUS' and not st.session_state.payee_decision_made:
                    st.error("Please confirm or reject the suggested payee before saving.")
                    is_valid = False

            if not st.session_state.global_transaction_data['payee']:
                st.error("Overall Payer/Payee is required.")
                is_valid = False
            if not st.session_state.global_transaction_data['account']:
                st.error("Overall Account is required.")
                is_valid = False

            if total_amount_sum <= 0 and selected_transaction_type != "Transfer":
                st.error("Total amount of splits must be positive for Expense/Income.")
                is_valid = False

            cleaned_metadata = []
            for meta_entry in st.session_state.manual_metadata_entries:
                key = meta_entry['key'].strip()
                value = meta_entry['value'].strip()
                if key and value:
                    cleaned_metadata.append({'key': key, 'value': value})
                elif key or value:
                    st.warning(
                        f"Metadata field found with only a key or a value (Key: '{key}', Value: '{value}'). Ignoring incomplete entry.")

            st.session_state.global_transaction_data['manual_metadata'] = cleaned_metadata

            if selected_transaction_type != "Transfer":
                for i, split_data in enumerate(st.session_state[split_key]):
                    if split_data['amount'] <= 0:
                        st.error(f"Split {i + 1}: Amount must be positive.")
                        is_valid = False
                    if not split_data['description']:
                        st.error(f"Split {i + 1}: Description is required.")
                        is_valid = False
                    if not split_data['full_budget_path'] or split_data['full_budget_path'].count(':') < 1:
                        st.error(f"Split {i + 1}: A specific category path (e.g., Scope:Category) is required.")
                        is_valid = False

                    if selected_transaction_type == "Income" and not split_data['full_budget_path'].startswith(
                            "Income:"):
                        st.error(f"Split {i + 1}: Income transactions must be categorized under an 'Income' path.")
                        is_valid = False
                    elif selected_transaction_type == "Expense" and split_data['full_budget_path'].startswith(
                            "Income:"):
                        st.error(f"Split {i + 1}: Expense transactions cannot be categorized under an 'Income' path.")
                        is_valid = False
            else:  # Transfer specific validation
                amount = st.session_state.transfer_data['amount']
                source_account_name = st.session_state.transfer_data['source_account']
                destination_account_name = st.session_state.transfer_data['destination_account']
                if amount <= 0 or not source_account_name or not destination_account_name:
                    st.error("A positive Amount, 'From Account', and 'To Account' are required for Transfer.")
                    is_valid = False
                elif source_account_name == destination_account_name:
                    st.error("Source and Destination accounts cannot be the same for Transfer.")
                    is_valid = False
                elif not st.session_state.transfer_data['full_budget_path'] or \
                        st.session_state.transfer_data['full_budget_path'].count(':') < 1:
                    st.error(
                        "A valid budget path (e.g., 'Transfer:Transfer' or 'Personal:Savings') is required for transfers.")
                    is_valid = False

            if is_valid:
                try:
                    if selected_transaction_type in ["Expense", "Income"]:
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

                        transaction_manager.add_manual_transaction(
                            transaction_id=st.session_state.current_transaction_id,
                            transaction_type=selected_transaction_type,
                            date=st.session_state.global_transaction_data['date'],
                            payee=st.session_state.global_transaction_data['payee'],
                            account=st.session_state.global_transaction_data['account'],
                            uploaded_file=st.session_state.global_transaction_data['uploaded_file'],
                            # Pass the attached file
                            splits=splits_for_manager,
                            manual_metadata=st.session_state.global_transaction_data['manual_metadata']
                        )
                        st.success(
                            f"{selected_transaction_type} transaction saved successfully with ID: **{st.session_state.current_transaction_id}**")

                    elif selected_transaction_type == "Transfer":
                        amount = st.session_state.transfer_data['amount']
                        source_account_name = st.session_state.transfer_data['source_account']
                        destination_account_name = st.session_state.transfer_data['destination_account']
                        description = st.session_state.transfer_data['description']
                        notes = st.session_state.transfer_data['notes']
                        transfer_payee = st.session_state.global_transaction_data['payee']
                        if not transfer_payee:
                            transfer_payee = f"Transfer to {destination_account_name}" if destination_account_name else "Transfer"

                        transfer_splits = [
                            {
                                'description': description or f"Transfer from {source_account_name} to {destination_account_name}",
                                'amount': -amount,
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
                                'amount': amount,
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
                            transaction_id=st.session_state.current_transaction_id,
                            transaction_type="Transfer",
                            date=st.session_state.transfer_data['date'],
                            payee=transfer_payee,
                            account=source_account_name,
                            uploaded_file=st.session_state.global_transaction_data['uploaded_file'],
                            # Pass the attached file
                            splits=transfer_splits,
                            manual_metadata=st.session_state.global_transaction_data['manual_metadata']
                        )
                        st.success(
                            f"Transfer transaction saved successfully with ID: **{st.session_state.current_transaction_id}**")

                    # Reset states after successful save for all transaction types
                    st.session_state.global_transaction_data = {
                        'date': datetime.date.today(), 'payee': '', 'account': '', 'uploaded_file': None,
                        'manual_metadata': []
                    }
                    st.session_state.payee_suggestion_result = None
                    st.session_state.payee_decision_made = True
                    st.session_state.raw_payee_input_original = ''
                    st.session_state.extracted_invoice_data = None  # Clear extracted data after saving

                    if 'expense_splits' in st.session_state: del st.session_state['expense_splits']
                    if 'income_splits' in st.session_state: del st.session_state['income_splits']
                    if 'transfer_data' in st.session_state: del st.session_state['transfer_data']

                    for key in list(st.session_state.keys()):
                        if '_cat_ui' in key:
                            del st.session_state[key]
                    if 'manual_metadata_entries' in st.session_state:
                        del st.session_state['manual_metadata_entries']
                    if 'general_payee_text_input' in st.session_state:
                        del st.session_state['general_payee_text_input']

                    st.session_state.current_transaction_id = f"TRN-{int(datetime.datetime.now().timestamp())}-{uuid.uuid4().hex[:6].upper()}"
                    st.rerun()

                except Exception as e:
                    st.error(f"Failed to save transaction: {e}")
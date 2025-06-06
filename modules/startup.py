# startup.py
import streamlit as st
import os
from modules.managers.config_manager import ConfigManager  # Assuming config_manager.py is accessible
import copy # Import copy for deepcopy

# This script is intended to be run once when the Streamlit app starts (or after a full rerun).
# It initializes global resources and performs initial checks.

def initialize_session_state():
    """
    Initializes session state variables that need to persist across reruns.
    This function should be called at the very beginning of your Streamlit app
    (e.g., in your main app.py file or each page file, but designed to run once).
    """
    if 'config_manager' not in st.session_state:
        # Assuming your project structure has 'configs' at the root level relative to 'modules'
        project_root = os.path.join(os.path.dirname(__file__), '..')
        st.session_state.config_manager = ConfigManager(project_root)

    # Flags for managing initial checks and UI flow
    if 'initial_consistency_check_done' not in st.session_state:
        st.session_state.initial_consistency_check_done = False  # Will be set to True after the first check

    if 'consistency_report' not in st.session_state:
        st.session_state.consistency_report = []

    if 'default_config_saved_recently' not in st.session_state:
        st.session_state.default_config_saved_recently = False

    # Initialize edited_default_financial_config and original_default_financial_config here
    # to ensure they are always available.
    if 'original_default_financial_config' not in st.session_state:
        st.session_state.original_default_financial_config = st.session_state.config_manager.load_default_financial_config()

    if 'edited_default_financial_config' not in st.session_state:
        # Use deepcopy to ensure that editing 'edited_default_financial_config'
        # doesn't inadvertently modify 'original_default_financial_config'
        st.session_state.edited_default_financial_config = copy.deepcopy(st.session_state.original_default_financial_config)

    # Initialize app_config
    if 'app_config' not in st.session_state:
        st.session_state.app_config = st.session_state.config_manager.load_app_config()

    # --- Initialize states for deletion confirmation dialog ---
    if 'item_to_delete' not in st.session_state:
        st.session_state.item_to_delete = None
    if 'confirm_delete_dialog_open' not in st.session_state:
        st.session_state.confirm_delete_dialog_open = False
    if 'changes_pending_delete' not in st.session_state:
        st.session_state.changes_pending_delete = False

    # --- Initialize temporary current month config data for proposal flow ---
    if 'temp_current_month_config_data' not in st.session_state:
        st.session_state['temp_current_month_config_data'] = None
    if 'temp_current_month_config_path' not in st.session_state:
        st.session_state['temp_current_month_config_path'] = None

    # --- Initialize input clearing flags for "Add New" sections ---
    # These flags control clearing of text input fields after adding a new item
    if 'clear_new_category_inputs' not in st.session_state:
        st.session_state.clear_new_category_inputs = False
    if 'new_category_name_input' not in st.session_state: # Also initialize input values
        st.session_state.new_category_name_input = ""
    if 'new_category_budget_input' not in st.session_state:
        st.session_state.new_category_budget_input = 0.00

    if 'clear_new_biz_expense_inputs' not in st.session_state:
        st.session_state.clear_new_biz_expense_inputs = False
    if 'new_biz_expense_name_input' not in st.session_state:
        st.session_state.new_biz_expense_name_input = ""
    if 'new_biz_expense_budget_input' not in st.session_state:
        st.session_state.new_biz_expense_budget_input = 0.00

    # For account types, use a loop to initialize all related flags and inputs
    ACCOUNT_TYPES_FOR_ADD = {
        'savings_accounts': {'type_display': 'Savings Account'},
        'debt_accounts': {'type_display': 'Debt Account'},
        'checking_accounts': {'type_display': 'Checking Account'},
        'other_accounts': {'type_display': 'Other Account'}
    }
    for acc_section_key in ACCOUNT_TYPES_FOR_ADD.keys():
        if f'clear_new_account_inputs_{acc_section_key}' not in st.session_state:
            st.session_state[f'clear_new_account_inputs_{acc_section_key}'] = False
        if f'new_account_key_input_{acc_section_key}' not in st.session_state:
            st.session_state[f'new_account_key_input_{acc_section_key}'] = ""
        if f'new_account_display_name_input_{acc_section_key}' not in st.session_state:
            st.session_state[f'new_account_display_name_input_{acc_section_key}'] = ""
        if f'new_account_initial_val_input_{acc_section_key}' not in st.session_state:
            st.session_state[f'new_account_initial_val_input_{acc_section_key}'] = 0.00


def perform_initial_checks():
    """
    Performs initial configuration consistency checks and stores the report in session state.
    This logic should execute only once per fresh app launch.
    """
    if not st.session_state.initial_consistency_check_done:
        st.session_state.initial_consistency_check_done = True  # Set flag immediately to prevent re-running on subsequent reruns within the same session

        # Load configs fresh for the consistency check
        try:
            st.session_state.consistency_report = st.session_state.config_manager.check_config_consistency()

            # Optional: Print to console for server-side logging
            if st.session_state.consistency_report:
                print("\n--- Initial Config Consistency Check Report ---")
                for item in st.session_state.consistency_report:
                    print(item)
                print("-------------------------------------------\n")
            else:
                print("\nInitial Config Consistency Check: All good!\n")

        except Exception as e:
            st.session_state.consistency_report.append(f"Error during initial consistency check: {e}")
            print(f"Error during initial consistency check: {e}")


# Execute these functions when startup.py is imported
# This is typically handled by the main app.py or page files calling these functions.
# They are commented out here to avoid re-execution if this file is imported multiple times.
# initialize_session_state()
# perform_initial_checks()
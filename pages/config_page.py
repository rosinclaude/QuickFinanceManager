import streamlit as st
import datetime

# IMPORTANT: Import the startup script to ensure it runs and initializes session state
from modules import startup

# Execute these functions when startup.py is imported
startup.initialize_session_state()
startup.perform_initial_checks()

# Access ConfigManager and other session state variables initialized by startup.py
config_manager = st.session_state.config_manager


# --- Helper Functions for UI ---
# (display_and_edit_dict and display_config_section functions are assumed to be present
#  or imported from a utils file. I'm including them here for completeness
#  but you might already have them externalized.)

def display_and_edit_dict(data: dict, parent_key: str = "", config_type_prefix: str = "") -> dict:
    """
    Recursively displays dictionary data with Streamlit input widgets for editing.
    Handles nested dictionaries and lists of strings (keywords).
    Returns the modified dictionary.

    Args:
        data (dict): The dictionary data to display and edit.
        parent_key (str): A string representing the parent keys, used for unique widget keys.
        config_type_prefix (str): A prefix to ensure widget keys are unique across different config types (tabs).
    """
    edited_data = {}
    for key, value in data.items():
        # Construct a truly unique key for each Streamlit widget
        # Combines the config_type_prefix, parent_key, and current key
        unique_widget_key = f"{config_type_prefix}_{parent_key}_{key}"

        if isinstance(value, dict):
            st.markdown(f"**{key.replace('_', ' ').title()}**")  # Changed to bold for readability in nested sections
            # Recursively call for nested dictionaries, passing the updated parent_key
            edited_data[key] = display_and_edit_dict(value, f"{parent_key}_{key}", config_type_prefix)
        elif isinstance(value, list) and all(isinstance(elem, str) for elem in value):
            # For lists of strings (keywords), use text_area or text_input
            current_value_str = ", ".join(value)
            new_value_str = st.text_area(f"{key.replace('_', ' ').title()}",
                                         value=current_value_str,
                                         key=unique_widget_key,
                                         help="Enter keywords separated by commas.")
            edited_data[key] = [s.strip() for s in new_value_str.split(',') if s.strip()]
        elif isinstance(value, (int, float)):
            # For numbers (budgets, balances, limits), use number_input
            edited_data[key] = st.number_input(f"{key.replace('_', ' ').title()}",
                                               value=float(value),
                                               key=unique_widget_key,
                                               format="%.2f")
        elif isinstance(value, str):
            # For strings (names, types, model names)
            edited_data[key] = st.text_input(f"{key.replace('_', ' ').title()}",
                                             value=value,
                                             key=unique_widget_key)
        elif value is None:
            # Handle null values (e.g., Income budget). Display as "null", convert back to None on save.
            displayed_value = "null" if value is None else str(value)
            input_value = st.text_input(f"{key.replace('_', ' ').title()}",
                                        value=displayed_value,
                                        key=unique_widget_key)
            if input_value.lower() == 'null':
                edited_data[key] = None
            else:
                try:
                    edited_data[key] = float(input_value)  # Attempt to convert to float if not null
                except ValueError:
                    st.warning(
                        f"Invalid input for {key}: '{input_value}'. Please enter a number or 'null'. Keeping as string.")
                    edited_data[key] = input_value  # Keep as string if conversion fails

    return edited_data


def display_config_section(config_data: dict, section_key: str, config_type_prefix: str) -> dict:
    """
    Displays and allows editing of a specific section of the config (e.g., categories, accounts).
    Now includes delete functionality for default config tab.

    Args:
        config_data (dict): The configuration data dictionary.
        section_key (str): The top-level key of the section (e.g., 'categories', 'savings_accounts').
        config_type_prefix (str): A prefix to ensure widget keys are unique across different config types (tabs).
    """
    with st.expander(f"Edit {section_key.replace('_', ' ').title()}"):
        if section_key in config_data and isinstance(config_data[section_key], dict):
            sorted_item_names = sorted(config_data[section_key].keys())
            if not sorted_item_names:
                st.info(f"No {section_key.replace('_', ' ')} defined yet. Add some above!")

            for item_name in sorted_item_names:
                item_data = config_data[section_key][item_name]

                # Use columns for item name, inputs, and delete button for 'default_financial' config
                if config_type_prefix == "default_financial":
                    item_col, delete_col = st.columns([0.8, 0.2])
                    with item_col:
                        st.markdown(f"#### {item_name.replace('_', ' ').title()}")
                        # Direct modification of st.session_state.edited_default_financial_config[section_key][item_name]
                        # This ensures changes made via display_and_edit_dict are reflected in the session state.
                        st.session_state.edited_default_financial_config[section_key][
                            item_name] = display_and_edit_dict(
                            item_data, f"{section_key}_{item_name}", config_type_prefix
                        )
                    with delete_col:
                        delete_button_key = f"delete_{section_key}_{item_name}"
                        # Only show delete button if not confirming a delete
                        if not st.session_state.get('confirm_delete_dialog_open', False): # Use the new session state var
                            if st.button("Delete", key=delete_button_key):
                                # Set item to delete and open confirmation dialog
                                st.session_state.item_to_delete = (section_key, item_name)
                                st.session_state.confirm_delete_dialog_open = True
                                # Mark that a deletion is pending user confirmation
                                st.session_state.changes_pending_delete = True
                                st.rerun()  # Rerun to display the confirmation dialog
                else:  # For current_financial and app_config, just display and edit without delete button
                    st.markdown(f"#### {item_name.replace('_', ' ').title()}")
                    # config_data is a copy for current_financial, so update it directly
                    # For app_config, we'll directly modify st.session_state.app_config later
                    config_data[section_key][item_name] = display_and_edit_dict(
                        item_data, f"{section_key}_{item_name}", config_type_prefix
                    )
        else:
            st.info(f"No {section_key.replace('_', ' ')} defined in this configuration.")

    return config_data  # Return potentially modified config_data (only relevant for current_financial/app_config copies)

# --- Helper function to re-run consistency check ---
def rerun_consistency_check():
    st.session_state.consistency_report = config_manager.check_config_consistency()
    st.rerun() # Rerun to refresh the UI with new consistency report

# --- Functions for global actions (Submit/Reject All) ---
def submit_all_config_changes():
    try:
        # 1. Handle pending deletion if any
        if st.session_state.item_to_delete and st.session_state.confirm_delete_dialog_open:
            section_key, item_name = st.session_state.item_to_delete
            # Actually remove from the in-memory edited configs before saving
            if section_key in st.session_state.edited_default_financial_config and \
               item_name in st.session_state.edited_default_financial_config[section_key]:
                del st.session_state.edited_default_financial_config[section_key][item_name]
            if section_key in st.session_state.app_config and \
               item_name in st.session_state.app_config[section_key]:
                del st.session_state.app_config[section_key][item_name]

            st.session_state.item_to_delete = None
            st.session_state.confirm_delete_dialog_open = False
            st.session_state.changes_pending_delete = False
            st.info(f"Deletion of '{item_name.replace('_', ' ').title()}' processed.")


        # 2. Save edited default financial config
        config_manager.save_default_financial_config(st.session_state.edited_default_financial_config)

        # 3. Save app config (this handles any edits made via the keyword fields and also structural sync)
        # IMPORTANT: We need to ensure app_config reflects any structural changes due to additions/deletions
        # from default financial config *before* saving.
        # Calling synchronize_app_config_structure with the *saved* default financial config ensures this.
        updated_default_financial_config_for_sync = config_manager.load_default_financial_config() # Load the freshly saved default
        config_manager.synchronize_app_config_structure(updated_default_financial_config_for_sync)
        config_manager.save_app_config(st.session_state.app_config) # Save the app_config (now consistent)


        # After saving, refresh the original default financial config to match the saved state
        st.session_state.original_default_financial_config = config_manager.load_default_financial_config()
        st.session_state.app_config = config_manager.load_app_config() # Reload app config to ensure full consistency

        st.success("All configuration changes saved successfully!")
        st.session_state.default_config_saved_recently = True
        rerun_consistency_check() # Re-check consistency after saving
    except Exception as e:
        st.error(f"Error saving configurations: {e}")
        st.session_state.default_config_saved_recently = False


def reject_all_config_changes():
    # Revert default financial config to its original loaded state
    st.session_state.edited_default_financial_config = st.session_state.original_default_financial_config.copy()
    # Reload app config to discard any unsaved keyword edits or structural changes from sync
    st.session_state.app_config = config_manager.load_app_config()

    # Clear any pending deletion states
    st.session_state.item_to_delete = None
    st.session_state.confirm_delete_dialog_open = False
    st.session_state.changes_pending_delete = False

    st.warning("All pending changes have been rejected.")
    st.session_state.default_config_saved_recently = False
    rerun_consistency_check() # Re-check consistency after rejection

# --- Main Streamlit Page Structure ---

st.title("💰 Configuration Management")

# Get current year and month for current financial config
current_year = datetime.datetime.now().year
current_month = datetime.datetime.now().month

# DYNAMICALLY DETERMINE FINANCIAL_CONFIG_SECTIONS
# We assume that any top-level dictionary in the financial config (excluding 'currency', 'month', 'year')
# represents a section with items to be managed.
# This assumes 'categories', 'business_expenses', and the account types are dictionaries within the config.
FINANCIAL_CONFIG_SECTIONS = [
    key for key, value in st.session_state.edited_default_financial_config.items()
    if isinstance(value, dict) and key not in ['currency', 'month', 'year']
]
# Optionally, sort them for consistent display
FINANCIAL_CONFIG_SECTIONS.sort()


# Using tabs for different config views
tab1, tab2, tab3 = st.tabs(
    ["Current Month Financial Config", "Default Financial Config", "Application Config (Keywords & LLM)"])

# Display Global Consistency Check Results (from startup.py)
if st.session_state.consistency_report:
    st.sidebar.warning("Inconsistencies detected in configuration files!")
    with st.sidebar.expander("Details"):
        for item in st.session_state.consistency_report:
            st.markdown(item)  # Use markdown for bold formatting from ConfigManager
else:
    st.sidebar.success("Configuration files are consistent.")

# --- Save/Reject Buttons (moved to the top for better visibility) ---
st.header("Actions for Default Financial & App Configs")
col_submit, col_reject = st.columns(2)

# Check if edited_default_financial_config is different from original_default_financial_config
# or if there are pending deletions OR if app_config itself has been modified (e.g., keywords)
configs_are_different = (st.session_state.edited_default_financial_config != st.session_state.original_default_financial_config or
                         st.session_state.changes_pending_delete or
                         st.session_state.app_config != config_manager.load_app_config()) # Compare current app_config in session state with on-disk

with col_submit:
    if st.button("Submit Changes", disabled=not configs_are_different, help="Save all changes to default financial config and app config files.", key="submit_all_changes_top"):
        submit_all_config_changes()

with col_reject:
    if st.button("Reject All Changes", disabled=not configs_are_different, help="Discard all unsaved changes to default financial config and app config files.", key="reject_all_changes_top"):
        reject_all_config_changes()

if st.session_state.default_config_saved_recently:
    st.success("Default Financial & App Configurations saved successfully!")
    st.session_state.default_config_saved_recently = False # Reset the flag


st.markdown("---")

with tab1:
    st.header(
        f"Current Month Financial Configuration ({datetime.date(current_year, current_month, 1).strftime('%B %Y')})")
    st.write("Edit your budget and current account balances for the current month.")

    # Load the current month's financial config
    try:
        current_financial_config = config_manager.load_financial_config(current_year, current_month)
        # Create a copy to allow direct editing without immediately affecting disk
        edited_current_financial_config = current_financial_config.copy()
    except Exception as e:
        st.error(f"Error loading current month's financial config: {e}")
        st.stop()

    # Display and edit General Configuration
    with st.expander("General Configuration"):
        edited_current_financial_config['currency'] = st.text_input("Currency",
                                                                    value=edited_current_financial_config.get(
                                                                        'currency', 'CAD'),
                                                                    key="current_financial_currency")

    # Display and edit financial sections using the loop
    for section_name in FINANCIAL_CONFIG_SECTIONS:
        # Pass the config_type_prefix unique to this tab
        edited_current_financial_config = display_config_section(edited_current_financial_config, section_name,
                                                                 "current_financial")

    st.markdown("---")  # Separator before save button

    # Check if there are temporary changes proposed for current month config
    if 'temp_current_month_config_data' not in st.session_state:
        # Initial save button for current month config
        if st.button("Propose & Review Current Month Config Changes", key="propose_current_month_button"):
            # Only propose if there are actual changes (optional, but good practice)
            if current_financial_config != edited_current_financial_config:
                try:
                    # Use session state to store the temporary file path across reruns
                    st.session_state['temp_current_month_config_data'], st.session_state[
                        'temp_current_month_config_path'] = \
                        config_manager.propose_merged_financial_config(current_year, current_month,
                                                                       edited_current_financial_config)

                    st.subheader("Proposed Changes for Current Month Financial Config:")
                    st.json(st.session_state['temp_current_month_config_data'])  # Show the proposed changes
                    st.warning("Please review the proposed changes above before confirming.")
                    st.info("Click 'Confirm and Save' below to finalize these changes.")
                except Exception as e:
                    st.error(f"Error proposing current month config changes: {e}")
            else:
                st.info("No changes detected in current month config to propose.")
    else:
        # If there are proposed changes, show the confirmation prompt
        st.subheader("Proposed Changes for Current Month Financial Config:")
        st.json(st.session_state['temp_current_month_config_data'])  # Show the proposed changes
        st.warning("Please review the proposed changes above before confirming.")

        col_confirm_current, col_cancel_current = st.columns(2)
        with col_confirm_current:
            if st.button("Confirm and Save Current Month Config", key="confirm_save_current_month_button"):
                try:
                    config_manager.confirm_and_replace_financial_config(
                        current_year, current_month, st.session_state['temp_current_month_config_path']
                    )
                    st.success("Current month financial configuration updated successfully!")
                    # Clean up session state after confirmed save
                    if 'temp_current_month_config_data' in st.session_state:
                        del st.session_state['temp_current_month_config_data']
                    if 'temp_current_month_config_path' in st.session_state:
                        del st.session_state['temp_current_month_config_path']
                    st.rerun()  # Rerun to show updated data and clear temp file display
                except Exception as e:
                    st.error(f"Error saving current month config: {e}")
        with col_cancel_current:
            if st.button("Cancel Proposed Changes", key="cancel_current_month_button"):
                if 'temp_current_month_config_data' in st.session_state:
                    del st.session_state['temp_current_month_config_data']
                if 'temp_current_month_config_path' in st.session_state:
                    del st.session_state['temp_current_month_config_path']
                st.info("Proposed changes for current month config have been cancelled.")
                st.rerun()

# ---

with tab2:
    st.header("Default Financial Configuration")
    st.write("Edit the default template for your financial configurations.")
    st.info(
        "Changes here are accumulated in memory and will only be saved when you click 'Submit Changes' at the top of the page.")

    # --- Access Default Financial Configs from Session State (initialized by startup.py) ---
    # These are already loaded by startup.py into session state
    edited_default_financial_config = st.session_state.edited_default_financial_config
    original_default_financial_config = st.session_state.original_default_financial_config

    # --- Handle Deletion Confirmation for Default Financial Config ---
    if st.session_state.get('confirm_delete_dialog_open', False) and st.session_state.item_to_delete:
        section, item_name = st.session_state.item_to_delete
        display_name = item_name.replace('_', ' ').title()
        st.warning(
            f"### Confirm Deletion")
        st.write(f"Are you sure you want to delete **'{display_name}'** from **{section.replace('_', ' ').title()}**?")
        st.write("This action will remove the item from the in-memory default financial config and app config.")
        st.write("It will only be made permanent after you click the 'Submit Changes' button at the top.")

        col_confirm_del, col_cancel_del = st.columns(2)
        with col_confirm_del:
            if st.button(f"Yes, Delete '{display_name}' (Memory Only)", key="confirm_delete_item_button"):
                # Remove from in-memory financial config
                if section in edited_default_financial_config and item_name in edited_default_financial_config[section]:
                    del edited_default_financial_config[section][item_name]
                    st.success(f"'{display_name}' removed from in-memory default financial config. Click 'Submit Changes' to save.")

                # Also remove from in-memory app config
                if section in st.session_state.app_config and item_name in st.session_state.app_config[section]:
                    del st.session_state.app_config[section][item_name]
                    st.info(f"'{display_name}' removed from in-memory app config.")

                st.session_state.item_to_delete = None
                st.session_state.confirm_delete_dialog_open = False
                # Re-evaluate if there are changes pending
                st.session_state.changes_pending_delete = (edited_default_financial_config != original_default_financial_config or
                                                           st.session_state.app_config != config_manager.load_app_config())
                rerun_consistency_check() # Rerun to update the display and consistency report

        with col_cancel_del:
            if st.button("No, Keep Item", key="cancel_delete_item_button"):
                st.session_state.item_to_delete = None
                st.session_state.confirm_delete_dialog_open = False
                st.session_state.changes_pending_delete = False # No pending deletion
                st.info("Deletion cancelled.")
                st.rerun()  # Rerun to remove confirmation prompt

    # Display and edit General Configuration
    with st.expander("General Configuration"):
        edited_default_financial_config['currency'] = st.text_input("Currency",
                                                                    value=edited_default_financial_config.get(
                                                                        'currency', 'CAD'),
                                                                    key="default_financial_currency",
                                                                    on_change=lambda: st.session_state.update(default_config_saved_recently=False)) # Mark as unsaved
        # Month/Year in default should remain placeholders or "Default"
        edited_default_financial_config['month'] = "Default"
        edited_default_financial_config['year'] = 0000

    # --- Add New Categories ---
    with st.expander("Add New Category"):
        st.markdown("Enter details for a new category.")

        # --- Clearing Logic for Category Inputs ---
        if st.session_state.get('clear_new_category_inputs', False):
            st.session_state['new_category_name_input'] = ""
            st.session_state['new_category_budget_input'] = 0.00
            st.session_state['clear_new_category_inputs'] = False  # Reset the flag

        col_cat_name, col_cat_budget = st.columns(2)
        with col_cat_name:
            if 'new_category_name_input' not in st.session_state:
                st.session_state['new_category_name_input'] = ""
            new_category_name = st.text_input("Category Name (e.g., 'Entertainment')",
                                              value=st.session_state['new_category_name_input'],
                                              key="new_category_name_input",
                                              on_change=lambda: st.session_state.update(default_config_saved_recently=False)) # Mark as unsaved
        with col_cat_budget:
            if 'new_category_budget_input' not in st.session_state:
                st.session_state['new_category_budget_input'] = 0.00
            new_category_budget = st.number_input("Initial Budget",
                                                  value=st.session_state['new_category_budget_input'],
                                                  min_value=0.00, format="%.2f",
                                                  key="new_category_budget_input",
                                                  on_change=lambda: st.session_state.update(default_config_saved_recently=False)) # Mark as unsaved

        if st.button("Add Category", key="add_category_button"):
            if new_category_name:
                normalized_name = new_category_name.replace(" ",
                                                            "_").strip().lower()  # Normalize to snake_case, ensure lowercase for keys
                if normalized_name not in edited_default_financial_config.get('categories', {}):
                    if 'categories' not in edited_default_financial_config:
                        edited_default_financial_config['categories'] = {}
                    edited_default_financial_config['categories'][normalized_name] = {'budget': new_category_budget}

                    st.success(
                        f"Category '{new_category_name}' added to memory. Click 'Submit Changes' to make permanent.")
                    st.session_state['clear_new_category_inputs'] = True  # Set flag to clear inputs on next rerun
                    st.session_state.default_config_saved_recently = False # Mark as unsaved
                    st.rerun()  # Rerun to refresh the displayed sections and clear inputs
                else:
                    st.warning(f"Category '{new_category_name}' already exists.")
            else:
                st.warning("Please enter a category name.")

    # --- Add New Business Expenses ---
    with st.expander("Add New Business Expense"):
        st.markdown("Enter details for a new business expense.")

        # --- Clearing Logic for Business Expense Inputs ---
        if st.session_state.get('clear_new_biz_expense_inputs', False):
            st.session_state['new_biz_expense_name_input'] = ""
            st.session_state['new_biz_expense_budget_input'] = 0.00
            st.session_state['clear_new_biz_expense_inputs'] = False  # Reset the flag

        col_biz_name, col_biz_budget = st.columns(2)
        with col_biz_name:
            if 'new_biz_expense_name_input' not in st.session_state:
                st.session_state['new_biz_expense_name_input'] = ""
            new_biz_expense_name = st.text_input("Business Expense Name (e.g., 'Software_Subscriptions')",
                                                 value=st.session_state['new_biz_expense_name_input'],
                                                 key="new_biz_expense_name_input",
                                                 on_change=lambda: st.session_state.update(default_config_saved_recently=False)) # Mark as unsaved
        with col_biz_budget:
            if 'new_biz_expense_budget_input' not in st.session_state:
                st.session_state['new_biz_expense_budget_input'] = 0.00
            new_biz_expense_budget = st.number_input("Initial Budget",
                                                     value=st.session_state['new_biz_expense_budget_input'],
                                                     min_value=0.00, format="%.2f",
                                                     key="new_biz_expense_budget_input",
                                                     on_change=lambda: st.session_state.update(default_config_saved_recently=False)) # Mark as unsaved

        if st.button("Add Business Expense", key="add_biz_expense_button"):
            if new_biz_expense_name:
                normalized_name = new_biz_expense_name.replace(" ",
                                                               "_").strip().lower()  # Normalize to snake_case, ensure lowercase for keys
                if normalized_name not in edited_default_financial_config.get('business_expenses', {}):
                    if 'business_expenses' not in edited_default_financial_config:
                        edited_default_financial_config['business_expenses'] = {}
                    edited_default_financial_config['business_expenses'][normalized_name] = {
                        'budget': new_biz_expense_budget}

                    st.success(
                        f"Business Expense '{new_biz_expense_name}' added to memory. Click 'Submit Changes' to make permanent.")
                    st.session_state['clear_new_biz_expense_inputs'] = True  # Set flag to clear inputs on next rerun
                    st.session_state.default_config_saved_recently = False # Mark as unsaved
                    st.rerun()  # Rerun to refresh and clear inputs
                else:
                    st.warning(f"Business Expense '{new_biz_expense_name}' already exists.")
            else:
                st.warning("Please enter a business expense name.")

    # --- Add New Accounts (Loop for each type) ---
    ACCOUNT_TYPES_FOR_ADD = {
        'savings_accounts': {'type_display': 'Savings Account',
                             'default_props': {'type': 'Savings Account', 'initial_balance': 0.00,
                                               'current_balance': 0.00}},
        'debt_accounts': {'type_display': 'Debt Account',
                          'default_props': {'type': 'Debt Account', 'initial_owed': 0.00, 'current_owed': 0.00}},
        'checking_accounts': {'type_display': 'Checking Account',
                              'default_props': {'type': 'Checking Account', 'initial_balance': 0.00,
                                                'current_balance': 0.00}},
        'other_accounts': {'type_display': 'Other Account',
                           'default_props': {'type': 'Other Account', 'initial_balance': 0.00, 'current_balance': 0.00}}
    }

    for acc_section_key, acc_info in ACCOUNT_TYPES_FOR_ADD.items():
        # Only display this expander if the section key is part of the FINANCIAL_CONFIG_SECTIONS
        # This prevents showing "Add New X Account" if X accounts are not defined in the config at all.
        if acc_section_key in FINANCIAL_CONFIG_SECTIONS:
            with st.expander(f"Add New {acc_info['type_display']} Account"):
                st.markdown(f"Enter details for a new {acc_info['type_display']} account.")

                # --- Clearing Logic for Account Inputs ---
                clear_flag_key = f'clear_new_account_inputs_{acc_section_key}'
                if st.session_state.get(clear_flag_key, False):
                    st.session_state[f'new_account_key_input_{acc_section_key}'] = ""
                    st.session_state[f'new_account_display_name_input_{acc_section_key}'] = ""
                    st.session_state[f'new_account_initial_val_input_{acc_section_key}'] = 0.00
                    st.session_state[clear_flag_key] = False  # Reset the flag

                # Use columns for input fields and button for better layout
                col1, col2, col3 = st.columns([0.3, 0.3, 0.4])

                with col1:
                    if f'new_account_key_input_{acc_section_key}' not in st.session_state:
                        st.session_state[f'new_account_key_input_{acc_section_key}'] = ""
                    new_acc_key = st.text_input(f"Account Internal Key (e.g., 'MY_BANK_CHEQUING')",
                                                value=st.session_state[f'new_account_key_input_{acc_section_key}'],
                                                key=f"new_account_key_input_{acc_section_key}",
                                                on_change=lambda: st.session_state.update(default_config_saved_recently=False)) # Mark as unsaved
                with col2:
                    if f'new_account_display_name_input_{acc_section_key}' not in st.session_state:
                        st.session_state[f'new_account_display_name_input_{acc_section_key}'] = ""
                    new_acc_display_name = st.text_input(f"Account Display Name (e.g., 'My Bank Chequing')",
                                                         value=st.session_state[
                                                             f'new_account_display_name_input_{acc_section_key}'],
                                                         key=f"new_account_display_name_input_{acc_section_key}",
                                                         on_change=lambda: st.session_state.update(default_config_saved_recently=False)) # Mark as unsaved
                with col3:
                    # Initial Balance/Owed field
                    initial_val_key_prop = 'initial_balance' if 'initial_balance' in acc_info[
                        'default_props'] else 'initial_owed'
                    initial_val_display = 'Initial Balance' if 'initial_balance' in acc_info[
                        'default_props'] else 'Initial Owed'

                    if f'new_account_initial_val_input_{acc_section_key}' not in st.session_state:
                        st.session_state[f'new_account_initial_val_input_{acc_section_key}'] = 0.00
                    new_acc_initial_val = st.number_input(initial_val_display,
                                                          value=float(st.session_state[
                                                                          f'new_account_initial_val_input_{acc_section_key}']),
                                                          min_value=0.00, format="%.2f",
                                                          key=f"new_account_initial_val_input_{acc_section_key}",
                                                          on_change=lambda: st.session_state.update(default_config_saved_recently=False)) # Mark as unsaved

                if st.button(f"Add New {acc_info['type_display']} Account",
                             key=f"add_account_button_{acc_section_key}"):
                    if new_acc_key:
                        normalized_key = new_acc_key.replace(" ",
                                                             "_").strip().upper()  # Normalize key to uppercase snake_case
                        if normalized_key not in edited_default_financial_config.get(acc_section_key, {}):
                            if acc_section_key not in edited_default_financial_config:
                                edited_default_financial_config[acc_section_key] = {}

                            new_account_data = acc_info['default_props'].copy()
                            new_account_data[
                                'name'] = new_acc_display_name if new_acc_display_name else normalized_key.replace('_',
                                                                                                                   ' ').title()
                            new_account_data['type'] = acc_info[
                                'type_display']  # Use default display type for simplicity on add
                            new_account_data[initial_val_key_prop] = new_acc_initial_val
                            # Ensure current_balance/current_owed are set to initial values
                            if 'current_balance' in new_account_data:
                                new_account_data['current_balance'] = new_account_data['initial_balance']
                            if 'current_owed' in new_account_data:
                                new_account_data['current_owed'] = new_account_data['initial_owed']

                            edited_default_financial_config[acc_section_key][normalized_key] = new_account_data

                            st.success(
                                f"{acc_info['type_display']} '{new_acc_display_name}' added to memory. Click 'Submit Changes' to make permanent.")
                            st.session_state[f'clear_new_account_inputs_{acc_section_key}'] = True  # Set flag to clear inputs on next rerun
                            st.session_state.default_config_saved_recently = False # Mark as unsaved
                            st.rerun()  # Rerun to refresh and clear inputs
                        else:
                            st.warning(f"{acc_info['type_display']} with key '{new_acc_key}' already exists.")
                    else:
                        st.warning("Please enter an account internal key.")
            # No separator needed here, expander provides visual separation

    # Display and edit financial sections using the loop
    for section_name in FINANCIAL_CONFIG_SECTIONS:
        # Pass st.session_state.edited_default_financial_config directly to be modified
        display_config_section(edited_default_financial_config, section_name, "default_financial")

# ---

with tab3:
    st.header("Application Configuration (Keywords & LLM)")
    st.write("Edit keywords for automatic categorization and LLM settings.")
    st.info(
        "Changes here are accumulated in memory and will only be saved when you click 'Submit Changes' at the top of the page.")

    # Access app_config from session state
    app_config = st.session_state.app_config

    # Synchronize app config structure with default financial config before displaying/editing
    # This ensures that any newly added categories/accounts in the default financial config
    # are reflected in the app config for keyword assignment.
    # Note: synchronize_app_config_structure internally loads and saves app_config, so
    # st.session_state.app_config will be up-to-date after this call if changes were made.
    config_manager.synchronize_app_config_structure(st.session_state.edited_default_financial_config)
    # Reload app_config into session state after sync to ensure it's the latest version
    st.session_state.app_config = config_manager.load_app_config()


    # Helper function to render keyword sections
    def render_keyword_section(section_key, display_name, keyword_field_names):
        st.subheader(display_name)
        app_section_data = st.session_state.app_config.get(section_key, {})
        financial_section_data = st.session_state.edited_default_financial_config.get(section_key, {})

        if not isinstance(app_section_data, dict):
            st.warning(f"Configuration error: '{section_key}' in app config is not a dictionary. Please fix your YAML.")
            app_section_data = {}

        # Sort items for consistent display
        sorted_app_items = sorted(app_section_data.keys())

        if not sorted_app_items:
            st.info(f"No {section_key.replace('_', ' ')} defined yet in App Config. Synchronize from Default Financial Config.")

        for item_name in sorted_app_items:
            app_item_values = app_section_data.get(item_name, {}) # Get current app config values for item
            # Get the display name from the financial config if available, otherwise use a fallback
            display_name_for_item = financial_section_data.get(item_name, {}).get('name', item_name.replace('_', ' ').title())

            st.markdown(f"##### Keywords for: {display_name_for_item}")
            for keyword_field in keyword_field_names:
                current_keywords = app_item_values.get(keyword_field, [])
                # Convert list to comma-separated string for text_input
                keywords_str = ", ".join(current_keywords)

                edited_keywords_str = st.text_input(
                    f"{display_name_for_item} {keyword_field.replace('keywords_', '').replace('_', ' ').title()}",
                    value=keywords_str,
                    key=f"app_{section_key}_{item_name}_{keyword_field}",
                    on_change=lambda: st.session_state.update(default_config_saved_recently=False) # Mark as unsaved
                )

                # Convert back to list, stripping whitespace and filtering empty strings
                st.session_state.app_config[section_key][item_name][keyword_field] = [
                    kw.strip() for kw in edited_keywords_str.split(',') if kw.strip()
                ]
        st.markdown("---")

    # The list of sections for keywords still needs to be explicitly defined or dynamically derived
    # if their presence isn't guaranteed in the default financial config.
    # However, if your 'synchronize_app_config_structure' ensures these are always present in app_config
    # then iterating over app_config's keys for these sections would also work.
    # For now, keeping these as explicitly defined for clarity and to ensure all expected keyword sections are shown.
    render_keyword_section('categories', 'Category Keywords', ['keywords'])
    render_keyword_section('business_expenses', 'Business Expense Keywords', ['keywords'])
    render_keyword_section('checking_accounts', 'Checking Account Keywords', ['keywords_deposit', 'keywords_withdrawal'])
    render_keyword_section('savings_accounts', 'Savings Account Keywords', ['keywords_deposit', 'keywords_withdrawal'])
    render_keyword_section('debt_accounts', 'Debt Account Keywords', ['keywords_accrual', 'keywords_payment'])
    render_keyword_section('other_accounts', 'Other Account Keywords', ['keywords_deposit', 'keywords_withdrawal'])


    # LLM Settings and OCR Confidence Threshold
    st.subheader("Application Settings")

    # Populate with existing values or defaults from app_config
    st.session_state.app_config['llm_model_name'] = st.text_input(
        "LLM Model Name",
        value=st.session_state.app_config.get('llm_model_name', 'placeholder-model'),
        key="app_llm_model_name",
        on_change=lambda: st.session_state.update(default_config_saved_recently=False)
    )
    st.session_state.app_config['llm_temperature'] = st.number_input(
        "LLM Temperature",
        value=float(st.session_state.app_config.get('llm_temperature', 0.7)),
        min_value=0.0, max_value=2.0, step=0.05,
        key="app_llm_temperature",
        on_change=lambda: st.session_state.update(default_config_saved_recently=False)
    )
    st.session_state.app_config['llm_max_tokens'] = st.number_input(
        "LLM Max Tokens",
        value=int(st.session_state.app_config.get('llm_max_tokens', 50)),
        min_value=1, step=1,
        key="app_llm_max_tokens",
        on_change=lambda: st.session_state.update(default_config_saved_recently=False)
    )
    st.session_state.app_config['ocr_confidence_threshold'] = st.number_input(
        "OCR Confidence Threshold",
        value=float(st.session_state.app_config.get('ocr_confidence_threshold', 0.8)),
        min_value=0.0, max_value=1.0, step=0.01,
        key="app_ocr_confidence_threshold",
        on_change=lambda: st.session_state.update(default_config_saved_recently=False)
    )
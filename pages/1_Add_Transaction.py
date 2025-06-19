# pages/1_Add_Transaction.py

import streamlit as st
import datetime
from modules.managers.csv_manager import CSVManager
from modules.managers.payee_manager import PayeeManager
from modules.managers.transaction_manager import TransactionManager
from modules.managers.finance_config_manager import FinanceConfigManager
from modules.managers.app_config_manager import AppConfigManager  # NEW
from modules.managers.metadata_manager import MetadataManager  # NEW
from modules.ui_tabs.manual_entry_tab import display_manual_entry_tab

# --- Page Configuration ---
st.set_page_config(
    page_title="Add Transaction",
    page_icon="💸",
    layout="centered"
)

st.title("Add a New Transaction")
st.write("Use the tabs below to add transactions manually, from an invoice, or by importing a bank statement.")


# --- Manager Initialization ---
@st.cache_resource
def get_managers():
    # Initialize AppConfigManager first to get all application-wide paths and settings
    app_config_manager = AppConfigManager()
    app_config = app_config_manager.get_config()

    # Get paths from app_config
    transactions_csv_path = app_config_manager.get_path('transactions_csv_file')
    payees_csv_path = app_config_manager.get_path('payees_csv_file')
    metadata_csv_path = app_config_manager.get_path('metadata_csv_file')  # NEW: Metadata path

    default_config_dir = app_config_manager.get_path('default_config_dir')
    monthly_config_dir = app_config_manager.get_path('monthly_config_dir')
    default_finance_config_file = app_config_manager.get_path('default_finance_config_file')

    # Get current month and year for monthly config
    current_date = datetime.date.today()
    current_year = current_date.year
    current_month = current_date.month

    # Initialize core managers
    csv_manager = CSVManager(transactions_csv_path, payees_csv_path, metadata_csv_path)
    metadata_manager = MetadataManager(csv_manager)

    finance_config_manager = None
    try:
        # Initialize FinanceConfigManager with current month/year and paths from app_config
        finance_config_manager = FinanceConfigManager(
            current_month=current_month,
            current_year=current_year,
            default_config_dir=default_config_dir,
            default_finance_config_file=default_finance_config_file,
            monthly_config_dir=monthly_config_dir
        )
    except FileNotFoundError as e:
        st.error(
            f"Configuration File Missing: {e}. Please ensure '{default_config_dir}{default_finance_config_file}' exists and is valid.")
        st.stop()
    except Exception as e:
        st.error(f"An unexpected error occurred during financial configuration loading: {e}")
        st.stop()

    payee_manager = PayeeManager(csv_manager=csv_manager)

    # TransactionManager takes all relevant managers and the full app_config
    transaction_manager = TransactionManager(
        csv_manager=csv_manager,
        finance_config_manager=finance_config_manager,  # Renamed from config_manager for clarity
        payee_manager=payee_manager,
        metadata_manager=metadata_manager,  # Pass metadata_manager
        app_config=app_config  # Pass the full app_config
    )

    return transaction_manager, finance_config_manager, payee_manager, app_config_manager  # Also return app_config_manager


transaction_manager, finance_config_manager, payee_manager, app_config_manager = get_managers()

# --- Display Budget Validation Messages ---
validation_messages = finance_config_manager.get_validation_messages()
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
tab_manual_entry, tab_invoice_entry, tab_statement_entry = st.tabs(
    ["Manual Entry", "From Invoice/Receipt", "From Bank Statement"])

with tab_manual_entry:
    # Pass app_config_manager to manual_entry_tab for app-wide settings like currency display
    display_manual_entry_tab(transaction_manager, finance_config_manager, app_config_manager)

with tab_invoice_entry:
    st.header("Upload an Invoice or Receipt")
    # Placeholder for invoice upload logic
    uploaded_invoice_file = st.file_uploader("Upload Image or PDF Invoice", type=['png', 'jpg', 'jpeg', 'pdf'],
                                             key="invoice_uploader")
    if uploaded_invoice_file:
        st.info("Processing invoice... This may take a moment.")
        try:
            # Process the uploaded file
            suggested_data = transaction_manager.process_uploaded_invoice(uploaded_invoice_file)
            st.success("Invoice processed successfully! Review the suggested transaction below.")

            st.subheader("Suggested Transaction Details from Invoice")
            st.json(suggested_data)  # Display the raw parsed data for review

            # You might want a form here to allow user to edit and then call add_manual_transaction
            # For simplicity, let's auto-add it for now (you'd replace with a review/edit UI)
            if st.button("Add Processed Invoice as Transaction", key="add_invoice_processed_btn"):
                # Reconstruct splits for add_manual_transaction
                splits_to_add = []
                for split in suggested_data['splits']:
                    splits_to_add.append({
                        'description': split.get('description', ''),
                        'amount': split.get('amount', 0.0),
                        'notes': split.get('notes', ''),
                        'budget_scope': split.get('budget_scope', ''),
                        'category': split.get('category', ''),
                        'sub_category': split.get('sub_category', ''),
                        'full_budget_path': split.get('full_budget_path', '')
                    })

                # Use the original uploaded file object to pass to add_manual_transaction
                # This might need re-handling if the file object is consumed or needs to be re-read.
                # For now, we'll pass the path, assuming add_manual_transaction can handle it (it copies it)

                transaction_manager.add_manual_transaction(
                    transaction_id=suggested_data['transaction_id'],
                    transaction_type=suggested_data.get('transaction_type', 'Expense'),
                    # Use parsed type, default to Expense
                    date=suggested_data['date'],
                    payee=suggested_data['payee'],
                    account=suggested_data['account'],
                    uploaded_file=uploaded_invoice_file,  # Pass the original uploaded file
                    splits=splits_to_add,
                    manual_metadata=suggested_data.get('metadata', [])
                )
                st.success(f"Invoice transaction saved successfully with ID: **{suggested_data['transaction_id']}**")
                # Clear the uploader to allow new upload
                st.session_state["invoice_uploader"] = None
                st.rerun()

        except Exception as e:
            st.error(f"Error processing invoice: {e}")
            st.warning("Please try another file or use manual entry.")

with tab_statement_entry:
    st.header("Import a Bank Statement")
    st.info("This feature is coming soon! Bank statements will be parsed and matched with existing transactions.")

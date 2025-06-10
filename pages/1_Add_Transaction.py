# pages/1_Add_Transaction.py

import streamlit as st
import datetime
from modules.managers.csv_manager import CSVManager
from modules.managers.payee_manager import PayeeManager
from modules.managers.transaction_manager import TransactionManager
from modules.managers.finance_config_manager import FinanceConfigManager  # Renamed import
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
    # Define paths
    transactions_csv_path = 'data/transactions.csv'
    payees_csv_path = 'data/payees.csv'

    # Get current month and year for monthly config
    current_date = datetime.date.today()
    current_year = current_date.year
    current_month = current_date.month

    # Initialize managers
    csv_manager = CSVManager(transactions_csv_path, payees_csv_path)
    finance_config_manager = None
    try:
        # Initialize FinanceConfigManager with current month/year
        finance_config_manager = FinanceConfigManager(current_month=current_month, current_year=current_year,
                                                      default_config_dir='configs/defaults/',
                                                      default_config_file='financial_config_default.yaml',
                                                      monthly_config_dir='configs/monthly/')
    except FileNotFoundError as e:
        st.error(
            f"Configuration File Missing: {e}. Please ensure 'configs/defaults/financial_config_default.yaml' exists.")
        # If the default config is missing, we can't proceed, so we stop here.
        st.stop()
    except Exception as e:
        st.error(f"An unexpected error occurred during configuration loading: {e}")
        # For other critical errors, also stop.
        st.stop()

    # PayeeManager now correctly takes CSVManager as its dependency.
    payee_manager = PayeeManager(csv_manager=csv_manager)

    # TransactionManager takes all relevant managers.
    transaction_manager = TransactionManager(csv_manager=csv_manager,
                                             config_manager=finance_config_manager,
                                             payee_manager=payee_manager)

    return transaction_manager, finance_config_manager, payee_manager


transaction_manager, finance_config_manager, payee_manager = get_managers()

# --- Display Budget Validation Messages ---
validation_messages = finance_config_manager.get_validation_messages()
if validation_messages:
    st.subheader("Budget Configuration Alerts")
    for msg in validation_messages:
        msg_type = msg.get('type')
        msg_content = msg.get('message')
        if msg_type == 'alarm':
            st.error(msg_content, icon="🚨")  # Red, most annoying
        elif msg_type == 'warning':
            st.warning(msg_content, icon="⚠️")  # Yellow
        elif msg_type == 'note':
            st.info(msg_content, icon="💡")  # Blue/light yellow, a reminder

# --- Tab-based UI ---
tab_manual_entry, tab_invoice_entry, tab_statement_entry = st.tabs(
    ["Manual Entry", "From Invoice/Receipt", "From Bank Statement"])

with tab_manual_entry:
    display_manual_entry_tab(transaction_manager, finance_config_manager)

with tab_invoice_entry:
    st.header("Upload an Invoice or Receipt")
    st.info("This feature is coming soon! Uploaded invoices will be processed by OCR for automatic data extraction.")

with tab_statement_entry:
    st.header("Import a Bank Statement")
    st.info("This feature is coming soon! Bank statements will be parsed and matched with existing transactions.")
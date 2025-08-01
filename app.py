# your_finance_app/app.py

import streamlit as st
import datetime # Import datetime here as it's used in manager initialization

# Import necessary managers
from modules.managers.csv_manager import CSVManager
from modules.managers.payee_manager import PayeeManager
from modules.managers.transaction_manager import TransactionManager
from modules.managers.finance_config_manager import MonthlyFinanceConfigManager
from modules.managers.app_config_manager import AppConfigManager
from modules.managers.metadata_manager import MetadataManager
from modules.managers.photo_manager import PhotoManager
# No need to import ui_tabs or automation modules here for initial setup

# Set general page configuration for the entire app
st.set_page_config(
    page_title="Personal Finance Dashboard",
    page_icon="💰",
    layout="wide", # Use 'wide' layout by default
    initial_sidebar_state="expanded" # Sidebar expanded by default
)

# --- Manager Initialization (Moved to app.py and cached) ---
# This function will run only once due to st.cache_resource
@st.cache_resource
def initialize_managers():
    st.info("Initializing application managers... This may take a moment.")
    # Initialize AppConfigManager first to get all application-wide paths and settings
    app_config_manager = AppConfigManager()
    app_config = app_config_manager.get_config()

    # Get paths from app_config
    transactions_csv_path = app_config_manager.get_path('transactions_csv_file')
    payees_csv_path = app_config_manager.get_path('payees_csv_file')
    metadata_csv_path = app_config_manager.get_path('metadata_csv_file')

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

    monthly_finance_config_manager = None
    try:
        # Initialize FinanceConfigManager with current month/year and paths from app_config
        monthly_finance_config_manager = MonthlyFinanceConfigManager(
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
    photo_manager = PhotoManager(csv_manager=csv_manager, photo_storage_dir=app_config_manager.get_path('invoices_input_dir'))
    # TransactionManager takes all relevant managers and the full app_config
    transaction_manager = TransactionManager(
        csv_manager=csv_manager,
        monthly_finance_config_manager=monthly_finance_config_manager,
        payee_manager=payee_manager,
        metadata_manager=metadata_manager,
        app_config=app_config,
        photo_manager=photo_manager
    )
    st.success("Managers initialized successfully!")
    return {
        "transaction_manager": transaction_manager,
        "monthly_finance_config_manager": monthly_finance_config_manager,
        "payee_manager": payee_manager,
        "app_config_manager": app_config_manager,
        "csv_manager": csv_manager, # Also store csv_manager for direct access if needed
        "metadata_manager": metadata_manager, # Also store metadata_manager for direct access if needed
        "photo_manager": photo_manager, # store photo_manager for direct access only if needed
    }

# Call the initialization function and store managers in session_state
if 'managers' not in st.session_state:
    st.session_state.managers = initialize_managers()

# You can add a title or introductory text for your main app page
st.title("Welcome to Your Personal Finance Dashboard!")
st.write("Use the sidebar to navigate through the different sections of the application.")

# Optionally, add some high-level overview or instructions here.
# For example:
st.markdown("""
This application helps you manage your personal finances by:
-   **Configuring your financial accounts and budgets.**
-   **Adding and managing your transactions.**
-   **Analyzing your spending and savings.**

Navigate using the links in the sidebar to get started!
""")

# Note: You do NOT explicitly import config_manager.py or pages/config_page.py here.
# Streamlit handles the discovery of pages in the 'pages/' directory.
# The `ConfigManager` is initialized within `config_page.py` and stored in `st.session_state`.
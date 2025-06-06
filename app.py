# your_finance_app/app.py

import streamlit as st

# Set general page configuration for the entire app
st.set_page_config(
    page_title="Personal Finance Dashboard",
    page_icon="💰",
    layout="wide", # Use 'wide' layout by default
    initial_sidebar_state="expanded" # Sidebar expanded by default
)

# You can add a title or introductory text for your main app page
st.title("Welcome to Your Personal Finance Dashboard!")
st.write("Use the sidebar to navigate through the different sections of the application.")

# Optionally, add some high-level overview or instructions here.
# For example:
st.markdown("""
This application helps you manage your personal finances by:
-   **Configuring your financial accounts and budgets.**
-   **Analyzing your transactions.**
-   **Providing insights into your spending and savings.**

Navigate using the links in the sidebar to get started!
""")

# Note: You do NOT explicitly import config_manager.py or pages/config_page.py here.
# Streamlit handles the discovery of pages in the 'pages/' directory.
# The `ConfigManager` is initialized within `config_page.py` and stored in `st.session_state`.
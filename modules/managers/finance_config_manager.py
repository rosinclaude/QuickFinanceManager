# modules/managers/finance_config_manager.py

import yaml
import os
import shutil
import datetime
from .budget_manager import BudgetManager


class FinanceConfigManager:
    """
    Manages loading and providing access to the financial configuration from YAML files.
    Prioritizes monthly configurations, falling back to a default template.
    Automatically creates monthly config if it doesn't exist.
    """
    DEFAULT_CONFIG_DIR = 'configs/defaults/'
    MONTHLY_CONFIG_DIR = 'configs/monthly/'
    DEFAULT_CONFIG_FILE = 'financial_config_default.yaml'

    def __init__(self, current_month: int, current_year: int):
        self.current_month = current_month
        self.current_year = current_year
        self._config = {}
        self.budget_manager = BudgetManager()
        self.validation_messages = []  # Store validation messages here

        self._ensure_config_dirs_exist()
        self._load_and_prepare_config()
        self._validate_config()  # This will now populate self.validation_messages

    def _ensure_config_dirs_exist(self):
        """Ensures the default and monthly config directories exist."""
        os.makedirs(self.DEFAULT_CONFIG_DIR, exist_ok=True)
        os.makedirs(self.MONTHLY_CONFIG_DIR, exist_ok=True)

    def _load_and_prepare_config(self):
        """
        Loads the monthly config if available, otherwise copies from default and loads it.
        """
        monthly_config_filename = f"financial_config_{self.current_year:04d}_{self.current_month:02d}.yaml"
        self.monthly_config_path = os.path.join(self.MONTHLY_CONFIG_DIR, monthly_config_filename)
        self.default_config_path = os.path.join(self.DEFAULT_CONFIG_DIR, self.DEFAULT_CONFIG_FILE)

        if not os.path.exists(self.default_config_path):
            raise FileNotFoundError(
                f"Default financial config file not found at: {self.default_config_path}. Please create it.")

        if not os.path.exists(self.monthly_config_path):
            print(f"Monthly config not found for {self.current_year}/{self.current_month}. Copying from default.")
            shutil.copy(self.default_config_path, self.monthly_config_path)

            # Update month and year in the new monthly config file
            try:
                with open(self.monthly_config_path, 'r') as f:
                    config_content = yaml.safe_load(f)
                config_content['month'] = self.current_month
                config_content['year'] = self.current_year
                with open(self.monthly_config_path, 'w') as f:
                    yaml.safe_dump(config_content, f, default_flow_style=False, sort_keys=False)
                print(f"Created and updated monthly config: {self.monthly_config_path}")
            except Exception as e:
                self.validation_messages.append(
                    {'type': 'alarm', 'message': f"Error updating month/year in new monthly config: {e}"})

        try:
            with open(self.monthly_config_path, 'r') as file:
                self._config = yaml.safe_load(file)
            print(f"Loaded financial config from: {self.monthly_config_path}")
        except yaml.YAMLError as e:
            self.validation_messages.append({'type': 'alarm',
                                             'message': f"Error parsing YAML financial config file '{self.monthly_config_path}': {e}. Please correct the YAML syntax."})
            # To allow app to continue with potentially incomplete config, we might not raise here,
            # but rather return an empty config or default config and let UI handle it.
            # For now, we'll load an empty config if parsing fails to prevent app crash.
            self._config = {}
        except FileNotFoundError:
            self.validation_messages.append({'type': 'alarm',
                                             'message': f"Financial config file not found at: {self.monthly_config_path}. This should not happen if default exists and copy was successful."})
            self._config = {}  # Load empty config to avoid errors later

    def _validate_config(self):
        """Validates the loaded configuration using the BudgetManager."""
        try:
            self.validation_messages.extend(self.budget_manager.validate_budget_allocations(self._config))
        except Exception as e:
            self.validation_messages.append(
                {'type': 'alarm', 'message': f"An unexpected error occurred during budget validation: {e}"})

    def get_config(self) -> dict:
        """Returns the entire loaded financial configuration."""
        return self._config

    def get_currency(self) -> str:
        """Returns the default currency."""
        return self._config.get('currency', 'CAD')

    def get_budget_scopes(self) -> list:
        """Returns a list of top-level budget scopes (e.g., 'Family', 'Personal')."""
        return self._config.get('budget_scopes', [])

    def get_income_categories(self) -> list:
        """Returns a list of defined income categories."""
        return list(self._config.get('income_categories', {}).keys())

    def get_accounts_by_type(self) -> dict:
        """
        Returns a dictionary mapping account types to a list of account names.
        e.g., {'Credit Card': ['DESJARDINS_VISA_0002'], 'Regular Savings': ['Personal_Savings'], 'Physical Cash': ['Cash']}
        """
        accounts_by_type = {}
        if not self._config: return accounts_by_type  # Return empty if config not loaded

        for acc_type_group, accounts_dict in self._config.items():
            if acc_type_group in ['savings_accounts', 'debt_accounts', 'other_accounts']:
                for acc_name, acc_details in accounts_dict.items():
                    type_name = acc_details.get('type', 'Other')
                    if type_name not in accounts_by_type:
                        accounts_by_type[type_name] = []
                    accounts_by_type[type_name].append(acc_name)
        return accounts_by_type

    def get_all_accounts_with_types(self) -> list:
        """
        Returns a list of tuples (account_name, account_type) for all accounts.
        e.g., [('DESJARDINS_VISA_0002', 'Credit Card'), ('Personal_Savings', 'Regular Savings')]
        """
        all_accounts = []
        if not self._config: return all_accounts  # Return empty if config not loaded

        if 'savings_accounts' in self._config:
            for name, details in self._config['savings_accounts'].items():
                all_accounts.append((name, details.get('type', 'Savings')))
        if 'debt_accounts' in self._config:
            for name, details in self._config['debt_accounts'].items():
                all_accounts.append((name, details.get('type', 'Debt')))
        if 'other_accounts' in self._config:
            for name, details in self._config['other_accounts'].items():
                all_accounts.append((name, details.get('type', 'Other')))
        return all_accounts

    def get_category_structure_for_ui(self) -> dict:
        """
        Prepares a deeply nested dictionary suitable for Streamlit's selectbox dependencies,
        reflecting the full hierarchy of budget categories and sub-budgets.
        """
        structured_categories = {}
        if not self._config:
            return structured_categories  # Return empty if config not loaded

        # Add Income Categories
        structured_categories['Income'] = list(self._config.get('income_categories', {}).keys())

        # Add Expense Categories per Budget Scope
        for scope_name in self.get_budget_scopes():
            structured_categories[scope_name] = self._build_nested_budget_structure(
                self._config.get(scope_name, {}).get('budget', {})
            )
        return structured_categories

    def _build_nested_budget_structure(self, budget_section: dict) -> dict | list:
        """
        Recursively builds the nested dictionary or list for a budget section.

        Args:
            budget_section (dict): A dictionary representing a portion of the budget hierarchy.

        Returns:
            dict | list: A nested dictionary reflecting categories or a list of sub-categories.
        """
        result_structure = {}

        for item_name, item_details in budget_section.items():
            if isinstance(item_details, dict):
                if 'budget' in item_details and isinstance(item_details['budget'], dict):
                    # This item has a nested 'budget' (e.g., 'Businesses', 'Photography Business')
                    # Recursively process its nested budget
                    result_structure[item_name] = self._build_nested_budget_structure(item_details['budget'])
                elif 'amount' in item_details:
                    # This is a final category with an amount, but no further nesting under 'budget'
                    # Treat it as a leaf node that doesn't expand further in the UI
                    result_structure[item_name] = []  # Or you could use None if you prefer
                elif 'template' in item_details:
                    # This is a business/template entry that *also* has a 'budget' key under it for its categories
                    # Handle this similar to the 'budget' in item_details path
                    if 'budget' in item_details and isinstance(item_details['budget'], dict):
                        result_structure[item_name] = self._build_nested_budget_structure(item_details['budget'])
                    else:
                        result_structure[item_name] = []  # A template without explicit sub-budget categories
                else:
                    # It's a dictionary, but not a nested budget or amount-based category.
                    # This might be an empty category or has other properties.
                    # For UI purposes, we'll assume it's a leaf or has no UI children.
                    result_structure[item_name] = []
            # This part handles direct category listings where the value is just the amount
            # e.g., 'Food': {'amount': 500} or 'Rent': {'amount': 1500}
            # For the UI, these are leaf nodes, so they have no further children to select.
            elif isinstance(item_details, (int, float)):
                result_structure[item_name] = []  # It's a direct amount, no further categories

        # Special case: if it's a list of actual subcategories (leaf nodes)
        # This occurs if the last 'budget' key in the YAML contains a list of names,
        # rather than a dictionary of category:details.
        # Based on your YAML, it's typically dict of category:details.
        # If your leaf categories are literally just names in a list,
        # e.g., 'Marketing': ['Online Ads', 'Print Ads'] directly in config:
        # you would need an extra check for `isinstance(budget_section, list)` and return `budget_section`
        # But `_build_nested_budget_structure` is always called with a `dict`.
        # So, the final leaf nodes are implicitly handled by `result_structure[item_name] = []`.

        return result_structure

    def get_validation_messages(self) -> list:
        """Returns the list of budget validation messages."""
        return self.validation_messages
# modules/managers/finance_config_manager.py
from typing import Optional, Dict, List, Any
import yaml
import os
import shutil
import datetime
from .budget_manager import BudgetManager  # Assuming this exists and is correctly implemented

class FinanceConfigManager:
    """
    Manages loading and providing access to the financial configuration from YAML files.
    Prioritizes monthly configurations, falling back to a default template.
    Automatically creates monthly config if it doesn't exist.
    """

    # Removed hardcoded paths; these will now be passed in via __init__
    # DEFAULT_CONFIG_DIR = 'configs/defaults/'
    # MONTHLY_CONFIG_DIR = 'configs/monthly/'
    # DEFAULT_CONFIG_FILE = 'financial_config_default.yaml'

    def __init__(self, current_month: int, current_year: int,
                 default_config_dir: str,
                 default_finance_config_file: str,
                 monthly_config_dir: str):
        self.current_month = current_month
        self.current_year = current_year

        # Use provided paths (these will come from AppConfigManager)
        self._default_config_dir = default_config_dir
        self._default_finance_config_file = default_finance_config_file
        self._monthly_config_dir = monthly_config_dir

        self._config = {}
        self.budget_manager = BudgetManager()
        self.validation_messages = []

        self._ensure_config_dirs_exist()
        self._load_and_prepare_config()
        self._validate_config()

        # Pre-process budget paths and category mappings for faster lookup
        self._full_budget_paths = self._build_full_budget_paths()
        self._default_category_mapping = self._build_default_category_mapping()

    def _ensure_config_dirs_exist(self):
        """Ensures the default and monthly config directories exist."""
        os.makedirs(self._default_config_dir, exist_ok=True)
        os.makedirs(self._monthly_config_dir, exist_ok=True)

    def _load_and_prepare_config(self):
        """
        Loads the default financial configuration and then overlays/creates
        the monthly configuration.
        """
        default_config_path = os.path.join(self._default_config_dir, self._default_finance_config_file)
        monthly_config_filename = f"financial_config_{self.current_year:04d}_{self.current_month:02d}.yaml"
        self.monthly_config_path = os.path.join(self._monthly_config_dir, monthly_config_filename)

        # 1. Ensure default financial config file exists, create if not
        if not os.path.exists(default_config_path):
            print(f"Default financial config file not found at {default_config_path}. Creating a default one.")
            self._create_default_config(default_config_path)

        # 2. Load the default configuration first
        try:
            with open(default_config_path, 'r') as f:
                self._config = yaml.safe_load(f)
            print(f"Loaded default financial config from: {default_config_path}")
        except yaml.YAMLError as e:
            self.validation_messages.append({'type': 'alarm',
                                             'message': f"Error parsing YAML default financial config file '{default_config_path}': {e}. Cannot proceed with default. Returning empty config."})
            self._config = {}
            return  # Stop if default fails to load

        # 3. Check for monthly config and create if it doesn't exist
        if not os.path.exists(self.monthly_config_path):
            print(
                f"Monthly financial config for {self.current_year}-{self.current_month:02d} not found. Copying from default.")
            shutil.copyfile(default_config_path, self.monthly_config_path)

            # Update month and year in the new monthly config file
            try:
                with open(self.monthly_config_path, 'r') as f:
                    config_content = yaml.safe_load(f)
                config_content['month'] = self.current_month
                config_content['year'] = self.current_year
                with open(self.monthly_config_path, 'w') as f:
                    yaml.safe_dump(config_content, f, default_flow_style=False, indent=2)  # Use indent for readability
                print(f"Created and updated monthly config: {self.monthly_config_path}")
            except Exception as e:
                self.validation_messages.append(
                    {'type': 'alarm', 'message': f"Error updating month/year in new monthly config: {e}"})

        # 4. Load monthly config on top of default
        try:
            with open(self.monthly_config_path, 'r') as f:
                monthly_data = yaml.safe_load(f)
                self._config = self._deep_merge_dicts(self._config, monthly_data)
            print(f"Loaded and merged monthly financial config from: {self.monthly_config_path}")
        except yaml.YAMLError as e:
            self.validation_messages.append({'type': 'alarm',
                                             'message': f"Error parsing YAML monthly financial config file '{self.monthly_config_path}': {e}. Using only default config."})
            # If monthly fails, _config retains the default data loaded earlier
        except FileNotFoundError:
            self.validation_messages.append({'type': 'alarm',
                                             'message': f"Monthly financial config file not found at: {self.monthly_config_path}. This should not happen. Using only default config."})

        # 5. Resolve templates after initial merge
        self._resolve_templates()

        print(f"Final financial configuration loaded for {self.current_year}-{self.current_month:02d}.")

    def _deep_merge_dicts(self, dict1: Dict, dict2: Dict) -> Dict:
        """Recursively merges dict2 into dict1. Values in dict2 override values in dict1."""
        merged = dict1.copy()
        for key, value in dict2.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = self._deep_merge_dicts(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _create_default_config(self, path: str):
        """Creates a basic default financial configuration file based on the new structure."""
        default_content = {
            'month': 'Default',
            'year': 0000,
            'currency': 'CAD',
            'currency_symbol': '$',
            '_definitions': {
                'template_business_expenses': {
                    'Marketing': {'amount': 0.00, 'description': 'Expenses related to promoting the business.'},
                    'Supplies': {'amount': 0.00, 'description': 'Materials and consumables for business operations.'},
                    'Equipment': {'amount': 0.00, 'description': 'Tools and machinery purchases or rentals.'},
                    'Travel': {'amount': 0.00, 'description': 'Business-related travel costs.'},
                    'Miscellaneous': {'amount': 0.00,
                                      'description': 'Catch-all for minor, uncategorized business expenses.'}
                }
            },
            'budget_scopes': ['Family', 'Personal'],
            'income_categories': {
                'Salary_Primary': {'description': 'Regular income from primary employment.'},
                'Freelance_Work': {'description': 'Income from independent contract or gig work.'},
                'Investment_Dividends': {'description': 'Income from stock dividends or other investments.'},
                'Rental_Income': {'description': 'Income from rented properties.'},
                'Gifts_Received': {'description': 'Money received as gifts.'},
                'Reimbursements': {'description': 'Money reimbursed for expenses.'},
                'Other_Income': {'description': 'Any other source of income not specifically categorized.'},
                'Salary_Photography': {'description': 'Salary from Photography Business.'},
                'Salary_Food': {'description': 'Salary from Food Business.'},
                'Salary_Sewing': {'description': 'Salary from Sewing Business.'},
                'Salary_Soap': {'description': 'Salary from Soap Making Business.'}
            },
            'Family': {
                'allocated': 5855.00,
                'budget': {
                    'Food': {'amount': 700.00,
                             'description': 'Groceries, dining out, and other food-related expenses.'},
                    'Transport_Gas': {'amount': 200.00, 'description': 'Fuel and public transportation costs.'},
                    'Car_Maintenance': {'amount': 250.00, 'description': 'Vehicle repairs, servicing, and upkeep.'},
                    'Utilities': {'amount': 250.00,
                                  'description': 'Electricity, water, internet, and other household utilities.'},
                    'Rent_Mortgage': {'amount': 1465.00, 'description': 'Monthly housing payment.'},
                    'Entertainment': {'amount': 100.00, 'description': 'Leisure activities, movies, concerts, etc.'},
                    'Health': {'amount': 75.00,
                               'description': 'Medical co-pays, prescriptions, and health-related items.'},
                    'Shopping': {'amount': 150.00, 'description': 'General retail purchases (excluding clothing).'},
                    'Clothing': {'amount': 70.00, 'description': 'Apparel and footwear purchases.'},
                    'Home_Supplies': {'amount': 100.00,
                                      'description': 'Cleaning supplies, household items, and minor repairs.'},
                    'Child_Expenses': {'amount': 350.00,
                                       'description': 'General expenses for children (e.g., toys, school supplies).'},
                    'Child_Nursery_Daycare': {'amount': 1300.00, 'description': 'Costs for childcare services.'},
                    'Insurances': {'amount': 400.00,
                                   'description': 'Premiums for various insurance policies (e.g., home, car, life).'},
                    'Pet_Care': {'amount': 0.00,
                                 'description': 'Expenses related to pet food, vet visits, and supplies.'},
                    'Education_Personal_Development': {'amount': 60.00,
                                                       'description': 'Costs for courses, books, and personal skill development.'},
                    'Travel': {'amount': 100.00,
                               'description': 'Travel-related expenses (e.g., short trips, weekend getaways).'},
                    'Subscriptions': {'amount': 50.00,
                                      'description': 'Recurring payments for services (e.g., streaming, software).'},
                    'Gifts_Donations_Family': {'amount': 50.00,
                                               'description': 'Gifts for family members or donations to family causes.'},
                    'Gifts_Donations_Friends': {'amount': 0.00, 'description': 'Gifts for friends.'},
                    'Gifts_Donations_Religious_Charity': {'amount': 25.00,
                                                          'description': 'Contributions to religious organizations or charities.'},
                    'Hobbies_Recreation': {'amount': 60.00,
                                           'description': 'Expenses for hobbies, sports, and recreational activities.'},
                    'Miscellaneous': {'amount': 100.00, 'description': 'Catch-all for anything not easily categorized.'}
                }
            },
            'Personal': {
                'allocated': 750.00,
                'budget': {
                    'Businesses': {
                        'allocated': 125.00,
                        'budget': {
                            'Photography_Business': {
                                'allocated': 000.00,
                                'template': 'template_business_expenses',
                                'budget': {  # This 'budget' section overrides or extends the template
                                    'Marketing': {'amount': 00.00,
                                                  'description': 'Specific marketing for photography.'},
                                    'Equipment': {'amount': 00.00, 'description': 'Camera gear, editing software.'},
                                    'Miscellaneous': {'amount': 00.00,
                                                      'description': 'Small, uncategorized photography expenses.'}
                                }
                            },
                            'Food_Business': {
                                'allocated': 50.00,
                                'template': 'template_business_expenses',
                                'budget': {
                                    'Supplies': {'amount': 50.00, 'description': 'Ingredients, packaging.'},
                                    'Packaging': {'amount': 00.00,
                                                  'description': 'Custom category: food packaging materials.'}
                                    # Example of custom key
                                }
                            },
                            'Sewing_Business': {
                                'allocated': 00.00,
                                'template': 'template_business_expenses',
                                'budget': {
                                    'Supplies': {'amount': 00.00, 'description': 'Fabric, thread, patterns.'}
                                }
                            },
                            'Soap_Making_Business': {
                                'allocated': 75.00,
                                'template': 'template_business_expenses',
                                'budget': {
                                    'Supplies': {'amount': 75.00, 'description': 'Soap bases, essential oils, molds.'},
                                    'Marketing': {'amount': 00.00, 'description': 'Promoting soap products.'}
                                }
                            }
                        }
                    },
                    'Miscellaneous': {'amount': 25.00, 'description': 'Personal miscellaneous spending.'},
                    'Subscriptions': {'amount': 25.00,
                                      'description': 'Personal subscriptions (e.g., gym, personal apps).'},
                    'Hobbies_Recreation': {'amount': 25.00, 'description': 'Personal hobbies and leisure activities.'}
                }
            },
            'savings_accounts': {  # These should probably be under a top-level 'accounts' key for consistency
                'Personal_Savings': {'name': 'My Personal Savings', 'type': 'Regular Savings', 'initial_balance': 0.0,
                                     'current_balance': 0.0}
            },
            'debt_accounts': {
                'DESJARDINS_VISA_0012': {'name': 'Desjardins Visa', 'type': 'Credit Card', 'limit': 9500.0,
                                         'initial_owed': 2334.74, 'current_owed': 2334.74}
            },
            'other_accounts': {
                'Cash': {'type': 'Physical Cash', 'initial_balance': 0.0, 'current_balance': 0.0}
            },
            'default_category_mapping': {
                'Family:Food': ['MAXI', 'IGA', 'WALMART', 'LOBLAW', 'SUPER C', 'PROVIGO', 'METRO', 'COSTCO',
                                'GROCERIES'],
                'Family:Entertainment': ['RESTAURANT', 'TIM HORTONS', 'STARBUCKS', 'MCDONALDS', 'BURGER KING', 'CINEMA',
                                         'CAFE'],
                'Family:Transport_Gas': ['ESSO', 'PETRO CANADA', 'SHELL', 'ULTRAMAR', 'GAS STATION', 'FUEL'],
                'Family:Utilities': ['BELL CANADA', 'VIDEOTRON', 'ROGERS', 'HYDRO-QUEBEC', 'INTERNET BILL',
                                     'ELECTRICITY'],
                'Family:Rent_Mortgage': ['RENT PAYMENT', 'LOUEUR', 'MORTGAGE'],
                'Family:Health': ['PHARMAPRIX', 'JEAN COUTU', 'PHARMACIE', 'UNIPRIX', 'DOCTOR VISIT'],
                'Family:Subscriptions': ['NETFLIX', 'SPOTIFY', 'DISNEY PLUS', 'AMAZON PRIME', 'HULU',
                                         'YOUTUBE PREMIUM'],
                'Personal:Businesses:Photography_Business:Equipment': ['CAMERA GEAR', 'LENS', 'PHOTOGRAPHY EQUIPMENT',
                                                                       'ADOBE CREATIVE CLOUD'],
                'Personal:Businesses:Food_Business:Supplies': ['FOOD INGREDIENTS', 'PACKAGING', 'WHOLESALE FOOD'],
                'Income:Salary_Primary': ['PAYROLL', 'SALARY DEPOSIT', 'WORK PAYMENT'],
                'Income:Freelance_Work': ['FREELANCE PAYMENT', 'CLIENT PAYMENT', 'CONTRACT WORK'],
                'Income:Investment_Dividends': ['DIVIDEND', 'INVESTMENT RETURN']
            }
        }
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            yaml.dump(default_content, f, default_flow_style=False, indent=2)
        print(f"Default financial configuration created at {path}")

    def _resolve_templates(self):
        """Recursively resolves templates within the loaded configuration."""
        definitions = self._config.get('_definitions', {})

        def apply_template_recursive(node: Any):
            # Base case: if not a dictionary, return as is
            if not isinstance(node, dict):
                return node

            # If this node has a 'template' key, resolve it
            if 'template' in node and node['template'] in definitions:
                template_name = node['template']
                template_content = definitions[template_name]

                # Merge template content into the current node's budget if 'budget' exists
                # or directly into the node if no 'budget' but template content is dict
                if 'budget' in node and isinstance(node['budget'], dict):
                    # Merge template's content into the node's 'budget' sub-dict
                    node['budget'] = self._deep_merge_dicts(template_content, node['budget'])
                else:
                    # If no 'budget' key, directly merge template content into the current node,
                    # ensuring existing keys in node take precedence.
                    # This implies the template's structure might directly apply at this level.
                    node = self._deep_merge_dicts(template_content, node)

                # Remove the template key after applying
                if 'template' in node:  # Check again as it might have been overridden by merge
                    del node['template']

                    # Recursively apply templates to child dictionaries
            for key, value in node.items():
                node[key] = apply_template_recursive(value)
            return node

        # Apply templates to the main budget scopes
        for scope_name in self._config.get('budget_scopes', []):
            if scope_name in self._config:
                self._config[scope_name] = apply_template_recursive(self._config[scope_name])

        print("Templates resolved in financial configuration.")

    def _validate_config(self):
        """Validates the loaded configuration using the BudgetManager and internal structure."""
        self.validation_messages = []  # Clear previous messages

        # Basic validation checks
        if 'currency' not in self._config or 'currency_symbol' not in self._config:
            self.validation_messages.append(
                {'type': 'alarm', 'message': "Currency and/or currency symbol not defined in config."})
        if 'income_categories' not in self._config or not self._config['income_categories']:
            self.validation_messages.append({'type': 'warning', 'message': "No income categories defined in config."})
        if 'budget_scopes' not in self._config or not self._config['budget_scopes']:
            self.validation_messages.append({'type': 'alarm', 'message': "No budget scopes defined in config."})

        # Check if defined budget scopes actually exist as sections
        for scope in self._config.get('budget_scopes', []):
            if scope not in self._config:
                self.validation_messages.append({'type': 'alarm',
                                                 'message': f"Budget scope '{scope}' listed in 'budget_scopes' but not defined as a top-level section."})
            elif 'budget' not in self._config[scope]:
                self.validation_messages.append(
                    {'type': 'alarm', 'message': f"Budget scope '{scope}' does not have a 'budget' section."})
            # Add more specific checks here if needed, e.g., if 'allocated' is missing

        # Validate accounts sections
        # account_sections = ['savings_accounts', 'debt_accounts', 'other_accounts',
        #                     'accounts']  # 'accounts' for future proofing
        account_sections = [section for section in self._config.keys() if 'accounts' in section]  # 'accounts' for future proofing
        found_any_account = False
        for section in account_sections:
            if section in self._config and self._config[section]:
                found_any_account = True
                break
        if not found_any_account:
            self.validation_messages.append(
                {'type': 'warning', 'message': "No accounts (savings, debt, other) defined in config."})

        # Validate _definitions and template usage (basic check)
        definitions = self._config.get('_definitions', {})
        for scope_name in self._config.get('budget_scopes', []):
            scope_data = self._config.get(scope_name, {})

            # Traverse and check for unresolved templates
            def _check_unresolved_templates(node: Any, current_path_str: str):
                if isinstance(node, dict):
                    if 'template' in node and node['template'] not in definitions:
                        self.validation_messages.append({'type': 'alarm',
                                                         'message': f"Unresolved template '{node['template']}' found at path '{current_path_str}'."})
                    for key, value in node.items():
                        if key not in ['amount', 'description', 'allocated', 'template']:
                            _check_unresolved_templates(value, f"{current_path_str}:{key}")

            _check_unresolved_templates(scope_data, scope_name)

        # Validate using BudgetManager (if it takes the full config)
        try:
            self.validation_messages.extend(self.budget_manager.validate_budget_allocations(self._config))
        except Exception as e:
            self.validation_messages.append(
                {'type': 'alarm',
                 'message': f"An unexpected error occurred during budget validation via BudgetManager: {e}"})

        if self.validation_messages:
            print("Configuration validation messages:")
            for msg in self.validation_messages:
                print(f"- {msg['type'].upper()}: {msg['message']}")

    def get_currency_symbol(self) -> str:
        return self._config.get('currency_symbol', '$')

    def get_currency(self, selected_account_name: str = '') -> str:
        if selected_account_name:
            for account_sections in [section for section in self._config.keys() if 'accounts' in section]:  # 'accounts' for future proofing
                for account_name, account_details in self._config[account_sections].items():
                    if account_details['name'] == selected_account_name:
                        return account_details.get('currency', self._config.get('currency', 'CAD'))
        return self._config.get('currency', 'CAD')

    def get_all_account_names(self) -> List[str]:
        """
        Returns a list of all configured account names from savings_accounts, debt_accounts, and other_accounts.
        """
        all_account_names = []
        # Check for each top-level account section and extend the list
        for section_key in ['savings_accounts', 'debt_accounts', 'other_accounts']:
            if section_key in self._config and isinstance(self._config[section_key], dict):
                all_account_names.extend(list(self._config[section_key].keys()))
        return all_account_names

    def get_all_budget_scopes(self) -> List[str]:
        """Returns a list of all top-level budget scopes (e.g., 'Family', 'Personal')."""
        # In the new config, budget_scopes is a list of strings directly
        return self._config.get('budget_scopes', [])

    def get_income_categories(self) -> List[str]:
        """Returns a list of all defined income categories."""
        return list(self._config.get('income_categories', {}).keys())

    def _build_full_budget_paths(self) -> List[str]:
        """
        Builds a flat list of all possible full budget paths (e.g., 'Family:Food', 'Personal:Businesses:Photography_Business:Marketing').
        This method will traverse the 'budget_scopes' and the actual budget sections after template resolution.
        """
        paths = []
        defined_scopes = self.get_all_budget_scopes()

        def traverse_budget(current_node: Dict[str, Any], current_path_parts: List[str]):
            # If the current node itself is a leaf (has 'amount' or 'description' but no 'budget' children)
            # This handles cases like Family:Food. The current_path_parts represents the full path to 'Food'.
            if 'amount' in current_node or 'description' in current_node:
                paths.append(":".join(current_path_parts))
                # Do not recurse further if it's a leaf.
                return

            # If it's a node that contains further budget items (e.g., 'Family' itself, or 'Personal:Businesses')
            if 'budget' in current_node and isinstance(current_node['budget'], dict):
                for key, value in current_node['budget'].items():
                    if isinstance(value, dict):
                        traverse_budget(value, current_path_parts + [key])
            # Handle cases where a category might exist without 'amount' or 'budget' (e.g., just a placeholder)
            # Or if it's a higher-level 'allocated' key without deeper budget.
            # We only add to paths if it's a final categorizable unit.

        # Traverse expense/general budget scopes
        for scope_name in defined_scopes:
            scope_data = self._config.get(scope_name, {})
            if 'budget' in scope_data and isinstance(scope_data['budget'], dict):
                # Start traversal from the 'budget' section of each scope
                for top_level_category_name, top_level_category_data in scope_data['budget'].items():
                    if isinstance(top_level_category_data, dict):  # Ensure it's a dict before recursing
                        traverse_budget(top_level_category_data, [scope_name, top_level_category_name])

        # Add income categories as valid paths
        for income_cat in self.get_income_categories():
            paths.append(f"Income:{income_cat}")

        print(f"Built {len(paths)} full budget paths.")
        return paths

    def get_full_budget_paths(self) -> List[str]:
        """Returns the pre-built list of all possible full budget paths."""
        return self._full_budget_paths

    def is_valid_budget_path(self, path: str) -> bool:
        """
        Checks if a given budget path (e.g., 'Family:Food', 'Income:Salary_Primary') is valid.
        """
        return path in self._full_budget_paths

    def _build_default_category_mapping(self) -> Dict[str, List[str]]:
        """
        Builds the default category mapping for rule-based categorization from the config.
        """
        mapping = self._config.get('default_category_mapping', {})
        print(f"Loaded {len(mapping)} default category mappings.")
        return mapping

    def get_default_category_mapping(self) -> Dict[str, List[str]]:
        """
        Returns the default category mapping for rule-based categorization.
        """
        return self._default_category_mapping

    def save_monthly_config(self):
        """Saves the current monthly configuration back to its YAML file."""
        try:
            with open(self.monthly_config_path, 'w') as file:
                # Use default_flow_style=False for block style, indent for readability
                yaml.dump(self._config, file, default_flow_style=False, indent=2)
            print(f"Monthly financial configuration saved to {self.monthly_config_path}.")
            # Re-validate after saving to catch any issues with the saved state
            self._validate_config()
        except Exception as e:
            self.validation_messages.append(
                {'type': 'alarm', 'message': f"Error saving monthly config to {self.monthly_config_path}: {e}"})

    # --- Methods for modifying config (if needed by UI) ---
    # These methods need to be adapted to the new config structure for adding/deleting items.
    # For now, keeping them as placeholders if their logic depends heavily on old structure.
    # The new config structure with nested 'budget' dicts will make these more complex.

    def add_account(self, account_section: str, account_name: str, account_type: str, initial_balance: float = 0.0):
        """Adds a new account to the monthly config within a specific section."""
        if account_section not in ['savings_accounts', 'debt_accounts', 'other_accounts']:
            print(f"Warning: Invalid account section '{account_section}'. Account not added.")
            return

        if account_section not in self._config:
            self._config[account_section] = {}

        if account_type == 'Credit Card':  # Specific handling for credit card limits
            self._config[account_section][account_name] = {'name': account_name, 'type': account_type,
                                                           'limit': initial_balance, 'initial_owed': 0.0,
                                                           'current_owed': 0.0}
        else:
            self._config[account_section][account_name] = {'name': account_name, 'type': account_type,
                                                           'initial_balance': initial_balance,
                                                           'current_balance': initial_balance}
        self.save_monthly_config()
        # After modification, rebuild paths and mappings to reflect changes
        self._full_budget_paths = self._build_full_budget_paths()
        print(f"Added account '{account_name}' to '{account_section}'.")

    def delete_account(self, account_section: str, account_name: str):
        """Deletes an account from the monthly config within a specific section."""
        if account_section in self._config and account_name in self._config[account_section]:
            del self._config[account_section][account_name]
            self.save_monthly_config()
            # After modification, rebuild paths and mappings to reflect changes
            self._full_budget_paths = self._build_full_budget_paths()
            print(f"Deleted account '{account_name}' from '{account_section}'.")

    def add_income_category(self, category_name: str, description: str = ""):
        """Adds a new income category."""
        if 'income_categories' not in self._config:
            self._config['income_categories'] = {}
        if category_name not in self._config['income_categories']:
            self._config['income_categories'][category_name] = {'description': description}
            self.save_monthly_config()
            self._full_budget_paths = self._build_full_budget_paths()  # Rebuild paths
            print(f"Added income category '{category_name}'.")

    def delete_income_category(self, category_name: str):
        """Deletes an income category."""
        if 'income_categories' in self._config and category_name in self._config['income_categories']:
            del self._config['income_categories'][category_name]
            self.save_monthly_config()
            self._full_budget_paths = self._build_full_budget_paths()  # Rebuild paths
            print(f"Deleted income category '{category_name}'.")

    def add_budget_category_or_subcategory(self, scope: str, path_parts: List[str], amount: Optional[float] = None,
                                           description: str = ""):
        """
        Adds a new budget category or subcategory to the monthly config.
        'path_parts' is a list like ['Food'] or ['Businesses', 'Photography_Business', 'Marketing'].
        Amount and description are for the leaf node.
        """
        if scope not in self._config.get('budget_scopes', []):
            print(f"Error: Budget scope '{scope}' is not defined. Cannot add category.")
            return

        current_level = self._config.get(scope, {}).get('budget', {})
        if not current_level:
            # If the budget section for this scope doesn't exist or is empty, initialize it
            if scope not in self._config:
                self._config[scope] = {}
            if 'budget' not in self._config[scope] or not isinstance(self._config[scope]['budget'], dict):
                self._config[scope]['budget'] = {}
            current_level = self._config[scope]['budget']

        for i, item_name in enumerate(path_parts):
            if i == len(path_parts) - 1:  # This is the item to add
                if item_name in current_level and isinstance(current_level[item_name], dict):
                    print(
                        f"Warning: Category/Subcategory '{item_name}' already exists at path '{scope}:{':'.join(path_parts)}'. Not adding.")
                    return

                new_item_content = {}
                if amount is not None:
                    new_item_content['amount'] = amount
                if description:
                    new_item_content['description'] = description

                # If it's a parent for deeper levels, add a 'budget' key.
                # If it's a leaf (has amount/description), no 'budget' key unless explicitly desired.
                if amount is None and not description:  # Create a parent node if no amount/description
                    new_item_content['budget'] = {}

                current_level[item_name] = new_item_content

            else:  # Traverse to the next level
                if item_name not in current_level or not isinstance(current_level[item_name], dict):
                    current_level[item_name] = {'budget': {}}  # Create intermediate dict with 'budget'
                elif 'budget' not in current_level[item_name] or not isinstance(current_level[item_name]['budget'],
                                                                                dict):
                    current_level[item_name]['budget'] = {}  # Ensure it has a budget dict

                current_level = current_level[item_name]['budget']

        self.save_monthly_config()
        self._full_budget_paths = self._build_full_budget_paths()  # Rebuild paths after modification
        print(f"Added category/subcategory to '{scope}:{':'.join(path_parts)}'.")

    def delete_budget_category_or_subcategory(self, scope: str, path_parts: List[str]):
        """
        Deletes a budget category or subcategory from the monthly config.
        'path_parts' is a list like ['Food'] or ['Businesses', 'Photography_Business', 'Marketing'].
        """
        if scope not in self._config.get('budget_scopes', []):
            print(f"Error: Budget scope '{scope}' is not defined. Cannot delete category.")
            return

        current_level = self._config.get(scope, {}).get('budget', {})
        if not current_level:
            print(f"No budget found for scope '{scope}'. Nothing to delete.")
            return

        target_key = path_parts[-1]
        parent_level = None

        # Traverse to the parent of the item to be deleted
        for i, item_name in enumerate(path_parts):
            if i == len(path_parts) - 1:  # Reached the item itself
                break

            if item_name in current_level and isinstance(current_level[item_name], dict):
                parent_level = current_level  # Keep track of the parent
                if 'budget' in current_level[item_name] and isinstance(current_level[item_name]['budget'], dict):
                    current_level = current_level[item_name]['budget']
                else:
                    print(
                        f"Path segment '{item_name}' at '{':'.join(path_parts[:i + 1])}' is not a parent with a 'budget' sub-section. Cannot traverse.")
                    return
            else:
                print(f"Path segment '{item_name}' not found at '{':'.join(path_parts[:i])}'. Cannot delete.")
                return

        # Now, current_level is the dictionary containing the target_key
        if target_key in current_level:
            del current_level[target_key]
            self.save_monthly_config()
            self._full_budget_paths = self._build_full_budget_paths()  # Rebuild paths
            print(f"Deleted category/subcategory '{target_key}' from '{scope}:{':'.join(path_parts[:-1])}'.")
        else:
            print(
                f"Category/Subcategory '{target_key}' not found at path '{scope}:{':'.join(path_parts)}'. Nothing to delete.")

    def get_all_account_types(self) -> List[str]:
        """Returns a list of all unique account types defined in the config."""
        types = set()
        for acc_section_key in ['savings_accounts', 'debt_accounts', 'other_accounts']:
            if acc_section_key in self._config:
                for _, acc_details in self._config[acc_section_key].items():
                    if 'type' in acc_details:
                        types.add(acc_details['type'])
        return sorted(list(types))

    def get_all_categories_recursive(self) -> Dict[str, Any]:
        """
        Returns a nested dictionary of all categories, including income, suitable for UI display.
        This provides a full tree-like structure.
        """
        structured_categories = {}

        # Add Income Categories directly
        income_cats = self._config.get('income_categories', {})
        if income_cats:
            # Assuming income categories are always leaf nodes for now
            structured_categories['Income'] = {name: {} for name in income_cats.keys()}

        # Add Expense/General Budget Categories per Budget Scope
        for scope_name in self.get_all_budget_scopes():
            scope_data = self._config.get(scope_name, {}).get('budget', {})
            if scope_data:
                # Recursively build the structure for each scope's budget
                structured_categories[scope_name] = self._build_recursive_category_structure(scope_data)
            else:
                structured_categories[scope_name] = {}  # Empty scope

        return structured_categories

    def _build_recursive_category_structure(self, budget_section: Dict[str, Any]) -> Dict[str, Any]:
        """
        Helper for get_all_categories_recursive: Recursively builds the nested dictionary
        for a budget section.
        """
        current_level_structure = {}
        for item_name, item_details in budget_section.items():
            if isinstance(item_details, dict):
                # If it has a 'budget' key, it's a parent with sub-categories
                if 'budget' in item_details and isinstance(item_details['budget'], dict) and item_details['budget']:
                    current_level_structure[item_name] = self._build_recursive_category_structure(
                        item_details['budget'])
                # If it's a leaf node (has amount/description, but no further 'budget' key, or an empty 'budget' key)
                elif 'amount' in item_details or 'description' in item_details or not item_details.get('budget'):
                    current_level_structure[item_name] = {}  # Represent as a selectable leaf
                # If it's just a dict without amount/description/budget, treat as a selectable leaf
                else:
                    current_level_structure[item_name] = {}
            # If it's not a dict (e.g., just an amount directly, though your config doesn't show this typically)
            # You might need to handle this if your config ever uses `Category: 100` directly
            elif isinstance(item_details, (int, float, str)):
                current_level_structure[item_name] = {}  # Treat as a selectable leaf

        return current_level_structure

    def get_validation_messages(self) -> list:
        """Returns the list of budget validation messages."""
        return self.validation_messages

    def get_all_accounts_with_types(self):
        """
        Retrieves all accounts from the loaded configuration, categorized by their types.
        It filters top-level keys that contain 'accounts' in their name and then
        iterates through their descendants to extract individual account details.

        Returns:
            dict: A dictionary where keys are account names (e.g., "Personal_Savings", "Cash")
                  and values are dictionaries containing the account's details
                  including an added 'account_category' field (e.g., "savings_accounts").
        """
        all_accounts = []
        for category_name, accounts_data in self._config.items():
            if "accounts" in category_name.lower():
                for account_generic_name, details in accounts_data.items():
                    # Add the category name to the account details for better context
                    all_accounts.append((details.get('name', f'UNKNOWN NAME FOR {account_generic_name}'),
                                         details.get('type', f'UNKNOWN TYPE FOR this {category_name} category')))
        return all_accounts

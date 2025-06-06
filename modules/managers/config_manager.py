import datetime
import os
import shutil

import yaml


class ConfigManager:
    """
    Manages loading, creating, and saving YAML configuration files.
    Handles two types of configs:
    1. Financial Config: Contains budgets, account balances (monthly versions).
    2. App Config: Contains keywords, LLM settings (single default version, can be updated independently).
    """

    def __init__(self, config_dir: str):
        """
        Initializes the ConfigManager.

        Args:
            config_dir (str): The base directory where configuration files are stored.
                              Monthly configs will be directly in here.
                              Default and app configs will be in a 'defaults' subfolder.
        """
        self.config_dir = config_dir
        self.defaults_subdir = "defaults"  # New subdirectory for default configs

        self.default_financial_config_name = "financial_config.yaml"
        self.default_app_config_name = "app_config.yaml"

        # Define the path to the defaults subdirectory
        self.defaults_dir_path = os.path.join(self.config_dir, self.defaults_subdir)

        # Update default config paths to point to the new defaults subdirectory
        self.default_financial_config_path = os.path.join(self.defaults_dir_path, self.default_financial_config_name)
        self.default_app_config_path = os.path.join(self.defaults_dir_path, self.default_app_config_name)

        # Initial startup checks:
        # 1. Ensure the base config directory and the defaults subdirectory exist
        self._initial_directory_setup()

        # 2. Check if default configs exist, if not, create minimal versions
        self._initial_default_config_creation()

    def _initial_directory_setup(self):
        """Ensures the base config directory and the defaults subdirectory exist."""
        print(f"Checking/creating base config directory: {self.config_dir}")
        os.makedirs(self.config_dir, exist_ok=True)
        print(f"Checking/creating defaults subdirectory: {self.defaults_dir_path}")
        os.makedirs(self.defaults_dir_path, exist_ok=True)

    def _initial_default_config_creation(self):
        """Checks for default configs and creates minimal versions if they don't exist."""
        # Check and create default financial config
        if not os.path.exists(self.default_financial_config_path):
            print(f"WARNING: Default financial config file not found at {self.default_financial_config_path}.")
            print("Attempting to create a minimal 'financial_config.yaml'. Please review and expand it.")
            self._create_minimal_default_financial_config()
        else:
            print(f"Default financial config found at {self.default_financial_config_path}.")

        # Check and create default app config
        if not os.path.exists(self.default_app_config_path):
            print(f"WARNING: Default app config file not found at {self.default_app_config_path}.")
            print("Attempting to create a minimal 'app_config.yaml'. Please review and expand it.")
            self._create_minimal_default_app_config()
        else:
            print(f"Default app config found at {self.default_app_config_path}.")

    def _create_minimal_default_financial_config(self):
        """Creates a minimal default financial config if it doesn't exist."""
        # Note: The file will now be created inside self.defaults_dir_path
        if not os.path.exists(self.default_financial_config_path):
            minimal_config = {
                'month': 'Default',
                'year': 0000,
                'currency': 'CAD',
                'categories': {
                    'Food': {'budget': 0.00},
                    'Miscellaneous': {'budget': 0.00}
                },
                'business_expenses': {
                    'General_Business': {'budget': 0.00}
                },
                'savings_accounts': {},
                'debt_accounts': {},
                'checking_accounts': {
                    'DefaultChecking': {
                        'name': 'Default Checking Account',
                        'type': 'Checking Account',
                        'initial_balance': 0.00,
                        'current_balance': 0.00
                    }
                },
                'other_accounts': {
                    'Cash': {
                        'type': 'Physical Cash',
                        'initial_balance': 0.00,
                        'current_balance': 0.00
                    }
                }
            }
            try:
                with open(self.default_financial_config_path, 'w') as f:
                    yaml.safe_dump(minimal_config, f, sort_keys=False)
                print(f"Created minimal default financial config at {self.default_financial_config_path}")
            except Exception as e:
                print(f"Failed to create minimal default financial config: {e}")

    def _create_minimal_default_app_config(self):
        """Creates a minimal default app config if it doesn't exist."""
        # Note: The file will now be created inside self.defaults_dir_path
        if not os.path.exists(self.default_app_config_path):
            minimal_config = {
                'categories': {
                    'Food': {'keywords': ["grocery", "restaurant"]},
                    'Miscellaneous': {'keywords': ["misc", "general", "other"]}
                },
                'business_expenses': {
                    'General_Business': {'keywords': ["business", "supplies"]}
                },
                'savings_accounts': {},
                'debt_accounts': {},
                'checking_accounts': {
                    'DefaultChecking': {
                        'name': 'Default Checking Account',
                        'type': 'Checking Account',
                        'keywords_deposit': [],
                        'keywords_withdrawal': []
                    }
                },
                'other_accounts': {
                    'Cash': {
                        'type': 'Physical Cash',
                        'keywords_deposit': [],
                        'keywords_withdrawal': []
                    }
                },
                'ocr_confidence_threshold': 0.8,
                'llm_model_name': 'placeholder-model',
                'llm_temperature': 0.7,
                'llm_max_tokens': 50
            }
            try:
                with open(self.default_app_config_path, 'w') as f:
                    yaml.safe_dump(minimal_config, f, sort_keys=False)
                print(f"Created minimal default app config at {self.default_app_config_path}")
            except Exception as e:
                print(f"Failed to create minimal default app config: {e}")

    def _get_monthly_financial_config_path(self, year: int, month: int) -> str:
        """
        Generates the file path for a specific monthly financial configuration.
        These remain directly in the main config_dir.
        """
        file_name = f"financial_config_{year:04d}_{month:02d}.yaml"
        return os.path.join(self.config_dir, file_name)

    def _get_temporary_financial_config_path(self, year: int, month: int) -> str:
        """
        Generates the file path for a temporary monthly financial configuration.
        These remain directly in the main config_dir.
        """
        file_name = f"financial_config_{year:04d}_{month:02d}_temp.yaml"
        return os.path.join(self.config_dir, file_name)

    def create_monthly_financial_config_if_not_exists(self, year: int, month: int):
        """
        Creates a new monthly financial configuration file from the default template if it doesn't already exist.
        """
        monthly_config_path = self._get_monthly_financial_config_path(year, month)

        if not os.path.exists(monthly_config_path):
            if not os.path.exists(self.default_financial_config_path):
                raise FileNotFoundError(
                    f"Cannot create monthly financial config. Default config file not found at "
                    f"{self.default_financial_config_path}. "
                    "Please ensure 'financial_config.yaml' exists in the 'defaults' subfolder."
                )

            try:
                shutil.copyfile(self.default_financial_config_path, monthly_config_path)

                with open(monthly_config_path, 'r') as f:
                    config_data = yaml.safe_load(f)

                config_data['month'] = datetime.date(year, month, 1).strftime('%B')
                config_data['year'] = year

                with open(monthly_config_path, 'w') as f:
                    yaml.safe_dump(config_data, f, sort_keys=False)

                print(f"Created new monthly financial config: {os.path.basename(monthly_config_path)}")
            except Exception as e:
                print(f"Error creating monthly financial config {os.path.basename(monthly_config_path)}: {e}")
                if os.path.exists(monthly_config_path):
                    os.remove(monthly_config_path)
                raise

    def load_financial_config(self, year: int, month: int) -> dict:
        """Loads the financial configuration for a specific month and year."""
        self.create_monthly_financial_config_if_not_exists(year, month)
        monthly_config_path = self._get_monthly_financial_config_path(year, month)

        try:
            with open(monthly_config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            return config_data
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Financial config file not found at {monthly_config_path}. This should not happen after create_monthly_financial_config_if_not_exists.")
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Error parsing YAML financial config file {monthly_config_path}: {e}")

    def save_financial_config(self, config_data: dict, year: int, month: int):
        """Saves the provided financial configuration data to the specific monthly YAML file."""
        monthly_config_path = self._get_monthly_financial_config_path(year, month)

        try:
            with open(monthly_config_path, 'w') as f:
                yaml.safe_dump(config_data, f, sort_keys=False)
            print(f"Financial configuration saved to {os.path.basename(monthly_config_path)}")
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Error dumping YAML financial config to {monthly_config_path}: {e}")
        except IOError as e:
            raise IOError(f"Error writing financial config file {monthly_config_path}: {e}")

    def load_default_financial_config(self) -> dict:
        """Loads the default financial configuration."""
        try:
            with open(self.default_financial_config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            return config_data
        except FileNotFoundError:
            raise FileNotFoundError(f"Default financial config file not found at {self.default_financial_config_path}.")
        except yaml.YAMLError as e:
            raise yaml.YAMLError(
                f"Error parsing YAML default financial config file {self.default_financial_config_path}: {e}")

    def save_default_financial_config(self, config_data: dict):
        """Saves the provided configuration data to the default financial YAML file."""
        try:
            with open(self.default_financial_config_path, 'w') as f:
                yaml.safe_dump(config_data, f, sort_keys=False)
            print(f"Default financial configuration saved to {os.path.basename(self.default_financial_config_path)}")
        except yaml.YAMLError as e:
            raise yaml.YAMLError(
                f"Error dumping YAML default financial config to {self.default_financial_config_path}: {e}")
        except IOError as e:
            raise IOError(f"Error writing default financial config file {self.default_financial_config_path}: {e}")

    def load_app_config(self) -> dict:
        """Loads the application configuration (keywords, LLM settings)."""
        try:
            with open(self.default_app_config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            return config_data
        except FileNotFoundError:
            raise FileNotFoundError(f"App config file not found at {self.default_app_config_path}.")
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Error parsing YAML app config file {self.default_app_config_path}: {e}")

    def save_app_config(self, config_data: dict):
        """Saves the provided configuration data to the application YAML file."""
        try:
            with open(self.default_app_config_path, 'w') as f:
                yaml.safe_dump(config_data, f, sort_keys=False)
            print(f"Application configuration saved to {os.path.basename(self.default_app_config_path)}")
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Error dumping YAML app config to {self.default_app_config_path}: {e}")
        except IOError as e:
            raise IOError(f"Error writing app config file {self.default_app_config_path}: {e}")

    def _merge_financial_configs(self, base_config: dict, overlay_config: dict) -> dict:
        """
        Merges an overlay financial config (e.g., from default) into a base financial config (e.g., current month).
        Preserves current_balance/current_owed for existing accounts.
        Adds new categories/accounts from overlay.
        Updates budget/limit values for existing categories/accounts.
        """
        merged_config = base_config.copy()

        if 'currency' in overlay_config:
            merged_config['currency'] = overlay_config['currency']

        # Helper to merge sections with a 'budget' key (categories, business_expenses)
        def merge_budget_section(section_key):
            if section_key in overlay_config and isinstance(overlay_config[section_key], dict):
                if section_key not in merged_config:
                    merged_config[section_key] = {}
                for item_name, data in overlay_config[section_key].items():
                    if item_name not in merged_config[section_key]:
                        merged_config[section_key][item_name] = {}
                    if 'budget' in data:
                        merged_config[section_key][item_name]['budget'] = data['budget']

        merge_budget_section('categories')
        merge_budget_section('business_expenses')

        # Merge Account types (Savings, Debt, Checking, Other)
        account_types = ['savings_accounts', 'debt_accounts', 'checking_accounts', 'other_accounts']
        for acc_type_key in account_types:
            if acc_type_key in overlay_config and isinstance(overlay_config[acc_type_key], dict):
                if acc_type_key not in merged_config:
                    merged_config[acc_type_key] = {}
                for acc_name, overlay_acc_data in overlay_config[acc_type_key].items():
                    if acc_name not in merged_config[acc_type_key]:
                        # New account, add it with initial_balance/initial_owed as current_balance/current_owed
                        merged_config[acc_type_key][acc_name] = overlay_acc_data.copy()
                        if 'initial_balance' in overlay_acc_data:
                            merged_config[acc_type_key][acc_name]['current_balance'] = overlay_acc_data[
                                'initial_balance']
                        if 'initial_owed' in overlay_acc_data:
                            merged_config[acc_type_key][acc_name]['current_owed'] = overlay_acc_data['initial_owed']
                    else:
                        # Existing account: update non-balance fields, PRESERVE current_balance/current_owed
                        existing_acc_data = merged_config[acc_type_key][acc_name]
                        for key, value in overlay_acc_data.items():
                            if acc_type_key == 'debt_accounts' and key == 'initial_owed':
                                existing_acc_data[key] = value
                            elif key == 'initial_balance':
                                existing_acc_data[key] = value
                            elif key not in ['current_balance', 'current_owed']:
                                existing_acc_data[key] = value
        return merged_config

    def propose_merged_financial_config(self, current_year: int, current_month: int, default_config_data: dict) -> \
            tuple[dict, str]:
        """
        Generates a temporary merged financial configuration when the default is updated.
        This allows the user to review changes before committing.
        """
        current_monthly_config = self.load_financial_config(current_year, current_month)

        proposed_merged_config = self._merge_financial_configs(current_monthly_config, default_config_data)

        proposed_merged_config['month'] = datetime.date(current_year, current_month, 1).strftime('%B')
        proposed_merged_config['year'] = current_year

        temp_path = self._get_temporary_financial_config_path(current_year, current_month)
        try:
            with open(temp_path, 'w') as f:
                yaml.safe_dump(proposed_merged_config, f, sort_keys=False)
            print(f"Proposed merged financial config saved to temporary file: {os.path.basename(temp_path)}")
            return proposed_merged_config, temp_path
        except Exception as e:
            print(f"Error saving temporary merged config: {e}")
            raise

    def confirm_and_replace_financial_config(self, year: int, month: int, temp_config_path: str):
        """
        Replaces the actual monthly financial config with a validated temporary one.
        """
        monthly_config_path = self._get_monthly_financial_config_path(year, month)
        try:
            shutil.move(temp_config_path, monthly_config_path)
            print(f"Monthly financial config updated from temporary file: {os.path.basename(monthly_config_path)}")
        except Exception as e:
            print(f"Error replacing monthly financial config with temporary file: {e}")
            raise
        finally:
            if os.path.exists(temp_config_path):
                os.remove(temp_config_path)  # Ensure temp file is removed even if move fails

    def synchronize_app_config_structure(self, default_financial_config_data: dict) -> list[dict]:
        """
        Ensures that all categories, business expenses, and accounts defined in the
        default financial config also exist in the app config with their basic structure
        and empty keyword lists.
        This method updates and saves the app_config.yaml.

        Args:
            default_financial_config_data (dict): The current default financial configuration data.

        Returns:
            list[dict]: A list of dictionaries, each describing a newly added item
            that needs keyword input from the user. Each dict includes keys like
            'section', 'name', 'display_name', 'keyword_fields'.
        """
        app_config_data = self.load_app_config()
        newly_added_items_for_keywords = []

        # --- Synchronize Categories ---
        if 'categories' in default_financial_config_data and isinstance(default_financial_config_data['categories'],
                                                                        dict):
            if 'categories' not in app_config_data:
                app_config_data['categories'] = {}
            for cat_name, fin_cat_data in default_financial_config_data['categories'].items():
                if cat_name not in app_config_data['categories']:
                    app_config_data['categories'][cat_name] = {'keywords': []}
                    newly_added_items_for_keywords.append({
                        'section': 'categories',
                        'name': cat_name,
                        'display_name': cat_name.replace('_', ' ').title(),
                        'keyword_fields': ['keywords']
                    })
                elif 'keywords' not in app_config_data['categories'][cat_name]:
                    app_config_data['categories'][cat_name]['keywords'] = []
                    print(f"WARNING: Added missing 'keywords' field for category '{cat_name}' in app_config.")

        # --- Synchronize Business Expenses ---
        if 'business_expenses' in default_financial_config_data and isinstance(
                default_financial_config_data['business_expenses'], dict):
            if 'business_expenses' not in app_config_data:
                app_config_data['business_expenses'] = {}
            for biz_name, fin_biz_data in default_financial_config_data['business_expenses'].items():
                if biz_name not in app_config_data['business_expenses']:
                    app_config_data['business_expenses'][biz_name] = {'keywords': []}
                    newly_added_items_for_keywords.append({
                        'section': 'business_expenses',
                        'name': biz_name,
                        'display_name': biz_name.replace('_', ' ').title(),
                        'keyword_fields': ['keywords']
                    })
                elif 'keywords' not in app_config_data['business_expenses'][biz_name]:
                    app_config_data['business_expenses'][biz_name]['keywords'] = []
                    print(f"WARNING: Added missing 'keywords' field for business expense '{biz_name}' in app_config.")

        # --- Synchronize Account types (Savings, Debt, Checking, Other) ---
        account_sections_map = {
            'savings_accounts': {'deposit_keywords': 'keywords_deposit', 'withdrawal_keywords': 'keywords_withdrawal'},
            'debt_accounts': {'accrual_keywords': 'keywords_accrual', 'payment_keywords': 'keywords_payment'},
            'checking_accounts': {'deposit_keywords': 'keywords_deposit', 'withdrawal_keywords': 'keywords_withdrawal'},
            'other_accounts': {'deposit_keywords': 'keywords_deposit', 'withdrawal_keywords': 'keywords_withdrawal'}
        }

        for acc_type_key, keyword_field_map in account_sections_map.items():
            if acc_type_key in default_financial_config_data and isinstance(default_financial_config_data[acc_type_key],
                                                                            dict):
                if acc_type_key not in app_config_data:
                    app_config_data[acc_type_key] = {}

                for acc_name, fin_acc_data in default_financial_config_data[acc_type_key].items():
                    if acc_name not in app_config_data[acc_type_key]:
                        # New account found in financial config, add to app config with placeholders
                        app_config_data[acc_type_key][acc_name] = {
                            'name': fin_acc_data.get('name', 'UNKNOWN_NAME'),
                            'type': fin_acc_data.get('type', 'UNKNOWN_TYPE')
                        }
                        for internal_key, app_key in keyword_field_map.items():
                            app_config_data[acc_type_key][acc_name][app_key] = []

                        newly_added_items_for_keywords.append({
                            'section': acc_type_key,
                            'name': acc_name,
                            'display_name': fin_acc_data.get('name', acc_name),
                            'keyword_fields': list(keyword_field_map.values())
                            # e.g., ['keywords_deposit', 'keywords_withdrawal']
                        })
                    else:
                        # Existing item: ensure name/type are consistent and keyword fields exist
                        existing_app_acc_data = app_config_data[acc_type_key][acc_name]
                        existing_app_acc_data['name'] = fin_acc_data.get('name', existing_app_acc_data.get('name',
                                                                                                           'UNKNOWN_NAME'))
                        existing_app_acc_data['type'] = fin_acc_data.get('type', existing_app_acc_data.get('type',
                                                                                                           'UNKNOWN_TYPE'))
                        for internal_key, app_key in keyword_field_map.items():
                            if app_key not in existing_app_acc_data:
                                existing_app_acc_data[app_key] = []
                                print(
                                    f"WARNING: Added missing keyword field '{app_key}' for account '{fin_acc_data.get('name', acc_name)}' in app_config.")

        self.save_app_config(app_config_data)
        return newly_added_items_for_keywords

    def check_config_consistency(self) -> list[str]:
        """
        Performs consistency checks between default financial config and app config.
        Checks if all categories, business expenses, and accounts in default financial config
        are present in the app config (at least in structure).

        Returns:
            list[str]: A list of human-readable strings describing any inconsistencies found.
        """
        inconsistencies = []

        try:
            default_financial_config = self.load_default_financial_config()
        except FileNotFoundError:
            inconsistencies.append(
                "❌ **Error**: Default financial config file not found. Cannot perform full consistency check.")
            return inconsistencies
        except yaml.YAMLError as e:
            inconsistencies.append(
                f"❌ **Error**: Failed to parse default financial config: {e}. Cannot perform full consistency check.")
            return inconsistencies

        try:
            app_config = self.load_app_config()
        except FileNotFoundError:
            inconsistencies.append("❌ **Error**: App config file not found. Cannot perform full consistency check.")
            return inconsistencies
        except yaml.YAMLError as e:
            inconsistencies.append(
                f"❌ **Error**: Failed to parse app config: {e}. Cannot perform full consistency check.")
            return inconsistencies

        # Define sections to check
        sections_to_check = {
            'categories': 'category',
            'business_expenses': 'business expense',
            'savings_accounts': 'savings account',
            'debt_accounts': 'debt account',
            'checking_accounts': 'checking account',
            'other_accounts': 'other account'
        }

        for fin_section_key, item_type_display in sections_to_check.items():
            financial_items = default_financial_config.get(fin_section_key, {})
            app_items = app_config.get(fin_section_key, {})

            if not isinstance(financial_items, dict):
                inconsistencies.append(
                    f"⚠️ **Warning**: '{fin_section_key}' in default financial config is not a dictionary.")
                financial_items = {}  # Treat as empty to avoid further errors

            if not isinstance(app_items, dict):
                inconsistencies.append(f"⚠️ **Warning**: '{fin_section_key}' in app config is not a dictionary.")
                app_items = {}  # Treat as empty to avoid further errors

            self._check_config_consistency_dicts(financial_items, app_items, inconsistencies, fin_section_key,
                                                 item_type_display, "default_financial_config.yaml", "app_config.yaml")
            self._check_config_consistency_dicts(app_items, financial_items, inconsistencies, fin_section_key,
                                                 item_type_display, "app_config.yaml", "default_financial_config.yaml")

        return inconsistencies

    def _check_config_consistency_dicts(self, dict1, dict2, inconsistencies, section_key, item_type_display,
                                        dict1_name, dict2_name):
        """
        Helper function to check if items in dict1 are present in dict2.
        Also checks for name/type consistency for accounts.
        """
        for item_name in dict1:
            if item_name not in dict2:
                inconsistencies.append(f"🚨 **Missing Item**: The {item_type_display} "
                                       f"**'{item_name.replace('_', ' ').title()}'** "
                                       f"from `{dict1_name}` is missing in `{dict2_name}` "
                                       f"(under `{section_key}`).")
            else:
                # Deeper check for account types to ensure 'name' and 'type' are consistent
                # This only applies if both items exist and the section is an account type
                if 'accounts' in item_type_display:
                    item_data1 = dict1[item_name]
                    item_data2 = dict2[item_name]

                    name1 = item_data1.get('name')
                    name2 = item_data2.get('name')
                    if name1 and name2 and name1 != name2:
                        inconsistencies.append(f"⚠️ **Name Mismatch**: Account '{item_name}' (under `{section_key}`) has "
                                               f"different display names: `{dict1_name}`='{name1}', "
                                               f"`{dict2_name}`='{name2}'. Consider synchronizing.")

                    type1 = item_data1.get('type')
                    type2 = item_data2.get('type')
                    if type1 and type2 and type1 != type2:
                        inconsistencies.append(f"⚠️ **Type Mismatch**: Account '{item_name}' (under `{section_key}`) has "
                                               f"different types: `{dict1_name}`='{type1}', "
                                               f"`{dict2_name}`='{type2}'. Consider synchronizing.")

    def delete_item_from_configs(self, section_key: str, item_name: str) -> tuple[bool, str]:
        """
        Deletes a specific item (category, business expense, or account) from both
        the default financial config and the app config.

        Args:
            section_key (str): The top-level key (e.g., 'categories', 'checking_accounts').
            item_name (str): The name of the item to delete.

        Returns:
            tuple[bool, str]: A tuple where the first element is True if deletion was successful,
                              False otherwise, and the second element is a message.
        """
        try:
            default_financial_config = self.load_default_financial_config()
            app_config = self.load_app_config()

            deleted_from_financial = False
            if section_key in default_financial_config and item_name in default_financial_config[section_key]:
                del default_financial_config[section_key][item_name]
                self.save_default_financial_config(default_financial_config)
                deleted_from_financial = True
                print(f"Deleted '{item_name}' from '{section_key}' in default_financial_config.yaml")
            else:
                print(f"Item '{item_name}' not found in '{section_key}' in default_financial_config.yaml.")

            deleted_from_app = False
            if section_key in app_config and item_name in app_config[section_key]:
                del app_config[section_key][item_name]
                self.save_app_config(app_config)
                deleted_from_app = True
                print(f"Deleted '{item_name}' from '{section_key}' in app_config.yaml")
            else:
                print(f"Item '{item_name}' not found in '{section_key}' in app_config.yaml.")

            if deleted_from_financial or deleted_from_app:
                return True, f"Successfully deleted '{item_name.replace('_', ' ').title()}' from both configuration files."
            else:
                return False, f"Item '{item_name.replace('_', ' ').title()}' not found in either configuration file under '{section_key}'."

        except Exception as e:
            return False, f"An error occurred during deletion: {e}"
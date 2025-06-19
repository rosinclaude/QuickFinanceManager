# modules/managers/app_config_manager.py

import yaml
import os
from typing import Dict, Any, Optional


class AppConfigManager:
    """
    Manages loading and providing application-wide configuration from app_config.yaml.
    Prioritizes user-defined config in 'configs/', then a default in 'configs/defaults/'.
    Creates a default config if neither exists.
    """
    _instance = None  # Singleton instance
    _config: Optional[Dict[str, Any]] = None  # Holds the loaded configuration
    USER_APP_CONFIG_FILE = 'configs/app_config.yaml'
    DEFAULT_APP_CONFIG_FILE = 'configs/defaults/app_config.yaml'  # This is the template source for default creation

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AppConfigManager, cls).__new__(cls)
            cls._instance._config = cls._instance._load_config()
            print(f"AppConfigManager initialized. Configuration loaded.")
        return cls._instance

    def _load_config(self) -> Dict[str, Any]:
        """
        Loads the application configuration.
        Prioritizes USER_APP_CONFIG_FILE, then DEFAULT_APP_CONFIG_FILE.
        Creates a default if neither exists.
        Ensures the loaded config contains all expected keys.
        """
        config_to_load = {}

        # 1. Try to load user-defined config
        if os.path.exists(self.USER_APP_CONFIG_FILE):
            print(f"Attempting to load app config from user file: {self.USER_APP_CONFIG_FILE}")
            try:
                with open(self.USER_APP_CONFIG_FILE, 'r') as file:
                    config_to_load = yaml.safe_load(file)
                if config_to_load is None:  # Handle empty YAML file
                    config_to_load = {}
                    print(f"User app config file '{self.USER_APP_CONFIG_FILE}' is empty. Proceeding to defaults.")
            except yaml.YAMLError as e:
                print(
                    f"Error parsing user app config file '{self.USER_APP_CONFIG_FILE}': {e}. Attempting to load default.")
                config_to_load = {}  # Reset if parsing failed

        # 2. If user-defined not found or failed, try to load default from defaults directory
        if not config_to_load and os.path.exists(self.DEFAULT_APP_CONFIG_FILE):
            print(f"Attempting to load app config from default template: {self.DEFAULT_APP_CONFIG_FILE}")
            try:
                with open(self.DEFAULT_APP_CONFIG_FILE, 'r') as file:
                    config_to_load = yaml.safe_load(file)
                if config_to_load is None:  # Handle empty YAML file
                    config_to_load = {}
                    print(
                        f"Default app config template '{self.DEFAULT_APP_CONFIG_FILE}' is empty. Proceeding to create new default.")
            except yaml.YAMLError as e:
                print(
                    f"Error parsing default app config file '{self.DEFAULT_APP_CONFIG_FILE}': {e}. Creating a new default.")
                config_to_load = {}  # Reset if parsing failed

        # 3. If neither exists or both failed to parse, create a new default template
        if not config_to_load:
            print(f"No valid app config file found. Creating a new default template at {self.DEFAULT_APP_CONFIG_FILE}.")
            self._create_default_app_config()  # This creates the template
            # After creating, load it to ensure it's valid
            try:
                with open(self.DEFAULT_APP_CONFIG_FILE, 'r') as file:
                    config_to_load = yaml.safe_load(file)
            except Exception as e:
                print(
                    f"FATAL ERROR: Newly created default app config template failed to load: {e}. Returning empty config.")
                return {}  # Critical failure

        # Ensure the loaded config has all necessary keys from the latest structure
        self._config = config_to_load  # Temporarily assign for _ensure_default_keys
        self._ensure_default_keys()  # This will merge any missing keys from the latest default structure
        return self._config

    def _save_config(self):
        """Saves the current application settings to the USER_APP_CONFIG_FILE."""
        os.makedirs(os.path.dirname(self.USER_APP_CONFIG_FILE), exist_ok=True)
        with open(self.USER_APP_CONFIG_FILE, 'w') as file:
            yaml.safe_dump(self._config, file, default_flow_style=False, indent=2)
        print(f"App config saved to {self.USER_APP_CONFIG_FILE}.")

    def _create_default_app_config(self):
        """
        Creates a comprehensive default app configuration file in the configs/defaults/ directory.
        This serves as the template for new user configurations.
        """
        default_content = {
            'paths': {
                'default_config_dir': 'configs/defaults/',
                'monthly_config_dir': 'configs/monthly/',
                'default_finance_config_file': 'financial_config_default.yaml',
                'vendor_patterns_file': 'configs/vendor_patterns.yaml',
                'transactions_csv_file': 'data/transactions.csv',
                'payees_csv_file': 'data/payees.csv',
                'metadata_csv_file': 'data/metadata.csv',
                'models_dir': 'models/',
                'invoice_input_dir': 'data/invoices/input/',
                'invoice_processed_dir': 'data/invoices/processed/',
                'invoice_failed_dir': 'data/invoices/failed/'
            },
            'llm_config': {
                'vendor_fuzzy_match_model': 'all-MiniLM-L6-v2',
                'vendor_fuzzy_match_threshold': 0.85,
                'categorization_llm_model': 'dummy-llm',
                'categorization_llm_api_key_env_var': 'GEMINI_API_KEY',
                'categorization_llm_temperature': 0.1,
                'categorization_llm_max_tokens': 50,
                'categorization_llm_few_shot_examples_count': 5
            },
            'ml_config': {
                # Updated paths for clarity and consistency with trainers
                'categorizer_model_path': 'models/category_model/model.joblib',
                'categorizer_vectorizer_path': 'models/category_model/vectorizer.joblib',
                'categorizer_label_encoder_path': 'models/category_model/label_encoder.joblib',
                'categorizer_confidence_threshold': 0.7,
                'payee_recognizer_model_path': 'models/payee_model/model.joblib',
                'payee_recognizer_vectorizer_path': 'models/payee_model/vectorizer.joblib',
                'payee_recognizer_label_encoder_path': 'models/payee_model/label_encoder.joblib'
            },
            'ocr_config': {
                'languages': ['en', 'fr'],
                'use_gpu': False
            },
            'app_settings': {
                'display_currency_symbol_on_amount': True,
                'default_transaction_account': 'Cash'  # Added default account
            },
            'ml_ops_settings': {  # Added ML Ops settings for fine-tuning suggestions
                'newly_verified_transactions_for_finetune_count': 0,
                'ml_finetune_suggestion_threshold': 20,
                'ml_finetune_last_suggested_count': 0
            }
        }
        os.makedirs(os.path.dirname(self.DEFAULT_APP_CONFIG_FILE), exist_ok=True)
        with open(self.DEFAULT_APP_CONFIG_FILE, 'w') as file:
            yaml.dump(default_content, file, default_flow_style=False, indent=2)
        print(f"Default app config template created at {self.DEFAULT_APP_CONFIG_FILE}.")

    def _ensure_default_keys(self):
        """
        Recursively ensures all expected keys from the latest default config structure
        are present in the currently loaded configuration.
        """
        updated = False
        # Define the most current comprehensive default structure for merging
        current_default_structure = {
            'paths': {
                'default_config_dir': 'configs/defaults/',
                'monthly_config_dir': 'configs/monthly/',
                'default_finance_config_file': 'financial_config_default.yaml',
                'vendor_patterns_file': 'configs/vendor_patterns.yaml',
                'transactions_csv_file': 'data/transactions.csv',
                'payees_csv_file': 'data/payees.csv',
                'metadata_csv_file': 'data/metadata.csv',
                'models_dir': 'models/',
                'invoice_input_dir': 'data/invoices/input/',
                'invoice_processed_dir': 'data/invoices/processed/',
                'invoice_failed_dir': 'data/invoices/failed/'
            },
            'llm_config': {
                'vendor_fuzzy_match_model': 'all-MiniLM-L6-v2',
                'vendor_fuzzy_match_threshold': 0.85,
                'categorization_llm_model': 'dummy-llm',
                'categorization_llm_api_key_env_var': 'GEMINI_API_KEY',
                'categorization_llm_temperature': 0.1,
                'categorization_llm_max_tokens': 50,
                'categorization_llm_few_shot_examples_count': 5
            },
            'ml_config': {
                'categorizer_model_path': 'models/category_model/model.joblib',
                'categorizer_vectorizer_path': 'models/category_model/vectorizer.joblib',
                'categorizer_label_encoder_path': 'models/category_model/label_encoder.joblib',
                'categorizer_confidence_threshold': 0.7,
                'payee_recognizer_model_path': 'models/payee_model/model.joblib',
                'payee_recognizer_vectorizer_path': 'models/payee_model/vectorizer.joblib',
                'payee_recognizer_label_encoder_path': 'models/payee_model/label_encoder.joblib'
            },
            'ocr_config': {
                'languages': ['en', 'fr'],
                'use_gpu': False
            },
            'app_settings': {
                'display_currency_symbol_on_amount': True,
                'default_transaction_account': 'Cash'
            },
            'ml_ops_settings': {
                'newly_verified_transactions_for_finetune_count': 0,
                'ml_finetune_suggestion_threshold': 20,
                'ml_finetune_last_suggested_count': 0
            }
        }

        def merge_dicts_recursive(source_dict, target_dict):
            nonlocal updated
            for key, value in source_dict.items():
                if key not in target_dict:
                    target_dict[key] = value
                    updated = True
                elif isinstance(value, dict) and isinstance(target_dict.get(key),
                                                            dict):  # Check if target_dict[key] is also a dict
                    merge_dicts_recursive(value, target_dict[key])
                # If key exists but its value is not a dict in target when it's a dict in source,
                # we don't overwrite. This implies the user has explicitly changed a sub-dictionary to a scalar.
                # If a key exists but the type doesn't match the default, we don't automatically update to avoid data loss.

        merge_dicts_recursive(current_default_structure, self._config)

        if updated:
            print("Missing keys found in app config. Merged with defaults and saving updated config.")
            self._save_config()

    def get_config(self) -> Dict[str, Any]:
        """Returns the loaded application configuration."""
        return self._config

    def get_path(self, path_key: str) -> str:
        """Helper to get a specific path from the config."""
        return self.get_setting(f'paths.{path_key}', '')

    def get_llm_config(self) -> Dict[str, Any]:
        """Helper to get LLM configuration."""
        return self.get_setting('llm_config', {})

    def get_ml_config(self) -> Dict[str, Any]:
        """Helper to get ML configuration."""
        return self.get_setting('ml_config', {})

    def get_ocr_config(self) -> Dict[str, Any]:
        """Helper to get OCR configuration."""
        return self.get_setting('ocr_config', {})

    def get_app_settings(self) -> Dict[str, Any]:
        """Helper to get general application settings."""
        return self.get_setting('app_settings', {})

    def get_ml_ops_settings(self) -> Dict[str, Any]:
        """Helper to get ML Ops settings."""
        return self.get_setting('ml_ops_settings', {})

    def get_setting(self, key_path: str, default: Any = None) -> Any:
        """
        Retrieves a setting using a dot-separated key path (e.g., 'paths.csv_dir').
        """
        keys = key_path.split('.')
        value = self._config
        try:
            for key in keys:
                if isinstance(value, dict):
                    value = value[key]
                else:
                    return default  # Path segment is not a dictionary, cannot traverse further
            return value
        except (KeyError, TypeError):
            return default

    def set_setting(self, key_path: str, value: Any):
        """
        Sets a setting using a dot-separated key path (e.g., 'ml_ops_settings.newly_verified_transactions_for_finetune_count').
        """
        keys = key_path.split('.')
        current_level = self._config
        for i, key in enumerate(keys):
            if i == len(keys) - 1:
                current_level[key] = value
            else:
                if key not in current_level or not isinstance(current_level[key], dict):
                    current_level[key] = {}  # Create dict if it doesn't exist or is wrong type
                current_level = current_level[key]
        self._save_config()

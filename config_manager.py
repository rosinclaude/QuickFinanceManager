# config_manager.py

import os
import yaml
import datetime
import shutil


class ConfigManager:
    """
    Manages loading, creating, and saving YAML configuration files for different months.
    This includes categories, budgets, debt accounts, and savings accounts.
    """

    def __init__(self, config_dir: str, default_config_name: str = "default_config.yaml"):
        """
        Initializes the ConfigManager.

        Args:
            config_dir (str): The directory where configuration files are stored.
            default_config_name (str): The name of the default configuration template file.
        """
        self.config_dir = config_dir
        self.default_config_path = os.path.join(config_dir, default_config_name)

        # Ensure the config directory exists
        os.makedirs(self.config_dir, exist_ok=True)

        # Check if default config exists, if not, inform the user to create it
        if not os.path.exists(self.default_config_path):
            print(f"WARNING: Default config file not found at {self.default_config_path}.")
            print("Please create a 'default_config.yaml' in the 'configs/' directory based on the provided structure.")
            # Optionally, create a minimal default config here if desired, but better to let user define it.

    def _get_monthly_config_path(self, year: int, month: int) -> str:
        """
        Generates the file path for a specific monthly configuration.

        Args:
            year (int): The year of the configuration.
            month (int): The month of the configuration (1-12).

        Returns:
            str: The full path to the monthly configuration file.
        """
        file_name = f"config_{year:04d}_{month:02d}.yaml"
        return os.path.join(self.config_dir, file_name)

    def create_monthly_config_if_not_exists(self, year: int, month: int):
        """
        Creates a new monthly configuration file from the default template if it doesn't already exist.

        Args:
            year (int): The year for the new configuration.
            month (int): The month for the new configuration (1-12).
        """
        monthly_config_path = self._get_monthly_config_path(year, month)

        if not os.path.exists(monthly_config_path):
            if not os.path.exists(self.default_config_path):
                raise FileNotFoundError(
                    f"Cannot create monthly config. Default config file not found at {self.default_config_path}. "
                    "Please ensure 'default_config.yaml' exists."
                )

            try:
                # Copy the default config
                shutil.copyfile(self.default_config_path, monthly_config_path)

                # Load the newly copied config to update month and year
                with open(monthly_config_path, 'r') as f:
                    config_data = yaml.safe_load(f)

                # Update month and year fields
                config_data['month'] = datetime.date(year, month, 1).strftime('%B')  # Full month name
                config_data['year'] = year

                # Save the updated config back
                with open(monthly_config_path, 'w') as f:
                    yaml.safe_dump(config_data, f, sort_keys=False)  # sort_keys=False to preserve order

                print(f"Created new monthly config: {os.path.basename(monthly_config_path)}")
            except Exception as e:
                print(f"Error creating monthly config {os.path.basename(monthly_config_path)}: {e}")
                # Clean up partially created file if an error occurred
                if os.path.exists(monthly_config_path):
                    os.remove(monthly_config_path)
                raise  # Re-raise the exception after logging

    def load_config(self, year: int, month: int) -> dict:
        """
        Loads the configuration for a specific month and year.
        Ensures the config file exists, creating it from default if not.

        Args:
            year (int): The year of the configuration.
            month (int): The month of the configuration (1-12).

        Returns:
            dict: The loaded configuration data.

        Raises:
            FileNotFoundError: If the monthly config or default config does not exist.
            yaml.YAMLError: If there's an error parsing the YAML file.
        """
        self.create_monthly_config_if_not_exists(year, month)  # Ensure it exists before loading
        monthly_config_path = self._get_monthly_config_path(year, month)

        try:
            with open(monthly_config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            return config_data
        except FileNotFoundError:
            print(
                f"Error: Config file not found at {monthly_config_path}. This should not happen after create_monthly_config_if_not_exists.")
            raise
        except yaml.YAMLError as e:
            print(f"Error parsing YAML config file {monthly_config_path}: {e}")
            raise

    def save_config(self, config_data: dict, year: int, month: int):
        """
        Saves the provided configuration data to the specific monthly YAML file.

        Args:
            config_data (dict): The configuration data to save.
            year (int): The year of the configuration.
            month (int): The month of the configuration (1-12).

        Raises:
            yaml.YAMLError: If there's an error dumping the YAML data.
            IOError: If there's an error writing to the file.
        """
        monthly_config_path = self._get_monthly_config_path(year, month)

        try:
            with open(monthly_config_path, 'w') as f:
                yaml.safe_dump(config_data, f, sort_keys=False)  # sort_keys=False to preserve order
            print(f"Configuration saved to {os.path.basename(monthly_config_path)}")
        except yaml.YAMLError as e:
            print(f"Error dumping YAML config to {monthly_config_path}: {e}")
            raise
        except IOError as e:
            print(f"Error writing config file {monthly_config_path}: {e}")
            raise
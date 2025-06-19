# QuickFinanceManager

## Overview

QuickFinanceManager is a personal finance management application designed to help users track, categorize, and analyze their financial transactions. It leverages a modern architecture with Streamlit for the user interface, Python for backend logic, and integrates advanced features like OCR for invoice processing, hybrid ML/LLM-based categorization, and extensible configuration management. The goal is to provide an intuitive and powerful tool for managing personal finances efficiently.

## Project Structure

The project follows a modular and organized structure to separate concerns and facilitate development and maintenance.

```
QuickFinanceManager/
├── app.py
├── configs/
│   ├── defaults/
│   │   ├── app_config.yaml
│   │   └── financial_config_default.yaml
│   └── monthly/
│       └── financial_config_2025_06.yaml
├── data/
│   ├── invoices/
│   │   ├── failed/
│   │   ├── input/
│   │   └── processed/
│   ├── metadata.csv
│   ├── payees.csv
│   └── transactions.csv
├── models/
├── modules/
│   ├── automation/
│   │   ├── hybrid_categorizer.py
│   │   ├── init.py
│   │   ├── invoice_parser.py
│   │   ├── ocr_processor.py
│   │   ├── statement_matcher.py
│   │   └── vendor_parsers/
│   │       ├── base_vendor_parser.py
│   │       ├── costco_parser.py
│   │       └── init.py
│   ├── init.py
│   ├── managers/
│   │   ├── app_config_manager.py
│   │   ├── budget_manager.py
│   │   ├── csv_manager.py
│   │   ├── finance_config_manager.py
│   │   ├── init.py
│   │   ├── metadata_manager.py
│   │   ├── payee_manager.py
│   │   ├── transaction_manager.py
│   │   └── vendor_config_manager.py
│   ├── ml/
│   │   ├── data_preprocessor.py
│   │   ├── init.py
│   │   ├── llm_fine_tuner.py
│   │   └── trainers.py
│   └── ui_tabs/
│       ├── init.py
│       ├── invoice_entry_tab.py
│       ├── manual_entry_tab.py
│       └── statement_entry_tab.py
├── pages/
│   ├── 1_Add_Transaction.py
│   └── init.py
└── README.md
```


---

## Directory and File Explanations

### Root Directory (`QuickFinanceManager/`)

* **`app.py`**:
    * **Purpose**: This is the main entry point for the Streamlit application. It sets up the global page configuration, displays a welcome message, and serves as the initial page when the application is launched. Streamlit automatically discovers additional pages located in the `pages/` directory.
    * **Content**: Contains Streamlit `set_page_config` and introductory UI elements.

* **`README.md`**:
    * **Purpose**: This file provides a comprehensive overview of the project, including its purpose, structure, and detailed explanations of all directories and files.

### `configs/`

This directory stores all application configuration files in YAML format. It's designed to be flexible, allowing for default settings and monthly overrides.

* **`configs/defaults/`**:
    * **Purpose**: Contains the primary, default configuration files for the application. These settings apply globally unless explicitly overridden.
    * **`app_config.yaml`**:
        * **Purpose**: Defines application-wide settings and paths, including directories for data, models, and various ML/LLM configurations (e.g., API keys, model types, thresholds). It's the central configuration hub for the application's operational parameters.
        * **Content**: YAML key-value pairs for paths, LLM settings, ML settings, OCR settings, and general application display settings.
    * **`financial_config_default.yaml`**:
        * **Purpose**: Defines the default financial structure, including currency, accounts, and the comprehensive budget hierarchy (scopes, categories, sub-categories). It also houses the `default_category_mapping` used for initial rule-based categorization.
        * **Content**: YAML structure for `currency_symbol`, `accounts`, `budget_structure`, and `default_category_mapping`.

* **`configs/monthly/`**:
    * **Purpose**: Designed to hold monthly-specific financial configuration overrides. This allows for dynamic budgeting or account setups that change on a month-to-month basis without altering the global defaults.
    * **`financial_config_2025_06.yaml`**:
        * **Purpose**: An example monthly financial configuration file for June 2025. This file would contain overrides for budget amounts, account statuses, or other financial parameters specific to that month.
        * **Content**: YAML structure for monthly overrides (e.g., `budget_allocations`, `account_limits`).

### `data/`

This directory is used for storing persistent application data, primarily CSV files for transactions, payees, and metadata, as well as directories for managing invoice processing files.

* **`data/invoices/`**:
    * **Purpose**: Manages the lifecycle of uploaded invoice and receipt files.
    * **`failed/`**:
        * **Purpose**: Stores invoice files that failed processing (e.g., due to OCR errors, unreadable formats). This helps in debugging and manual review of problematic files.
    * **`input/`**:
        * **Purpose**: A temporary staging area for raw invoice images/PDFs immediately after they are uploaded by the user, before being processed by the OCR and parsing modules.
    * **`processed/`**:
        * **Purpose**: Stores invoice files that have been successfully processed by the OCR and invoice parsing modules. These files are moved here after their data has been extracted and (potentially) used to pre-fill transaction forms.
* **`metadata.csv`**:
    * **Purpose**: Stores additional, unstructured metadata associated with transactions. This allows for flexible storage of details that don't fit into the main `transactions.csv` schema (e.g., tax details from an invoice, loyalty numbers).
    * **Content**: CSV format, linking metadata entries to `TransactionID` and `SplitIndex`.
* **`payees.csv`**:
    * **Purpose**: Maintains a normalized list of payee (vendor) names. This helps in standardizing payee names, reducing data inconsistencies, and supporting features like vendor-specific parsing or fuzzy matching.
    * **Content**: CSV format, typically `ConformedPayeeName` and any `Aliases`.
* **`transactions.csv`**:
    * **Purpose**: The core ledger of all financial transactions. This file stores detailed records of every income, expense, and transfer, including splits and categorized budget paths.
    * **Content**: CSV format with columns like `TransactionID`, `Date`, `Payer/Payee`, `Account`, `Amount`, `BudgetPath`, `Notes`, `IsVerified`, `FilePath`, etc.

### `models/`

* **Purpose**: This directory serves as the central repository for all trained machine learning models and their associated components (e.g., TF-IDF vectorizers, label encoders). It will contain subdirectories for each specific model type (e.g., `models/logistic_regression_categorizer/`, `models/tensorflow_dnn_categorizer/`).

### `modules/`

This directory encapsulates the core Python application logic, divided into functional sub-modules.

* **`modules/__init__.py`**:
    * **Purpose**: Marks the `modules` directory as a Python package, allowing its subdirectories and files to be imported as modules.

* **`modules/automation/`**:
    * **Purpose**: Contains modules responsible for automating various tasks, such as invoice processing, data extraction, and intelligent categorization.
    * **`hybrid_categorizer.py`**:
        * **Purpose**: Implements the core logic for automatically suggesting a budget category for transactions. It uses a multi-tiered approach: attempting rule-based matching first, then falling back to a trained ML model (Logistic Regression, Decision Tree, or DNN), and finally to a Large Language Model (LLM) for more complex or novel cases. It's responsible for loading the trained ML models for inference.
        * **Content**: `HybridCategorizer` class, `LLMClient` (for LLM interaction), and `LLMFineTuner` (for LLM prompt generation).
    * **`invoice_parser.py`**:
        * **Purpose**: Extracts structured data (date, total, payee, line items, taxes) from the raw text obtained via OCR from invoices or receipts. It attempts to identify specific vendors and dispatch to custom vendor-specific parsers for higher accuracy, falling back to a generic parser if no custom one is available.
        * **Content**: `InvoiceParser` class.
    * **`ocr_processor.py`**:
        * **Purpose**: Handles the Optical Character Recognition (OCR) process. It takes an image file (e.g., JPG, PNG) and converts the text content into a machine-readable string. It uses libraries like EasyOCR.
        * **Content**: `OCRProcessor` class.
    * **`statement_matcher.py`**:
        * **Purpose**: (Placeholder) This module is intended to provide functionality for matching bank statement entries to existing transactions or suggesting new ones.
        * **Content**: Placeholder class/functions for bank statement reconciliation.
    * **`vendor_parsers/`**:
        * **Purpose**: Contains specific parsing logic for different vendors. When the `InvoiceParser` identifies a known vendor, it can delegate the parsing of the invoice text to a specialized parser in this directory for higher accuracy and consistency.
        * **`base_vendor_parser.py`**:
            * **Purpose**: Defines an abstract base class (`BaseVendorParser`) for all vendor-specific invoice parsers. It establishes the common interface (`parse()` method) that each custom parser must implement, ensuring uniformity.
        * **`costco_parser.py`**:
            * **Purpose**: An example of a concrete vendor-specific parser for Costco invoices. It would contain regular expressions or other logic tailored to extract information from Costco receipt layouts.
        * **`vendor_parsers/__init__.py`**:
            * **Purpose**: Marks `vendor_parsers` as a Python package.

* **`modules/managers/`**:
    * **Purpose**: Contains classes responsible for managing application data, configuration, and business logic. They act as an abstraction layer between the UI/automation and raw data storage.
    * **`app_config_manager.py`**:
        * **Purpose**: Manages the loading, access, and potentially modification of the `app_config.yaml`. It provides a structured way to retrieve application settings and paths, ensuring consistency across the application.
        * **Content**: `AppConfigManager` class.
    * **`budget_manager.py`**:
        * **Purpose**: Responsible for managing budget-related data and operations. This might include calculating budget utilization, tracking spending against allocated amounts, and providing budget reports.
        * **Content**: `BudgetManager` class.
    * **`csv_manager.py`**:
        * **Purpose**: Handles all interactions with CSV files (transactions, payees, metadata). It provides methods for loading, saving, appending, and querying data from these core data stores, acting as a data access layer.
        * **Content**: `CSVManager` class.
    * **`finance_config_manager.py`**:
        * **Purpose**: Manages the loading, merging, and validation of financial configuration files (`financial_config_default.yaml` and monthly overrides). It provides methods to access accounts, budget structures, currencies, and categorization mappings.
        * **Content**: `FinanceConfigManager` class.
    * **`modules/managers/__init__.py`**:
        * **Purpose**: Marks `managers` as a Python package.
    * **`metadata_manager.py`**:
        * **Purpose**: Manages the storage and retrieval of additional, often unstructured, transaction-specific metadata. It interacts with `metadata.csv`.
        * **Content**: `MetadataManager` class.
    * **`payee_manager.py`**:
        * **Purpose**: Manages payee (vendor) data, including adding new payees and retrieving existing ones. It ensures that payee names are consistent and facilitates the use of conformed payee names throughout the application.
        * **Content**: `PayeeManager` class.
    * **`transaction_manager.py`**:
        * **Purpose**: This is a central orchestrator for transaction-related operations. It handles adding new transactions (manual or from invoices), integrates with `OCRProcessor`, `InvoiceParser`, `HybridCategorizer`, `PayeeManager`, and `MetadataManager` to process and save complete transaction records.
        * **Content**: `TransactionManager` class.
    * **`vendor_config_manager.py`**:
        * **Purpose**: Manages the configuration of vendors, including their conform names, patterns for identification, and associations with custom parsers. It supports fuzzy matching for vendor identification.
        * **Content**: `VendorConfigManager` class.

* **`modules/ml/`**:
    * **Purpose**: Contains all components related to machine learning models used in the application, specifically for transaction categorization.
    * **`data_preprocessor.py`**:
        * **Purpose**: Centralizes data preparation logic for ML models. It handles filtering trainable transactions, creating combined text features, performing TF-IDF vectorization, and label encoding for BudgetPaths. It also manages saving/loading the fitted vectorizer and label encoder.
        * **Content**: `DataPreprocessor` class.
    * **`modules/ml/__init__.py`**:
        * **Purpose**: Marks `ml` as a Python package.
    * **`llm_fine_tuner.py`**:
        * **Purpose**: A conceptual module responsible for generating few-shot examples for LLM prompts. In a more advanced setup, it would handle actual fine-tuning of LLMs or generating prompts based on user-verified data to improve LLM categorization accuracy.
        * **Content**: `LLMFineTuner` class.
    * **`trainers.py`**:
        * **Purpose**: Defines various trainer classes (`BaseTrainer`, `LogisticRegressionCategorizerTrainer`, `DecisionTreeCategorizerTrainer`, `DNNCategorizerTrainerTF`, `DNNCategorizerTrainerPyTorch`). Each trainer is specialized for a particular ML model type, handling its architecture definition, training process (including data splitting and evaluation), and saving the trained model artifact. These classes are designed to be used independently (e.g., in a separate training script or Jupyter notebook).
        * **Content**: `BaseTrainer` and its concrete subclasses for different categorization models.

* **`modules/ui_tabs/`**:
    * **Purpose**: Contains reusable Streamlit UI components designed to be integrated as tabs or sections within larger Streamlit pages. This promotes UI modularity and reusability.
    * **`modules/ui_tabs/__init__.py`**:
        * **Purpose**: Marks `ui_tabs` as a Python package.
    * **`invoice_entry_tab.py`**:
        * **Purpose**: (Placeholder) This module is intended to provide UI elements specific to invoice entry, possibly for displaying extracted invoice data in a structured way before it's passed to the main transaction entry form.
        * **Content**: Placeholder functions for invoice-specific UI.
    * **`manual_entry_tab.py`**:
        * **Purpose**: Provides a comprehensive Streamlit UI for manually entering new transactions, including handling multi-split transactions and dynamic budget category selection. It is designed to be reusable and can be pre-filled with data (e.g., from invoice processing).
        * **Content**: `display_manual_entry_tab` function and its helper functions.
    * **`statement_entry_tab.py`**:
        * **Purpose**: (Placeholder) This module is intended to provide UI elements for importing and managing bank statements.
        * **Content**: Placeholder functions for bank statement UI.

### `pages/`

This directory is where Streamlit looks for additional pages to create a multi-page application. Each Python file in this directory (excluding `__init__.py`) will become a separate page in the Streamlit sidebar navigation.

* **`1_Add_Transaction.py`**:
    * **Purpose**: This is a Streamlit multi-page application page. It orchestrates the display of different transaction input methods (Manual Entry, From Invoice/Receipt, From Bank Statement) using tabs, and integrates with the various manager and automation modules to handle transaction data. It also initializes all necessary managers using Streamlit's resource caching.
    * **Content**: Streamlit page layout, manager initialization, and calls to `ui_tabs` functions.
* **`pages/__init__.py`**:
    * **Purpose**: Marks `pages` as a Python package.

---

This `README.md` provides a detailed map of your `QuickFinanceManager` project, which should be helpful for onboarding new developers, understanding the project's architecture, and maintaining the codebase.

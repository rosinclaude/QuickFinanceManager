# modules/automation/hybrid_categorizer.py

import os
import re
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple, Union

# Conditional imports for ML frameworks
_TF_AVAILABLE = False
try:
    import tensorflow as tf
    from tensorflow.keras.models import load_model  # Specific import for Keras model loading

    _TF_AVAILABLE = True
    print("TensorFlow for HybridCategorizer imported successfully.")
except ImportError:
    print("WARNING: TensorFlow not installed. TensorFlow DNN models cannot be loaded by HybridCategorizer.")
except Exception as e:
    print(f"WARNING: Error importing TensorFlow for HybridCategorizer: {e}. TF DNN models might not be available.")

_TORCH_AVAILABLE = False
try:
    import torch
    import torch.jit  # Required for loading scripted PyTorch models
    import torch.nn as nn  # Needed for type hinting if loading base nn.Module

    _TORCH_AVAILABLE = True
    print("PyTorch for HybridCategorizer imported successfully.")
except ImportError:
    print("WARNING: PyTorch not installed. PyTorch DNN models cannot be loaded by HybridCategorizer.")
except Exception as e:
    print(f"WARNING: Error importing PyTorch for HybridCategorizer: {e}. PyTorch DNN models might not be available.")

import joblib  # For loading scikit-learn models and components

# Import the DataPreprocessor
from modules.ml.data_preprocessor import DataPreprocessor
from modules.ml.llm_fine_tuner import LLMFineTuner, LLMClient
# Import LLMClient and LLMFineTuner as they are still part of the hybrid approach
from modules.managers.finance_config_manager import FinanceConfigManager


class HybridCategorizer:
    """
    Categorizes transactions using a hybrid approach:
    1. Rule-based matching (from config)
    2. Trained Machine Learning model
    3. Large Language Model (LLM) for fuzzy/novel cases

    This class is now responsible for loading the ML models directly,
    rather than relying on trainer classes for loading.
    """

    def __init__(self, config_manager: FinanceConfigManager, app_config: Dict[str, Any]):
        """
        Initializes the HybridCategorizer.

        Args:
            config_manager (FinanceConfigManager): An instance of FinanceConfigManager.
            app_config (Dict[str, Any]): The loaded application configuration.
        """
        self.config_manager = config_manager
        self.app_config = app_config
        self.default_category_mapping = self.config_manager.get_default_category_mapping()

        # Combine all valid budget paths (expense) and income paths for validation and LLM context
        self.all_valid_paths = self.config_manager.get_full_budget_paths() + \
                               [f"Income:{cat}" for cat in self.config_manager.get_income_categories()]

        # ML Model Configuration from app_config
        # `model_artifact_base_dir` is the root where ML components (vectorizer, encoder)
        # and model-specific subdirectories are stored.
        self.model_artifact_base_dir = self.app_config['ml_config']['model_artifact_base_dir']
        # `selected_model_type` determines which specific ML model to load.
        self.selected_ml_model_type = self.app_config['ml_config']['selected_model_type']
        self.ML_MODEL_CONFIDENCE_THRESHOLD = self.app_config['ml_config']['categorizer_confidence_threshold']

        # LLM Configuration from app_config
        self.LLM_MODEL_NAME = self.app_config['llm_config']['categorization_llm_model']
        self.LLM_API_KEY_ENV_VAR = self.app_config['llm_config']['categorization_llm_api_key_env_var']
        self.LLM_TEMPERATURE = self.app_config['llm_config']['categorization_llm_temperature']
        self.LLM_MAX_TOKENS = self.app_config['llm_config']['categorization_llm_max_tokens']
        self.LLM_FEW_SHOT_EXAMPLES_COUNT = self.app_config['llm_config']['categorization_llm_few_shot_examples_count']

        # Initialize DataPreprocessor, which loads vectorizer and label encoder
        self.data_preprocessor = DataPreprocessor(model_dir=self.model_artifact_base_dir)
        self.ml_vectorizer = self.data_preprocessor.vectorizer
        self.ml_label_encoder = self.data_preprocessor.label_encoder

        # Load the selected ML model
        self.ml_model = self._load_selected_ml_model()

        # Initialize LLM client with parameters from app_config
        self.llm_client = LLMClient(
            model_name=self.LLM_MODEL_NAME,
            api_key_env_var=self.LLM_API_KEY_ENV_VAR,
            temperature=self.LLM_TEMPERATURE,
            max_tokens=self.LLM_MAX_TOKENS
        )
        # LLMFineTuner needs the LLMClient instance
        self.llm_fine_tuner = LLMFineTuner(llm_inference_client=self.llm_client)

        print("HybridCategorizer initialized.")
        if not self.ml_model:
            print(
                f"Warning: ML Categorizer model '{self.selected_ml_model_type}' not loaded. ML-based categorization will be skipped.")
        if not self.ml_vectorizer:
            print("Warning: ML TF-IDF Vectorizer not loaded. ML-based categorization will be skipped.")
        if not self.ml_label_encoder:
            print("Warning: ML Label Encoder not loaded. ML-based categorization will be skipped.")

    def _load_selected_ml_model(self) -> Optional[Any]:
        """
        Loads the specific ML model selected in app_config based on its type.
        This method encapsulates the loading logic for different ML frameworks.
        """
        model = None
        model_type_dir = os.path.join(self.model_artifact_base_dir, self.selected_ml_model_type)

        # Determine the file path and loading method based on the selected model type
        if self.selected_ml_model_type == "logistic_regression_categorizer" or \
                self.selected_ml_model_type == "decision_tree_categorizer":
            model_path = os.path.join(model_type_dir, 'model.joblib')
            if os.path.exists(model_path):
                try:
                    model = joblib.load(model_path)
                    print(f"ML Model ({self.selected_ml_model_type}) loaded successfully from {model_path}")
                except Exception as e:
                    print(f"Error loading scikit-learn model from {model_path}: {e}")
            else:
                print(f"No scikit-learn model found at {model_path}.")

        elif self.selected_ml_model_type == "tensorflow_dnn_categorizer":
            if _TF_AVAILABLE:
                model_path = os.path.join(model_type_dir, 'model.keras')
                if os.path.exists(model_path):
                    try:
                        model = load_model(model_path)  # TensorFlow's load_model handles architecture and weights
                        print(f"ML Model ({self.selected_ml_model_type}) loaded successfully from {model_path}")
                    except Exception as e:
                        print(f"Error loading TensorFlow model from {model_path}: {e}")
                else:
                    print(f"No TensorFlow model found at {model_path}.")
            else:
                print(f"TensorFlow is not available. Cannot load {self.selected_ml_model_type}.")

        elif self.selected_ml_model_type == "pytorch_dnn_categorizer":
            if _TORCH_AVAILABLE:
                model_path = os.path.join(model_type_dir, 'model.pt')  # .pt for traced models
                if os.path.exists(model_path):
                    try:
                        model = torch.jit.load(model_path)  # PyTorch JIT load for traced models
                        model.eval()  # Set to evaluation mode
                        print(f"ML Model ({self.selected_ml_model_type}) loaded successfully from {model_path}")
                    except Exception as e:
                        print(f"Error loading PyTorch model from {model_path}: {e}")
                else:
                    print(f"No PyTorch model found at {model_path}.")
            else:
                print(f"PyTorch is not available. Cannot load {self.selected_ml_model_type}.")

        else:
            print(
                f"Unknown or unsupported ML model type specified: {self.selected_ml_model_type}. No ML model will be loaded.")

        return model

    def suggest_category(self,
                         description: str,
                         payee: str,
                         account: str,
                         current_notes: str = "",
                         transaction_type: str = "Expense"  # Added for better LLM context
                         ) -> Dict[
        str, Any]:  # Removed current_budget_path from args as it's not primarily used for suggestion logic flow here
        """
        Suggests a budget category using a hybrid approach (Rules -> ML -> LLM).

        Args:
            description (str): The primary description of the transaction or split.
            payee (str): The detected payee/vendor.
            account (str): The account used for the transaction.
            current_notes (str): Any additional notes from OCR or user.
            transaction_type (str): The type of transaction (e.g., "Expense", "Income").

        Returns:
            Dict[str, Any]: Contains 'BudgetScope', 'Category', 'SubCategory', 'BudgetPath', 'Confidence', 'Source'.
        """
        suggestion = {
            'BudgetScope': 'Uncategorized',
            'Category': 'Unassigned',
            'SubCategory': '',
            'BudgetPath': 'Uncategorized:Unassigned',
            'Confidence': 0.0,
            'Source': 'None'
        }

        combined_text = f"Description: {description}. Payee: {payee}. Account: {account}. Notes: {current_notes}".strip()

        # --- 1. Rule-Based Categorization ---
        # Rule-based now checks against ALL_VALID_PATHS internally based on default_category_mapping
        rule_based_path = self._apply_rule_based_categorization(description, payee, account, transaction_type)
        if rule_based_path:
            # Check validity against the combined list of all valid paths (expense & income)
            if rule_based_path in self.all_valid_paths:
                parsed = self._parse_budget_path(rule_based_path)
                suggestion.update(parsed)
                suggestion['Confidence'] = 0.95
                suggestion['Source'] = 'Rule-Based'
                print(f"Rule-based category: {rule_based_path}")
                return suggestion
            else:
                print(f"Rule-based system suggested an invalid path: {rule_based_path}. Falling back.")

        # --- 2. Machine Learning Model Categorization ---
        if self.ml_model and self.ml_vectorizer and self.ml_label_encoder:
            ml_prediction, ml_confidence = self._apply_ml_categorization(combined_text)
            if ml_prediction and ml_confidence >= self.ML_MODEL_CONFIDENCE_THRESHOLD:
                # Validate ML prediction against the combined list of all valid paths
                if ml_prediction in self.all_valid_paths:
                    parsed = self._parse_budget_path(ml_prediction)
                    suggestion.update(parsed)
                    suggestion['Confidence'] = ml_confidence
                    suggestion['Source'] = 'ML_Model'
                    print(f"ML Model category: {ml_prediction} (Confidence: {ml_confidence:.2f})")
                    return suggestion
                else:
                    print(f"ML model predicted invalid path: {ml_prediction}. Falling back to LLM.")
            elif ml_prediction:  # Prediction made but below confidence threshold
                print(
                    f"ML model prediction '{ml_prediction}' below confidence threshold ({ml_confidence:.2f} < {self.ML_MODEL_CONFIDENCE_THRESHOLD}). Falling back to LLM.")
            else:  # No prediction made by ML model
                print("ML model could not make a prediction. Falling back to LLM.")

        # --- 3. LLM Categorization ---
        print("Attempting LLM-based categorization...")
        llm_suggestion_path = self._apply_llm_categorization(
            description=description,
            payee=payee,
            account=account,
            notes=current_notes,
            transaction_type=transaction_type,
            valid_paths=self.all_valid_paths  # Pass all valid paths (expense + income)
        )
        # Validate LLM suggestion against the combined list of all valid paths
        if llm_suggestion_path and llm_suggestion_path in self.all_valid_paths:
            parsed = self._parse_budget_path(llm_suggestion_path)
            suggestion.update(parsed)
            suggestion['Confidence'] = 0.8  # LLM confidence (arbitrary, can be adjusted based on testing)
            suggestion['Source'] = 'LLM'
            print(f"LLM category: {llm_suggestion_path}")
            return suggestion
        else:
            if llm_suggestion_path:
                print(f"LLM suggested an invalid or unrecognized path: '{llm_suggestion_path}'. Keeping Uncategorized.")
            else:
                print("LLM could not provide a confident or valid category.")

        return suggestion

    def _apply_rule_based_categorization(self, description: str, payee: str, account: str, transaction_type: str) -> \
            Optional[str]:
        """
        Applies rule-based mapping from config to categorize a transaction.
        Checks if the matched path is valid within the context of the transaction type.
        """
        text_to_match = (description + " " + payee + " " + account).upper()

        for budget_path, keywords in self.default_category_mapping.items():
            if any(re.search(r'\b' + re.escape(kw.upper()) + r'\b', text_to_match) for kw in keywords):
                # Basic check: if it's an Income transaction, only match Income paths.
                # If it's an Expense transaction, match other paths.
                if transaction_type == "Income" and budget_path.startswith("Income:"):
                    return budget_path
                elif transaction_type == "Expense" and not budget_path.startswith("Income:"):
                    return budget_path
                # Add logic for other transaction types like 'Transfer' if they need categorization

        return None

    def _apply_ml_categorization(self, combined_text: str) -> Tuple[Optional[str], float]:
        """
        Applies the trained ML model to categorize the transaction.
        Returns (predicted_path, confidence).
        """
        if not self.ml_model or not self.ml_vectorizer or not self.ml_label_encoder:
            return None, 0.0

        try:
            # Use the data_preprocessor to transform the text consistently
            text_vectorized = self.data_preprocessor.prepare_data_for_prediction(
                description=combined_text, payee="", account=""  # Pass combined text as description for TFIDF
            )

            probabilities = None
            if self.selected_ml_model_type.startswith("logistic_regression") or \
                    self.selected_ml_model_type.startswith("decision_tree"):
                # Scikit-learn models usually have predict_proba
                probabilities = self.ml_model.predict_proba(text_vectorized)[0]
            elif self.selected_ml_model_type == "tensorflow_dnn_categorizer" and _TF_AVAILABLE:
                # Keras models predict probabilities directly
                probabilities = self.ml_model.predict(text_vectorized.toarray())[0]
            elif self.selected_ml_model_type == "pytorch_dnn_categorizer" and _TORCH_AVAILABLE:
                # PyTorch models output logits, need softmax to get probabilities
                # Convert sparse matrix to dense tensor for PyTorch model
                input_tensor = torch.tensor(text_vectorized.toarray(), dtype=torch.float32)
                with torch.no_grad():
                    logits = self.ml_model(input_tensor)
                    probabilities = torch.softmax(logits, dim=1).cpu().numpy()[0]
            else:
                print(
                    f"ML model type {self.selected_ml_model_type} not supported for prediction probability calculation.")
                return None, 0.0

            if probabilities is None:
                return None, 0.0

            predicted_class_idx = probabilities.argmax()
            predicted_confidence = probabilities[predicted_class_idx]

            # Use the data_preprocessor to decode the prediction consistently
            predicted_budget_path = self.data_preprocessor.decode_predictions([predicted_class_idx])[0]

            return predicted_budget_path, predicted_confidence

        except Exception as e:
            print(f"Error during ML categorization: {e}")
            return None, 0.0

    def _apply_llm_categorization(self, description: str, payee: str, account: str, notes: str, transaction_type: str,
                                  valid_paths: List[str]) -> Optional[str]:
        """
        Uses the LLM to categorize the transaction based on context.
        Includes few-shot examples for better performance.
        """
        if not self.llm_client or (not self.llm_client.api_key and self.llm_client.model_name != 'dummy-llm'):
            print("LLM is not configured or API key is missing. Skipping LLM categorization.")
            return None

        # Fetch few-shot examples from the LLM fine-tuner (conceptual or real data)
        # In a full system, you would load your `transactions_df` from `CSVManager`
        # and pass it to LLMFineTuner to get real examples.
        # For this demonstration, we'll use a dummy data frame.
        dummy_transactions_df_for_examples = pd.DataFrame([
            {'Description': 'Coffee', 'Payer/Payee': 'Tim Hortons', 'Account': 'Chequing',
             'BudgetPath': 'Family:Entertainment'},
            {'Description': 'Internet bill', 'Payer/Payee': 'Bell Canada', 'Account': 'Credit Card',
             'BudgetPath': 'Family:Utilities'},
            {'Description': 'Weekly groceries', 'Payer/Payee': 'Maxi', 'Account': 'Chequing',
             'BudgetPath': 'Family:Food'},
            {'Description': 'Salary from freelance work', 'Payer/Payee': 'Client B', 'Account': 'Chequing',
             'BudgetPath': 'Income:Freelance_Work'},
            {'Description': 'Camera lens', 'Payer/Payee': 'B&H Photo', 'Account': 'Credit Card',
             'BudgetPath': 'Personal:Businesses:Photography_Business:Equipment'},
            {'Description': 'Fabric for new project', 'Payer/Payee': 'Fabricville', 'Account': 'Credit Card',
             'BudgetPath': 'Personal:Businesses:Sewing_Business:Supplies'}
        ])

        few_shot_examples = self.llm_fine_tuner.generate_few_shot_prompt_examples(
            dummy_transactions_df_for_examples,
            num_examples=self.LLM_FEW_SHOT_EXAMPLES_COUNT
        )

        prompt_parts = []
        prompt_parts.append(
            "You are an expert financial categorizer. Your task is to assign the most appropriate budget path "
            "to a given transaction. The budget path format is 'Scope:Category:SubCategory' or 'Scope:Category' "
            "for expenses, and 'Income:Category' for income. DO NOT output anything other than the exact budget path.\n"
            "Here are the valid budget paths:\n"
            + "\n".join(f"- {path}" for path in sorted(valid_paths)) + "\n\n"  # Sort for consistency
                                                                       "Here are a few examples:\n"
        )

        for example in few_shot_examples:
            prompt_parts.append(f"Transaction: {example['input']}\nCategory: {example['output']}\n")

        prompt_parts.append("Categorize the following transaction:\n")
        prompt_parts.append(
            f"Transaction Type: {transaction_type}\nDescription: {description}\nPayee: {payee}\nAccount: {account}\nNotes: {notes}")
        prompt_parts.append("Category:")

        full_prompt = "\n".join(prompt_parts)

        try:
            llm_response = self.llm_client.generate(
                full_prompt)  # Use self.llm_client.generate without max_tokens/temperature args
            cleaned_response = llm_response.strip().split('\n')[0]

            if cleaned_response in valid_paths:  # Direct check against pre-built list
                return cleaned_response
            else:
                print(f"LLM returned an invalid or unparseable category: '{cleaned_response}'")
                return None
        except Exception as e:
            print(f"Failed to get LLM categorization: {e}")
            return None

    def _parse_budget_path(self, budget_path: str) -> Dict[str, str]:
        """
        Parses a full budget path string into its components.
        """
        parts = budget_path.split(':')
        scope = parts[0] if len(parts) > 0 else ''
        category = parts[1] if len(parts) > 1 else ''
        sub_category = parts[2] if len(parts) > 2 else ''

        return {
            'BudgetScope': scope,
            'Category': category,
            'SubCategory': sub_category,
            'BudgetPath': budget_path
        }
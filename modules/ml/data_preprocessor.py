# modules/ml/data_preprocessor.py
"""
Objective:
This script defines the DataPreprocessor class, which is a crucial component in the
machine learning pipeline for transaction categorization. Its primary goal is to
centralize and standardize the data preparation steps required for various
machine learning models (Logistic Regression, Decision Trees, TensorFlow DNNs,
PyTorch DNNs, and potentially LLMs). By decoupling data preprocessing from
model training and inference, it ensures consistency, reusability, and maintainability
of the data transformation logic.

Key responsibilities include:
- Filtering raw transaction data to select relevant, verified training examples.
- Creating a combined text feature from multiple transaction fields.
- Performing TF-IDF (Term Frequency-Inverse Document Frequency) vectorization
  to convert text into numerical features suitable for ML models.
- Encoding categorical target labels (BudgetPaths) into numerical representations.
- Providing methods to save and load the fitted TF-IDF vectorizer and label encoder,
  ensuring that the same transformations are applied during both training and prediction.
- Offering utilities to convert data to formats specific to different ML frameworks
  (e.g., dense NumPy arrays for Keras/PyTorch, PyTorch tensors).
"""

import pandas as pd
import joblib
import os
import torch
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import LabelEncoder
from typing import Dict, Any, List, Optional, Tuple, Union

# Attempt to import TensorFlow if available, mainly for type hinting in environments where it's installed.
# It's not strictly required for the DataPreprocessor's core functionality but helps with clarity.
try:
    import tensorflow as tf
except ImportError:
    pass  # No worries if TF isn't available, this block is just for import success/failure reporting elsewhere.

#TODO: Initialise the data preprocessor to train models. See transaction_manager to get same exact init variable
# declared in app_config file.
class DataPreprocessor:
    """
    The DataPreprocessor class is responsible for all data transformation steps
    required before feeding data to machine learning models for transaction categorization.
    This includes text vectorization, label encoding, and data format conversions.
    It manages the persistence of its fitted components (Vectorizer and LabelEncoder)
    to ensure consistent preprocessing across training and prediction phases.
    """

    def __init__(self, model_dir: str):
        """
        Initializes the DataPreprocessor.

        Args:
            model_dir (str): The base directory path where shared ML components
                             (like the TF-IDF vectorizer and label encoder)
                             should be saved and loaded. This typically points to
                             a common 'models/' directory to centralize these assets.
        """
        self.model_dir = model_dir
        # Ensure the directory for storing preprocessor components exists
        os.makedirs(self.model_dir, exist_ok=True)

        # Define file paths for the vectorizer and label encoder within the specified model_dir
        self.vectorizer_path = os.path.join(self.model_dir, 'tfidf_vectorizer.joblib')
        self.label_encoder_path = os.path.join(self.model_dir, 'label_encoder.joblib')

        # Initialize attributes for the vectorizer and label encoder.
        # They will be loaded if existing, or set during data preparation for training.
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.label_encoder: Optional[LabelEncoder] = None

        # Attempt to load previously saved components upon initialization
        self._load_components()
        print(f"DataPreprocessor initialized. Components will be stored/loaded from: {self.model_dir}")

    def _load_components(self):
        """
        Internal method to load the TF-IDF Vectorizer and Label Encoder from disk.
        This is called during initialization to ensure the preprocessor is ready
        to transform data for prediction immediately if components exist.
        """
        self.vectorizer = self._load_joblib_component(self.vectorizer_path, "TF-IDF Vectorizer")
        self.label_encoder = self._load_joblib_component(self.label_encoder_path, "Label Encoder")

    def _load_joblib_component(self, path: str, name: str) -> Optional[Any]:
        """
        Generic helper method to load any component saved using joblib.
        Encapsulates error handling for file loading.

        Args:
            path (str): The full file path to the joblib-saved component.
            name (str): A descriptive name of the component for logging purposes.

        Returns:
            Optional[Any]: The loaded component object, or None if loading fails.
        """
        if not os.path.exists(path):
            print(f"No {name} found to load at {path}.")
            return None
        try:
            component = joblib.load(path)
            print(f"{name} loaded successfully from {path}.")
            return component
        except Exception as e:
            print(f"Error loading {name} from {path}: {e}")
            return None

    def save_components(self):
        """
        Saves the current state of the TF-IDF Vectorizer and Label Encoder to disk
        using joblib. This method should be called after `prepare_data_for_training`
        to persist the transformations learned from the training data.
        """
        if self.vectorizer:
            joblib.dump(self.vectorizer, self.vectorizer_path)
            print(f"TF-IDF Vectorizer saved to {self.vectorizer_path}")
        if self.label_encoder:
            joblib.dump(self.label_encoder, self.label_encoder_path)
            print(f"Label Encoder saved to {self.label_encoder_path}")

    def select_trainable_transactions(self, transactions_df: pd.DataFrame) -> pd.DataFrame:
        """
        Filters the raw transaction DataFrame to select records suitable for training
        a supervised machine learning model. This includes transactions that:
        1. Have been `IsVerified` by the user (or are assumed verified if column missing).
        2. Have a non-null and non-empty `BudgetPath` (the target variable).

        Args:
            transactions_df (pd.DataFrame): The raw DataFrame containing historical transactions.

        Returns:
            pd.DataFrame: A new DataFrame containing only the filtered, trainable transactions.
                          A `.copy()` is made to prevent `SettingWithCopyWarning` in Pandas.
        """
        # Ensure 'IsVerified' column exists. If not, assume all are verified for older datasets.
        if 'IsVerified' not in transactions_df.columns:
            transactions_df['IsVerified'] = True

        # Filter for verified transactions with a valid BudgetPath
        filtered_df = transactions_df[
            (transactions_df["IsVerified"] == True) &
            (transactions_df['BudgetPath'].notna()) &
            (transactions_df['BudgetPath'] != '')
            ].copy()

        # Reset index to ensure a clean DataFrame for further processing
        return filtered_df.reset_index(drop=True)

    def prepare_data_for_training(self, transactions_df: pd.DataFrame) -> Tuple[Any, np.ndarray]:
        """
        Prepares a batch of transaction data specifically for model training.
        This involves:
        1. Filtering for trainable transactions.
        2. Combining relevant text fields ('Description', 'Payer/Payee', 'Account').
        3. Fitting and transforming the `LabelEncoder` on the `BudgetPath` target.
        4. Fitting and transforming the `TfidfVectorizer` on the combined text.
        The fitted `vectorizer` and `label_encoder` are then saved.

        Args:
            transactions_df (pd.DataFrame): DataFrame containing historical transactions.
                                             Expected columns: 'Description', 'Payer/Payee',
                                             'Account', and 'BudgetPath'.

        Returns:
            Tuple[Any, np.ndarray]:
                - X_vectorized: The TF-IDF vectorized features (a sparse matrix).
                - y_encoded: The label-encoded target variable (a NumPy array).

        Raises:
            ValueError: If no valid historical data is found after filtering,
                        or if there are fewer than 2 unique BudgetPaths (required for classification).
        """
        # Step 1: Select only the relevant and verified transactions for training
        df = self.select_trainable_transactions(transactions_df)
        if df.empty:
            raise ValueError("No valid historical data with BudgetPaths to prepare for training.")

        # Step 2: Create a combined text feature from relevant columns.
        # This aggregates information that might be useful for categorization.
        df['combined_text'] = df['Description'].fillna('') + " " + \
                              df['Payer/Payee'].fillna('') + " " + \
                              df['Account'].fillna('')
        df['combined_text'] = df['combined_text'].str.lower()  # Convert to lowercase for consistency

        X_text = df['combined_text']  # Features (text)
        y_labels = df['BudgetPath']  # Target labels (BudgetPath strings)

        # Step 3: Check for sufficient unique classes for classification
        if y_labels.nunique() < 2:
            raise ValueError(f"Only {y_labels.nunique()} unique BudgetPath found. Need at least 2 for classification.")

        # Step 4: Fit and transform the LabelEncoder for the target labels.
        # This converts string labels (e.g., 'Groceries') into numerical IDs.
        self.label_encoder = LabelEncoder()
        y_encoded = self.label_encoder.fit_transform(y_labels)

        # Step 5: Fit and transform the TF-IDF Vectorizer for the text features.
        # This converts the combined text into a sparse numerical representation,
        # where each number represents the importance of a word in a document relative to the corpus.
        self.vectorizer = TfidfVectorizer(stop_words='english',
                                          max_features=5000)  # Limit features to avoid curse of dimensionality
        X_vectorized = self.vectorizer.fit_transform(X_text)

        print(
            f"Data prepared for training. X_vectorized shape: {X_vectorized.shape}, y_encoded shape: {y_encoded.shape}")

        # Step 6: Save the fitted vectorizer and label encoder.
        # This is critical to ensure that during prediction, new data is transformed
        # using the exact same vocabulary and encoding as during training.
        self.save_components()
        return X_vectorized, y_encoded

    def prepare_data_for_prediction(self, description: str, payee: str, account: str) -> Any:
        """
        Prepares a single instance of transaction data for model prediction.
        This method uses the *already loaded or fitted* TF-IDF vectorizer and
        does not fit it again, ensuring consistent transformation.

        Args:
            description (str): The transaction description.
            payee (str): The transaction payer/payee.
            account (str): The transaction account.

        Returns:
            Any: The TF-IDF vectorized features for the single instance (a sparse matrix).
                 The exact type depends on the vectorizer's output (e.g., scipy sparse matrix).

        Raises:
            RuntimeError: If the TF-IDF Vectorizer has not been loaded or fitted prior to calling.
        """
        if self.vectorizer is None:
            raise RuntimeError("TF-IDF Vectorizer not loaded. Cannot prepare data for prediction. "
                               "Ensure `prepare_data_for_training` was called or components were loaded.")

        # Combine text fields for the single instance, normalize to lowercase
        combined_text = f"{description} {payee} {account}".strip().lower()
        # Transform the single instance using the fitted vectorizer
        X_vectorized = self.vectorizer.transform([combined_text])

        return X_vectorized

    def get_feature_dim(self) -> int:
        """
        Returns the number of features (i.e., the size of the vocabulary)
        that the TF-IDF vectorizer has learned. This is essential for
        initializing deep learning models (like DNNs) with the correct
        input layer size.

        Returns:
            int: The number of features.

        Raises:
            RuntimeError: If the TF-IDF Vectorizer has not been loaded or fitted.
        """
        if self.vectorizer is None:
            raise RuntimeError("TF-IDF Vectorizer not loaded. Cannot determine feature dimension.")
        # `max_features` limits the vocabulary size, so `len(vocabulary_)` reflects the actual number used.
        return len(self.vectorizer.vocabulary_)

    def get_num_classes(self) -> int:
        """
        Returns the number of unique target classes (BudgetPaths) that the
        label encoder has learned. This is crucial for setting the output
        layer size of classification models.

        Returns:
            int: The number of unique classes.

        Raises:
            RuntimeError: If the Label Encoder has not been loaded or fitted.
        """
        if self.label_encoder is None:
            raise RuntimeError("Label Encoder not loaded. Cannot determine number of classes.")
        return len(self.label_encoder.classes_)

    def decode_predictions(self, encoded_predictions: Union[np.ndarray, torch.Tensor]) -> List[str]:
        """
        Decodes numerical predictions (e.g., class IDs from a model's argmax output)
        back into their original string representations (BudgetPaths).

        Args:
            encoded_predictions (Union[np.ndarray, torch.Tensor]): Numerical predictions.
                Can be a single scalar, a 1D array/tensor of class IDs, or
                a 2D array/tensor of probabilities (in which case argmax is applied).

        Returns:
            List[str]: A list of decoded budget path strings.

        Raises:
            RuntimeError: If the Label Encoder has not been loaded or fitted.
            ValueError: If the input `encoded_predictions` has an unsupported shape.
        """
        if self.label_encoder is None:
            raise RuntimeError("Label Encoder not loaded. Cannot decode predictions. "
                               "Ensure `prepare_data_for_training` was called or components were loaded.")

        # Convert PyTorch tensors to NumPy arrays if applicable
        if isinstance(encoded_predictions, torch.Tensor):
            encoded_predictions = encoded_predictions.cpu().numpy()

        # Handle different shapes of input predictions
        if np.isscalar(encoded_predictions) or encoded_predictions.ndim == 0:
            # Single scalar prediction (e.g., a single class ID)
            return [self.label_encoder.inverse_transform([encoded_predictions])[0]]
        elif encoded_predictions.ndim == 1:
            # 1D array/tensor (e.g., a batch of class IDs)
            return self.label_encoder.inverse_transform(encoded_predictions).tolist()
        elif encoded_predictions.ndim == 2:
            # 2D array/tensor (e.g., a batch of probability distributions).
            # We need to find the class with the highest probability for each instance.
            predicted_classes = np.argmax(encoded_predictions, axis=1)
            return self.label_encoder.inverse_transform(predicted_classes).tolist()
        else:
            raise ValueError(f"Unsupported shape for encoded_predictions: {encoded_predictions.shape}. "
                             "Expected 0D, 1D, or 2D array/tensor.")
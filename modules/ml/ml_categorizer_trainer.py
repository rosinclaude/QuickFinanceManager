# modules/ml/ml_categorizer_trainer.py

import os
from typing import Dict, Any, Optional

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder


class MLCategorizerTrainer:
    """
    Manages the training and persistence of a classical Machine Learning model
    for transaction categorization.
    """

    # Removed hardcoded paths; these will now be passed in via __init__
    # MODEL_PATH = 'models/ml_categorizer_model.joblib'
    # VECTORIZER_PATH = 'models/tfidf_vectorizer.joblib'
    # LABEL_ENCODER_PATH = 'models/label_encoder.joblib'

    def __init__(self, app_config: Dict[str, Any]):  # Accept app_config
        """
        Initializes the MLCategorizerTrainer.

        Args:
            app_config (Dict[str, Any]): The loaded application configuration,
                                         containing paths for models.
        """
        self.app_config = app_config
        ml_config = app_config.get('ml_config', {})
        paths_config = app_config.get('paths', {})

        self.MODEL_PATH = ml_config.get('categorizer_model_path', 'models/ml_categorizer_model.joblib')
        self.VECTORIZER_PATH = ml_config.get('categorizer_vectorizer_path', 'models/tfidf_vectorizer.joblib')
        self.LABEL_ENCODER_PATH = ml_config.get('categorizer_label_encoder_path', 'models/label_encoder.joblib')
        self.MODELS_DIR = paths_config.get('models_dir', 'models/')

        os.makedirs(self.MODELS_DIR, exist_ok=True)
        print("MLCategorizerTrainer initialized.")

    def select_trainable_transactions(self, transactions_df):
        """
        Filter the transaction the model can be trained on, which should be transaction verified by the user.
        Args:
            transactions_df (pd.DataFrame): DataFrame containing historical transactions,
                                            at least with 'Description', 'Payer/Payee', and 'BudgetPath' columns.

        Returns:
            Filtered transaction (pd.DataFrame)
        """
        return transactions_df[transactions_df["IsVerified"] == True]

    def train_model(self, transactions_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Trains an ML model to predict 'BudgetPath' based on 'Description' and 'Payer/Payee'.

        Args:
            transactions_df (pd.DataFrame): DataFrame containing historical transactions,
                                            at least with 'Description', 'Payer/Payee', and 'BudgetPath' columns.

        Returns:
            Optional[Dict[str, Any]]: Training metrics if successful, None otherwise.
        """
        # Filter for transactions that have a valid BudgetPath
        df = transactions_df.copy()
        df = self.select_trainable_transactions(df)
        df = df[df['BudgetPath'].notna() & (df['BudgetPath'] != '')].reset_index(drop=True)

        if df.empty:
            print("No valid historical data with BudgetPaths to train the ML categorizer.")
            return None

        # Create combined text feature
        df['combined_text'] = df['Description'].fillna('') + " " + df['Payer/Payee'].fillna('')
        df['combined_text'] = df['combined_text'].str.lower()  # Normalize

        X = df['combined_text']
        y = df['BudgetPath']

        if len(y.unique()) < 2:
            print(
                f"Only {len(y.unique())} unique BudgetPath found. Need at least 2 for classification. Skipping ML training.")
            return None

        # Encode target labels
        label_encoder = LabelEncoder()
        y_encoded = label_encoder.fit_transform(y)

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(X, y_encoded, test_size=0.2, random_state=42,
                                                            stratify=y_encoded)

        # Create a pipeline: TF-IDF Vectorizer + Logistic Regression Classifier
        # You could experiment with other classifiers like RandomForestClassifier, SVC, etc.
        model_pipeline = Pipeline([
            ('tfidf', TfidfVectorizer(stop_words='english', max_features=5000)),
            ('classifier', LogisticRegression(random_state=42, solver='liblinear', multi_class='ovr', max_iter=1000))
        ])

        print("Training ML Categorizer model...")
        model_pipeline.fit(X_train, y_train)
        print("ML Categorizer model training complete.")

        # Evaluate (optional, for feedback)
        accuracy = model_pipeline.score(X_test, y_test)
        print(f"ML Model Test Accuracy: {accuracy:.4f}")

        # Save the trained model and components
        joblib.dump(model_pipeline, self.MODEL_PATH)
        joblib.dump(model_pipeline.named_steps['tfidf'], self.VECTORIZER_PATH)
        joblib.dump(label_encoder, self.LABEL_ENCODER_PATH)
        print(f"ML Model saved to {self.MODEL_PATH}")
        print(f"TF-IDF Vectorizer saved to {self.VECTORIZER_PATH}")
        print(f"Label Encoder saved to {self.LABEL_ENCODER_PATH}")

        return {"accuracy": accuracy}

    def load_model(self) -> Optional[Pipeline]:
        """Loads the trained ML model and associated components."""
        if not os.path.exists(self.MODEL_PATH):
            print("No ML model found to load.")
            return None
        try:
            model = joblib.load(self.MODEL_PATH)
            print("ML model loaded successfully.")
            return model
        except Exception as e:
            print(f"Error loading ML model: {e}")
            return None

    def load_vectorizer(self) -> Optional[TfidfVectorizer]:
        """Loads the TF-IDF Vectorizer."""
        if not os.path.exists(self.VECTORIZER_PATH):
            print("No TF-IDF Vectorizer found to load.")
            return None
        try:
            vectorizer = joblib.load(self.VECTORIZER_PATH)
            print("TF-IDF Vectorizer loaded successfully.")
            return vectorizer
        except Exception as e:
            print(f"Error loading TF-IDF Vectorizer: {e}")
            return None

    def load_label_encoder(self) -> Optional[LabelEncoder]:
        """Loads the Label Encoder."""
        if not os.path.exists(self.LABEL_ENCODER_PATH):
            print("No Label Encoder found to load.")
            return None
        try:
            encoder = joblib.load(self.LABEL_ENCODER_PATH)
            print("Label Encoder loaded successfully.")
            return encoder
        except Exception as e:
            print(f"Error loading Label Encoder: {e}")
            return None

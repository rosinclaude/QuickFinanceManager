# modules/ml/trainers.py
"""
Objective:
This script defines various trainer classes for different machine learning models
used in transaction categorization (specifically BudgetPath prediction).
Each trainer is responsible for:
- Defining the architecture of its specific model (e.g., Logistic Regression,
  Decision Tree, TensorFlow DNN, PyTorch DNN).
- Orchestrating the model training process, including data splitting
  (train/test), model fitting, and evaluation.
- Saving the trained model to disk in a format suitable for that model type,
  ensuring it can be loaded later without needing its original class definition
  for deep learning models (TensorFlow and PyTorch).
- Loading a previously saved model for inference or further training (primarily for internal trainer use).

Crucially, these trainers *do not* handle data preprocessing directly.
Instead, they rely on a `DataPreprocessor` instance to prepare the input data
into the appropriate format (e.g., TF-IDF vectors, label-encoded targets)
before training. This separation of concerns improves modularity and reusability.
"""

import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
import joblib
import os
import datetime
from typing import Dict, Any, Optional, Union, List, Tuple

# Import the DataPreprocessor from the new module
from modules.ml.data_preprocessor import DataPreprocessor

# Attempt to import TensorFlow/Keras and PyTorch.
# These imports are wrapped in try-except blocks to allow the application
# to run even if one of the deep learning frameworks is not installed.
# This makes the trainers more robust in varied deployment environments.
try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential, load_model  # Specific imports for Keras model operations
    from tensorflow.keras.layers import Dense, Dropout  # Layers used in DNNs
    from tensorflow.keras.optimizers import Adam  # Optimizer for DNNs
    from tensorflow.keras.callbacks import EarlyStopping  # Callback for training control

    print("TensorFlow imported successfully.")
    _TF_AVAILABLE = True  # Flag to check TensorFlow availability
except ImportError:
    print("WARNING: TensorFlow not installed. TensorFlow DNN models will not be available.")
    _TF_AVAILABLE = False
except Exception as e:
    # Catch any other potential errors during import (e.g., corrupted installation)
    print(f"WARNING: Error importing TensorFlow: {e}. TensorFlow DNN models might not be available.")
    _TF_AVAILABLE = False

try:
    import torch
    import torch.nn as nn  # Neural network modules
    import torch.optim as optim  # Optimizers
    from torch.utils.data import TensorDataset, DataLoader  # Data handling utilities
    # Import torch.jit for scripting PyTorch models to save/load entire model graph
    import torch.jit

    print("PyTorch imported successfully.")
    _TORCH_AVAILABLE = True  # Flag to check PyTorch availability
except ImportError:
    print("WARNING: PyTorch not installed. PyTorch DNN models will not be available.")
    _TORCH_AVAILABLE = False
except Exception as e:
    print(f"WARNING: Error importing PyTorch: {e}. PyTorch DNN models might not be available.")
    _TORCH_AVAILABLE = False


class BaseTrainer:
    """
    Abstract base class for all machine learning model trainers.
    It defines the common interface and shared attributes for trainers,
    ensuring a consistent structure across different model types.

    Key responsibilities:
    - Initialize with a specific model directory and a `DataPreprocessor` instance.
    - Provide abstract methods for `train()`, `save_model()`, and `load_model()`
      that must be implemented by concrete subclasses.
    - Offer a generic `_get_model_path` utility for consistent file naming.
    """
    MODEL_TYPE: str = "base_model"  # Placeholder for the specific model type (e.g., 'logistic_regression')

    def __init__(self, model_dir: str, data_preprocessor: DataPreprocessor):
        """
        Initializes the BaseTrainer.

        Args:
            model_dir (str): The specific directory path where this particular model's
                             trained weights/artifacts should be saved and loaded.
                             This ensures each model type has its own storage location.
            data_preprocessor (DataPreprocessor): An instance of DataPreprocessor.
                                                  This dependency allows trainers to
                                                  access prepared data without handling
                                                  preprocessing logic themselves.
        """
        self.model_dir = model_dir
        os.makedirs(self.model_dir, exist_ok=True)  # Create the model-specific directory if it doesn't exist
        self.model = None  # Placeholder for the trained ML model
        self.data_preprocessor = data_preprocessor  # Reference to the shared data preprocessor
        print(f"BaseTrainer initialized for {self.MODEL_TYPE}. Model directory: {self.model_dir}")

    def _get_model_path(self, suffix: str = '') -> str:
        """
        Helper method to construct a standard file path for saving or loading
        the main model artifact within its designated `model_dir`.

        Args:
            suffix (str): An optional file extension or unique identifier (e.g., '.joblib', '.keras', '.pt').

        Returns:
            str: The full path to the model file.
        """
        # The file name is standardized as 'model' within its specific directory
        return os.path.join(self.model_dir, f'model{suffix}')

    def save_model(self):
        """
        Abstract method. Concrete trainer subclasses must implement this to define
        how their specific model type (e.g., scikit-learn, Keras, PyTorch) is saved to disk.
        """
        raise NotImplementedError("Subclasses must implement the 'save_model' method for their specific model type.")

    def load_model(self) -> Optional[Any]:
        """
        Abstract method. Concrete trainer subclasses must implement this to define
        how their specific model type is loaded from disk into memory.

        Returns:
            Optional[Any]: The loaded model object, or None if loading fails.
        """
        raise NotImplementedError("Subclasses must implement the 'load_model' method for their specific model type.")

    def get_model(self) -> Optional[Any]:
        """
        Returns the currently loaded or trained model instance.
        """
        return self.model

    def train(self, transactions_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Abstract method. Concrete trainer subclasses must implement this to define
        the entire training workflow for their specific model.

        Args:
            transactions_df (pd.DataFrame): The raw historical transaction data.
                                            This will be passed to `DataPreprocessor`
                                            for transformation.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing training metrics
                                      (e.g., accuracy, loss), or None if training fails.
        """
        raise NotImplementedError("Subclasses must implement the 'train' method.")


class LogisticRegressionCategorizerTrainer(BaseTrainer):
    """
    Concrete trainer class for training a Logistic Regression model
    for transaction categorization (BudgetPath prediction).
    Logistic Regression is a linear model often used as a strong baseline
    for classification tasks, particularly with sparse text features like TF-IDF.
    """
    MODEL_TYPE: str = "logistic_regression_categorizer"

    def __init__(self, model_dir: str, data_preprocessor: DataPreprocessor):
        """
        Initializes LogisticRegressionCategorizerTrainer.

        Args:
            model_dir (str): Dedicated directory for this model's artifacts.
            data_preprocessor (DataPreprocessor): Shared data preprocessor instance.
        """
        super().__init__(model_dir, data_preprocessor)
        print(f"{self.MODEL_TYPE} initialized.")

    def train(self, transactions_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Orchestrates the training process for the Logistic Regression model.

        1. Calls `DataPreprocessor` to prepare (vectorize and encode) the input data.
        2. Splits the prepared data into training and testing sets.
        3. Initializes and trains a `LogisticRegression` model.
        4. Evaluates the trained model on the test set.
        5. Saves the trained model to its designated directory.

        Args:
            transactions_df (pd.DataFrame): Raw historical transactions for training.

        Returns:
            Optional[Dict[str, Any]]: Dictionary with 'accuracy' metric, or None on failure.
        """
        try:
            # Use the shared DataPreprocessor to get vectorized features and encoded labels
            X_vectorized, y_encoded = self.data_preprocessor.prepare_data_for_training(transactions_df)
        except ValueError as e:
            # Handle cases where data is insufficient or invalid for training
            print(f"Data preparation error for {self.MODEL_TYPE} Trainer: {e}")
            return None

        # Split the data into training and testing sets for model evaluation.
        # `stratify=y_encoded` ensures that the proportion of classes is roughly the same in train and test sets.
        X_train, X_test, y_train, y_test = train_test_split(X_vectorized, y_encoded, test_size=0.2, random_state=42,
                                                            stratify=y_encoded)

        # Initialize the Logistic Regression model.
        # `solver='liblinear'` is good for small datasets and 'ovr' (one-vs-rest) for multi-class.
        # `max_iter` increased to ensure convergence on potentially complex datasets.
        self.model = LogisticRegression(random_state=42, solver='liblinear', multi_class='ovr', max_iter=1000)

        print(f"Training {self.MODEL_TYPE} model...")
        self.model.fit(X_train, y_train)  # Train the model
        print(f"{self.MODEL_TYPE} training complete.")

        # Evaluate the model's performance on the unseen test data
        accuracy = self.model.score(X_test, y_test)
        print(f"{self.MODEL_TYPE} Test Accuracy: {accuracy:.4f}")

        self.save_model()  # Save the trained Logistic Regression model
        # Note: The DataPreprocessor's components (vectorizer, label_encoder) are saved
        # automatically within `data_preprocessor.prepare_data_for_training()`.

        return {"accuracy": accuracy}

    def save_model(self):
        """
        Saves the trained Logistic Regression model to disk using `joblib`.
        `joblib` is suitable for saving scikit-learn models as it preserves their state.
        """
        if self.model:  # Ensure a model actually exists before attempting to save
            joblib.dump(self.model, self._get_model_path(suffix='.joblib'))  # Use .joblib suffix for clarity
            print(f"{self.MODEL_TYPE} Model saved to {self._get_model_path(suffix='.joblib')}")

    def load_model(self) -> Optional[LogisticRegression]:
        """
        Loads a previously saved Logistic Regression model from disk.

        Returns:
            Optional[LogisticRegression]: The loaded LogisticRegression model instance, or None if not found/error.
        """
        model_path = self._get_model_path(suffix='.joblib')
        if not os.path.exists(model_path):
            print(f"No {self.MODEL_TYPE} model found to load at {model_path}.")
            self.model = None
            return None
        try:
            self.model = joblib.load(model_path)
            print(f"{self.MODEL_TYPE} model loaded successfully from {model_path}.")
            return self.model
        except Exception as e:
            print(f"Error loading {self.MODEL_TYPE} model from {model_path}: {e}")
            self.model = None
            return None


class DecisionTreeCategorizerTrainer(BaseTrainer):
    """
    Concrete trainer class for training a Decision Tree model for transaction categorization.
    Decision Trees are inherently "rules-based" as they learn a series of if-then-else rules
    from the data, making them interpretable.
    """
    MODEL_TYPE: str = "decision_tree_categorizer"

    def __init__(self, model_dir: str, data_preprocessor: DataPreprocessor):
        """
        Initializes DecisionTreeCategorizerTrainer.

        Args:
            model_dir (str): Dedicated directory for this model's artifacts.
            data_preprocessor (DataPreprocessor): Shared data preprocessor instance.
        """
        super().__init__(model_dir, data_preprocessor)
        print(f"{self.MODEL_TYPE} initialized.")

    def train(self, transactions_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Orchestrates the training process for the Decision Tree model.

        1. Calls `DataPreprocessor` to prepare the input data.
        2. Splits the data into training and testing sets.
        3. Initializes and trains a `DecisionTreeClassifier` model.
        4. Evaluates the model.
        5. Saves the trained model.

        Args:
            transactions_df (pd.DataFrame): Raw historical transactions for training.

        Returns:
            Optional[Dict[str, Any]]: Dictionary with 'accuracy' metric, or None on failure.
        """
        try:
            X_vectorized, y_encoded = self.data_preprocessor.prepare_data_for_training(transactions_df)
        except ValueError as e:
            print(f"Data preparation error for {self.MODEL_TYPE} Trainer: {e}")
            return None

        X_train, X_test, y_train, y_test = train_test_split(X_vectorized, y_encoded, test_size=0.2, random_state=42,
                                                            stratify=y_encoded)

        self.model = DecisionTreeClassifier(random_state=42)  # Initialize Decision Tree classifier

        print(f"Training {self.MODEL_TYPE} model...")
        self.model.fit(X_train, y_train)  # Train the model
        print(f"{self.MODEL_TYPE} training complete.")

        accuracy = self.model.score(X_test, y_test)
        print(f"{self.MODEL_TYPE} Test Accuracy: {accuracy:.4f}")

        self.save_model()  # Save the trained Decision Tree model
        return {"accuracy": accuracy}

    def save_model(self):
        """
        Saves the trained Decision Tree model to disk using `joblib`.
        """
        if self.model:
            joblib.dump(self.model, self._get_model_path(suffix='.joblib'))
            print(f"{self.MODEL_TYPE} Model saved to {self._get_model_path(suffix='.joblib')}")

    def load_model(self) -> Optional[DecisionTreeClassifier]:
        """
        Loads a previously saved Decision Tree model from disk.
        """
        model_path = self._get_model_path(suffix='.joblib')
        if not os.path.exists(model_path):
            print(f"No {self.MODEL_TYPE} model found to load at {model_path}.")
            self.model = None
            return None
        try:
            self.model = joblib.load(model_path)
            print(f"{self.MODEL_TYPE} model loaded successfully from {model_path}.")
            return self.model
        except Exception as e:
            print(f"Error loading {self.MODEL_TYPE} model from {model_path}: {e}")
            self.model = None
            return None


class DNNCategorizerTrainerTF(BaseTrainer):
    """
    Concrete trainer class for training a Deep Neural Network (DNN) model
    for transaction categorization using TensorFlow/Keras.
    DNNs can capture complex non-linear relationships in the data.
    """
    MODEL_TYPE: str = "tensorflow_dnn_categorizer"

    def __init__(self, model_dir: str, data_preprocessor: DataPreprocessor):
        """
        Initializes DNNCategorizerTrainerTF.

        Args:
            model_dir (str): Dedicated directory for this model's artifacts.
            data_preprocessor (DataPreprocessor): Shared data preprocessor instance.
        """
        super().__init__(model_dir, data_preprocessor)
        print(f"{self.MODEL_TYPE} initialized.")

    def train(self, transactions_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Orchestrates the training process for the TensorFlow/Keras DNN model.

        1. Checks for TensorFlow availability.
        2. Uses `DataPreprocessor` to get vectorized features and encoded labels.
        3. Converts sparse TF-IDF data to dense NumPy arrays, which Keras prefers.
        4. Splits data into train/test sets.
        5. Defines a Sequential Keras model with Dense layers and Dropout for regularization.
        6. Compiles the model with Adam optimizer and sparse categorical crossentropy loss.
        7. Trains the model with Early Stopping to prevent overfitting.
        8. Evaluates and saves the trained model in Keras's native format.

        Args:
            transactions_df (pd.DataFrame): Raw historical transactions for training.

        Returns:
            Optional[Dict[str, Any]]: Dictionary with 'accuracy' and 'loss' metrics, or None on failure.
        """
        if not _TF_AVAILABLE:
            # Skip training if TensorFlow is not installed
            print("TensorFlow is not available. Skipping TensorFlow DNN model training.")
            return None

        try:
            X_vectorized, y_encoded = self.data_preprocessor.prepare_data_for_training(transactions_df)
        except ValueError as e:
            print(f"Data preparation error for {self.MODEL_TYPE} Trainer: {e}")
            return None

        # Convert sparse TF-IDF matrix to dense NumPy array as Keras models typically expect dense input
        X_train_dense, X_test_dense, y_train, y_test = train_test_split(
            X_vectorized.toarray(), y_encoded, test_size=0.2, random_state=42, stratify=y_encoded
        )

        # Get number of output classes and input features from the preprocessor
        num_classes = self.data_preprocessor.get_num_classes()
        input_dim = X_train_dense.shape[1]  # Number of features from TF-IDF vectorization

        # Define the Keras Sequential model architecture
        self.model = Sequential([
            tf.keras.Input(shape=(input_dim,)),  # Explicit Input layer for clarity and robust saving/loading
            Dense(256, activation='relu'),  # First hidden layer with ReLU activation
            Dropout(0.4),  # Dropout for regularization to prevent overfitting
            Dense(128, activation='relu'),  # Second hidden layer
            Dropout(0.4),
            Dense(num_classes, activation='softmax')  # Output layer for multi-class classification
        ])

        # Compile the model: define optimizer, loss function, and metrics
        self.model.compile(optimizer=Adam(learning_rate=0.001),  # Adam is a popular adaptive optimizer
                           loss='sparse_categorical_crossentropy',  # Suitable for integer-encoded labels
                           metrics=['accuracy'])  # Monitor accuracy during training

        # Define Early Stopping callback to stop training when validation loss stops improving
        early_stopping = EarlyStopping(monitor='val_loss', patience=10, restore_best_weights=True)

        print(f"Training {self.MODEL_TYPE} model...")
        # Train the model
        history = self.model.fit(
            X_train_dense, y_train,
            epochs=100,  # Max number of training epochs
            batch_size=32,  # Number of samples per gradient update
            validation_data=(X_test_dense, y_test),  # Data for validation during training
            callbacks=[early_stopping],  # Apply early stopping
            verbose=0  # Suppress detailed output per epoch for cleaner console
        )
        print(f"{self.MODEL_TYPE} training complete.")

        # Evaluate the final trained model on the test set
        loss, accuracy = self.model.evaluate(X_test_dense, y_test, verbose=0)
        print(f"{self.MODEL_TYPE} Test Accuracy: {accuracy:.4f}, Loss: {loss:.4f}")

        self.save_model()  # Save the trained Keras model
        return {"accuracy": accuracy, "loss": loss}

    def save_model(self):
        """
        Saves the trained TensorFlow/Keras model.
        Keras models are saved in their native `.keras` format, which includes
        architecture, weights, and compilation information. This allows for
        seamless loading without needing to define the model structure beforehand.
        """
        if self.model and _TF_AVAILABLE:
            model_save_path = self._get_model_path(suffix='.keras')  # Keras native format
            self.model.save(model_save_path)
            print(f"{self.MODEL_TYPE} Model saved to {model_save_path}")

    def load_model(self) -> Optional[Sequential]:
        """
        Loads a previously saved TensorFlow/Keras model from disk.
        The `tf.keras.models.load_model` function automatically reconstructs
        the model architecture and loads its weights.

        Returns:
            Optional[Sequential]: The loaded Keras Sequential model instance, or None if not found/error.
        """
        if not _TF_AVAILABLE:
            print(f"Cannot load {self.MODEL_TYPE} model, TensorFlow not available.")
            self.model = None
            return None
        model_path = self._get_model_path(suffix='.keras')
        if not os.path.exists(model_path):
            print(f"No {self.MODEL_TYPE} model found to load at {model_path}.")
            self.model = None
            return None
        try:
            self.model = load_model(model_path)  # Use tf.keras.models.load_model
            print(f"{self.MODEL_TYPE} Model loaded successfully from {model_path}.")
            return self.model
        except Exception as e:
            print(f"Error loading {self.MODEL_TYPE} model from {model_path}: {e}")
            self.model = None
            return None


class DNNCategorizerTrainerPyTorch(BaseTrainer):
    """
    Concrete trainer class for training a Deep Neural Network (DNN) model
    for transaction categorization using PyTorch.
    This class now uses `torch.jit.trace` to save the entire model graph,
    allowing for loading without needing the original Python class definition.
    """
    MODEL_TYPE: str = "pytorch_dnn_categorizer"

    # Define the PyTorch DNN architecture as an inner class.
    # This keeps the model definition encapsulated within its specific trainer,
    # making it clear which trainer uses which architecture.
    class SimpleDNN(nn.Module):
        """
        A simple Feed-Forward Deep Neural Network architecture for classification.
        Consists of two hidden layers with ReLU activation and Dropout for regularization,
        followed by an output layer with linear activation (CrossEntropyLoss handles softmax internally).
        """

        def __init__(self, input_dim: int, num_classes: int):
            """
            Initializes the SimpleDNN model.

            Args:
                input_dim (int): The number of input features (from TF-IDF vectorizer).
                num_classes (int): The number of output classes (BudgetPaths).
            """
            super().__init__()
            self.fc1 = nn.Linear(input_dim, 256)  # First fully connected layer
            self.dropout1 = nn.Dropout(0.4)  # Dropout layer
            self.fc2 = nn.Linear(256, 128)  # Second fully connected layer
            self.dropout2 = nn.Dropout(0.4)
            self.fc3 = nn.Linear(128, num_classes)  # Output layer

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """
            Defines the forward pass of the neural network.

            Args:
                x (torch.Tensor): Input tensor.

            Returns:
                torch.Tensor: Output tensor (logits before softmax).
            """
            x = torch.relu(self.fc1(x))  # Apply ReLU activation
            x = self.dropout1(x)
            x = torch.relu(self.fc2(x))
            x = self.dropout2(x)
            x = self.fc3(x)  # Output logits
            return x

    def __init__(self, model_dir: str, data_preprocessor: DataPreprocessor):
        """
        Initializes DNNCategorizerTrainerPyTorch.

        Args:
            model_dir (str): Dedicated directory for this model's artifacts.
            data_preprocessor (DataPreprocessor): Shared data preprocessor instance.
        """
        super().__init__(model_dir, data_preprocessor)
        print(f"{self.MODEL_TYPE} initialized.")
        # Define the specific path for saving the traced PyTorch model
        self.model_save_path = self._get_model_path(suffix='.pt')

    def train(self, transactions_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Orchestrates the training process for the PyTorch DNN model.

        1. Checks for PyTorch availability.
        2. Uses `DataPreprocessor` to get vectorized features and encoded labels.
        3. Converts sparse TF-IDF data to dense NumPy arrays, then to PyTorch tensors.
        4. Splits data into train/test sets and creates PyTorch DataLoaders.
        5. Initializes the `SimpleDNN` model, loss function (CrossEntropyLoss), and optimizer (Adam).
        6. Implements a training loop with validation and early stopping,
           saving the best model's state_dict.
        7. **Traces the best model for deployment and saves the traced model.**
        8. Evaluates the final (best) model on the test set.

        Args:
            transactions_df (pd.DataFrame): Raw historical transactions for training.

        Returns:
            Optional[Dict[str, Any]]: Dictionary with 'accuracy' and 'loss' metrics, or None on failure.
        """
        if not _TORCH_AVAILABLE:
            print("PyTorch is not available. Skipping PyTorch DNN model training.")
            return None

        try:
            X_vectorized, y_encoded = self.data_preprocessor.prepare_data_for_training(transactions_df)
        except ValueError as e:
            print(f"Data preparation error for {self.MODEL_TYPE} Trainer: {e}")
            return None

        # Convert sparse TF-IDF matrix to dense NumPy array for PyTorch
        X_train_dense, X_test_dense, y_train, y_test = train_test_split(
            X_vectorized.toarray(), y_encoded, test_size=0.2, random_state=42, stratify=y_encoded
        )

        # Convert NumPy arrays to PyTorch tensors.
        # Ensure target labels `y_encoded` are `torch.long` for `CrossEntropyLoss`.
        X_train_tensor = torch.tensor(X_train_dense, dtype=torch.float32)
        y_train_tensor = torch.tensor(y_train, dtype=torch.long)
        X_test_tensor = torch.tensor(X_test_dense, dtype=torch.float32)
        y_test_tensor = torch.tensor(y_test, dtype=torch.long)

        # Create PyTorch TensorDatasets and DataLoaders for efficient batching during training
        train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
        train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)  # Shuffle training data
        test_dataset = TensorDataset(X_test_tensor, y_test_tensor)
        test_loader = DataLoader(test_dataset, batch_size=32, shuffle=False)  # No need to shuffle test data

        # Get input and output dimensions from the DataPreprocessor
        input_dim = self.data_preprocessor.get_feature_dim()
        num_classes = self.data_preprocessor.get_num_classes()

        # Initialize the PyTorch model, loss function, and optimizer
        self.model = self.SimpleDNN(input_dim, num_classes)
        criterion = nn.CrossEntropyLoss()  # Standard loss for multi-class classification
        optimizer = optim.Adam(self.model.parameters(), lr=0.001)  # Adam optimizer

        print(f"Training {self.MODEL_TYPE} model...")
        best_val_loss = float('inf')  # Initialize for early stopping
        epochs_no_improve = 0
        patience = 10  # Number of epochs to wait for improvement before stopping
        num_epochs = 100  # Maximum number of epochs

        # Temporary path for saving only the state_dict during early stopping
        temp_state_dict_path = os.path.join(self.model_dir, 'temp_best_state_dict.pth')

        # Training loop
        for epoch in range(num_epochs):
            self.model.train()  # Set model to training mode (enables dropout, etc.)
            total_train_loss = 0
            for inputs, labels in train_loader:
                optimizer.zero_grad()  # Clear gradients from previous step
                outputs = self.model(inputs)  # Forward pass
                loss = criterion(outputs, labels)  # Calculate loss
                loss.backward()  # Backpropagation
                optimizer.step()  # Update model weights
                total_train_loss += loss.item()  # Accumulate training loss

            # Validation phase after each epoch
            self.model.eval()  # Set model to evaluation mode (disables dropout, etc.)
            val_loss = 0.0
            correct = 0
            total = 0
            with torch.no_grad():  # Disable gradient calculation during validation for efficiency
                for inputs, labels in test_loader:
                    outputs = self.model(inputs)
                    loss = criterion(outputs, labels)
                    val_loss += loss.item()
                    _, predicted = torch.max(outputs.data, 1)  # Get predicted class (index of max logit)
                    total += labels.size(0)
                    correct += (predicted == labels).sum().item()  # Count correct predictions

            avg_val_loss = val_loss / len(test_loader)
            val_accuracy = correct / total
            # print(f"Epoch {epoch+1}/{num_epochs}, Train Loss: {total_train_loss / len(train_loader):.4f}, "
            #       f"Val Loss: {avg_val_loss:.4f}, Val Acc: {val_accuracy:.4f}")

            # Early stopping logic: Save best model's state_dict and stop if no improvement
            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                epochs_no_improve = 0
                # Save only the state_dict for best validation performance
                torch.save(self.model.state_dict(), temp_state_dict_path)
            else:
                epochs_no_improve += 1
                if epochs_no_improve >= patience:
                    print(f"Early stopping at epoch {epoch + 1}/{num_epochs} as validation loss stopped improving.")
                    break

        # Load the best performing model weights from the temporary state_dict file
        self.model.load_state_dict(torch.load(temp_state_dict_path))
        # Remove the temporary state_dict file
        os.remove(temp_state_dict_path)
        print(f"{self.MODEL_TYPE} training complete.")

        # After training and loading the best state_dict, trace the model for deployment.
        # This creates a TorchScript module that can be saved and loaded without the
        # original Python class definition, aligning with Keras's seamless loading.
        # Use an example input from the test set for tracing.
        example_input = X_test_tensor[0:1]  # Take the first sample as example input
        self.model = torch.jit.trace(self.model, example_input)

        self.save_model()  # Save the traced PyTorch model

        # Final evaluation on the test set using the best model
        self.model.eval()
        correct = 0
        total = 0
        with torch.no_grad():
            for inputs, labels in test_loader:
                # Ensure inputs are treated as float32 for traced model
                outputs = self.model(inputs.float())
                _, predicted = torch.max(outputs.data, 1)
                total += labels.size(0)
                correct += (predicted == labels).sum().item()

        accuracy = correct / total
        print(f"PyTorch DNN Model Test Accuracy: {accuracy:.4f}")

        return {"accuracy": accuracy, "loss": best_val_loss}

    def save_model(self):
        """
        Saves the PyTorch model using `torch.jit.save()`.
        This method is called after the model has been traced in `train()`.
        Saving a traced model allows it to be loaded later without requiring
        the original `SimpleDNN` class definition or its `input_dim`/`num_classes`.
        """
        if self.model and _TORCH_AVAILABLE:
            # Check if the model is already a ScriptModule (traced)
            if isinstance(self.model, torch.jit.ScriptModule):
                torch.jit.save(self.model, self.model_save_path)
                print(f"PyTorch traced Model saved to {self.model_save_path}")
            else:
                print(f"WARNING: PyTorch model is not a traced ScriptModule. Cannot save in deployable format.")
                # Fallback to state_dict if for some reason tracing didn't happen (not ideal for deployment)
                torch.save(self.model.state_dict(), self._get_model_path(suffix='_state_dict.pth'))
                print(
                    f"WARNING: PyTorch model state_dict saved as fallback to {self._get_model_path(suffix='_state_dict.pth')}")

    def load_model(self) -> Optional[nn.Module]:
        """
        Loads a previously saved PyTorch model using `torch.jit.load()`.
        This method can directly load the traced model without needing
        prior knowledge of its architecture or dimensions.

        Returns:
            Optional[nn.Module]: The loaded PyTorch ScriptModule, or None if not found/error.
        """
        if not _TORCH_AVAILABLE:
            print(f"Cannot load {self.MODEL_TYPE} model, PyTorch not available.")
            self.model = None
            return None

        model_path = self.model_save_path
        if not os.path.exists(model_path):
            print(f"No {self.MODEL_TYPE} model found to load at {model_path}.")
            self.model = None
            return None

        try:
            self.model = torch.jit.load(model_path)
            self.model.eval()  # Set model to evaluation mode after loading
            print(f"{self.MODEL_TYPE} Model loaded successfully from {model_path}.")
            return self.model
        except Exception as e:
            print(f"Error loading {self.MODEL_TYPE} model from {model_path}: {e}")
            self.model = None
            return None

# The PayeeNameRecognizerTrainer class was removed as per the user's request
# to focus solely on BudgetPath prediction within this ML module for trainers.
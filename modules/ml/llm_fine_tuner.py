# modules/ml/llm_fine_tuner.py

import os
import pandas as pd
from typing import Dict, List, Any, Optional


# For few-shot learning, we usually use the same LLM client as for inference.
# For demonstration, we'll keep it simple, assuming you'd use something like
# `transformers` for local models, or `openai`, `google.generativeai` for APIs.
# For now, this will primarily focus on prompt construction for few-shot.
# For LLM inference, we'll use a simple conceptual client.
# In a real application, this would be an API client (e.g., google.generativeai, openai)
# or a local model inference setup (e.g., transformers pipeline).
class LLMClient:
    def __init__(self, model_name: str, api_key_env_var: str, temperature: float, max_tokens: int):
        """
        Initializes the LLM client with parameters from app_config.
        Args:
            model_name (str): The name of the LLM model to use (e.g., 'gemini-pro', 'dummy-llm').
            api_key_env_var (str): The name of the environment variable holding the API key.
            temperature (float): Controls the randomness of the LLM's output.
            max_tokens (int): The maximum number of tokens to generate in the LLM's response.
        """
        self.model_name = model_name
        self.api_key_env_var = api_key_env_var
        self.api_key = os.getenv(api_key_env_var)
        self.temperature = temperature
        self.max_tokens = max_tokens

        print(
            f"LLMClient initialized for model '{model_name}'. API key from '{api_key_env_var}' {'loaded' if self.api_key else 'NOT FOUND'}.")

        if not self.api_key and self.model_name != 'dummy-llm':
            print(
                f"WARNING: LLM API key not found in environment variable '{self.api_key_env_var}'. Real LLM calls will fail.")

        # Real LLM setup (conceptual - requires installing specific LLM client libraries)
        # if self.model_name == 'gemini-pro' and self.api_key:
        #     try:
        #         import google.generativeai as genai
        #         genai.configure(api_key=self.api_key)
        #         self._gemini_model = genai.GenerativeModel('gemini-pro')
        #         print("Google Generative AI (Gemini-pro) model configured.")
        #     except ImportError:
        #         print("WARNING: 'google-generativeai' not installed. Cannot use Gemini-pro.")
        #         self._gemini_model = None
        #     except Exception as e:
        #         print(f"ERROR: Failed to configure Gemini-pro model: {e}")
        #         self._gemini_model = None
        # else:
        #     self._gemini_model = None

    def generate(self, prompt: str) -> Optional[str]:  # Removed max_tokens and temperature from args; use self.
        """
        Sends a prompt to the LLM and gets a response.
        Args:
            prompt (str): The prompt string for the LLM.
        Returns:
            Optional[str]: The LLM's response, or None if an error occurs or no API key.
        """
        print(f"\n--- LLM Query ({self.model_name}) ---")
        print(f"Prompt:\n{prompt}")
        print(f"--- End LLM Query ---")

        # --- MOCK LLM RESPONSE LOGIC (for dummy-llm) ---
        if self.model_name == 'dummy-llm':
            # Updated mock logic to better reflect new financial_config structure and income
            if "groceries" in prompt.lower() or "supermarket" in prompt.lower() or "maxi" in prompt.lower() or "iga" in prompt.lower():
                return "Family:Food"
            elif "netflix" in prompt.lower() or "spotify" in prompt.lower():
                return "Family:Subscriptions"
            elif "hydro" in prompt.lower() and "quebec" in prompt.lower():
                return "Family:Utilities"
            elif "rent" in prompt.lower() or "mortgage" in prompt.lower():
                return "Family:Rent_Mortgage"
            elif "tim hortons" in prompt.lower() or "starbucks" in prompt.lower():
                return "Family:Entertainment"
            elif "salary" in prompt.lower() and "photography" in prompt.lower():
                return "Income:Salary_Photography"
            elif "camera gear" in prompt.lower() or "photography equipment" in prompt.lower():
                return "Personal:Businesses:Photography_Business:Equipment"
            elif "sewing" in prompt.lower() and "supplies" in prompt.lower():
                return "Personal:Businesses:Sewing_Business:Supplies"
            elif "food business" in prompt.lower() and "supplies" in prompt.lower():
                return "Personal:Businesses:Food_Business:Supplies"
            elif "soap" in prompt.lower() and "marketing" in prompt.lower():
                return "Personal:Businesses:Soap_Making_Business:Marketing"

            print("LLM mock: Returning a generic fallback category. (Update with real LLM inference!)")
            return "Uncategorized:LLM Fallback"
            # --- END MOCK LLM RESPONSE LOGIC ---

        # --- REAL LLM INTEGRATION (Example with Google Generative AI - requires 'google-generativeai' package) ---
        # if self.api_key and hasattr(self, '_gemini_model') and self._gemini_model:
        #     try:
        #         from google.generativeai import types
        #         response = self._gemini_model.generate_content(
        #             prompt,
        #             generation_config=types.GenerationConfig(
        #                 max_output_tokens=self.max_tokens,
        #                 temperature=self.temperature,
        #             )
        #         )
        #         # Assuming the LLM is well-behaved and returns just the category path
        #         return response.text.strip()
        #     except Exception as e:
        #         print(f"Error calling real LLM ({self.model_name}): {e}")
        #         return None
        # else:
        #     print("No real LLM client configured or API key missing.")
        return None  # If real LLM isn't set up or fails


class LLMFineTuner:
    """
    Conceptual class for generating few-shot examples for LLM prompting.
    In a real scenario, this would interact with a database of labeled transactions.
    """

    def __init__(self, llm_inference_client: LLMClient):
        """
        Initializes the LLMFineTuner.
        Args:
            llm_inference_client (LLMClient): An instance of the LLMClient for potential future fine-tuning APIs.
        """
        self.llm_inference_client = llm_inference_client
        print("LLMFineTuner initialized (conceptual for example generation).")

    def generate_few_shot_prompt_examples(self, transactions_df: pd.DataFrame, num_examples: int = 3) -> List[
        Dict[str, str]]:
        """
        Generates few-shot examples from historical transactions to include in LLM prompts.
        Args:
            transactions_df (pd.DataFrame): DataFrame of historical transactions with 'Description', 'Payer/Payee', 'Account', 'BudgetPath'.
            num_examples (int): The number of examples to generate.
        Returns:
            List[Dict[str, str]]: A list of dictionaries, each with 'input' and 'output' for the LLM prompt.
        """
        if transactions_df.empty:
            return []

        # Sample examples randomly to get diverse cases
        # Ensure we don't try to sample more examples than available
        examples = transactions_df.sample(min(num_examples, len(transactions_df)), random_state=42)

        formatted_examples = []
        for _, row in examples.iterrows():
            input_text = f"Description: {row['Description']}. Payee: {row['Payer/Payee']}. Account: {row['Account']}"
            output_text = row['BudgetPath']
            formatted_examples.append({"input": input_text, "output": output_text})

        return formatted_examples


class LLMFineTuner:
    """
    Manages fine-tuning or few-shot learning for the LLM used in categorization.
    """

    # If full fine-tuning a local model and saving it, you might retrieve this path from app_config:
    # FINETUNED_MODEL_PATH = 'models/finetuned_llm_categorizer'

    def __init__(self, llm_inference_client: LLMClient):
        """
        Initializes the LLMFineTuner.

        Args:
            llm_inference_client (Any): An instance of the LLM client (e.g., LLMClient from HybridCategorizer)
                                        used for potential conceptual fine-tuning or few-shot inference.
        """
        self.llm_inference_client = llm_inference_client
        print("LLMFineTuner initialized.")

    def fine_tune_llm(self, transactions_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Placeholder for actual LLM fine-tuning logic.

        Note: Full LLM fine-tuning typically requires significant resources and specialized libraries
              (e.g., PEFT, TRL with Hugging Face Transformers). This method provides a conceptual outline.

        Args:
            transactions_df (pd.DataFrame): Historical transactions for fine-tuning.
                                            Should include 'Description', 'Payer/Payee', 'BudgetPath'.

        Returns:
            Optional[Dict[str, Any]]: Metrics or confirmation of fine-tuning if successful, None otherwise.
        """
        print("Initiating LLM fine-tuning process (conceptual/placeholder).")

        training_data = []
        for _, row in transactions_df.iterrows():
            if pd.notna(row['BudgetPath']) and row['BudgetPath'] != '':
                training_data.append({
                    "instruction": f"Categorize the following transaction: Description: {row['Description']}, Payee: {row['Payer/Payee']}, Account: {row.get('Account', 'N/A')}, Notes: {row.get('Notes', 'N/A')}",
                    "output": row['BudgetPath']
                })

        if not training_data:
            print("No data available for LLM fine-tuning.")
            return None

        # Here you would integrate with a fine-tuning library (e.g., HuggingFace Transformers trainer, OpenAI API fine-tuning)
        # Example (conceptual):
        # trainer = SomeFineTuningTrainer(model=self.llm_inference_client.get_model_instance(), data=training_data)
        # trainer.train()
        # trainer.save_model(self.FINETUNED_MODEL_PATH)

        print(f"Prepared {len(training_data)} examples for LLM fine-tuning.")
        print("LLM fine-tuning process completed (conceptual).")
        return {"status": "fine_tuning_initiated", "num_examples": len(training_data)}

    def generate_few_shot_prompt_examples(self, transactions_df: pd.DataFrame, num_examples: int = 5) -> List[
        Dict[str, str]]:
        """
        Generates few-shot examples from historical data to be included in LLM prompts.

        Args:
            transactions_df (pd.DataFrame): Historical transactions.
            num_examples (int): Number of examples to select.

        Returns:
            List[Dict[str, str]]: A list of dictionaries, each containing 'input' and 'output'
                                  for the few-shot prompt.
        """
        df = transactions_df.copy()
        df = df[df['BudgetPath'].notna() & (df['BudgetPath'] != '')].reset_index(drop=True)

        if df.empty:
            print("No data to generate few-shot examples from.")
            return []

        # Select random examples, or more strategically select diverse examples
        # For simplicity, we'll take a random sample
        sample_df = df.sample(min(num_examples, len(df)), random_state=42)

        examples = []
        for _, row in sample_df.iterrows():
            # Use .get() for columns that might not always be present (like 'Notes')
            example_input = (f"Description: {row['Description']}\nPayee: {row['Payer/Payee']}\n"
                             f"Account: {row.get('Account', 'N/A')}\nNotes: {row.get('Notes', 'N/A')}")
            example_output = row['BudgetPath']
            examples.append({
                "input": example_input,
                "output": example_output
            })
        print(f"Generated {len(examples)} few-shot examples.")
        return examples

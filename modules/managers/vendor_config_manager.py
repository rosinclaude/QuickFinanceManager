# modules/managers/vendor_config_manager.py

import yaml
import os
import re
from typing import Dict, List, Any, Optional, Tuple
import torch
from sentence_transformers import SentenceTransformer, util


class VendorConfigManager:
    """
    Manages vendor-specific configurations, including identification patterns,
    custom parser mappings, and conforming vendor names for the database.
    Automatically updates the vendor patterns YAML if a new vendor is encountered.
    """
    # Removed hardcoded paths and LLM config; these will now be passed in via __init__
    # VENDOR_PATTERNS_FILE = 'configs/vendor_patterns.yaml'
    # LLM_MODEL_NAME = 'all-MiniLM-L6-v2'
    # LLM_SIMILARITY_THRESHOLD = 0.85

    def __init__(self, vendor_patterns_file: str, llm_model_name: str, llm_similarity_threshold: float):
        """
        Initializes the VendorConfigManager.

        Args:
            vendor_patterns_file (str): Path to the vendor patterns YAML file.
            llm_model_name (str): Name of the SentenceTransformer model for fuzzy matching.
            llm_similarity_threshold (float): Cosine similarity threshold for LLM fuzzy matching.
        """
        self.VENDOR_PATTERNS_FILE = vendor_patterns_file
        self.LLM_MODEL_NAME = llm_model_name
        self.LLM_SIMILARITY_THRESHOLD = llm_similarity_threshold

        self._vendor_patterns = self._load_vendor_patterns()
        print(f"VendorConfigManager initialized. Loaded {len(self._vendor_patterns.get('vendors', []))} known vendors.")

        self._llm_model = None
        self._load_llm_model()

    def _load_llm_model(self):
        """Loads the Hugging Face Sentence Transformer model."""
        try:
            print(f"Loading LLM model for vendor fuzzy matching: {self.LLM_MODEL_NAME}...")
            self._llm_model = SentenceTransformer(self.LLM_MODEL_NAME)
            print("LLM model loaded successfully.")
        except Exception as e:
            print(f"Failed to load LLM model {self.LLM_MODEL_NAME}: {e}")
            print("LLM-based vendor fuzzy matching will be disabled.")
            self._llm_model = None

    def _load_vendor_patterns(self) -> Dict[str, List[Dict[str, Any]]]:
        """Loads vendor identification patterns from the vendor_patterns.yaml file."""
        if not os.path.exists(self.VENDOR_PATTERNS_FILE):
            print(f"Vendor patterns config file not found at {self.VENDOR_PATTERNS_FILE}. Creating default.")
            self._create_default_vendor_patterns()

        try:
            with open(self.VENDOR_PATTERNS_FILE, 'r') as file:
                return yaml.safe_load(file)
        except yaml.YAMLError as e:
            print(f"Error parsing YAML vendor patterns file '{self.VENDOR_PATTERNS_FILE}': {e}")
            return {'vendors': []}

    def _create_default_vendor_patterns(self):
        """Creates a default vendor patterns YAML file."""
        default_patterns = {
            'vendors': [
                {'name': 'MAXI', 'patterns': ['MAXI', 'GROUPE PROVIGO'], 'custom_parser_module': None},
                {'name': 'COSTCO', 'patterns': ['COSTCO WHOLESALE', 'COSTCO'], 'custom_parser_module': 'costco_parser'},
                {'name': 'SAQ', 'patterns': ['SAQ', 'SOCIETE DES ALCOOLS DU QUEBEC'], 'custom_parser_module': None},
                {'name': 'WALMART', 'patterns': ['WAL-MART', 'WALMART'], 'custom_parser_module': None},
                {'name': 'IGA', 'patterns': ['IGA ST-HUBERT', 'IGA'], 'custom_parser_module': None},
                {'name': 'LOBLAW', 'patterns': ['LOBLAW'], 'custom_parser_module': None},
                {'name': 'RENO-DEPOT', 'patterns': ['RENO-DEPOT'], 'custom_parser_module': None},
            ]
        }
        os.makedirs(os.path.dirname(self.VENDOR_PATTERNS_FILE), exist_ok=True)
        with open(self.VENDOR_PATTERNS_FILE, 'w') as file:
            yaml.dump(default_patterns, file, default_flow_style=False, indent=2) # Added indent for readability
        print(f"Default vendor patterns config created at {self.VENDOR_PATTERNS_FILE}.")

    def save_vendor_patterns(self):
        """Saves the current vendor patterns back to the YAML file."""
        try:
            with open(self.VENDOR_PATTERNS_FILE, 'w') as file:
                yaml.dump(self._vendor_patterns, file, default_flow_style=False, indent=2) # Added indent for readability
            print(f"Vendor patterns saved to {self.VENDOR_PATTERNS_FILE}.")
        except Exception as e:
            print(f"Error saving vendor patterns to {self.VENDOR_PATTERNS_FILE}: {e}")

    def get_all_vendor_info(self) -> List[Dict[str, Any]]:
        """Returns the list of all configured vendor information."""
        return self._vendor_patterns.get('vendors', [])

    def get_conform_vendor_name(self, raw_vendor_name: str) -> str:
        """
        Attempts to find a conform vendor name for a given raw vendor name.
        Prioritizes exact/pattern match, then uses LLM for fuzzy matching.
        If no conform name is found, returns the raw name.
        """
        raw_vendor_name_upper = raw_vendor_name.upper()

        # 1. Exact/Pattern Match (high confidence, fast)
        for vendor_info in self._vendor_patterns.get('vendors', []):
            patterns = [p.upper() for p in vendor_info.get('patterns', [])]
            if any(pattern in raw_vendor_name_upper for pattern in patterns):
                return vendor_info['name']

        # 2. LLM-based Fuzzy Match (for variations, OCR errors, etc.)
        if self._llm_model:
            llm_conform_name = self._fuzzy_match_vendor_name(raw_vendor_name)
            if llm_conform_name:
                print(f"LLM identified '{raw_vendor_name}' as conform name '{llm_conform_name}'.")
                current_patterns = [p for v in self._vendor_patterns.get('vendors', []) if v['name'] == llm_conform_name
                                    for p in v.get('patterns', [])]
                if raw_vendor_name.upper() not in [p.upper() for p in current_patterns]:
                    self.update_vendor_patterns(llm_conform_name, [raw_vendor_name])
                return llm_conform_name

        # 3. If no match (neither pattern nor LLM), return the raw name
        return raw_vendor_name

    def _fuzzy_match_vendor_name(self, raw_vendor_name: str) -> Optional[str]:
        """
        Uses an LLM to compare the raw_vendor_name against known conform vendor names
        and suggest a match if similarity is above a threshold.
        """
        if not self._llm_model:
            return None

        known_conform_names = [v['name'] for v in self._vendor_patterns.get('vendors', [])]
        if not known_conform_names:
            return None

        all_texts = [raw_vendor_name] + known_conform_names
        try:
            embeddings = self._llm_model.encode(all_texts, convert_to_tensor=True)
            raw_embedding = embeddings[0]
            conform_embeddings = embeddings[1:]

            similarities = util.cos_sim(raw_embedding, conform_embeddings)[0]

            best_match_idx = torch.argmax(similarities).item()
            best_similarity = similarities[best_match_idx].item()
            best_match_name = known_conform_names[best_match_idx]

            print(f"LLM Fuzzy Match Similarity for '{raw_vendor_name}' vs '{best_match_name}': {best_similarity:.4f}")

            if best_similarity >= self.LLM_SIMILARITY_THRESHOLD:
                return best_match_name

        except Exception as e:
            print(f"Error during LLM-based vendor fuzzy matching: {e}")
            self._llm_model = None

        return None

    def get_custom_parser_module(self, conform_vendor_name: str) -> Optional[str]:
        """
        Returns the custom parser module name for a given conform vendor name, if one exists.
        """
        for vendor_info in self._vendor_patterns.get('vendors', []):
            if vendor_info['name'].upper() == conform_vendor_name.upper():
                return vendor_info.get('custom_parser_module')
        return None

    def add_new_vendor(self, new_vendor_name: str, patterns: List[str], custom_parser_module: Optional[str] = None):
        """
        Adds a new vendor entry to the configuration and saves it.
        This method should be called when a new, unidentifiable vendor is found.
        """
        for vendor_info in self._vendor_patterns.get('vendors', []):
            if vendor_info['name'].upper() == new_vendor_name.upper():
                print(f"Vendor '{new_vendor_name}' already exists in config. Updating its patterns.")
                self.update_vendor_patterns(new_vendor_name, patterns)
                return

        new_entry = {
            'name': new_vendor_name,
            'patterns': patterns,
            'custom_parser_module': custom_parser_module
        }
        self._vendor_patterns.setdefault('vendors', []).append(new_entry)
        self.save_vendor_patterns()
        print(f"Added new vendor '{new_vendor_name}' to {self.VENDOR_PATTERNS_FILE}.")

    def update_vendor_patterns(self, vendor_name: str, new_patterns: List[str]):
        """
        Updates the identification patterns for an existing vendor.
        """
        for vendor_info in self._vendor_patterns.get('vendors', []):
            if vendor_info['name'].upper() == vendor_name.upper():
                existing_patterns_upper = [p.upper() for p in vendor_info['patterns']]
                for pattern in new_patterns:
                    if pattern.upper() not in existing_patterns_upper:
                        vendor_info['patterns'].append(pattern)
                self.save_vendor_patterns()
                print(f"Updated patterns for vendor '{vendor_name}'.")
                return
        print(f"Vendor '{vendor_name}' not found for pattern update.")

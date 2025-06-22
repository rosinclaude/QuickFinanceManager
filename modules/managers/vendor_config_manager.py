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
    Leverages SentenceTransformer for semantic fuzzy matching of vendor names.
    """

    def __init__(self, vendor_patterns_file: str, llm_model_name: str,
                 llm_similarity_threshold: float, llm_ambiguity_threshold: float):
        """
        Initializes the VendorConfigManager.

        Args:
            vendor_patterns_file (str): Path to the vendor patterns YAML file.
            llm_model_name (str): Name of the SentenceTransformer model for fuzzy matching.
            llm_similarity_threshold (float): Cosine similarity threshold for LLM fuzzy matching (for auto-acceptance).
            llm_ambiguity_threshold (float): Lower cosine similarity threshold (below this is 'NO_MATCH', above this
                                             and below llm_similarity_threshold is 'AMBIGUOUS').
        """
        self.VENDOR_PATTERNS_FILE = vendor_patterns_file
        self.LLM_MODEL_NAME = llm_model_name
        self.LLM_SIMILARITY_THRESHOLD = llm_similarity_threshold
        self.LLM_AMBIGUITY_THRESHOLD = llm_ambiguity_threshold  # NEW: Ambiguity threshold

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
            yaml.dump(default_patterns, file, default_flow_style=False, indent=2)
        print(f"Default vendor patterns config created at {self.VENDOR_PATTERNS_FILE}.")

    def save_vendor_patterns(self):
        """Saves the current vendor patterns back to the YAML file."""
        try:
            with open(self.VENDOR_PATTERNS_FILE, 'w') as file:
                yaml.dump(self._vendor_patterns, file, default_flow_style=False, indent=2)
            print(f"Vendor patterns saved to {self.VENDOR_PATTERNS_FILE}.")
        except Exception as e:
            print(f"Error saving vendor patterns to {self.VENDOR_PATTERNS_FILE}: {e}")

    def get_all_vendor_info(self) -> List[Dict[str, Any]]:
        """Returns the list of all configured vendor information."""
        return self._vendor_patterns.get('vendors', [])

    def _fuzzy_match_vendor_name(self, raw_vendor_name: str) -> Tuple[Optional[str], float]:
        """
        Uses an LLM (SentenceTransformer) to compare the raw_vendor_name against known conform vendor names
        and returns the best match and its similarity score.
        Returns (best_match_name, best_similarity).
        """
        if not self._llm_model:
            return None, 0.0

        known_conform_names = [v['name'] for v in self._vendor_patterns.get('vendors', [])]
        if not known_conform_names:
            return None, 0.0

        all_texts = [raw_vendor_name] + known_conform_names
        try:
            embeddings = self._llm_model.encode(all_texts, convert_to_tensor=True)
            raw_embedding = embeddings[0]
            conform_embeddings = embeddings[1:]

            similarities = util.cos_sim(raw_embedding, conform_embeddings)[0]

            best_match_idx = torch.argmax(similarities).item()
            best_similarity = similarities[best_match_idx].item()
            best_match_name = known_conform_names[best_match_idx]

            # print(f"LLM Fuzzy Match Similarity for '{raw_vendor_name}' vs '{best_match_name}': {best_similarity:.4f}")
            return best_match_name, best_similarity

        except Exception as e:
            print(f"Error during LLM-based vendor fuzzy matching: {e}")
            # Do not disable model here, just return None. Model might fail for one case but work for others.
            return None, 0.0

    def suggest_conformed_payee(self, raw_payee_input: str) -> Dict[str, Any]:
        """
        Suggests a conformed payee name based on exact/pattern match first,
        then LLM semantic fuzzy matching, considering confidence thresholds.

        Args:
            raw_payee_input (str): The raw payee name provided by the user or OCR.

        Returns:
            Dict[str, Any]: A dictionary containing:
                'suggested_conformed_name' (str | None): The best suggested conformed name.
                'similarity_score' (float): The score of the best match (0.0 to 1.0).
                'status' (str): 'EXACT_MATCH', 'HIGH_CONFIDENCE', 'AMBIGUOUS', 'NO_MATCH'.
                'alternatives' (List[Dict[str, Any]]): Top N alternative matches (name and score) for 'AMBIGUOUS' status.
        """
        raw_payee_input_upper = raw_payee_input.upper()

        # Initialize result structure
        result = {
            'suggested_conformed_name': None,
            'similarity_score': 0.0,
            'status': 'NO_MATCH',
            'alternatives': []
        }

        # 1. Exact/Pattern Match (highest confidence)
        for vendor_info in self._vendor_patterns.get('vendors', []):
            patterns_upper = [p.upper() for p in vendor_info.get('patterns', [])]
            if any(pattern == raw_payee_input_upper for pattern in patterns_upper):  # Check for exact pattern match
                result['suggested_conformed_name'] = vendor_info['name']
                result['similarity_score'] = 1.0
                result['status'] = 'EXACT_MATCH'
                return result
            # Also check if raw_payee_input is itself a conformed name
            if vendor_info['name'].upper() == raw_payee_input_upper:
                result['suggested_conformed_name'] = vendor_info['name']
                result['similarity_score'] = 1.0
                result['status'] = 'EXACT_MATCH'
                return result

        # 2. LLM-based Fuzzy Match (semantic similarity)
        best_match_name, best_similarity = self._fuzzy_match_vendor_name(raw_payee_input)

        if best_match_name and best_similarity > 0:  # If LLM found any match
            result['suggested_conformed_name'] = best_match_name
            result['similarity_score'] = best_similarity

            if best_similarity >= self.LLM_SIMILARITY_THRESHOLD:
                result['status'] = 'HIGH_CONFIDENCE'
                # Optionally, update patterns for future faster matches
                # self.update_vendor_patterns(best_match_name, [raw_payee_input]) # This will be handled by TransactionManager/PayeeManager

            elif best_similarity >= self.LLM_AMBIGUITY_THRESHOLD:
                result['status'] = 'AMBIGUOUS'
                # Collect and add top alternatives if in ambiguous range
                all_known_names = [v['name'] for v in self._vendor_patterns.get('vendors', [])]
                if all_known_names:
                    all_texts_for_alternatives = [raw_payee_input] + all_known_names
                    try:
                        embeddings_for_alternatives = self._llm_model.encode(all_texts_for_alternatives,
                                                                             convert_to_tensor=True)
                        raw_embedding_alt = embeddings_for_alternatives[0]
                        conform_embeddings_alt = embeddings_for_alternatives[1:]
                        similarities_alt = util.cos_sim(raw_embedding_alt, conform_embeddings_alt)[0]

                        alternative_matches = []
                        # Create a list of (score, name) tuples, excluding the best match itself
                        scored_names = []
                        for i, sim_score in enumerate(similarities_alt):
                            if all_known_names[i] != best_match_name:  # Exclude the best match
                                scored_names.append((sim_score.item(), all_known_names[i]))

                        scored_names.sort(key=lambda x: x[0], reverse=True)  # Sort by score

                        # Collect top N alternatives above ambiguity threshold
                        for score, name in scored_names:
                            if score >= self.LLM_AMBIGUITY_THRESHOLD and len(
                                    result['alternatives']) < 3:  # Limit to 3 alternatives
                                result['alternatives'].append({'name': name, 'score': score})
                            elif len(result['alternatives']) >= 3:
                                break
                    except Exception as e:
                        print(f"Error collecting alternatives for LLM-based fuzzy matching: {e}")

            else:  # Below ambiguity threshold
                result['status'] = 'NO_MATCH'

        return result

    def get_conform_vendor_name(self, raw_vendor_name: str) -> str:
        """
        Attempts to find a conform vendor name for a given raw vendor name based on
        exact/pattern match or high-confidence LLM fuzzy match.
        If no high-confidence conform name is found, returns the raw name.
        This method is intended for internal use where auto-conforming is desired,
        while `suggest_conformed_payee` provides richer detail for UI.
        """
        suggestion_result = self.suggest_conformed_payee(raw_vendor_name)

        if suggestion_result['status'] in ['EXACT_MATCH', 'HIGH_CONFIDENCE']:
            return suggestion_result['suggested_conformed_name']

        # If not high confidence or exact match, return the original raw name
        # The UI will then use the full suggestion_result for user interaction.
        return raw_vendor_name

    def get_custom_parser_module(self, conform_vendor_name: str) -> Optional[str]:
        """
        Returns the custom parser module name for a given conform vendor name, if one exists.
        """
        for vendor_info in self._vendor_patterns.get('vendors', []):
            if vendor_info['name'].upper() == conform_vendor_name.upper():
                return vendor_info.get('custom_parser_module')
        return None

    def add_new_vendor(self, new_vendor_name: str, patterns: Optional[List[str]] = None,
                       custom_parser_module: Optional[str] = None):
        """
        Adds a new vendor entry to the configuration and saves it.
        This method should be called when a new, unidentifiable vendor is found.
        If vendor already exists, it updates its patterns.
        """
        patterns = patterns if patterns is not None else []

        # Check if the exact vendor name (case-insensitive) already exists as a canonical name
        for vendor_info in self._vendor_patterns.get('vendors', []):
            if vendor_info['name'].upper() == new_vendor_name.upper():
                print(
                    f"Vendor '{new_vendor_name}' already exists as canonical name. Updating its patterns if new ones provided.")
                self.update_vendor_patterns(new_vendor_name, patterns)
                return

        # Check if new_vendor_name exists as an alias to an existing vendor.
        # This requires iterating through all vendors' patterns to find if this new name
        # is actually an existing pattern for a different canonical vendor.
        for vendor_info in self._vendor_patterns.get('vendors', []):
            existing_patterns_upper = [p.upper() for p in vendor_info.get('patterns', [])]
            if new_vendor_name.upper() in existing_patterns_upper:
                print(
                    f"'{new_vendor_name}' is already an alias for existing vendor '{vendor_info['name']}'. No new vendor added.")
                return  # Do not add a new vendor if it's already an alias

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
        Adds new_patterns to the existing list without duplicates.
        """
        found = False
        for vendor_info in self._vendor_patterns.get('vendors', []):
            if vendor_info['name'].upper() == vendor_name.upper():
                existing_patterns_upper = {p.upper() for p in vendor_info['patterns']}
                initial_pattern_count = len(vendor_info['patterns'])
                for pattern in new_patterns:
                    if pattern.upper() not in existing_patterns_upper:
                        vendor_info['patterns'].append(pattern)

                if len(vendor_info['patterns']) > initial_pattern_count:  # Only save if new patterns were added
                    self.save_vendor_patterns()
                    print(f"Updated patterns for vendor '{vendor_name}'.")
                else:
                    print(f"No new patterns to add for vendor '{vendor_name}'.")
                found = True
                return
        if not found:
            print(f"Vendor '{vendor_name}' not found for pattern update. Consider adding it first.")
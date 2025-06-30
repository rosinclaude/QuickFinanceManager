# modules/managers/vendor_config_manager.py
# TODO: save and extract from databases.

import yaml
import os
import re
from typing import Dict, List, Any, Optional, Tuple
import torch
from sentence_transformers import SentenceTransformer, util

from modules.managers.payee_manager import PayeeManager


class VendorConfigManager:
    """
    Manages vendor-specific configurations, including identification patterns,
    custom parser mappings, and conforming vendor names for the database.
    Leverages SentenceTransformer for semantic fuzzy matching of payee names
    against configured patterns and all known payees from the PayeeManager.
    """

    def __init__(self, vendor_patterns_file: str, llm_model_name: str,
                 llm_similarity_threshold: float, llm_ambiguity_threshold: float,
                 payee_manager: PayeeManager):
        """
        Initializes the VendorConfigManager.

        Args:
            vendor_patterns_file (str): Path to the vendor patterns YAML file.
            llm_model_name (str): Name of the SentenceTransformer model for fuzzy matching.
            llm_similarity_threshold (float): Cosine similarity threshold for LLM fuzzy matching (for auto-acceptance).
            llm_ambiguity_threshold (float): Lower cosine similarity threshold (below this is 'NO_MATCH', above this
                                             and below llm_similarity_threshold is 'AMBIGUOUS').
            payee_manager (PayeeManager): An instance of PayeeManager to access all known payees.
        """
        self.VENDOR_PATTERNS_FILE = vendor_patterns_file
        self.LLM_MODEL_NAME = llm_model_name
        self.LLM_SIMILARITY_THRESHOLD = llm_similarity_threshold
        self.LLM_AMBIGUITY_THRESHOLD = llm_ambiguity_threshold

        self.payee_manager = payee_manager  # Store payee_manager

        self._vendor_patterns = self._load_vendor_patterns()
        print(f"VendorConfigManager initialized. Loaded {len(self._vendor_patterns.get('vendors', []))} known vendors.")

        self._llm_model = None
        # These will store the texts we embed and their corresponding canonical names
        self._known_matchable_texts = []  # List of strings to embed (canonical names, patterns, historical payees)
        # This maps index in _known_matchable_texts to its canonical name
        self._matchable_text_to_canonical_map = {}  # Dict: {index_in_known_matchable_texts: canonical_name}

        self._load_llm_model()  # This now also triggers _precompute_known_embeddings

    def _load_llm_model(self):
        """Loads the Hugging Face Sentence Transformer model and pre-computes embeddings."""
        try:
            print(f"Loading LLM model for vendor fuzzy matching: {self.LLM_MODEL_NAME}...")
            self._llm_model = SentenceTransformer(self.LLM_MODEL_NAME)
            print("LLM model loaded successfully.")
            self._precompute_known_embeddings()  # Initial pre-computation
        except Exception as e:
            print(f"Failed to load LLM model {self.LLM_MODEL_NAME}: {e}")
            print("LLM-based vendor fuzzy matching will be disabled.")
            self._llm_model = None
            self._known_embeddings = None  # Ensure embeddings are cleared if model fails
            self._known_matchable_texts = []
            self._matchable_text_to_canonical_map = {}

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
                {'name': 'MAXI', 'patterns': ['MAXI', 'GROUPE PROVIGO', 'MAXI & CIE'], 'custom_parser_module': None},
                {'name': 'COSTCO', 'patterns': ['COSTCO WHOLESALE', 'COSTCO'], 'custom_parser_module': 'costco_parser'},
                {'name': 'SAQ', 'patterns': ['SAQ', 'SOCIETE DES ALCOOLS DU QUEBEC'], 'custom_parser_module': None},
                {'name': 'WALMART', 'patterns': ['WAL-MART', 'WALMART SUPERCENTER'], 'custom_parser_module': None},
                {'name': 'IGA', 'patterns': ['IGA ST-HUBERT', 'IGA EXPRESS'], 'custom_parser_module': None},
                {'name': 'LOBLAW', 'patterns': ['LOBLAW CITYMARKET', 'LOBLAWS'], 'custom_parser_module': None},
                {'name': 'RENO-DEPOT', 'patterns': ['RONA RENODEPOT'], 'custom_parser_module': None},
                # Add Cargill/Carglass examples for testing ambiguity
                {'name': 'CARGILL', 'patterns': ['CARGILL FOODS'], 'custom_parser_module': None},
                {'name': 'CARGLASS', 'patterns': ['CARGLASS CANADA'], 'custom_parser_module': None},
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
            if self._llm_model:  # Only re-compute if model is loaded
                self._precompute_known_embeddings()  # Re-compute embeddings after saving patterns
        except Exception as e:
            print(f"Error saving vendor patterns to {self.VENDOR_PATTERNS_FILE}: {e}")

    def get_all_vendor_info(self) -> List[Dict[str, Any]]:
        """Returns the list of all configured vendor information."""
        return self._vendor_patterns.get('vendors', [])

    def _precompute_known_embeddings(self):
        """
        Pre-computes embeddings for all known matchable payee texts (canonical names, patterns, historical payees)
        and stores the mapping to their canonical names.
        This is called on init and after vendor patterns are saved/updated.
        """
        if not self._llm_model:
            return

        matchable_texts = []  # List of unique strings to be embedded
        matchable_to_canonical_map = {}  # Maps index in matchable_texts to its canonical vendor name
        seen_texts_lower = set()

        # 1. Add canonical vendor names and their patterns from vendor_patterns.yaml
        for vendor_info in self._vendor_patterns.get('vendors', []):
            canonical_name = vendor_info['name']

            # Add canonical name itself if not seen
            if canonical_name.lower() not in seen_texts_lower:
                matchable_texts.append(canonical_name)
                matchable_to_canonical_map[len(matchable_texts) - 1] = canonical_name
                seen_texts_lower.add(canonical_name.lower())

            # Add all patterns/aliases for this canonical name
            for pattern in vendor_info.get('patterns', []):
                if pattern.lower() not in seen_texts_lower:
                    matchable_texts.append(pattern)
                    matchable_to_canonical_map[len(matchable_texts) - 1] = canonical_name
                    seen_texts_lower.add(pattern.lower())

        # 2. Add all unique payees from payees.csv that are NOT already canonical names or patterns
        # This is where the payee_manager integrates
        all_saved_payees = self.payee_manager.get_all_payee_names()
        for payee_name in all_saved_payees:
            # Check if this saved payee is already covered by a canonical name or a pattern
            is_covered = False
            for vendor_info in self._vendor_patterns.get('vendors', []):
                if vendor_info['name'].upper() == payee_name.upper():
                    is_covered = True
                    break
                for pattern in vendor_info.get('patterns', []):
                    if pattern.upper() == payee_name.upper():
                        is_covered = True
                        break
                if is_covered:
                    break

            if not is_covered and payee_name.lower() not in seen_texts_lower:
                matchable_texts.append(payee_name)
                # For historical payees not in vendor_patterns, their canonical name is themselves
                matchable_to_canonical_map[len(matchable_texts) - 1] = payee_name
                seen_texts_lower.add(payee_name.lower())

        self._known_matchable_texts = matchable_texts
        self._matchable_text_to_canonical_map = matchable_to_canonical_map

        if self._known_matchable_texts:
            print(f"Pre-computing embeddings for {len(self._known_matchable_texts)} known matchable texts.")
            try:
                self._known_embeddings = self._llm_model.encode(
                    self._known_matchable_texts, convert_to_tensor=True
                )
                print("Known embeddings pre-computed successfully.")
            except Exception as e:
                print(f"Error pre-computing embeddings: {e}")
                self._known_embeddings = None
        else:
            print("No known matchable texts to pre-compute embeddings for.")
            self._known_embeddings = None

    def _are_embeddings_ready(self) -> bool:
        """
        Checks if the LLM model is loaded, and if known embeddings and matchable texts are available and usable.
        Returns True if ready, False otherwise.
        """
        if self._llm_model is None:
            # print("LLM model is not loaded.")
            return False
        if self._known_embeddings is None:
            # print("Known embeddings have not been computed yet (is None).")
            return False
        # Check if the tensor is empty using .numel()
        if self._known_embeddings.numel() == 0:
            # print("Known embeddings tensor is empty.")
            return False
        if not self._known_matchable_texts:  # Check if the list of texts is empty
            # print("No known matchable texts to compare against.")
            return False
        return True

    def _compute_fuzzy_matches(self, raw_payee_input: str) -> List[Dict[str, Any]]:
        """
        Computes cosine similarities between raw_payee_input and all known matchable texts.
        Returns a sorted list of matches, including their text, score, and canonical name.
        """
        if not self._are_embeddings_ready():
            return []

        try:
            raw_embedding = self._llm_model.encode(raw_payee_input, convert_to_tensor=True)
            similarities = util.cos_sim(raw_embedding, self._known_embeddings)[0]

            matches = []
            for i, sim_score in enumerate(similarities):
                score_item = sim_score.item()
                if score_item >= self.LLM_AMBIGUITY_THRESHOLD:  # Only consider matches above ambiguity threshold
                    matches.append({
                        'text': self._known_matchable_texts[i],
                        'score': score_item,
                        'canonical_name': self._matchable_text_to_canonical_map[i]
                    })

            # Sort by score in descending order
            matches.sort(key=lambda x: x['score'], reverse=True)
            return matches

        except Exception as e:
            print(f"Error during LLM-based fuzzy matching: {e}")
            return []

    def suggest_conformed_payee(self, raw_payee_input: str) -> Dict[str, Any]:
        """
        Suggests a conformed payee name based on LLM semantic fuzzy matching,
        considering confidence thresholds.

        Args:
            raw_payee_input (str): The raw payee name provided by the user or OCR.

        Returns:
            Dict[str, Any]: A dictionary containing:
                'suggested_conformed_name' (str | None): The best suggested conformed name.
                'similarity_score' (float): The score of the best match (0.0 to 1.0).
                'status' (str): 'EXACT_MATCH', 'HIGH_CONFIDENCE', 'AMBIGUOUS', 'NO_MATCH'.
                'alternatives' (List[Dict[str, Any]]): Top N alternative matches (canonical name and score).
        """
        result = {
            'suggested_conformed_name': None,
            'similarity_score': 0.0,
            'status': 'NO_MATCH',
            'alternatives': []
        }

        if not raw_payee_input:
            return result

        # 1. Compute all fuzzy matches once
        all_matches = self._compute_fuzzy_matches(raw_payee_input)

        if not all_matches:
            return result  # No matches found above ambiguity threshold

        # Find the best match overall, considering exact match first, then highest semantic score
        best_overall_match_text = None
        best_overall_score = 0.0
        best_overall_canonical_name = None

        # Check for an exact match among canonical names or patterns first for highest confidence
        raw_payee_input_lower = raw_payee_input.lower()
        for match in all_matches:
            if match['text'].lower() == raw_payee_input_lower:
                result['suggested_conformed_name'] = match['canonical_name']
                result['similarity_score'] = 1.0
                result['status'] = 'EXACT_MATCH'
                return result  # Exact match found, return immediately

        # If no exact text match, proceed with the best semantic match from all_matches
        # all_matches is already sorted by score, so the first one is the best semantic match
        best_semantic_match = all_matches[0]
        best_overall_match_text = best_semantic_match['text']
        best_overall_score = best_semantic_match['score']
        best_overall_canonical_name = best_semantic_match['canonical_name']

        result['suggested_conformed_name'] = best_overall_canonical_name
        result['similarity_score'] = best_overall_score

        # Determine status based on thresholds
        if best_overall_score >= self.LLM_SIMILARITY_THRESHOLD:
            result['status'] = 'HIGH_CONFIDENCE'
        elif best_overall_score >= self.LLM_AMBIGUITY_THRESHOLD:
            result['status'] = 'AMBIGUOUS'
        else:
            result['status'] = 'NO_MATCH'  # Below ambiguity threshold

        # Collect alternatives for 'AMBIGUOUS' status
        if result['status'] == 'AMBIGUOUS':
            added_canonical_names = {best_overall_canonical_name}  # Use set to track added canonical names
            for match in all_matches:
                if match['canonical_name'] not in added_canonical_names:  # Ensure unique canonical alternatives
                    # Only add if score is still relevant (above ambiguity threshold) and we haven't hit limit
                    if match['score'] >= self.LLM_AMBIGUITY_THRESHOLD and len(result['alternatives']) < 3:
                        result['alternatives'].append({
                            'name': match['canonical_name'],  # Report the canonical name
                            'score': match['score']
                        })
                        added_canonical_names.add(match['canonical_name'])
                    elif len(result['alternatives']) >= 3:
                        break  # Stop if we have enough alternatives

        return result

    def get_conform_vendor_name(self, raw_vendor_name: str) -> str:
        """
        Attempts to find a conform vendor name for a given raw vendor name based on
        exact match or high-confidence LLM semantic fuzzy match.
        If no high-confidence conform name is found, returns the raw name.
        This method is intended for internal use where auto-conforming is desired
        (e.g., in OCR processing), while `suggest_conformed_payee` provides richer
        detail for UI interaction.
        """
        suggestion_result = self.suggest_conformed_payee(raw_vendor_name)

        if suggestion_result['status'] in ['EXACT_MATCH', 'HIGH_CONFIDENCE']:
            return suggestion_result['suggested_conformed_name']

        # If not high confidence or exact match, return the original raw name
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
        This method should be called when a new, unidentifiable vendor is found
        and confirmed by the user. If vendor already exists, it updates its patterns.
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

        # If it's truly a new canonical vendor
        new_entry = {
            'name': new_vendor_name,
            'patterns': patterns,
            'custom_parser_module': custom_parser_module
        }
        self._vendor_patterns.setdefault('vendors', []).append(new_entry)
        self.save_vendor_patterns()  # This will trigger re-embedding of all texts
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
                    self.save_vendor_patterns()  # This will trigger re-embedding
                    print(f"Updated patterns for vendor '{vendor_name}'.")
                else:
                    print(f"No new patterns to add for vendor '{vendor_name}'.")
                found = True
                return
        if not found:
            print(f"Vendor '{vendor_name}' not found for pattern update. Consider adding it first.")
# modules/automation/ocr_processor.py

import easyocr
import cv2
import numpy as np
import os
from typing import Dict, Any, List


class OCRProcessor:
    def __init__(self, languages: List[str], gpu: bool):
        """
        Initializes the EasyOCR reader.
        Args:
            languages (list): List of languages to use for OCR (e.g., ['en', 'fr']).
            gpu (bool): Whether to use GPU for OCR (requires CUDA). Set to False for CPU.
        """
        self.languages = languages
        self.gpu = gpu
        try:
            # Ensure the EasyOCR data directory exists and is writable if models need to be downloaded
            # Corrected parameter: changed 'download_path' to 'model_storage_directory'
            easyocr_data_dir = os.path.join(os.path.expanduser("~"), ".EasyOCR")
            os.makedirs(easyocr_data_dir, exist_ok=True)

            self.reader = easyocr.Reader(self.languages, gpu=self.gpu, model_storage_directory=easyocr_data_dir)
            print(f"EasyOCR reader initialized with languages: {self.languages}, GPU: {self.gpu}")
        except Exception as e:
            print(f"Error initializing EasyOCR: {e}. Please ensure necessary dependencies are installed.")
            # Fallback or raise error
            self.reader = None  # Indicate that reader is not available
            raise  # Re-raise to ensure the error is propagated if OCR is critical

    def process_image(self, image_path: str) -> str:
        """
        Processes an image file using OCR and returns the extracted text.
        Args:
            image_path (str): The full path to the image file.
        Returns:
            str: The concatenated text extracted from the image, or an empty string if OCR fails.
        Raises:
            FileNotFoundError: If the image_path does not exist.
            Exception: For other OCR processing errors.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found at: {image_path}")

        if self.reader is None:
            raise RuntimeError(
                "OCR reader not initialized. Cannot process image. Check previous initialization errors.")

        try:
            # Read the image using OpenCV. cv2.imread is generally robust.
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError(f"Could not read image file: {image_path}. Check file corruption or format.")

            # EasyOCR expects RGB for color images, and cv2.imread reads BGR.
            # Conversion is good practice if color information matters or if grayscale causes issues.
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            # Perform OCR
            results = self.reader.readtext(img_rgb)

            # Concatenate all detected text, ensuring each detection is on a new line
            extracted_text = "\n".join([text for (bbox, text, prob) in results])

            print(f"OCR processed image: {image_path}")
            print(f"Extracted text sample:\n{extracted_text[:200]}...")  # Print first 200 chars

            return extracted_text
        except Exception as e:
            print(f"Error during OCR processing of {image_path}: {e}")
            raise  # Re-raise to be caught by higher-level error handling

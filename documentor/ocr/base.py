"""
Base classes for working with OCR.

Defines interfaces for:
- Layout detection
- Text recognition
- Reading order building
- Table parsing
- Text extraction
- Formula extraction
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    pd = None  # type: ignore


class BaseLayoutDetector(ABC):
    """
    Base class for layout detection.
    
    Defines interface for determining document page structure.
    """
    
    @abstractmethod
    def detect_layout(
        self, 
        image: Image.Image, 
        origin_image: Optional[Image.Image] = None
    ) -> List[Dict[str, Any]]:
        """
        Detects page layout.
        
        Args:
            image: Page image (optimized/preprocessed)
            origin_image: Original image (optional, for post-processing)
            
        Returns:
            List[Dict[str, Any]]: List of layout elements with fields:
                - bbox: [x1, y1, x2, y2]
                - category: element type
                - text: element text (if available)
        """
        raise NotImplementedError
    
    def detect_layout_with_text(
        self, 
        image: Image.Image, 
        origin_image: Optional[Image.Image] = None
    ) -> List[Dict[str, Any]]:
        """
        Detects page layout with text content.
        
        Optional method for models that can return layout + text simultaneously.
        Default implementation calls detect_layout.
        
        Args:
            image: Page image (optimized/preprocessed)
            origin_image: Original image (optional, for post-processing)
            
        Returns:
            List[Dict[str, Any]]: List of layout elements with text content
        """
        return self.detect_layout(image, origin_image)


class BaseOCR(ABC):
    """
    Base class for text recognition.
    
    Defines interface for OCR image processing.
    """
    
    @abstractmethod
    def recognize_text(self, image: Image.Image) -> str:
        """
        Recognizes text from image.
        
        Args:
            image: Image for recognition
            
        Returns:
            str: Recognized text
        """
        raise NotImplementedError


class BaseReadingOrderBuilder(ABC):
    """
    Base class for building reading order.
    
    Defines interface for determining reading order of elements on a page.
    """
    
    @abstractmethod
    def build_reading_order(self, layout_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Builds reading order of elements.
        
        Args:
            layout_elements: List of layout elements
            
        Returns:
            List[Dict[str, Any]]: Elements in reading order
        """
        raise NotImplementedError


class BaseTableParser(ABC):
    """
    Base class for table parsing.
    
    Defines interface for parsing tables from images.
    """
    
    @abstractmethod
    def parse_table(
        self, 
        image: Image.Image, 
        bbox: List[float]
    ) -> Tuple[Optional[str], bool]:
        """
        Parse table from image.
        
        Args:
            image: Image containing the table
            bbox: Bounding box [x1, y1, x2, y2] of the table region
            
        Returns:
            Tuple containing:
                - HTML string or None
                - success: bool indicating if parsing was successful
        """
        raise NotImplementedError


class BaseTextExtractor(ABC):
    """
    Base class for text extraction.
    
    Defines interface for extracting text from images.
    """
    
    @abstractmethod
    def extract_text(
        self, 
        image: Image.Image, 
        bbox: List[float], 
        category: str
    ) -> str:
        """
        Extract text from image.
        
        Args:
            image: Image containing the text
            bbox: Bounding box [x1, y1, x2, y2] of the text region
            category: Category of the text element (Text, Title, Section-header, etc.)
            
        Returns:
            str: Extracted text
        """
        raise NotImplementedError


class BaseFormulaExtractor(ABC):
    """
    Base class for formula extraction.
    
    Defines interface for extracting formulas from images.
    """
    
    @abstractmethod
    def extract_formula(
        self, 
        image: Image.Image, 
        bbox: List[float]
    ) -> str:
        """
        Extract formula in LaTeX format from image.
        
        Args:
            image: Image containing the formula
            bbox: Bounding box [x1, y1, x2, y2] of the formula region
            
        Returns:
            str: Formula in LaTeX format
        """
        raise NotImplementedError

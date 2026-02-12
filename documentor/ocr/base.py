"""
Base classes for working with OCR.

Defines interfaces for:
- Layout detection
- Text recognition
- Reading order building
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from PIL import Image


class BaseLayoutDetector(ABC):
    """
    Base class for layout detection.
    
    Defines interface for determining document page structure.
    """
    
    @abstractmethod
    def detect_layout(self, image: Image.Image) -> List[Dict[str, Any]]:
        """
        Detects page layout.
        
        Args:
            image: Page image
            
        Returns:
            List[Dict[str, Any]]: List of layout elements with fields:
                - bbox: [x1, y1, x2, y2]
                - category: element type
                - text: element text (if available)
        """
        raise NotImplementedError


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

"""
Text extractor for Dots.OCR.

Wrapper class for extracting text from images using Dots.OCR API.
"""

import re
from typing import Any, Dict, List, Optional

from PIL import Image

from ..base import BaseTextExtractor
from .client import process_layout_detection
from .prompts import DOTS_OCR_PROMPTS


class DotsOCRTextExtractor(BaseTextExtractor):
    """
    Text extractor for Dots.OCR.
    
    Implements BaseTextExtractor interface for Dots.OCR API.
    """
    
    def __init__(self) -> None:
        """Initialize text extractor."""
        pass
    
    def extract_text(
        self, 
        image: Image.Image, 
        bbox: List[float], 
        category: str
    ) -> str:
        """
        Extract text from image using Dots OCR.
        
        Args:
            image: Image containing the text
            bbox: Bounding box [x1, y1, x2, y2] of the text region
            category: Category of the text element (Text, Title, Section-header, etc.)
        
        Returns:
            str: Extracted text
        """
        # Use prompt_layout_all_en to get text
        prompt = DOTS_OCR_PROMPTS.get("prompt_layout_all_en")
        
        layout_cells, _, success = process_layout_detection(
            image=image,
            origin_image=image,
            prompt=prompt,
        )
        
        if not success or layout_cells is None:
            return ""
        
        # Find element by bbox and category
        element = self._find_element_by_bbox_and_category(layout_cells, bbox, category)
        if not element:
            return ""
        
        text = element.get("text", "")
        
        # Clean markdown formatting (except for Formula)
        if category != "Formula":
            from .markdown_formatting import remove_markdown_formatting
            text = remove_markdown_formatting(text)
        
        return text.strip()
    
    def _find_element_by_bbox_and_category(
        self, 
        layout_cells: List[Dict[str, Any]], 
        bbox: List[float], 
        category: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find element by bbox and category.
        
        Args:
            layout_cells: List of layout elements from Dots OCR
            bbox: Target bounding box [x1, y1, x2, y2]
            category: Target category
        
        Returns:
            Element dict or None if not found
        """
        if len(bbox) < 4:
            return None
        
        target_x1, target_y1, target_x2, target_y2 = bbox[:4]
        target_area = (target_x2 - target_x1) * (target_y2 - target_y1)
        
        best_match = None
        best_overlap = 0.0
        
        for element in layout_cells:
            if element.get("category") != category:
                continue
            
            elem_bbox = element.get("bbox", [])
            if len(elem_bbox) < 4:
                continue
            
            elem_x1, elem_y1, elem_x2, elem_y2 = elem_bbox[:4]
            
            # Calculate intersection
            x1_i = max(target_x1, elem_x1)
            y1_i = max(target_y1, elem_y1)
            x2_i = min(target_x2, elem_x2)
            y2_i = min(target_y2, elem_y2)
            
            if x2_i <= x1_i or y2_i <= y1_i:
                continue
            
            intersection = (x2_i - x1_i) * (y2_i - y1_i)
            elem_area = (elem_x2 - elem_x1) * (elem_y2 - elem_y1)
            
            # Calculate overlap ratio
            overlap = intersection / min(target_area, elem_area) if min(target_area, elem_area) > 0 else 0.0
            
            if overlap > best_overlap and overlap > 0.5:  # 50% overlap threshold
                best_overlap = overlap
                best_match = element
        
        return best_match

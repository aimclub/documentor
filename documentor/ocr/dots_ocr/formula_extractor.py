"""
Formula extractor for Dots.OCR.

Wrapper class for extracting formulas from images using Dots.OCR API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PIL import Image

from ...base import BaseFormulaExtractor
from .client import process_layout_detection
from .prompts import DOTS_OCR_PROMPTS


class DotsOCRFormulaExtractor(BaseFormulaExtractor):
    """
    Formula extractor for Dots.OCR.
    
    Implements BaseFormulaExtractor interface for Dots.OCR API.
    """
    
    def __init__(self) -> None:
        """Initialize formula extractor."""
        pass
    
    def extract_formula(
        self, 
        image: Image.Image, 
        bbox: List[float]
    ) -> str:
        """
        Extract formula in LaTeX format from image using Dots OCR.
        
        Args:
            image: Image containing the formula
            bbox: Bounding box [x1, y1, x2, y2] of the formula region
        
        Returns:
            str: Formula in LaTeX format
        """
        # Use prompt_layout_all_en to get LaTeX formula
        prompt = DOTS_OCR_PROMPTS.get("prompt_layout_all_en")
        
        layout_cells, _, success = process_layout_detection(
            image=image,
            origin_image=image,
            prompt=prompt,
        )
        
        if not success or layout_cells is None:
            return ""
        
        # Find formula element by bbox
        formula_element = self._find_formula_by_bbox(layout_cells, bbox)
        if not formula_element:
            return ""
        
        # Extract LaTeX (do NOT clean markdown - LaTeX may contain *, **, _, __)
        formula_latex = formula_element.get("text", "").strip()
        return formula_latex
    
    def _find_formula_by_bbox(
        self, 
        layout_cells: List[Dict[str, Any]], 
        bbox: List[float]
    ) -> Optional[Dict[str, Any]]:
        """
        Find formula element by bbox.
        
        Args:
            layout_cells: List of layout elements from Dots OCR
            bbox: Target bounding box [x1, y1, x2, y2]
        
        Returns:
            Formula element dict or None if not found
        """
        if len(bbox) < 4:
            return None
        
        target_x1, target_y1, target_x2, target_y2 = bbox[:4]
        target_area = (target_x2 - target_x1) * (target_y2 - target_y1)
        
        best_match = None
        best_overlap = 0.0
        
        for element in layout_cells:
            if element.get("category") != "Formula":
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

"""
Table parser for Dots.OCR.

Wrapper class for parsing tables from images using Dots.OCR API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    pd = None  # type: ignore

from ..base import BaseTableParser
from .client import process_layout_detection
from .prompts import DOTS_OCR_PROMPTS
from .html_table_parser import parse_table_from_html


class DotsOCRTableParser(BaseTableParser):
    """
    Table parser for Dots.OCR.
    
    Implements BaseTableParser interface for Dots.OCR API.
    """
    
    def __init__(self) -> None:
        """Initialize table parser."""
        pass
    
    def parse_table(
        self, 
        image: Image.Image, 
        bbox: List[float]
    ) -> Tuple[Optional[Any], Optional[str], bool]:
        """
        Parse table from image using Dots OCR.
        
        Args:
            image: Image containing the table
            bbox: Bounding box [x1, y1, x2, y2] of the table region
        
        Returns:
            Tuple containing:
                - DataFrame or None (if pandas available)
                - HTML string or None
                - success: bool indicating if parsing was successful
        """
        # Use prompt_layout_all_en to get HTML table
        prompt = DOTS_OCR_PROMPTS.get("prompt_layout_all_en")
        
        layout_cells, raw_response, success = process_layout_detection(
            image=image,
            origin_image=image,
            prompt=prompt,
        )
        
        if not success or layout_cells is None:
            return None, None, False
        
        # Find table element by bbox
        table_element = self._find_table_by_bbox(layout_cells, bbox)
        if not table_element:
            return None, None, False
        
        # Extract HTML from text field
        table_html = table_element.get("text", "")
        if not table_html:
            return None, None, False
        
        # Parse HTML to DataFrame
        _, dataframe, parse_success = parse_table_from_html(
            table_html,
            method="dataframe",
        )
        
        if not parse_success:
            return None, table_html, False
        
        return dataframe, table_html, True
    
    def _find_table_by_bbox(
        self, 
        layout_cells: List[Dict[str, Any]], 
        bbox: List[float]
    ) -> Optional[Dict[str, Any]]:
        """
        Find table element by bbox proximity.
        
        Args:
            layout_cells: List of layout elements from Dots OCR
            bbox: Target bounding box [x1, y1, x2, y2]
        
        Returns:
            Table element dict or None if not found
        """
        if len(bbox) < 4:
            return None
        
        target_x1, target_y1, target_x2, target_y2 = bbox[:4]
        target_area = (target_x2 - target_x1) * (target_y2 - target_y1)
        
        best_match = None
        best_overlap = 0.0
        
        for element in layout_cells:
            if element.get("category") != "Table":
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

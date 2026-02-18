"""
Layout detector for Dots.OCR.

Wrapper class for layout detection using Dots.OCR API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PIL import Image

from ...base import BaseLayoutDetector
from .client import process_layout_detection
from .prompts import DOTS_OCR_PROMPTS


class DotsOCRLayoutDetector(BaseLayoutDetector):
    """
    Layout detector for Dots.OCR.
    
    Implements BaseLayoutDetector interface for Dots.OCR API.
    """
    
    def __init__(
        self, 
        use_direct_api: bool = True, 
        ocr_manager: Optional[Any] = None
    ) -> None:
        """
        Initialize detector.
        
        Args:
            use_direct_api: If True, uses direct API call. 
                          If False, uses DotsOCRManager (not implemented yet).
            ocr_manager: DotsOCRManager instance (for future use)
        """
        self.use_direct_api = use_direct_api
        self.ocr_manager = ocr_manager
    
    def detect_layout(
        self, 
        image: Image.Image, 
        origin_image: Optional[Image.Image] = None
    ) -> List[Dict[str, Any]]:
        """
        Detects page layout using prompt_layout_only_en.
        
        Args:
            image: Page image (already prepared via smart_resize)
            origin_image: Original image (for post_process_output)
        
        Returns:
            List[Dict[str, Any]]: List of layout elements with fields:
                - bbox: [x1, y1, x2, y2]
                - category: element type
        """
        if not self.use_direct_api and self.ocr_manager:
            # TODO: Implement DotsOCRManager path
            raise NotImplementedError("DotsOCRManager path not yet implemented")
        
        # Use default prompt_layout_only_en
        prompt = DOTS_OCR_PROMPTS.get("prompt_layout_only_en")
        
        layout_cells, raw_response, success = process_layout_detection(
            image=image,
            origin_image=origin_image,
            prompt=prompt,
        )
        
        if not success or layout_cells is None:
            raise RuntimeError(
                f"Layout detection failed: {raw_response[:200] if raw_response else 'None'}"
            )
        
        return layout_cells
    
    def detect_layout_with_text(
        self, 
        image: Image.Image, 
        origin_image: Optional[Image.Image] = None
    ) -> List[Dict[str, Any]]:
        """
        Detects page layout with text using prompt_layout_all_en.
        
        Args:
            image: Page image (already prepared via smart_resize)
            origin_image: Original image (for post_process_output)
        
        Returns:
            List[Dict[str, Any]]: List of layout elements with fields:
                - bbox: [x1, y1, x2, y2]
                - category: element type
                - text: element text (if available)
        """
        if not self.use_direct_api and self.ocr_manager:
            # TODO: Implement DotsOCRManager path
            raise NotImplementedError("DotsOCRManager path not yet implemented")
        
        # Use prompt_layout_all_en to get text
        prompt = DOTS_OCR_PROMPTS.get("prompt_layout_all_en")
        
        layout_cells, raw_response, success = process_layout_detection(
            image=image,
            origin_image=origin_image,
            prompt=prompt,
        )
        
        if not success or layout_cells is None:
            raise RuntimeError(
                f"Layout detection with text failed: {raw_response[:200] if raw_response else 'None'}"
            )
        
        return layout_cells

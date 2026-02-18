"""
Layout detection for PDF via Dots.OCR.

Contains classes for detecting PDF page structure
using Dots.OCR via DotsOCRManager or direct API call.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PIL import Image

from documentor.ocr.base import BaseLayoutDetector
from documentor.ocr.dots_ocr import DotsOCRLayoutDetector

# Lazy import to avoid circular dependencies
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from documentor.ocr.manager import DotsOCRManager, TaskStatus


class PdfLayoutDetector(BaseLayoutDetector):
    """
    Layout detector for PDF via Dots.OCR.
    
    Supports two modes:
    1. Via DotsOCRManager (async queue)
    2. Direct API call (synchronous, as in pdf_pipeline_dots_ocr.py)
    """
    
    def __init__(
        self,
        ocr_manager: Optional[Any] = None,
        use_direct_api: bool = True,
    ) -> None:
        """
        Initialize detector.
        
        Args:
            ocr_manager: DotsOCRManager instance. If None and use_direct_api=False, 
                        automatically created from .env.
            use_direct_api: If True, uses direct API call (as in pdf_pipeline_dots_ocr.py).
                          If False, uses DotsOCRManager.
        """
        self.use_direct_api = use_direct_api
        self.ocr_manager = ocr_manager
        
        # Create Dots OCR layout detector
        self.dots_detector = DotsOCRLayoutDetector(
            use_direct_api=use_direct_api,
            ocr_manager=ocr_manager
        )
        
        if use_direct_api:
            self._own_manager = False
        else:
            if ocr_manager is None:
                # Lazy import to avoid circular dependencies
                from documentor.ocr.manager import DotsOCRManager
                self.ocr_manager = DotsOCRManager(auto_load_models=True)
                self._own_manager = True
            else:
                self._own_manager = False
    
    def detect_layout(
        self,
        image: Image.Image,
        origin_image: Optional[Image.Image] = None,
    ) -> List[Dict[str, Any]]:
        """
        Detects page layout via Dots.OCR.
        
        Args:
            image: PDF page image (already prepared via smart_resize)
            origin_image: Original image (for post_process_output)
        
        Returns:
            List[Dict[str, Any]]: List of layout elements with fields:
                - bbox: [x1, y1, x2, y2]
                - category: element type
                - text: element text (if available)
        """
        if self.use_direct_api:
            # Use Dots OCR layout detector
            return self.dots_detector.detect_layout(image, origin_image)
        else:
            # Using DotsOCRManager (async queue)
            task_id = self.ocr_manager.submit_task(
                image=image,
                task_format="Layout",
                prompt_mode="prompt_layout_only_en"
            )
            
            # Wait for result
            from documentor.ocr.manager import TaskStatus
            task = self.ocr_manager.wait_for_task(task_id, timeout=300)
            
            if task.status != TaskStatus.COMPLETED:
                raise RuntimeError(f"Layout detection error: {task.error}")
            
            result = task.result
            
            # Normalize result to list of elements
            if isinstance(result, list):
                return result
            elif isinstance(result, dict):
                # If result is dict with 'elements' key
                if 'elements' in result:
                    return result['elements']
                # If result is single element
                return [result]
            else:
                raise ValueError(f"Unexpected result format: {type(result)}")
    
    def __enter__(self) -> PdfLayoutDetector:
        """Context manager support."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Cleanup on context manager exit."""
        if self._own_manager and self.ocr_manager is not None:
            self.ocr_manager.__exit__(exc_type, exc_val, exc_tb)

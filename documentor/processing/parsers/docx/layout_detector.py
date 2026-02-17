"""
DOCX layout detection processor.

Handles layout detection for DOCX documents using Dots OCR.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import fitz
from tqdm import tqdm

from ....utils.config_loader import ConfigLoader
from ....utils.pdf_text_extractor import PdfTextExtractorUtil
from ..pdf.ocr.dots_ocr_client import process_layout_detection
from ..pdf.ocr.page_renderer import PdfPageRenderer

logger = logging.getLogger(__name__)


class DocxLayoutDetector:
    """
    Processor for DOCX layout detection via OCR.
    
    Handles:
    - PDF page rendering
    - Layout detection via Dots OCR
    - Text extraction from PDF by bbox
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize layout detector.
        
        Args:
            config: Configuration dictionary.
        """
        self.config = config
        self.renderer: PdfPageRenderer = None

    def _get_config(self, key: str, default: Any = None) -> Any:
        """Gets value from configuration."""
        return ConfigLoader.get_config_value(self.config, key, default)

    def _initialize_renderer(self) -> None:
        """Initialize page renderer if not already initialized."""
        if self.renderer is None:
            render_scale = self._get_config("layout_detection.render_scale", 2.0)
            self.renderer = PdfPageRenderer(render_scale=render_scale)

    def detect_layout_for_all_pages(
        self, pdf_path: Path
    ) -> tuple[List[Dict[str, Any]], Dict[int, Any]]:
        """
        Performs layout detection for all PDF pages.

        Args:
            pdf_path: Path to PDF file (converted from DOCX).

        Returns:
            Tuple of (layout elements, page images dictionary).
        """
        self._initialize_renderer()
        
        pdf_doc = fitz.open(str(pdf_path))
        try:
            total_pages = len(pdf_doc)
            
            # Check if we should skip title page
            skip_title_page = self._get_config("processing.skip_title_page", False)
            start_page = 1 if skip_title_page else 0
            
            if skip_title_page and total_pages > 1:
                logger.info(f"Skipping title page (page 1), processing pages 2-{total_pages}")
            
            ocr_elements = []
            page_images = {}
            
            for page_num in tqdm(range(start_page, total_pages), desc="Processing PDF pages", unit="page", leave=False):
                page_image = self.renderer.render_page(pdf_path, page_num)
                if page_image is None:
                    continue
                
                page_images[page_num] = page_image
                
                try:
                    layout_cells, _, success = process_layout_detection(
                        image=page_image,
                        origin_image=page_image
                    )
                    
                    if success and layout_cells:
                        for element in layout_cells:
                            element["page_num"] = page_num
                            ocr_elements.append(element)
                except Exception:
                    continue
            
            return ocr_elements, page_images
        finally:
            pdf_doc.close()

    def extract_text_from_pdf_by_bbox(
        self, elements: List[Dict[str, Any]], pdf_doc: fitz.Document, render_scale: float
    ) -> List[Dict[str, Any]]:
        """
        Extracts text from PDF by bbox found via DOTS OCR, using PyMuPDF.
        
        Args:
            elements: List of OCR elements with bbox.
            pdf_doc: PyMuPDF document.
            render_scale: Render scale used for rendering.
        
        Returns:
            List of elements with extracted text.
        """
        results = []
        
        for element in tqdm(elements, desc="Extracting text from PDF", unit="element", leave=False):
            category = element.get("category", "")
            bbox = element.get("bbox", [])
            page_num = element.get("page_num", 0)
            
            if category not in ["Section-header", "Caption"]:
                continue
            
            if not bbox or len(bbox) < 4:
                continue
            
            if page_num >= len(pdf_doc):
                continue
            
            try:
                page = pdf_doc[page_num]
                text = PdfTextExtractorUtil.extract_text_by_bbox(page, bbox, render_scale)
                element["text"] = text
                results.append(element)
            except Exception as e:
                logger.warning(f"Error extracting text for element: {e}")
                element["text"] = ""
                results.append(element)
        
        return results

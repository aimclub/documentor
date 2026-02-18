"""
PDF layout detection processor.

Handles layout detection for PDF documents using Dots OCR.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from tqdm import tqdm

from ....utils.config_loader import ConfigLoader
from .ocr.layout_detector import PdfLayoutDetector
from .ocr.page_renderer import PdfPageRenderer

logger = logging.getLogger(__name__)


class PdfLayoutProcessor:
    """
    Processor for PDF layout detection.
    
    Handles:
    - Page rendering
    - Layout detection via OCR
    - Filtering unnecessary elements
    - Table reprocessing with full extraction
    """

    def __init__(
        self,
        ocr_manager: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
        layout_detector: Optional[Any] = None,
    ) -> None:
        """
        Initialize layout processor.
        
        Args:
            ocr_manager: DotsOCRManager instance for OCR processing.
            config: Configuration dictionary.
            layout_detector: Custom layout detector implementing BaseLayoutDetector.
                           If None, uses default Dots OCR layout detector.
        """
        self.ocr_manager = ocr_manager
        self.config = config or {}
        self.page_renderer: Optional[PdfPageRenderer] = None
        self.layout_detector: Optional[Any] = layout_detector
        self._custom_detector = layout_detector is not None

    def _get_config(self, key: str, default: Any = None) -> Any:
        """Gets value from configuration."""
        return ConfigLoader.get_config_value(self.config, key, default)

    def _initialize_renderer(self) -> None:
        """Initialize page renderer if not already initialized."""
        if self.page_renderer is None:
            render_scale = self._get_config("layout_detection.render_scale", 2.0)
            optimize_for_ocr = self._get_config("layout_detection.optimize_for_ocr", True)
            self.page_renderer = PdfPageRenderer(
                render_scale=render_scale,
                optimize_for_ocr=optimize_for_ocr,
            )

    def _initialize_detector(self) -> None:
        """Initialize layout detector if not already initialized."""
        if self.layout_detector is None:
            # Use custom detector if provided, otherwise create default
            if self._custom_detector:
                # Custom detector already set in __init__
                return
            
            use_direct_api = self._get_config("layout_detection.use_direct_api", True)
            
            if use_direct_api:
                ocr_manager = None
            else:
                ocr_manager = self.ocr_manager
                if ocr_manager is None:
                    raise RuntimeError(
                        "OCR processing unavailable: DotsOCRManager cannot be created. "
                        "Check settings in .env file"
                    )

            self.layout_detector = PdfLayoutDetector(
                ocr_manager=ocr_manager,
                use_direct_api=use_direct_api
            )

    def detect_layout_for_all_pages(
        self, source: str, use_text_extraction: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Performs layout detection for all PDF pages.

        Args:
            source: Path to PDF file.
            use_text_extraction: If True, uses prompt_layout_all_en to extract text, tables (HTML), and formulas.
                               If False, uses prompt_layout_only_en for layout only (text via PyMuPDF).

        Returns:
            List of layout elements with bbox, category, page_num fields.
            If use_text_extraction=True, elements also contain 'text' field from Dots OCR.
        """
        self._initialize_renderer()
        self._initialize_detector()
        
        pdf_path = Path(source)
        total_pages = self.page_renderer.get_page_count(pdf_path)
        all_layout_elements: List[Dict[str, Any]] = []
        
        # Check if we should skip title page
        skip_title_page = self._get_config("processing.skip_title_page", False)
        start_page = 1 if skip_title_page else 0
        
        if skip_title_page and total_pages > 1:
            logger.info(f"Skipping title page (page 1), processing pages 2-{total_pages}")
        else:
            logger.info(f"Starting layout detection for {total_pages} pages")
        
        for page_num in tqdm(range(start_page, total_pages), desc="Layout detection", unit="page"):
            try:
                original_image, optimized_image = self.page_renderer.render_page(
                    pdf_path, page_num, return_original=True
                )
                
                if use_text_extraction:
                    # For scanned PDFs: use detect_layout_with_text to get text, tables (HTML), and formulas
                    # Check if custom detector or default PdfLayoutDetector
                    if hasattr(self.layout_detector, 'dots_detector'):
                        # Default PdfLayoutDetector - use dots_detector
                        layout = self.layout_detector.dots_detector.detect_layout_with_text(
                            optimized_image, 
                            origin_image=original_image
                        )
                    else:
                        # Custom layout detector - use detect_layout_with_text if available
                        layout = self.layout_detector.detect_layout_with_text(
                            optimized_image,
                            origin_image=original_image
                        )
                else:
                    # For text-extractable PDFs: use prompt_layout_only_en for layout only (text via PyMuPDF)
                    layout = self.layout_detector.detect_layout(optimized_image, origin_image=original_image)
                
                # Add page number to each element
                for element in layout:
                    element["page_num"] = page_num
                    all_layout_elements.append(element)
                
                logger.debug(f"Layout detection for page {page_num + 1}/{total_pages}: found {len(layout)} elements")
            except Exception as e:
                logger.error(f"Error in layout detection for page {page_num + 1}: {e}")
                continue
        
        logger.info(f"Layout detection completed: total {len(all_layout_elements)} elements found")
        return all_layout_elements

    def reprocess_tables_with_all_en(
        self, source: str, layout_elements: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Re-processes pages with tables using prompt_layout_all_en to get HTML.
        
        For text-extractable PDFs: after initial layout detection with prompt_layout_only_en,
        this method identifies pages with tables and re-processes them with prompt_layout_all_en
        to get detailed HTML table content.
        
        Args:
            source: Path to PDF file.
            layout_elements: Initial layout elements from prompt_layout_only_en.
        
        Returns:
            Updated layout elements with HTML table content for table elements.
        """
        self._initialize_renderer()
        
        # Find pages with tables
        pages_with_tables = set()
        for element in layout_elements:
            if element.get("category") == "Table":
                page_num = element.get("page_num", 0)
                pages_with_tables.add(page_num)
        
        if not pages_with_tables:
            logger.debug("No tables found, skipping table reprocessing")
            return layout_elements
        
        logger.info(f"Re-processing {len(pages_with_tables)} pages with tables using prompt_layout_all_en")
        
        pdf_path = Path(source)
        updated_elements = []
        table_elements_by_page: Dict[int, List[Dict[str, Any]]] = {}
        
        # Group table elements by page
        for element in layout_elements:
            if element.get("category") == "Table":
                page_num = element.get("page_num", 0)
                if page_num not in table_elements_by_page:
                    table_elements_by_page[page_num] = []
                table_elements_by_page[page_num].append(element)
            else:
                updated_elements.append(element)
        
        # Re-process pages with tables using detect_layout_with_text
        for page_num in tqdm(pages_with_tables, desc="Re-processing tables", unit="page", leave=False):
            try:
                original_image, optimized_image = self.page_renderer.render_page(
                    pdf_path, page_num, return_original=True
                )
                
                # Process with detect_layout_with_text to get HTML tables
                try:
                    # Check if custom detector or default PdfLayoutDetector
                    if hasattr(self.layout_detector, 'dots_detector'):
                        # Default PdfLayoutDetector - use dots_detector
                        layout = self.layout_detector.dots_detector.detect_layout_with_text(
                            optimized_image,
                            origin_image=original_image
                        )
                    else:
                        # Custom layout detector - use detect_layout_with_text if available
                        layout = self.layout_detector.detect_layout_with_text(
                            optimized_image,
                            origin_image=original_image
                        )
                except Exception as e:
                    logger.warning(f"Table reprocessing failed for page {page_num + 1}: {e}")
                    # Keep original elements
                    updated_elements.extend(table_elements_by_page.get(page_num, []))
                    continue
                
                # Find table elements in new layout and update original ones
                new_table_elements = [e for e in layout if e.get("category") == "Table"]
                original_table_elements = table_elements_by_page.get(page_num, [])
                
                # Match tables by bbox proximity
                for orig_table in original_table_elements:
                    orig_bbox = orig_table.get("bbox", [])
                    best_match = None
                    best_overlap = 0.0
                    
                    for new_table in new_table_elements:
                        new_bbox = new_table.get("bbox", [])
                        
                        # Calculate overlap
                        if len(orig_bbox) >= 4 and len(new_bbox) >= 4:
                            overlap = self._calculate_bbox_overlap(orig_bbox, new_bbox)
                            if overlap > best_overlap and overlap > 0.5:  # 50% overlap threshold
                                best_overlap = overlap
                                best_match = new_table
                    
                    if best_match:
                        # Update original table with HTML from new layout
                        orig_table["table_html"] = best_match.get("text", "")
                        orig_table["text"] = best_match.get("text", "")
                        logger.debug(f"Updated table on page {page_num + 1} with HTML content")
                    else:
                        logger.warning(f"Could not match table on page {page_num + 1}")
                    
                    updated_elements.append(orig_table)
            
            except Exception as e:
                logger.error(f"Error reprocessing tables for page {page_num + 1}: {e}")
                # Keep original elements
                updated_elements.extend(table_elements_by_page.get(page_num, []))
                continue
        
        return updated_elements

    def _calculate_bbox_overlap(self, bbox1: List[float], bbox2: List[float]) -> float:
        """Calculate overlap ratio between two bounding boxes."""
        if len(bbox1) < 4 or len(bbox2) < 4:
            return 0.0
        
        x1_1, y1_1, x2_1, y2_1 = bbox1
        x1_2, y1_2, x2_2, y2_2 = bbox2
        
        # Calculate intersection
        x1_i = max(x1_1, x1_2)
        y1_i = max(y1_1, y1_2)
        x2_i = min(x2_1, x2_2)
        y2_i = min(y2_1, y2_2)
        
        if x2_i <= x1_i or y2_i <= y1_i:
            return 0.0
        
        intersection = (x2_i - x1_i) * (y2_i - y1_i)
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection
        
        if union == 0:
            return 0.0
        
        return intersection / union

    def filter_layout_elements(self, layout_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filters unnecessary elements (Page-header, Page-footer).
        
        Args:
            layout_elements: List of layout elements.
        
        Returns:
            Filtered list of layout elements.
        """
        remove_page_headers = self._get_config("filtering.remove_page_headers", True)
        remove_page_footers = self._get_config("filtering.remove_page_footers", True)
        
        filtered = []
        for element in layout_elements:
            category = element.get("category", "")
            
            if remove_page_headers and category == "Page-header":
                continue
            if remove_page_footers and category == "Page-footer":
                continue
            
            filtered.append(element)
        
        return filtered

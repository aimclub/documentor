"""
PDF layout detection processor.

Handles layout detection for PDF documents using Dots OCR.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from tqdm import tqdm
from PIL import Image

from documentor.config.loader import ConfigLoader
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
                    if self.layout_detector is None:
                        raise RuntimeError("Layout detector not initialized")
                    
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
                    if self.layout_detector is None:
                        raise RuntimeError("Layout detector not initialized")
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
        self._initialize_detector()  # Ensure detector is initialized
        
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
        
        # Get timeout for table reprocessing (use increased timeout for complex table processing)
        # Load OCR config separately since self.config is for pdf_parser, not ocr_config
        from documentor.ocr.dots_ocr.client import _get_config_value
        default_timeout = _get_config_value(
            "dots_ocr.recognition.timeout",
            "DOTS_OCR_TIMEOUT",
            120
        )
        table_timeout = _get_config_value(
            "dots_ocr.recognition.table_reprocessing_timeout",
            None,  # No env var for this, use config or default
            default_timeout * 2  # Default: 2x the base timeout
        )
        logger.debug(f"Using timeout {table_timeout}s for table reprocessing (default: {default_timeout}s)")
        
        # Note: We create full-page images with only the table visible (rest is white)
        # This is because the model is trained on full A4 page scans
        
        # Count total tables for progress bar
        total_tables = sum(len(table_elements_by_page.get(page_num, [])) for page_num in pages_with_tables)
        
        # Create progress bar for all tables
        pbar = tqdm(total=total_tables, desc="Re-processing tables", unit="table", leave=False)
        
        # Process each table individually by cropping it from the page
        # This is much faster as we only send the table image, not the entire page
        for page_num in pages_with_tables:
            original_table_elements = table_elements_by_page.get(page_num, [])
            if not original_table_elements:
                continue
            
            try:
                # Render page once
                original_image, optimized_image = self.page_renderer.render_page(
                    pdf_path, page_num, return_original=True
                )
                
                # Process each table on this page individually
                for orig_table in original_table_elements:
                    orig_bbox = orig_table.get("bbox", [])
                    
                    if len(orig_bbox) < 4:
                        logger.warning(f"Table on page {page_num + 1} has invalid bbox, skipping")
                        updated_elements.append(orig_table)
                        pbar.update(1)
                        continue
                    
                    # Extract table bbox coordinates
                    x1, y1, x2, y2 = orig_bbox
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                    
                    # Get full page dimensions
                    img_width, img_height = optimized_image.size
                    
                    # Crop table image from optimized page image
                    table_cropped = optimized_image.crop((x1, y1, x2, y2))
                    table_original_cropped = original_image.crop((x1, y1, x2, y2))
                    
                    # Create a new full-page-sized image with white background
                    # This is important because the model is trained on full A4 page scans
                    table_image = Image.new('RGB', (img_width, img_height), color='white')
                    table_original_image = Image.new('RGB', (img_width, img_height), color='white')
                    
                    # Paste the cropped table into the full-page image at its original position
                    table_image.paste(table_cropped, (x1, y1))
                    table_original_image.paste(table_original_cropped, (x1, y1))
                    
                    # Process only the cropped table image
                    try:
                        if self.layout_detector is None:
                            raise RuntimeError("Layout detector not initialized")
                        
                        # Check if custom detector or default PdfLayoutDetector
                        if hasattr(self.layout_detector, 'dots_detector'):
                            # Default PdfLayoutDetector - use dots_detector with increased timeout
                            layout = self.layout_detector.dots_detector.detect_layout_with_text(
                                table_image,
                                origin_image=table_original_image,
                                timeout=table_timeout
                            )
                        else:
                            # Custom layout detector - use detect_layout_with_text if available
                            layout = self.layout_detector.detect_layout_with_text(
                                table_image,
                                origin_image=table_original_image,
                                timeout=table_timeout
                            )
                    except Exception as e:
                        logger.warning(f"Table reprocessing failed for table on page {page_num + 1}: {e}")
                        # Keep original element without HTML
                        updated_elements.append(orig_table)
                        pbar.update(1)
                        continue
                    
                    # Find table element in result (should be the only one or the largest one)
                    table_elements = [e for e in layout if e.get("category") == "Table"]
                    
                    if table_elements:
                        # Take the first/largest table (should be the only one since we cropped just the table)
                        best_match = table_elements[0]
                        if len(table_elements) > 1:
                            # If multiple tables found, take the largest one
                            best_match = max(table_elements, key=lambda t: (
                                (t.get("bbox", [2])[2] - t.get("bbox", [0, 0, 0, 0])[0]) *
                                (t.get("bbox", [3])[3] - t.get("bbox", [0, 0, 0, 0])[1])
                                if len(t.get("bbox", [])) >= 4 else 0
                            ))
                        
                        # Update original table with HTML from cropped image result
                        # Note: bbox in result is relative to cropped image, but we don't need it
                        orig_table["table_html"] = best_match.get("text", "")
                        orig_table["text"] = best_match.get("text", "")
                        logger.debug(f"Updated table on page {page_num + 1} with HTML content (cropped image)")
                    else:
                        logger.warning(f"No table found in cropped image for page {page_num + 1}")
                        # Keep original element without HTML
                    
                    # Add table to updated elements
                    updated_elements.append(orig_table)
                    # Update progress bar
                    pbar.update(1)
            
            except Exception as e:
                logger.error(f"Error reprocessing tables for page {page_num + 1}: {e}")
                # Keep original elements and update progress for all failed tables
                for failed_table in original_table_elements:
                    updated_elements.append(failed_table)
                    pbar.update(1)
                continue
        
        # Close progress bar
        pbar.close()
        
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

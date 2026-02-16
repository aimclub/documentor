"""
Parser for PDF documents.

Supports layout-based approach:
- Layout detection via Dots.OCR for all pages
- Building hierarchy from Section-header
- Filtering unnecessary elements (Page-header, side text)
- Text extraction via PyMuPDF by coordinates
- Merging close text blocks
- Table parsing via Qwen2.5
- Storing images in metadata
"""

from __future__ import annotations

import logging
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz
import pandas as pd
import yaml
from langchain_core.documents import Document
from PIL import Image
from tqdm import tqdm

# URL pattern for extracting links from text
URL_PATTERN = re.compile(
    r'(?:https?://|www\.|ftp://)[^\s<>"{}|\\^`\[\]]+[^\s<>"{}|\\^`\[\].,;:!?]',
    re.IGNORECASE
)

from ....domain import DocumentFormat, Element, ElementType, ParsedDocument
from ....exceptions import ParsingError
from ..base import BaseParser
from .ocr.layout_detector import PdfLayoutDetector
from .ocr.page_renderer import PdfPageRenderer
from .ocr.qwen_table_parser import (
    parse_table_with_qwen,
    detect_merged_tables,
    markdown_to_dataframe,
)
from .ocr.qwen_ocr import ocr_text_with_qwen


logger = logging.getLogger(__name__)


class PdfParser(BaseParser):
    """
    Parser for PDF documents.

    Uses layout-based approach:
    - Layout detection via Dots.OCR for all pages
    - Building hierarchy from Section-header
    - Filtering unnecessary elements
    - Text extraction via PyMuPDF by coordinates
    - Merging close text blocks
    - Table parsing via Qwen2.5
    """

    format = DocumentFormat.PDF

    def __init__(self, ocr_manager: Optional[Any] = None) -> None:
        """
        Initialize parser.
        
        Args:
            ocr_manager: DotsOCRManager instance for OCR processing. 
                        If None, automatically created from .env when needed.
        """
        super().__init__()
        self.ocr_manager = ocr_manager
        self.layout_detector: Optional[PdfLayoutDetector] = None
        self.page_renderer: Optional[PdfPageRenderer] = None
        self._config: Optional[Dict[str, Any]] = None
        self._load_config()
    
    def _load_config(self) -> None:
        """Loads configuration from config.yaml."""
        config_path = Path(__file__).parent.parent.parent.parent / "config" / "config.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                self._config = config.get("pdf_parser", {})
        else:
            self._config = {}
            logger.warning(f"Configuration file not found: {config_path}, using default values")

    def _get_config(self, key: str, default: Any = None) -> Any:
        """Gets value from configuration."""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value if value is not None else default
    
    def _get_ocr_manager(self) -> Optional[Any]:
        """
        Gets OCR manager, creating it if necessary.
        
        Returns:
            DotsOCRManager or None if .env is not configured
        """
        if self.ocr_manager is None:
            try:
                from ....ocr.manager import DotsOCRManager
                self.ocr_manager = DotsOCRManager(auto_load_models=True)
                logger.debug("DotsOCRManager automatically created from .env")
            except Exception as e:
                logger.warning(f"Failed to create DotsOCRManager from .env: {e}")
                return None
        return self.ocr_manager

    def parse(self, document: Document) -> ParsedDocument:
        """
        Parse PDF document using layout-based approach.

        Process:
        1. Check extractable text
        2. Layout detection via Dots.OCR for all pages
        3. Building hierarchy from Section-header
        4. Filtering unnecessary elements
        5. Text extraction via PyMuPDF by coordinates
        6. Merging close text blocks
        7. Creating elements and building hierarchy
        8. Storing images in metadata
        9. Table parsing via Qwen2.5

        Args:
            document: LangChain Document with PDF content.

        Returns:
            ParsedDocument: Structured document representation.

        Raises:
            ValidationError: If input data is invalid.
            UnsupportedFormatError: If document format is not supported.
            ParsingError: If parsing error occurred.
        """
        self._validate_input(document)

        source = self.get_source(document)
        self._log_parsing_start(source)

        try:
            # Check if text is extractable
            is_text_extractable = self._is_text_extractable(source)
            
            if not is_text_extractable:
                logger.warning(
                    f"Text cannot be extracted from PDF, using layout-based approach (source: {source})"
                )
            
            # Layout-based approach (always use, even if text is extractable)
            # Step 1: Layout Detection for all pages
            layout_elements = self._detect_layout_for_all_pages(source)
            
            # Step 2: Filtering unnecessary elements
            logger.info("Step 2: Filtering elements...")
            filtered_elements = self._filter_layout_elements(layout_elements)
            logger.info(f"Filtered: {len(layout_elements)} -> {len(filtered_elements)} elements")
            
            # Step 3: Header level analysis (determine levels first)
            logger.info("Step 3: Analyzing header levels...")
            analyzed_elements = self._analyze_header_levels_from_elements(filtered_elements, source)
            logger.info(f"Analyzed headers: {len([e for e in analyzed_elements if e.get('category') == 'Section-header'])}")
            
            # Step 4: Building hierarchy from Section-header (with levels)
            logger.info("Step 4: Building hierarchy...")
            hierarchy = self._build_hierarchy_from_section_headers(analyzed_elements)
            logger.info(f"Built sections: {len(hierarchy)}")
            
            # Step 5: Text extraction via PyMuPDF or OCR
            # For scanned PDFs use OCR via Qwen2.5
            logger.info("Step 5: Extracting text...")
            text_elements = self._extract_text_by_bboxes(
                source, analyzed_elements, use_ocr=not is_text_extractable
            )
            logger.info(f"Extracted text elements: {len(text_elements)}")
            
            # Step 6: Merging consecutive Text elements
            logger.info("Step 6: Merging text blocks...")
            merged_text_elements = self._merge_nearby_text_blocks(text_elements, max_chunk_size=3000)
            logger.info(f"Merged: {len(text_elements)} -> {len(merged_text_elements)} elements")
            
            # Step 7: Creating elements from hierarchy
            logger.info("Step 7: Creating elements from hierarchy...")
            elements = self._create_elements_from_hierarchy(hierarchy, merged_text_elements, analyzed_elements, source)
            logger.info(f"Created elements: {len(elements)}")
            
            # Step 8: Storing images in metadata
            logger.info("Step 8: Storing images in metadata...")
            elements = self._store_images_in_metadata(elements, source)
            logger.info("Images stored")
            
            # Step 9: Table parsing via Qwen2.5
            logger.info("Step 9: Parsing tables...")
            elements = self._parse_tables_with_qwen(elements, source)
            logger.info("Tables processed")
            
            # Create ParsedDocument
            parsed_document = ParsedDocument(
                source=source,
                format=self.format,
                elements=elements,
                metadata={
                    "parser": "pdf",
                    "status": "completed",
                    "processing_method": "layout_based",
                    "total_pages": self._get_page_count(source),
                    "elements_count": len(elements),
                    "headers_count": len([e for e in elements if e.type.name.startswith("HEADER")]),
                    "tables_count": len([e for e in elements if e.type == ElementType.TABLE]),
                    "images_count": len([e for e in elements if e.type == ElementType.IMAGE]),
                },
            )

            self._validate_parsed_document(parsed_document)
            self._log_parsing_end(source, len(elements))

            return parsed_document

        except Exception as e:
            error_msg = f"Error parsing PDF document (source: {source})"
            logger.error(f"{error_msg}. Original error: {e}")
            raise ParsingError(error_msg, source=source, original_error=e) from e

    def _is_text_extractable(self, source: str) -> bool:
        """
        Determines if text can be extracted from PDF.

        Args:
            source: Path to PDF file.

        Returns:
            True if text can be extracted, False otherwise.
        """
        try:
            pdf_document = fitz.open(source)
            try:
                # Check first page
                if len(pdf_document) == 0:
                    return False
                
                page = pdf_document.load_page(0)
                text = page.get_text("text")
                
                return len(text.strip()) >= 100
            finally:
                pdf_document.close()
        except Exception as e:
            logger.warning(f"Error checking extractable text: {e}")
            return False

    def _get_page_count(self, source: str) -> int:
        """Returns number of pages in PDF."""
        pdf_document = fitz.open(source)
        try:
            return len(pdf_document)
        finally:
            pdf_document.close()

    def _detect_layout_for_all_pages(self, source: str) -> List[Dict[str, Any]]:
        """
        Performs layout detection for all PDF pages.

        Args:
            source: Path to PDF file.

        Returns:
            List of layout elements with bbox, category, page_num fields.
        """
        if self.page_renderer is None:
            render_scale = self._get_config("layout_detection.render_scale", 2.0)
            optimize_for_ocr = self._get_config("layout_detection.optimize_for_ocr", True)
            self.page_renderer = PdfPageRenderer(
                render_scale=render_scale,
                optimize_for_ocr=optimize_for_ocr,
            )
        
        if self.layout_detector is None:
            use_direct_api = self._get_config("layout_detection.use_direct_api", True)
            
            if use_direct_api:
                # When using direct API, manager is not needed
                ocr_manager = None
            else:
                # When using DotsOCRManager, manager is needed
                ocr_manager = self._get_ocr_manager()
                if ocr_manager is None:
                    raise RuntimeError(
                        "OCR processing unavailable: DotsOCRManager cannot be created. "
                        "Check settings in .env file"
                    )

            self.layout_detector = PdfLayoutDetector(ocr_manager=ocr_manager, use_direct_api=use_direct_api)
        
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

    def _filter_layout_elements(self, layout_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filters unnecessary elements (Page-header, Page-footer, side text).

        Args:
            layout_elements: List of layout elements.

        Returns:
            Filtered list of elements.
        """
        filtered: List[Dict[str, Any]] = []
        
        remove_page_headers = self._get_config("filtering.remove_page_headers", True)
        remove_page_footers = self._get_config("filtering.remove_page_footers", True)
        
        for element in layout_elements:
            category = element.get("category", "")
            
            # Remove Page-header and Page-footer
            if remove_page_headers and category == "Page-header":
                continue
            if remove_page_footers and category == "Page-footer":
                continue
            
            filtered.append(element)
        
        logger.debug(f"Filtering: {len(layout_elements)} -> {len(filtered)} elements")
        return filtered

    def _build_hierarchy_from_section_headers(
        self, layout_elements: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Builds element hierarchy, grouping them by Section-header.

        Args:
            layout_elements: List of layout elements.

        Returns:
            List of sections with headers and child elements.
        """
        # Sort elements by page and Y coordinate
        sorted_elements = sorted(
            layout_elements,
            key=lambda e: (e.get("page_num", 0), e.get("bbox", [1, 0])[1] if len(e.get("bbox", [])) >= 2 else 0)
        )
        
        sections: List[Dict[str, Any]] = []
        current_section: Optional[Dict[str, Any]] = None
        
        for element in sorted_elements:
            category = element.get("category", "")
            
            if category == "Section-header":
                # Save previous section
                if current_section is not None:
                    sections.append(current_section)
                
                # Create new section
                current_section = {
                    "header": element,
                    "children": [],
                }
            else:
                # Add element to current section
                if current_section is not None:
                    current_section["children"].append(element)
                else:
                    # Elements before first header - create section without header
                    current_section = {
                        "header": None,
                        "children": [element],
                    }
        
        # Add last section
        if current_section is not None:
            sections.append(current_section)
        
        logger.debug(f"Hierarchy built: {len(sections)} sections")
        return sections

    def _analyze_header_levels_from_elements(
        self, layout_elements: List[Dict[str, Any]], source: str
    ) -> List[Dict[str, Any]]:
        """
        Analyzes header levels from element list (before building hierarchy).
        
        Considers context: if there is a header with numbering (e.g., "1.2"),
        following headers without numbering get level + 1.

        Args:
            layout_elements: List of layout elements.
            source: Path to PDF file.

        Returns:
            List of elements with determined header levels.
        """
        pdf_document = fitz.open(source)
        try:
            analyzed_elements: List[Dict[str, Any]] = []
            render_scale = self._get_config("layout_detection.render_scale", 2.0)
            
            # Last header level with explicit numbering
            last_numbered_level: Optional[int] = None
            # History of previous headers for font size comparison
            previous_headers: List[Dict[str, Any]] = []  # {level, font_size, page_num}
            
            for element in layout_elements:
                category = element.get("category", "")
                
                if category == "Section-header":
                    # Extract header text via PyMuPDF
                    bbox = element.get("bbox", [])
                    page_num = element.get("page_num", 0)
                    
                    if len(bbox) >= 4 and page_num < len(pdf_document):
                        try:
                            page = pdf_document.load_page(page_num)
                            # Convert coordinates to original PDF scale
                            x1, y1, x2, y2 = (
                                bbox[0] / render_scale,
                                bbox[1] / render_scale,
                                bbox[2] / render_scale,
                                bbox[3] / render_scale,
                            )
                            rect = fitz.Rect(x1, y1, x2, y2)
                            
                            # Try get_textbox first - more accurate method
                            text = page.get_textbox(rect).strip()
                            
                            # If failed, use fallback
                            if not text or len(text) < 2:
                                text = page.get_text("text", clip=rect).strip()
                            
                            # Get font size for comparison
                            font_size = self._get_font_size(page, rect)
                            
                            # Determine header level
                            level = self._determine_header_level(
                                text, element, page, rect, last_numbered_level, previous_headers, font_size
                            )
                            
                            # If header has explicit numbering, update last_numbered_level
                            if self._has_explicit_numbering(text):
                                last_numbered_level = level
                            
                            # Save header info for comparison with subsequent headers
                            previous_headers.append({
                                "level": level,
                                "font_size": font_size,
                                "page_num": page_num,
                            })
                            
                            element_type = getattr(ElementType, f"HEADER_{level}", ElementType.HEADER_1)
                            
                            element["text"] = text
                            element["level"] = level
                            element["element_type"] = element_type
                        except Exception as e:
                            logger.warning(f"Error analyzing header: {e}")
                            element["level"] = 1
                            element["element_type"] = ElementType.HEADER_1
                            previous_headers.append({
                                "level": 1,
                                "font_size": None,
                                "page_num": page_num,
                            })
                    else:
                        element["level"] = 1
                        element["element_type"] = ElementType.HEADER_1
                        previous_headers.append({
                            "level": 1,
                            "font_size": None,
                            "page_num": page_num,
                        })
                
                analyzed_elements.append(element)
            
            return analyzed_elements
        finally:
            pdf_document.close()

    def _analyze_header_levels(
        self, hierarchy: List[Dict[str, Any]], source: str
    ) -> List[Dict[str, Any]]:
        """
        Analyzes header levels in already built hierarchy (legacy method).

        Args:
            hierarchy: List of sections with headers.
            source: Path to PDF file.

        Returns:
            List of sections with determined header levels.
        """
        # If headers are already analyzed, just return hierarchy
        for section in hierarchy:
            header = section.get("header")
            if header is not None and "level" not in header:
                # Header not analyzed - use old logic
                pdf_document = fitz.open(source)
                try:
                    bbox = header.get("bbox", [])
                    page_num = header.get("page_num", 0)
                    
                    if len(bbox) >= 4 and page_num < len(pdf_document):
                        try:
                            page = pdf_document.load_page(page_num)
                            render_scale = self._get_config("layout_detection.render_scale", 2.0)
                            x1, y1, x2, y2 = (
                                bbox[0] / render_scale,
                                bbox[1] / render_scale,
                                bbox[2] / render_scale,
                                bbox[3] / render_scale,
                            )
                            rect = fitz.Rect(x1, y1, x2, y2)
                            
                            # Try get_textbox first - more accurate method
                            text = page.get_textbox(rect).strip()
                            
                            # If failed, use fallback
                            if not text or len(text) < 2:
                                text = page.get_text("text", clip=rect).strip()
                            
                            level = self._determine_header_level(text, header, page, rect, None, None, None)
                            element_type = getattr(ElementType, f"HEADER_{level}", ElementType.HEADER_1)
                            
                            header["text"] = text
                            header["level"] = level
                            header["element_type"] = element_type
                        except Exception as e:
                            logger.warning(f"Error analyzing header: {e}")
                            header["level"] = 1
                            header["element_type"] = ElementType.HEADER_1
                    else:
                        header["level"] = 1
                        header["element_type"] = ElementType.HEADER_1
                finally:
                    pdf_document.close()
        
        return hierarchy

    def _has_explicit_numbering(self, text: str) -> bool:
        """
        Checks if header has explicit numbering (digits, letters, etc.).

        Args:
            text: Header text.

        Returns:
            True if header has explicit numbering.
        """
        # Check various numbering patterns
        patterns = [
            r'^\d+\s+',  # "1 ", "2 "
            r'^\d+\.\d+\s+',  # "1.1 ", "1.2 "
            r'^\d+\.\d+\.\d+\s+',  # "1.1.1 ", "1.1.2 "
            r'^[A-Z]\.\s+',  # "A. ", "B. "
            r'^[a-z]\.\s+',  # "a. ", "b. "
            r'^\([A-Z]\)\s+',  # "(A) ", "(B) "
            r'^\([a-z]\)\s+',  # "(a) ", "(b) "
            r'^[IVX]+\.\s+',  # "I. ", "II. ", "III. "
            r'^[ivx]+\.\s+',  # "i. ", "ii. ", "iii. "
        ]
        
        for pattern in patterns:
            if re.match(pattern, text):
                return True
        
        return False

    def _get_font_size(self, page: fitz.Page, rect: fitz.Rect) -> Optional[float]:
        """
        Extracts maximum font size from header area.

        Args:
            page: PDF page.
            rect: Header rectangle.

        Returns:
            Maximum font size or None if cannot be determined.
        """
        try:
            text_dict = page.get_text("dict", clip=rect)
            blocks = text_dict.get("blocks", [])
            
            font_sizes = []
            for block in blocks:
                if block.get("type") == 0:  # Text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            font_size = span.get("size", 0)
                            if font_size > 0:
                                font_sizes.append(font_size)
            
            if font_sizes:
                return max(font_sizes)
            return None
        except Exception:
            return None

    def _determine_header_level(
        self,
        text: str,
        header: Dict[str, Any],
        page: fitz.Page,
        rect: fitz.Rect,
        last_numbered_level: Optional[int] = None,
        previous_headers: Optional[List[Dict[str, Any]]] = None,
        font_size: Optional[float] = None,
    ) -> int:
        """
        Determines header level based on text and font size.
        
        If header has no explicit numbering and last_numbered_level exists,
        returns last_numbered_level + 1.
        
        If no numbering, compares font size with previous headers.

        Args:
            text: Header text.
            header: Dictionary with header information.
            page: PDF page.
            rect: Header rectangle.
            last_numbered_level: Level of last header with explicit numbering.
            previous_headers: List of previous headers for font size comparison.
            font_size: Current header font size.

        Returns:
            Header level (1-6).
        """
        # Numbering analysis
        # Headers like "1", "2", "3" -> HEADER_1
        if re.match(r'^\d+\s+[A-Z]', text):
            return 1
        # Headers like "1.1", "1.2" -> HEADER_2
        if re.match(r'^\d+\.\d+\s+', text):
            return 2
        # Headers like "1.1.1", "1.1.2" -> HEADER_3
        if re.match(r'^\d+\.\d+\.\d+\s+', text):
            return 3
        # Headers like "1.1.1.1" -> HEADER_4
        if re.match(r'^\d+\.\d+\.\d+\.\d+\s+', text):
            return 4
        
        # If header has no explicit numbering but has context with numbering
        if last_numbered_level is not None:
            # Return level + 1 from last numbered header
            return min(last_numbered_level + 1, 6)  # Limit maximum to 6
        
        # If no numbering, compare font size with previous headers
        if font_size is not None:
            if previous_headers:
                # Find previous headers with known font size
                previous_with_font = [
                    h for h in previous_headers
                    if h.get("font_size") is not None
                ]
                
                if previous_with_font:
                    # Take last header with known font size
                    last_header = previous_with_font[-1]
                    last_font_size = last_header.get("font_size")
                    last_level = last_header.get("level", 1)
                    
                    # Compare font sizes
                    # If font is significantly larger (>= 2pt difference) - higher level
                    if font_size >= last_font_size + 2:
                        return max(1, last_level - 1)
                    # If font is significantly smaller (>= 2pt difference) - lower level
                    elif font_size <= last_font_size - 2:
                        return min(6, last_level + 1)
                    # If size is approximately the same - same level
                    else:
                        return last_level
            
            # If no previous headers for comparison, use absolute values
            # Font >= 16pt -> usually HEADER_1 or HEADER_2
            if font_size >= 16:
                return 1
            # Font 12-16pt -> usually HEADER_2 or HEADER_3
            elif font_size >= 12:
                return 2
            # Font < 12pt -> usually HEADER_3
            else:
                return 3
        
        # Default HEADER_1
        return 1

    def _extract_text_by_bboxes(
        self, source: str, layout_elements: List[Dict[str, Any]], use_ocr: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Extracts text via PyMuPDF by coordinates from layout elements.
        For scanned PDFs (use_ocr=True) uses Qwen2.5 OCR.

        Args:
            source: Path to PDF file.
            layout_elements: List of layout elements with bbox.
            use_ocr: If True, uses OCR via Qwen2.5 instead of PyMuPDF.

        Returns:
            List of elements with extracted text.
        """
        pdf_document = fitz.open(source)
        try:
            text_elements: List[Dict[str, Any]] = []
            render_scale = self._get_config("layout_detection.render_scale", 2.0)
            
            # For OCR need to store original page images
            page_images: Dict[int, Image.Image] = {}
            
            if use_ocr:
                logger.info("Starting OCR processing: rendering pages...")
                # Render all pages in advance for OCR
                if self.page_renderer is None:
                    self.page_renderer = PdfPageRenderer(
                        render_scale=render_scale,
                        optimize_for_ocr=False,  # Don't apply smart_resize for original images
                    )
                
                pdf_path = Path(source)
                # Check if we should skip title page
                skip_title_page = self._get_config("processing.skip_title_page", False)
                start_page = 1 if skip_title_page else 0
                
                # Render pages that might be needed (all pages, as elements may reference any page)
                for page_num in tqdm(range(len(pdf_document)), desc="Rendering pages for OCR", unit="page", leave=False):
                    original_image, _ = self.page_renderer.render_page(
                        pdf_path, page_num, return_original=True
                    )
                    page_images[page_num] = original_image
                
                # Count elements for OCR
                ocr_elements = [
                    e for e in layout_elements 
                    if e.get("category", "") in ["Text", "Section-header", "Title", "Caption"]
                    and e.get("category", "") != "Picture"
                ]
                logger.info(f"Found {len(ocr_elements)} elements for OCR processing")
            
            for element in tqdm(layout_elements, desc="Extracting text", unit="element", disable=not use_ocr, leave=False):
                category = element.get("category", "")
                bbox = element.get("bbox", [])
                page_num = element.get("page_num", 0)
                
                # Skip Picture - don't do OCR for images
                if category == "Picture":
                    text_elements.append(element)
                    continue
                
                # Extract text only for text elements
                if category not in ["Text", "Section-header", "Title", "Caption"]:
                    text_elements.append(element)
                    continue
                
                if len(bbox) >= 4 and page_num < len(pdf_document):
                    try:
                        if use_ocr:
                            # Use OCR via Qwen2.5
                            if page_num not in page_images:
                                logger.warning(f"Page image {page_num} not found for OCR")
                                element["text"] = ""
                                text_elements.append(element)
                                continue
                            
                            page_image = page_images[page_num]
                            
                            # Crop element from image
                            x1, y1, x2, y2 = bbox
                            padding = 5
                            x1_crop = max(0, int(x1) - padding)
                            y1_crop = max(0, int(y1) - padding)
                            x2_crop = min(page_image.width, int(x2) + padding)
                            y2_crop = min(page_image.height, int(y2) + padding)
                            
                            cropped_image = page_image.crop((x1_crop, y1_crop, x2_crop, y2_crop))
                            
                            # OCR via Qwen2.5
                            text = ocr_text_with_qwen(cropped_image)
                            element["text"] = text.strip() if text else ""
                        else:
                            # Use PyMuPDF for extractable text
                            page = pdf_document.load_page(page_num)
                            # Convert coordinates to original PDF scale
                            x1, y1, x2, y2 = (
                                bbox[0] / render_scale,
                                bbox[1] / render_scale,
                                bbox[2] / render_scale,
                                bbox[3] / render_scale,
                            )
                            rect = fitz.Rect(x1, y1, x2, y2)
                            
                            # Try get_textbox first - more accurate method
                            text = page.get_textbox(rect).strip()
                            
                            # If get_textbox failed, try another method
                            if not text or len(text) < 2:
                                # Try to get text with clip for better performance
                                text_dict = page.get_text("dict", clip=rect)
                                text_parts = []
                                
                                for block in text_dict.get("blocks", []):
                                    if "lines" not in block:
                                        continue
                                    for line in block["lines"]:
                                        for span in line.get("spans", []):
                                            text_parts.append(span.get("text", ""))
                                
                                text = " ".join(text_parts).strip()
                            
                            # If that didn't help, use old method as fallback
                            if not text or len(text) < 2:
                                text = page.get_text("text", clip=rect).strip()
                            
                            element["text"] = text
                    except Exception as e:
                        logger.warning(f"Error extracting text for element: {e}")
                        element["text"] = ""
                else:
                    element["text"] = ""
                
                text_elements.append(element)
            
            return text_elements
        finally:
            pdf_document.close()

    def _merge_nearby_text_blocks(
        self, text_elements: List[Dict[str, Any]], max_chunk_size: int
    ) -> List[Dict[str, Any]]:
        """
        Merges consecutive Text elements.

        If text elements follow each other, merge them.

        Args:
            text_elements: List of text elements.
            max_chunk_size: Maximum block size in characters.

        Returns:
            List of merged elements.
        """
        if not text_elements:
            return []
        
        merged: List[Dict[str, Any]] = []
        current_block: Optional[Dict[str, Any]] = None
        
        # Sort by page and Y coordinate
        sorted_elements = sorted(
            text_elements,
            key=lambda e: (
                e.get("page_num", 0),
                e.get("bbox", [1, 0])[1] if len(e.get("bbox", [])) >= 2 else 0,
            ),
        )
        
        for element in sorted_elements:
            category = element.get("category", "")
            text = element.get("text", "")
            
            # Merge only Text elements
            if category != "Text":
                if current_block is not None:
                    merged.append(current_block)
                    current_block = None
                merged.append(element)
                continue
            
            if current_block is None:
                current_block = element.copy()
                continue
            
            # If current block is Text and next element is also Text, merge
            current_text = current_block.get("text", "")
            combined_text = f"{current_text} {text}".strip()
            
            # Check size
            if len(combined_text) <= max_chunk_size:
                current_block["text"] = combined_text
                # Update bbox
                current_bbox = current_block.get("bbox", [])
                element_bbox = element.get("bbox", [])
                if len(current_bbox) >= 4 and len(element_bbox) >= 4:
                    current_block["bbox"] = [
                        min(current_bbox[0], element_bbox[0]),
                        min(current_bbox[1], element_bbox[1]),
                        max(current_bbox[2], element_bbox[2]),
                        max(current_bbox[3], element_bbox[3]),
                    ]
                continue
            
            # Cannot merge (size exceeded) - save current block and start new
            merged.append(current_block)
            current_block = element.copy()
        
        # Add last block
        if current_block is not None:
            merged.append(current_block)
        
        logger.debug(f"Text merging: {len(text_elements)} -> {len(merged)} elements")
        return merged

    def _extract_links_from_text(self, text: str) -> List[str]:
        """
        Extracts URLs from text using regex pattern.
        
        Args:
            text: Text to search for URLs.
            
        Returns:
            List of found URLs.
        """
        if not text:
            return []
        
        links = URL_PATTERN.findall(text)
        # Normalize URLs (add http:// if starts with www.)
        normalized_links = []
        for link in links:
            if link.startswith("www."):
                normalized_links.append(f"http://{link}")
            else:
                normalized_links.append(link)
        
        return list(set(normalized_links))  # Remove duplicates

    def _extract_links_from_pdf_page(self, page: fitz.Page, rect: Optional[fitz.Rect] = None) -> List[Dict[str, str]]:
        """
        Extracts hyperlinks from PDF page annotations.
        
        Args:
            page: PyMuPDF page object.
            rect: Optional rectangle to filter links by area.
            
        Returns:
            List of dictionaries with link information (uri, type).
        """
        links = []
        try:
            link_list = page.get_links()
            for link in link_list:
                if link.get("kind") == fitz.LINK_URI:
                    uri = link.get("uri", "")
                    if uri:
                        # If rect is provided, check if link is within the rectangle
                        if rect is not None:
                            link_rect = fitz.Rect(link.get("from", (0, 0, 0, 0)))
                            if not rect.intersects(link_rect):
                                continue
                        links.append({"uri": uri, "type": "uri"})
        except Exception as e:
            logger.debug(f"Error extracting links from PDF page: {e}")
        
        return links

    def _create_elements_from_hierarchy(
        self,
        hierarchy: List[Dict[str, Any]],
        merged_text_elements: List[Dict[str, Any]],
        layout_elements: List[Dict[str, Any]],
        source: str | Path,
    ) -> List[Element]:
        """
        Creates elements from hierarchy.

        Args:
            hierarchy: List of sections with headers.
            merged_text_elements: List of merged text elements.
            layout_elements: All layout elements (for text search).

        Returns:
            List of Element elements.
        """
        elements: List[Element] = []
        header_stack: List[Tuple[int, str]] = []  # (level, element_id)
        
        # Create index of text elements by bbox for fast lookup
        text_elements_by_bbox: Dict[Tuple[int, int, int, int, int], Dict[str, Any]] = {}
        for elem in merged_text_elements:
            bbox = elem.get("bbox", [])
            page_num = elem.get("page_num", 0)
            if len(bbox) >= 4:
                # Use rounded coordinates for search
                key = (page_num, int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
                text_elements_by_bbox[key] = elem
        
        # Also create index for all layout elements
        layout_elements_by_bbox: Dict[Tuple[int, int, int, int, int], Dict[str, Any]] = {}
        for elem in layout_elements:
            bbox = elem.get("bbox", [])
            page_num = elem.get("page_num", 0)
            if len(bbox) >= 4:
                key = (page_num, int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
                layout_elements_by_bbox[key] = elem
        
        for section in hierarchy:
            header = section.get("header")
            children = section.get("children", [])
            
            # Create header element
            if header is not None:
                level = header.get("level", 1)
                element_type = header.get("element_type", ElementType.HEADER_1)
                text = header.get("text", "")
                
                # Update header stack
                while header_stack and header_stack[-1][0] >= level:
                    header_stack.pop()
                
                parent_id = header_stack[-1][1] if header_stack else None
                
                # Extract links from header text
                links_in_text = self._extract_links_from_text(text)
                
                metadata = {
                    "source": "ocr",
                    "level": level,
                    "bbox": header.get("bbox", []),
                    "page_num": header.get("page_num", 0),
                    "category": header.get("category", ""),
                }
                
                # Add links to metadata if found
                if links_in_text:
                    metadata["links"] = links_in_text
                
                header_element = self._create_element(
                    type=element_type,
                    content=text,
                    parent_id=parent_id,
                    metadata=metadata,
                )
                elements.append(header_element)
                header_stack.append((level, header_element.id))
                current_parent_id = header_element.id
            else:
                current_parent_id = header_stack[-1][1] if header_stack else None
            
            # Create elements for child elements
            for child in children:
                category = child.get("category", "")
                bbox = child.get("bbox", [])
                page_num = child.get("page_num", 0)
                
                if category == "Text":
                    # Search text in merged_text_elements (merged blocks)
                    text = ""
                    if len(bbox) >= 4:
                        # Try to find exact match
                        key = (page_num, int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
                        merged_elem = text_elements_by_bbox.get(key)
                        if merged_elem:
                            text = merged_elem.get("text", "")
                        else:
                            # If no exact match, use text from child
                            text = child.get("text", "")
                    else:
                        text = child.get("text", "")
                    
                    if text:
                        # Extract links from text
                        links_in_text = self._extract_links_from_text(text)
                        
                        metadata = {
                            "source": "ocr",
                            "bbox": bbox,
                            "page_num": page_num,
                            "category": category,
                        }
                        
                        # Add links to metadata if found
                        if links_in_text:
                            metadata["links"] = links_in_text
                        
                        # Also try to extract hyperlinks from PDF page
                        try:
                            pdf_document = fitz.open(source)
                            try:
                                page = pdf_document.load_page(page_num)
                                render_scale = self._get_config("layout_detection.render_scale", 2.0)
                                if len(bbox) >= 4:
                                    x1, y1, x2, y2 = (
                                        bbox[0] / render_scale,
                                        bbox[1] / render_scale,
                                        bbox[2] / render_scale,
                                        bbox[3] / render_scale,
                                    )
                                    rect = fitz.Rect(x1, y1, x2, y2)
                                    pdf_links = self._extract_links_from_pdf_page(page, rect)
                                    if pdf_links:
                                        if "links" not in metadata:
                                            metadata["links"] = []
                                        # Add PDF hyperlinks (avoid duplicates)
                                        existing_uris = set(links_in_text)
                                        for pdf_link in pdf_links:
                                            uri = pdf_link.get("uri", "")
                                            if uri and uri not in existing_uris:
                                                metadata["links"].append(uri)
                                                existing_uris.add(uri)
                            finally:
                                pdf_document.close()
                        except Exception as e:
                            logger.debug(f"Error extracting PDF hyperlinks: {e}")
                        
                        element = self._create_element(
                            type=ElementType.TEXT,
                            content=text,
                            parent_id=current_parent_id,
                            metadata=metadata,
                        )
                        elements.append(element)
                elif category == "Table":
                    # Tables will be processed later via Qwen
                    element = self._create_element(
                        type=ElementType.TABLE,
                        content="",  # will be filled during parsing
                        parent_id=current_parent_id,
                        metadata={
                            "source": "ocr",
                            "bbox": bbox,
                            "page_num": page_num,
                            "category": category,
                        },
                    )
                    elements.append(element)
                elif category == "Picture":
                    element = self._create_element(
                        type=ElementType.IMAGE,
                        content="",  # image will be in metadata
                        parent_id=current_parent_id,
                        metadata={
                            "source": "ocr",
                            "bbox": bbox,
                            "page_num": page_num,
                            "category": category,
                        },
                    )
                    elements.append(element)
                elif category == "Caption":
                    text = child.get("text", "")
                    # Extract links from caption text
                    links_in_text = self._extract_links_from_text(text)
                    
                    metadata = {
                        "source": "ocr",
                        "bbox": bbox,
                        "page_num": page_num,
                        "category": category,
                    }
                    
                    # Add links to metadata if found
                    if links_in_text:
                        metadata["links"] = links_in_text
                    
                    element = self._create_element(
                        type=ElementType.CAPTION,
                        content=text,
                        parent_id=current_parent_id,
                        metadata=metadata,
                    )
                    elements.append(element)
                elif category == "Title":
                    text = child.get("text", "")
                    element = self._create_element(
                        type=ElementType.TITLE,
                        content=text,
                        parent_id=None,  # Title has no parent
                        metadata={
                            "source": "ocr",
                            "bbox": bbox,
                            "page_num": page_num,
                            "category": category,
                        },
                    )
                    elements.append(element)
        
        return elements

    def _store_images_in_metadata(
        self, elements: List[Element], source: str
    ) -> List[Element]:
        """
        Stores images in Caption element metadata.
        
        Logic:
        - Finds IMAGE elements
        - Finds corresponding CAPTION elements (by bbox proximity)
        - Saves image in CAPTION metadata
        - CAPTION is already linked to Header via parent_id

        Args:
            elements: List of elements.
            source: Path to PDF file.

        Returns:
            List of elements with updated metadata.
        """
        pdf_document = fitz.open(source)
        try:
            render_scale = self._get_config("layout_detection.render_scale", 2.0)
            
            image_elements = [e for e in elements if e.type == ElementType.IMAGE]
            caption_elements = [e for e in elements if e.type == ElementType.CAPTION]
            
            for image_element in tqdm(image_elements, desc="Processing images", unit="image", leave=False):
                image_bbox = image_element.metadata.get("bbox", [])
                image_page = image_element.metadata.get("page_num", 0)
                
                if len(image_bbox) < 4 or image_page >= len(pdf_document):
                    continue
                
                try:
                    # Extract image
                    page = pdf_document.load_page(image_page)
                    x1, y1, x2, y2 = (
                        image_bbox[0] / render_scale,
                        image_bbox[1] / render_scale,
                        image_bbox[2] / render_scale,
                        image_bbox[3] / render_scale,
                    )
                    rect = fitz.Rect(x1, y1, x2, y2)
                    pix = page.get_pixmap(clip=rect)
                    img_data = pix.tobytes("png")
                    import base64
                    img_base64 = base64.b64encode(img_data).decode("utf-8")
                    
                    # Find corresponding Caption element
                    # Find nearest Caption on same page
                    best_caption = None
                    min_distance = float('inf')
                    
                    for caption_element in caption_elements:
                        caption_bbox = caption_element.metadata.get("bbox", [])
                        caption_page = caption_element.metadata.get("page_num", 0)
                        
                        if caption_page != image_page or len(caption_bbox) < 4:
                            continue
                        
                        # Check proximity: Caption is usually below image
                        # Vertical distance between bottom edge of image and top edge of Caption
                        distance = abs(caption_bbox[1] - image_bbox[3])
                        
                        # Caption should be below image (or very close)
                        if caption_bbox[1] >= image_bbox[1] - 50 and distance < min_distance:
                            min_distance = distance
                            best_caption = caption_element
                    
                    # If Caption found, save image in its metadata
                    if best_caption is not None:
                        best_caption.metadata["image_data"] = f"data:image/png;base64,{img_base64}"
                        logger.debug(f"Image saved in Caption metadata {best_caption.id}")
                    else:
                        # If Caption not found, save in IMAGE metadata (fallback)
                        image_element.metadata["image_data"] = f"data:image/png;base64,{img_base64}"
                        logger.warning(f"Caption not found for image {image_element.id}, image saved in IMAGE")
                        
                except Exception as e:
                    logger.warning(f"Error extracting image {image_element.id}: {e}")
        
        finally:
            pdf_document.close()
        
        return elements

    def _parse_tables_with_qwen(
        self, elements: List[Element], source: str
    ) -> List[Element]:
        """
        Parses tables via Qwen2.5.

        Args:
            elements: List of elements.
            source: Path to PDF file.

        Returns:
            List of elements with parsed tables.
        """
        table_elements = [e for e in elements if e.type == ElementType.TABLE]
        
        if not table_elements:
            return elements
        
        method = self._get_config("table_parsing.method", "markdown")
        detect_merged = self._get_config("table_parsing.detect_merged_tables", True)
        
        pdf_document = fitz.open(source)
        try:
            render_scale = self._get_config("layout_detection.render_scale", 2.0)
            
            for element in tqdm(table_elements, desc="Parsing tables", unit="table", leave=False):
                bbox = element.metadata.get("bbox", [])
                page_num = element.metadata.get("page_num", 0)
                
                if len(bbox) < 4 or page_num >= len(pdf_document):
                    logger.warning(f"Skipping table with invalid bbox or page_num: {element.id}")
                    continue
                
                try:
                    page = pdf_document.load_page(page_num)
                    # Convert coordinates to original PDF scale
                    x1, y1, x2, y2 = (
                        bbox[0] / render_scale,
                        bbox[1] / render_scale,
                        bbox[2] / render_scale,
                        bbox[3] / render_scale,
                    )
                    rect = fitz.Rect(x1, y1, x2, y2)
                    
                    # Render table area
                    mat = fitz.Matrix(2.0, 2.0)  # Increase for better quality
                    pix = page.get_pixmap(matrix=mat, clip=rect)
                    img_data = pix.tobytes("png")
                    
                    # Save table image in base64 (as for regular images)
                    import base64
                    img_base64 = base64.b64encode(img_data).decode("utf-8")
                    element.metadata["image_data"] = f"data:image/png;base64,{img_base64}"
                    
                    # Convert for parsing via Qwen
                    table_image = Image.open(BytesIO(img_data)).convert("RGB")
                    
                    # Parse table via Qwen
                    markdown_content, dataframe, success = parse_table_with_qwen(
                        table_image,
                        method=method,
                    )
                    
                    if not success:
                        logger.warning(f"Failed to parse table {element.id}")
                        element.content = ""
                        element.metadata["parsing_error"] = "Failed to parse table with Qwen"
                        # Create empty DataFrame
                        element.metadata["dataframe"] = pd.DataFrame()
                        element.metadata["rows_count"] = 0
                        element.metadata["cols_count"] = 0
                        continue
                    
                    # Process merged tables
                    if detect_merged and markdown_content:
                        tables = detect_merged_tables(markdown_content)
                        
                        if len(tables) > 1:
                            # Multiple tables merged - create separate elements
                            logger.info(f"Detected {len(tables)} merged tables in element {element.id}")
                            
                            # Update first element
                            element.content = tables[0]
                            if dataframe is not None:
                                element.metadata["dataframe"] = dataframe
                            else:
                                # Create empty DataFrame if parsing failed
                                element.metadata["dataframe"] = pd.DataFrame()
                            element.metadata["parsing_method"] = method
                            element.metadata["merged_tables"] = True
                            element.metadata["table_count"] = len(tables)
                            element.metadata["rows_count"] = len(dataframe) if dataframe is not None else 0
                            element.metadata["cols_count"] = len(dataframe.columns) if dataframe is not None else 0
                            # Image already saved above
                            
                            # Create additional elements for remaining tables
                            parent_id = element.parent_id
                            for i, table_md in enumerate(tables[1:], start=1):
                                # Parse each table separately
                                table_df = markdown_to_dataframe(table_md) if method == "markdown" else None
                                
                                new_element = self._create_element(
                                    type=ElementType.TABLE,
                                    content=table_md,
                                    parent_id=parent_id,
                                    metadata={
                                        "source": "ocr",
                                        "bbox": bbox,  # Same bbox, as tables are merged
                                        "page_num": page_num,
                                        "category": "Table",
                                        "parsing_method": method,
                                        "merged_tables": True,
                                        "table_index": i,
                                        "image_data": f"data:image/png;base64,{img_base64}",  # Same image
                                    },
                                )
                                if table_df is not None:
                                    new_element.metadata["dataframe"] = table_df
                                    new_element.metadata["rows_count"] = len(table_df)
                                    new_element.metadata["cols_count"] = len(table_df.columns)
                                else:
                                    # Create empty DataFrame if parsing failed
                                    new_element.metadata["dataframe"] = pd.DataFrame()
                                    new_element.metadata["rows_count"] = 0
                                    new_element.metadata["cols_count"] = 0
                                
                                # Insert after current element
                                element_idx = elements.index(element)
                                elements.insert(element_idx + i, new_element)
                        else:
                            # Single table
                            element.content = markdown_content
                            if dataframe is not None:
                                element.metadata["dataframe"] = dataframe
                            else:
                                # Create empty DataFrame if parsing failed
                                element.metadata["dataframe"] = pd.DataFrame()
                            element.metadata["parsing_method"] = method
                    else:
                        # Without merged table processing
                        element.content = markdown_content
                        if dataframe is not None:
                            element.metadata["dataframe"] = dataframe
                        else:
                            # Create empty DataFrame if parsing failed
                            element.metadata["dataframe"] = pd.DataFrame()
                        element.metadata["parsing_method"] = method
                    
                    logger.debug(f"Table {element.id} successfully parsed")
                
                except Exception as e:
                    logger.error(f"Error parsing table {element.id}: {e}")
                    element.content = ""
                    element.metadata["parsing_error"] = str(e)
                    continue
        
        finally:
            pdf_document.close()
        
        return elements

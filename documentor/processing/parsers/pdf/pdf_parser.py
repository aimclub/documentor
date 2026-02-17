"""
Parser for PDF documents.

Supports layout-based approach:
- Layout detection via Dots.OCR for all pages
- For scanned PDFs: uses prompt_layout_all_en to extract text, tables (HTML), and formulas (LaTeX) directly
- For PDFs with extractable text: uses prompt_layout_only_en, then extracts text via PyMuPDF
- Building hierarchy from Section-header
- Filtering unnecessary elements (Page-header, side text)
- Text extraction via PyMuPDF (for extractable text) or from Dots OCR (for scanned PDFs)
- Merging close text blocks
- Table parsing from Dots OCR HTML (for scanned PDFs) or via Qwen2.5 (fallback)
- Storing images in metadata (base64)
- Formula extraction in LaTeX format from Dots OCR
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
from .ocr.html_table_parser import (
    parse_table_from_html,
)
# Note: ocr_text_with_qwen is no longer used for scanned PDFs
# Text is extracted directly from Dots OCR (prompt_layout_all_en)


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
           - For scanned PDFs: uses prompt_layout_all_en (layout + text + tables + formulas)
           - For PDFs with text: uses prompt_layout_only_en (layout only)
        3. Building hierarchy from Section-header
        4. Filtering unnecessary elements
        5. Text extraction:
           - For scanned PDFs: text already extracted by Dots OCR
           - For PDFs with text: via PyMuPDF by coordinates
        6. Merging close text blocks
        7. Creating elements and building hierarchy
        8. Storing images in metadata (base64)
        9. Table parsing:
           - For scanned PDFs: from Dots OCR HTML
           - Fallback: via Qwen2.5
        10. Formula extraction: LaTeX from Dots OCR (for scanned PDFs)

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
        
        # Reset ID generator for each new document
        self._reset_id_generator()

        source = self.get_source(document)
        self._log_parsing_start(source)

        try:
            # Check if text is extractable
            is_text_extractable = self._is_text_extractable(source)
            
            if not is_text_extractable:
                logger.info(
                    f"Scanned PDF detected, using prompt_layout_all_en for text extraction via Dots OCR (source: {source})"
                )
            
            # Layout-based approach (always use, even if text is extractable)
            # Step 1: Layout Detection for all pages
            # For scanned PDFs, use prompt_layout_all_en to get text directly from Dots OCR
            layout_elements = self._detect_layout_for_all_pages(source, use_text_extraction=not is_text_extractable)
            
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
            
            # Step 5: Text extraction via PyMuPDF or from Dots OCR
            # For scanned PDFs, text is already extracted by Dots OCR (prompt_layout_all_en)
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
            
            # Step 9: Table parsing from Dots OCR HTML or via Qwen2.5 (fallback)
            logger.info("Step 9: Parsing tables...")
            elements = self._parse_tables(elements, source, use_dots_ocr_html=not is_text_extractable)
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

    def _detect_layout_for_all_pages(self, source: str, use_text_extraction: bool = False) -> List[Dict[str, Any]]:
        """
        Performs layout detection for all PDF pages.

        Args:
            source: Path to PDF file.
            use_text_extraction: If True, uses prompt_layout_all_en to extract text directly from Dots OCR.
                                If False, uses prompt_layout_only_en (layout only, text via PyMuPDF).

        Returns:
            List of layout elements with bbox, category, page_num fields.
            If use_text_extraction=True, elements also contain 'text' field from Dots OCR.
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
        
        # Load prompt for text extraction if needed
        prompt = None
        if use_text_extraction:
            from documentor.ocr.dots_ocr import load_prompts_from_config
            config_path = Path(__file__).parent.parent.parent.parent / "config" / "ocr_config.yaml"
            prompts = load_prompts_from_config(config_path)
            prompt = prompts.get("prompt_layout_all_en")
            if not prompt:
                logger.warning("prompt_layout_all_en not found in config, falling back to prompt_layout_only_en")
                use_text_extraction = False
        
        for page_num in tqdm(range(start_page, total_pages), desc="Layout detection", unit="page"):
            try:
                original_image, optimized_image = self.page_renderer.render_page(
                    pdf_path, page_num, return_original=True
                )
                
                if use_text_extraction:
                    # Use direct API call with prompt_layout_all_en to get text
                    from .ocr.dots_ocr_client import process_layout_detection
                    layout, _, success = process_layout_detection(
                        image=optimized_image,
                        origin_image=original_image,
                        prompt=prompt,
                    )
                    if not success or layout is None:
                        logger.warning(f"Layout detection failed for page {page_num + 1}, trying fallback")
                        layout = self.layout_detector.detect_layout(optimized_image, origin_image=original_image)
                else:
                    # Use standard layout detection (prompt_layout_only_en)
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
            
            # Check if text is extractable (to determine if we should use Dots OCR text)
            is_text_extractable = self._is_text_extractable(source)
            
            # Last header level with explicit numbering
            last_numbered_level: Optional[int] = None
            # History of previous headers for font size comparison
            previous_headers: List[Dict[str, Any]] = []  # {level, font_size, page_num}
            
            for element in layout_elements:
                category = element.get("category", "")
                
                if category == "Section-header":
                    # For scanned PDFs, text is already in element from Dots OCR
                    # For PDFs with extractable text, extract via PyMuPDF
                    bbox = element.get("bbox", [])
                    page_num = element.get("page_num", 0)
                    text = element.get("text", "")  # Try to get text from Dots OCR first
                    font_size = None
                    
                    if not is_text_extractable and text:
                        # For scanned PDFs: use text from Dots OCR
                        # Still need font_size for level determination, try to get it
                        if len(bbox) >= 4 and page_num < len(pdf_document):
                            try:
                                page = pdf_document.load_page(page_num)
                                x1, y1, x2, y2 = (
                                    bbox[0] / render_scale,
                                    bbox[1] / render_scale,
                                    bbox[2] / render_scale,
                                    bbox[3] / render_scale,
                                )
                                rect = fitz.Rect(x1, y1, x2, y2)
                                font_size = self._get_font_size(page, rect)
                            except Exception:
                                pass
                    elif len(bbox) >= 4 and page_num < len(pdf_document):
                        # For PDFs with extractable text: extract via PyMuPDF
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
                        except Exception as e:
                            logger.warning(f"Error analyzing header: {e}")
                            text = ""
                    
                    if text:
                        # Remove markdown formatting from header text
                        # 1. Remove all # symbols from the beginning (Dots OCR adds ## to headers)
                        cleaned_text = text.strip()
                        while cleaned_text.startswith('#'):
                            cleaned_text = cleaned_text.lstrip('#').strip()
                        
                        # 2. Remove markdown bold formatting (**text** or __text__)
                        cleaned_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned_text)  # **bold** -> bold
                        cleaned_text = re.sub(r'__([^_]+)__', r'\1', cleaned_text)  # __bold__ -> bold
                        # Also handle single asterisks/underscores (but be careful not to remove valid characters)
                        cleaned_text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'\1', cleaned_text)  # *italic* -> italic (if not part of **)
                        cleaned_text = re.sub(r'(?<!_)_([^_]+)_(?!_)', r'\1', cleaned_text)  # _italic_ -> italic (if not part of __)
                        cleaned_text = cleaned_text.strip()
                        
                        # Check if header ends with colon - if so, convert to Text (not a header)
                        # Headers like "Задачи:", "Плюсы:", "Минусы:" should be text, not headers
                        if cleaned_text.endswith(':'):
                            element["category"] = "Text"
                            element["text"] = cleaned_text
                            analyzed_elements.append(element)
                            continue
                        
                        # Determine header level (use cleaned text for level detection)
                        level = self._determine_header_level(
                            cleaned_text, element, None, None, last_numbered_level, previous_headers, font_size
                        )
                        
                        # If header has explicit numbering, update last_numbered_level
                        if self._has_explicit_numbering(cleaned_text):
                            last_numbered_level = level
                        
                        # Save header info for comparison with subsequent headers
                        previous_headers.append({
                            "level": level,
                            "font_size": font_size,
                            "page_num": page_num,
                            "text": cleaned_text,  # Save text to check for letter-based numbering context
                        })
                        
                        element_type = getattr(ElementType, f"HEADER_{level}", ElementType.HEADER_1)
                        
                        # Save cleaned text (without markdown symbols)
                        element["text"] = cleaned_text
                        element["level"] = level
                        element["element_type"] = element_type
                    else:
                        # If no text found, default to HEADER_1
                        logger.warning(f"Header text not found for element on page {page_num + 1}")
                        element["text"] = ""
                        element["level"] = 1
                        element["element_type"] = ElementType.HEADER_1
                        previous_headers.append({
                            "level": 1,
                            "font_size": None,
                            "page_num": page_num,
                            "text": "",  # No text available
                        })
                
                    # Add header element to analyzed_elements
                    analyzed_elements.append(element)
                else:
                    # Add non-header elements to analyzed_elements
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
        # Headers with Roman numerals (I, II, III, IV, V, VI, etc.) -> HEADER_1
        # Pattern matches: "I. ", "II. ", "III. ", "IV. ", "V. ", "VI. ", etc.
        if re.match(r'^[IVX]+\.\s+', text, re.IGNORECASE):
            return 1
        # Headers like "1", "2", "3" -> HEADER_1
        # Supports both Latin and Cyrillic letters
        # Pattern: digit(s) + one or more spaces + uppercase letter (Latin or Cyrillic)
        # This should match "5 Работа...", "6 Подведение..." etc.
        text_stripped = text.strip()
        if re.match(r'^\d+\s+[A-ZА-ЯЁ]', text_stripped):
            return 1
        # Headers like "A.1", "B.1", "C.1" -> HEADER_3 (subsections under letter headers)
        if re.match(r'^[A-Z]\.\d+\s+', text):
            return 3
        # Headers like "1.1", "1.2" -> HEADER_2
        if re.match(r'^\d+\.\d+\s+', text):
            return 2
        # Headers like "A. ", "B. ", "C. " -> HEADER_2 (letter-based sections with dot)
        if re.match(r'^[A-Z]\.\s+', text):
            return 2
        # Headers like "A ", "B ", "C " -> HEADER_2 (letter-based sections without dot)
        if re.match(r'^[A-Z]\s+[A-Z]', text):
            return 2
        # Headers like "1.1.1", "1.1.2" -> HEADER_3
        if re.match(r'^\d+\.\d+\.\d+\s+', text):
            return 3
        # Headers like "1.1.1.1" -> HEADER_4
        if re.match(r'^\d+\.\d+\.\d+\.\d+\s+', text):
            return 4
        # Special headers like "References", "Bibliography", "Abstract" -> HEADER_1
        text_upper = text.strip().upper()
        if text_upper in ["REFERENCES", "BIBLIOGRAPHY", "ABSTRACT", "INTRODUCTION", "CONCLUSION", "CONCLUSIONS", "ACKNOWLEDGEMENT", "ACKNOWLEDGMENTS", "СПИСОК ЛИТЕРАТУРЫ", "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", "ЛИТЕРАТУРА"]:
            return 1
        
        # Headers like "Приложение А.", "Приложение Б.", "Appendix A.", "Приложение 1." -> HEADER_2
        # Pattern: "Приложение" or "Appendix" + space + letter or digit + optional dot
        # These are subsections under "ПРИЛОЖЕНИЯ" (HEADER_1)
        if re.match(r'^(ПРИЛОЖЕНИЕ|APPENDIX)\s+[A-ZА-ЯЁ0-9]\.?', text_upper):
            return 2
        
        # Headers like "Приложения", "Appendices", "Appendix" -> HEADER_1
        if text_upper in ["ПРИЛОЖЕНИЯ", "APPENDICES", "APPENDIX", "ПРИЛОЖЕНИЕ"]:
            return 1
        
        # Check if we're inside letter-based numbering context (e.g., "H", "H.2")
        # If header has no explicit numbering and previous headers have letter-based numbering,
        # this header should be one level below the last letter-based header
        if previous_headers:
            # Check recent previous headers for letter-based numbering
            # Look at last few headers (up to 5) to find letter-based context
            recent_headers = previous_headers[-5:] if len(previous_headers) > 5 else previous_headers
            for prev_header in reversed(recent_headers):
                prev_text = prev_header.get("text", "")
                if prev_text:
                    # Check if previous header has letter-based numbering
                    # Pattern: "H ", "H.2 ", "A ", "A.1 ", etc.
                    if re.match(r'^[A-Z](\.\d+)?\s+', prev_text):
                        # We're inside letter-based numbering context
                        # Headers without explicit numbering should be one level below the last letter-based header
                        prev_level = prev_header.get("level", 2)  # Default to 2 if level not found
                        return min(prev_level + 1, 6)  # Limit maximum to 6
        
        # Check if we're inside numeric numbering context (e.g., "2", "2.1", "2.1.1")
        # If header has no explicit numbering and previous headers have numeric numbering,
        # this header should be one level below the last numeric header
        # IMPORTANT: Only apply this if the current header does NOT have explicit numeric numbering
        # Headers with explicit numbering (like "5 ", "6 ") should already be handled above
        if previous_headers:
            # Check recent previous headers for numeric numbering
            # Look at last few headers (up to 5) to find numeric context
            recent_headers = previous_headers[-5:] if len(previous_headers) > 5 else previous_headers
            for prev_header in reversed(recent_headers):
                prev_text = prev_header.get("text", "")
                if prev_text:
                    # Check if previous header has numeric numbering
                    # Pattern: "2 ", "2.1 ", "2.1.1 ", etc.
                    if re.match(r'^\d+(\.\d+)*\s+', prev_text):
                        # We're inside numeric numbering context
                        # Headers without explicit numbering should be one level below the last numeric header
                        prev_level = prev_header.get("level", 1)  # Default to 1 if level not found
                        return min(prev_level + 1, 6)  # Limit maximum to 6
        
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

    def _remove_markdown_formatting(self, text: str) -> str:
        """
        Remove markdown formatting (**text**, __text__, *text*) from text.
        Preserves single asterisks (*) used as list markers at the start of lines.
        
        Args:
            text: Text with potential markdown formatting
            
        Returns:
            Text with markdown formatting removed
        """
        if not text:
            return text
        
        # First, remove **text** (bold) -> text
        cleaned_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        # Remove __text__ (bold) -> text
        cleaned_text = re.sub(r'__([^_]+)__', r'\1', cleaned_text)
        
        # Remove *text* (italic) but preserve list markers (* at start of line or after newline)
        # Split by lines to handle list markers correctly
        lines = cleaned_text.split('\n')
        cleaned_lines = []
        for line in lines:
            # If line starts with "* " (list marker), preserve it and remove *text* from the rest
            if line.strip().startswith('* '):
                # Keep the "* " prefix, remove *text* from the rest
                prefix = line[:line.find('* ') + 2]  # "* " + everything before it
                rest = line[line.find('* ') + 2:]
                # Remove *text* from the rest
                rest_cleaned = re.sub(r'\*([^*]+)\*', r'\1', rest)
                cleaned_lines.append(prefix + rest_cleaned)
            else:
                # Remove all *text* (italic) from the line
                cleaned_line = re.sub(r'\*([^*]+)\*', r'\1', line)
                cleaned_lines.append(cleaned_line)
        
        cleaned_text = '\n'.join(cleaned_lines)
        
        return cleaned_text.strip()

    def _extract_text_by_bboxes(
        self, source: str, layout_elements: List[Dict[str, Any]], use_ocr: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Extracts text via PyMuPDF by coordinates from layout elements.
        For scanned PDFs (use_ocr=True), text is already extracted by Dots OCR (prompt_layout_all_en).

        Args:
            source: Path to PDF file.
            layout_elements: List of layout elements with bbox.
            use_ocr: If True, text is already in elements from Dots OCR, just use it.
                     If False, extracts text via PyMuPDF.

        Returns:
            List of elements with extracted text.
        """
        pdf_document = fitz.open(source)
        try:
            text_elements: List[Dict[str, Any]] = []
            render_scale = self._get_config("layout_detection.render_scale", 2.0)
            
            if use_ocr:
                # For scanned PDFs, text is already extracted by Dots OCR (prompt_layout_all_en)
                # Just use the text from layout_elements
                logger.info("Using text from Dots OCR (prompt_layout_all_en)")
                
                for element in tqdm(layout_elements, desc="Processing text from Dots OCR", unit="element", leave=False):
                    category = element.get("category", "")
                    
                    # Skip Picture - no text for images
                    if category == "Picture":
                        text_elements.append(element)
                        continue
                    
                    # For text elements, use text from Dots OCR if available
                    if category in ["Text", "Section-header", "Title", "Caption", "Formula", "List-item"]:
                        # Text should already be in element from Dots OCR
                        # Clean and normalize if needed
                        text = element.get("text", "")
                        if text:
                            # Remove markdown formatting (**text** or __text__)
                            # BUT: Do NOT apply to Formula - LaTeX may contain *, **, _, __ as part of syntax
                            if category != "Formula":
                                text = self._remove_markdown_formatting(text)
                            # Remove extra whitespace but preserve structure
                            element["text"] = text.strip()
                        else:
                            element["text"] = ""
                    
                    text_elements.append(element)
            else:
                # For PDFs with extractable text, use PyMuPDF
                for element in tqdm(layout_elements, desc="Extracting text via PyMuPDF", unit="element", leave=False):
                    category = element.get("category", "")
                    bbox = element.get("bbox", [])
                    page_num = element.get("page_num", 0)
                    
                    # Skip Picture - don't extract text for images
                    if category == "Picture":
                        text_elements.append(element)
                        continue
                    
                    # Extract text only for text elements
                    if category not in ["Text", "Section-header", "Title", "Caption"]:
                        text_elements.append(element)
                        continue
                    
                    if len(bbox) >= 4 and page_num < len(pdf_document):
                        try:
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
                # Get text from header - it should be there from _analyze_header_levels_from_elements
                text = header.get("text", "")
                
                # If text is still empty, try to get it from merged_text_elements or layout_elements
                if not text:
                    bbox = header.get("bbox", [])
                    page_num = header.get("page_num", 0)
                    if len(bbox) >= 4:
                        # Try to find in merged_text_elements first
                        key = (page_num, int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
                        merged_elem = text_elements_by_bbox.get(key)
                        if merged_elem:
                            text = merged_elem.get("text", "")
                        # If still no text, try from layout_elements
                        if not text:
                            layout_elem = layout_elements_by_bbox.get(key)
                            if layout_elem:
                                text = layout_elem.get("text", "")
                
                # If still no text, log warning but create header anyway
                if not text:
                    logger.warning(f"Header text is empty for header on page {header.get('page_num', 0) + 1}, bbox: {header.get('bbox', [])}")
                
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
                        # Remove markdown formatting (**text** or __text__)
                        cleaned_text = self._remove_markdown_formatting(text)
                        
                        # Extract links from text
                        links_in_text = self._extract_links_from_text(cleaned_text)
                        
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
                            content=cleaned_text,
                            parent_id=current_parent_id,
                            metadata=metadata,
                        )
                        elements.append(element)
                elif category == "Table":
                    # For scanned PDFs, HTML is already in layout_elements from Dots OCR
                    # Store it in metadata for later parsing
                    table_html = child.get("text", "")  # HTML from Dots OCR (prompt_layout_all_en)
                    
                    element = self._create_element(
                        type=ElementType.TABLE,
                        content="",  # will be filled during parsing
                        parent_id=current_parent_id,
                        metadata={
                            "source": "ocr",
                            "bbox": bbox,
                            "page_num": page_num,
                            "category": category,
                            "table_html": table_html,  # Store HTML for parsing
                        },
                    )
                    elements.append(element)
                elif category == "Formula":
                    # Formulas are in LaTeX format from Dots OCR
                    formula_latex = child.get("text", "")  # LaTeX from Dots OCR
                    # DO NOT remove markdown formatting from formulas!
                    # LaTeX syntax may contain *, **, _, __ as valid operators/symbols
                    # (e.g., x^2 * y^2, x_1, etc.)
                    # Only strip whitespace
                    formula_latex = formula_latex.strip()
                    
                    element = self._create_element(
                        type=ElementType.TEXT,  # Formula is stored as TEXT with LaTeX in metadata
                        content=formula_latex,  # LaTeX content
                        parent_id=current_parent_id,
                        metadata={
                            "source": "ocr",
                            "bbox": bbox,
                            "page_num": page_num,
                            "category": category,
                            "formula_latex": formula_latex,  # Store LaTeX in metadata
                            "is_formula": True,
                        },
                    )
                    elements.append(element)
                elif category == "List-item":
                    # List items from Dots OCR
                    list_text = child.get("text", "")
                    
                    # Remove markdown bold formatting (**text** or __text__) but preserve list markers (*)
                    cleaned_list_text = self._remove_markdown_formatting(list_text)
                    
                    element = self._create_element(
                        type=ElementType.LIST_ITEM,
                        content=cleaned_list_text,
                        parent_id=current_parent_id,
                        metadata={
                            "source": "ocr",
                            "bbox": bbox,
                            "page_num": page_num,
                            "category": category,
                            "is_list_item": True,
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
                    # Remove markdown formatting (**text** or __text__)
                    cleaned_text = self._remove_markdown_formatting(text)
                    # Extract links from caption text
                    links_in_text = self._extract_links_from_text(cleaned_text)
                    
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
                        content=cleaned_text,
                        parent_id=current_parent_id,
                        metadata=metadata,
                    )
                    elements.append(element)
                elif category == "Title":
                    text = child.get("text", "")
                    # Remove markdown formatting (**text** or __text__)
                    cleaned_text = self._remove_markdown_formatting(text)
                    element = self._create_element(
                        type=ElementType.TITLE,
                        content=cleaned_text,
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
                
                if len(image_bbox) < 4:
                    logger.warning(f"Image {image_element.id} has invalid bbox: {image_bbox}")
                    continue
                
                if image_page >= len(pdf_document):
                    logger.warning(f"Image {image_element.id} has invalid page number: {image_page} (max: {len(pdf_document) - 1})")
                    continue
                
                try:
                    # Extract image
                    page = pdf_document.load_page(image_page)
                    
                    # Convert coordinates: bbox is in render_scale coordinates, need to convert to PDF coordinates
                    # For scanned PDFs, bbox comes from Dots OCR which uses render_scale
                    x1, y1, x2, y2 = (
                        image_bbox[0] / render_scale,
                        image_bbox[1] / render_scale,
                        image_bbox[2] / render_scale,
                        image_bbox[3] / render_scale,
                    )
                    
                    # Ensure coordinates are within page bounds
                    page_rect = page.rect
                    x1 = max(0, min(x1, page_rect.width))
                    y1 = max(0, min(y1, page_rect.height))
                    x2 = max(x1, min(x2, page_rect.width))
                    y2 = max(y1, min(y2, page_rect.height))
                    
                    # Validate that rect has positive area
                    if x2 <= x1 or y2 <= y1:
                        logger.warning(f"Image {image_element.id} has invalid rect after conversion: ({x1}, {y1}, {x2}, {y2})")
                        continue
                    
                    rect = fitz.Rect(x1, y1, x2, y2)
                    
                    # Calculate image dimensions in PDF coordinates
                    img_width = x2 - x1
                    img_height = y2 - y1
                    
                    # Limit maximum image size to avoid huge base64 strings
                    # Target: max 1280px on the longest side, maintain aspect ratio
                    # This significantly reduces file size while maintaining reasonable quality
                    max_dimension = 1280
                    scale_factor = 1.0
                    
                    if img_width > max_dimension or img_height > max_dimension:
                        if img_width > img_height:
                            scale_factor = max_dimension / img_width
                        else:
                            scale_factor = max_dimension / img_height
                    
                    # Render image with reasonable quality
                    # Use calculated scale_factor to limit size, but don't go below 1.0x
                    render_scale = max(1.0, min(1.5, scale_factor * 1.5))
                    mat = fitz.Matrix(render_scale, render_scale)
                    pix = page.get_pixmap(matrix=mat, clip=rect)
                    
                    if pix is None or pix.width == 0 or pix.height == 0:
                        logger.warning(f"Image {image_element.id} rendered as empty pixmap")
                        continue
                    
                    # Convert to PIL Image for compression
                    import io
                    
                    # Convert pixmap to PIL Image
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    
                    # Resize if still too large (double-check after rendering)
                    final_max_dimension = 1280
                    if img.width > final_max_dimension or img.height > final_max_dimension:
                        if img.width > img.height:
                            new_width = final_max_dimension
                            new_height = int(img.height * (final_max_dimension / img.width))
                        else:
                            new_height = final_max_dimension
                            new_width = int(img.width * (final_max_dimension / img.height))
                        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    # Compress as JPEG with quality 75 (good balance between quality and size)
                    # Quality 75 provides good visual quality while significantly reducing file size
                    output = io.BytesIO()
                    img.save(output, format="JPEG", quality=75, optimize=True)
                    img_data = output.getvalue()
                    
                    if not img_data or len(img_data) == 0:
                        logger.warning(f"Image {image_element.id} has empty image data after compression")
                        continue
                    
                    import base64
                    img_base64 = base64.b64encode(img_data).decode("utf-8")
                    
                    # Log image size for debugging
                    logger.debug(f"Image {image_element.id}: {pix.width}x{pix.height}, base64 size: {len(img_base64)} chars, compressed: {len(img_data)} bytes")
                    
                    if not img_base64 or len(img_base64) == 0:
                        logger.warning(f"Image {image_element.id} has empty base64 data")
                        continue
                    
                    # Find corresponding Caption element
                    # Caption can be above or below image
                    # Also need to distinguish: if caption is followed by table, it's for table, not for image
                    best_caption = None
                    min_distance = float('inf')
                    
                    # Get all elements to check what comes after caption
                    all_elements = elements
                    image_element_idx = all_elements.index(image_element) if image_element in all_elements else -1
                    
                    for caption_element in caption_elements:
                        caption_bbox = caption_element.metadata.get("bbox", [])
                        caption_page = caption_element.metadata.get("page_num", 0)
                        
                        if caption_page != image_page or len(caption_bbox) < 4:
                            continue
                        
                        # Check if this caption is for a table (if table follows immediately after caption)
                        caption_element_idx = all_elements.index(caption_element) if caption_element in all_elements else -1
                        if caption_element_idx >= 0 and caption_element_idx + 1 < len(all_elements):
                            next_element = all_elements[caption_element_idx + 1]
                            if next_element.type == ElementType.TABLE:
                                # This caption is for table, skip it
                                continue
                        
                        # Check proximity: Caption can be above or below image
                        # Convert to same scale for comparison
                        caption_y1 = caption_bbox[1] / render_scale
                        caption_y3 = caption_bbox[3] / render_scale
                        image_y1 = image_bbox[1] / render_scale
                        image_y3 = image_bbox[3] / render_scale
                        
                        # Calculate distance: caption can be above (caption_y3 < image_y1) or below (caption_y1 > image_y3)
                        if caption_y3 < image_y1:
                            # Caption is above image
                            distance = abs(caption_y3 - image_y1)
                        elif caption_y1 > image_y3:
                            # Caption is below image
                            distance = abs(caption_y1 - image_y3)
                        else:
                            # Caption overlaps with image (shouldn't happen, but handle it)
                            distance = 0
                        
                        # Check horizontal overlap (caption should be near image horizontally)
                        caption_x1 = caption_bbox[0] / render_scale
                        caption_x2 = caption_bbox[2] / render_scale
                        image_x1 = image_bbox[0] / render_scale
                        image_x2 = image_bbox[2] / render_scale
                        
                        # Check if there's horizontal overlap or they're close
                        horizontal_overlap = not (caption_x2 < image_x1 or caption_x1 > image_x2)
                        horizontal_distance = min(abs(caption_x2 - image_x1), abs(caption_x1 - image_x2)) if not horizontal_overlap else 0
                        
                        # Prefer captions with horizontal overlap or close horizontally (within 100px)
                        if (horizontal_overlap or horizontal_distance < 100) and distance < min_distance:
                            min_distance = distance
                            best_caption = caption_element
                    
                    # Save image ONLY in CAPTION metadata (not in IMAGE)
                    if best_caption is not None:
                        best_caption.metadata["image_data"] = f"data:image/jpeg;base64,{img_base64}"
                        # Update IMAGE parent_id to point to CAPTION
                        image_element.parent_id = best_caption.id
                        logger.debug(f"Image {image_element.id} saved in Caption metadata {best_caption.id}, IMAGE parent_id updated to {best_caption.id} (size: {len(img_base64)} chars)")
                    else:
                        # If Caption not found, save in IMAGE metadata as fallback
                        image_element.metadata["image_data"] = f"data:image/jpeg;base64,{img_base64}"
                        logger.warning(f"Caption not found for image {image_element.id}, image saved in IMAGE metadata only (size: {len(img_base64)} chars)")
                        
                except Exception as e:
                    logger.warning(f"Error extracting image {image_element.id}: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
        
        finally:
            pdf_document.close()
        
        return elements

    def _parse_tables(
        self, elements: List[Element], source: str, use_dots_ocr_html: bool = False
    ) -> List[Element]:
        """
        Parses tables from Dots OCR HTML (for scanned PDFs) or via Qwen2.5 (fallback).

        Args:
            elements: List of elements.
            source: Path to PDF file.
            use_dots_ocr_html: If True, uses HTML from Dots OCR (prompt_layout_all_en).
                              If False, uses Qwen2.5 for table parsing.

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
            
            # For scanned PDFs, we need to get HTML from layout_elements
            # Store layout_elements in a way accessible to this method
            # We'll pass it through metadata or find it from analyzed_elements
            
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
                    
                    # Render table area for image storage
                    mat = fitz.Matrix(2.0, 2.0)  # Increase for better quality
                    pix = page.get_pixmap(matrix=mat, clip=rect)
                    img_data = pix.tobytes("png")
                    
                    # Save table image in base64 (as for regular images)
                    import base64
                    img_base64 = base64.b64encode(img_data).decode("utf-8")
                    element.metadata["image_data"] = f"data:image/png;base64,{img_base64}"
                    
                    # Parse table: use HTML from Dots OCR or Qwen as fallback
                    markdown_content = None
                    dataframe = None
                    success = False
                    
                    if use_dots_ocr_html:
                        # Try to get HTML from element metadata (stored during element creation)
                        table_html = element.metadata.get("table_html")
                        if table_html:
                            # Parse HTML table from Dots OCR
                            from .ocr.html_table_parser import parse_table_from_html
                            markdown_content, dataframe, success = parse_table_from_html(
                                table_html,
                                method=method,
                            )
                            if success:
                                logger.debug(f"Table {element.id} parsed from Dots OCR HTML")
                    
                    # Fallback to Qwen if HTML parsing failed or not available
                    if not success:
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
                        error_source = "Dots OCR HTML" if use_dots_ocr_html else "Qwen"
                        element.metadata["parsing_error"] = f"Failed to parse table with {error_source}"
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

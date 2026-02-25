"""
Parser for PDF documents.

Supports layout-based approach:
- Layout detection via OCR for all pages
- Building hierarchy from Section-header
- Filtering unnecessary elements (Page-header, side text)
- Text extraction from OCR (for scanned PDFs) or PyMuPDF (for text-extractable PDFs)
- Merging close text blocks
- Table parsing from OCR HTML
- Storing images in metadata (base64)
- Formula extraction in LaTeX format from OCR
"""

import logging
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import fitz
import pandas as pd
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
from documentor.config.loader import ConfigLoader
from ...headers.constants import SPECIAL_HEADER_1, APPENDIX_HEADER_PATTERN
from ..base import BaseParser
from .hierarchy_builder import PdfHierarchyBuilder
from .image_processor import PdfImageProcessor
from .layout_processor import PdfLayoutProcessor
from .table_parser import PdfTableParser
from .text_extractor import PdfTextExtractor


logger = logging.getLogger(__name__)


class PdfParser(BaseParser):
    """
    Parser for PDF documents.

    Uses layout-based approach:
    - Layout detection via OCR for all pages (default: Dots OCR)
    - For scanned PDFs: uses OCR with full extraction (layout + text + tables + formulas)
    - For text-extractable PDFs:
      * Uses OCR for layout detection only
      * If tables found, re-processes pages with tables using OCR to get table HTML
      * Extracts text via PyMuPDF by coordinates
    - Building hierarchy from Section-header
    - Filtering unnecessary elements
    - Text extraction via PyMuPDF (for extractable text) or from OCR (for scanned PDFs)
    - Merging close text blocks
    - Table parsing from OCR HTML (default: Dots OCR)
    
    Supports custom OCR components via constructor parameters:
    - layout_detector: Custom layout detector implementing BaseLayoutDetector
    - text_extractor: Custom text extractor implementing BaseTextExtractor
    - table_parser: Custom table parser implementing BaseTableParser
    - formula_extractor: Custom formula extractor implementing BaseFormulaExtractor
    """

    format = DocumentFormat.PDF

    def __init__(
        self, 
        ocr_manager: Optional[Any] = None,
        layout_detector: Optional[Any] = None,
        text_extractor: Optional[Any] = None,
        table_parser: Optional[Any] = None,
        formula_extractor: Optional[Any] = None,
        config_path: Optional[Union[str, Path]] = None,
        config_dict: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Initialize parser.
        
        Args:
            ocr_manager: DotsOCRManager instance for OCR processing. 
                        If None, automatically created from .env when needed.
            layout_detector: Custom layout detector implementing BaseLayoutDetector.
                            If None, uses default Dots OCR layout detector.
            text_extractor: Custom text extractor implementing BaseTextExtractor.
                          If None, uses default text extractor (PyMuPDF or Dots OCR).
            table_parser: Custom table parser implementing BaseTableParser.
                         If None, uses default Dots OCR table parser.
            formula_extractor: Custom formula extractor implementing BaseFormulaExtractor.
                             If None, uses default Dots OCR formula extractor.
            config_path: Optional path to external config YAML file. 
                        If None, uses default internal config.
            config_dict: Optional dictionary with full config. 
                       If provided, extracts "pdf_parser" section.
                       Takes priority over config_path.
        
        Examples:
            # Use default Dots OCR components and default config
            parser = PdfParser()
            
            # Use custom config file
            parser = PdfParser(config_path="/path/to/my_config.yaml")
            
            # Use custom config dictionary
            parser = PdfParser(config_dict={
                "pdf_parser": {
                    "layout_detection": {"render_scale": 3.0},
                    "processing": {"skip_title_page": True}
                }
            })
            
            # Use custom layout detector with custom config
            from documentor.ocr.base import BaseLayoutDetector
            
            class MyLayoutDetector(BaseLayoutDetector):
                def detect_layout(self, image, origin_image=None):
                    # Your custom implementation
                    return [...]
            
            parser = PdfParser(
                layout_detector=MyLayoutDetector(),
                config_path="/path/to/my_config.yaml"
            )
        """
        super().__init__()
        self.ocr_manager = ocr_manager
        self._config: Optional[Dict[str, Any]] = None
        self._load_config(config_path=config_path, config_dict=config_dict)
        
        # Initialize specialized processors with optional custom components
        self.layout_processor = PdfLayoutProcessor(
            ocr_manager=ocr_manager, 
            config=self._config,
            layout_detector=layout_detector
        )
        self.text_extractor = PdfTextExtractor(
            config=self._config,
            text_extractor=text_extractor
        )
        self.table_parser = PdfTableParser(
            config=self._config,
            table_parser=table_parser
        )
        self.image_processor = PdfImageProcessor(config=self._config)
        self.hierarchy_builder = PdfHierarchyBuilder(config=self._config, id_generator=self.id_generator)
        self.formula_extractor = formula_extractor
    
    def _load_config(
        self, 
        config_path: Optional[Union[str, Path]] = None,
        config_dict: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Loads configuration from config file or dictionary.
        
        Args:
            config_path: Optional path to external config YAML file.
            config_dict: Optional dictionary with full config.
        """
        self._config = ConfigLoader.load_config(
            "pdf_parser",
            config_path=config_path,
            config_dict=config_dict
        )

    def _get_config(self, key: str, default: Any = None) -> Any:
        """Gets value from configuration."""
        return ConfigLoader.get_config_value(self._config, key, default)
    
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
        1. Check if text is extractable
        2. Layout detection via OCR for all pages
           - For scanned PDFs: uses OCR with full extraction (layout + text + tables + formulas)
           - For text-extractable PDFs: uses OCR for layout only
        3. For text-extractable PDFs: if tables found, re-process pages with tables using OCR to get HTML
        4. Building hierarchy from Section-header
        5. Filtering unnecessary elements
        6. Text extraction:
           - For scanned PDFs: text already extracted by OCR
           - For text-extractable PDFs: via PyMuPDF by coordinates
        7. Merging close text blocks
        8. Creating elements and building hierarchy
        9. Storing images in metadata (base64)
        10. Table parsing from OCR HTML
        11. Formula extraction: LaTeX from OCR (for scanned PDFs)

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
                    f"Scanned PDF detected, using OCR for text extraction (source: {source})"
                )
            else:
                logger.info(
                    f"Text-extractable PDF detected, using OCR for layout and tables, PyMuPDF for text (source: {source})"
                )
            
            # Layout-based approach
            # Step 1: Layout Detection for all pages
            # For scanned PDFs: use prompt_layout_all_en to get text, tables (HTML), and formulas
            # For text-extractable PDFs: use prompt_layout_only_en for layout, then prompt_layout_all_en for tables only
            layout_elements = self.layout_processor.detect_layout_for_all_pages(
                source, use_text_extraction=not is_text_extractable
            )
            
            # Step 1.5: For text-extractable PDFs, if tables found, re-process pages with tables using prompt_layout_all_en
            # This can be disabled via config to speed up parsing (at the cost of table quality)
            if is_text_extractable:
                reprocess_tables = self._get_config("table_parsing.reprocess_tables", True)
                if reprocess_tables:
                    layout_elements = self.layout_processor.reprocess_tables_with_all_en(source, layout_elements)
                else:
                    logger.info("Table reprocessing disabled - using layout-only detection for faster parsing")
            
            # Step 2: Filtering unnecessary elements
            logger.info("Step 2: Filtering elements...")
            filtered_elements = self.layout_processor.filter_layout_elements(layout_elements)
            logger.info(f"Filtered: {len(layout_elements)} -> {len(filtered_elements)} elements")
            
            # Step 3: Header level analysis (determine levels first)
            logger.info("Step 3: Analyzing header levels...")
            analyzed_elements = self.hierarchy_builder.analyze_header_levels_from_elements(
                filtered_elements, source, is_text_extractable
            )
            logger.info(f"Analyzed headers: {len([e for e in analyzed_elements if e.get('category') == 'Section-header'])}")
            
            # Step 4: Building hierarchy from Section-header (with levels)
            logger.info("Step 4: Building hierarchy...")
            hierarchy = self.hierarchy_builder.build_hierarchy_from_section_headers(analyzed_elements)
            logger.info(f"Built sections: {len(hierarchy)}")
            
            # Step 5: Text extraction
            # For scanned PDFs: text is already extracted by Dots OCR (prompt_layout_all_en)
            # For text-extractable PDFs: extract text via PyMuPDF by coordinates
            logger.info("Step 5: Extracting text...")
            text_elements = self.text_extractor.extract_text_by_bboxes(
                source, analyzed_elements, use_ocr=not is_text_extractable
            )
            logger.info(f"Extracted text elements: {len(text_elements)}")
            
            # Step 6: Merging consecutive Text elements
            logger.info("Step 6: Merging text blocks...")
            merged_text_elements = self.text_extractor.merge_nearby_text_blocks(text_elements, max_chunk_size=3000)
            logger.info(f"Merged: {len(text_elements)} -> {len(merged_text_elements)} elements")
            
            # Step 7: Creating elements from hierarchy
            logger.info("Step 7: Creating elements from hierarchy...")
            elements = self.hierarchy_builder.create_elements_from_hierarchy(
                hierarchy, merged_text_elements, analyzed_elements, source
            )
            logger.info(f"Created elements: {len(elements)}")
            
            # Step 8: Storing images in metadata
            logger.info("Step 8: Storing images in metadata...")
            elements = self.image_processor.store_images_in_metadata(elements, source)
            logger.info("Images stored")
            
            # Step 8.5: Merge split tables across pages
            detect_merged_tables = self._get_config("table_parsing.detect_merged_tables", True)
            if detect_merged_tables:
                logger.info("Step 8.5: Merging split tables...")
                from ...table_merger import merge_pdf_tables
                # Get page height for determining table position
                page_height = None
                try:
                    pdf_doc = fitz.open(source)
                    if len(pdf_doc) > 0:
                        page = pdf_doc.load_page(0)
                        render_scale = self._get_config("layout_detection.render_scale", 2.0)
                        page_height = page.rect.height * render_scale
                    pdf_doc.close()
                except Exception as e:
                    logger.debug(f"Could not get page height for table merging: {e}")
                
                elements = merge_pdf_tables(elements, page_height)
                logger.info("Tables merged")
            
            # Step 9: Table parsing from Dots OCR HTML
            logger.info("Step 9: Parsing tables...")
            elements = self.table_parser.parse_tables(elements, source, use_dots_ocr_html=True)
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
            use_text_extraction: If True, uses prompt_layout_all_en to extract text, tables (HTML), and formulas.
                               If False, uses prompt_layout_only_en for layout only (text via PyMuPDF).

        Returns:
            List of layout elements with bbox, category, page_num fields.
            If use_text_extraction=True, elements also contain 'text' field from Dots OCR.
        """
        return self.layout_processor.detect_layout_for_all_pages(source, use_text_extraction=use_text_extraction)

    def _reprocess_tables_with_all_en(
        self, source: str, layout_elements: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        For text-extractable PDFs: re-process pages with tables using prompt_layout_all_en to get HTML.
        
        Args:
            source: Path to PDF file.
            layout_elements: List of layout elements from prompt_layout_only_en.
        
        Returns:
            Updated layout elements with table_html for table elements.
        """
        return self.layout_processor.reprocess_tables_with_all_en(source, layout_elements)

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
            
            # Check if text is extractable (to determine if we should use Dots OCR text or PyMuPDF)
            is_text_extractable = self._is_text_extractable(source)
            
            # Last header level with explicit numbering
            last_numbered_level: Optional[int] = None
            # History of previous headers for font size comparison
            previous_headers: List[Dict[str, Any]] = []  # {level, font_size, page_num}
            # Track if we've seen any headers yet (for TITLE detection)
            first_header_seen = False
            
            for element in layout_elements:
                category = element.get("category", "")
                
                if category == "Section-header":
                    # For scanned PDFs, text is already in element from Dots OCR
                    # For PDFs with extractable text, extract via PyMuPDF
                    bbox = element.get("bbox", [])
                    page_num = element.get("page_num", 0)
                    text = element.get("text", "")  # Try to get text from Dots OCR first
                    font_size = None
                    
                    font_properties = None
                    font_size = None
                    if not is_text_extractable and text:
                        # For scanned PDFs: use text from Dots OCR
                        # Still need font_properties for level determination, try to get it
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
                                font_properties = self._get_font_properties(page, rect)
                                font_size = font_properties.get("font_size")
                            except Exception:
                                font_properties = None
                                font_size = None
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
                            
                            # Get font properties for comparison (size, bold, italic)
                            font_properties = self._get_font_properties(page, rect)
                            font_size = font_properties.get("font_size")
                        except Exception as e:
                            logger.warning(f"Error analyzing header: {e}")
                            text = ""
                            font_properties = None
                    
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
                        # Headers ending with colon (e.g., "Tasks:", "Pros:", "Cons:") should be text, not headers
                        if cleaned_text.endswith(':'):
                            element["category"] = "Text"
                            element["text"] = cleaned_text
                            analyzed_elements.append(element)
                            continue
                        
                        # Check if this should be TITLE instead of HEADER
                        # TITLE: first header on first page, no explicit numbering, long text
                        is_title = False
                        if not first_header_seen and page_num == 0:
                            has_numbering = self._has_explicit_numbering(cleaned_text)
                            # If it's a long text (likely title) and has no numbering, it's probably TITLE
                            if not has_numbering and len(cleaned_text) > 30:
                                is_title = True
                                element["category"] = "Title"
                        
                        if is_title:
                            # Convert to TITLE
                            element["text"] = cleaned_text
                            element["element_type"] = ElementType.TITLE
                            element["level"] = None  # Title has no level
                            first_header_seen = True
                        else:
                            # Determine header level (use cleaned text for level detection)
                            # Передаем font_properties для сравнения стилей
                            level = self._determine_header_level(
                                cleaned_text, element, page, rect, last_numbered_level, previous_headers, font_size, font_properties
                            )
                            
                            # If header has explicit numbering, update last_numbered_level
                            if self._has_explicit_numbering(cleaned_text):
                                last_numbered_level = level
                            
                            # Save header info for comparison with subsequent headers
                            # Сохраняем также is_bold для сравнения стилей
                            header_info = {
                                "level": level,
                                "font_size": font_size,
                                "page_num": page_num,
                                "text": cleaned_text,  # Save text to check for letter-based numbering context
                            }
                            if font_properties:
                                header_info["is_bold"] = font_properties.get("is_bold", False)
                                header_info["is_italic"] = font_properties.get("is_italic", False)
                                header_info["font_name"] = font_properties.get("font_name")
                            previous_headers.append(header_info)
                            
                            element_type = getattr(ElementType, f"HEADER_{level}", ElementType.HEADER_1)
                            
                            # Save cleaned text (without markdown symbols)
                            element["text"] = cleaned_text
                            element["level"] = level
                            element["element_type"] = element_type
                            first_header_seen = True
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
                            
                            # Извлекаем свойства шрифта для определения уровня
                            font_properties = self._get_font_properties(page, rect) if page and rect else None
                            font_size = font_properties.get("font_size") if font_properties else None
                            level = self._determine_header_level(text, header, page, rect, None, None, font_size, font_properties)
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
            r'^\d+\.(?!\d)',  # "1. ", "2. ", "3. " (numbered sections, not "1.1")
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

    def _get_font_properties(
        self, page: fitz.Page, rect: fitz.Rect
    ) -> Dict[str, Any]:
        """
        Извлекает свойства шрифта из области текста (размер, жирный, курсив).
        
        Аналогично функции в DOCX пайплайне, которая проверяет стили для определения иерархии заголовков.
        
        Args:
            page: PDF страница.
            rect: Прямоугольник области текста.
        
        Returns:
            Словарь с ключами:
            - font_size: максимальный размер шрифта (float или None)
            - is_bold: True если ≥95% текста жирный (bool)
            - is_italic: True если ≥95% текста курсив (bool)
            - font_name: основное имя шрифта (str или None)
        """
        try:
            text_dict = page.get_text("dict", clip=rect)
            blocks = text_dict.get("blocks", [])
            
            font_sizes = []
            font_names = []
            bold_spans = 0
            italic_spans = 0
            total_spans = 0
            total_text_length = 0
            bold_text_length = 0
            
            for block in blocks:
                if block.get("type") == 0:  # Text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            font_size = span.get("size", 0)
                            if font_size > 0:
                                font_sizes.append(font_size)
                            
                            font_name = span.get("font", "")
                            if font_name:
                                font_names.append(font_name)
                            
                            # Проверяем флаги форматирования
                            flags = span.get("flags", 0)
                            span_text = span.get("text", "")
                            span_length = len(span_text)
                            
                            if span_length > 0:
                                total_spans += 1
                                total_text_length += span_length
                                
                                # Проверяем жирный через флаги (бит 19 = ForceBold)
                                # Или через имя шрифта (содержит "Bold")
                                is_bold_span = False
                                if flags & (1 << 18):  # Bit 19 (0-indexed = 18) = ForceBold
                                    is_bold_span = True
                                elif font_name and "bold" in font_name.lower():
                                    is_bold_span = True
                                
                                if is_bold_span:
                                    bold_spans += 1
                                    bold_text_length += span_length
                                
                                # Проверяем курсив через флаги (бит 7 = Italic)
                                # Или через имя шрифта (содержит "Italic" или "Oblique")
                                if flags & (1 << 6):  # Bit 7 (0-indexed = 6) = Italic
                                    italic_spans += 1
                                elif font_name and ("italic" in font_name.lower() or "oblique" in font_name.lower()):
                                    italic_spans += 1
            
            result = {
                "font_size": max(font_sizes) if font_sizes else None,
                "is_bold": False,
                "is_italic": False,
                "font_name": None
            }
            
            # Определяем основное имя шрифта (самое частое)
            if font_names:
                from collections import Counter
                font_counter = Counter(font_names)
                result["font_name"] = font_counter.most_common(1)[0][0]
            
            # Проверяем жирный: ≥95% текста должен быть жирным (как в DOCX)
            if total_text_length > 0:
                bold_ratio = bold_text_length / total_text_length
                result["is_bold"] = bold_ratio >= 0.95
            
            # Проверяем курсив: ≥95% spans должны быть курсивом
            if total_spans > 0:
                italic_ratio = italic_spans / total_spans
                result["is_italic"] = italic_ratio >= 0.95
            
            return result
        except Exception:
            return {
                "font_size": None,
                "is_bold": False,
                "is_italic": False,
                "font_name": None
            }
    
    def _get_font_size(self, page: fitz.Page, rect: fitz.Rect) -> Optional[float]:
        """
        Extracts maximum font size from header area.
        
        DEPRECATED: Используйте _get_font_properties для получения всех свойств шрифта.
        Оставлено для обратной совместимости.

        Args:
            page: PDF page.
            rect: Header rectangle.

        Returns:
            Maximum font size or None if cannot be determined.
        """
        font_props = self._get_font_properties(page, rect)
        return font_props.get("font_size")

    def _determine_header_level(
        self,
        text: str,
        header: Dict[str, Any],
        page: Optional[fitz.Page],
        rect: Optional[fitz.Rect],
        last_numbered_level: Optional[int] = None,
        previous_headers: Optional[List[Dict[str, Any]]] = None,
        font_size: Optional[float] = None,
        font_properties: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Определяет уровень заголовка на основе текста, нумерации и стилей шрифта.
        
        Аналогично функции в DOCX пайплайне, использует:
        - Нумерацию (приоритет 1)
        - Сравнение размера шрифта с предыдущими заголовками
        - Проверку жирного текста (≥95% текста должен быть жирным)
        - Сравнение стилей с предыдущими заголовками
        
        Если заголовок не имеет явной нумерации и last_numbered_level существует,
        возвращает last_numbered_level + 1.
        
        Если нумерации нет, сравнивает размер шрифта и стили с предыдущими заголовками.

        Args:
            text: Текст заголовка.
            header: Словарь с информацией о заголовке.
            page: PDF страница (может быть None для scanned PDF).
            rect: Прямоугольник заголовка (может быть None для scanned PDF).
            last_numbered_level: Уровень последнего заголовка с явной нумерацией.
            previous_headers: Список предыдущих заголовков для сравнения стилей.
            font_size: Размер шрифта текущего заголовка (устаревший параметр).
            font_properties: Словарь со свойствами шрифта (font_size, is_bold, is_italic, font_name).

        Returns:
            Уровень заголовка (1-6).
        """
        # Numbering analysis
        # Headers with Roman numerals (I, II, III, IV, V, VI, etc.) -> HEADER_1
        # Pattern matches: "I. ", "II. ", "III. ", "IV. ", "V. ", "VI. ", etc.
        if re.match(r'^[IVX]+\.\s+', text, re.IGNORECASE):
            return 1
        # Headers like "1. ", "2. ", "3. " -> HEADER_1 (numbered sections)
        # Pattern: digit(s) + dot + (space or non-digit character)
        # This should match "1. Общая характеристика...", "2. Экспериментальная часть..." etc.
        # Does NOT match "1.1", "1.2" (those are handled below)
        if re.match(r'^\d+\.(?!\d)', text):
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
        # Remove trailing colon before comparison
        text_normalized = text.strip().rstrip(':').strip().upper()
        if text_normalized in SPECIAL_HEADER_1:
            return 1
        
        # Headers like "Приложение А.", "Приложение Б.", "Appendix A.", "Приложение 1." -> HEADER_2
        # Pattern: "Приложение" or "Appendix" + space + letter or digit + optional dot
        # These are subsections under "ПРИЛОЖЕНИЯ" (HEADER_1)
        if re.match(APPENDIX_HEADER_PATTERN, text_normalized):
            return 2
        
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
        
        # Если font_properties не переданы, но есть page и rect, извлекаем их
        if font_properties is None and page is not None and rect is not None:
            font_properties = self._get_font_properties(page, rect)
        
        # Используем font_size из font_properties, если он не передан отдельно
        if font_size is None and font_properties:
            font_size = font_properties.get("font_size")
        
        # Если нет нумерации, сравниваем размер шрифта и стили с предыдущими заголовками
        # Аналогично DOCX пайплайну: используем размер шрифта и жирный текст для определения иерархии
        if font_size is not None:
            if previous_headers:
                # Находим предыдущие заголовки с известным размером шрифта
                previous_with_font = [
                    h for h in previous_headers
                    if h.get("font_size") is not None
                ]
                
                if previous_with_font:
                    # Берем последний заголовок с известным размером шрифта
                    last_header = previous_with_font[-1]
                    last_font_size = last_header.get("font_size")
                    last_level = last_header.get("level", 1)
                    last_is_bold = last_header.get("is_bold", False)
                    
                    # Получаем информацию о текущем заголовке
                    current_is_bold = False
                    if font_properties:
                        current_is_bold = font_properties.get("is_bold", False)
                    
                    # Сравниваем размеры шрифта и стили
                    # Если шрифт значительно больше (>= 2pt разница) - более высокий уровень
                    if font_size >= last_font_size + 2:
                        return max(1, last_level - 1)
                    # Если шрифт значительно меньше (>= 2pt разница) - более низкий уровень
                    elif font_size <= last_font_size - 2:
                        return min(6, last_level + 1)
                    # Если размер примерно одинаковый - сравниваем стили
                    else:
                        # Если текущий заголовок жирный, а предыдущий нет - более высокий уровень
                        if current_is_bold and not last_is_bold:
                            return max(1, last_level - 1)
                        # Если текущий заголовок не жирный, а предыдущий жирный - более низкий уровень
                        elif not current_is_bold and last_is_bold:
                            return min(6, last_level + 1)
                        # Если стили одинаковые - тот же уровень
                        else:
                            return last_level
            
            # Если нет предыдущих заголовков для сравнения, используем абсолютные значения
            # Аналогично DOCX: большие жирные заголовки обычно HEADER_1
            current_is_bold = False
            if font_properties:
                current_is_bold = font_properties.get("is_bold", False)
            
            # Font >= 16pt и жирный -> обычно HEADER_1
            if font_size >= 16 and current_is_bold:
                return 1
            # Font >= 16pt -> обычно HEADER_1 или HEADER_2
            elif font_size >= 16:
                return 1
            # Font 12-16pt и жирный -> обычно HEADER_2
            elif font_size >= 12 and current_is_bold:
                return 2
            # Font 12-16pt -> обычно HEADER_2 или HEADER_3
            elif font_size >= 12:
                return 2
            # Font < 12pt и жирный -> обычно HEADER_3
            elif current_is_bold:
                return 3
            # Font < 12pt -> обычно HEADER_3
            else:
                return 3
        
        # Если нет информации о размере шрифта, но есть информация о стиле
        # Используем жирный текст как индикатор заголовка (как в DOCX)
        if font_properties:
            current_is_bold = font_properties.get("is_bold", False)
            if current_is_bold and previous_headers:
                # Если текущий заголовок жирный, а предыдущий нет - более высокий уровень
                last_header = previous_headers[-1] if previous_headers else None
                if last_header:
                    last_is_bold = last_header.get("is_bold", False)
                    last_level = last_header.get("level", 1)
                    if not last_is_bold:
                        return max(1, last_level - 1)
                    else:
                        return last_level
        
        # По умолчанию HEADER_1
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
                            # Remove markdown formatting (**text** or __text__) from Dots OCR output
                            # BUT: Do NOT apply to Formula - LaTeX may contain *, **, _, __ as part of syntax
                            # Note: This is Dots OCR specific - custom layout detectors may not return markdown
                            if category != "Formula":
                                # Use Dots OCR utility for markdown removal
                                try:
                                    from documentor.ocr.dots_ocr.markdown_formatting import remove_markdown_formatting
                                    text = remove_markdown_formatting(text)
                                except ImportError:
                                    # Fallback if utils not available
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
                        # Remove markdown formatting (**text** or __text__) from Dots OCR output
                        # Note: This is Dots OCR specific - custom layout detectors may not return markdown
                        try:
                            from documentor.ocr.dots_ocr.markdown_formatting import remove_markdown_formatting
                            cleaned_text = remove_markdown_formatting(text)
                        except ImportError:
                            # Fallback if utils not available
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
                    # HTML is in table_html field (from prompt_layout_all_en re-processing for text-extractable PDFs)
                    # or in text field (from prompt_layout_all_en for scanned PDFs)
                    table_html = child.get("table_html", "") or child.get("text", "")
                    
                    # Skip table if HTML is empty (layout detector didn't extract it)
                    if not table_html and not self.table_parser.custom_table_parser:
                        logger.warning(
                            f"Table element on page {page_num + 1} has empty HTML. "
                            f"Layout detector may not support table extraction. "
                            f"Consider providing a custom table_parser."
                        )
                        # Skip this table element - don't create element without table data
                        continue
                    
                    element = self._create_element(
                        type=ElementType.TABLE,
                        content="",  # will be filled during parsing
                        parent_id=current_parent_id,
                        metadata={
                            "source": "ocr",
                            "bbox": bbox,
                            "page_num": page_num,
                            "category": category,
                            "table_html": table_html,  # Store HTML for parsing (may be empty if custom parser will be used)
                        },
                    )
                    elements.append(element)
                elif category == "Formula":
                    # Extract formula using custom extractor or from layout elements
                    if self.formula_extractor and len(bbox) >= 4:
                        # Use custom formula extractor
                        try:
                            pdf_document = fitz.open(source)
                            try:
                                page = pdf_document.load_page(page_num)
                                render_scale = self._get_config("layout_detection.render_scale", 2.0)
                                
                                # Convert bbox to original PDF scale and render formula region
                                x1, y1, x2, y2 = (
                                    bbox[0] / render_scale,
                                    bbox[1] / render_scale,
                                    bbox[2] / render_scale,
                                    bbox[3] / render_scale,
                                )
                                rect = fitz.Rect(x1, y1, x2, y2)
                                
                                # Render formula region
                                mat = fitz.Matrix(render_scale, render_scale)
                                pix = page.get_pixmap(matrix=mat, clip=rect)
                                formula_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                                
                                # Extract formula using custom extractor
                                formula_latex = self.formula_extractor.extract_formula(formula_image, bbox)
                            finally:
                                pdf_document.close()
                        except Exception as e:
                            logger.warning(f"Error using custom formula extractor: {e}, falling back to layout text")
                            # Fallback to text from layout
                            formula_latex = child.get("text", "")
                    else:
                        # Use formula text from layout elements (from Dots OCR or custom layout detector)
                        formula_latex = child.get("text", "")
                    
                    # DO NOT remove markdown formatting from formulas!
                    # LaTeX syntax may contain *, **, _, __ as valid operators/symbols
                    # (e.g., x^2 * y^2, x_1, etc.)
                    # Only strip whitespace
                    formula_latex = formula_latex.strip()
                    
                    # Skip formula if text is empty (layout detector didn't extract it)
                    if not formula_latex:
                        logger.warning(
                            f"Formula element on page {page_num + 1} has empty text. "
                            f"Layout detector may not support formula extraction. "
                            f"Consider providing a custom formula_extractor."
                        )
                        # Skip this formula element - don't create empty element
                        continue
                    
                    element = self._create_element(
                        type=ElementType.TEXT,  # Formula is stored as TEXT with LaTeX in metadata
                        content=formula_latex,  # LaTeX content
                        parent_id=current_parent_id,
                        metadata={
                            "source": "ocr" if not self.formula_extractor else "custom_extractor",
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
                    # Note: This is Dots OCR specific - custom layout detectors may not return markdown
                    try:
                        from documentor.ocr.dots_ocr.markdown_formatting import remove_markdown_formatting
                        cleaned_list_text = remove_markdown_formatting(list_text)
                    except ImportError:
                        # Fallback if utils not available
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
                    # Remove markdown formatting (**text** or __text__) from Dots OCR output
                    # Note: This is Dots OCR specific - custom layout detectors may not return markdown
                    try:
                        from documentor.ocr.dots_ocr.markdown_formatting import remove_markdown_formatting
                        cleaned_text = remove_markdown_formatting(text)
                    except ImportError:
                        # Fallback if utils not available
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
                    # Remove markdown formatting (**text** or __text__) from Dots OCR output
                    # Note: This is Dots OCR specific - custom layout detectors may not return markdown
                    try:
                        from documentor.ocr.dots_ocr.markdown_formatting import remove_markdown_formatting
                        cleaned_text = remove_markdown_formatting(text)
                    except ImportError:
                        # Fallback if utils not available
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
        
        # Пересвязываем caption, table и image по новой логике
        elements = self._link_caption_table_image(elements)
        
        # Подвязываем элементы без родителя к TITLE, если есть TITLE и еще нет header
        elements = self._link_elements_to_title(elements)
        
        return elements

    def _link_caption_table_image(self, elements: List[Element]) -> List[Element]:
        """
        Связывает caption, table и image элементы по новой логике:
        - Если встретили caption, ищем ближайший table или image и связываем их
        - Если встретили table или image, ищем ближайший caption и связываем их
        - У table и image родитель всегда caption (если найден)
        - У caption родитель всегда header
        - К связанным элементам больше нельзя подвязывать другие элементы
        
        Args:
            elements: Список элементов
            
        Returns:
            Список элементов с обновленными parent_id
        """
        from typing import Optional
        
        # Находим все caption, table и image элементы
        caption_elements = [e for e in elements if e.type == ElementType.CAPTION]
        table_elements = [e for e in elements if e.type == ElementType.TABLE]
        image_elements = [e for e in elements if e.type == ElementType.IMAGE]
        
        # Множества для отслеживания уже связанных элементов
        linked_captions = set()
        linked_tables = set()
        linked_images = set()
        
        # Создаем индекс элементов по позиции для быстрого поиска ближайших
        element_positions = {}
        for i, elem in enumerate(elements):
            element_positions[elem.id] = i
        
        def find_nearest_table_or_image(caption_elem: Element, start_idx: int) -> Optional[Element]:
            """Находит ближайший table или image для caption только среди соседних элементов."""
            # Проверяем только соседние элементы (предыдущий и следующий)
            # Предыдущий элемент
            if start_idx > 0:
                prev_elem = elements[start_idx - 1]
                if prev_elem.type == ElementType.TABLE and prev_elem.id not in linked_tables:
                    # Проверяем, что на той же странице
                    caption_page = caption_elem.metadata.get('page_num', 0)
                    prev_page = prev_elem.metadata.get('page_num', 0)
                    if caption_page == prev_page:
                        return prev_elem
                elif prev_elem.type == ElementType.IMAGE and prev_elem.id not in linked_images:
                    # Проверяем, что на той же странице
                    caption_page = caption_elem.metadata.get('page_num', 0)
                    prev_page = prev_elem.metadata.get('page_num', 0)
                    if caption_page == prev_page:
                        return prev_elem
            
            # Следующий элемент
            if start_idx < len(elements) - 1:
                next_elem = elements[start_idx + 1]
                if next_elem.type == ElementType.TABLE and next_elem.id not in linked_tables:
                    # Проверяем, что на той же странице
                    caption_page = caption_elem.metadata.get('page_num', 0)
                    next_page = next_elem.metadata.get('page_num', 0)
                    if caption_page == next_page:
                        return next_elem
                elif next_elem.type == ElementType.IMAGE and next_elem.id not in linked_images:
                    # Проверяем, что на той же странице
                    caption_page = caption_elem.metadata.get('page_num', 0)
                    next_page = next_elem.metadata.get('page_num', 0)
                    if caption_page == next_page:
                        return next_elem
            
            return None
        
        def find_nearest_caption(elem: Element, start_idx: int) -> Optional[Element]:
            """Находит ближайший caption для table или image только среди соседних элементов."""
            # Проверяем только соседние элементы (предыдущий и следующий)
            # Предыдущий элемент
            if start_idx > 0:
                prev_elem = elements[start_idx - 1]
                if prev_elem.type == ElementType.CAPTION:
                    # Проверяем, что на той же странице
                    elem_page = elem.metadata.get('page_num', 0)
                    prev_page = prev_elem.metadata.get('page_num', 0)
                    if elem_page == prev_page:
                        return prev_elem
            
            # Следующий элемент
            if start_idx < len(elements) - 1:
                next_elem = elements[start_idx + 1]
                if next_elem.type == ElementType.CAPTION:
                    # Проверяем, что на той же странице
                    elem_page = elem.metadata.get('page_num', 0)
                    next_page = next_elem.metadata.get('page_num', 0)
                    if elem_page == next_page:
                        return next_elem
            
            return None
        
        # Обрабатываем caption: ищем все соседние table или image элементы
        for caption_elem in caption_elements:
            if caption_elem.id in linked_captions:
                continue
            
            caption_idx = element_positions.get(caption_elem.id, -1)
            if caption_idx < 0:
                continue
            
            # Находим все соседние table или image элементы (может быть несколько подряд)
            linked_to_this_caption = []
            
            # Проверяем предыдущий элемент
            if caption_idx > 0:
                prev_elem = elements[caption_idx - 1]
                if prev_elem.type == ElementType.TABLE and prev_elem.id not in linked_tables:
                    caption_page = caption_elem.metadata.get('page_num', 0)
                    prev_page = prev_elem.metadata.get('page_num', 0)
                    if caption_page == prev_page:
                        linked_to_this_caption.append(prev_elem)
                elif prev_elem.type == ElementType.IMAGE and prev_elem.id not in linked_images:
                    caption_page = caption_elem.metadata.get('page_num', 0)
                    prev_page = prev_elem.metadata.get('page_num', 0)
                    if caption_page == prev_page:
                        linked_to_this_caption.append(prev_elem)
            
            # Проверяем следующие элементы подряд (может быть несколько таблиц/изображений)
            current_idx = caption_idx + 1
            while current_idx < len(elements):
                next_elem = elements[current_idx]
                # Если это не table/image, прекращаем поиск
                if next_elem.type not in [ElementType.TABLE, ElementType.IMAGE]:
                    break
                # Если элемент уже связан, прекращаем поиск
                if (next_elem.type == ElementType.TABLE and next_elem.id in linked_tables) or \
                   (next_elem.type == ElementType.IMAGE and next_elem.id in linked_images):
                    break
                # Проверяем страницу
                caption_page = caption_elem.metadata.get('page_num', 0)
                next_page = next_elem.metadata.get('page_num', 0)
                if caption_page != next_page:
                    break
                # Добавляем к связанным
                linked_to_this_caption.append(next_elem)
                current_idx += 1
            
            # Связываем все найденные элементы с caption
            if linked_to_this_caption:
                for elem in linked_to_this_caption:
                    elem.parent_id = caption_elem.id
                    if elem.type == ElementType.TABLE:
                        linked_tables.add(elem.id)
                    else:
                        linked_images.add(elem.id)
                
                # Находим header для caption (родитель должен быть header)
                # Если у caption уже есть parent_id, проверяем, что это header
                current_parent_id = caption_elem.parent_id
                if current_parent_id:
                    parent_elem = next((e for e in elements if e.id == current_parent_id), None)
                    if parent_elem and parent_elem.type not in [ElementType.HEADER_1, ElementType.HEADER_2, 
                                                                 ElementType.HEADER_3, ElementType.HEADER_4,
                                                                 ElementType.HEADER_5, ElementType.HEADER_6]:
                        # Если родитель не header, ищем ближайший header
                        # Ищем header перед caption
                        best_header = None
                        for i in range(caption_idx - 1, -1, -1):
                            if i < len(elements):
                                prev_elem = elements[i]
                                if prev_elem.type in [ElementType.HEADER_1, ElementType.HEADER_2,
                                                      ElementType.HEADER_3, ElementType.HEADER_4,
                                                      ElementType.HEADER_5, ElementType.HEADER_6]:
                                    best_header = prev_elem
                                    break
                        if best_header:
                            caption_elem.parent_id = best_header.id
                
                # Помечаем caption как связанный только после того, как связали все элементы
                linked_captions.add(caption_elem.id)
        
        # Обрабатываем table: ищем ближайший caption
        for table_elem in table_elements:
            if table_elem.id in linked_tables:
                continue
            
            table_idx = element_positions.get(table_elem.id, -1)
            if table_idx < 0:
                continue
            
            # Находим ближайший caption
            nearest_caption = find_nearest_caption(table_elem, table_idx)
            
            if nearest_caption:
                # Связываем: table -> caption
                table_elem.parent_id = nearest_caption.id
                
                # Убеждаемся, что у caption родитель - header
                if nearest_caption.parent_id:
                    parent_elem = next((e for e in elements if e.id == nearest_caption.parent_id), None)
                    if parent_elem and parent_elem.type not in [ElementType.HEADER_1, ElementType.HEADER_2,
                                                                 ElementType.HEADER_3, ElementType.HEADER_4,
                                                                 ElementType.HEADER_5, ElementType.HEADER_6]:
                        # Ищем ближайший header
                        caption_idx = element_positions.get(nearest_caption.id, -1)
                        best_header = None
                        for i in range(caption_idx - 1, -1, -1):
                            if i < len(elements):
                                prev_elem = elements[i]
                                if prev_elem.type in [ElementType.HEADER_1, ElementType.HEADER_2,
                                                      ElementType.HEADER_3, ElementType.HEADER_4,
                                                      ElementType.HEADER_5, ElementType.HEADER_6]:
                                    best_header = prev_elem
                                    break
                        if best_header:
                            nearest_caption.parent_id = best_header.id
                
                # Помечаем как связанные
                linked_tables.add(table_elem.id)
                linked_captions.add(nearest_caption.id)
        
        # Обрабатываем image: ищем ближайший caption
        for image_elem in image_elements:
            if image_elem.id in linked_images:
                continue
            
            image_idx = element_positions.get(image_elem.id, -1)
            if image_idx < 0:
                continue
            
            # Находим ближайший caption
            nearest_caption = find_nearest_caption(image_elem, image_idx)
            
            if nearest_caption:
                # Связываем: image -> caption
                image_elem.parent_id = nearest_caption.id
                
                # Убеждаемся, что у caption родитель - header
                if nearest_caption.parent_id:
                    parent_elem = next((e for e in elements if e.id == nearest_caption.parent_id), None)
                    if parent_elem and parent_elem.type not in [ElementType.HEADER_1, ElementType.HEADER_2,
                                                                 ElementType.HEADER_3, ElementType.HEADER_4,
                                                                 ElementType.HEADER_5, ElementType.HEADER_6]:
                        # Ищем ближайший header
                        caption_idx = element_positions.get(nearest_caption.id, -1)
                        best_header = None
                        for i in range(caption_idx - 1, -1, -1):
                            if i < len(elements):
                                prev_elem = elements[i]
                                if prev_elem.type in [ElementType.HEADER_1, ElementType.HEADER_2,
                                                      ElementType.HEADER_3, ElementType.HEADER_4,
                                                      ElementType.HEADER_5, ElementType.HEADER_6]:
                                    best_header = prev_elem
                                    break
                        if best_header:
                            nearest_caption.parent_id = best_header.id
                
                # Помечаем как связанные
                linked_images.add(image_elem.id)
                linked_captions.add(nearest_caption.id)
        
        return elements

    def _link_elements_to_title(self, elements: List[Element]) -> List[Element]:
        """
        Подвязывает элементы без родителя к TITLE, если есть TITLE и еще нет header.
        
        Логика:
        - Если есть TITLE элемент
        - И есть элементы без родителя (parent_id is None)
        - И эти элементы идут до первого header в документе
        - То подвязываем их к TITLE
        
        Args:
            elements: Список элементов
            
        Returns:
            Список элементов с обновленными parent_id
        """
        # Находим первый TITLE элемент
        title_elem = None
        title_idx = -1
        for i, elem in enumerate(elements):
            if elem.type == ElementType.TITLE:
                title_elem = elem
                title_idx = i
                break
        
        # Если нет TITLE, ничего не делаем
        if not title_elem:
            return elements
        
        # Находим первый header элемент после TITLE
        first_header_idx = -1
        for i in range(title_idx + 1, len(elements)):
            elem = elements[i]
            if elem.type in [ElementType.HEADER_1, ElementType.HEADER_2,
                             ElementType.HEADER_3, ElementType.HEADER_4,
                             ElementType.HEADER_5, ElementType.HEADER_6]:
                first_header_idx = i
                break
        
        # Подвязываем элементы без родителя к TITLE
        # Только те, которые идут после TITLE и до первого header (или до конца, если header нет)
        end_idx = first_header_idx if first_header_idx >= 0 else len(elements)
        
        for i in range(title_idx + 1, end_idx):
            elem = elements[i]
            # Пропускаем сам TITLE и элементы, которые уже имеют родителя
            if elem.type == ElementType.TITLE or elem.parent_id is not None:
                continue
            
            # Подвязываем к TITLE
            elem.parent_id = title_elem.id
        
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
        self, elements: List[Element], source: str, use_dots_ocr_html: bool = True
    ) -> List[Element]:
        """
        Parses tables from Dots OCR HTML.

        Args:
            elements: List of elements.
            source: Path to PDF file.
            use_dots_ocr_html: If True, uses HTML from Dots OCR (prompt_layout_all_en).
                              Always True now.

        Returns:
            List of elements with parsed tables.
        """
        table_elements = [e for e in elements if e.type == ElementType.TABLE]
        
        if not table_elements:
            return elements
        
        # NOTE: detect_merged_tables works with markdown, currently disabled
        # detect_merged = self._get_config("table_parsing.detect_merged_tables", True)
        
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
                    
                    # Parse table: use HTML from Dots OCR
                    table_html = None
                    success = False
                    
                    # Try to get HTML from element metadata (stored during element creation)
                    table_html = element.metadata.get("table_html")
                    if table_html:
                        # Validate HTML
                        from documentor.ocr.dots_ocr.html_table_parser import parse_table_from_html
                        _, success = parse_table_from_html(table_html)
                        if success:
                            logger.debug(f"Table {element.id} validated from Dots OCR HTML")
                    
                    if not success or not table_html:
                        logger.warning(f"Failed to parse table {element.id} - no HTML from Dots OCR")
                        element.content = ""
                        element.metadata["parsing_error"] = "Failed to parse table: no HTML from Dots OCR"
                        continue
                    
                    # Store HTML in content
                    element.content = table_html
                    element.metadata["parsing_method"] = "dots_ocr_html"
                    
                    logger.debug(f"Table {element.id} successfully parsed")
                
                except Exception as e:
                    logger.error(f"Error parsing table {element.id}: {e}")
                    element.content = ""
                    element.metadata["parsing_error"] = str(e)
                    continue
        
        finally:
            pdf_document.close()
        
        return elements

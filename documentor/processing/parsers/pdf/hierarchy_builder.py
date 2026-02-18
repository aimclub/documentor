"""
PDF hierarchy building processor.

Handles hierarchy building and header level analysis for PDF documents.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import fitz

from ....domain import Element, ElementType
from ....utils.config_loader import ConfigLoader
from ....utils.header_consts import SPECIAL_HEADER_1, APPENDIX_HEADER_PATTERN

# URL pattern for extracting links from text
URL_PATTERN = re.compile(
    r'(?:https?://|www\.|ftp://)[^\s<>"{}|\\^`\[\]]+[^\s<>"{}|\\^`\[\].,;:!?]',
    re.IGNORECASE
)

logger = logging.getLogger(__name__)


class PdfHierarchyBuilder:
    """
    Processor for PDF hierarchy building.
    
    Handles:
    - Header level analysis
    - Hierarchy building from section headers
    - Element creation from hierarchy
    """

    def __init__(self, config: Dict[str, Any], id_generator) -> None:
        """
        Initialize hierarchy builder.
        
        Args:
            config: Configuration dictionary.
            id_generator: Element ID generator.
        """
        self.config = config
        self.id_generator = id_generator

    def _get_config(self, key: str, default: Any = None) -> Any:
        """Gets value from configuration."""
        return ConfigLoader.get_config_value(self.config, key, default)

    def build_hierarchy_from_section_headers(
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

    def analyze_header_levels_from_elements(
        self, layout_elements: List[Dict[str, Any]], source: str, is_text_extractable: bool
    ) -> List[Dict[str, Any]]:
        """
        Analyzes header levels from element list (before building hierarchy).
        
        Considers context: if there is a header with numbering (e.g., "1.2"),
        following headers without numbering get level + 1.

        Args:
            layout_elements: List of layout elements.
            source: Path to PDF file.
            is_text_extractable: Whether PDF has extractable text.

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
                    # For scanned PDFs, text is already in element from OCR
                    # For PDFs with extractable text, extract via PyMuPDF
                    bbox = element.get("bbox", [])
                    page_num = element.get("page_num", 0)
                    text = element.get("text", "")  # Try to get text from OCR first
                    font_size = None
                    
                    if not is_text_extractable and text:
                        # For scanned PDFs: use text from OCR
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
                        cleaned_text = self._clean_header_text(text)
                        
                        # Check if header ends with colon - if so, convert to Text (not a header)
                        if cleaned_text.endswith(':'):
                            element["category"] = "Text"
                            element["text"] = cleaned_text
                            analyzed_elements.append(element)
                            continue
                        
                        # Determine header level (use cleaned text for level detection)
                        # Check if header has explicit numbering first
                        has_explicit_numbering = self._has_explicit_numbering(cleaned_text)
                        
                        # Check if header is a special header (always HEADER_1)
                        cleaned_text_upper = cleaned_text.strip().upper()
                        is_special_header = cleaned_text_upper in SPECIAL_HEADER_1
                        
                        level = self._determine_header_level(
                            cleaned_text, element, None, None, last_numbered_level, previous_headers, font_size
                        )
                        
                        # If header has explicit numbering, update last_numbered_level
                        # and ensure the level is not overridden by context
                        if has_explicit_numbering:
                            last_numbered_level = level
                            # Don't override level for explicitly numbered headers
                        elif is_special_header:
                            # Special headers are always HEADER_1, don't override
                            level = 1
                            last_numbered_level = 1
                        else:
                            # If header has no explicit numbering and we have a numbered header context,
                            # ensure it's at least one level deeper than the last numbered header
                            if last_numbered_level is not None:
                                # Ensure level is at least last_numbered_level + 1
                                level = max(level, min(6, last_numbered_level + 1))
                        
                        # Save header info for comparison with subsequent headers
                        previous_headers.append({
                            "level": level,
                            "font_size": font_size,
                            "page_num": page_num,
                            "text": cleaned_text,
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
                            "text": "",
                        })
                
                    # Add header element to analyzed_elements
                    analyzed_elements.append(element)
                else:
                    # Add non-header elements to analyzed_elements
                    analyzed_elements.append(element)
            
            return analyzed_elements
        finally:
            pdf_document.close()

    def _clean_header_text(self, text: str) -> str:
        """Cleans header text by removing markdown formatting."""
        # Remove all # symbols from the beginning (OCR may add ## to headers)
        cleaned_text = text.strip()
        while cleaned_text.startswith('#'):
            cleaned_text = cleaned_text.lstrip('#').strip()
        
        # Remove markdown bold formatting (**text** or __text__)
        cleaned_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned_text)  # **bold** -> bold
        cleaned_text = re.sub(r'__([^_]+)__', r'\1', cleaned_text)  # __bold__ -> bold
        # Also handle single asterisks/underscores
        cleaned_text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'\1', cleaned_text)  # *italic* -> italic
        cleaned_text = re.sub(r'(?<!_)_([^_]+)_(?!_)', r'\1', cleaned_text)  # _italic_ -> italic
        cleaned_text = cleaned_text.strip()
        
        return cleaned_text

    def _get_font_size(self, page: fitz.Page, rect: fitz.Rect) -> Optional[float]:
        """Gets average font size from text in rectangle."""
        try:
            text_dict = page.get_text("dict", clip=rect)
            font_sizes = []
            
            for block in text_dict.get("blocks", []):
                if "lines" not in block:
                    continue
                for line in block["lines"]:
                    for span in line.get("spans", []):
                        size = span.get("size", 0)
                        if size > 0:
                            font_sizes.append(size)
            
            if font_sizes:
                return sum(font_sizes) / len(font_sizes)
        except Exception:
            pass
        
        return None

    def _has_explicit_numbering(self, text: str) -> bool:
        """Checks if header has explicit numbering (e.g., "1.2", "A.1", "I.", "3", "B Formulation")."""
        text_stripped = text.strip()
        
        # Check for various numbering patterns
        patterns = [
            r'^\d+\.\d+',  # "1.2"
            r'^\d+\.',  # "1."
            r'^\d+\s+[A-ZА-ЯЁ]',  # "3 SAGA", "2 Evaluating" - single number followed by capital letter
            r'^[IVX]+\.',  # "I.", "II.", "III."
            r'^[A-Z]\.\d+',  # "A.1"
            r'^[A-Z]\.',  # "A."
            r'^[A-Z]\s+[A-Z]',  # "B Formulation", "A Methodologies" - single letter followed by space and capital letter
        ]
        
        for pattern in patterns:
            if re.match(pattern, text_stripped, re.IGNORECASE):
                return True
        
        return False

    def _determine_header_level(
        self,
        text: str,
        header: Dict[str, Any],
        page: Optional[fitz.Page],
        rect: Optional[fitz.Rect],
        last_numbered_level: Optional[int] = None,
        previous_headers: Optional[List[Dict[str, Any]]] = None,
        font_size: Optional[float] = None,
    ) -> int:
        """
        Determines header level based on text content, numbering, and context.
        
        Args:
            text: Header text.
            header: Header element dictionary.
            page: PDF page (optional, for font size analysis).
            rect: Bounding box rectangle (optional).
            last_numbered_level: Last header level with explicit numbering.
            previous_headers: List of previous headers for context.
            font_size: Font size of header text.
        
        Returns:
            Header level (1-6).
        """
        if previous_headers is None:
            previous_headers = []
        
        # Check special headers first (always HEADER_1)
        text_upper = text.strip().upper()
        if text_upper in SPECIAL_HEADER_1:
            return 1
        
        # Check for appendix headers
        if re.match(APPENDIX_HEADER_PATTERN, text_upper):
            return 2
        
        # Check for explicit numbering patterns
        # Headers like "I. ", "II. ", "III. ", "IV. ", "V. ", "VI. ", etc.
        if re.match(r'^[IVX]+\.\s+', text, re.IGNORECASE):
            return 1
        
        # Headers like "1", "2", "3" -> HEADER_1
        text_stripped = text.strip()
        if re.match(r'^\d+\s+[A-ZА-ЯЁ]', text_stripped):
            return 1
        
        # Headers like "A.1", "B.1", "C.1" -> HEADER_3
        if re.match(r'^[A-Z]\.\d+\s+', text):
            return 3
        
        # Headers like "1.1", "1.2" -> HEADER_2
        if re.match(r'^\d+\.\d+\s+', text):
            return 2
        
        # Headers like "A. ", "B. ", "C. " -> HEADER_2
        if re.match(r'^[A-Z]\.\s+', text):
            return 2
        
        # Headers like "A ", "B ", "C " -> HEADER_2
        if re.match(r'^[A-Z]\s+[A-Z]', text):
            return 2
        
        # Headers like "1.1.1", "1.1.2" -> HEADER_3
        if re.match(r'^\d+\.\d+\.\d+\s+', text):
            return 3
        
        # Headers like "1.1.1.1" -> HEADER_4
        if re.match(r'^\d+\.\d+\.\d+\.\d+\s+', text):
            return 4
        
        # If header has no explicit numbering and we have a numbered header context,
        # ensure it's at least one level deeper than the last numbered header
        if last_numbered_level is not None:
            # Use font size and position if available
            use_font_size = self._get_config("header_analysis.use_font_size", True)
            use_position = self._get_config("header_analysis.use_position", True)
            
            if use_font_size and font_size is not None and previous_headers:
                # Compare with previous headers
                for prev_header in reversed(previous_headers):
                    prev_font_size = prev_header.get("font_size")
                    if prev_font_size is not None:
                        min_font_size_diff = self._get_config("header_analysis.min_font_size_diff", 2)
                        if font_size > prev_font_size + min_font_size_diff:
                            # Larger font -> higher level (lower number)
                            # But ensure it's at least last_numbered_level + 1
                            font_based_level = max(1, prev_header["level"] - 1)
                            return max(font_based_level, min(6, last_numbered_level + 1))
                        elif font_size < prev_font_size - min_font_size_diff:
                            # Smaller font -> lower level (higher number)
                            # This is fine, can be deeper than last_numbered_level + 1
                            return min(6, prev_header["level"] + 1)
                        else:
                            # Similar font size -> same level or deeper
                            # But ensure it's at least last_numbered_level + 1
                            return max(prev_header["level"], min(6, last_numbered_level + 1))
            
            # Default: if there was a numbered header, use level + 1
            return min(6, last_numbered_level + 1)
        
        # Use font size and position if available (when no numbered header context)
        use_font_size = self._get_config("header_analysis.use_font_size", True)
        use_position = self._get_config("header_analysis.use_position", True)
        
        if use_font_size and font_size is not None and previous_headers:
            # Compare with previous headers
            for prev_header in reversed(previous_headers):
                prev_font_size = prev_header.get("font_size")
                if prev_font_size is not None:
                    min_font_size_diff = self._get_config("header_analysis.min_font_size_diff", 2)
                    if font_size > prev_font_size + min_font_size_diff:
                        # Larger font -> higher level (lower number)
                        return max(1, prev_header["level"] - 1)
                    elif font_size < prev_font_size - min_font_size_diff:
                        # Smaller font -> lower level (higher number)
                        return min(6, prev_header["level"] + 1)
                    else:
                        # Similar font size -> same level
                        return prev_header["level"]
        
        # Default to HEADER_1
        return 1

    def create_elements_from_hierarchy(
        self,
        hierarchy: List[Dict[str, Any]],
        merged_text_elements: List[Dict[str, Any]],
        layout_elements: List[Dict[str, Any]],
        source: str,
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
                # Get text from header - it should be there from analyze_header_levels_from_elements
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
                    # HTML is in table_html field (from OCR re-processing for text-extractable PDFs)
                    # or in text field (from OCR for scanned PDFs)
                    table_html = child.get("table_html", "") or child.get("text", "")
                    
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
                    # Formulas are in LaTeX format from OCR
                    formula_latex = child.get("text", "")  # LaTeX from OCR
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
                    # List items from OCR
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

    def _create_element(
        self,
        type: ElementType,
        content: str,
        parent_id: Optional[str],
        metadata: Dict[str, Any],
    ) -> Element:
        """Creates an Element using the ID generator."""
        element_id = self.id_generator.next_id()
        return Element(
            id=element_id,
            type=type,
            content=content,
            parent_id=parent_id,
            metadata=metadata,
        )

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

"""
PDF hierarchy building processor.

Handles hierarchy building and header level analysis for PDF documents.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import fitz

from ....domain import Element, ElementType
from documentor.config.loader import ConfigLoader
from ...headers.constants import SPECIAL_HEADER_1, APPENDIX_HEADER_PATTERN

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
        
        Uses header rules (similar to DOCX parser) to filter out non-header elements
        based on font properties (bold, italic, font size, caps lock, etc.).

        Args:
            layout_elements: List of layout elements.
            source: Path to PDF file.
            is_text_extractable: Whether PDF has extractable text.

        Returns:
            List of elements with determined header levels.
        """
        from .header_finder import (
            build_header_rules, 
            _is_header_by_properties, 
            extract_text_properties, 
            determine_header_level_by_font_name,
            determine_level_by_numbering,
            _is_numbered_header
        )
        
        pdf_document = fitz.open(source)
        try:
            analyzed_elements: List[Dict[str, Any]] = []
            render_scale = self._get_config("layout_detection.render_scale", 2.0)
            
            # First pass: collect all Section-header elements to build rules
            header_positions: List[Dict[str, Any]] = []
            
            # Last header level with explicit numbering
            last_numbered_level: Optional[int] = None
            # History of previous headers for font size comparison
            previous_headers: List[Dict[str, Any]] = []  # {level, font_size, page_num}
            # Track if we've seen any headers yet (for TITLE detection)
            first_header_seen = False
            # Font name для заголовков первого уровня (определяется из специальных заголовков: Abstract, Introduction)
            level_1_font_name: Optional[str] = None
            
            for element in layout_elements:
                category = element.get("category", "")
                
                if category == "Section-header":
                    # For scanned PDFs, text is already in element from OCR
                    # For PDFs with extractable text, extract via PyMuPDF
                    bbox = element.get("bbox", [])
                    page_num = element.get("page_num", 0)
                    text = element.get("text", "")  # Try to get text from OCR first
                    font_size = None
                    
                    font_properties = None
                    font_size = None
                    if not is_text_extractable and text:
                        # For scanned PDFs: use text from OCR
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
                            font_size = None
                    
                    if text:
                        # Remove markdown formatting from header text
                        cleaned_text = self._clean_header_text(text)
                        
                        # Check if header ends with colon - if so, convert to Text (not a header)
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
                            # Check if header is a special header (always HEADER_1) - highest priority
                            # Remove trailing colon before comparison
                            cleaned_text_normalized = cleaned_text.strip().rstrip(':').strip().upper()
                            is_special_header = cleaned_text_normalized in SPECIAL_HEADER_1
                            
                            # УМНАЯ ЛОГИКА: Сначала проверяем, пронумерован ли заголовок
                            is_numbered = _is_numbered_header(cleaned_text)
                            
                            # ПРИОРИТЕТ 1: Специальные заголовки (Abstract, Introduction) - всегда HEADER_1
                            level = None
                            if is_special_header:
                                level = 1
                                if font_properties:
                                    special_font_name = font_properties.get("font_name")
                                    if special_font_name and not level_1_font_name:
                                        level_1_font_name = special_font_name
                                        logger.debug(f"Detected level 1 font name from special header '{cleaned_text}': {level_1_font_name}")
                            
                            # ПРИОРИТЕТ 2: Если заголовок ПРОНУМЕРОВАН - определяем уровень по нумерации
                            elif is_numbered:
                                level = determine_level_by_numbering(cleaned_text)
                                if level is None:
                                    # Fallback: используем стандартную логику
                                    level = self._determine_header_level(
                                        cleaned_text, element, page, rect, None, previous_headers, font_size, font_properties
                                    )
                                logger.debug(f"Determined level {level} for numbered header '{cleaned_text[:50]}...' by numbering pattern")
                            
                            # ПРИОРИТЕТ 3: Если заголовок НЕ пронумерован - определяем уровень по стилю (font_name)
                            else:
                                if level_1_font_name and font_properties:
                                    element_font_name = font_properties.get("font_name")
                                    if element_font_name:
                                        # Точное совпадение - это HEADER_1
                                        if element_font_name == level_1_font_name:
                                            level = 1
                                            logger.debug(f"Determined level 1 for unnumbered header '{cleaned_text[:50]}...' by exact font_name match: {element_font_name}")
                                        # Проверяем, является ли это базовым именем + "Ital" - это HEADER_2
                                        else:
                                            # Убираем "Ital", "Italic", "Oblique" из font_name и сравниваем
                                            font_base = element_font_name
                                            for suffix in ['Ital', 'Italic', 'Oblique', 'Obl']:
                                                if font_base.endswith(suffix):
                                                    font_base = font_base[:-len(suffix)]
                                                    break
                                            
                                            level_1_base = level_1_font_name
                                            for suffix in ['Ital', 'Italic', 'Oblique', 'Obl']:
                                                if level_1_base.endswith(suffix):
                                                    level_1_base = level_1_base[:-len(suffix)]
                                                    break
                                            
                                            if font_base == level_1_base:
                                                font_lower = element_font_name.lower()
                                                if 'ital' in font_lower or 'oblique' in font_lower:
                                                    level = 2
                                                    logger.debug(f"Determined level 2 for unnumbered header '{cleaned_text[:50]}...' by font_name with Ital: {element_font_name}")
                                                else:
                                                    level = 1
                                                    logger.debug(f"Determined level 1 for unnumbered header '{cleaned_text[:50]}...' by font_name base match: {element_font_name}")
                                
                                # Если уровень все еще не определен, используем стандартную логику
                                if level is None:
                                    level = self._determine_header_level(
                                        cleaned_text, element, page, rect, None, previous_headers, font_size, font_properties
                                    )
                            
                            # Save header info for comparison with subsequent headers
                            # Сохраняем также is_bold для сравнения стилей
                            header_info = {
                                "level": level,
                                "font_size": font_size,
                                "page_num": page_num,
                                "text": cleaned_text,
                                "bbox": bbox,
                            }
                            if font_properties:
                                header_info["is_bold"] = font_properties.get("is_bold", False)
                                header_info["is_italic"] = font_properties.get("is_italic", False)
                                header_info["font_name"] = font_properties.get("font_name")
                            previous_headers.append(header_info)
                            header_positions.append(header_info)
                            
                            element_type = getattr(ElementType, f"HEADER_{level}", ElementType.HEADER_1)
                            
                            # Save cleaned text (without markdown symbols)
                            element["text"] = cleaned_text
                            element["level"] = level
                            element["element_type"] = element_type
                            # Сохраняем font_properties в элементе для использования во втором проходе
                            if font_properties:
                                element["font_properties"] = font_properties
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
                            "text": "",
                        })
                
                    # Add header element to analyzed_elements
                    analyzed_elements.append(element)
                else:
                    # Add non-header elements to analyzed_elements
                    analyzed_elements.append(element)
            
            # Build header rules from found headers (similar to DOCX parser)
            header_rules = None
            if header_positions:
                try:
                    header_rules = build_header_rules(source, header_positions)
                    logger.debug(f"Built header rules from {len(header_positions)} headers")
                except Exception as e:
                    logger.warning(f"Failed to build header rules: {e}")
            
            # Second pass: переопределяем уровни заголовков на основе font_name
            # Это ПРИОРИТЕТНЫЙ метод: если font_name совпадает с известными заголовками - используем их уровень
            if header_rules:
                for element in analyzed_elements:
                    category = element.get("category", "")
                    if category == "Section-header":
                        text = element.get("text", "").strip()
                        
                        # Quick filter: obvious non-headers
                        if text.endswith(':') or len(text) > 300:
                            logger.debug(f"Filtered out obvious non-header: '{text[:50]}...'")
                            element["category"] = "Text"
                            continue
                        
                        # Получаем font_name элемента
                        font_properties = element.get("font_properties")
                        if not font_properties:
                            # Пытаемся извлечь font_properties, если их нет
                            bbox = element.get("bbox", [])
                            page_num = element.get("page_num", 0)
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
                                    font_properties = extract_text_properties(page, rect, text)
                                    element["font_properties"] = font_properties
                                except Exception:
                                    pass
                        
                        if font_properties:
                            font_name = font_properties.get("font_name")
                            if font_name:
                                # Определяем уровень на основе font_name
                                level_by_font = determine_header_level_by_font_name(font_name, header_rules)
                                if level_by_font is not None:
                                    # Переопределяем уровень заголовка на основе font_name
                                    element["level"] = level_by_font
                                    element["element_type"] = getattr(ElementType, f"HEADER_{level_by_font}", ElementType.HEADER_1)
                                    logger.debug(f"Determined level {level_by_font} for '{text[:50]}...' by font_name '{font_name}'")
            
            # Third pass: filter out obvious non-headers
            filtered_elements: List[Dict[str, Any]] = []
            for element in analyzed_elements:
                category = element.get("category", "")
                if category == "Section-header":
                    text = element.get("text", "").strip()
                    
                    # Quick filter: obvious non-headers
                    if text.endswith(':') or len(text) > 300:
                        logger.debug(f"Filtered out obvious non-header: '{text[:50]}...'")
                        element["category"] = "Text"
                        filtered_elements.append(element)
                        continue
                
                filtered_elements.append(element)
            
            return filtered_elements
            
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

    def _get_font_properties(
        self, page: fitz.Page, rect: fitz.Rect
    ) -> Dict[str, Any]:
        """
        Извлекает свойства шрифта из области текста (размер, жирный, курсив).
        
        Аналогично функции в DOCX пайплайне и pdf_parser.py.
        
        Args:
            page: PDF страница.
            rect: Прямоугольник области текста.
        
        Returns:
            Словарь с ключами:
            - font_size: средний размер шрифта (float или None)
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
                "font_size": sum(font_sizes) / len(font_sizes) if font_sizes else None,
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
        Gets average font size from text in rectangle.
        
        DEPRECATED: Используйте _get_font_properties для получения всех свойств шрифта.
        Оставлено для обратной совместимости.
        """
        font_props = self._get_font_properties(page, rect)
        return font_props.get("font_size")

    def _has_explicit_numbering(self, text: str) -> bool:
        """Checks if header has explicit numbering (e.g., "1.2", "A.1", "I.", "3", "B Formulation")."""
        text_stripped = text.strip()
        
        # Check for various numbering patterns
        patterns = [
            r'^\d+\.(?!\d)',  # "1. ", "2. ", "3. " (numbered sections, not "1.1")
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
        font_properties: Optional[Dict[str, Any]] = None,
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
        # Remove trailing colon before comparison
        text_normalized = text.strip().rstrip(':').strip().upper()
        if text_normalized in SPECIAL_HEADER_1:
            return 1
        
        # Check for appendix headers
        if re.match(APPENDIX_HEADER_PATTERN, text_normalized):
            return 2
        
        # Check for explicit numbering patterns
        # Headers like "I. ", "II. ", "III. ", "IV. ", "V. ", "VI. ", etc.
        if re.match(r'^[IVX]+\.\s+', text, re.IGNORECASE):
            return 1
        
        # Headers like "1. ", "2. ", "3. " -> HEADER_1 (numbered sections)
        # Pattern: digit(s) + dot + (space or non-digit character)
        # This should match "1. Общая характеристика...", "2. Экспериментальная часть..." etc.
        # Does NOT match "1.1", "1.2" (those are handled below)
        if re.match(r'^\d+\.(?!\d)', text):
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
        
        # Если font_properties не переданы, но есть page и rect, извлекаем их
        if font_properties is None and page is not None and rect is not None:
            font_properties = self._get_font_properties(page, rect)
        
        # Используем font_size из font_properties, если он не передан отдельно
        if font_size is None and font_properties:
            font_size = font_properties.get("font_size")
        
        # Use font size and position if available (when no numbered header context)
        use_font_size = self._get_config("header_analysis.use_font_size", True)
        use_position = self._get_config("header_analysis.use_position", True)
        
        if use_font_size and font_size is not None and previous_headers:
            # Compare with previous headers
            for prev_header in reversed(previous_headers):
                prev_font_size = prev_header.get("font_size")
                if prev_font_size is not None:
                    min_font_size_diff = self._get_config("header_analysis.min_font_size_diff", 2)
                    prev_is_bold = prev_header.get("is_bold", False)
                    
                    # Получаем информацию о текущем заголовке
                    current_is_bold = False
                    if font_properties:
                        current_is_bold = font_properties.get("is_bold", False)
                    
                    if font_size > prev_font_size + min_font_size_diff:
                        # Larger font -> higher level (lower number)
                        return max(1, prev_header["level"] - 1)
                    elif font_size < prev_font_size - min_font_size_diff:
                        # Smaller font -> lower level (higher number)
                        return min(6, prev_header["level"] + 1)
                    else:
                        # Similar font size -> compare styles
                        # Если текущий заголовок жирный, а предыдущий нет - более высокий уровень
                        if current_is_bold and not prev_is_bold:
                            return max(1, prev_header["level"] - 1)
                        # Если текущий заголовок не жирный, а предыдущий жирный - более низкий уровень
                        elif not current_is_bold and prev_is_bold:
                            return min(6, prev_header["level"] + 1)
                        # Если стили одинаковые - тот же уровень
                        else:
                            return prev_header["level"]
        
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

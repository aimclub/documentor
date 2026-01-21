"""
Типы элементов layout, возвращаемые Dots.OCR.

Используется для определения структуры страницы при OCR обработке.
Типы маппятся в ElementType при структурировании документа.

См. также: ocr/dots_ocr.py для реализации layout detection
"""
from enum import Enum


class LayoutTypeDotsOCR(str, Enum):
    """Типы элементов layout, возвращаемые dots.ocr."""
    
    TEXT = "Text"
    PICTURE = "Picture"
    CAPTION = "Caption"
    SECTION_HEADER = "Section-header"
    FOOTNOTE = "Footnote"
    FORMULA = "Formula"
    TABLE = "Table"
    TITLE = "Title"
    LIST_ITEM = "List-item"
    PAGE_HEADER = "Page-header"
    PAGE_FOOTER = "Page-footer"
    OTHER = "Other"
    UNKNOWN = "Unknown"



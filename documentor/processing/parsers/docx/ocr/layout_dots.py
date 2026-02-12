"""
Layout element types returned by Dots.OCR.

Used for determining page structure during OCR processing.
Types are mapped to ElementType when structuring the document.

See also: ocr/dots_ocr.py for layout detection implementation
"""
from enum import Enum


class LayoutTypeDotsOCR(str, Enum):
    """Layout element types returned by dots.ocr."""
    
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



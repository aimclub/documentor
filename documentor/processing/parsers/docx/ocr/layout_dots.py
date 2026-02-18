"""
Layout element types returned by Dots.OCR.

DEPRECATED: This module is kept for backward compatibility.
New code should use documentor.ocr.dots_ocr.types.LayoutTypeDotsOCR instead.

Used for determining page structure during OCR processing.
Types are mapped to ElementType when structuring the document.
"""

import warnings

# Re-export from new module for backward compatibility
from documentor.ocr.dots_ocr.types import LayoutTypeDotsOCR

warnings.warn(
    "documentor.processing.parsers.docx.ocr.layout_dots is deprecated. "
    "Use documentor.ocr.dots_ocr.types.LayoutTypeDotsOCR instead.",
    DeprecationWarning,
    stacklevel=2
)



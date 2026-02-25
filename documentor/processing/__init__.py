"""
Document processing module.

Contains parsers, loaders, and hierarchy building utilities for document processing.
"""

# Re-export parsers
from .parsers import (
    BaseParser,
    DocxParser,
    MarkdownParser,
    PdfParser,
)

# Re-export loader utilities
from .loader import (
    detect_document_format,
    get_document_source,
    normalize_metadata,
    validate_document,
)

__all__ = [
    # Parsers
    "BaseParser",
    "DocxParser",
    "MarkdownParser",
    "PdfParser",
    # Loader utilities
    "detect_document_format",
    "get_document_source",
    "normalize_metadata",
    "validate_document",
]

"""
Utilities for working with LangChain Document and format detection.

Contains functions for:
- Detecting document format by file extension, MIME type, or magic bytes
- Getting document source from metadata
- Validating documents
- Normalizing metadata
"""

import logging
from pathlib import Path
from typing import Optional

from langchain_core.documents import Document

from ...domain import DocumentFormat

logger = logging.getLogger(__name__)

# Magic bytes for file format detection
MAGIC_BYTES = {
    b"%PDF": DocumentFormat.PDF,
    b"PK\x03\x04": DocumentFormat.DOCX,  # DOCX is a ZIP archive
}

# MIME types for format detection
MIME_TYPE_MAP = {
    "application/pdf": DocumentFormat.PDF,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocumentFormat.DOCX,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template": DocumentFormat.DOCX,
    "text/markdown": DocumentFormat.MARKDOWN,
    "text/x-markdown": DocumentFormat.MARKDOWN,
}

# File extensions for format detection
EXTENSION_MAP = {
    "md": DocumentFormat.MARKDOWN,
    "markdown": DocumentFormat.MARKDOWN,
    "pdf": DocumentFormat.PDF,
    "docx": DocumentFormat.DOCX,
}


def get_document_source(document: Document) -> str:
    """
    Gets document source from metadata.
    
    Checks the following keys in priority order:
    - source
    - file_path
    - path
    - filename
    - file_name
    
    Args:
        document: LangChain Document
        
    Returns:
        str: Path to document source or "unknown" if not found
    """
    metadata = document.metadata or {}
    for key in ("source", "file_path", "path", "filename", "file_name"):
        value = metadata.get(key)
        if value:
            source = str(value)
            logger.debug(f"Document source found by key '{key}': {source}")
            return source
    
    logger.warning("Document source not found in metadata")
    return "unknown"


def _detect_format_by_extension(source: str) -> Optional[DocumentFormat]:
    """
    Determines document format by file extension.
    
    Args:
        source: File path
        
    Returns:
        DocumentFormat or None if cannot be determined
    """
    try:
        path = Path(source)
        extension = path.suffix.lower().lstrip(".")
        if extension:
            format_ = EXTENSION_MAP.get(extension)
            if format_:
                logger.debug(f"Format determined by extension '{extension}': {format_.value}")
                return format_
    except (ValueError, AttributeError) as e:
        logger.debug(f"Error determining format by extension: {e}")
    return None


def _detect_format_by_mime_type(metadata: dict) -> Optional[DocumentFormat]:
    """
    Determines document format by MIME type from metadata.
    
    Args:
        metadata: Document metadata
        
    Returns:
        DocumentFormat or None if cannot be determined
    """
    mime_type = metadata.get("mime_type", "")
    if mime_type:
        format_ = MIME_TYPE_MAP.get(mime_type)
        if format_:
            logger.debug(f"Format determined by MIME type '{mime_type}': {format_.value}")
            return format_
    return None


def _detect_format_by_magic_bytes(source: str) -> Optional[DocumentFormat]:
    """
    Determines document format by magic bytes (file signature).
    
    Args:
        source: File path
        
    Returns:
        DocumentFormat or None if cannot be determined
    """
    try:
        path = Path(source)
        if not path.exists() or not path.is_file():
            return None
        
        with open(path, "rb") as f:
            # Read first 4 bytes to check signature
            header = f.read(4)
            if len(header) < 4:
                return None
            
            # Check magic bytes
            for magic, format_ in MAGIC_BYTES.items():
                if header.startswith(magic):
                    logger.debug(f"Format determined by magic bytes: {format_.value}")
                    return format_
            
            # For DOCX need to check more bytes (ZIP signature)
            if header.startswith(b"PK"):
                f.seek(0)
                # DOCX files have specific ZIP structure
                # Check for [Content_Types].xml file in ZIP
                zip_header = f.read(30)
                if b"[Content_Types].xml" in zip_header or b"word/" in zip_header:
                    logger.debug("Format determined by ZIP structure (DOCX)")
                    return DocumentFormat.DOCX
                    
    except (OSError, IOError, ValueError) as e:
        logger.debug(f"Error reading magic bytes: {e}")
    return None


def detect_document_format(document: Document) -> DocumentFormat:
    """
    Determines document format.
    
    Uses several methods in priority order:
    1. File extension
    2. MIME type from metadata
    3. Magic bytes (file signature)
    
    Args:
        document: LangChain Document
        
    Returns:
        DocumentFormat: Determined document format
        
    Raises:
        ValueError: If document is invalid (no page_content and source)
    """
    source = get_document_source(document)
    # Check that there is either non-empty page_content or valid source
    has_content = bool(document.page_content and document.page_content.strip())
    has_source = source != "unknown"
    
    if not has_content and not has_source:
        raise ValueError("Document must contain page_content or source in metadata")
    
    metadata = document.metadata or {}
    
    # Method 1: By file extension
    format_ = _detect_format_by_extension(source)
    if format_:
        return format_
    
    # Method 2: By MIME type
    format_ = _detect_format_by_mime_type(metadata)
    if format_:
        return format_
    
    # Method 3: By magic bytes (only if source is a file path)
    if source != "unknown":
        format_ = _detect_format_by_magic_bytes(source)
        if format_:
            return format_
    
    logger.warning(f"Failed to determine document format for source: {source}")
    return DocumentFormat.UNKNOWN


def validate_document(document: Document) -> None:
    """
    Validates LangChain Document.
    
    Checks:
    - Document is not None
    - Has page_content or source in metadata
    - page_content is a string (if specified)
    
    Args:
        document: LangChain Document to validate
        
    Raises:
        ValueError: If document is invalid
        TypeError: If not a Document object is passed
    """
    if document is None:
        raise ValueError("Document cannot be None")
    
    if not isinstance(document, Document):
        raise TypeError(f"Expected Document, got {type(document).__name__}")
    
    # Check for content or source
    has_content = bool(document.page_content)
    has_source = bool(get_document_source(document) != "unknown")
    
    if not has_content and not has_source:
        raise ValueError("Document must contain page_content or source in metadata")
    
    # Check page_content type
    if document.page_content is not None and not isinstance(document.page_content, str):
        raise TypeError(
            f"page_content must be a string, got {type(document.page_content).__name__}"
        )
    
    # Check metadata type
    if document.metadata is not None and not isinstance(document.metadata, dict):
        raise TypeError(
            f"metadata must be a dict, got {type(document.metadata).__name__}"
        )


def normalize_metadata(document: Document) -> dict:
    """
    Normalizes document metadata.
    
    Ensures standard keys:
    - source: file path
    - format: determined document format
    
    Args:
        document: LangChain Document
        
    Returns:
        dict: Normalized metadata
    """
    metadata = dict(document.metadata or {})
    
    # Add source if missing
    if "source" not in metadata:
        source = get_document_source(document)
        if source != "unknown":
            metadata["source"] = source
    
    # Add format if missing
    if "format" not in metadata:
        try:
            format_ = detect_document_format(document)
            metadata["format"] = format_.value
        except ValueError:
            # If format cannot be determined, don't add it
            pass
    
    return metadata
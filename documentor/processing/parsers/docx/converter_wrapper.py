"""
DOCX to PDF converter wrapper.

Provides a clean interface for converting DOCX files to PDF.
"""

import logging
from pathlib import Path

from .converter import convert_docx_to_pdf

logger = logging.getLogger(__name__)


class DocxConverter:
    """
    Converter for DOCX to PDF transformation.
    
    Handles:
    - DOCX to PDF conversion
    - Temporary file management
    """

    @staticmethod
    def convert_to_pdf(docx_path: Path, pdf_path: Path) -> None:
        """
        Converts DOCX file to PDF.
        
        Args:
            docx_path: Path to DOCX file.
            pdf_path: Path to output PDF file.
        
        Raises:
            Exception: If conversion fails.
        """
        convert_docx_to_pdf(docx_path, pdf_path)
        logger.debug(f"Converted DOCX to PDF: {docx_path} -> {pdf_path}")

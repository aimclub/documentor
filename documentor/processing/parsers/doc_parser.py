"""DOC parser with automatic conversion to DOCX using Word COM."""

from pathlib import Path
from typing import Set, Optional

from ...core.interfaces import BaseParser
from ...core.document import Document
from ...core.logging import get_logger
from .word_com_converter import get_word_com_converter, is_word_com_available
from .docx_parser import DocxParser

logger = get_logger(__name__)


class DocParser(BaseParser):
    """
    Parser for DOC files using Word COM conversion to DOCX.
    
    This parser automatically converts DOC files to DOCX using Microsoft Word COM interface,
    then processes them using the DOCX parser.
    
    Requirements:
    - Windows operating system
    - Microsoft Word installed
    - pywin32 package (win32com.client)
    """
    
    def __init__(self):
        """Initialize DOC parser."""
        self.word_com_available = is_word_com_available()
        self.converter = get_word_com_converter()
        self.docx_parser = None
        
        if self.word_com_available:
            try:
                self.docx_parser = DocxParser()
                logger.info("DOC parser initialized with Word COM conversion support")
            except Exception as e:
                logger.error(f"Failed to initialize DOCX parser: {e}")
                self.word_com_available = False
        else:
            logger.warning("DOC parser initialized but Word COM not available - DOC files will be skipped")
    
    def supported_extensions(self) -> Set[str]:
        """Get supported extensions."""
        if self.word_com_available:
            return {'.doc'}
        else:
            return set()  # No support if Word COM not available
    
    def parse(self, file_path: Path) -> Document:
        """
        Parse DOC file by converting to DOCX first.
        
        Args:
            file_path: Path to DOC file
            
        Returns:
            Document: Parsed document
            
        Raises:
            FileNotFoundError: If file not found
            ValueError: If file cannot be processed or Word COM not available
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")
        
        if file_path.suffix.lower() not in self.supported_extensions():
            raise ValueError(f"Unsupported file extension: {file_path.suffix}")
        
        if not self.word_com_available:
            raise ValueError("Word COM not available - cannot process DOC files")
        
        if not self.docx_parser:
            raise ValueError("DOCX parser not available")
        
        logger.info(f"Parsing DOC file with conversion: {file_path}")
        
        # Convert DOC to DOCX
        temp_docx_path = self.converter.convert_doc_to_docx(file_path)
        if not temp_docx_path:
            raise ValueError(f"Failed to convert DOC file to DOCX: {file_path}")
        
        try:
            # Parse the converted DOCX file
            document = self.docx_parser.parse(temp_docx_path)
            
            # Update metadata to reflect original DOC file
            if hasattr(document, 'metadata') and document.metadata:
                document.metadata.file_path = str(file_path)
                document.metadata.processing_method = "doc_conversion_processing"
                
                # Add conversion metadata
                if not hasattr(document.metadata, 'params'):
                    document.metadata.params = {}
                document.metadata.params.update({
                    'original_format': 'doc',
                    'converted_format': 'docx',
                    'conversion_method': 'word_com',
                    'temp_docx_path': str(temp_docx_path)
                })
            
            logger.info(f"Successfully parsed DOC file via conversion: {len(document.fragments())} fragments")
            return document
            
        finally:
            # Clean up temporary DOCX file
            try:
                self.converter.cleanup_temp_file(temp_docx_path)
            except Exception as e:
                logger.warning(f"Error cleaning up temporary file: {e}")
    
    def is_available(self) -> bool:
        """
        Check if DOC parser is available.
        
        Returns:
            bool: True if Word COM and DOCX parser are available
        """
        return self.word_com_available and self.docx_parser is not None

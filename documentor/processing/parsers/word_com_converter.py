"""Word COM converter for DOC to DOCX conversion on Windows."""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Tuple
import logging

from ...core.logging import get_logger

logger = get_logger(__name__)

# Check if we're on Windows
IS_WINDOWS = sys.platform == 'win32'

# Try to import win32com.client
try:
    if IS_WINDOWS:
        import win32com.client
        WORD_COM_AVAILABLE = True
    else:
        WORD_COM_AVAILABLE = False
except ImportError:
    WORD_COM_AVAILABLE = False


class WordComConverter:
    """
    Converter for DOC files to DOCX using Microsoft Word COM interface.
    
    This converter is only available on Windows systems with Microsoft Word installed.
    """
    
    def __init__(self):
        """Initialize Word COM converter."""
        self.available = self._check_availability()
        if self.available:
            logger.info("Word COM converter initialized")
        else:
            logger.warning("Word COM converter not available - DOC files will be skipped")
    
    def _check_availability(self) -> bool:
        """
        Check if Word COM conversion is available.
        
        Returns:
            bool: True if Word COM is available, False otherwise
        """
        if not IS_WINDOWS:
            logger.debug("Not on Windows - Word COM not available")
            return False
        
        if not WORD_COM_AVAILABLE:
            logger.debug("win32com.client not available - Word COM not available")
            return False
        
        try:
            # Try to create Word application object
            word_app = win32com.client.Dispatch("Word.Application")
            word_app.Visible = False
            word_app.Quit()
            logger.debug("Word COM interface test successful")
            return True
        except Exception as e:
            logger.debug(f"Word COM interface test failed: {e}")
            return False
    
    def convert_doc_to_docx(self, doc_path: Path) -> Optional[Path]:
        """
        Convert DOC file to DOCX using Word COM.
        
        Args:
            doc_path: Path to DOC file
            
        Returns:
            Optional[Path]: Path to converted DOCX file, or None if conversion failed
        """
        if not self.available:
            logger.warning(f"Cannot convert {doc_path} - Word COM not available")
            return None
        
        if not doc_path.exists():
            logger.error(f"DOC file not found: {doc_path}")
            return None
        
        if doc_path.suffix.lower() != '.doc':
            logger.error(f"File is not a DOC file: {doc_path}")
            return None
        
        # Create temporary directory for conversion
        temp_dir = tempfile.mkdtemp(prefix="documentor_word_com_")
        temp_docx_path = Path(temp_dir) / f"{doc_path.stem}.docx"
        
        word_app = None
        try:
            logger.info(f"Converting DOC to DOCX using Word COM: {doc_path}")
            
            # Create Word application
            word_app = win32com.client.Dispatch("Word.Application")
            word_app.Visible = False
            word_app.DisplayAlerts = False  # Suppress alerts
            
            # Open DOC file
            doc = word_app.Documents.Open(str(doc_path.absolute()))
            
            # Save as DOCX
            doc.SaveAs2(str(temp_docx_path.absolute()), FileFormat=16)  # 16 = wdFormatXMLDocument (DOCX)
            
            # Close document
            doc.Close()
            
            # Verify the converted file exists
            if temp_docx_path.exists():
                logger.info(f"Successfully converted DOC to DOCX: {temp_docx_path}")
                return temp_docx_path
            else:
                logger.error("Conversion completed but DOCX file not found")
                return None
                
        except Exception as e:
            logger.error(f"Error converting DOC to DOCX: {e}")
            return None
        finally:
            # Clean up Word application
            if word_app:
                try:
                    word_app.Quit()
                except Exception as e:
                    logger.warning(f"Error closing Word application: {e}")
    
    def cleanup_temp_file(self, temp_docx_path: Path) -> None:
        """
        Clean up temporary DOCX file and its directory.
        
        Args:
            temp_docx_path: Path to temporary DOCX file
        """
        try:
            if temp_docx_path.exists():
                temp_docx_path.unlink()
            
            # Remove parent directory if empty
            temp_dir = temp_docx_path.parent
            if temp_dir.exists() and not any(temp_dir.iterdir()):
                temp_dir.rmdir()
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logger.warning(f"Error cleaning up temporary file {temp_docx_path}: {e}")
    
    def is_available(self) -> bool:
        """
        Check if converter is available.
        
        Returns:
            bool: True if converter is available
        """
        return self.available


# Global converter instance
_converter_instance: Optional[WordComConverter] = None


def get_word_com_converter() -> WordComConverter:
    """
    Get global Word COM converter instance.
    
    Returns:
        WordComConverter: Converter instance
    """
    global _converter_instance
    if _converter_instance is None:
        _converter_instance = WordComConverter()
    return _converter_instance


def is_word_com_available() -> bool:
    """
    Check if Word COM conversion is available.
    
    Returns:
        bool: True if available
    """
    return get_word_com_converter().is_available()

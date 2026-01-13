"""Parser registry for automatic parser selection."""

from pathlib import Path
from typing import Dict, Set, Optional

from ...core.interfaces import BaseParser
from ...core.document import Document
from ...core.logging import get_logger
from .txt_parser import TxtParser
from .image_parser import ImageParser
from .pdf_parser import PdfParser
from ..pipelines.ocr.config import OCRPipelineConfig

logger = get_logger(__name__)


class ParserRegistry:
    """
    Parser registry for automatic parser selection by file extension.
    """
    
    def __init__(self, ocr_config: Optional[OCRPipelineConfig] = None):
        """
        Initialize registry.
        
        Args:
            ocr_config: OCR configuration for image and PDF parsers
        """
        self.ocr_config = ocr_config or OCRPipelineConfig.create_default()
        self._parsers: Dict[str, BaseParser] = {}
        self._setup_default_parsers()
    
    def _setup_default_parsers(self) -> None:
        """Configure default parsers."""
        try:
            # TXT parser
            txt_parser = TxtParser()
            for ext in txt_parser.supported_extensions():
                self._parsers[ext] = txt_parser
            
            # Image parser
            image_parser = ImageParser(self.ocr_config)
            if image_parser.is_available():
                for ext in image_parser.supported_extensions():
                    self._parsers[ext] = image_parser
                logger.info("Image parser registered successfully")
            else:
                logger.warning("Image parser not available - OCR services not accessible")
            
            # PDF parser
            pdf_parser = PdfParser(self.ocr_config)
            if pdf_parser.is_available():
                for ext in pdf_parser.supported_extensions():
                    self._parsers[ext] = pdf_parser
                logger.info("PDF parser registered successfully")
            else:
                logger.warning("PDF parser not available - OCR services not accessible")
            
            # DOCX parser
            try:
                from .docx_parser import DocxParser
                docx_parser = DocxParser()
                for ext in docx_parser.supported_extensions():
                    self._parsers[ext] = docx_parser
                logger.info("DOCX parser registered successfully")
            except ImportError as e:
                logger.warning(f"DOCX parser not available: {e}")
            
            # DOC parser (with Word COM conversion)
            try:
                from .doc_parser import DocParser
                doc_parser = DocParser()
                for ext in doc_parser.supported_extensions():
                    self._parsers[ext] = doc_parser
                if doc_parser.is_available():
                    logger.info("DOC parser registered successfully (Word COM available)")
                else:
                    logger.warning("DOC parser not available - Word COM not installed or not on Windows")
            except ImportError as e:
                logger.warning(f"DOC parser not available: {e}")
            
            logger.info(f"Registered parsers for extensions: {list(self._parsers.keys())}")
            
        except Exception as e:
            logger.error(f"Error setting up default parsers: {e}")
    
    def register_parser(self, parser: BaseParser) -> None:
        """
        Register parser.
        
        Args:
            parser: Parser to register
        """
        for extension in parser.supported_extensions():
            self._parsers[extension] = parser
            logger.info(f"Registered parser {type(parser).__name__} for extension {extension}")
    
    def get_parser(self, file_path: Path) -> Optional[BaseParser]:
        """
        Get parser for file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Optional[BaseParser]: Parser or None if not found
        """
        extension = file_path.suffix.lower()
        return self._parsers.get(extension)
    
    def can_parse(self, file_path: Path) -> bool:
        """
        Check if any registered parser can process the file.
        
        Args:
            file_path: Path to file
            
        Returns:
            bool: True if file can be processed
        """
        extension = file_path.suffix.lower()
        return extension in self._parsers
    
    def parse_file(self, file_path: Path) -> Document:
        """
        Parse file with automatic parser selection.
        
        Args:
            file_path: Path to file
            
        Returns:
            Document: Parsed document
            
        Raises:
            ValueError: If parser not found or parsing error occurred
        """
        parser = self.get_parser(file_path)
        if parser is None:
            raise ValueError(f"Parser not found for file: {file_path}")
        
        logger.info(f"Using parser {type(parser).__name__} for file {file_path}")
        return parser.parse(file_path)
    
    def supported_extensions(self) -> Set[str]:
        """
        Get all supported extensions.
        
        Returns:
            Set[str]: Set of supported extensions
        """
        return set(self._parsers.keys())
    
    def get_parser_info(self) -> Dict[str, str]:
        """
        Get information about registered parsers.
        
        Returns:
            Dict[str, str]: Dictionary {extension: parser_name}
        """
        return {ext: type(parser).__name__ for ext, parser in self._parsers.items()}

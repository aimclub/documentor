"""PDF parser with selective text and OCR support."""

from pathlib import Path
from typing import Set, Iterator

try:
    import PyPDF2
    from pdf2image import convert_from_path
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

from PIL import Image

from ...core.interfaces import BaseParser
from ...core.document import Document
from ...core.logging import get_logger
from ...data.structures.metadata import Metadata
from ...data.structures.fragment.text import ParagraphFragment
from ..pipelines.ocr.pdf_processor import PDFProcessor
from ..pipelines.ocr.config import OCRPipelineConfig

logger = get_logger(__name__)


class PdfParser(BaseParser):
    """
    Parser for PDF files.
    
    Supports two modes:
    1. Selective text extraction (if available)
    2. OCR processing (if no selective text or too little)
    
    Uses existing PDFProcessor from OCR pipeline.
    """
    
    def __init__(
        self, 
        ocr_config: OCRPipelineConfig,
        min_text_threshold: int = 50,
        dpi: int = 200
    ):
        """
        Initialize parser.
        
        Args:
            ocr_config: OCR pipeline configuration
            min_text_threshold: Minimum character count for selective text usage
            dpi: DPI for PDF to image conversion
        """
        if not PDF_SUPPORT:
            raise ImportError("PyPDF2 and pdf2image libraries are required for PDF processing")
        
        self.ocr_config = ocr_config
        self.min_text_threshold = min_text_threshold
        self.dpi = dpi
        self._ocr_available = False
        self.pdf_processor = None
        
        # Create PDF processor
        self._setup_pdf_processor()
        
        logger.info("PDF parser initialized")
    
    def _setup_pdf_processor(self) -> None:
        """Setup PDF processor with OCR support."""
        try:
            # Test OCR services availability first
            from .ocr_health_check import check_ocr_services_from_env
            ocr_results = check_ocr_services_from_env()
            
            if not ocr_results['overall_available']:
                self._ocr_available = False
                logger.warning("OCR services not available - PDF parser disabled")
                return
            
            self.pdf_processor = PDFProcessor(self.ocr_config)
            self._ocr_available = True
            logger.info("PDF processor with OCR support initialized")
        except Exception as e:
            self._ocr_available = False
            logger.warning(f"PDF processor with OCR not available: {e}")
    
    def supported_extensions(self) -> Set[str]:
        """Get supported extensions."""
        if self._ocr_available:
            return {'.pdf'}
        else:
            return set()  # No support if OCR not available
    
    def is_available(self) -> bool:
        """Check if parser is available (OCR services must be available)."""
        return self._ocr_available
    
    def parse(self, file_path: Path) -> Document:
        """
        Parse PDF file.
        
        Args:
            file_path: Path to PDF file
            
        Returns:
            Document: Document with fragments from all pages
            
        Raises:
            FileNotFoundError: If file not found
            ValueError: If file cannot be processed
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")
        
        if file_path.suffix.lower() not in self.supported_extensions():
            raise ValueError(f"Unsupported file extension: {file_path.suffix}")
        
        logger.info(f"Parsing PDF file: {file_path}")
        
        metadata = Metadata.from_path(
            file_path,
            processing_method="pdf_processing"
        )
        
        all_fragments = []
        
        try:
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                total_pages = len(reader.pages)
            
            metadata.params['total_pages'] = total_pages
            logger.info(f"PDF contains {total_pages} pages")
            
            for page_num in range(total_pages):
                logger.info(f"Processing page {page_num + 1}/{total_pages}")
                
                try:
                    page_fragments = list(self._process_page(file_path, page_num))
                    
                    for fragment in page_fragments:
                        if fragment.page is None:
                            fragment.page = str(page_num + 1)
                    
                    all_fragments.extend(page_fragments)
                    
                except Exception as e:
                    logger.error(f"Error processing page {page_num + 1}: {e}")
                    continue
            
            logger.info(f"Created {len(all_fragments)} fragments from {total_pages} pages")
            
            document = Document(
                fragments=all_fragments,
                metadata=metadata
            )
            
            document.create_structure_from_headers()
            
            return document
            
        except Exception as e:
            logger.error(f"Error processing PDF file {file_path}: {e}")
            raise ValueError(f"Failed to process PDF file: {e}")
    
    def _process_page(self, pdf_path: Path, page_num: int) -> Iterator:
        """
        Process single PDF page.
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (starting from 0)
            
        Yields:
            Fragment: Fragments from the page
        """
        selectable_text = self.pdf_processor.extract_selectable_text(str(pdf_path), page_num)
        
        if selectable_text and len(selectable_text) >= self.min_text_threshold:
            logger.info(f"Using selectable text for page {page_num + 1}")
            
            yield from self._create_fragments_from_text(selectable_text, page_num + 1)
        else:
            logger.info(f"Using OCR for page {page_num + 1}")
            
            page_image = self._convert_page_to_image(pdf_path, page_num)
            
            if page_image:
                yield from self.pdf_processor.process_image(page_image)
    
    def _convert_page_to_image(self, pdf_path: Path, page_num: int) -> Image.Image | None:
        """
        Convert PDF page to image.
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (starting from 0)
            
        Returns:
            Image.Image | None: Page image or None on error
        """
        try:
            images = convert_from_path(
                pdf_path,
                dpi=self.dpi,
                first_page=page_num + 1,
                last_page=page_num + 1
            )
            
            if images:
                return images[0]
            else:
                logger.warning(f"Failed to convert page {page_num + 1}")
                return None
                
        except Exception as e:
            logger.error(f"Error converting page {page_num + 1} to image: {e}")
            return None
    
    def _create_fragments_from_text(self, text: str, page_num: int) -> Iterator:
        """
        Create fragments from selectable text.
        
        Args:
            text: Page text
            page_num: Page number
            
        Yields:
            Fragment: Text fragments
        """
        paragraphs = text.split('\n\n')
        
        for para_num, paragraph in enumerate(paragraphs):
            paragraph = paragraph.strip()
            if paragraph:
                fragment = ParagraphFragment(
                    value=paragraph,
                    page=str(page_num),
                    id=f"page_{page_num}_para_{para_num + 1}"
                )
                yield fragment

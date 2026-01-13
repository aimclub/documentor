"""Image parser using OCR pipeline."""

import base64
from io import BytesIO
from pathlib import Path
from typing import Set

from PIL import Image

from ...core.interfaces import BaseParser
from ...core.document import Document
from ...core.logging import get_logger
from ...data.structures.metadata import Metadata
from ..pipelines.ocr.pipeline import ScanPipeline
from ..pipelines.ocr.detector import DotsBlockDetector
from ..pipelines.ocr.recognizer import QwenBlockRecognizer
from ..pipelines.ocr.dots_ocr_client import DotsOCRClient
from ..pipelines.ocr.qwen_client import QwenClient
from ..pipelines.ocr.config import OCRPipelineConfig

logger = get_logger(__name__)


class ImageParser(BaseParser):
    """
    Parser for images (PNG, JPG, JPEG) using OCR.
    
    Uses existing OCR pipeline (dots.ocr + Qwen2.5) for text recognition.
    """
    
    def __init__(self, ocr_config: OCRPipelineConfig):
        """
        Initialize parser.
        
        Args:
            ocr_config: OCR pipeline configuration
        """
        self.ocr_config = ocr_config
        self._ocr_available = False
        self.ocr_pipeline = None
        self._setup_ocr_pipeline()
    
    def _setup_ocr_pipeline(self) -> None:
        """Setup OCR pipeline."""
        try:
            # Test OCR services availability first
            from .ocr_health_check import check_ocr_services_from_env
            ocr_results = check_ocr_services_from_env()
            
            if not ocr_results['overall_available']:
                self._ocr_available = False
                logger.warning("OCR services not available - Image parser disabled")
                return
            
            # Create LLM clients
            dots_client = DotsOCRClient(self.ocr_config.dots_ocr_config)
            qwen_client = QwenClient(self.ocr_config.qwen_config)
            
            # Create pipeline components
            detector = DotsBlockDetector(dots_client)
            recognizer = QwenBlockRecognizer(qwen_client)
            
            # Create OCR pipeline
            self.ocr_pipeline = ScanPipeline(
                detector=detector,
                recognizer=recognizer
            )
            
            self._ocr_available = True
            logger.info("OCR pipeline configured for image processing")
        except Exception as e:
            self._ocr_available = False
            logger.warning(f"OCR pipeline not available for image processing: {e}")
    
    def supported_extensions(self) -> Set[str]:
        """Get supported extensions."""
        if self._ocr_available:
            return {'.png', '.jpg', '.jpeg'}
        else:
            return set()  # No support if OCR not available
    
    def is_available(self) -> bool:
        """Check if parser is available (OCR services must be available)."""
        return self._ocr_available
    
    def parse(self, file_path: Path) -> Document:
        """
        Parse image using OCR.
        
        Args:
            file_path: Path to image file
            
        Returns:
            Document: Document with recognized fragments
            
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
        
        logger.info(f"Parsing image with OCR: {file_path}")
        
        # Create document metadata
        metadata = Metadata.from_path(
            file_path,
            processing_method="ocr"
        )
        
        try:
            # Load image
            image = Image.open(file_path)
            
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            logger.info(f"Image loaded: {image.size}, mode: {image.mode}")
            
            # Add image info to metadata
            metadata.params.update({
                'image_width': image.size[0],
                'image_height': image.size[1], 
                'image_mode': image.mode,
                'image_format': image.format
            })
            
            # Process image through OCR pipeline
            fragments = list(self.ocr_pipeline.process(image))
            
            logger.info(f"OCR processing completed: found {len(fragments)} fragments")
            
            # Create document
            document = Document(
                fragments=fragments,
                metadata=metadata
            )
            
            # Try to create hierarchical structure from headers
            document.create_structure_from_headers()
            
            return document
            
        except Exception as e:
            logger.error(f"Error processing image {file_path}: {e}")
            raise ValueError(f"Failed to process image: {e}")
    
    def image_to_base64(self, image: Image.Image, format: str = "PNG") -> str:
        """
        Convert image to base64 string.
        
        Args:
            image: PIL image
            format: Format for saving (PNG, JPEG)
            
        Returns:
            str: base64 image string
        """
        buffer = BytesIO()
        image.save(buffer, format=format)
        img_bytes = buffer.getvalue()
        buffer.close()
        
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        return f"data:image/{format.lower()};base64,{img_base64}"

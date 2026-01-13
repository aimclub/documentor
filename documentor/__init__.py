"""
Documentor - Universal document parser with OCR support.

Document processing system for TXT, PDF, and image files 
with automatic text recognition via dots.ocr and Qwen2.5-VL.

Main components:
- DocumentProcessor: Main document processing orchestrator
- Document: LangChain-independent document system
- Parsers: TXT, PDF, Image parsers with OCR
- Loaders: Recursive loader with ZIP support
- OCR Pipeline: dots.ocr + Qwen2.5-VL integration
"""

# Load environment variables from .env file
from .core.load_env import load_env_file
load_env_file()

__version__ = "2.0.0"
__author__ = "Documentor Team"

# Core exports
from .core.document import Document
from .core.interfaces import BaseLoader, BaseParser
from .core.logging import get_logger, setup_logging

from .processing import DocumentProcessor, ProcessingConfig
from .processing.parsers import TxtParser, ImageParser, PdfParser, ParserRegistry

# Optional Word parsers
try:
    from .processing.parsers import DocxParser
    DOCX_PARSER_AVAILABLE = True
except ImportError:
    DOCX_PARSER_AVAILABLE = False

try:
    from .processing.parsers import DocParser
    DOC_PARSER_AVAILABLE = True
except ImportError:
    DOC_PARSER_AVAILABLE = False

from .processing import RecursiveDocumentLoader
from .processing.pipelines.ocr.config import OCRPipelineConfig

# Fragment exports
from .data.structures.fragment import (
    Fragment,
    TextFragment, 
    ParagraphFragment,
    ImageFragment,
    TableFragment,
    HeaderFragment,
    TitleFragment,
    ImageFormulaFragment,
    LatexFormulaFragment,
    ListItemFragment,
    FootnoteFragment,
    HyperlinkFragment,
    StyleFragment,
    CommentFragment,
    BreakFragment
)

# Metadata and structure exports
from .data.structures.metadata import Metadata
from .data.structures.structure import DocumentStructure, StructureNode

__all__ = [
    # Version
    "__version__",
    
    # Core classes
    "Document",
    "DocumentProcessor", 
    "ProcessingConfig",
    
    # Interfaces
    "BaseLoader",
    "BaseParser", 
    
    # Parsers
    "TxtParser",
    "ImageParser", 
    "PdfParser",
    "ParserRegistry",
    
    # Loaders
    "RecursiveDocumentLoader",
    
    # Configuration
    "OCRPipelineConfig",
    
    # Fragments
    "Fragment",
    "TextFragment",
    "ParagraphFragment", 
    "ImageFragment",
    "TableFragment",
    "HeaderFragment",
    "TitleFragment",
    "ImageFormulaFragment",
    "LatexFormulaFragment",
    "ListItemFragment",
    "FootnoteFragment", 
    "HyperlinkFragment",
    "StyleFragment",
    "CommentFragment",
    "BreakFragment",
    
    # Metadata and structures
    "Metadata",
    "DocumentStructure",
    "StructureNode",
    
    # Logging
    "get_logger",
    "setup_logging",
]


def quick_start():
    """
    Quick start for working with Documentor.
    
    Returns:
        DocumentProcessor: Configured document processor
    """
    from .processors import DocumentProcessor
    return DocumentProcessor()


def create_processor(
    auto_watch: bool = False,
    output_directory: str = None,
    log_level: str = "INFO"
) -> DocumentProcessor:
    """
    Create configured DocumentProcessor.
    
    Args:
        auto_watch: Enable file auto-watching
        output_directory: Directory for saving results
        log_level: Logging level
        
    Returns:
        DocumentProcessor: Configured processor
    """
    from pathlib import Path
    from .processors import ProcessingConfig
    
    config = ProcessingConfig.create_default(
        auto_watch=auto_watch,
        output_directory=Path(output_directory) if output_directory else None
    )
    config.log_level = log_level
    
    return DocumentProcessor(config)


# Convenient functions for quick usage
def process_file(file_path: str) -> Document:
    """
    Quickly process single file.
    
    Args:
        file_path: Path to file
        
    Returns:
        Document: Processed document
    """
    processor = quick_start()
    return processor.process_file(Path(file_path))


def process_directory(directory_path: str, recursive: bool = True):
    """
    Quickly process directory with files.
    
    Args:
        directory_path: Path to directory
        recursive: Recursive processing
        
    Returns:
        List[Document]: List of processed documents
    """
    processor = quick_start()
    return processor.process_directory_to_list(Path(directory_path), recursive)


# System information
def get_system_info():
    """
    Get Documentor system information.
    
    Returns:
        dict: Information about version, supported formats, etc.
    """
    processor = quick_start()
    stats = processor.get_processing_stats()
    
    return {
        "version": __version__,
        "supported_extensions": stats["supported_extensions"],
        "parsers": stats["parsers"],
        "ocr_support": True,  # dots.ocr + Qwen2.5
        "langchain_free": True,  # No LangChain dependencies
    }


# ASCII logo for fun
LOGO = """
██████╗  ██████╗  ██████╗██╗   ██╗███╗   ███╗███████╗███╗   ██╗████████╗ ██████╗ ██████╗ 
██╔══██╗██╔═══██╗██╔════╝██║   ██║████╗ ████║██╔════╝████╗  ██║╚══██╔══╝██╔═══██╗██╔══██╗
██║  ██║██║   ██║██║     ██║   ██║██╔████╔██║█████╗  ██╔██╗ ██║   ██║   ██║   ██║██████╔╝
██║  ██║██║   ██║██║     ██║   ██║██║╚██╔╝██║██╔══╝  ██║╚██╗██║   ██║   ██║   ██║██╔══██╗
██████╔╝╚██████╔╝╚██████╗╚██████╔╝██║ ╚═╝ ██║███████╗██║ ╚████║   ██║   ╚██████╔╝██║  ██║
╚═════╝  ╚═════╝  ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚══════╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝
"""

def print_logo():
    """Show Documentor logo."""
    print(LOGO)
    print(f"Version {__version__} - Universal document parser with OCR")
    print("=" * 80)

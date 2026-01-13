"""Document parser system without LangChain dependencies."""

from .txt_parser import TxtParser
from .image_parser import ImageParser
from .pdf_parser import PdfParser
from .registry import ParserRegistry

# Word parsers - optional imports
try:
    from .docx_parser import DocxParser
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    from .doc_parser import DocParser
    DOC_AVAILABLE = True
except ImportError:
    DOC_AVAILABLE = False

__all__ = [
    "TxtParser",
    "ImageParser", 
    "PdfParser",
    "ParserRegistry",
]

# Add Word parsers to exports if available
if DOCX_AVAILABLE:
    __all__.append("DocxParser")

if DOC_AVAILABLE:
    __all__.append("DocParser")

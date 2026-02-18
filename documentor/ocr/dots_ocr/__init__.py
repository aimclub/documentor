"""
Dots.OCR integration module.

Contains classes and functions for working with Dots.OCR:
- Layout detection
- Table parsing
- Text extraction
- Formula extraction
"""

from .client import run_inference, process_layout_detection
from .prompts import DOTS_OCR_PROMPTS, load_prompts_from_config
from .types import LayoutTypeDotsOCR

from .layout_detector import DotsOCRLayoutDetector
from .table_parser import DotsOCRTableParser
from .text_extractor import DotsOCRTextExtractor
from .formula_extractor import DotsOCRFormulaExtractor
from .prompts import get_system_prompt
from .utils import remove_markdown_formatting

__all__ = [
    "run_inference",
    "process_layout_detection",
    "DOTS_OCR_PROMPTS",
    "load_prompts_from_config",
    "get_system_prompt",
    "LayoutTypeDotsOCR",
    "DotsOCRLayoutDetector",
    "DotsOCRTableParser",
    "DotsOCRTextExtractor",
    "DotsOCRFormulaExtractor",
    "remove_markdown_formatting",
]

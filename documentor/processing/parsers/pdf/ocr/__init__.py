"""
OCR modules for PDF parser.

Contains:
- Layout detection via Dots.OCR
- Page rendering to images
- Direct client for Dots.OCR API
"""

from .layout_detector import PdfLayoutDetector
from .page_renderer import PdfPageRenderer
from .dots_ocr_client import run_inference, process_layout_detection

__all__ = [
    "PdfLayoutDetector",
    "PdfPageRenderer",
    "run_inference",
    "process_layout_detection",
]

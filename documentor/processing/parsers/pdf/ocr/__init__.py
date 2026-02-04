"""
OCR модули для PDF парсера.

Содержит:
- Layout detection через Dots.OCR
- Рендеринг страниц в изображения
- Прямой клиент для Dots.OCR API
- Парсинг таблиц через Qwen2.5
"""

from .layout_detector import PdfLayoutDetector
from .page_renderer import PdfPageRenderer
from .dots_ocr_client import run_inference, process_layout_detection
from .qwen_table_parser import (
    parse_table_with_qwen,
    detect_merged_tables,
    markdown_to_dataframe,
)
from .qwen_ocr import ocr_text_with_qwen

__all__ = [
    "PdfLayoutDetector",
    "PdfPageRenderer",
    "run_inference",
    "process_layout_detection",
    "parse_table_with_qwen",
    "detect_merged_tables",
    "markdown_to_dataframe",
    "ocr_text_with_qwen",
]

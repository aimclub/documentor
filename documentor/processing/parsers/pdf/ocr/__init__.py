"""
OCR модули для PDF парсера.

Содержит:
- Layout detection через Dots.OCR
- Рендеринг страниц в изображения
"""

from .layout_detector import PdfLayoutDetector

__all__ = [
    "PdfLayoutDetector",
]

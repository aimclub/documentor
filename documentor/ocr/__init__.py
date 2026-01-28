"""
Модуль для работы с OCR (Optical Character Recognition).

Содержит классы и функции для:
- Layout detection (определение структуры страницы)
- Распознавания текста
- Построения порядка чтения (reading order)
- Работы с различными OCR инструментами (Dots.OCR, Qwen OCR)
- Управления очередями и состоянием моделей
"""

from .base import BaseLayoutDetector, BaseOCR, BaseReadingOrderBuilder
from .manager import DotsOCRManager, OCRTask, TaskStatus, ModelConfig, ModelState
from .dots_ocr import DotsOCRLayoutDetector, get_system_prompt, load_prompts_from_config

__all__ = [
    "BaseLayoutDetector",
    "BaseOCR",
    "BaseReadingOrderBuilder",
    "DotsOCRManager",
    "OCRTask",
    "TaskStatus",
    "ModelConfig",
    "ModelState",
    "DotsOCRLayoutDetector",
    "get_system_prompt",
    "load_prompts_from_config",
]

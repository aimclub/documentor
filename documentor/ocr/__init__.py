"""
Module for working with OCR (Optical Character Recognition).

Contains classes and functions for:
- Layout detection (page structure determination)
- Text recognition
- Reading order building
- Working with Dots.OCR service
- Managing queues and model states
"""

from .base import (
    BaseLayoutDetector,
    BaseOCR,
    BaseReadingOrderBuilder,
    BaseTableParser,
    BaseTextExtractor,
    BaseFormulaExtractor,
)
from .manager import DotsOCRManager, OCRTask, TaskStatus, ModelConfig, ModelState
from .dots_ocr import (
    DotsOCRLayoutDetector,
    DotsOCRTableParser,
    DotsOCRTextExtractor,
    DotsOCRFormulaExtractor,
    get_system_prompt,
    load_prompts_from_config,
)

__all__ = [
    "BaseLayoutDetector",
    "BaseOCR",
    "BaseReadingOrderBuilder",
    "BaseTableParser",
    "BaseTextExtractor",
    "BaseFormulaExtractor",
    "DotsOCRManager",
    "OCRTask",
    "TaskStatus",
    "ModelConfig",
    "ModelState",
    "DotsOCRLayoutDetector",
    "DotsOCRTableParser",
    "DotsOCRTextExtractor",
    "DotsOCRFormulaExtractor",
    "get_system_prompt",
    "load_prompts_from_config",
]

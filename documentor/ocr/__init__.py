"""
Module for working with OCR (Optical Character Recognition).

Contains classes and functions for:
- Layout detection (page structure determination)
- Text recognition
- Reading order building
- Working with various OCR tools (Dots.OCR, Qwen OCR)
- Managing queues and model states
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

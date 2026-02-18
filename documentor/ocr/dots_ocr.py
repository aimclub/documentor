"""
Integration with Dots.OCR for layout detection.

DEPRECATED: This module is kept for backward compatibility.
New code should use documentor.ocr.dots_ocr module instead.

This module re-exports classes and functions from documentor.ocr.dots_ocr.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional
from pathlib import Path

# Re-export from new dots_ocr module for backward compatibility
from .dots_ocr import (
    DotsOCRLayoutDetector,
    DOTS_OCR_PROMPTS,
    load_prompts_from_config,
    get_system_prompt,
    LayoutTypeDotsOCR,
)
from .dots_ocr.client import run_inference, process_layout_detection

warnings.warn(
    "documentor.ocr.dots_ocr module is deprecated. "
    "Use documentor.ocr.dots_ocr.* instead.",
    DeprecationWarning,
    stacklevel=2
)

# All functionality is now in documentor.ocr.dots_ocr submodule
# This file exists only for backward compatibility

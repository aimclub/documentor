"""
Tests for OCR constants.

Tested constants:
- MIN_PIXELS
- MAX_PIXELS
- IMAGE_FACTOR
- image_extensions
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to PYTHONPATH
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest

from documentor.utils.ocr_consts import (
    IMAGE_FACTOR,
    MAX_PIXELS,
    MIN_PIXELS,
    image_extensions,
)


class TestOCRConstants:
    """Tests for OCR constants."""

    def test_min_pixels(self):
        """Test MIN_PIXELS constant."""
        assert MIN_PIXELS == 3136
        assert isinstance(MIN_PIXELS, int)
        assert MIN_PIXELS > 0

    def test_max_pixels(self):
        """Test MAX_PIXELS constant."""
        assert MAX_PIXELS == 11289600
        assert isinstance(MAX_PIXELS, int)
        assert MAX_PIXELS > MIN_PIXELS

    def test_image_factor(self):
        """Test IMAGE_FACTOR constant."""
        assert IMAGE_FACTOR == 28
        assert isinstance(IMAGE_FACTOR, int)
        assert IMAGE_FACTOR > 0

    def test_image_extensions(self):
        """Test image_extensions set."""
        assert isinstance(image_extensions, set)
        assert '.jpg' in image_extensions
        assert '.jpeg' in image_extensions
        assert '.png' in image_extensions
        assert len(image_extensions) == 3

    def test_constants_relationships(self):
        """Test relationships between constants."""
        # MAX_PIXELS should be much larger than MIN_PIXELS
        assert MAX_PIXELS > MIN_PIXELS * 100
        
        # IMAGE_FACTOR should be reasonable for image processing
        assert 1 < IMAGE_FACTOR < 100

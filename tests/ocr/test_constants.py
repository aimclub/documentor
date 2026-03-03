"""
Unit tests for OCR constants.

Tested constants:
- MIN_PIXELS, MAX_PIXELS, IMAGE_FACTOR
- image_extensions
"""

import pytest

from documentor.ocr.constants import (
    IMAGE_FACTOR,
    MAX_PIXELS,
    MIN_PIXELS,
    image_extensions,
)


class TestOCRConstants:
    """Tests for OCR constants."""

    def test_min_pixels(self):
        """MIN_PIXELS has expected value and type."""
        assert MIN_PIXELS == 3136
        assert isinstance(MIN_PIXELS, int)
        assert MIN_PIXELS > 0

    def test_max_pixels(self):
        """MAX_PIXELS has expected value and is greater than MIN_PIXELS."""
        assert MAX_PIXELS == 11289600
        assert isinstance(MAX_PIXELS, int)
        assert MAX_PIXELS > MIN_PIXELS

    def test_image_factor(self):
        """IMAGE_FACTOR has expected value."""
        assert IMAGE_FACTOR == 28
        assert isinstance(IMAGE_FACTOR, int)
        assert IMAGE_FACTOR > 0

    def test_image_extensions_set(self):
        """image_extensions is a set with expected entries."""
        assert isinstance(image_extensions, set)
        assert ".jpg" in image_extensions
        assert ".jpeg" in image_extensions
        assert ".png" in image_extensions
        assert len(image_extensions) == 3

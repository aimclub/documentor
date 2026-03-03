"""
Unit tests for processing image utils.

Tested class: ImageUtils (optimize_image, encode_to_base64,
process_and_encode_image, decode_from_base64).
"""

import pytest
from PIL import Image

from documentor.processing.image.image_utils import ImageUtils


class TestOptimizeImage:
    """Tests for ImageUtils.optimize_image."""

    def test_small_image_unchanged(self):
        """Image smaller than max_dimension is returned as-is (no resize)."""
        img = Image.new("RGB", (100, 100), color="red")
        out = ImageUtils.optimize_image(img, max_dimension=1280)
        assert out.size == (100, 100)

    def test_large_image_resized(self):
        """Image larger than max_dimension is resized."""
        img = Image.new("RGB", (2000, 1000), color="blue")
        out = ImageUtils.optimize_image(img, max_dimension=1280)
        assert out.size[0] <= 1280 and out.size[1] <= 1280


class TestEncodeToBase64:
    """Tests for ImageUtils.encode_to_base64."""

    def test_returns_data_uri(self):
        """encode_to_base64 returns string with data:image/ prefix."""
        img = Image.new("RGB", (10, 10), color="green")
        s = ImageUtils.encode_to_base64(img, format="JPEG")
        assert s.startswith("data:image/")
        assert "base64," in s

    def test_png_format(self):
        """Can encode as PNG."""
        img = Image.new("RGB", (10, 10), color="red")
        s = ImageUtils.encode_to_base64(img, format="PNG")
        assert "image/png" in s


class TestProcessAndEncodeImage:
    """Tests for ImageUtils.process_and_encode_image."""

    def test_returns_base64_string(self):
        """process_and_encode_image returns base64 data URI."""
        img = Image.new("RGB", (50, 50), color="yellow")
        s = ImageUtils.process_and_encode_image(img)
        assert isinstance(s, str)
        assert s.startswith("data:image/")


class TestDecodeFromBase64:
    """Tests for ImageUtils.decode_from_base64."""

    def test_decode_roundtrip(self):
        """decode_from_base64(encode_to_base64(img)) returns image of same size."""
        img = Image.new("RGB", (20, 20), color="blue")
        encoded = ImageUtils.encode_to_base64(img, format="PNG")
        decoded = ImageUtils.decode_from_base64(encoded)
        assert decoded is not None
        assert decoded.size == (20, 20)

    def test_decode_invalid_returns_none(self):
        """Invalid base64 returns None."""
        assert ImageUtils.decode_from_base64("not-valid-base64!!!") is None

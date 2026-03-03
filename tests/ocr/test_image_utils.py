"""
Unit tests for OCR image utilities.

Tested functions:
- round_by_factor, ceil_by_factor, floor_by_factor
- smart_resize
- to_rgb
- image_to_base64, base64_to_image
- fetch_image (PIL, base64, local path; no network)
"""

import pytest
from PIL import Image

from documentor.ocr.image.image_utils import (
    base64_to_image,
    ceil_by_factor,
    floor_by_factor,
    image_to_base64,
    round_by_factor,
    smart_resize,
    to_rgb,
)
from documentor.ocr.image import image_utils


class TestFactorFunctions:
    """Tests for factor-based rounding functions."""

    def test_round_by_factor(self):
        """round_by_factor returns value divisible by factor."""
        assert round_by_factor(100, 28) == 112
        assert round_by_factor(28, 28) == 28
        assert round_by_factor(56, 28) == 56
        assert round_by_factor(30, 28) == 28
        assert round_by_factor(42, 28) == 56

    def test_ceil_by_factor(self):
        """ceil_by_factor returns smallest value >= n divisible by factor."""
        assert ceil_by_factor(28, 28) == 28
        assert ceil_by_factor(29, 28) == 56
        assert ceil_by_factor(56, 28) == 56
        assert ceil_by_factor(1, 28) == 28

    def test_floor_by_factor(self):
        """floor_by_factor returns largest value <= n divisible by factor."""
        assert floor_by_factor(28, 28) == 28
        assert floor_by_factor(29, 28) == 28
        assert floor_by_factor(56, 28) == 56
        assert floor_by_factor(55, 28) == 28


class TestSmartResize:
    """Tests for smart_resize."""

    def test_smart_resize_basic(self):
        """Dimensions divisible by factor and pixel count in range."""
        height, width = smart_resize(100, 200, factor=28, min_pixels=3136, max_pixels=11289600)
        assert height % 28 == 0
        assert width % 28 == 0
        assert 3136 <= height * width <= 11289600

    def test_smart_resize_small_image(self):
        """Small image is upscaled to meet min_pixels."""
        height, width = smart_resize(50, 50, factor=28, min_pixels=3136, max_pixels=11289600)
        assert height * width >= 3136
        assert height % 28 == 0
        assert width % 28 == 0

    def test_smart_resize_large_image(self):
        """Large image is downscaled to meet max_pixels."""
        height, width = smart_resize(5000, 5000, factor=28, min_pixels=3136, max_pixels=11289600)
        assert height * width <= 11289600
        assert height % 28 == 0
        assert width % 28 == 0

    def test_smart_resize_extreme_aspect_ratio_raises(self):
        """Extreme aspect ratio raises ValueError."""
        with pytest.raises(ValueError, match="aspect ratio"):
            smart_resize(1, 300, factor=28, min_pixels=3136, max_pixels=11289600)


class TestToRGB:
    """Tests for to_rgb."""

    def test_to_rgb_rgb_image(self):
        """to_rgb leaves RGB image mode as RGB."""
        img = Image.new("RGB", (100, 100), color="red")
        result = to_rgb(img)
        assert result.mode == "RGB"
        assert result.size == img.size

    def test_to_rgb_rgba_image(self):
        """to_rgb converts RGBA to RGB."""
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        result = to_rgb(img)
        assert result.mode == "RGB"
        assert result.size == img.size

    def test_to_rgb_grayscale_image(self):
        """to_rgb converts L to RGB."""
        img = Image.new("L", (100, 100), color=128)
        result = to_rgb(img)
        assert result.mode == "RGB"
        assert result.size == img.size


class TestImageBase64:
    """Tests for image_to_base64 and base64_to_image."""

    def test_image_to_base64_returns_data_url(self):
        """image_to_base64 returns string starting with data:image/."""
        img = Image.new("RGB", (100, 100), color="red")
        s = image_to_base64(img)
        assert isinstance(s, str)
        assert s.startswith("data:image/")
        assert len(s) > 0

    def test_base64_to_image_roundtrip(self):
        """base64_to_image(image_to_base64(img)) returns same size image."""
        img = Image.new("RGB", (100, 100), color="blue")
        s = image_to_base64(img)
        restored = base64_to_image(s)
        assert restored is not None
        assert restored.size == img.size

    def test_base64_to_image_invalid_returns_none(self):
        """base64_to_image with invalid data returns None."""
        assert base64_to_image("invalid_base64") is None


class TestFetchImage:
    """Tests for fetch_image (PIL, base64, local path; no network)."""

    def test_fetch_image_from_pil(self):
        """fetch_image with PIL Image returns image."""
        img = Image.new("RGB", (100, 100), color="blue")
        result = image_utils.fetch_image(img)
        assert isinstance(result, Image.Image)
        assert result.size == img.size

    def test_fetch_image_from_base64(self):
        """fetch_image with data:image base64 URL returns PIL Image."""
        img = Image.new("RGB", (50, 50), color="green")
        data_url = image_to_base64(img)
        result = image_utils.fetch_image(data_url)
        assert isinstance(result, Image.Image)

    def test_fetch_image_from_local_path(self, tmp_path):
        """fetch_image with local file path loads image."""
        path = tmp_path / "test.png"
        img = Image.new("RGB", (100, 100), color="yellow")
        img.save(path)
        result = image_utils.fetch_image(str(path))
        assert isinstance(result, Image.Image)
        assert result.size == (100, 100)

    def test_fetch_image_none_raises(self):
        """fetch_image with None raises AssertionError."""
        with pytest.raises(AssertionError):
            image_utils.fetch_image(None)

"""
Tests for OCR image utilities.

Tested functions:
- round_by_factor()
- ceil_by_factor()
- floor_by_factor()
- smart_resize()
- image_to_base64()
- base64_to_image()
"""

import base64
import sys
from io import BytesIO
from pathlib import Path

# Add project root to PYTHONPATH
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from PIL import Image

from documentor.ocr.image import (
    base64_to_image,
    ceil_by_factor,
    fetch_image,
    floor_by_factor,
    image_to_base64,
    round_by_factor,
    smart_resize,
    to_rgb,
)


class TestFactorFunctions:
    """Tests for factor-based rounding functions."""

    def test_round_by_factor(self):
        """Test round_by_factor function."""
        # 100 / 28 ≈ 3.57, round(3.57) = 4, 4 * 28 = 112
        assert round_by_factor(100, 28) == 112
        assert round_by_factor(28, 28) == 28
        assert round_by_factor(56, 28) == 56
        assert round_by_factor(30, 28) == 28  # 30/28 ≈ 1.07, round to 1, 1*28 = 28
        assert round_by_factor(42, 28) == 56  # 42/28 = 1.5, round to 2, 2*28 = 56

    def test_ceil_by_factor(self):
        """Test ceil_by_factor function."""
        assert ceil_by_factor(28, 28) == 28
        assert ceil_by_factor(29, 28) == 56  # 29/28 ≈ 1.04, ceil to 2, 2*28 = 56
        assert ceil_by_factor(56, 28) == 56
        assert ceil_by_factor(1, 28) == 28  # 1/28 ≈ 0.04, ceil to 1, 1*28 = 28

    def test_floor_by_factor(self):
        """Test floor_by_factor function."""
        assert floor_by_factor(28, 28) == 28
        assert floor_by_factor(29, 28) == 28  # 29/28 ≈ 1.04, floor to 1, 1*28 = 28
        assert floor_by_factor(56, 28) == 56
        assert floor_by_factor(55, 28) == 28  # 55/28 ≈ 1.96, floor to 1, 1*28 = 28


class TestSmartResize:
    """Tests for smart_resize function."""

    def test_smart_resize_basic(self):
        """Test basic smart_resize functionality."""
        height, width = smart_resize(100, 200, factor=28, min_pixels=3136, max_pixels=11289600)
        
        # Both dimensions should be divisible by factor
        assert height % 28 == 0
        assert width % 28 == 0
        
        # Total pixels should be within range
        total_pixels = height * width
        assert 3136 <= total_pixels <= 11289600

    def test_smart_resize_small_image(self):
        """Test smart_resize with small image."""
        height, width = smart_resize(50, 50, factor=28, min_pixels=3136, max_pixels=11289600)
        
        # Should be resized to meet minimum pixels
        total_pixels = height * width
        assert total_pixels >= 3136
        assert height % 28 == 0
        assert width % 28 == 0

    def test_smart_resize_large_image(self):
        """Test smart_resize with large image."""
        height, width = smart_resize(5000, 5000, factor=28, min_pixels=3136, max_pixels=11289600)
        
        # Should be resized to meet maximum pixels
        total_pixels = height * width
        assert total_pixels <= 11289600
        assert height % 28 == 0
        assert width % 28 == 0

    def test_smart_resize_aspect_ratio(self):
        """Test that smart_resize maintains aspect ratio."""
        original_height, original_width = 200, 400
        height, width = smart_resize(
            original_height, original_width, 
            factor=28, min_pixels=3136, max_pixels=11289600
        )
        
        # Aspect ratio should be approximately maintained
        original_ratio = original_width / original_height
        new_ratio = width / height
        assert abs(original_ratio - new_ratio) < 0.1  # Allow small difference

    def test_smart_resize_extreme_aspect_ratio(self):
        """Test smart_resize with extreme aspect ratio."""
        with pytest.raises(ValueError, match="aspect ratio"):
            smart_resize(1, 300, factor=28, min_pixels=3136, max_pixels=11289600)


class TestImageConversion:
    """Tests for image conversion functions."""

    def test_image_to_base64(self):
        """Test image_to_base64 function."""
        # Create a simple test image
        img = Image.new('RGB', (100, 100), color='red')
        
        base64_str = image_to_base64(img)
        
        assert isinstance(base64_str, str)
        assert base64_str.startswith('data:image/')
        assert len(base64_str) > 0

    def test_base64_to_image(self):
        """Test base64_to_image function."""
        # Create a simple test image
        img = Image.new('RGB', (100, 100), color='blue')
        base64_str = image_to_base64(img)
        
        # Convert back
        restored_img = base64_to_image(base64_str)
        
        assert restored_img is not None
        assert isinstance(restored_img, Image.Image)
        assert restored_img.size == img.size

    def test_base64_to_image_with_data_prefix(self):
        """Test base64_to_image with data:image prefix."""
        img = Image.new('RGB', (50, 50), color='green')
        base64_str = image_to_base64(img)
        
        # Should work with or without prefix
        restored_img1 = base64_to_image(base64_str)
        assert restored_img1 is not None
        
        # Remove prefix and test
        base64_without_prefix = base64_str.split(',')[1] if ',' in base64_str else base64_str
        restored_img2 = base64_to_image(f"data:image/png;base64,{base64_without_prefix}")
        assert restored_img2 is not None

    def test_base64_to_image_invalid(self):
        """Test base64_to_image with invalid data."""
        result = base64_to_image("invalid_base64_string")
        assert result is None

    def test_image_conversion_roundtrip(self):
        """Test full roundtrip: image -> base64 -> image."""
        original_img = Image.new('RGB', (200, 150), color='yellow')
        
        base64_str = image_to_base64(original_img)
        restored_img = base64_to_image(base64_str)
        
        assert restored_img is not None
        assert restored_img.size == original_img.size
        # Note: We can't easily compare pixel data without loading the image,
        # but size should match


class TestToRGB:
    """Tests for to_rgb function."""

    def test_to_rgb_rgb_image(self):
        """Test to_rgb with RGB image."""
        img = Image.new('RGB', (100, 100), color='red')
        result = to_rgb(img)
        
        assert result.mode == 'RGB'
        assert result.size == img.size

    def test_to_rgb_rgba_image(self):
        """Test to_rgb with RGBA image."""
        img = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128))
        result = to_rgb(img)
        
        assert result.mode == 'RGB'
        assert result.size == img.size

    def test_to_rgb_grayscale_image(self):
        """Test to_rgb with grayscale image."""
        img = Image.new('L', (100, 100), color=128)
        result = to_rgb(img)
        
        assert result.mode == 'RGB'
        assert result.size == img.size


class TestFetchImage:
    """Tests for fetch_image function."""

    def test_fetch_image_from_pil(self):
        """Test fetch_image with PIL Image."""
        img = Image.new('RGB', (100, 100), color='blue')
        result = fetch_image(img)
        
        assert isinstance(result, Image.Image)
        assert result.size == img.size

    def test_fetch_image_from_base64(self):
        """Test fetch_image with base64 data URL."""
        img = Image.new('RGB', (50, 50), color='green')
        base64_str = image_to_base64(img)
        
        result = fetch_image(base64_str)
        
        assert isinstance(result, Image.Image)
        # Size might be different due to resizing

    def test_fetch_image_from_local_path(self, tmp_path: Path):
        """Test fetch_image with local file path."""
        img_file = tmp_path / "test_image.png"
        img = Image.new('RGB', (100, 100), color='yellow')
        img.save(img_file)
        
        result = fetch_image(str(img_file))
        
        assert isinstance(result, Image.Image)

    def test_fetch_image_with_resize(self):
        """Test fetch_image with resize parameters."""
        img = Image.new('RGB', (2000, 2000), color='red')
        
        result = fetch_image(
            img,
            resized_height=500,
            resized_width=500
        )
        
        assert isinstance(result, Image.Image)
        # Should be resized (may be slightly larger due to factor rounding, e.g., 504 for factor 28)
        assert result.size[0] <= 504  # 500 rounded up to nearest multiple of 28
        assert result.size[1] <= 504

    def test_fetch_image_with_min_max_pixels(self):
        """Test fetch_image with min/max pixels."""
        img = Image.new('RGB', (50, 50), color='blue')
        
        result = fetch_image(
            img,
            min_pixels=10000,
            max_pixels=1000000
        )
        
        assert isinstance(result, Image.Image)
        total_pixels = result.size[0] * result.size[1]
        assert 10000 <= total_pixels <= 1000000

    def test_fetch_image_none_raises_error(self):
        """Test fetch_image with None raises error."""
        with pytest.raises(AssertionError):
            fetch_image(None)  # type: ignore

    def test_fetch_image_invalid_input_raises_error(self):
        """Test fetch_image with invalid input raises error."""
        # fetch_image tries to open as file first, so it raises FileNotFoundError
        # We check for either ValueError or FileNotFoundError
        with pytest.raises((ValueError, FileNotFoundError)):
            fetch_image("invalid_input_string")

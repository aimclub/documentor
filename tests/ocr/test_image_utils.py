"""
Tests for ImageUtils utility.

Tests:
- ImageUtils.optimize_image
- ImageUtils.encode_to_base64
- ImageUtils.process_and_encode_image
- ImageUtils.decode_from_base64
"""

import sys
from pathlib import Path
import base64
import io

import pytest
from PIL import Image

# Add project root to path
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from documentor.processing.image.image_utils import ImageUtils


class TestImageUtils:
    """Tests for ImageUtils utility."""

    def test_optimize_image_small_image(self):
        """Test optimizing small image (no resize needed)."""
        img = Image.new("RGB", (100, 100), color="white")
        optimized = ImageUtils.optimize_image(img, max_dimension=1280)
        assert optimized.size == (100, 100)

    def test_optimize_image_large_width(self):
        """Test optimizing large image (width > max_dimension)."""
        img = Image.new("RGB", (2000, 1000), color="white")
        optimized = ImageUtils.optimize_image(img, max_dimension=1280)
        assert optimized.width == 1280
        assert optimized.height == 640

    def test_optimize_image_large_height(self):
        """Test optimizing large image (height > max_dimension)."""
        img = Image.new("RGB", (1000, 2000), color="white")
        optimized = ImageUtils.optimize_image(img, max_dimension=1280)
        assert optimized.width == 640
        assert optimized.height == 1280

    def test_encode_to_base64_jpeg(self):
        """Test encoding image to base64 JPEG."""
        img = Image.new("RGB", (100, 100), color="red")
        base64_str = ImageUtils.encode_to_base64(img, format="JPEG", quality=75)
        assert base64_str.startswith("data:image/jpeg;base64,")
        assert len(base64_str) > 50

    def test_encode_to_base64_png(self):
        """Test encoding image to base64 PNG."""
        img = Image.new("RGB", (100, 100), color="blue")
        base64_str = ImageUtils.encode_to_base64(img, format="PNG")
        assert base64_str.startswith("data:image/png;base64,")
        assert len(base64_str) > 50

    def test_process_and_encode_image(self):
        """Test processing and encoding image in one step."""
        img = Image.new("RGB", (2000, 1000), color="green")
        base64_str = ImageUtils.process_and_encode_image(img, max_dimension=1280, quality=75)
        assert base64_str.startswith("data:image/jpeg;base64,")
        decoded = ImageUtils.decode_from_base64(base64_str)
        assert decoded is not None
        assert decoded.width <= 1280
        assert decoded.height <= 1280

    def test_decode_from_base64_with_prefix(self):
        """Test decoding base64 string with data URI prefix."""
        img = Image.new("RGB", (100, 100), color="yellow")
        base64_str = ImageUtils.encode_to_base64(img, format="JPEG")
        decoded = ImageUtils.decode_from_base64(base64_str)
        assert decoded is not None
        assert decoded.size == (100, 100)

    def test_decode_from_base64_without_prefix(self):
        """Test decoding base64 string without data URI prefix."""
        img = Image.new("RGB", (100, 100), color="cyan")
        base64_str = ImageUtils.encode_to_base64(img, format="JPEG")
        base64_only = base64_str.split(",", 1)[1]
        decoded = ImageUtils.decode_from_base64(base64_only)
        assert decoded is not None
        assert decoded.size == (100, 100)

    def test_decode_from_base64_invalid(self):
        """Test decoding invalid base64 string."""
        decoded = ImageUtils.decode_from_base64("invalid_base64_string")
        assert decoded is None

    def test_process_and_encode_image_rgba(self):
        """Test processing RGBA image (converts to RGB for JPEG)."""
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        base64_str = ImageUtils.process_and_encode_image(img, format="JPEG")
        assert base64_str.startswith("data:image/jpeg;base64,")
        decoded = ImageUtils.decode_from_base64(base64_str)
        assert decoded is not None
        assert decoded.mode == "RGB"

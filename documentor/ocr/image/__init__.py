"""
OCR image processing utilities.

Contains functions for:
- Image resizing and optimization for OCR
- Image format conversion
- Base64 encoding/decoding for OCR
- Fetching images from various sources
"""

from .image_utils import (
    smart_resize,
    to_rgb,
    image_to_base64,
    base64_to_image,
    fetch_image,
    round_by_factor,
    ceil_by_factor,
    floor_by_factor,
)

__all__ = [
    "smart_resize",
    "to_rgb",
    "image_to_base64",
    "base64_to_image",
    "fetch_image",
    "round_by_factor",
    "ceil_by_factor",
    "floor_by_factor",
]

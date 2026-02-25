"""
Image processing utility.

Provides common functions for image optimization and base64 encoding.
"""

import base64
import io
import logging
from typing import Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)


class ImageUtils:
    """
    Utility class for image processing operations.
    
    Provides common functionality for image optimization and encoding.
    """

    @staticmethod
    def optimize_image(
        img: Image.Image,
        max_dimension: int = 1280,
        quality: int = 75,
    ) -> Image.Image:
        """
        Optimizes image by resizing if too large.
        
        Args:
            img: PIL Image object.
            max_dimension: Maximum dimension (width or height) in pixels.
            quality: JPEG quality (1-100, higher is better).
        
        Returns:
            Optimized PIL Image.
        """
        if img.width > max_dimension or img.height > max_dimension:
            if img.width > img.height:
                new_width = max_dimension
                new_height = int(img.height * (max_dimension / img.width))
            else:
                new_height = max_dimension
                new_width = int(img.width * (max_dimension / img.height))
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        return img

    @staticmethod
    def encode_to_base64(
        img: Image.Image,
        format: str = "JPEG",
        quality: int = 75,
        optimize: bool = True,
    ) -> str:
        """
        Encodes image to base64 string with data URI prefix.
        
        Args:
            img: PIL Image object.
            format: Image format ("JPEG", "PNG", etc.).
            quality: JPEG quality (1-100, higher is better). Only for JPEG.
            optimize: Whether to optimize the image.
        
        Returns:
            Base64 encoded string with data URI prefix (e.g., "data:image/jpeg;base64,...").
        """
        # Convert RGBA to RGB for JPEG format
        if format == "JPEG" and img.mode in ("RGBA", "LA", "P"):
            # Create white background
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            rgb_img.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = rgb_img
        elif format == "JPEG" and img.mode != "RGB":
            img = img.convert("RGB")
        
        buffer = io.BytesIO()
        
        save_kwargs = {"format": format}
        if format == "JPEG":
            save_kwargs["quality"] = quality
        if optimize:
            save_kwargs["optimize"] = True
        
        img.save(buffer, **save_kwargs)
        img_bytes = buffer.getvalue()
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")
        
        mime_type = f"image/{format.lower()}"
        return f"data:{mime_type};base64,{img_base64}"

    @staticmethod
    def process_and_encode_image(
        img: Image.Image,
        max_dimension: int = 1280,
        format: str = "JPEG",
        quality: int = 75,
    ) -> str:
        """
        Optimizes and encodes image to base64 in one step.
        
        Args:
            img: PIL Image object.
            max_dimension: Maximum dimension (width or height) in pixels.
            format: Image format ("JPEG", "PNG", etc.).
            quality: JPEG quality (1-100, higher is better). Only for JPEG.
        
        Returns:
            Base64 encoded string with data URI prefix.
        """
        optimized_img = ImageUtils.optimize_image(img, max_dimension, quality)
        return ImageUtils.encode_to_base64(optimized_img, format, quality)

    @staticmethod
    def decode_from_base64(base64_string: str) -> Optional[Image.Image]:
        """
        Decodes base64 string to PIL Image.
        
        Args:
            base64_string: Base64 encoded string (with or without data URI prefix).
        
        Returns:
            PIL Image object or None if decoding fails.
        """
        try:
            # Remove data URI prefix if present
            if base64_string.startswith("data:image/"):
                base64_string = base64_string.split(",", 1)[1]
            
            img_data = base64.b64decode(base64_string)
            img = Image.open(io.BytesIO(img_data))
            return img
        except Exception as e:
            logger.error(f"Error decoding base64 image: {e}")
            return None

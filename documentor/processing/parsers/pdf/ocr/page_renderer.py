"""
PDF page rendering to images.

Contains classes for:
- Converting PDF pages to images
- Working with various image formats
- Optimizing images for OCR
"""

from typing import List, Optional, Tuple, Union
from pathlib import Path
from io import BytesIO

from PIL import Image
import fitz

# Import utilities from documentor.ocr
from documentor.ocr.constants import MIN_PIXELS, MAX_PIXELS
from documentor.ocr.image.image_utils import fetch_image


class PdfPageRenderer:
    """
    PDF page renderer to images.
    
    Supports:
    - Rendering all pages or individual pages
    - Resolution scaling during rendering (2x for better OCR quality)
    - Image optimization for OCR via smart_resize
    """
    
    def __init__(
        self,
        render_scale: float = 2.0,
        optimize_for_ocr: bool = True,
        min_pixels: Optional[int] = None,
        max_pixels: Optional[int] = None,
    ) -> None:
        """
        Initialize renderer.
        
        Args:
            render_scale: Render scale (2.0 = 2x increase)
            optimize_for_ocr: Whether to apply smart_resize for OCR optimization
            min_pixels: Minimum number of pixels (if None - uses from dots.ocr)
            max_pixels: Maximum number of pixels (if None - uses from dots.ocr)
        """
        self.render_scale = render_scale
        self.optimize_for_ocr = optimize_for_ocr
        
        if min_pixels is None:
            min_pixels = MIN_PIXELS
        if max_pixels is None:
            max_pixels = MAX_PIXELS
        
        self.min_pixels = min_pixels
        self.max_pixels = max_pixels
    
    def render_page(
        self,
        pdf_path: Path,
        page_num: int,
        return_original: bool = False,
    ) -> Union[Image.Image, Tuple[Image.Image, Image.Image]]:
        """
        Renders a single PDF page to an image.
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (0-based)
            return_original: If True, returns tuple (original_image, optimized_image)
        
        Returns:
            Image.Image or tuple[Image.Image, Image.Image] if return_original=True
        """
        pdf_document = fitz.open(str(pdf_path))
        try:
            page = pdf_document.load_page(page_num)
            mat = fitz.Matrix(self.render_scale, self.render_scale)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("ppm")
            original_image = Image.open(BytesIO(img_data)).convert("RGB")
            
            if self.optimize_for_ocr:
                optimized_image = fetch_image(
                    original_image,
                    min_pixels=self.min_pixels,
                    max_pixels=self.max_pixels,
                )
            else:
                optimized_image = original_image
            
            if return_original:
                return original_image, optimized_image
            return optimized_image
        finally:
            pdf_document.close()
    
    def render_pages(
        self,
        pdf_path: Path,
        page_nums: Optional[List[int]] = None,
        return_originals: bool = False,
    ) -> Union[List[Image.Image], List[Tuple[Image.Image, Image.Image]]]:
        """
        Renders multiple PDF pages to images.
        
        Args:
            pdf_path: Path to PDF file
            page_nums: List of page numbers (0-based). If None - renders all pages
            return_originals: If True, returns tuples (original_image, optimized_image)
        
        Returns:
            List[Image.Image] or List[tuple[Image.Image, Image.Image]]
        """
        pdf_document = fitz.open(str(pdf_path))
        try:
            total_pages = len(pdf_document)
            
            if page_nums is None:
                page_nums = list(range(total_pages))
            
            images = []
            for page_num in page_nums:
                if page_num < 0 or page_num >= total_pages:
                    raise ValueError(f"Page number {page_num} is out of range [0, {total_pages})")
                
                result = self.render_page(pdf_path, page_num, return_original=return_originals)
                images.append(result)
            
            return images
        finally:
            pdf_document.close()
    
    def get_page_count(self, pdf_path: Path) -> int:
        """
        Returns number of pages in PDF.
        
        Args:
            pdf_path: Path to PDF file
        
        Returns:
            Number of pages
        """
        pdf_document = fitz.open(str(pdf_path))
        try:
            return len(pdf_document)
        finally:
            pdf_document.close()

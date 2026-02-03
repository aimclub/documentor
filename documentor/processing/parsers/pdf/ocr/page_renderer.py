"""
Рендеринг страниц PDF в изображения.

Содержит классы для:
- Конвертации страниц PDF в изображения
- Работы с различными форматами изображений
- Оптимизации изображений для OCR
"""

from __future__ import annotations

from typing import List, Optional, Tuple, Union
from pathlib import Path
from io import BytesIO

from PIL import Image
import fitz

# Импортируем утилиты из dots.ocr если доступны
try:
    import sys
    from pathlib import Path as PathLib
    
    _dots_ocr_path = PathLib(__file__).resolve().parents[5] / "dots.ocr"
    if _dots_ocr_path.exists():
        sys.path.insert(0, str(_dots_ocr_path))
    
    from dots_ocr.utils.consts import MIN_PIXELS, MAX_PIXELS
    from dots_ocr.utils.image_utils import fetch_image
except ImportError:
    MIN_PIXELS = None
    MAX_PIXELS = None
    fetch_image = None


class PdfPageRenderer:
    """
    Рендерер страниц PDF в изображения.
    
    Поддерживает:
    - Рендеринг всех страниц или отдельных страниц
    - Увеличение разрешения при рендеринге (2x для лучшего качества OCR)
    - Оптимизацию изображений для OCR через smart_resize
    """
    
    def __init__(
        self,
        render_scale: float = 2.0,
        optimize_for_ocr: bool = True,
        min_pixels: Optional[int] = None,
        max_pixels: Optional[int] = None,
    ) -> None:
        """
        Инициализация рендерера.
        
        Args:
            render_scale: Масштаб рендеринга (2.0 = увеличение в 2 раза)
            optimize_for_ocr: Применять ли smart_resize для оптимизации под OCR
            min_pixels: Минимальное число пикселей (если None - используется из dots.ocr)
            max_pixels: Максимальное число пикселей (если None - используется из dots.ocr)
        """
        self.render_scale = render_scale
        self.optimize_for_ocr = optimize_for_ocr
        
        if min_pixels is None:
            min_pixels = MIN_PIXELS if MIN_PIXELS is not None else 100000
        if max_pixels is None:
            max_pixels = MAX_PIXELS if MAX_PIXELS is not None else 1000000
        
        self.min_pixels = min_pixels
        self.max_pixels = max_pixels
    
    def render_page(
        self,
        pdf_path: Path,
        page_num: int,
        return_original: bool = False,
    ) -> Union[Image.Image, Tuple[Image.Image, Image.Image]]:
        """
        Рендерит одну страницу PDF в изображение.
        
        Args:
            pdf_path: Путь к PDF файлу
            page_num: Номер страницы (0-based)
            return_original: Если True, возвращает кортеж (original_image, optimized_image)
        
        Returns:
            Image.Image или tuple[Image.Image, Image.Image] если return_original=True
        """
        pdf_document = fitz.open(str(pdf_path))
        try:
            page = pdf_document.load_page(page_num)
            mat = fitz.Matrix(self.render_scale, self.render_scale)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("ppm")
            original_image = Image.open(BytesIO(img_data)).convert("RGB")
            
            if self.optimize_for_ocr and fetch_image is not None:
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
        Рендерит несколько страниц PDF в изображения.
        
        Args:
            pdf_path: Путь к PDF файлу
            page_nums: Список номеров страниц (0-based). Если None - рендерит все страницы
            return_originals: Если True, возвращает кортежи (original_image, optimized_image)
        
        Returns:
            List[Image.Image] или List[tuple[Image.Image, Image.Image]]
        """
        pdf_document = fitz.open(str(pdf_path))
        try:
            total_pages = len(pdf_document)
            
            if page_nums is None:
                page_nums = list(range(total_pages))
            
            images = []
            for page_num in page_nums:
                if page_num < 0 or page_num >= total_pages:
                    raise ValueError(f"Номер страницы {page_num} вне диапазона [0, {total_pages})")
                
                result = self.render_page(pdf_path, page_num, return_original=return_originals)
                images.append(result)
            
            return images
        finally:
            pdf_document.close()
    
    def get_page_count(self, pdf_path: Path) -> int:
        """
        Возвращает количество страниц в PDF.
        
        Args:
            pdf_path: Путь к PDF файлу
        
        Returns:
            Количество страниц
        """
        pdf_document = fitz.open(str(pdf_path))
        try:
            return len(pdf_document)
        finally:
            pdf_document.close()

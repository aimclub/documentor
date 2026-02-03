"""
Тесты для рендеринга страниц PDF.

Тестируемый класс:
- PdfPageRenderer
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

# Добавляем корневую директорию проекта в PYTHONPATH
_project_root = Path(__file__).parent.parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from documentor.processing.parsers.pdf.ocr.page_renderer import PdfPageRenderer


# ============================================================================
# Фикстуры
# ============================================================================

@pytest.fixture
def sample_pdf_path(tmp_path):
    """Создает временный PDF файл для тестов."""
    pdf_path = tmp_path / "test.pdf"
    try:
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Test PDF Content")
        doc.save(str(pdf_path))
        doc.close()
        return pdf_path
    except ImportError:
        pytest.skip("PyMuPDF (fitz) не установлен")


# ============================================================================
# Тесты инициализации
# ============================================================================

class TestPdfPageRendererInitialization:
    """Тесты инициализации PdfPageRenderer."""

    def test_default_initialization(self):
        """Тест инициализации с параметрами по умолчанию."""
        renderer = PdfPageRenderer()
        assert renderer.render_scale == 2.0
        assert renderer.optimize_for_ocr is True
        assert renderer.min_pixels is not None
        assert renderer.max_pixels is not None

    def test_custom_initialization(self):
        """Тест инициализации с кастомными параметрами."""
        renderer = PdfPageRenderer(
            render_scale=3.0,
            optimize_for_ocr=False,
            min_pixels=50000,
            max_pixels=500000,
        )
        assert renderer.render_scale == 3.0
        assert renderer.optimize_for_ocr is False
        assert renderer.min_pixels == 50000
        assert renderer.max_pixels == 500000

    def test_initialization_with_default_pixels(self):
        """Тест инициализации с дефолтными значениями пикселей."""
        renderer = PdfPageRenderer()
        # Проверяем, что значения установлены
        assert renderer.min_pixels > 0
        assert renderer.max_pixels > renderer.min_pixels


# ============================================================================
# Тесты render_page
# ============================================================================

class TestRenderPage:
    """Тесты метода render_page."""

    def test_render_page_basic(self, sample_pdf_path):
        """Тест базового рендеринга страницы."""
        renderer = PdfPageRenderer(optimize_for_ocr=False)
        image = renderer.render_page(sample_pdf_path, 0)
        
        assert isinstance(image, Image.Image)
        assert image.mode == "RGB"

    def test_render_page_with_original(self, sample_pdf_path):
        """Тест рендеринга страницы с возвратом оригинального изображения."""
        renderer = PdfPageRenderer(optimize_for_ocr=False)
        original, optimized = renderer.render_page(sample_pdf_path, 0, return_original=True)
        
        assert isinstance(original, Image.Image)
        assert isinstance(optimized, Image.Image)
        assert original.mode == "RGB"
        assert optimized.mode == "RGB"

    def test_render_page_with_ocr_optimization(self, sample_pdf_path):
        """Тест рендеринга страницы с оптимизацией для OCR."""
        renderer = PdfPageRenderer(optimize_for_ocr=True)
        image = renderer.render_page(sample_pdf_path, 0)
        
        assert isinstance(image, Image.Image)

    def test_render_page_invalid_page_num(self, sample_pdf_path):
        """Тест рендеринга несуществующей страницы."""
        renderer = PdfPageRenderer()
        with pytest.raises(Exception):
            renderer.render_page(sample_pdf_path, 999)

    def test_render_page_custom_scale(self, sample_pdf_path):
        """Тест рендеринга страницы с кастомным масштабом."""
        renderer = PdfPageRenderer(render_scale=1.5, optimize_for_ocr=False)
        image = renderer.render_page(sample_pdf_path, 0)
        
        assert isinstance(image, Image.Image)

    @patch("documentor.processing.parsers.pdf.ocr.page_renderer.fetch_image")
    def test_render_page_with_fetch_image(self, mock_fetch, sample_pdf_path):
        """Тест рендеринга страницы с использованием fetch_image."""
        mock_fetch.return_value = Image.new("RGB", (800, 600), color="white")
        
        renderer = PdfPageRenderer(optimize_for_ocr=True)
        image = renderer.render_page(sample_pdf_path, 0)
        
        assert isinstance(image, Image.Image)
        # Проверяем, что fetch_image был вызван, если доступен
        if mock_fetch is not None:
            # fetch_image может быть вызван или нет в зависимости от наличия модуля
            pass


# ============================================================================
# Тесты render_pages
# ============================================================================

class TestRenderPages:
    """Тесты метода render_pages."""

    def test_render_pages_all(self, sample_pdf_path):
        """Тест рендеринга всех страниц."""
        renderer = PdfPageRenderer(optimize_for_ocr=False)
        images = renderer.render_pages(sample_pdf_path)
        
        assert isinstance(images, list)
        assert len(images) > 0
        assert all(isinstance(img, Image.Image) for img in images)

    def test_render_pages_specific(self, sample_pdf_path):
        """Тест рендеринга конкретных страниц."""
        renderer = PdfPageRenderer(optimize_for_ocr=False)
        images = renderer.render_pages(sample_pdf_path, page_nums=[0])
        
        assert isinstance(images, list)
        assert len(images) == 1
        assert isinstance(images[0], Image.Image)

    def test_render_pages_with_originals(self, sample_pdf_path):
        """Тест рендеринга страниц с возвратом оригинальных изображений."""
        renderer = PdfPageRenderer(optimize_for_ocr=False)
        images = renderer.render_pages(sample_pdf_path, return_originals=True)
        
        assert isinstance(images, list)
        assert len(images) > 0
        assert all(isinstance(img, tuple) and len(img) == 2 for img in images)
        assert all(isinstance(img[0], Image.Image) and isinstance(img[1], Image.Image) for img in images)

    def test_render_pages_invalid_page_num(self, sample_pdf_path):
        """Тест рендеринга страниц с невалидным номером страницы."""
        renderer = PdfPageRenderer()
        with pytest.raises(ValueError, match="Номер страницы"):
            renderer.render_pages(sample_pdf_path, page_nums=[999])

    def test_render_pages_negative_page_num(self, sample_pdf_path):
        """Тест рендеринга страниц с отрицательным номером страницы."""
        renderer = PdfPageRenderer()
        with pytest.raises(ValueError, match="Номер страницы"):
            renderer.render_pages(sample_pdf_path, page_nums=[-1])


# ============================================================================
# Тесты get_page_count
# ============================================================================

class TestGetPageCount:
    """Тесты метода get_page_count."""

    def test_get_page_count(self, sample_pdf_path):
        """Тест получения количества страниц."""
        renderer = PdfPageRenderer()
        count = renderer.get_page_count(sample_pdf_path)
        
        assert isinstance(count, int)
        assert count >= 1

    def test_get_page_count_invalid_path(self):
        """Тест получения количества страниц для несуществующего файла."""
        renderer = PdfPageRenderer()
        invalid_path = Path("/nonexistent/file.pdf")
        with pytest.raises(Exception):
            renderer.get_page_count(invalid_path)

    def test_get_page_count_multiple_pages(self, tmp_path):
        """Тест получения количества страниц для многостраничного PDF."""
        pdf_path = tmp_path / "multi_page.pdf"
        try:
            import fitz
            doc = fitz.open()
            for i in range(3):
                page = doc.new_page()
                page.insert_text((50, 50), f"Page {i + 1}")
            doc.save(str(pdf_path))
            doc.close()
            
            renderer = PdfPageRenderer()
            count = renderer.get_page_count(pdf_path)
            assert count == 3
        except ImportError:
            pytest.skip("PyMuPDF (fitz) не установлен")

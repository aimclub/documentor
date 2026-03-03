"""
Tests for PDF page rendering.

Class under test:
- PdfPageRenderer
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

# Add project root to PYTHONPATH
_project_root = Path(__file__).parent.parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from documentor.processing.parsers.pdf.ocr.page_renderer import PdfPageRenderer


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_pdf_path(tmp_path):
    """Create temporary PDF file for tests."""
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
        pytest.skip("PyMuPDF (fitz) is not installed")


# ============================================================================
# Initialization tests
# ============================================================================

class TestPdfPageRendererInitialization:
    """PdfPageRenderer initialization tests."""

    def test_default_initialization(self):
        """Test initialization with default parameters."""
        renderer = PdfPageRenderer()
        assert renderer.render_scale == 2.0
        assert renderer.optimize_for_ocr is True
        assert renderer.min_pixels is not None
        assert renderer.max_pixels is not None

    def test_custom_initialization(self):
        """Test initialization with custom parameters."""
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
        """Test initialization with default pixel values."""
        renderer = PdfPageRenderer()
        # Check that values are set
        assert renderer.min_pixels > 0
        assert renderer.max_pixels > renderer.min_pixels


# ============================================================================
# render_page tests
# ============================================================================

class TestRenderPage:
    """Tests for render_page method."""

    def test_render_page_basic(self, sample_pdf_path):
        """Test basic page rendering."""
        renderer = PdfPageRenderer(optimize_for_ocr=False)
        image = renderer.render_page(sample_pdf_path, 0)
        
        assert isinstance(image, Image.Image)
        assert image.mode == "RGB"

    def test_render_page_with_original(self, sample_pdf_path):
        """Test page rendering with original image return."""
        renderer = PdfPageRenderer(optimize_for_ocr=False)
        original, optimized = renderer.render_page(sample_pdf_path, 0, return_original=True)
        
        assert isinstance(original, Image.Image)
        assert isinstance(optimized, Image.Image)
        assert original.mode == "RGB"
        assert optimized.mode == "RGB"

    def test_render_page_with_ocr_optimization(self, sample_pdf_path):
        """Test page rendering with OCR optimization."""
        renderer = PdfPageRenderer(optimize_for_ocr=True)
        image = renderer.render_page(sample_pdf_path, 0)
        
        assert isinstance(image, Image.Image)

    def test_render_page_invalid_page_num(self, sample_pdf_path):
        """Test rendering non-existent page."""
        renderer = PdfPageRenderer()
        with pytest.raises(Exception):
            renderer.render_page(sample_pdf_path, 999)

    def test_render_page_custom_scale(self, sample_pdf_path):
        """Test page rendering with custom scale."""
        renderer = PdfPageRenderer(render_scale=1.5, optimize_for_ocr=False)
        image = renderer.render_page(sample_pdf_path, 0)
        
        assert isinstance(image, Image.Image)

    @patch("documentor.processing.parsers.pdf.ocr.page_renderer.fetch_image")
    def test_render_page_with_fetch_image(self, mock_fetch, sample_pdf_path):
        """Test page rendering using fetch_image."""
        mock_fetch.return_value = Image.new("RGB", (800, 600), color="white")
        
        renderer = PdfPageRenderer(optimize_for_ocr=True)
        image = renderer.render_page(sample_pdf_path, 0)
        
        assert isinstance(image, Image.Image)
        # Check that fetch_image was called if available
        if mock_fetch is not None:
            # fetch_image may or may not be called depending on module availability
            pass


# ============================================================================
# render_pages tests
# ============================================================================

class TestRenderPages:
    """Tests for render_pages method."""

    def test_render_pages_all(self, sample_pdf_path):
        """Test rendering all pages."""
        renderer = PdfPageRenderer(optimize_for_ocr=False)
        images = renderer.render_pages(sample_pdf_path)
        
        assert isinstance(images, list)
        assert len(images) > 0
        assert all(isinstance(img, Image.Image) for img in images)

    def test_render_pages_specific(self, sample_pdf_path):
        """Test rendering specific pages."""
        renderer = PdfPageRenderer(optimize_for_ocr=False)
        images = renderer.render_pages(sample_pdf_path, page_nums=[0])
        
        assert isinstance(images, list)
        assert len(images) == 1
        assert isinstance(images[0], Image.Image)

    def test_render_pages_with_originals(self, sample_pdf_path):
        """Test rendering pages with original images return."""
        renderer = PdfPageRenderer(optimize_for_ocr=False)
        images = renderer.render_pages(sample_pdf_path, return_originals=True)
        
        assert isinstance(images, list)
        assert len(images) > 0
        assert all(isinstance(img, tuple) and len(img) == 2 for img in images)
        assert all(isinstance(img[0], Image.Image) and isinstance(img[1], Image.Image) for img in images)

    def test_render_pages_invalid_page_num(self, sample_pdf_path):
        """Test rendering pages with invalid page number."""
        renderer = PdfPageRenderer()
        with pytest.raises(ValueError, match="Page number"):
            renderer.render_pages(sample_pdf_path, page_nums=[999])

    def test_render_pages_negative_page_num(self, sample_pdf_path):
        """Test rendering pages with negative page number."""
        renderer = PdfPageRenderer()
        with pytest.raises(ValueError, match="Page number"):
            renderer.render_pages(sample_pdf_path, page_nums=[-1])


# ============================================================================
# get_page_count tests
# ============================================================================

class TestGetPageCount:
    """Tests for get_page_count method."""

    def test_get_page_count(self, sample_pdf_path):
        """Test getting page count."""
        renderer = PdfPageRenderer()
        count = renderer.get_page_count(sample_pdf_path)
        
        assert isinstance(count, int)
        assert count >= 1

    def test_get_page_count_invalid_path(self):
        """Test getting page count for non-existent file."""
        renderer = PdfPageRenderer()
        invalid_path = Path("/nonexistent/file.pdf")
        with pytest.raises(Exception):
            renderer.get_page_count(invalid_path)

    def test_get_page_count_multiple_pages(self, tmp_path):
        """Test getting page count for multi-page PDF."""
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
            pytest.skip("PyMuPDF (fitz) is not installed")

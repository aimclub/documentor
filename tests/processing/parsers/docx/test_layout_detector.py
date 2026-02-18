"""
Tests for DocxLayoutDetector.

Tests:
- DocxLayoutDetector.detect_layout_for_all_pages
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

# Add project root to path
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from documentor.processing.parsers.docx.layout_detector import DocxLayoutDetector


@pytest.fixture
def sample_pdf_path(tmp_path):
    """Create a temporary PDF file for tests."""
    try:
        import fitz
        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Test PDF Content")
        doc.save(str(pdf_path))
        doc.close()
        return pdf_path
    except ImportError:
        pytest.skip("PyMuPDF (fitz) not installed")


@pytest.fixture
def mock_image():
    """Create a mock image."""
    return Image.new("RGB", (800, 600), color="white")


@pytest.fixture
def layout_detector():
    """Create DocxLayoutDetector instance."""
    config = {
        "layout_detection": {
            "render_scale": 2.0,
        },
        "processing": {
            "skip_title_page": False,
        },
    }
    return DocxLayoutDetector(config=config)


class TestDocxLayoutDetector:
    """Tests for DocxLayoutDetector."""

    @patch("documentor.processing.parsers.docx.layout_detector.PdfPageRenderer")
    @patch("documentor.processing.parsers.docx.layout_detector.process_layout_detection")
    def test_detect_layout_for_all_pages(self, mock_process_layout, mock_renderer_class, layout_detector, sample_pdf_path, mock_image):
        """Test detecting layout for all pages."""
        mock_renderer = MagicMock()
        mock_renderer.render_page.return_value = (mock_image, mock_image)
        mock_renderer_class.return_value = mock_renderer
        
        # Mock process_layout_detection to return tuple (layout, _, success)
        mock_process_layout.return_value = (
            [{"bbox": [0, 0, 100, 50], "category": "Text", "page_num": 0}],
            None,
            True
        )
        
        layout_detector.renderer = mock_renderer
        
        elements, page_images = layout_detector.detect_layout_for_all_pages(sample_pdf_path)
        
        assert len(elements) > 0
        assert isinstance(page_images, dict)
        mock_process_layout.assert_called()

    @patch("documentor.processing.parsers.docx.layout_detector.PdfPageRenderer")
    @patch("documentor.processing.parsers.docx.layout_detector.process_layout_detection")
    def test_detect_layout_skip_title_page(self, mock_process_layout, mock_renderer_class, layout_detector, sample_pdf_path, mock_image):
        """Test detecting layout with title page skipped."""
        layout_detector.config["processing"]["skip_title_page"] = True
        
        mock_renderer = MagicMock()
        mock_renderer.render_page.return_value = (mock_image, mock_image)
        mock_renderer_class.return_value = mock_renderer
        
        mock_process_layout.return_value = []
        
        layout_detector.renderer = mock_renderer
        
        elements, page_images = layout_detector.detect_layout_for_all_pages(sample_pdf_path)
        
        # Should skip first page
        assert isinstance(elements, list)
        assert isinstance(page_images, dict)

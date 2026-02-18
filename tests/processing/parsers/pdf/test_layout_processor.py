"""
Tests for PdfLayoutProcessor.

Tests:
- PdfLayoutProcessor.detect_layout_for_all_pages
- PdfLayoutProcessor.reprocess_tables_with_all_en
- PdfLayoutProcessor.filter_layout_elements
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

from documentor.processing.parsers.pdf.layout_processor import PdfLayoutProcessor


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
        return str(pdf_path)
    except ImportError:
        pytest.skip("PyMuPDF (fitz) not installed")


@pytest.fixture
def mock_image():
    """Create a mock image."""
    return Image.new("RGB", (800, 600), color="white")


@pytest.fixture
def layout_processor():
    """Create PdfLayoutProcessor instance."""
    config = {
        "layout_detection": {
            "render_scale": 2.0,
            "optimize_for_ocr": True,
            "use_direct_api": True,
        },
    }
    return PdfLayoutProcessor(config=config)


class TestPdfLayoutProcessor:
    """Tests for PdfLayoutProcessor."""

    @patch("documentor.processing.parsers.pdf.layout_processor.PdfPageRenderer")
    @patch("documentor.processing.parsers.pdf.layout_processor.PdfLayoutDetector")
    def test_detect_layout_for_all_pages(self, mock_detector_class, mock_renderer_class, layout_processor, sample_pdf_path, mock_image):
        """Test detecting layout for all pages."""
        mock_renderer = MagicMock()
        mock_renderer.get_page_count.return_value = 1
        mock_renderer.render_page.return_value = (mock_image, mock_image)
        mock_renderer_class.return_value = mock_renderer
        
        mock_detector = MagicMock()
        mock_detector.detect_layout.return_value = [
            {"bbox": [0, 0, 100, 50], "category": "Text", "page_num": 0},
        ]
        mock_detector_class.return_value = mock_detector
        
        layout_processor.page_renderer = mock_renderer
        layout_processor.layout_detector = mock_detector
        
        result = layout_processor.detect_layout_for_all_pages(sample_pdf_path, use_text_extraction=False)
        
        assert len(result) > 0
        assert all("page_num" in elem for elem in result)
        mock_detector.detect_layout.assert_called()

    def test_filter_layout_elements(self, layout_processor):
        """Test filtering layout elements."""
        elements = [
            {"category": "Page-header", "bbox": [0, 0, 100, 50]},
            {"category": "Text", "bbox": [0, 100, 100, 150]},
            {"category": "Page-footer", "bbox": [0, 200, 100, 250]},
            {"category": "Picture", "bbox": [0, 300, 100, 350]},
        ]
        
        filtered = layout_processor.filter_layout_elements(elements)
        
        assert len(filtered) == 2
        assert all(e["category"] in ["Text", "Picture"] for e in filtered)

    @patch("documentor.processing.parsers.pdf.layout_processor.PdfPageRenderer")
    @patch("documentor.processing.parsers.pdf.ocr.dots_ocr_client.process_layout_detection")
    def test_reprocess_tables_with_all_en(self, mock_process_layout, mock_renderer_class, layout_processor, sample_pdf_path, mock_image):
        """Test reprocessing tables with all_en prompt."""
        mock_renderer = MagicMock()
        mock_renderer.render_page.return_value = (mock_image, mock_image)
        mock_renderer_class.return_value = mock_renderer
        
        # Mock process_layout_detection to return tuple (layout, _, success)
        mock_process_layout.return_value = (
            [{"bbox": [0, 0, 100, 50], "category": "Table", "page_num": 0, "table_html": "<table></table>"}],
            None,
            True
        )
        
        layout_processor.page_renderer = mock_renderer
        
        layout_elements = [
            {"bbox": [0, 0, 100, 50], "category": "Table", "page_num": 0},
        ]
        
        result = layout_processor.reprocess_tables_with_all_en(sample_pdf_path, layout_elements)
        
        # Should have reprocessed table with HTML
        assert len(result) > 0
        mock_process_layout.assert_called()

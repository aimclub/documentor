"""
Tests for PdfTextExtractorUtil utility.

Tests:
- PdfTextExtractorUtil.extract_text_by_bbox
- PdfTextExtractorUtil.extract_text_for_elements
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path (tests/processing/parsers/pdf/)
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    import fitz
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

from documentor.utils.pdf_text_extractor import PdfTextExtractorUtil


@pytest.fixture
def sample_pdf_path(tmp_path):
    """Create a temporary PDF file for tests."""
    if not FITZ_AVAILABLE:
        pytest.skip("PyMuPDF (fitz) not installed")

    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Test PDF Content")
    page.insert_text((50, 100), "Another line of text")
    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)


@pytest.fixture
def mock_page():
    """Create a mock PDF page."""
    page = MagicMock()
    page.get_textbox.return_value = "Extracted text"
    page.get_text.return_value = "Fallback text"
    return page


class TestPdfTextExtractorUtil:
    """Tests for PdfTextExtractorUtil."""

    def test_extract_text_by_bbox_success(self, mock_page):
        """Test extracting text by bbox successfully."""
        bbox = [50, 50, 200, 100]
        text = PdfTextExtractorUtil.extract_text_by_bbox(mock_page, bbox, render_scale=2.0)
        assert text == "Extracted text"
        mock_page.get_textbox.assert_called_once()

    def test_extract_text_by_bbox_invalid_bbox(self, mock_page):
        """Test extracting text with invalid bbox."""
        bbox = [50, 50]  # Too short
        text = PdfTextExtractorUtil.extract_text_by_bbox(mock_page, bbox, render_scale=2.0)
        assert text == ""

    def test_extract_text_by_bbox_empty_result(self, mock_page):
        """Test extracting text when get_textbox returns empty."""
        mock_page.get_textbox.return_value = ""

        def mock_get_text(mode="text", clip=None):
            if mode == "dict":
                return {
                    "blocks": [
                        {
                            "lines": [
                                {
                                    "spans": [
                                        {"text": "Fallback text", "bbox": [25, 25, 100, 50]}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            return "Fallback text"

        mock_page.get_text.side_effect = mock_get_text

        bbox = [50, 50, 200, 100]
        text = PdfTextExtractorUtil.extract_text_by_bbox(mock_page, bbox, render_scale=2.0)
        assert text == "Fallback text"

    def test_extract_text_by_bbox_exception(self, mock_page):
        """Test extracting text when exception occurs."""
        mock_page.get_textbox.side_effect = Exception("Error")
        bbox = [50, 50, 200, 100]
        text = PdfTextExtractorUtil.extract_text_by_bbox(mock_page, bbox, render_scale=2.0)
        assert text == ""

    def test_extract_text_for_elements_success(self, sample_pdf_path):
        """Test extracting text for multiple elements."""
        if not FITZ_AVAILABLE:
            pytest.skip("PyMuPDF (fitz) not installed")

        doc = fitz.open(sample_pdf_path)
        try:
            elements = [
                {"category": "Text", "bbox": [40, 40, 300, 60], "page_num": 0},
                {"category": "Picture", "bbox": [0, 0, 100, 100], "page_num": 0},
            ]
            results = PdfTextExtractorUtil.extract_text_for_elements(
                elements, doc, render_scale=1.0
            )
            assert len(results) == 2
            assert "text" in results[0]
            assert results[0]["category"] == "Text"
            assert results[1]["category"] == "Picture"
        finally:
            doc.close()

    def test_extract_text_for_elements_invalid_bbox(self, sample_pdf_path):
        """Test extracting text for elements with invalid bbox."""
        if not FITZ_AVAILABLE:
            pytest.skip("PyMuPDF (fitz) not installed")

        doc = fitz.open(sample_pdf_path)
        try:
            elements = [{"category": "Text", "bbox": [], "page_num": 0}]
            results = PdfTextExtractorUtil.extract_text_for_elements(
                elements, doc, render_scale=1.0
            )
            assert len(results) == 1
            assert results[0]["text"] == ""
        finally:
            doc.close()

    def test_extract_text_for_elements_invalid_page(self, sample_pdf_path):
        """Test extracting text for elements with invalid page number."""
        if not FITZ_AVAILABLE:
            pytest.skip("PyMuPDF (fitz) not installed")

        doc = fitz.open(sample_pdf_path)
        try:
            elements = [{"category": "Text", "bbox": [50, 50, 200, 100], "page_num": 999}]
            results = PdfTextExtractorUtil.extract_text_for_elements(
                elements, doc, render_scale=1.0
            )
            assert len(results) == 1
            assert results[0]["text"] == ""
        finally:
            doc.close()

    def test_extract_text_for_elements_filtered_categories(self, sample_pdf_path):
        """Test extracting text with filtered categories."""
        if not FITZ_AVAILABLE:
            pytest.skip("PyMuPDF (fitz) not installed")

        doc = fitz.open(sample_pdf_path)
        try:
            elements = [
                {"category": "Text", "bbox": [40, 40, 300, 60], "page_num": 0},
                {"category": "Section-header", "bbox": [40, 100, 300, 120], "page_num": 0},
                {"category": "Picture", "bbox": [0, 0, 100, 100], "page_num": 0},
            ]
            results = PdfTextExtractorUtil.extract_text_for_elements(
                elements, doc, render_scale=1.0, allowed_categories=["Text"]
            )
            assert len(results) == 3
            assert "text" in results[0]
            assert results[1]["category"] == "Section-header"
            assert results[2]["category"] == "Picture"
        finally:
            doc.close()

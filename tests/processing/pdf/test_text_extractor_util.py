"""
Unit tests for PDF text extractor util.

Tested class: PdfTextExtractorUtil (extract_text_by_bbox, extract_text_for_elements).
Uses mocks for fitz to avoid real PDF dependency in unit tests.
"""

from unittest.mock import MagicMock

import pytest

from documentor.processing.pdf.text_extractor_util import PdfTextExtractorUtil


class TestExtractTextByBbox:
    """Tests for PdfTextExtractorUtil.extract_text_by_bbox."""

    def test_bbox_fewer_than_four_returns_empty(self):
        """Bbox with fewer than 4 coordinates returns empty string."""
        mock_page = MagicMock()
        assert PdfTextExtractorUtil.extract_text_by_bbox(mock_page, []) == ""
        assert PdfTextExtractorUtil.extract_text_by_bbox(mock_page, [0, 0]) == ""

    def test_returns_text_from_mock_page(self):
        """When get_textbox returns text, that text is returned."""
        mock_page = MagicMock()
        mock_page.get_textbox.return_value = "  extracted text  "
        result = PdfTextExtractorUtil.extract_text_by_bbox(
            mock_page, [0, 0, 100, 100], render_scale=2.0
        )
        assert result.strip() == "extracted text"
        mock_page.get_textbox.assert_called_once()


class TestExtractTextForElements:
    """Tests for PdfTextExtractorUtil.extract_text_for_elements."""

    def test_empty_elements_returns_empty_list(self):
        """Empty elements list returns empty list."""
        mock_doc = MagicMock()
        assert PdfTextExtractorUtil.extract_text_for_elements([], mock_doc) == []

    def test_element_without_allowed_category_unchanged(self):
        """Element with category not in allowed_categories is passed through with no text key or unchanged."""
        mock_doc = MagicMock()
        elements = [{"category": "Formula", "bbox": [0, 0, 10, 10], "page_num": 0}]
        result = PdfTextExtractorUtil.extract_text_for_elements(
            elements, mock_doc, allowed_categories=["Text"]
        )
        assert len(result) == 1
        assert result[0]["category"] == "Formula"

    def test_element_with_short_bbox_gets_empty_text(self):
        """Element with bbox length < 4 gets text set to empty."""
        mock_doc = MagicMock()
        elements = [{"category": "Text", "bbox": [0, 0], "page_num": 0}]
        result = PdfTextExtractorUtil.extract_text_for_elements(elements, mock_doc)
        assert len(result) == 1
        assert result[0].get("text") == ""

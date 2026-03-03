"""
Tests for PdfTableParser.

Tests:
- PdfTableParser.parse_tables
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pandas as pd

# Add project root to path
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    import fitz
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

from documentor.domain import Element, ElementType
from documentor.processing.parsers.pdf.table_parser import PdfTableParser


@pytest.fixture
def sample_pdf_path(tmp_path):
    """Create a temporary PDF file for tests."""
    if not FITZ_AVAILABLE:
        pytest.skip("PyMuPDF (fitz) not installed")
    
    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    page = doc.new_page()
    # Create a simple table-like structure
    page.insert_text((50, 50), "Header1")
    page.insert_text((150, 50), "Header2")
    page.insert_text((50, 100), "Value1")
    page.insert_text((150, 100), "Value2")
    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)


@pytest.fixture
def table_parser():
    """Create PdfTableParser instance."""
    config = {
        "layout_detection": {
            "render_scale": 2.0,
        },
    }
    return PdfTableParser(config=config)


class TestPdfTableParser:
    """Tests for PdfTableParser."""

    def test_parse_tables_no_tables(self, table_parser, sample_pdf_path):
        """Test parsing when there are no tables."""
        elements = [
            Element(
                id="00000001",
                type=ElementType.TEXT,
                content="Text content",
                metadata={},
            ),
        ]
        
        result = table_parser.parse_tables(elements, sample_pdf_path)
        assert len(result) == 1
        assert result[0].type == ElementType.TEXT

    def test_parse_tables_with_html(self, table_parser, sample_pdf_path):
        """Test parsing tables with HTML from Dots OCR."""
        if not FITZ_AVAILABLE:
            pytest.skip("PyMuPDF (fitz) not installed")
        
        table_html = "<table><tr><td>Header1</td><td>Header2</td></tr><tr><td>Value1</td><td>Value2</td></tr></table>"
        
        elements = [
            Element(
                id="00000001",
                type=ElementType.TABLE,
                content="",
                metadata={
                    "bbox": [50, 50, 200, 150],
                    "page_num": 0,
                    "table_html": table_html,
                },
            ),
        ]
        
        with patch("documentor.processing.parsers.pdf.table_parser.parse_table_from_html") as mock_parse:
            mock_parse.return_value = (table_html, True)
            
            result = table_parser.parse_tables(elements, sample_pdf_path)
            
            assert len(result) == 1
            assert result[0].type == ElementType.TABLE
            assert "<table>" in result[0].content or "image_data" in result[0].metadata

    def test_parse_tables_invalid_bbox(self, table_parser, sample_pdf_path):
        """Test parsing tables with invalid bbox."""
        elements = [
            Element(
                id="00000001",
                type=ElementType.TABLE,
                content="",
                metadata={
                    "bbox": [50, 50],  # Invalid bbox
                    "page_num": 0,
                    "table_html": "<table></table>",
                },
            ),
        ]
        
        result = table_parser.parse_tables(elements, sample_pdf_path)
        assert len(result) == 1
        # Table should still be in result, but not processed

    def test_parse_tables_no_html(self, table_parser, sample_pdf_path):
        """Test parsing tables without HTML."""
        if not FITZ_AVAILABLE:
            pytest.skip("PyMuPDF (fitz) not installed")
        
        elements = [
            Element(
                id="00000001",
                type=ElementType.TABLE,
                content="",
                metadata={
                    "bbox": [50, 50, 200, 150],
                    "page_num": 0,
                    # No table_html
                },
            ),
        ]
        
        result = table_parser.parse_tables(elements, sample_pdf_path)
        
        assert len(result) == 1
        assert result[0].type == ElementType.TABLE
        assert "parsing_error" in result[0].metadata

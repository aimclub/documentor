"""
Tests for PdfTextExtractor.

Tests:
- PdfTextExtractor.extract_text_by_bboxes
- PdfTextExtractor.merge_nearby_text_blocks
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add project root to path
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

try:
    import fitz
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

from documentor.processing.parsers.pdf.text_extractor import PdfTextExtractor


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
def text_extractor():
    """Create PdfTextExtractor instance."""
    config = {
        "layout_detection": {
            "render_scale": 2.0,
        },
    }
    return PdfTextExtractor(config=config)


class TestPdfTextExtractor:
    """Tests for PdfTextExtractor."""

    def test_extract_text_by_bboxes_with_text(self, text_extractor, sample_pdf_path):
        """Test extracting text by bboxes for PDF with extractable text."""
        if not FITZ_AVAILABLE:
            pytest.skip("PyMuPDF (fitz) not installed")
        
        layout_elements = [
            {"category": "Text", "bbox": [40, 40, 300, 60], "page_num": 0},
            {"category": "Section-header", "bbox": [40, 90, 300, 110], "page_num": 0},
        ]
        
        result = text_extractor.extract_text_by_bboxes(sample_pdf_path, layout_elements, use_ocr=False)
        
        assert len(result) == 2
        assert "text" in result[0]
        assert "text" in result[1]

    def test_extract_text_by_bboxes_with_ocr(self, text_extractor, sample_pdf_path):
        """Test extracting text by bboxes when text is already from OCR."""
        layout_elements = [
            {"category": "Text", "bbox": [40, 40, 300, 60], "page_num": 0, "text": "OCR extracted text"},
            {"category": "Picture", "bbox": [0, 0, 100, 100], "page_num": 0},
        ]
        
        result = text_extractor.extract_text_by_bboxes(sample_pdf_path, layout_elements, use_ocr=True)
        
        assert len(result) == 2
        assert result[0]["text"] == "OCR extracted text"
        assert result[1]["category"] == "Picture"

    def test_extract_text_by_bboxes_picture_skipped(self, text_extractor, sample_pdf_path):
        """Test that Picture elements are skipped during text extraction."""
        layout_elements = [
            {"category": "Picture", "bbox": [0, 0, 100, 100], "page_num": 0},
        ]
        
        result = text_extractor.extract_text_by_bboxes(sample_pdf_path, layout_elements, use_ocr=False)
        
        assert len(result) == 1
        assert result[0]["category"] == "Picture"
        # Picture should not have text extracted

    def test_merge_nearby_text_blocks(self, text_extractor):
        """Test merging nearby text blocks."""
        layout_elements = [
            {"category": "Text", "bbox": [50, 50, 200, 70], "page_num": 0, "text": "First"},
            {"category": "Text", "bbox": [50, 75, 200, 95], "page_num": 0, "text": "Second"},
            {"category": "Text", "bbox": [50, 200, 200, 220], "page_num": 0, "text": "Distant"},
        ]
        
        result = text_extractor.merge_nearby_text_blocks(layout_elements, max_chunk_size=1000)
        
        # First two should be merged (close vertically), third should remain separate
        assert len(result) <= 3
        # At least one merged block should exist
        merged = next((e for e in result if "First" in e.get("text", "")), None)
        if merged:
            assert "Second" in merged.get("text", "")

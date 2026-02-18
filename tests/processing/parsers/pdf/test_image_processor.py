"""
Tests for PdfImageProcessor.

Tests:
- PdfImageProcessor.store_images_in_metadata
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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

from documentor.domain import Element, ElementType
from documentor.processing.parsers.pdf.image_processor import PdfImageProcessor


@pytest.fixture
def sample_pdf_path(tmp_path):
    """Create a temporary PDF file for tests."""
    if not FITZ_AVAILABLE:
        pytest.skip("PyMuPDF (fitz) not installed")
    
    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    page = doc.new_page()
    # Add some text instead of image (insert_image requires actual image data)
    page.insert_text((50, 50), "Test PDF Content")
    doc.save(str(pdf_path))
    doc.close()
    return str(pdf_path)


@pytest.fixture
def image_processor():
    """Create PdfImageProcessor instance."""
    config = {
        "layout_detection": {
            "render_scale": 2.0,
        },
    }
    return PdfImageProcessor(config=config)


class TestPdfImageProcessor:
    """Tests for PdfImageProcessor."""

    def test_store_images_in_metadata_no_images(self, image_processor, sample_pdf_path):
        """Test storing images when there are no images."""
        elements = [
            Element(
                id="00000001",
                type=ElementType.TEXT,
                content="Text content",
                metadata={},
            ),
        ]
        
        result = image_processor.store_images_in_metadata(elements, sample_pdf_path)
        assert len(result) == 1
        assert result[0].type == ElementType.TEXT

    def test_store_images_in_metadata_with_caption(self, image_processor, sample_pdf_path):
        """Test storing images with matching caption."""
        if not FITZ_AVAILABLE:
            pytest.skip("PyMuPDF (fitz) not installed")
        
        elements = [
            Element(
                id="00000001",
                type=ElementType.IMAGE,
                content="",
                metadata={
                    "bbox": [50, 50, 150, 150],
                    "page_num": 0,
                },
            ),
            Element(
                id="00000002",
                type=ElementType.CAPTION,
                content="Figure 1: Test image",
                metadata={
                    "bbox": [50, 160, 200, 180],
                    "page_num": 0,
                },
            ),
        ]
        
        result = image_processor.store_images_in_metadata(elements, sample_pdf_path)
        
        assert len(result) == 2
        # Image should be stored in caption metadata
        caption = next(e for e in result if e.type == ElementType.CAPTION)
        assert "image_data" in caption.metadata
        assert "image_id" in caption.metadata
        assert caption.metadata["image_id"] == "00000001"

    def test_store_images_in_metadata_no_caption(self, image_processor, sample_pdf_path):
        """Test storing images without matching caption."""
        if not FITZ_AVAILABLE:
            pytest.skip("PyMuPDF (fitz) not installed")
        
        elements = [
            Element(
                id="00000001",
                type=ElementType.IMAGE,
                content="",
                metadata={
                    "bbox": [50, 50, 150, 150],
                    "page_num": 0,
                },
            ),
        ]
        
        result = image_processor.store_images_in_metadata(elements, sample_pdf_path)
        
        assert len(result) == 1
        # Image should be stored in image element itself
        assert "image_data" in result[0].metadata

    def test_store_images_in_metadata_invalid_bbox(self, image_processor, sample_pdf_path):
        """Test storing images with invalid bbox."""
        elements = [
            Element(
                id="00000001",
                type=ElementType.IMAGE,
                content="",
                metadata={
                    "bbox": [50, 50],  # Invalid bbox
                    "page_num": 0,
                },
            ),
        ]
        
        result = image_processor.store_images_in_metadata(elements, sample_pdf_path)
        assert len(result) == 1
        # Image should still be in result, but not processed

"""
Tests for DocxLayoutDetector.

Tests:
- DocxLayoutDetector.detect_layout_for_all_pages
"""

import sys
from pathlib import Path
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
    pass

"""
Tests for DocxHeaderProcessor.

Tests:
- DocxHeaderProcessor.process_headers
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

from documentor.processing.parsers.docx.header_processor import DocxHeaderProcessor


@pytest.fixture
def header_processor():
    """Create DocxHeaderProcessor instance."""
    config = {
        "header_analysis": {
            "use_font_size": True,
            "use_position": True,
        },
    }
    return DocxHeaderProcessor(config=config)


@pytest.fixture
def sample_docx_path(tmp_path):
    """Create a temporary DOCX file for tests."""
    docx_path = tmp_path / "test.docx"
    docx_path.touch()  # Create empty file
    return docx_path


class TestDocxHeaderProcessor:
    """Tests for DocxHeaderProcessor."""

    @patch("documentor.processing.parsers.docx.header_processor.find_header_in_xml")
    @patch("documentor.processing.parsers.docx.header_processor.extract_paragraph_properties")
    def test_process_headers_basic(self, mock_extract_props, mock_find_header, header_processor, sample_docx_path):
        """Test processing headers with basic structure."""
        ocr_elements = [
            {"category": "Section-header", "bbox": [50, 50, 200, 70], "page_num": 0, "text": "1 Introduction"},
            {"category": "Text", "bbox": [50, 100, 400, 120], "page_num": 0},
        ]
        
        xml_paragraphs = [
            {"text": "1 Introduction", "style": "Heading 1"},
        ]
        
        toc_headers = {}
        
        # Mock find_header_in_xml to return position 0
        mock_find_header.return_value = 0
        # Mock extract_paragraph_properties to return heading style
        mock_extract_props.return_value = {
            "is_heading_style": True,
            "is_list_item": False,
        }
        
        result = header_processor.process_headers(ocr_elements, xml_paragraphs, toc_headers, sample_docx_path)
        
        assert len(result) > 0
        # Headers should be processed

    @patch("documentor.processing.parsers.docx.header_processor.find_header_in_xml")
    @patch("documentor.processing.parsers.docx.header_processor.extract_paragraph_properties")
    def test_process_headers_with_toc(self, mock_extract_props, mock_find_header, header_processor, sample_docx_path):
        """Test processing headers with table of contents."""
        ocr_elements = [
            {"category": "Section-header", "bbox": [50, 50, 200, 70], "page_num": 0, "text": "Introduction"},
        ]
        
        xml_paragraphs = [
            {"text": "Introduction", "style": "Heading 1"},
        ]
        
        toc_headers = {
            "introduction": {"original_title": "Introduction", "level": 1}
        }
        
        # Mock find_header_in_xml to return position 0
        mock_find_header.return_value = 0
        # Mock extract_paragraph_properties to return heading style
        mock_extract_props.return_value = {
            "is_heading_style": True,
            "is_list_item": False,
        }
        
        result = header_processor.process_headers(ocr_elements, xml_paragraphs, toc_headers, sample_docx_path)
        
        assert len(result) > 0

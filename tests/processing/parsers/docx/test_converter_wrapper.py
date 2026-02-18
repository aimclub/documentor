"""
Tests for DocxConverter.

Tests:
- DocxConverter.convert_to_pdf
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add project root to path
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from documentor.processing.parsers.docx.converter_wrapper import DocxConverter


@pytest.fixture
def sample_docx_path(tmp_path):
    """Create a temporary DOCX file for tests."""
    docx_path = tmp_path / "test.docx"
    docx_path.touch()  # Create empty file
    return docx_path


class TestDocxConverter:
    """Tests for DocxConverter."""

    @patch("documentor.processing.parsers.docx.converter_wrapper.convert_docx_to_pdf")
    def test_convert_to_pdf(self, mock_convert, sample_docx_path, tmp_path):
        """Test converting DOCX to PDF."""
        pdf_path = tmp_path / "test.pdf"
        
        DocxConverter.convert_to_pdf(sample_docx_path, pdf_path)
        
        mock_convert.assert_called_once_with(sample_docx_path, pdf_path)

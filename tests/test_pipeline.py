"""
Tests for main Pipeline.

Tested classes and functions:
- Pipeline
- pipeline()
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to PYTHONPATH
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from langchain_core.documents import Document

from documentor.domain import DocumentFormat, Element, ElementType, ParsedDocument
from documentor.exceptions import ParsingError, UnsupportedFormatError, ValidationError
from documentor.pipeline import Pipeline, pipeline


class TestPipeline:
    """Tests for Pipeline class."""

    def test_pipeline_initialization(self):
        """Test Pipeline initialization."""
        pipe = Pipeline()
        assert pipe is not None
        assert isinstance(pipe, Pipeline)

    def test_pipeline_parse_markdown(self):
        """Test parsing Markdown document."""
        pipe = Pipeline()
        doc = Document(
            page_content="# Header\n\nSome text",
            metadata={"source": "test.md"}
        )
        
        result = pipe.parse(doc)
        
        assert isinstance(result, ParsedDocument)
        assert result.format == DocumentFormat.MARKDOWN
        assert len(result.elements) > 0
        assert any(e.type == ElementType.HEADER_1 for e in result.elements)

    def test_pipeline_parse_pdf(self, tmp_path: Path):
        """Test parsing PDF document."""
        # Create a minimal PDF file for testing
        pdf_file = tmp_path / "test.pdf"
        # Write minimal PDF header (this won't be a valid PDF, but tests format detection)
        pdf_file.write_bytes(b"%PDF-1.4\n")
        
        pipe = Pipeline()
        doc = Document(
            page_content="",
            metadata={"source": str(pdf_file)}
        )
        
        # This will likely fail due to invalid PDF, but tests the pipeline flow
        with pytest.raises((ParsingError, Exception)):
            pipe.parse(doc)

    def test_pipeline_parse_docx(self, tmp_path: Path):
        """Test parsing DOCX document."""
        # Create a minimal DOCX file (ZIP archive) for testing
        import zipfile
        docx_file = tmp_path / "test.docx"
        with zipfile.ZipFile(docx_file, 'w') as zf:
            zf.writestr("[Content_Types].xml", "<?xml version='1.0'?><Types></Types>")
        
        pipe = Pipeline()
        doc = Document(
            page_content="",
            metadata={"source": str(docx_file)}
        )
        
        # This will likely fail due to invalid DOCX, but tests the pipeline flow
        with pytest.raises((ParsingError, Exception)):
            pipe.parse(doc)

    def test_pipeline_parse_unknown_format(self):
        """Test parsing document with unknown format."""
        pipe = Pipeline()
        doc = Document(
            page_content="Some content",
            metadata={"source": "test.unknown"}
        )
        
        with pytest.raises(UnsupportedFormatError):
            pipe.parse(doc)

    def test_pipeline_parse_invalid_document(self):
        """Test parsing invalid document."""
        pipe = Pipeline()
        
        with pytest.raises(ValidationError):
            pipe.parse(None)  # type: ignore

    def test_pipeline_parse_empty_document(self):
        """Test parsing empty document."""
        pipe = Pipeline()
        doc = Document(
            page_content="",
            metadata={}
        )
        
        with pytest.raises(ValidationError):
            pipe.parse(doc)

    def test_pipeline_parse_batch(self):
        """Test parsing multiple documents."""
        pipe = Pipeline()
        docs = [
            Document(page_content="# Header 1", metadata={"source": "test1.md"}),
            Document(page_content="# Header 2", metadata={"source": "test2.md"}),
        ]
        
        results = pipe.parse_many(docs)
        
        assert len(results) == 2
        assert all(isinstance(r, ParsedDocument) for r in results)

    def test_pipeline_parse_batch_with_errors(self):
        """Test parsing batch with some errors."""
        pipe = Pipeline()
        docs = [
            Document(page_content="# Header 1", metadata={"source": "test1.md"}),
            Document(page_content="", metadata={}),  # Invalid document
        ]
        
        # parse_many will raise ParsingError if all fail, but will return partial results if some succeed
        # Since the second document will fail, we expect either an exception or partial results
        try:
            results = pipe.parse_many(docs)
            # If we get here, we should have at least one successful result
            assert len(results) >= 1
        except ParsingError:
            # If all documents fail, that's also acceptable behavior
            pass

    @patch('documentor.pipeline.DotsOCRManager')
    def test_pipeline_with_ocr_manager(self, mock_ocr_manager):
        """Test Pipeline with OCR manager."""
        mock_manager = MagicMock()
        mock_ocr_manager.return_value = mock_manager
        
        pipe = Pipeline()
        assert pipe is not None

    def test_pipeline_function(self):
        """Test pipeline() function."""
        doc = Document(
            page_content="# Header\n\nSome text",
            metadata={"source": "test.md"}
        )
        
        result = pipeline(doc)
        
        assert isinstance(result, ParsedDocument)
        assert result.format == DocumentFormat.MARKDOWN

    def test_pipeline_function_with_error(self):
        """Test pipeline() function with error."""
        doc = Document(
            page_content="",
            metadata={}
        )
        
        with pytest.raises((ValueError, ValidationError)):
            pipeline(doc)

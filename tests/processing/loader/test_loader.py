"""
Tests for document loader.

Tested functions:
- detect_document_format()
- get_document_source()
- validate_document()
- normalize_metadata()
"""

import sys
from pathlib import Path

# Add project root to PYTHONPATH for direct run
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import shutil
import tempfile
import pytest
from langchain_core.documents import Document

from documentor.domain import DocumentFormat
from documentor.processing.loader.loader import (
    get_document_source,
    detect_document_format,
    validate_document,
    normalize_metadata,
    _detect_format_by_extension,
    _detect_format_by_mime_type,
    _detect_format_by_magic_bytes,
)


# Fixtures for test files
@pytest.fixture
def test_files_dir() -> Path:
    """Returns path to directory with test files."""
    return Path(__file__).parent.parent.parent / "files_for_tests"


@pytest.fixture
def markdown_file(test_files_dir: Path) -> Path:
    """Path to test Markdown file."""
    return test_files_dir / "md.md"


@pytest.fixture
def pdf_file(test_files_dir: Path) -> Path:
    """Path to test PDF file."""
    return test_files_dir / "pdf.pdf"


@pytest.fixture
def image_pdf_file(test_files_dir: Path) -> Path:
    """Path to test PDF file with images."""
    return test_files_dir / "image.pdf"


@pytest.fixture
def docx_file(test_files_dir: Path) -> Path:
    """Path to test DOCX file."""
    return test_files_dir / "docx.docx"


class TestGetDocumentSource:
    """Tests for get_document_source()."""

    def test_source_from_source_key(self):
        """Test getting source from 'source' key."""
        doc = Document(
            page_content="test",
            metadata={"source": "/path/to/file.md"}
        )
        assert get_document_source(doc) == "/path/to/file.md"

    def test_source_from_file_path_key(self):
        """Test getting source from 'file_path' key."""
        doc = Document(
            page_content="test",
            metadata={"file_path": "/path/to/file.pdf"}
        )
        assert get_document_source(doc) == "/path/to/file.pdf"

    def test_source_from_path_key(self):
        """Test getting source from 'path' key."""
        doc = Document(
            page_content="test",
            metadata={"path": "/path/to/file.docx"}
        )
        assert get_document_source(doc) == "/path/to/file.docx"

    def test_source_from_filename_key(self):
        """Test getting source from 'filename' key."""
        doc = Document(
            page_content="test",
            metadata={"filename": "/path/to/file.md"}
        )
        assert get_document_source(doc) == "/path/to/file.md"

    def test_source_from_file_name_key(self):
        """Test getting source from 'file_name' key."""
        doc = Document(
            page_content="test",
            metadata={"file_name": "/path/to/file.pdf"}
        )
        assert get_document_source(doc) == "/path/to/file.pdf"

    def test_source_priority_order(self):
        """Test key priority (source has highest priority)."""
        doc = Document(
            page_content="test",
            metadata={
                "source": "/correct/path.md",
                "file_path": "/wrong/path.pdf",
                "path": "/also/wrong/path.docx"
            }
        )
        assert get_document_source(doc) == "/correct/path.md"

    def test_source_unknown_when_no_metadata(self):
        """Test returning 'unknown' when no metadata."""
        doc = Document(page_content="test", metadata={})
        assert get_document_source(doc) == "unknown"

    def test_source_unknown_when_metadata_none(self):
        """Test returning 'unknown' when metadata = None."""
        # LangChain Document does not allow metadata=None, use empty dict
        doc = Document(page_content="test", metadata={})
        assert get_document_source(doc) == "unknown"

    def test_source_unknown_when_no_relevant_keys(self):
        """Test returning 'unknown' when no relevant keys."""
        doc = Document(
            page_content="test",
            metadata={"other_key": "/path/to/file.md"}
        )
        assert get_document_source(doc) == "unknown"


class TestDetectFormatByExtension:
    """Tests for _detect_format_by_extension()."""

    def test_detect_markdown_by_md_extension(self):
        """Test detecting Markdown by .md extension."""
        assert _detect_format_by_extension("/path/to/file.md") == DocumentFormat.MARKDOWN

    def test_detect_markdown_by_markdown_extension(self):
        """Test detecting Markdown by .markdown extension."""
        assert _detect_format_by_extension("/path/to/file.markdown") == DocumentFormat.MARKDOWN

    def test_detect_pdf_by_extension(self):
        """Test detecting PDF by extension."""
        assert _detect_format_by_extension("/path/to/file.pdf") == DocumentFormat.PDF

    def test_detect_docx_by_extension(self):
        """Test detecting DOCX by extension."""
        assert _detect_format_by_extension("/path/to/file.docx") == DocumentFormat.DOCX

    def test_case_insensitive_extension(self):
        """Test case-insensitive extension."""
        assert _detect_format_by_extension("/path/to/FILE.PDF") == DocumentFormat.PDF
        assert _detect_format_by_extension("/path/to/FILE.DOCX") == DocumentFormat.DOCX

    def test_unknown_extension_returns_none(self):
        """Test returning None for unknown extension."""
        assert _detect_format_by_extension("/path/to/file.txt") is None
        assert _detect_format_by_extension("/path/to/file") is None

    def test_no_extension_returns_none(self):
        """Test returning None for file without extension."""
        assert _detect_format_by_extension("/path/to/file") is None


class TestDetectFormatByMimeType:
    """Tests for _detect_format_by_mime_type()."""

    def test_detect_pdf_by_mime_type(self):
        """Test detecting PDF by MIME type."""
        metadata = {"mime_type": "application/pdf"}
        assert _detect_format_by_mime_type(metadata) == DocumentFormat.PDF

    def test_detect_docx_by_mime_type(self):
        """Test detecting DOCX by MIME type."""
        metadata = {"mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
        assert _detect_format_by_mime_type(metadata) == DocumentFormat.DOCX

    def test_detect_docx_template_by_mime_type(self):
        """Test detecting DOCX template by MIME type."""
        metadata = {"mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.template"}
        assert _detect_format_by_mime_type(metadata) == DocumentFormat.DOCX

    def test_detect_markdown_by_mime_type(self):
        """Test detecting Markdown by MIME type."""
        metadata = {"mime_type": "text/markdown"}
        assert _detect_format_by_mime_type(metadata) == DocumentFormat.MARKDOWN

    def test_detect_markdown_by_alternative_mime_type(self):
        """Test detecting Markdown by alternative MIME type."""
        metadata = {"mime_type": "text/x-markdown"}
        assert _detect_format_by_mime_type(metadata) == DocumentFormat.MARKDOWN

    def test_unknown_mime_type_returns_none(self):
        """Test returning None for unknown MIME type."""
        metadata = {"mime_type": "text/plain"}
        assert _detect_format_by_mime_type(metadata) is None

    def test_no_mime_type_returns_none(self):
        """Test returning None when no MIME type."""
        metadata = {}
        assert _detect_format_by_mime_type(metadata) is None

    def test_empty_mime_type_returns_none(self):
        """Test returning None for empty MIME type."""
        metadata = {"mime_type": ""}
        assert _detect_format_by_mime_type(metadata) is None


class TestDetectFormatByMagicBytes:
    """Tests for _detect_format_by_magic_bytes()."""

    def test_detect_pdf_by_magic_bytes(self, pdf_file: Path):
        """Test detecting PDF by magic bytes."""
        assert _detect_format_by_magic_bytes(str(pdf_file)) == DocumentFormat.PDF

    def test_detect_pdf_image_by_magic_bytes(self, image_pdf_file: Path):
        """Test detecting PDF with images by magic bytes."""
        assert _detect_format_by_magic_bytes(str(image_pdf_file)) == DocumentFormat.PDF

    def test_detect_docx_by_magic_bytes(self, docx_file: Path):
        """Test detecting DOCX by magic bytes."""
        assert _detect_format_by_magic_bytes(str(docx_file)) == DocumentFormat.DOCX

    def test_nonexistent_file_returns_none(self):
        """Test returning None for non-existent file."""
        assert _detect_format_by_magic_bytes("/nonexistent/file.pdf") is None

    def test_directory_returns_none(self, test_files_dir: Path):
        """Test returning None for directory."""
        assert _detect_format_by_magic_bytes(str(test_files_dir)) is None

    def test_markdown_returns_none(self, markdown_file: Path):
        """Test returning None for Markdown (no magic bytes for text files)."""
        # Markdown is text file, magic bytes not defined
        result = _detect_format_by_magic_bytes(str(markdown_file))
        # May be None or determined differently
        assert result is None or result == DocumentFormat.UNKNOWN


class TestDetectDocumentFormat:
    """Tests for detect_document_format()."""

    def test_detect_markdown_by_extension(self, markdown_file: Path):
        """Test detecting Markdown by extension."""
        doc = Document(
            page_content="# Test",
            metadata={"source": str(markdown_file)}
        )
        assert detect_document_format(doc) == DocumentFormat.MARKDOWN

    def test_detect_pdf_by_extension(self, pdf_file: Path):
        """Test detecting PDF by extension."""
        doc = Document(
            page_content="PDF content",
            metadata={"source": str(pdf_file)}
        )
        assert detect_document_format(doc) == DocumentFormat.PDF

    def test_detect_docx_by_extension(self, docx_file: Path):
        """Test detecting DOCX by extension."""
        doc = Document(
            page_content="DOCX content",
            metadata={"source": str(docx_file)}
        )
        assert detect_document_format(doc) == DocumentFormat.DOCX

    def test_detect_by_mime_type_when_no_extension(self):
        """Test detecting format by MIME type when no extension."""
        doc = Document(
            page_content="PDF content",
            metadata={
                "source": "/path/to/file",
                "mime_type": "application/pdf"
            }
        )
        assert detect_document_format(doc) == DocumentFormat.PDF

    def test_detect_by_magic_bytes_when_no_extension_or_mime(self, pdf_file: Path):
        """Test detecting format by magic bytes when no extension and MIME type."""
        # Use real file path but without extension in metadata
        # Create temp file without extension, copying PDF content
        tmp_dir = tempfile.gettempdir()
        tmp_path = Path(tmp_dir) / f"test_pdf_{tempfile.gettempprefix()}"
        try:
            shutil.copy(pdf_file, tmp_path)
            doc = Document(
                page_content="PDF content",
                metadata={"source": str(tmp_path)}
            )
            # Should detect by magic bytes
            assert detect_document_format(doc) == DocumentFormat.PDF
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_priority_extension_over_mime_type(self, markdown_file: Path):
        """Test extension priority over MIME type."""
        doc = Document(
            page_content="# Test",
            metadata={
                "source": str(markdown_file),
                "mime_type": "application/pdf"  # Wrong MIME type
            }
        )
        # Should detect by extension, ignoring MIME type
        assert detect_document_format(doc) == DocumentFormat.MARKDOWN

    def test_priority_mime_type_over_magic_bytes(self, pdf_file: Path):
        """Test MIME type priority over magic bytes."""
        # Create document with wrong extension but correct MIME type
        doc = Document(
            page_content="PDF content",
            metadata={
                "source": str(pdf_file.with_suffix(".txt")),
                "mime_type": "application/pdf"
            }
        )
        # Should detect by MIME type
        assert detect_document_format(doc) == DocumentFormat.PDF

    def test_unknown_format_when_all_methods_fail(self):
        """Test returning UNKNOWN when all methods fail."""
        doc = Document(
            page_content="Unknown content",
            metadata={"source": "/path/to/unknown.xyz"}
        )
        assert detect_document_format(doc) == DocumentFormat.UNKNOWN

    def test_raises_error_when_no_content_and_no_source(self):
        """Test raising error when no content and no source."""
        doc = Document(page_content="", metadata={})
        with pytest.raises(ValueError, match="Document must contain page_content or source"):
            detect_document_format(doc)

    def test_works_with_only_source_no_content(self, markdown_file: Path):
        """Test when only source, no page_content."""
        doc = Document(
            page_content="",
            metadata={"source": str(markdown_file)}
        )
        assert detect_document_format(doc) == DocumentFormat.MARKDOWN

    def test_works_with_only_content_no_source(self):
        """Test when only page_content, no source."""
        doc = Document(
            page_content="# Markdown content",
            metadata={}
        )
        # Should return UNKNOWN as no way to determine format
        assert detect_document_format(doc) == DocumentFormat.UNKNOWN


class TestValidateDocument:
    """Tests for validate_document()."""

    def test_valid_document_with_content(self):
        """Test validating valid document with content."""
        doc = Document(page_content="Test content", metadata={})
        # Should not raise
        validate_document(doc)

    def test_valid_document_with_source(self):
        """Test validating valid document with source."""
        doc = Document(
            page_content="",
            metadata={"source": "/path/to/file.md"}
        )
        validate_document(doc)

    def test_valid_document_with_both(self):
        """Test validating valid document with content and source."""
        doc = Document(
            page_content="Test content",
            metadata={"source": "/path/to/file.md"}
        )
        validate_document(doc)

    def test_raises_error_when_none(self):
        """Test raising error when document is None."""
        with pytest.raises(ValueError, match="Document cannot be None"):
            validate_document(None)

    def test_raises_error_when_not_document(self):
        """Test raising error when not a Document is passed."""
        with pytest.raises(TypeError, match="Expected Document"):
            validate_document("not a document")

    def test_raises_error_when_no_content_and_no_source(self):
        """Test raising error when no content and no source."""
        doc = Document(page_content="", metadata={})
        with pytest.raises(ValueError, match="Document must contain page_content or source"):
            validate_document(doc)

    def test_raises_error_when_content_not_string(self):
        """Test raising error when page_content is not string."""
        # LangChain Document does not allow non-string for page_content
        # Check that Document is not created
        with pytest.raises(Exception):  # Pydantic ValidationError
            Document(page_content=123, metadata={})

    def test_raises_error_when_metadata_not_dict(self):
        """Test raising error when metadata is not dict."""
        # LangChain Document does not allow non-dict for metadata
        # Check that Document is not created
        with pytest.raises(Exception):  # Pydantic ValidationError
            Document(page_content="test", metadata="not a dict")

    def test_valid_with_none_metadata(self):
        """Test validating document with metadata = None."""
        # LangChain Document does not allow metadata=None, use empty dict
        doc = Document(page_content="test", metadata={})
        validate_document(doc)


class TestNormalizeMetadata:
    """Tests for normalize_metadata()."""

    def test_adds_source_when_missing(self, markdown_file: Path):
        """Test adding source when missing."""
        doc = Document(
            page_content="# Test",
            metadata={"file_path": str(markdown_file)}
        )
        normalized = normalize_metadata(doc)
        assert "source" in normalized
        assert normalized["source"] == str(markdown_file)

    def test_adds_format_when_missing(self, markdown_file: Path):
        """Test adding format when missing."""
        doc = Document(
            page_content="# Test",
            metadata={"source": str(markdown_file)}
        )
        normalized = normalize_metadata(doc)
        assert "format" in normalized
        assert normalized["format"] == "markdown"

    def test_preserves_existing_source(self):
        """Test preserving existing source."""
        doc = Document(
            page_content="test",
            metadata={"source": "/custom/path.md"}
        )
        normalized = normalize_metadata(doc)
        assert normalized["source"] == "/custom/path.md"

    def test_preserves_existing_format(self):
        """Test preserving existing format."""
        doc = Document(
            page_content="test",
            metadata={"source": "/path/to/file.md", "format": "custom_format"}
        )
        normalized = normalize_metadata(doc)
        assert normalized["format"] == "custom_format"

    def test_preserves_all_existing_metadata(self):
        """Test preserving all existing metadata."""
        doc = Document(
            page_content="test",
            metadata={
                "source": "/path/to/file.md",
                "author": "Test Author",
                "title": "Test Title"
            }
        )
        normalized = normalize_metadata(doc)
        assert normalized["author"] == "Test Author"
        assert normalized["title"] == "Test Title"
        assert "format" in normalized

    def test_handles_unknown_source(self):
        """Test handling unknown source."""
        doc = Document(
            page_content="test",
            metadata={}
        )
        normalized = normalize_metadata(doc)
        # source should not be added if unknown
        assert "source" not in normalized or normalized.get("source") == "unknown"

    def test_handles_unknown_format_gracefully(self):
        """Test correct handling when format cannot be determined."""
        doc = Document(
            page_content="test",
            metadata={"source": "/path/to/unknown.xyz"}
        )
        normalized = normalize_metadata(doc)
        # format may be "unknown" or absent
        assert "format" not in normalized or normalized["format"] in ("unknown", "xyz")

    def test_creates_new_dict(self):
        """Test creating new dict (not modifying original)."""
        doc = Document(
            page_content="test",
            metadata={"source": "/path/to/file.md"}
        )
        original_metadata = doc.metadata.copy()
        normalized = normalize_metadata(doc)
        # Original metadata should not change
        assert doc.metadata == original_metadata
        # Normalized should be new dict
        assert normalized is not doc.metadata

    def test_handles_none_metadata(self, markdown_file: Path):
        """Test handling metadata = None."""
        # LangChain Document does not allow metadata=None, use empty dict
        doc = Document(
            page_content="# Test",
            metadata={"file_path": str(markdown_file)}
        )
        normalized = normalize_metadata(doc)
        assert isinstance(normalized, dict)
        assert "source" in normalized

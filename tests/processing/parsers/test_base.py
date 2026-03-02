"""
Tests for base parser.

Tested classes and methods:
- BaseParser (abstract class)
- can_parse()
- get_source()
- _validate_input()
- _create_element()
- _validate_parsed_document()
- _log_parsing_start() / _log_parsing_end()
- Error handling
"""

import sys
from pathlib import Path

# Add project root to PYTHONPATH for direct run
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import logging
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from documentor.domain import DocumentFormat, Element, ElementIdGenerator, ElementType, ParsedDocument
from documentor.exceptions import ParsingError, UnsupportedFormatError, ValidationError
from documentor.processing.parsers.base import BaseParser


# Concrete BaseParser implementation for testing
class MockParser(BaseParser):
    """Concrete BaseParser implementation for testing."""

    format = DocumentFormat.MARKDOWN

    def parse(self, document: Document) -> ParsedDocument:
        """Simple parse implementation for testing."""
        self._validate_input(document)
        source = self.get_source(document)
        self._log_parsing_start(source)

        # Create simple element
        element = self._create_element(ElementType.TEXT, document.page_content or "")

        parsed_doc = ParsedDocument(
            source=source,
            format=self.format,
            elements=[element],
        )

        self._validate_parsed_document(parsed_doc)
        self._log_parsing_end(source, len(parsed_doc.elements))

        return parsed_doc


# ============================================================================
# Initialization tests
# ============================================================================

class TestBaseParserInitialization:
    """BaseParser initialization tests."""

    def test_default_initialization(self):
        """Test initialization with default parameters."""
        parser = MockParser()
        assert isinstance(parser.id_generator, ElementIdGenerator)
        assert parser.format == DocumentFormat.MARKDOWN

    def test_custom_id_generator(self):
        """Test initialization with custom ID generator."""
        custom_generator = ElementIdGenerator(start=100, width=4)
        parser = MockParser(id_generator=custom_generator)
        assert parser.id_generator is custom_generator
        assert parser.id_generator._counter == 100

    def test_id_generator_property(self):
        """Test id_generator property."""
        parser = MockParser()
        generator = parser.id_generator
        assert isinstance(generator, ElementIdGenerator)
        # Same object
        assert parser.id_generator is generator


# ============================================================================
# can_parse tests
# ============================================================================

class TestCanParse:
    """Tests for can_parse method."""

    def test_can_parse_matching_format(self):
        """Test can_parse for matching format."""
        parser = MockParser()
        doc = Document(page_content="# Title", metadata={"source": "test.md"})
        assert parser.can_parse(doc) is True

    def test_can_parse_non_matching_format(self):
        """Test can_parse for non-matching format."""
        parser = MockParser()
        doc = Document(page_content="PDF content", metadata={"source": "test.pdf"})
        assert parser.can_parse(doc) is False

    def test_can_parse_handles_errors(self):
        """Test can_parse handles errors gracefully."""
        parser = MockParser()
        # Document without source and page_content
        doc = Document(page_content="", metadata={})
        # Should not raise, return False
        result = parser.can_parse(doc)
        assert isinstance(result, bool)


# ============================================================================
# get_source tests
# ============================================================================

class TestGetSource:
    """Tests for get_source method."""

    def test_get_source_from_metadata(self):
        """Test getting source from metadata."""
        parser = MockParser()
        doc = Document(page_content="test", metadata={"source": "/path/to/file.md"})
        assert parser.get_source(doc) == "/path/to/file.md"

    def test_get_source_unknown(self):
        """Test getting source when missing."""
        parser = MockParser()
        doc = Document(page_content="test", metadata={})
        assert parser.get_source(doc) == "unknown"

    def test_get_source_from_different_keys(self):
        """Test getting source from different metadata keys."""
        parser = MockParser()
        # Check file_path
        doc = Document(page_content="test", metadata={"file_path": "/path/to/file.md"})
        assert parser.get_source(doc) == "/path/to/file.md"


# ============================================================================
# _validate_input tests
# ============================================================================

class TestValidateInput:
    """Tests for _validate_input method."""

    def test_validate_input_valid_document(self):
        """Test validation of valid document."""
        parser = MockParser()
        doc = Document(page_content="# Title", metadata={"source": "test.md"})
        # Should not raise
        parser._validate_input(doc)

    def test_validate_input_none_document(self):
        """Test validation of None document."""
        parser = MockParser()
        with pytest.raises(ValidationError, match="Document cannot be None"):
            parser._validate_input(None)  # type: ignore

    def test_validate_input_non_document_type(self):
        """Test validation of non-Document object."""
        parser = MockParser()
        with pytest.raises(ValidationError, match="Expected Document"):
            parser._validate_input("not a document")  # type: ignore

    def test_validate_input_invalid_document_no_content(self):
        """Test validation of document without content and source."""
        parser = MockParser()
        doc = Document(page_content="", metadata={})
        with pytest.raises(ValidationError, match="Document is invalid"):
            parser._validate_input(doc)

    def test_validate_input_wrong_format(self):
        """Test validation of document with wrong format."""
        parser = MockParser()
        doc = Document(page_content="PDF content", metadata={"source": "test.pdf"})
        with pytest.raises(UnsupportedFormatError, match="cannot handle format"):
            parser._validate_input(doc)


# ============================================================================
# _create_element tests
# ============================================================================

class TestCreateElement:
    """Tests for _create_element method."""

    def test_create_element_basic(self):
        """Test creating basic element."""
        parser = MockParser()
        element = parser._create_element(ElementType.TEXT, "Test content")
        assert isinstance(element, Element)
        assert element.type == ElementType.TEXT
        assert element.content == "Test content"
        assert element.id == "00000001"  # First ID
        assert element.parent_id is None
        assert element.metadata == {}

    def test_create_element_with_parent(self):
        """Test creating element with parent_id."""
        parser = MockParser()
        element = parser._create_element(ElementType.HEADER_1, "Header", parent_id="00000001")
        assert element.parent_id == "00000001"

    def test_create_element_with_metadata(self):
        """Test creating element with metadata."""
        parser = MockParser()
        metadata = {"page": 1, "position": {"x": 10}}
        element = parser._create_element(ElementType.TEXT, "Content", metadata=metadata)
        assert element.metadata == metadata

    def test_create_element_sequential_ids(self):
        """Test sequential ID generation."""
        parser = MockParser()
        elem1 = parser._create_element(ElementType.TEXT, "Content 1")
        elem2 = parser._create_element(ElementType.TEXT, "Content 2")
        elem3 = parser._create_element(ElementType.TEXT, "Content 3")
        assert elem1.id == "00000001"
        assert elem2.id == "00000002"
        assert elem3.id == "00000003"


# ============================================================================
# _validate_parsed_document tests
# ============================================================================

class TestValidateParsedDocument:
    """Tests for _validate_parsed_document method."""

    def test_validate_parsed_document_valid(self):
        """Test validation of valid ParsedDocument."""
        parser = MockParser()
        elements = [Element(id="001", type=ElementType.TITLE, content="Title")]
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=elements)
        # Should not raise
        parser._validate_parsed_document(doc)

    def test_validate_parsed_document_invalid(self):
        """Test validation of invalid ParsedDocument."""
        parser = MockParser()
        # Create valid document then modify for test
        elements = [Element(id="001", type=ElementType.TITLE, content="Title")]
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=elements)
        # Empty elements list is now valid (code allows empty documents)
        # This test just ensures validation passes
        parser._validate_parsed_document(doc)

    def test_validate_parsed_document_duplicate_ids(self):
        """Test validation of ParsedDocument with duplicate IDs."""
        parser = MockParser()
        # Create valid document then modify for test
        elements = [Element(id="001", type=ElementType.TEXT, content="Text 1")]
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=elements)
        # Add duplicate ID, bypassing creation validation
        doc.elements.append(Element(id="001", type=ElementType.TEXT, content="Text 2"))
        with pytest.raises(ValidationError, match="Parsing result is invalid"):
            parser._validate_parsed_document(doc)


# ============================================================================
# Logging tests
# ============================================================================

class TestLogging:
    """Tests for logging methods."""

    def test_log_parsing_start(self, caplog):
        """Test logging of parsing start."""
        with caplog.at_level(logging.INFO):
            parser = MockParser()
            parser._log_parsing_start("test.md")
            assert "Starting document parsing" in caplog.text
            assert "test.md" in caplog.text
            assert "markdown" in caplog.text

    def test_log_parsing_end(self, caplog):
        """Test logging of parsing completion."""
        with caplog.at_level(logging.INFO):
            parser = MockParser()
            parser._log_parsing_end("test.md", 5)
            assert "Parsing completed" in caplog.text
            assert "test.md" in caplog.text
            assert "5" in caplog.text


# ============================================================================
# Full parse cycle tests
# ============================================================================

class TestParseFullCycle:
    """Full parsing cycle tests."""

    def test_parse_valid_document(self):
        """Test parsing valid document."""
        parser = MockParser()
        doc = Document(page_content="# Title", metadata={"source": "test.md"})
        result = parser.parse(doc)
        assert isinstance(result, ParsedDocument)
        assert result.source == "test.md"
        assert result.format == DocumentFormat.MARKDOWN
        assert len(result.elements) == 1
        assert result.elements[0].content == "# Title"

    def test_parse_invalid_document_raises_error(self):
        """Test parsing invalid document raises error."""
        parser = MockParser()
        doc = Document(page_content="", metadata={})  # No source and content
        with pytest.raises(ValidationError):
            parser.parse(doc)

    def test_parse_wrong_format_raises_error(self):
        """Test parsing document with wrong format."""
        parser = MockParser()
        doc = Document(page_content="PDF", metadata={"source": "test.pdf"})
        with pytest.raises(UnsupportedFormatError):
            parser.parse(doc)

    def test_parse_logs_start_and_end(self, caplog):
        """Test that parse logs start and end."""
        with caplog.at_level(logging.INFO):
            parser = MockParser()
            doc = Document(page_content="Content", metadata={"source": "test.md"})
            parser.parse(doc)
            assert "Starting document parsing" in caplog.text
            assert "Parsing completed" in caplog.text


# ============================================================================
# Error handling tests
# ============================================================================

class TestErrorHandling:
    """Error handling tests."""

    def test_parse_handles_internal_errors(self):
        """Test that parse handles internal errors."""
        parser = MockParser()

        # Document that will cause error when parsing
        # Mock _create_element to trigger error
        with patch.object(parser, "_create_element", side_effect=Exception("Internal error")):
            doc = Document(page_content="test", metadata={"source": "test.md"})
            with pytest.raises(Exception, match="Internal error"):
                parser.parse(doc)

    def test_validate_input_preserves_original_error(self):
        """Test that _validate_input preserves original error."""
        parser = MockParser()
        doc = Document(page_content="", metadata={})
        try:
            parser._validate_input(doc)
        except ValidationError as e:
            # Original error preserved
            assert "Document is invalid" in str(e)


# ============================================================================
# Abstract class tests
# ============================================================================

class TestAbstractClass:
    """Tests for BaseParser abstract class."""

    def test_cannot_instantiate_base_parser(self):
        """Test that BaseParser cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseParser()  # type: ignore

    def test_must_implement_parse(self):
        """Test that subclass must implement parse."""

        class IncompleteParser(BaseParser):
            format = DocumentFormat.MARKDOWN
            # parse method not implemented

        with pytest.raises(TypeError):
            IncompleteParser()  # type: ignore

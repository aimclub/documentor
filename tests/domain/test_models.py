"""
Tests for domain models.

Classes under test:
- DocumentFormat (Enum)
- ElementType (Enum)
- Element (dataclass)
- ParsedDocument (dataclass)
- ElementIdGenerator
"""

import json
import sys
from pathlib import Path

# Add project root to PYTHONPATH for direct run
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest

from documentor.domain.models import (
    DocumentFormat,
    Element,
    ElementIdGenerator,
    ElementType,
    ParsedDocument,
)


# ============================================================================
# Tests for DocumentFormat
# ============================================================================

class TestDocumentFormat:
    """Tests for DocumentFormat enum."""

    def test_all_formats_exist(self):
        """Test that all expected formats exist."""
        expected_formats = {"markdown", "pdf", "docx", "unknown"}
        actual_formats = {fmt.value for fmt in DocumentFormat}
        assert actual_formats == expected_formats

    def test_format_values(self):
        """Test format values."""
        assert DocumentFormat.MARKDOWN.value == "markdown"
        assert DocumentFormat.PDF.value == "pdf"
        assert DocumentFormat.DOCX.value == "docx"
        assert DocumentFormat.UNKNOWN.value == "unknown"

    def test_format_from_value(self):
        """Test creating format from value."""
        assert DocumentFormat("markdown") == DocumentFormat.MARKDOWN
        assert DocumentFormat("pdf") == DocumentFormat.PDF
        assert DocumentFormat("docx") == DocumentFormat.DOCX
        assert DocumentFormat("unknown") == DocumentFormat.UNKNOWN

    def test_invalid_format_raises_error(self):
        """Test error on invalid format."""
        with pytest.raises(ValueError):
            DocumentFormat("invalid_format")


# ============================================================================
# Tests for ElementType
# ============================================================================

class TestElementType:
    """Tests for ElementType enum."""

    def test_all_types_exist(self):
        """Test that all expected element types exist."""
        expected_types = {
            "title",
            "header_1",
            "header_2",
            "header_3",
            "header_4",
            "header_5",
            "header_6",
            "text",
            "image",
            "table",
            "formula",
            "list_item",
            "caption",
            "footnote",
            "page_header",
            "page_footer",
            "code_block",
            "link",
        }
        actual_types = {elem_type.value for elem_type in ElementType}
        assert actual_types == expected_types

    def test_header_levels(self):
        """Test headers by level."""
        assert ElementType.HEADER_1.value == "header_1"
        assert ElementType.HEADER_2.value == "header_2"
        assert ElementType.HEADER_3.value == "header_3"
        assert ElementType.HEADER_4.value == "header_4"
        assert ElementType.HEADER_5.value == "header_5"
        assert ElementType.HEADER_6.value == "header_6"

    def test_type_from_value(self):
        """Test creating type from value."""
        assert ElementType("title") == ElementType.TITLE
        assert ElementType("header_1") == ElementType.HEADER_1
        assert ElementType("text") == ElementType.TEXT

    def test_invalid_type_raises_error(self):
        """Test error on invalid type."""
        with pytest.raises(ValueError):
            ElementType("invalid_type")


# ============================================================================
# Tests for Element
# ============================================================================

class TestElement:
    """Tests for Element dataclass."""

    def test_create_valid_element(self):
        """Test creating valid element."""
        element = Element(
            id="001",
            type=ElementType.TITLE,
            content="Test Title",
        )
        assert element.id == "001"
        assert element.type == ElementType.TITLE
        assert element.content == "Test Title"
        assert element.parent_id is None
        assert element.metadata == {}

    def test_create_element_with_parent(self):
        """Test creating element with parent_id."""
        element = Element(
            id="002",
            type=ElementType.HEADER_1,
            content="Header 1",
            parent_id="001",
        )
        assert element.parent_id == "001"

    def test_create_element_with_metadata(self):
        """Test creating element with metadata."""
        metadata = {"page": 1, "position": {"x": 10, "y": 20}}
        element = Element(
            id="003",
            type=ElementType.TEXT,
            content="Some text",
            metadata=metadata,
        )
        assert element.metadata == metadata

    def test_validate_empty_id_raises_error(self):
        """Test validation: empty id raises error."""
        with pytest.raises(ValueError, match="id must be a non-empty string"):
            Element(id="", type=ElementType.TEXT, content="test")

    def test_validate_whitespace_id_raises_error(self):
        """Test validation: whitespace-only id raises error."""
        with pytest.raises(ValueError, match="id must be a non-empty string"):
            Element(id="   ", type=ElementType.TEXT, content="test")

    def test_validate_invalid_type_raises_error(self):
        """Test validation: invalid type raises error."""
        with pytest.raises(ValueError, match="type must be ElementType"):
            Element(id="001", type="invalid", content="test")  # type: ignore

    def test_validate_none_content_raises_error(self):
        """Test validation: None content raises error."""
        with pytest.raises(ValueError, match="content cannot be None"):
            Element(id="001", type=ElementType.TEXT, content=None)  # type: ignore

    def test_validate_non_string_content_raises_error(self):
        """Test validation: non-string content raises error."""
        with pytest.raises(ValueError, match="content must be a string"):
            Element(id="001", type=ElementType.TEXT, content=123)  # type: ignore

    def test_validate_invalid_metadata_raises_error(self):
        """Test validation: invalid metadata raises error."""
        with pytest.raises(ValueError, match="metadata must be a dict"):
            Element(id="001", type=ElementType.TEXT, content="test", metadata="invalid")  # type: ignore

    def test_validate_empty_parent_id_raises_error(self):
        """Test validation: empty parent_id raises error."""
        with pytest.raises(ValueError, match="parent_id must be a non-empty string or None"):
            Element(id="001", type=ElementType.TEXT, content="test", parent_id="")

    def test_validate_whitespace_parent_id_raises_error(self):
        """Test validation: whitespace-only parent_id raises error."""
        with pytest.raises(ValueError, match="parent_id must be a non-empty string or None"):
            Element(id="001", type=ElementType.TEXT, content="test", parent_id="   ")

    def test_repr(self):
        """Test __repr__ method."""
        element = Element(
            id="001",
            type=ElementType.TITLE,
            content="Test Title",
        )
        repr_str = repr(element)
        assert "Element" in repr_str
        assert "id='001'" in repr_str
        assert "type='title'" in repr_str
        assert "Test Title" in repr_str

    def test_repr_with_long_content(self):
        """Test __repr__ with long content (truncated)."""
        long_content = "A" * 100
        element = Element(id="001", type=ElementType.TEXT, content=long_content)
        repr_str = repr(element)
        assert len(repr_str) < len(long_content) + 50  # Should be truncated
        assert "..." in repr_str

    def test_str(self):
        """Test __str__ method."""
        element = Element(
            id="001",
            type=ElementType.TITLE,
            content="Test Title",
        )
        str_repr = str(element)
        assert "title[001]" in str_repr
        assert "Test Title" in str_repr

    def test_str_with_parent(self):
        """Test __str__ с parent_id."""
        element = Element(
            id="002",
            type=ElementType.HEADER_1,
            content="Header",
            parent_id="001",
        )
        str_repr = str(element)
        assert "parent: 001" in str_repr

    def test_to_dict_minimal(self):
        """Test to_dict for minimal element."""
        element = Element(id="001", type=ElementType.TEXT, content="test")
        result = element.to_dict()
        assert result == {
            "id": "001",
            "type": "text",
            "content": "test",
        }

    def test_to_dict_with_parent(self):
        """Test to_dict с parent_id."""
        element = Element(
            id="002",
            type=ElementType.HEADER_1,
            content="Header",
            parent_id="001",
        )
        result = element.to_dict()
        assert result["parent_id"] == "001"

    def test_to_dict_with_metadata(self):
        """Test to_dict with metadata."""
        metadata = {"page": 1, "key": "value"}
        element = Element(
            id="003",
            type=ElementType.TEXT,
            content="test",
            metadata=metadata,
        )
        result = element.to_dict()
        assert result["metadata"] == metadata

    def test_from_dict_minimal(self):
        """Test from_dict for minimal element."""
        data = {
            "id": "001",
            "type": "text",
            "content": "test",
        }
        element = Element.from_dict(data)
        assert element.id == "001"
        assert element.type == ElementType.TEXT
        assert element.content == "test"
        assert element.parent_id is None
        assert element.metadata == {}

    def test_from_dict_with_parent(self):
        """Test from_dict with parent_id."""
        data = {
            "id": "002",
            "type": "header_1",
            "content": "Header",
            "parent_id": "001",
        }
        element = Element.from_dict(data)
        assert element.parent_id == "001"

    def test_from_dict_with_metadata(self):
        """Test from_dict with metadata."""
        data = {
            "id": "003",
            "type": "text",
            "content": "test",
            "metadata": {"page": 1},
        }
        element = Element.from_dict(data)
        assert element.metadata == {"page": 1}

    def test_from_dict_missing_required_field(self):
        """Test from_dict with missing required field."""
        data = {"id": "001", "type": "text"}  # No content
        with pytest.raises(ValueError, match="Missing required fields"):
            Element.from_dict(data)

    def test_from_dict_invalid_type(self):
        """Test from_dict with invalid type."""
        data = {
            "id": "001",
            "type": "invalid_type",
            "content": "test",
        }
        with pytest.raises(ValueError, match="Invalid ElementType"):
            Element.from_dict(data)

    def test_from_dict_not_dict(self):
        """Test from_dict with non-dict."""
        with pytest.raises(ValueError, match="Expected dict"):
            Element.from_dict("not a dict")  # type: ignore

    def test_to_json(self):
        """Test to_json method."""
        element = Element(id="001", type=ElementType.TEXT, content="test")
        json_str = element.to_json()
        assert isinstance(json_str, str)
        data = json.loads(json_str)
        assert data["id"] == "001"
        assert data["type"] == "text"
        assert data["content"] == "test"

    def test_from_json(self):
        """Test from_json method."""
        json_str = '{"id": "001", "type": "text", "content": "test"}'
        element = Element.from_json(json_str)
        assert element.id == "001"
        assert element.type == ElementType.TEXT
        assert element.content == "test"

    def test_from_json_invalid_json(self):
        """Test from_json with invalid JSON."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            Element.from_json("not a json")

    def test_from_json_not_string(self):
        """Test from_json with non-string."""
        with pytest.raises(ValueError, match="Expected str"):
            Element.from_json({"id": "001"})  # type: ignore

    def test_round_trip_dict(self):
        """Test round-trip: to_dict -> from_dict."""
        original = Element(
            id="001",
            type=ElementType.HEADER_1,
            content="Header",
            parent_id=None,
            metadata={"page": 1},
        )
        restored = Element.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.type == original.type
        assert restored.content == original.content
        assert restored.parent_id == original.parent_id
        assert restored.metadata == original.metadata

    def test_round_trip_json(self):
        """Test round-trip: to_json -> from_json."""
        original = Element(
            id="001",
            type=ElementType.TEXT,
            content="Test content",
            parent_id="000",
            metadata={"key": "value"},
        )
        restored = Element.from_json(original.to_json())
        assert restored.id == original.id
        assert restored.type == original.type
        assert restored.content == original.content
        assert restored.parent_id == original.parent_id
        assert restored.metadata == original.metadata


# ============================================================================
# Tests for ParsedDocument
# ============================================================================

class TestParsedDocument:
    """Tests for ParsedDocument dataclass."""

    @pytest.fixture
    def sample_elements(self):
        """Fixture with sample elements."""
        return [
            Element(id="001", type=ElementType.TITLE, content="Title"),
            Element(id="002", type=ElementType.HEADER_1, content="Header 1", parent_id="001"),
            Element(id="003", type=ElementType.TEXT, content="Text", parent_id="002"),
        ]

    def test_create_valid_document(self, sample_elements):
        """Test creating valid document."""
        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=sample_elements,
        )
        assert doc.source == "test.md"
        assert doc.format == DocumentFormat.MARKDOWN
        assert len(doc.elements) == 3
        assert doc.metadata == {}

    def test_create_document_with_metadata(self, sample_elements):
        """Test creating document with metadata."""
        metadata = {"author": "Test", "version": "1.0"}
        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=sample_elements,
            metadata=metadata,
        )
        assert doc.metadata == metadata

    def test_validate_empty_source_raises_error(self, sample_elements):
        """Test validation: empty source raises error."""
        with pytest.raises(ValueError, match="source must be a non-empty string"):
            ParsedDocument(source="", format=DocumentFormat.MARKDOWN, elements=sample_elements)

    def test_validate_invalid_format_raises_error(self, sample_elements):
        """Test validation: invalid format raises error."""
        with pytest.raises(ValueError, match="format must be DocumentFormat"):
            ParsedDocument(source="test.md", format="invalid", elements=sample_elements)  # type: ignore

    def test_validate_empty_elements_allowed(self):
        """Test validation: empty elements list allowed."""
        # Empty documents allowed
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=[])
        assert doc.elements == []
        assert len(doc.elements) == 0

    def test_validate_non_list_elements_raises_error(self):
        """Test validation: elements not a list raises error."""
        with pytest.raises(ValueError, match="elements must be a list"):
            ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements="not a list")  # type: ignore

    def test_validate_non_element_in_list_raises_error(self):
        """Test validation: non-Element item raises error."""
        with pytest.raises(ValueError, match="must be Element instances"):
            ParsedDocument(
                source="test.md",
                format=DocumentFormat.MARKDOWN,
                elements=["not an element"],  # type: ignore
            )

    def test_validate_duplicate_ids_raises_error(self):
        """Test validation: duplicate ids raise error."""
        elements = [
            Element(id="001", type=ElementType.TEXT, content="Text 1"),
            Element(id="001", type=ElementType.TEXT, content="Text 2"),  # Duplicate
        ]
        with pytest.raises(ValueError, match="Duplicate element ids"):
            ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=elements)

    def test_validate_hierarchy_nonexistent_parent(self):
        """Test hierarchy validation: non-existent parent_id."""
        elements = [
            Element(id="001", type=ElementType.TEXT, content="Text", parent_id="999"),  # Non-existent parent
        ]
        with pytest.raises(ValueError, match="references non-existent parent_id"):
            ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=elements)

    def test_validate_hierarchy_self_parent(self):
        """Test hierarchy validation: element cannot be its own parent."""
        elements = [
            Element(id="001", type=ElementType.TEXT, content="Text", parent_id="001"),  # Own parent
        ]
        with pytest.raises(ValueError, match="cannot be its own parent"):
            ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=elements)

    def test_validate_hierarchy_cycle_direct(self):
        """Test hierarchy validation: direct cycle."""
        elements = [
            Element(id="001", type=ElementType.TEXT, content="Text 1", parent_id="002"),
            Element(id="002", type=ElementType.TEXT, content="Text 2", parent_id="001"),  # Cycle
        ]
        with pytest.raises(ValueError, match="Cycle detected"):
            ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=elements)

    def test_validate_hierarchy_cycle_indirect(self):
        """Test hierarchy validation: indirect cycle (A -> B -> C -> A)."""
        elements = [
            Element(id="001", type=ElementType.TEXT, content="Text 1", parent_id="003"),
            Element(id="002", type=ElementType.TEXT, content="Text 2", parent_id="001"),
            Element(id="003", type=ElementType.TEXT, content="Text 3", parent_id="002"),  # Cycle
        ]
        with pytest.raises(ValueError, match="Cycle detected"):
            ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=elements)

    def test_validate_hierarchy_valid_tree(self):
        """Test hierarchy validation: valid tree."""
        elements = [
            Element(id="001", type=ElementType.TITLE, content="Title"),
            Element(id="002", type=ElementType.HEADER_1, content="H1", parent_id="001"),
            Element(id="003", type=ElementType.HEADER_2, content="H2", parent_id="002"),
            Element(id="004", type=ElementType.TEXT, content="Text", parent_id="003"),
        ]
        # Should not raise
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=elements)
        assert len(doc.elements) == 4

    def test_validate_hierarchy_header_reset_allowed(self):
        """Test hierarchy validation: header hierarchy reset allowed."""
        # HEADER_1 after HEADER_2 without parent - allowed
        elements = [
            Element(id="001", type=ElementType.HEADER_1, content="H1"),
            Element(id="002", type=ElementType.HEADER_2, content="H2", parent_id="001"),
            Element(id="003", type=ElementType.HEADER_1, content="H1 again"),  # Hierarchy reset
        ]
        # Should not raise
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=elements)
        assert len(doc.elements) == 3

    def test_repr(self, sample_elements):
        """Test __repr__ method."""
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=sample_elements)
        repr_str = repr(doc)
        assert "ParsedDocument" in repr_str
        assert "source='test.md'" in repr_str
        assert "format='markdown'" in repr_str
        assert "elements=3" in repr_str

    def test_str(self, sample_elements):
        """Test __str__ method."""
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=sample_elements)
        str_repr = str(doc)
        assert "ParsedDocument" in str_repr
        assert "markdown" in str_repr
        assert "test.md" in str_repr
        assert "3 elements" in str_repr

    def test_str_with_path(self, sample_elements):
        """Test __str__ with file path."""
        doc = ParsedDocument(source="/path/to/test.md", format=DocumentFormat.MARKDOWN, elements=sample_elements)
        str_repr = str(doc)
        assert "test.md" in str_repr

    def test_to_dicts(self, sample_elements):
        """Test to_dicts method."""
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=sample_elements)
        dicts = doc.to_dicts()
        assert len(dicts) == 3
        assert all(isinstance(d, dict) for d in dicts)
        assert dicts[0]["id"] == "001"

    def test_to_dict(self, sample_elements):
        """Test to_dict method."""
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=sample_elements)
        result = doc.to_dict()
        assert result["source"] == "test.md"
        assert result["format"] == "markdown"
        assert len(result["elements"]) == 3
        assert "metadata" not in result  # Empty metadata not included

    def test_to_dict_with_metadata(self, sample_elements):
        """Test to_dict with metadata."""
        metadata = {"author": "Test"}
        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=sample_elements,
            metadata=metadata,
        )
        result = doc.to_dict()
        assert result["metadata"] == metadata

    def test_from_dict(self, sample_elements):
        """Test from_dict method."""
        data = {
            "source": "test.md",
            "format": "markdown",
            "elements": [elem.to_dict() for elem in sample_elements],
        }
        doc = ParsedDocument.from_dict(data)
        assert doc.source == "test.md"
        assert doc.format == DocumentFormat.MARKDOWN
        assert len(doc.elements) == 3

    def test_from_dict_with_metadata(self, sample_elements):
        """Test from_dict with metadata."""
        data = {
            "source": "test.md",
            "format": "markdown",
            "elements": [elem.to_dict() for elem in sample_elements],
            "metadata": {"author": "Test"},
        }
        doc = ParsedDocument.from_dict(data)
        assert doc.metadata == {"author": "Test"}

    def test_from_dict_missing_required_field(self):
        """Test from_dict with missing required field."""
        data = {"source": "test.md", "format": "markdown"}  # No elements
        with pytest.raises(ValueError, match="Missing required fields"):
            ParsedDocument.from_dict(data)

    def test_from_dict_invalid_format(self, sample_elements):
        """Test from_dict with invalid format."""
        data = {
            "source": "test.md",
            "format": "invalid_format",
            "elements": [elem.to_dict() for elem in sample_elements],
        }
        with pytest.raises(ValueError, match="Invalid DocumentFormat"):
            ParsedDocument.from_dict(data)

    def test_from_dict_not_dict(self):
        """Test from_dict with non-dict."""
        with pytest.raises(ValueError, match="Expected dict"):
            ParsedDocument.from_dict("not a dict")  # type: ignore

    def test_to_json(self, sample_elements):
        """Test to_json method."""
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=sample_elements)
        json_str = doc.to_json()
        assert isinstance(json_str, str)
        data = json.loads(json_str)
        assert data["source"] == "test.md"
        assert data["format"] == "markdown"

    def test_from_json(self, sample_elements):
        """Test from_json method."""
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=sample_elements)
        json_str = doc.to_json()
        restored = ParsedDocument.from_json(json_str)
        assert restored.source == doc.source
        assert restored.format == doc.format
        assert len(restored.elements) == len(doc.elements)

    def test_from_json_invalid_json(self):
        """Test from_json with invalid JSON."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            ParsedDocument.from_json("not a json")

    def test_from_json_not_string(self):
        """Test from_json with non-string."""
        with pytest.raises(ValueError, match="Expected str"):
            ParsedDocument.from_json({"source": "test.md"})  # type: ignore

    def test_round_trip_dict(self, sample_elements):
        """Test round-trip: to_dict -> from_dict."""
        original = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=sample_elements,
            metadata={"author": "Test"},
        )
        restored = ParsedDocument.from_dict(original.to_dict())
        assert restored.source == original.source
        assert restored.format == original.format
        assert len(restored.elements) == len(original.elements)
        assert restored.metadata == original.metadata

    def test_round_trip_json(self, sample_elements):
        """Test round-trip: to_json -> from_json."""
        original = ParsedDocument(
            source="test.md",
            format=DocumentFormat.PDF,
            elements=sample_elements,
            metadata={"version": "1.0"},
        )
        restored = ParsedDocument.from_json(original.to_json())
        assert restored.source == original.source
        assert restored.format == original.format
        assert len(restored.elements) == len(original.elements)
        assert restored.metadata == original.metadata


# ============================================================================
# Tests for ElementIdGenerator
# ============================================================================

class TestElementIdGenerator:
    """Tests for ElementIdGenerator."""

    def test_default_initialization(self):
        """Test initialization with default parameters."""
        generator = ElementIdGenerator()
        assert generator._counter == 1
        assert generator._width == 8

    def test_custom_initialization(self):
        """Test initialization with custom parameters."""
        generator = ElementIdGenerator(start=10, width=4)
        assert generator._counter == 10
        assert generator._width == 4

    def test_next_id_default(self):
        """Test ID generation with default parameters."""
        generator = ElementIdGenerator()
        assert generator.next_id() == "00000001"
        assert generator.next_id() == "00000002"
        assert generator.next_id() == "00000003"

    def test_next_id_custom_width(self):
        """Test ID generation with custom width."""
        generator = ElementIdGenerator(start=1, width=4)
        assert generator.next_id() == "0001"
        assert generator.next_id() == "0002"

    def test_next_id_custom_start(self):
        """Test ID generation with custom start."""
        generator = ElementIdGenerator(start=100, width=6)
        assert generator.next_id() == "000100"
        assert generator.next_id() == "000101"

    def test_reset_to_default(self):
        """Test reset to default value."""
        generator = ElementIdGenerator()
        generator.next_id()
        generator.next_id()
        generator.reset()
        assert generator.next_id() == "00000001"

    def test_reset_to_custom(self):
        """Test reset to custom value."""
        generator = ElementIdGenerator()
        generator.next_id()
        generator.next_id()
        generator.reset(50)
        assert generator.next_id() == "00000050"

    def test_repr(self):
        """Test __repr__ method."""
        generator = ElementIdGenerator(start=5, width=4)
        repr_str = repr(generator)
        assert "ElementIdGenerator" in repr_str
        assert "counter=5" in repr_str
        assert "width=4" in repr_str
        assert "next_id='0005'" in repr_str

    def test_str(self):
        """Test __str__ method."""
        generator = ElementIdGenerator(start=10, width=6)
        str_repr = str(generator)
        assert "ElementIdGenerator" in str_repr
        assert "width=6" in str_repr
        assert "next_id=000010" in str_repr

    def test_sequential_ids(self):
        """Test sequential ID generation."""
        generator = ElementIdGenerator(start=1, width=3)
        ids = [generator.next_id() for _ in range(5)]
        assert ids == ["001", "002", "003", "004", "005"]

    def test_large_numbers(self):
        """Test large number generation."""
        generator = ElementIdGenerator(start=999, width=4)
        assert generator.next_id() == "0999"
        assert generator.next_id() == "1000"
        assert generator.next_id() == "1001"


# ============================================================================
# Tests for Element.dataframe property
# ============================================================================

class TestElementDataframe:
    """Tests for Element.dataframe property."""

    def test_dataframe_for_table_element(self):
        """Test getting DataFrame for table element."""
        import pandas as pd

        df = pd.DataFrame({"Col1": ["A1", "A2"], "Col2": ["B1", "B2"]})
        element = Element(
            id="001",
            type=ElementType.TABLE,
            content="| Col1 | Col2 |\n|------|------|\n| A1   | B1   |",
            metadata={"dataframe": df},
        )

        result_df = element.dataframe
        assert result_df is not None
        assert isinstance(result_df, pd.DataFrame)
        assert len(result_df) == 2
        assert list(result_df.columns) == ["Col1", "Col2"]

    def test_dataframe_for_non_table_element(self):
        """Test getting DataFrame for non-table element."""
        element = Element(
            id="001",
            type=ElementType.TEXT,
            content="Some text",
        )

        assert element.dataframe is None

    def test_dataframe_for_table_without_dataframe(self):
        """Test getting DataFrame for table without DataFrame in metadata."""
        element = Element(
            id="001",
            type=ElementType.TABLE,
            content="| Col1 | Col2 |",
            metadata={},  # No dataframe
        )

        assert element.dataframe is None


# ============================================================================
# Tests for ParsedDocument.get_elements_by_type
# ============================================================================

class TestParsedDocumentGetElementsByType:
    """Tests for ParsedDocument.get_elements_by_type method."""

    @pytest.fixture
    def mixed_elements(self):
        """Fixture with elements of different types."""
        return [
            Element(id="001", type=ElementType.TITLE, content="Title"),
            Element(id="002", type=ElementType.HEADER_1, content="Header 1"),
            Element(id="003", type=ElementType.TEXT, content="Text 1"),
            Element(id="004", type=ElementType.HEADER_2, content="Header 2"),
            Element(id="005", type=ElementType.TEXT, content="Text 2"),
            Element(id="006", type=ElementType.IMAGE, content="Image"),
        ]

    def test_get_elements_by_type_text(self, mixed_elements):
        """Test getting elements of type TEXT."""
        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=mixed_elements,
        )

        text_elements = doc.get_elements_by_type(ElementType.TEXT)
        assert len(text_elements) == 2
        assert all(elem.type == ElementType.TEXT for elem in text_elements)
        assert text_elements[0].id == "003"
        assert text_elements[1].id == "005"

    def test_get_elements_by_type_header(self, mixed_elements):
        """Test getting elements of type HEADER_1."""
        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=mixed_elements,
        )

        header_elements = doc.get_elements_by_type(ElementType.HEADER_1)
        assert len(header_elements) == 1
        assert header_elements[0].id == "002"
        assert header_elements[0].content == "Header 1"

    def test_get_elements_by_type_nonexistent(self, mixed_elements):
        """Test getting elements of non-existent type."""
        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=mixed_elements,
        )

        code_blocks = doc.get_elements_by_type(ElementType.CODE_BLOCK)
        assert len(code_blocks) == 0
        assert isinstance(code_blocks, list)


# ============================================================================
# Tests for ParsedDocument.get_tables
# ============================================================================

class TestParsedDocumentGetTables:
    """Tests for ParsedDocument.get_tables method."""

    def test_get_tables_with_tables(self):
        """Test getting tables from document with tables."""
        import pandas as pd

        df1 = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
        df2 = pd.DataFrame({"X": ["a", "b"], "Y": ["c", "d"]})

        elements = [
            Element(id="001", type=ElementType.TITLE, content="Title"),
            Element(
                id="002",
                type=ElementType.TABLE,
                content="| A | B |\n| 1 | 3 |",
                metadata={"dataframe": df1},
            ),
            Element(id="003", type=ElementType.TEXT, content="Text"),
            Element(
                id="004",
                type=ElementType.TABLE,
                content="| X | Y |\n| a | c |",
                metadata={"dataframe": df2},
            ),
        ]

        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=elements,
        )

        tables = doc.get_tables()
        assert len(tables) == 2
        assert tables[0].id == "002"
        assert tables[1].id == "004"
        assert tables[0].dataframe is not None
        assert tables[1].dataframe is not None

    def test_get_tables_without_tables(self):
        """Test getting tables from document without tables."""
        elements = [
            Element(id="001", type=ElementType.TITLE, content="Title"),
            Element(id="002", type=ElementType.TEXT, content="Text"),
        ]

        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=elements,
        )

        tables = doc.get_tables()
        assert len(tables) == 0
        assert isinstance(tables, list)

    def test_get_tables_dataframe_access(self):
        """Test DataFrame access via get_tables()."""
        import pandas as pd

        df = pd.DataFrame({"Name": ["John", "Jane"], "Age": [25, 30]})
        elements = [
            Element(
                id="001",
                type=ElementType.TABLE,
                content="| Name | Age |",
                metadata={"dataframe": df},
            ),
        ]

        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=elements,
        )

        table = doc.get_tables()[0]
        result_df = table.dataframe

        assert result_df is not None
        assert len(result_df) == 2
        assert list(result_df.columns) == ["Name", "Age"]
        assert result_df.iloc[0]["Name"] == "John"
        assert result_df.iloc[1]["Age"] == 30


# ============================================================================
# Tests for ParsedDocument.get_headers
# ============================================================================

class TestParsedDocumentGetHeaders:
    """Tests for ParsedDocument.get_headers method."""

    @pytest.fixture
    def header_elements(self):
        """Fixture with header elements of different levels."""
        return [
            Element(id="001", type=ElementType.TITLE, content="Title"),
            Element(id="002", type=ElementType.HEADER_1, content="H1-1"),
            Element(id="003", type=ElementType.HEADER_2, content="H2-1"),
            Element(id="004", type=ElementType.HEADER_3, content="H3-1"),
            Element(id="005", type=ElementType.HEADER_1, content="H1-2"),
            Element(id="006", type=ElementType.HEADER_2, content="H2-2"),
            Element(id="007", type=ElementType.TEXT, content="Text"),
        ]

    def test_get_headers_all(self, header_elements):
        """Test getting all headers."""
        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=header_elements,
        )

        headers = doc.get_headers()
        assert len(headers) == 5
        assert all(
            elem.type
            in [
                ElementType.HEADER_1,
                ElementType.HEADER_2,
                ElementType.HEADER_3,
                ElementType.HEADER_4,
                ElementType.HEADER_5,
                ElementType.HEADER_6,
            ]
            for elem in headers
        )
        assert headers[0].id == "002"  # H1-1
        assert headers[1].id == "003"  # H2-1
        assert headers[2].id == "004"  # H3-1
        assert headers[3].id == "005"  # H1-2
        assert headers[4].id == "006"  # H2-2

    def test_get_headers_level_1(self, header_elements):
        """Test getting level 1 headers."""
        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=header_elements,
        )

        h1_headers = doc.get_headers(level=1)
        assert len(h1_headers) == 2
        assert all(elem.type == ElementType.HEADER_1 for elem in h1_headers)
        assert h1_headers[0].id == "002"
        assert h1_headers[1].id == "005"

    def test_get_headers_level_2(self, header_elements):
        """Test getting level 2 headers."""
        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=header_elements,
        )

        h2_headers = doc.get_headers(level=2)
        assert len(h2_headers) == 2
        assert all(elem.type == ElementType.HEADER_2 for elem in h2_headers)
        assert h2_headers[0].id == "003"
        assert h2_headers[1].id == "006"

    def test_get_headers_level_3(self, header_elements):
        """Test getting level 3 headers."""
        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=header_elements,
        )

        h3_headers = doc.get_headers(level=3)
        assert len(h3_headers) == 1
        assert h3_headers[0].type == ElementType.HEADER_3
        assert h3_headers[0].id == "004"

    def test_get_headers_level_nonexistent(self, header_elements):
        """Test getting headers of non-existent level."""
        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=header_elements,
        )

        h4_headers = doc.get_headers(level=4)
        assert len(h4_headers) == 0
        assert isinstance(h4_headers, list)

    def test_get_headers_invalid_level(self, header_elements):
        """Test getting headers with invalid level."""
        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=header_elements,
        )

        with pytest.raises(ValueError, match="Header level must be between 1 and 6"):
            doc.get_headers(level=0)

        with pytest.raises(ValueError, match="Header level must be between 1 and 6"):
            doc.get_headers(level=7)

    def test_get_headers_without_headers(self):
        """Test getting headers from document without headers."""
        elements = [
            Element(id="001", type=ElementType.TEXT, content="Text 1"),
            Element(id="002", type=ElementType.TEXT, content="Text 2"),
        ]

        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=elements,
        )

        headers = doc.get_headers()
        assert len(headers) == 0
        assert isinstance(headers, list)

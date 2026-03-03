"""
Tests for Markdown parser.

Tested class:
- MarkdownParser
"""

import sys
from pathlib import Path

# Add project root to PYTHONPATH for direct run
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from langchain_core.documents import Document

from documentor.domain import DocumentFormat, Element, ElementIdGenerator, ElementType, ParsedDocument
from documentor.exceptions import ParsingError, UnsupportedFormatError, ValidationError
from documentor.processing.parsers.md.md_parser import MarkdownParser


class TestMarkdownParserInitialization:
    """MarkdownParser initialization tests."""

    def test_default_initialization(self):
        """Test initialization with default parameters."""
        parser = MarkdownParser()
        assert parser.format == DocumentFormat.MARKDOWN
        assert isinstance(parser.id_generator, ElementIdGenerator)

    def test_custom_id_generator(self):
        """Test initialization with custom ID generator."""
        custom_generator = ElementIdGenerator(start=100, width=4)
        parser = MarkdownParser(id_generator=custom_generator)
        assert parser.id_generator is custom_generator
        assert parser.id_generator._counter == 100


class TestMarkdownParserBasicParsing:
    """Basic Markdown parsing tests."""

    def test_parse_simple_text(self):
        """Test parsing simple text."""
        parser = MarkdownParser()
        doc = Document(page_content="Plain text", metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert isinstance(result, ParsedDocument)
        assert result.format == DocumentFormat.MARKDOWN
        assert result.source == "test.md"
        assert len(result.elements) == 1
        assert result.elements[0].type == ElementType.TEXT
        assert result.elements[0].content == "Plain text"

    def test_parse_empty_document(self):
        """Test parsing empty document."""
        parser = MarkdownParser()
        doc = Document(page_content="", metadata={"source": "empty.md"})
        result = parser.parse(doc)

        assert isinstance(result, ParsedDocument)
        assert result.format == DocumentFormat.MARKDOWN
        assert len(result.elements) == 0

    def test_parse_multiple_paragraphs(self):
        """Test parsing multiple paragraphs."""
        parser = MarkdownParser()
        content = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 3
        assert all(elem.type == ElementType.TEXT for elem in result.elements)
        assert result.elements[0].content == "First paragraph."
        assert result.elements[1].content == "Second paragraph."
        assert result.elements[2].content == "Third paragraph."


class TestMarkdownParserHeadings:
    """Heading parsing tests."""

    def test_parse_h1_heading(self):
        """Test parsing H1 heading."""
        parser = MarkdownParser()
        doc = Document(page_content="# Header 1", metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 1
        assert result.elements[0].type == ElementType.HEADER_1
        assert result.elements[0].content == "Header 1"
        assert result.elements[0].parent_id is None

    def test_parse_all_heading_levels(self):
        """Test parsing all heading levels."""
        parser = MarkdownParser()
        content = "# H1\n## H2\n### H3\n#### H4\n##### H5\n###### H6"
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 6
        assert result.elements[0].type == ElementType.HEADER_1
        assert result.elements[1].type == ElementType.HEADER_2
        assert result.elements[2].type == ElementType.HEADER_3
        assert result.elements[3].type == ElementType.HEADER_4
        assert result.elements[4].type == ElementType.HEADER_5
        assert result.elements[5].type == ElementType.HEADER_6

    def test_heading_hierarchy(self):
        """Test heading hierarchy building."""
        parser = MarkdownParser()
        content = """# Header 1
Text under H1
## Header 2
Text under H2
### Header 3
Text under H3
## Header 2 again
Text under H2 again"""
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        # Check structure
        h1 = result.elements[0]
        text1 = result.elements[1]
        h2_1 = result.elements[2]
        text2 = result.elements[3]
        h3 = result.elements[4]
        text3 = result.elements[5]
        h2_2 = result.elements[6]
        text4 = result.elements[7]

        assert h1.type == ElementType.HEADER_1
        assert h1.parent_id is None

        assert text1.type == ElementType.TEXT
        assert text1.parent_id == h1.id

        assert h2_1.type == ElementType.HEADER_2
        assert h2_1.parent_id == h1.id

        assert text2.type == ElementType.TEXT
        assert text2.parent_id == h2_1.id

        assert h3.type == ElementType.HEADER_3
        assert h3.parent_id == h2_1.id

        assert text3.type == ElementType.TEXT
        assert text3.parent_id == h3.id

        assert h2_2.type == ElementType.HEADER_2
        assert h2_2.parent_id == h1.id  # Should be under H1, not H3

        assert text4.type == ElementType.TEXT
        assert text4.parent_id == h2_2.id


class TestMarkdownParserLists:
    """List parsing tests."""

    def test_parse_unordered_list(self):
        """Test parsing unordered list."""
        parser = MarkdownParser()
        content = """- Item 1
- Item 2
- Item 3"""
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 3
        assert all(elem.type == ElementType.LIST_ITEM for elem in result.elements)
        assert result.elements[0].content == "Item 1"
        assert result.elements[1].content == "Item 2"
        assert result.elements[2].content == "Item 3"

    def test_parse_ordered_list(self):
        """Test parsing ordered list."""
        parser = MarkdownParser()
        content = """1. First
2. Second
3. Third"""
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 3
        assert all(elem.type == ElementType.LIST_ITEM for elem in result.elements)
        assert "First" in result.elements[0].content
        assert result.elements[0].metadata.get("list_type") == "ordered"

    def test_parse_nested_list(self):
        """Test parsing nested lists."""
        parser = MarkdownParser()
        content = """- Item 1
  - Nested 1
  - Nested 2
- Item 2
  - Nested 3
    - Deeply nested"""
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        list_items = [e for e in result.elements if e.type == ElementType.LIST_ITEM]
        assert len(list_items) >= 6
        
        # Check nesting levels
        first_level = [e for e in list_items if e.metadata.get("list_level", 0) == 0]
        second_level = [e for e in list_items if e.metadata.get("list_level", 0) == 1]
        third_level = [e for e in list_items if e.metadata.get("list_level", 0) == 2]
        
        assert len(first_level) >= 2  # Item 1, Item 2
        assert len(second_level) >= 3  # Nested items
        assert len(third_level) >= 1  # Deeply nested

    def test_nested_list_hierarchy(self):
        """Test nested list hierarchy."""
        parser = MarkdownParser()
        content = """- Parent 1
  - Child 1
  - Child 2
- Parent 2"""
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        list_items = [e for e in result.elements if e.type == ElementType.LIST_ITEM]
        
        # Find elements by content
        parent1 = next((e for e in list_items if "Parent 1" in e.content), None)
        child1 = next((e for e in list_items if "Child 1" in e.content), None)
        child2 = next((e for e in list_items if "Child 2" in e.content), None)
        
        assert parent1 is not None
        assert child1 is not None
        assert child2 is not None
        
        # Check that children reference parent
        assert child1.parent_id == parent1.id
        assert child2.parent_id == parent1.id
        
        # Check element content
        assert "Child 1" in child1.content
        assert "Child 2" in child2.content
        assert "Parent 1" in parent1.content


class TestMarkdownParserTables:
    """Table parsing tests."""

    def test_parse_simple_table(self):
        """Test parsing simple table."""
        parser = MarkdownParser()
        content = """| Header 1 | Header 2 |
|----------|----------|
| Cell 1   | Cell 2   |
| Cell 3   | Cell 4   |"""
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 1
        assert result.elements[0].type == ElementType.TABLE
        assert "Header 1" in result.elements[0].content
        assert "Cell 1" in result.elements[0].content


class TestMarkdownParserCodeBlocks:
    """Code block parsing tests."""

    def test_parse_code_block(self):
        """Test parsing code block."""
        parser = MarkdownParser()
        content = """```python
def hello():
    print("Hello, World!")
```"""
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 1
        assert result.elements[0].type == ElementType.CODE_BLOCK
        assert "def hello()" in result.elements[0].content
        assert result.elements[0].metadata.get("language") == "python"

    def test_parse_code_block_without_language(self):
        """Test parsing code block without language specified."""
        parser = MarkdownParser()
        content = """```
Simple code
```"""
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 1
        assert result.elements[0].type == ElementType.CODE_BLOCK
        assert "Simple code" in result.elements[0].content
        assert result.elements[0].metadata.get("language") == "" or "language" not in result.elements[0].metadata


class TestMarkdownParserLinks:
    """Link parsing tests."""

    def test_parse_standalone_link(self):
        """Test parsing standalone link."""
        parser = MarkdownParser()
        content = "[Link text](https://example.com)"
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        # Link should be created as separate LINK element
        link_elements = [e for e in result.elements if e.type == ElementType.LINK]
        assert len(link_elements) >= 1
        assert link_elements[0].content == "Link text"
        assert link_elements[0].metadata.get("href") == "https://example.com"

    def test_parse_link_in_text(self):
        """Test parsing link inside text."""
        parser = MarkdownParser()
        content = "Here is [link to Google](https://www.google.com) in text."
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        # Should have LINK and TEXT elements
        link_elements = [e for e in result.elements if e.type == ElementType.LINK]
        text_elements = [e for e in result.elements if e.type == ElementType.TEXT]
        
        assert len(link_elements) >= 1
        assert link_elements[0].metadata.get("href") == "https://www.google.com"
        # Text should be processed separately
        assert len(text_elements) >= 1

    def test_parse_multiple_links(self):
        """Test parsing multiple links."""
        parser = MarkdownParser()
        content = "[Link 1](https://example.com) and [Link 2](https://github.com)"
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        link_elements = [e for e in result.elements if e.type == ElementType.LINK]
        assert len(link_elements) >= 2
        assert link_elements[0].metadata.get("href") == "https://example.com"
        assert link_elements[1].metadata.get("href") == "https://github.com"


class TestMarkdownParserImages:
    """Image parsing tests."""

    def test_parse_standalone_image(self):
        """Test parsing standalone image."""
        parser = MarkdownParser()
        content = "![Alt text](image.jpg)"
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        # Image should be created as separate IMAGE element
        image_elements = [e for e in result.elements if e.type == ElementType.IMAGE]
        assert len(image_elements) >= 1
        assert image_elements[0].metadata.get("alt") == "Alt text"
        assert image_elements[0].metadata.get("src") == "image.jpg"
        assert image_elements[0].content == "Alt text"

    def test_parse_image_in_text(self):
        """Test parsing image inside text."""
        parser = MarkdownParser()
        content = "Here is ![picture](image.png) in text."
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        # Should have IMAGE and TEXT elements
        image_elements = [e for e in result.elements if e.type == ElementType.IMAGE]
        text_elements = [e for e in result.elements if e.type == ElementType.TEXT]
        
        assert len(image_elements) >= 1
        assert image_elements[0].metadata.get("src") == "image.png"
        # Text should be processed separately
        assert len(text_elements) >= 1

    def test_parse_image_without_alt(self):
        """Test parsing image without alt text."""
        parser = MarkdownParser()
        content = "![](image.jpg)"
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        image_elements = [e for e in result.elements if e.type == ElementType.IMAGE]
        assert len(image_elements) >= 1
        assert image_elements[0].metadata.get("src") == "image.jpg"
        assert image_elements[0].content == "image.jpg"  # URL used as content


class TestMarkdownParserQuotes:
    """Blockquote parsing tests."""

    def test_parse_blockquote(self):
        """Test parsing blockquote."""
        parser = MarkdownParser()
        content = "> This is a quote"
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 1
        assert result.elements[0].type == ElementType.TEXT
        assert "This is a quote" in result.elements[0].content
        assert result.elements[0].metadata.get("quote") is True


class TestMarkdownParserComplexDocument:
    """Complex document parsing tests."""

    def test_parse_complex_document(self):
        """Test parsing document with various elements."""
        parser = MarkdownParser()
        content = """# Main header

This is a paragraph.

## Subheader

- List item 1
- List item 2

```python
code = "example"
```

| Table | Column |
|-------|--------|
| Data  | Value  |

> Quote

[Link](https://example.com)
"""
        doc = Document(page_content=content, metadata={"source": "complex.md"})
        result = parser.parse(doc)

        assert isinstance(result, ParsedDocument)
        assert result.format == DocumentFormat.MARKDOWN
        assert len(result.elements) > 0

        # Check presence of various element types
        types = [elem.type for elem in result.elements]
        assert ElementType.HEADER_1 in types
        assert ElementType.HEADER_2 in types
        assert ElementType.TEXT in types
        assert ElementType.LIST_ITEM in types
        assert ElementType.CODE_BLOCK in types
        assert ElementType.TABLE in types

    def test_parse_real_file(self):
        """Test parsing a real file from tests/data."""
        parser = MarkdownParser()
        test_file = Path(__file__).parent.parent.parent / "data" / "md.md"

        if test_file.exists():
            content = test_file.read_text(encoding="utf-8")
            doc = Document(page_content=content, metadata={"source": str(test_file)})
            result = parser.parse(doc)

            assert isinstance(result, ParsedDocument)
            assert result.format == DocumentFormat.MARKDOWN
            assert len(result.elements) > 0


class TestMarkdownParserValidation:
    """Input validation tests."""

    def test_validate_input_none_document(self):
        """Test validation of None document."""
        parser = MarkdownParser()
        with pytest.raises(ValidationError):
            parser.parse(None)  # type: ignore

    def test_validate_input_wrong_format(self):
        """Test validation of wrong format document."""
        parser = MarkdownParser()
        doc = Document(page_content="PDF content", metadata={"source": "test.pdf"})
        with pytest.raises(UnsupportedFormatError):
            parser.parse(doc)

    def test_validate_input_empty_content(self):
        """Test validation of document with empty content."""
        parser = MarkdownParser()
        doc = Document(page_content="", metadata={"source": "test.md"})
        result = parser.parse(doc)
        # Empty document should be valid but with no elements
        assert isinstance(result, ParsedDocument)
        assert len(result.elements) == 0


class TestMarkdownParserErrorHandling:
    """Error handling tests."""

    def test_parsing_error_handling(self):
        """Test parse error handling."""
        parser = MarkdownParser()
        # Document that might cause error (mistune usually handles most cases)
        doc = Document(page_content="Normal text", metadata={"source": "test.md"})
        # Should parse successfully
        result = parser.parse(doc)
        assert isinstance(result, ParsedDocument)


class TestMarkdownParserIntegration:
    """BaseParser integration tests."""

    def test_inherits_from_base_parser(self):
        """Test inheritance from BaseParser."""
        parser = MarkdownParser()
        assert hasattr(parser, "can_parse")
        assert hasattr(parser, "get_source")
        assert hasattr(parser, "parse")

    def test_can_parse_method(self):
        """Test can_parse method."""
        parser = MarkdownParser()
        doc_md = Document(page_content="# Test", metadata={"source": "test.md"})
        doc_pdf = Document(page_content="PDF", metadata={"source": "test.pdf"})

        assert parser.can_parse(doc_md) is True
        assert parser.can_parse(doc_pdf) is False

    def test_get_source_method(self):
        """Test get_source method."""
        parser = MarkdownParser()
        doc = Document(page_content="# Test", metadata={"source": "test.md"})
        assert parser.get_source(doc) == "test.md"

    def test_id_generation(self):
        """Test element ID generation."""
        parser = MarkdownParser()
        doc = Document(page_content="# H1\n## H2\n### H3", metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 3
        # Check that IDs are unique
        ids = [elem.id for elem in result.elements]
        assert len(ids) == len(set(ids))
        # Check ID format (should be sequential)
        assert result.elements[0].id == "00000001"
        assert result.elements[1].id == "00000002"
        assert result.elements[2].id == "00000003"


class TestMarkdownParserFullDocument:
    """Full document parsing tests (all element types)."""


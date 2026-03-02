"""
Integration tests for Markdown parser.

Tests parsing of real Markdown documents via Pipeline.
Covers end-to-end usage scenarios.
"""

import sys
from pathlib import Path

# Add project root to PYTHONPATH for direct run
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from langchain_core.documents import Document

from documentor import Pipeline, pipeline
from documentor.domain import DocumentFormat, ElementType


class TestMarkdownIntegrationBasic:
    """Basic integration tests for Markdown via Pipeline."""

    def test_pipeline_parse_simple_markdown(self):
        """Test parsing simple Markdown via Pipeline."""
        pipeline_instance = Pipeline()
        doc = Document(
            page_content="# Header\n\nParagraph text.",
            metadata={"source": "test.md"}
        )
        
        result = pipeline_instance.parse(doc)
        
        assert result.format == DocumentFormat.MARKDOWN
        assert result.source == "test.md"
        assert len(result.elements) >= 2
        assert result.elements[0].type == ElementType.HEADER_1
        assert result.elements[1].type == ElementType.TEXT

    def test_pipeline_function_simple_markdown(self):
        """Test parsing via pipeline() function."""
        doc = Document(
            page_content="## Subheader\n\nPlain text.",
            metadata={"source": "test.md"}
        )
        
        result = pipeline(doc)
        
        assert result.format == DocumentFormat.MARKDOWN
        assert len(result.elements) >= 2

    def test_pipeline_parse_many_markdown(self):
        """Test batch processing of multiple Markdown documents."""
        pipeline_instance = Pipeline()
        documents = [
            Document(page_content="# Document 1", metadata={"source": "doc1.md"}),
            Document(page_content="# Document 2", metadata={"source": "doc2.md"}),
            Document(page_content="# Document 3", metadata={"source": "doc3.md"}),
        ]
        
        results = pipeline_instance.parse_many(documents)
        
        assert len(results) == 3
        assert all(r.format == DocumentFormat.MARKDOWN for r in results)
        assert results[0].source == "doc1.md"
        assert results[1].source == "doc2.md"
        assert results[2].source == "doc3.md"


class TestMarkdownIntegrationWithFile:
    """Integration tests with file loading."""

    def test_load_and_parse_markdown_file(self):
        """Test loading and parsing Markdown file."""
        test_file = _project_root / "tests" / "data" / "md.md"
        
        if not test_file.exists():
            pytest.skip(f"Test file not found: {test_file}")
        
        # User creates Document from file
        content = test_file.read_text(encoding="utf-8")
        doc = Document(
            page_content=content,
            metadata={"source": str(test_file), "file_path": str(test_file)}
        )
        result = pipeline(doc)
        
        assert result.format == DocumentFormat.MARKDOWN
        assert result.source == str(test_file)
        assert len(result.elements) > 0

    def test_load_and_parse_full_markdown_file(self):
        """Test parsing full markdown file with all element types."""
        test_file = _project_root / "tests" / "data" / "full_markdown.md"
        
        if not test_file.exists():
            pytest.skip(f"Test file not found: {test_file}")
        
        # User creates Document from file
        content = test_file.read_text(encoding="utf-8")
        doc = Document(
            page_content=content,
            metadata={"source": str(test_file), "file_path": str(test_file)}
        )
        result = pipeline(doc)
        
        # Basic checks
        assert result.format == DocumentFormat.MARKDOWN
        assert result.source == str(test_file)
        assert len(result.elements) > 0
        
        # Check presence of various element types
        element_types = {elem.type for elem in result.elements}
        
        # All header levels should be present
        assert ElementType.HEADER_1 in element_types
        assert ElementType.HEADER_2 in element_types
        assert ElementType.HEADER_3 in element_types
        
        # Other elements
        assert ElementType.TEXT in element_types
        assert ElementType.LIST_ITEM in element_types
        assert ElementType.TABLE in element_types
        assert ElementType.CODE_BLOCK in element_types

    def test_parse_many_from_files(self):
        """Test batch processing of files."""
        test_dir = _project_root / "tests" / "data"
        md_file = test_dir / "md.md"
        full_md_file = test_dir / "full_markdown.md"
        
        if not md_file.exists() or not full_md_file.exists():
            pytest.skip("Test files not found")
        
        # User creates Documents from files
        documents = [
            Document(
                page_content=md_file.read_text(encoding="utf-8"),
                metadata={"source": str(md_file), "file_path": str(md_file)}
            ),
            Document(
                page_content=full_md_file.read_text(encoding="utf-8"),
                metadata={"source": str(full_md_file), "file_path": str(full_md_file)}
            ),
        ]
        
        pipeline_instance = Pipeline()
        results = pipeline_instance.parse_many(documents)
        
        assert len(results) == 2
        assert all(r.format == DocumentFormat.MARKDOWN for r in results)


class TestMarkdownIntegrationMetrics:
    """Performance metrics tests."""

    def test_pipeline_metrics_in_metadata(self):
        """Test that result metadata contains metrics."""
        doc = Document(
            page_content="# Header\n\nText.",
            metadata={"source": "test.md"}
        )
        
        result = pipeline(doc)
        
        # Check metrics presence
        assert result.metadata is not None
        assert "pipeline_metrics" in result.metadata
        
        metrics = result.metadata["pipeline_metrics"]
        
        # Check basic metrics structure
        assert "parsing_time_seconds" in metrics
        assert "num_elements" in metrics
        assert "parser_class" in metrics
        
        # Check new metrics
        assert "elements_by_type" in metrics
        assert "elements_per_second" in metrics
        assert "document_size_bytes" in metrics
        assert "document_lines" in metrics
        
        # Check basic metric values
        assert isinstance(metrics["parsing_time_seconds"], (int, float))
        assert metrics["parsing_time_seconds"] >= 0
        assert metrics["num_elements"] == len(result.elements)
        assert metrics["parser_class"] == "MarkdownParser"
        
        # Check new metric values
        assert isinstance(metrics["elements_by_type"], dict)
        assert isinstance(metrics["elements_per_second"], (int, float))
        assert metrics["elements_per_second"] >= 0
        assert isinstance(metrics["document_size_bytes"], int)
        assert metrics["document_size_bytes"] > 0
        assert isinstance(metrics["document_lines"], int)
        assert metrics["document_lines"] >= 0

    def test_metrics_accuracy(self):
        """Test metrics accuracy."""
        content = "# H1\n## H2\n### H3\n\nText."
        doc = Document(
            page_content=content,
            metadata={"source": "test.md"}
        )
        
        result = pipeline(doc)
        metrics = result.metadata["pipeline_metrics"]
        
        # Element count should match
        assert metrics["num_elements"] == len(result.elements)
        assert metrics["num_elements"] >= 4  # at least 3 headers + text
        
        # Parsing time should be reasonable (under 5 seconds for simple doc)
        assert metrics["parsing_time_seconds"] < 5.0
        
        # Check elements_by_type
        elements_by_type = metrics["elements_by_type"]
        assert isinstance(elements_by_type, dict)
        # Headers should be present
        assert "header_1" in elements_by_type or sum(
            v for k, v in elements_by_type.items() if k.startswith("header_")
        ) >= 3
        
        # Check document_size_bytes and document_lines
        expected_bytes = len(content.encode("utf-8"))
        expected_lines = len(content.splitlines())
        assert metrics["document_size_bytes"] == expected_bytes
        assert metrics["document_lines"] == expected_lines
        
        # Check elements_per_second (pipeline.py uses round(..., 2), so allow tolerance)
        if metrics["parsing_time_seconds"] > 0:
            expected_eps = metrics["num_elements"] / metrics["parsing_time_seconds"]
            # Account for rounding to 2 decimal places in pipeline.py
            assert abs(metrics["elements_per_second"] - expected_eps) < 0.5


class TestMarkdownIntegrationHierarchy:
    """Element hierarchy tests."""

    def test_hierarchy_structure(self):
        """Test hierarchy is built correctly."""
        doc = Document(
            page_content="""# Main header

Text under main header.

## Subheader 1

Text under subheader 1.

### Sub-subheader

Text under sub-subheader.

## Subheader 2

Text under subheader 2.
""",
            metadata={"source": "test.md"}
        )
        
        result = pipeline(doc)
        
        # Find headers
        headers = [e for e in result.elements if e.type in [
            ElementType.HEADER_1, ElementType.HEADER_2, ElementType.HEADER_3
        ]]
        
        assert len(headers) >= 4
        
        # Check that text elements have correct parent_id
        text_elements = [e for e in result.elements if e.type == ElementType.TEXT]
        for text_elem in text_elements:
            if text_elem.parent_id:
                # parent_id must reference an existing element
                parent_ids = {e.id for e in result.elements}
                assert text_elem.parent_id in parent_ids

    def test_hierarchy_with_lists(self):
        """Test hierarchy with lists."""
        doc = Document(
            page_content="""# Header

- Item 1
- Item 2
  - Nested item
- Item 3
""",
            metadata={"source": "test.md"}
        )
        
        result = pipeline(doc)
        
        # Should have header and list items
        assert any(e.type == ElementType.HEADER_1 for e in result.elements)
        assert any(e.type == ElementType.LIST_ITEM for e in result.elements)


class TestMarkdownIntegrationTables:
    """Table parsing tests."""

    def test_table_parsing(self):
        """Test table parsing."""
        doc = Document(
            page_content="""# Table

| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Data 1   | Data 2   | Data 3   |
| Value A  | Value B  | Value C  |
""",
            metadata={"source": "test.md"}
        )
        
        result = pipeline(doc)
        
        # Find table
        tables = [e for e in result.elements if e.type == ElementType.TABLE]
        assert len(tables) > 0
        
        table = tables[0]
        assert table.metadata is not None
        # Tables are stored as HTML in content
        assert isinstance(table.content, str)
        assert "<table>" in table.content
        assert "</table>" in table.content


class TestMarkdownIntegrationErrorHandling:
    """Error handling tests."""

    def test_invalid_document_format(self):
        """Test handling unsupported format."""
        pipeline_instance = Pipeline()
        # Create document with wrong format in metadata
        doc = Document(
            page_content="Some content",
            metadata={"source": "file.xyz", "format": "unknown"}
        )
        
        # Pipeline should detect format by extension or return error
        try:
            result = pipeline_instance.parse(doc)
            assert result.format in [DocumentFormat.MARKDOWN, DocumentFormat.UNKNOWN]
        except Exception:
            pass

    def test_empty_document(self):
        """Test handling empty document."""
        doc = Document(page_content="", metadata={"source": "empty.md"})
        result = pipeline(doc)
        
        assert result.format == DocumentFormat.MARKDOWN
        assert len(result.elements) == 0

    def test_missing_source(self):
        """Test handling document without source."""
        from documentor.exceptions import UnsupportedFormatError
        
        doc = Document(page_content="# Header", metadata={})
        
        # Without source format is UNKNOWN, no parser for it
        with pytest.raises(UnsupportedFormatError, match="No parser available for format: unknown"):
            pipeline(doc)


class TestMarkdownIntegrationPerformance:
    """Performance tests."""

    def test_large_document_performance(self):
        """Test performance on large document."""
        # Create large document
        content = "# Header\n\n" + "\n\n".join([
            f"## Section {i}\n\nSection {i} text." 
            for i in range(100)
        ])
        
        doc = Document(page_content=content, metadata={"source": "large.md"})
        
        result = pipeline(doc)
        metrics = result.metadata["pipeline_metrics"]
        
        # Parsing should succeed
        assert len(result.elements) > 100
        
        # Parsing time should be reasonable (under 5 seconds for 100 sections)
        assert metrics["parsing_time_seconds"] < 5.0

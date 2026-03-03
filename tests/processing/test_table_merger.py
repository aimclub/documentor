"""
Unit tests for table_merger.

Tested functions: compare_table_structures, extract_table_data_from_html,
merge_table_html, merge_docx_tables (basic), merge_pdf_tables (basic).
"""

import pytest

from documentor.processing.table_merger import (
    compare_table_structures,
    extract_table_data_from_html,
    merge_docx_tables,
    merge_pdf_tables,
    merge_table_html,
)


class TestCompareTableStructures:
    """Tests for compare_table_structures."""

    def test_empty_tables_return_zero(self):
        """Empty tables return similarity 0.0."""
        assert compare_table_structures([], []) == 0.0
        assert compare_table_structures([], [["A", "B"]]) == 0.0
        assert compare_table_structures([["A"]], []) == 0.0

    def test_same_headers_same_columns(self):
        """Same headers and column count return 1.0."""
        t1 = [["Col1", "Col2"], ["a", "b"]]
        t2 = [["Col1", "Col2"], ["x", "y"]]
        assert compare_table_structures(t1, t2) == 1.0

    def test_different_column_count_return_zero(self):
        """Different column counts return 0.0."""
        t1 = [["A", "B"]]
        t2 = [["A", "B", "C"]]
        assert compare_table_structures(t1, t2) == 0.0

    def test_headers_case_insensitive(self):
        """Header comparison is case insensitive."""
        t1 = [["COL1", "COL2"]]
        t2 = [["col1", "col2"]]
        assert compare_table_structures(t1, t2) == 1.0

    def test_similarity_threshold_ignored_for_exact_match(self):
        """Exact match returns 1.0 regardless of threshold."""
        t1 = [["H1", "H2"]]
        t2 = [["H1", "H2"]]
        assert compare_table_structures(t1, t2, similarity_threshold=0.9) == 1.0


class TestExtractTableDataFromHtml:
    """Tests for extract_table_data_from_html."""

    def test_extract_simple_table(self):
        """Extracts rows and cells from simple HTML table."""
        html = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
        result = extract_table_data_from_html(html)
        assert result is not None
        assert len(result) == 2
        assert result[0] == ["A", "B"]
        assert result[1] == ["1", "2"]

    def test_no_table_returns_none(self):
        """HTML without table returns None."""
        assert extract_table_data_from_html("<div>no table</div>") is None

    def test_empty_table_returns_none(self):
        """Empty table returns None."""
        assert extract_table_data_from_html("<table></table>") is None


class TestMergeTableHtml:
    """Tests for merge_table_html."""

    def test_merge_two_tables_same_header(self):
        """Merges two tables with same header; skips duplicate header."""
        html1 = "<table><tr><th>X</th><th>Y</th></tr><tr><td>1</td><td>2</td></tr></table>"
        html2 = "<table><tr><th>X</th><th>Y</th></tr><tr><td>3</td><td>4</td></tr></table>"
        result = merge_table_html(html1, html2)
        assert result is not None
        assert "<table>" in result
        assert "1" in result and "2" in result
        assert "3" in result and "4" in result

    def test_merge_missing_table_returns_none(self):
        """If one HTML has no table, returns None."""
        html1 = "<table><tr><td>a</td></tr></table>"
        html2 = "<div>no table</div>"
        assert merge_table_html(html1, html2) is None


class TestMergeDocxTables:
    """Tests for merge_docx_tables."""

    def test_fewer_than_two_tables_returns_unchanged(self):
        """With fewer than 2 tables returns list unchanged."""
        single = [{"xml_position": 0, "type": "table"}]
        assert merge_docx_tables(single, []) == single
        assert merge_docx_tables([], []) == []


class TestMergePdfTables:
    """Tests for merge_pdf_tables."""

    def test_empty_list_returns_empty(self):
        """Empty elements list returns empty list."""
        assert merge_pdf_tables([]) == []

    def test_single_table_returns_unchanged(self):
        """Single table element returns list unchanged."""
        from documentor.domain import Element, ElementType

        el = Element(
            id="t1",
            type=ElementType.TABLE,
            content="<table></table>",
            metadata={"page_num": 0},
        )
        assert merge_pdf_tables([el]) == [el]

"""
Unit tests for reading order building.

Tested class:
- BaseReadingOrderBuilder (via concrete stub)
"""

import pytest

from documentor.ocr.base import BaseReadingOrderBuilder


class StubReadingOrderBuilder(BaseReadingOrderBuilder):
    """Stub that returns elements in input order."""

    def build_reading_order(self, layout_elements):
        return list(layout_elements)


class ReverseReadingOrderBuilder(BaseReadingOrderBuilder):
    """Stub that returns elements in reverse order (for testing order logic)."""

    def build_reading_order(self, layout_elements):
        return list(reversed(layout_elements))


class TestBaseReadingOrderBuilder:
    """Tests for BaseReadingOrderBuilder interface."""

    def test_build_reading_order_returns_list(self):
        """build_reading_order returns a list of elements."""
        builder = StubReadingOrderBuilder()
        elements = [{"bbox": [0, 0, 10, 10], "category": "Title"}]
        result = builder.build_reading_order(elements)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_build_reading_order_preserves_input_order_when_stub(self):
        """Stub implementation preserves input order."""
        builder = StubReadingOrderBuilder()
        elements = [
            {"bbox": [0, 0, 50, 50], "category": "Title", "text": "A"},
            {"bbox": [0, 60, 50, 110], "category": "Text", "text": "B"},
        ]
        result = builder.build_reading_order(elements)
        assert [r["text"] for r in result] == ["A", "B"]

    def test_build_reading_order_reverse_stub(self):
        """Reverse stub returns elements in reverse order."""
        builder = ReverseReadingOrderBuilder()
        elements = [
            {"bbox": [0, 0, 50, 50], "category": "Title", "text": "First"},
            {"bbox": [0, 60, 50, 110], "category": "Text", "text": "Second"},
        ]
        result = builder.build_reading_order(elements)
        assert [r["text"] for r in result] == ["Second", "First"]

    def test_build_reading_order_empty_input(self):
        """build_reading_order with empty list returns empty list."""
        builder = StubReadingOrderBuilder()
        result = builder.build_reading_order([])
        assert result == []

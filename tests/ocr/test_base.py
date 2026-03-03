"""
Unit tests for OCR base classes.

Tested classes:
- BaseLayoutDetector
- BaseOCR
- BaseReadingOrderBuilder
- BaseTableParser
- BaseTextExtractor
- BaseFormulaExtractor
"""

import pytest
from PIL import Image

from documentor.ocr.base import (
    BaseFormulaExtractor,
    BaseLayoutDetector,
    BaseOCR,
    BaseReadingOrderBuilder,
    BaseTableParser,
    BaseTextExtractor,
)


class StubLayoutDetector(BaseLayoutDetector):
    """Concrete implementation for testing BaseLayoutDetector."""

    def detect_layout(self, image, origin_image=None):
        return [{"bbox": [0, 0, 100, 100], "category": "Text", "text": "sample"}]


class StubOCR(BaseOCR):
    """Concrete implementation for testing BaseOCR."""

    def recognize_text(self, image):
        return "recognized text"


class StubReadingOrderBuilder(BaseReadingOrderBuilder):
    """Concrete implementation for testing BaseReadingOrderBuilder."""

    def build_reading_order(self, layout_elements):
        return list(layout_elements)


class StubTableParser(BaseTableParser):
    """Concrete implementation for testing BaseTableParser."""

    def parse_table(self, image, bbox):
        return "<table></table>", True


class StubTextExtractor(BaseTextExtractor):
    """Concrete implementation for testing BaseTextExtractor."""

    def extract_text(self, image, bbox, category):
        return "extracted text"


class StubFormulaExtractor(BaseFormulaExtractor):
    """Concrete implementation for testing BaseFormulaExtractor."""

    def extract_formula(self, image, bbox):
        return "x^2 + y^2"


class TestBaseLayoutDetector:
    """Tests for BaseLayoutDetector."""

    def test_detect_layout_returns_list(self):
        """detect_layout returns a list of layout elements."""
        img = Image.new("RGB", (200, 200), color="white")
        detector = StubLayoutDetector()
        result = detector.detect_layout(img)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["category"] == "Text"
        assert "bbox" in result[0]

    def test_detect_layout_with_text_default_uses_detect_layout(self):
        """detect_layout_with_text defaults to detect_layout when not overridden."""
        img = Image.new("RGB", (200, 200), color="white")
        detector = StubLayoutDetector()
        result = detector.detect_layout_with_text(img)
        assert result == detector.detect_layout(img)


class TestBaseOCR:
    """Tests for BaseOCR."""

    def test_recognize_text_returns_string(self):
        """recognize_text returns a string."""
        img = Image.new("RGB", (100, 100), color="white")
        ocr = StubOCR()
        result = ocr.recognize_text(img)
        assert isinstance(result, str)
        assert result == "recognized text"


class TestBaseReadingOrderBuilder:
    """Tests for BaseReadingOrderBuilder."""

    def test_build_reading_order_preserves_elements(self):
        """build_reading_order returns elements (order depends on implementation)."""
        builder = StubReadingOrderBuilder()
        elements = [
            {"bbox": [0, 0, 50, 50], "category": "Title"},
            {"bbox": [0, 60, 50, 110], "category": "Text"},
        ]
        result = builder.build_reading_order(elements)
        assert len(result) == 2
        assert result[0]["category"] == "Title"
        assert result[1]["category"] == "Text"


class TestBaseTableParser:
    """Tests for BaseTableParser."""

    def test_parse_table_returns_tuple(self):
        """parse_table returns (html_or_none, success)."""
        img = Image.new("RGB", (200, 200), color="white")
        parser = StubTableParser()
        html, success = parser.parse_table(img, [0, 0, 200, 200])
        assert success is True
        assert html == "<table></table>"


class TestBaseTextExtractor:
    """Tests for BaseTextExtractor."""

    def test_extract_text_returns_string(self):
        """extract_text returns a string."""
        img = Image.new("RGB", (100, 100), color="white")
        extractor = StubTextExtractor()
        result = extractor.extract_text(img, [0, 0, 100, 100], "Text")
        assert isinstance(result, str)
        assert result == "extracted text"


class TestBaseFormulaExtractor:
    """Tests for BaseFormulaExtractor."""

    def test_extract_formula_returns_string(self):
        """extract_formula returns a string (e.g. LaTeX)."""
        img = Image.new("RGB", (100, 50), color="white")
        extractor = StubFormulaExtractor()
        result = extractor.extract_formula(img, [0, 0, 100, 50])
        assert isinstance(result, str)
        assert "x^2" in result

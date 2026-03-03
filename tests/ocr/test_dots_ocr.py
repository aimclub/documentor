"""
Unit tests for Dots.OCR integration.

Tested classes:
- DotsOCRLayoutDetector
- DotsOCRTextExtractor
- DotsOCRTableParser
- DotsOCRFormulaExtractor
"""

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from documentor.ocr.base import (
    BaseFormulaExtractor,
    BaseLayoutDetector,
    BaseTableParser,
    BaseTextExtractor,
)
from documentor.ocr.dots_ocr.formula_extractor import DotsOCRFormulaExtractor
from documentor.ocr.dots_ocr.layout_detector import DotsOCRLayoutDetector
from documentor.ocr.dots_ocr.table_parser import DotsOCRTableParser
from documentor.ocr.dots_ocr.text_extractor import DotsOCRTextExtractor


class TestDotsOCRLayoutDetector:
    """Tests for DotsOCRLayoutDetector."""

    def test_is_subclass_of_base_layout_detector(self):
        """DotsOCRLayoutDetector is a subclass of BaseLayoutDetector."""
        assert issubclass(DotsOCRLayoutDetector, BaseLayoutDetector)

    def test_initialization_default(self):
        """Detector initializes with use_direct_api=True by default."""
        detector = DotsOCRLayoutDetector()
        assert detector.use_direct_api is True
        assert detector.ocr_manager is None

    def test_initialization_with_manager(self):
        """Detector accepts ocr_manager argument."""
        mock_manager = MagicMock()
        detector = DotsOCRLayoutDetector(use_direct_api=False, ocr_manager=mock_manager)
        assert detector.use_direct_api is False
        assert detector.ocr_manager is mock_manager

    @patch("documentor.ocr.dots_ocr.layout_detector.process_layout_detection")
    def test_detect_layout_returns_mocked_cells(self, mock_process):
        """detect_layout returns layout cells from process_layout_detection."""
        mock_process.return_value = (
            [{"bbox": [10, 10, 90, 90], "category": "Text", "text": "hello"}],
            "raw",
            True,
        )
        detector = DotsOCRLayoutDetector()
        img = Image.new("RGB", (100, 100), color="white")
        result = detector.detect_layout(img)
        assert len(result) == 1
        assert result[0]["category"] == "Text"
        assert result[0]["text"] == "hello"
        mock_process.assert_called_once()


class TestDotsOCRTextExtractor:
    """Tests for DotsOCRTextExtractor."""

    def test_is_subclass_of_base_text_extractor(self):
        """DotsOCRTextExtractor is a subclass of BaseTextExtractor."""
        assert issubclass(DotsOCRTextExtractor, BaseTextExtractor)

    def test_initialization(self):
        """Text extractor initializes without arguments."""
        ext = DotsOCRTextExtractor()
        assert ext is not None


class TestDotsOCRTableParser:
    """Tests for DotsOCRTableParser."""

    def test_is_subclass_of_base_table_parser(self):
        """DotsOCRTableParser is a subclass of BaseTableParser."""
        assert issubclass(DotsOCRTableParser, BaseTableParser)

    def test_initialization(self):
        """Table parser can be instantiated."""
        parser = DotsOCRTableParser()
        assert parser is not None


class TestDotsOCRFormulaExtractor:
    """Tests for DotsOCRFormulaExtractor."""

    def test_is_subclass_of_base_formula_extractor(self):
        """DotsOCRFormulaExtractor is a subclass of BaseFormulaExtractor."""
        assert issubclass(DotsOCRFormulaExtractor, BaseFormulaExtractor)

    def test_initialization(self):
        """Formula extractor can be instantiated."""
        ext = DotsOCRFormulaExtractor()
        assert ext is not None

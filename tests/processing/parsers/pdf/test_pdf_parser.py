"""
Tests for PDF parser with Dots OCR.

Tested class:
- PdfParser
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from io import BytesIO

import pytest
from langchain_core.documents import Document
from PIL import Image
import pandas as pd

# Add project root to PYTHONPATH
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from documentor.domain import DocumentFormat, Element, ElementType, ParsedDocument
from documentor.exceptions import ParsingError, ValidationError, UnsupportedFormatError
from documentor.processing.parsers.pdf.pdf_parser import PdfParser


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_pdf_path(tmp_path):
    """Create temporary PDF file for tests."""
    pdf_path = tmp_path / "test.pdf"
    try:
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Test PDF Content")
        doc.save(str(pdf_path))
        doc.close()
        return str(pdf_path)
    except ImportError:
        pytest.skip("PyMuPDF (fitz) not installed")


@pytest.fixture
def scanned_pdf_path(tmp_path):
    """Create temporary scanned PDF file (no text layer)."""
    pdf_path = tmp_path / "scanned_test.pdf"
    try:
        import fitz
        from PIL import Image
        
        doc = fitz.open()
        page = doc.new_page()
        
        # Create white image
        white_image = Image.new("RGB", (200, 100), color="white")
        img_bytes = BytesIO()
        white_image.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        
        # Insert image into PDF
        img_rect = fitz.Rect(0, 0, 200, 100)
        page.insert_image(img_rect, stream=img_bytes.getvalue())
        
        doc.save(str(pdf_path))
        doc.close()
        return str(pdf_path)
    except ImportError:
        pytest.skip("PyMuPDF (fitz) or PIL not installed")


@pytest.fixture
def mock_layout_elements():
    """Return mock layout elements from Dots OCR."""
    return [
        {
            "bbox": [100, 50, 500, 100],
            "category": "Section-header",
            "page_num": 0,
            "text": "Introduction",
        },
        {
            "bbox": [100, 120, 500, 200],
            "category": "Text",
            "page_num": 0,
            "text": "This is a test paragraph.",
        },
        {
            "bbox": [100, 220, 500, 300],
            "category": "Text",
            "page_num": 0,
            "text": "Another paragraph.",
        },
        {
            "bbox": [100, 350, 400, 450],
            "category": "Picture",
            "page_num": 0,
        },
        {
            "bbox": [100, 470, 400, 500],
            "category": "Caption",
            "page_num": 0,
            "text": "Figure 1: Test image",
        },
    ]


@pytest.fixture
def mock_image():
    """Create test image."""
    return Image.new("RGB", (800, 600), color="white")


@pytest.fixture
def pdf_parser():
    """Create PdfParser instance for tests."""
    return PdfParser()


# ============================================================================
# Initialization tests
# ============================================================================

class TestPdfParserInitialization:
    """PdfParser initialization tests."""

    def test_default_initialization(self):
        """Test initialization with default parameters."""
        parser = PdfParser()
        assert parser.format == DocumentFormat.PDF
        assert parser._config is not None

    def test_initialization_with_ocr_manager(self):
        """Test initialization with OCR manager."""
        mock_manager = MagicMock()
        parser = PdfParser(ocr_manager=mock_manager)
        assert parser.ocr_manager is mock_manager

    def test_load_config(self):
        """Test config loading."""
        parser = PdfParser()
        assert parser._config is not None
        # Check we can get values from config
        render_scale = parser._get_config("layout_detection.render_scale", 2.0)
        assert isinstance(render_scale, (int, float))


# ============================================================================
# can_parse tests
# ============================================================================

class TestCanParse:
    """Tests for can_parse method."""

    def test_can_parse_pdf(self):
        """Test can_parse for PDF file."""
        parser = PdfParser()
        doc = Document(page_content="", metadata={"source": "test.pdf"})
        assert parser.can_parse(doc) is True

    def test_can_parse_non_pdf(self):
        """Test can_parse for non-PDF file."""
        parser = PdfParser()
        doc = Document(page_content="", metadata={"source": "test.md"})
        assert parser.can_parse(doc) is False

    def test_can_parse_no_source(self):
        """Test can_parse for document without source."""
        parser = PdfParser()
        doc = Document(page_content="", metadata={})
        assert parser.can_parse(doc) is False


# ============================================================================
# _is_text_extractable tests
# ============================================================================

class TestIsTextExtractable:
    """Tests for _is_text_extractable method."""

    def test_is_text_extractable_with_text(self, sample_pdf_path):
        """Test extractable text check in PDF with text."""
        parser = PdfParser()
        result = parser._is_text_extractable(sample_pdf_path)
        assert isinstance(result, bool)

    def test_is_text_extractable_scanned_pdf(self, scanned_pdf_path):
        """Test extractable text check in scanned PDF."""
        parser = PdfParser()
        result = parser._is_text_extractable(scanned_pdf_path)
        assert result is False

    def test_is_text_extractable_invalid_path(self):
        """Test extractable text check for nonexistent file."""
        parser = PdfParser()
        result = parser._is_text_extractable("/nonexistent/file.pdf")
        assert result is False

    def test_is_text_extractable_handles_errors(self):
        """Test that _is_text_extractable handles errors gracefully."""
        parser = PdfParser()
        with patch("documentor.processing.parsers.pdf.pdf_parser.fitz.open", side_effect=Exception("Error")):
            result = parser._is_text_extractable("test.pdf")
            assert result is False


# ============================================================================
# _get_page_count tests
# ============================================================================

class TestGetPageCount:
    """Tests for _get_page_count method."""

    def test_get_page_count(self, sample_pdf_path):
        """Test getting page count."""
        parser = PdfParser()
        count = parser._get_page_count(sample_pdf_path)
        assert count >= 1

    def test_get_page_count_invalid_path(self):
        """Test getting page count for nonexistent file."""
        parser = PdfParser()
        with pytest.raises(Exception):
            parser._get_page_count("/nonexistent/file.pdf")


# ============================================================================
# _filter_layout_elements tests
# ============================================================================

class TestFilterLayoutElements:
    """Tests for _filter_layout_elements method."""

    def test_filter_page_headers(self, pdf_parser):
        """Test filtering Page-header elements."""
        elements = [
            {"category": "Page-header", "bbox": [0, 0, 100, 50]},
            {"category": "Text", "bbox": [0, 100, 100, 150]},
            {"category": "Page-header", "bbox": [0, 200, 100, 250]},
        ]
        filtered = pdf_parser.layout_processor.filter_layout_elements(elements)
        assert len(filtered) == 1
        assert filtered[0]["category"] == "Text"

    def test_filter_page_footers(self, pdf_parser):
        """Test filtering Page-footer elements."""
        elements = [
            {"category": "Page-footer", "bbox": [0, 0, 100, 50]},
            {"category": "Text", "bbox": [0, 100, 100, 150]},
        ]
        filtered = pdf_parser.layout_processor.filter_layout_elements(elements)
        assert len(filtered) == 1
        assert filtered[0]["category"] == "Text"

    def test_filter_keeps_other_elements(self, pdf_parser):
        """Test that other elements are not filtered."""
        elements = [
            {"category": "Text", "bbox": [0, 0, 100, 50]},
            {"category": "Picture", "bbox": [0, 100, 100, 150]},
            {"category": "Table", "bbox": [0, 200, 100, 250]},
        ]
        filtered = pdf_parser.layout_processor.filter_layout_elements(elements)
        assert len(filtered) == 3


# ============================================================================
# _detect_layout_for_all_pages tests
# ============================================================================

class TestDetectLayoutForAllPages:
    """Tests for _detect_layout_for_all_pages with Dots OCR."""

    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfLayoutProcessor")
    def test_detect_layout_for_all_pages_with_text(
        self, mock_processor_class, pdf_parser, sample_pdf_path, mock_image
    ):
        """Test layout detection for PDF with text (prompt_layout_only_en)."""
        mock_processor = MagicMock()
        mock_processor.detect_layout_for_all_pages.return_value = [
            {"bbox": [0, 0, 100, 50], "category": "Text", "page_num": 0},
        ]
        mock_processor_class.return_value = mock_processor
        
        pdf_parser.layout_processor = mock_processor
        
        layout_elements = pdf_parser._detect_layout_for_all_pages(sample_pdf_path, use_text_extraction=False)
        assert len(layout_elements) > 0
        assert all("page_num" in elem for elem in layout_elements)
        # For PDF with text, prompt_layout_only_en should be used
        mock_processor.detect_layout_for_all_pages.assert_called()

    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfLayoutProcessor")
    def test_detect_layout_for_all_pages_scanned(
        self, mock_processor_class, pdf_parser, scanned_pdf_path, mock_image
    ):
        """Test layout detection for scanned PDF (prompt_layout_all_en)."""
        mock_processor = MagicMock()
        mock_processor.detect_layout_for_all_pages.return_value = [
            {"bbox": [0, 0, 100, 50], "category": "Text", "page_num": 0, "text": "Extracted text"},
        ]
        mock_processor_class.return_value = mock_processor
        
        pdf_parser.layout_processor = mock_processor
        
        layout_elements = pdf_parser._detect_layout_for_all_pages(scanned_pdf_path, use_text_extraction=True)
        assert len(layout_elements) > 0
        # Check that processor was used
        mock_processor.detect_layout_for_all_pages.assert_called()

    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfLayoutProcessor")
    def test_detect_layout_handles_errors(self, mock_processor_class, pdf_parser, sample_pdf_path):
        """Test that layout detection handles errors."""
        mock_processor = MagicMock()
        mock_processor.detect_layout_for_all_pages.side_effect = Exception("Layout error")
        mock_processor_class.return_value = mock_processor
        
        pdf_parser.layout_processor = mock_processor
        
        # Error should propagate as method just delegates
        with pytest.raises(Exception, match="Layout error"):
            pdf_parser._detect_layout_for_all_pages(sample_pdf_path, use_text_extraction=False)


# ============================================================================
# _analyze_header_levels_from_elements tests
# ============================================================================

class TestAnalyzeHeaderLevels:
    """Tests for _analyze_header_levels_from_elements method."""

    def test_analyze_header_levels(self, pdf_parser, mock_layout_elements, sample_pdf_path):
        """Test header level analysis."""
        analyzed = pdf_parser.hierarchy_builder.analyze_header_levels_from_elements(
            mock_layout_elements, sample_pdf_path, is_text_extractable=True
        )
        # Method returns all elements, possibly with extra fields
        assert len(analyzed) >= len(mock_layout_elements)
        # Check that Section-header got level
        header = next((e for e in analyzed if e.get("category") == "Section-header"), None)
        if header:
            assert "level" in header

    def test_analyze_header_levels_no_headers(self, pdf_parser, sample_pdf_path):
        """Test level analysis when no headers."""
        elements = [
            {"category": "Text", "bbox": [0, 0, 100, 50], "page_num": 0},
            {"category": "Picture", "bbox": [0, 100, 100, 150], "page_num": 0},
        ]
        analyzed = pdf_parser.hierarchy_builder.analyze_header_levels_from_elements(
            elements, sample_pdf_path, is_text_extractable=True
        )
        # Method returns all elements, possibly with extra fields
        assert len(analyzed) >= len(elements)


# ============================================================================
# _build_hierarchy_from_section_headers tests
# ============================================================================

class TestBuildHierarchy:
    """Tests for _build_hierarchy_from_section_headers method."""

    def test_build_hierarchy_with_headers(self, pdf_parser, mock_layout_elements):
        """Test building hierarchy with headers."""
        hierarchy = pdf_parser.hierarchy_builder.build_hierarchy_from_section_headers(mock_layout_elements)
        assert len(hierarchy) > 0
        assert all("header" in section and "children" in section for section in hierarchy)

    def test_build_hierarchy_no_headers(self, pdf_parser):
        """Test building hierarchy without headers."""
        elements = [
            {"category": "Text", "bbox": [0, 0, 100, 50], "page_num": 0},
            {"category": "Picture", "bbox": [0, 100, 100, 150], "page_num": 0},
        ]
        hierarchy = pdf_parser.hierarchy_builder.build_hierarchy_from_section_headers(elements)
        assert len(hierarchy) == 1
        assert hierarchy[0]["header"] is None
        assert len(hierarchy[0]["children"]) == 2


# ============================================================================
# _extract_text_by_bboxes tests
# ============================================================================

class TestExtractTextByBboxes:
    """Tests for _extract_text_by_bboxes method."""

    def test_extract_text_by_bboxes_with_text(self, pdf_parser, sample_pdf_path):
        """Test text extraction by bbox for PDF with text."""
        elements = [
            {"category": "Text", "bbox": [50, 50, 200, 100], "page_num": 0},
        ]
        text_elements = pdf_parser.text_extractor.extract_text_by_bboxes(sample_pdf_path, elements, use_ocr=False)
        assert len(text_elements) == len(elements)
        assert all("text" in elem for elem in text_elements)

    def test_extract_text_by_bboxes_no_text_elements(self, pdf_parser, sample_pdf_path):
        """Test text extraction when no text elements."""
        elements = [
            {"category": "Picture", "bbox": [0, 0, 100, 50], "page_num": 0},
        ]
        text_elements = pdf_parser.text_extractor.extract_text_by_bboxes(sample_pdf_path, elements, use_ocr=False)
        # Method returns all elements (Picture skipped but added to result)
        assert len(text_elements) >= len(elements)

    def test_extract_text_by_bboxes_scanned_pdf(self, pdf_parser, scanned_pdf_path):
        """Test text extraction for scanned PDF (text already in elements)."""
        # For scanned PDF text is already extracted by Dots OCR
        elements = [
            {"category": "Text", "bbox": [50, 50, 200, 100], "page_num": 0, "text": "Extracted by OCR"},
        ]
        # use_ocr=True means text is already in elements
        text_elements = pdf_parser.text_extractor.extract_text_by_bboxes(scanned_pdf_path, elements, use_ocr=True)
        assert len(text_elements) == len(elements)
        # Text should already be in elements (possibly markdown-cleaned)
        assert "Extracted by OCR" in text_elements[0].get("text", "") or text_elements[0].get("text", "") == "Extracted by OCR"


# ============================================================================
# _parse_tables tests
# ============================================================================

class TestParseTables:
    """Tests for _parse_tables with Dots OCR HTML."""

    @patch("documentor.processing.parsers.pdf.table_parser.parse_table_from_html")
    def test_parse_tables_from_dots_ocr_html(self, mock_parse_html, pdf_parser, sample_pdf_path):
        """Test parsing tables from Dots OCR HTML."""
        mock_parse_html.return_value = (
            "<table><tr><td>Col1</td><td>Col2</td></tr></table>",
            True,
        )
        
        elements = [
            Element(
                id="00000001",
                type=ElementType.TABLE,
                content="",
                metadata={
                    "bbox": [100, 100, 400, 300],
                    "page_num": 0,
                    "table_html": "<table><tr><td>Col1</td><td>Col2</td></tr></table>",
                },
            ),
        ]
        parsed_elements = pdf_parser.table_parser.parse_tables(elements, sample_pdf_path, use_dots_ocr_html=True)
        assert len(parsed_elements) == len(elements)
        mock_parse_html.assert_called()
        table_elem = next((e for e in parsed_elements if e.type == ElementType.TABLE), None)
        if table_elem:
            assert "<table>" in table_elem.content or "table" in str(table_elem.metadata.get("content", ""))


    def test_parse_tables_no_tables(self, pdf_parser, sample_pdf_path):
        """Test parsing tables when there are none."""
        elements = [
            Element(
                id="00000001",
                type=ElementType.TEXT,
                content="Text content",
                metadata={},
            ),
        ]
        parsed_elements = pdf_parser.table_parser.parse_tables(elements, sample_pdf_path)
        assert len(parsed_elements) == len(elements)


# ============================================================================
# _store_images_in_metadata tests
# ============================================================================

class TestStoreImagesInMetadata:
    """Tests for _store_images_in_metadata method."""

    def test_store_images_in_metadata(self, pdf_parser, sample_pdf_path):
        """Test storing images in metadata."""
        elements = [
            Element(
                id="00000001",
                type=ElementType.IMAGE,
                content="",
                metadata={"bbox": [100, 100, 200, 200], "page_num": 0},
            ),
            Element(
                id="00000002",
                type=ElementType.CAPTION,
                content="Image caption",
                metadata={"bbox": [100, 210, 200, 230], "page_num": 0},
            ),
        ]
        stored_elements = pdf_parser.image_processor.store_images_in_metadata(elements, sample_pdf_path)
        # Check that images were processed
        assert len(stored_elements) == len(elements)

    def test_store_images_no_images(self, pdf_parser, sample_pdf_path):
        """Test storing images when there are none."""
        elements = [
            Element(
                id="00000001",
                type=ElementType.TEXT,
                content="Text content",
                metadata={},
            ),
        ]
        stored_elements = pdf_parser.image_processor.store_images_in_metadata(elements, sample_pdf_path)
        assert len(stored_elements) == len(elements)


# ============================================================================
# Full parse cycle tests
# ============================================================================

class TestParseFullCycle:
    """Full parsing cycle tests."""

    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfLayoutProcessor")
    def test_parse_complete_cycle(
        self,
        mock_processor_class,
        pdf_parser,
        sample_pdf_path,
        mock_image,
        mock_layout_elements,
    ):
        """Test full parse cycle for PDF with text."""
        # Set up mocks
        mock_processor = MagicMock()
        mock_processor.detect_layout_for_all_pages.return_value = mock_layout_elements
        mock_processor.reprocess_tables_with_all_en.return_value = mock_layout_elements
        mock_processor.filter_layout_elements.return_value = mock_layout_elements
        mock_processor_class.return_value = mock_processor
        
        pdf_parser.layout_processor = mock_processor
        
        doc = Document(page_content="", metadata={"source": sample_pdf_path})
        result = pdf_parser.parse(doc)
        
        assert isinstance(result, ParsedDocument)
        assert result.format == DocumentFormat.PDF
        assert result.source == sample_pdf_path
        assert len(result.elements) > 0

    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfLayoutProcessor")
    def test_parse_scanned_pdf_full_cycle(
        self,
        mock_processor_class,
        pdf_parser,
        scanned_pdf_path,
        mock_image,
        mock_layout_elements,
    ):
        """Test full parse cycle for scanned PDF."""
        # For scanned PDF elements already contain text from Dots OCR
        mock_layout_elements_with_text = [
            {**elem, "text": "Extracted text"} if elem.get("category") == "Text" else elem
            for elem in mock_layout_elements
        ]
        
        # Set up mocks
        mock_processor = MagicMock()
        mock_processor.detect_layout_for_all_pages.return_value = mock_layout_elements_with_text
        mock_processor.filter_layout_elements.return_value = mock_layout_elements_with_text
        mock_processor_class.return_value = mock_processor
        
        pdf_parser.layout_processor = mock_processor
        
        doc = Document(page_content="", metadata={"source": scanned_pdf_path})
        result = pdf_parser.parse(doc)
        
        assert isinstance(result, ParsedDocument)
        assert result.format == DocumentFormat.PDF
        assert len(result.elements) > 0

    def test_parse_invalid_document(self, pdf_parser):
        """Test parsing invalid document."""
        doc = Document(page_content="", metadata={})
        with pytest.raises(ValidationError):
            pdf_parser.parse(doc)

    def test_parse_wrong_format(self, pdf_parser):
        """Test parsing document with wrong format."""
        doc = Document(page_content="", metadata={"source": "test.md"})
        with pytest.raises(UnsupportedFormatError):
            pdf_parser.parse(doc)

    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfLayoutProcessor")
    def test_parse_handles_parsing_errors(self, mock_processor_class, pdf_parser, sample_pdf_path):
        """Test that parse handles parsing errors."""
        mock_processor = MagicMock()
        mock_processor.detect_layout_for_all_pages.side_effect = Exception("Error")
        mock_processor_class.return_value = mock_processor
        
        pdf_parser.layout_processor = mock_processor
        
        doc = Document(page_content="", metadata={"source": sample_pdf_path})
        with pytest.raises(ParsingError):
            pdf_parser.parse(doc)

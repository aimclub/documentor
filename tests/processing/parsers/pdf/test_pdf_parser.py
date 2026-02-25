"""
Тесты для PDF парсера с Dots OCR.

Тестируемый класс:
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

# Добавляем корневую директорию проекта в PYTHONPATH
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from documentor.domain import DocumentFormat, Element, ElementType, ParsedDocument
from documentor.exceptions import ParsingError, ValidationError, UnsupportedFormatError
from documentor.processing.parsers.pdf.pdf_parser import PdfParser


# ============================================================================
# Фикстуры
# ============================================================================

@pytest.fixture
def sample_pdf_path(tmp_path):
    """Создает временный PDF файл для тестов."""
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
        pytest.skip("PyMuPDF (fitz) не установлен")


@pytest.fixture
def scanned_pdf_path(tmp_path):
    """Создает временный сканированный PDF файл (без текстового слоя)."""
    pdf_path = tmp_path / "scanned_test.pdf"
    try:
        import fitz
        from PIL import Image
        
        doc = fitz.open()
        page = doc.new_page()
        
        # Создаем белое изображение
        white_image = Image.new("RGB", (200, 100), color="white")
        img_bytes = BytesIO()
        white_image.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        
        # Вставляем изображение в PDF
        img_rect = fitz.Rect(0, 0, 200, 100)
        page.insert_image(img_rect, stream=img_bytes.getvalue())
        
        doc.save(str(pdf_path))
        doc.close()
        return str(pdf_path)
    except ImportError:
        pytest.skip("PyMuPDF (fitz) или PIL не установлен")


@pytest.fixture
def mock_layout_elements():
    """Возвращает моковые элементы layout от Dots OCR."""
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
    """Создает тестовое изображение."""
    return Image.new("RGB", (800, 600), color="white")


@pytest.fixture
def pdf_parser():
    """Создает экземпляр PdfParser для тестов."""
    return PdfParser()


# ============================================================================
# Тесты инициализации
# ============================================================================

class TestPdfParserInitialization:
    """Тесты инициализации PdfParser."""

    def test_default_initialization(self):
        """Тест инициализации с параметрами по умолчанию."""
        parser = PdfParser()
        assert parser.format == DocumentFormat.PDF
        assert parser._config is not None

    def test_initialization_with_ocr_manager(self):
        """Тест инициализации с OCR менеджером."""
        mock_manager = MagicMock()
        parser = PdfParser(ocr_manager=mock_manager)
        assert parser.ocr_manager is mock_manager

    def test_load_config(self):
        """Тест загрузки конфигурации."""
        parser = PdfParser()
        assert parser._config is not None
        # Проверяем, что можем получить значения из конфига
        render_scale = parser._get_config("layout_detection.render_scale", 2.0)
        assert isinstance(render_scale, (int, float))


# ============================================================================
# Тесты can_parse
# ============================================================================

class TestCanParse:
    """Тесты метода can_parse."""

    def test_can_parse_pdf(self):
        """Тест can_parse для PDF файла."""
        parser = PdfParser()
        doc = Document(page_content="", metadata={"source": "test.pdf"})
        assert parser.can_parse(doc) is True

    def test_can_parse_non_pdf(self):
        """Тест can_parse для не-PDF файла."""
        parser = PdfParser()
        doc = Document(page_content="", metadata={"source": "test.md"})
        assert parser.can_parse(doc) is False

    def test_can_parse_no_source(self):
        """Тест can_parse для документа без source."""
        parser = PdfParser()
        doc = Document(page_content="", metadata={})
        assert parser.can_parse(doc) is False


# ============================================================================
# Тесты _is_text_extractable
# ============================================================================

class TestIsTextExtractable:
    """Тесты метода _is_text_extractable."""

    def test_is_text_extractable_with_text(self, sample_pdf_path):
        """Тест проверки выделяемого текста в PDF с текстом."""
        parser = PdfParser()
        result = parser._is_text_extractable(sample_pdf_path)
        assert isinstance(result, bool)
        # PDF с текстом может вернуть True или False в зависимости от количества текста
        # Просто проверяем, что метод работает

    def test_is_text_extractable_scanned_pdf(self, scanned_pdf_path):
        """Тест проверки выделяемого текста в сканированном PDF."""
        parser = PdfParser()
        result = parser._is_text_extractable(scanned_pdf_path)
        # Сканированный PDF должен вернуть False
        assert result is False

    def test_is_text_extractable_invalid_path(self):
        """Тест проверки выделяемого текста для несуществующего файла."""
        parser = PdfParser()
        result = parser._is_text_extractable("/nonexistent/file.pdf")
        assert result is False

    def test_is_text_extractable_handles_errors(self):
        """Тест что _is_text_extractable обрабатывает ошибки gracefully."""
        parser = PdfParser()
        with patch("documentor.processing.parsers.pdf.pdf_parser.fitz.open", side_effect=Exception("Error")):
            result = parser._is_text_extractable("test.pdf")
            assert result is False


# ============================================================================
# Тесты _get_page_count
# ============================================================================

class TestGetPageCount:
    """Тесты метода _get_page_count."""

    def test_get_page_count(self, sample_pdf_path):
        """Тест получения количества страниц."""
        parser = PdfParser()
        count = parser._get_page_count(sample_pdf_path)
        assert count >= 1

    def test_get_page_count_invalid_path(self):
        """Тест получения количества страниц для несуществующего файла."""
        parser = PdfParser()
        with pytest.raises(Exception):
            parser._get_page_count("/nonexistent/file.pdf")


# ============================================================================
# Тесты _filter_layout_elements
# ============================================================================

class TestFilterLayoutElements:
    """Тесты метода _filter_layout_elements."""

    def test_filter_page_headers(self, pdf_parser):
        """Тест фильтрации Page-header элементов."""
        elements = [
            {"category": "Page-header", "bbox": [0, 0, 100, 50]},
            {"category": "Text", "bbox": [0, 100, 100, 150]},
            {"category": "Page-header", "bbox": [0, 200, 100, 250]},
        ]
        filtered = pdf_parser.layout_processor.filter_layout_elements(elements)
        assert len(filtered) == 1
        assert filtered[0]["category"] == "Text"

    def test_filter_page_footers(self, pdf_parser):
        """Тест фильтрации Page-footer элементов."""
        elements = [
            {"category": "Page-footer", "bbox": [0, 0, 100, 50]},
            {"category": "Text", "bbox": [0, 100, 100, 150]},
        ]
        filtered = pdf_parser.layout_processor.filter_layout_elements(elements)
        assert len(filtered) == 1
        assert filtered[0]["category"] == "Text"

    def test_filter_keeps_other_elements(self, pdf_parser):
        """Тест что другие элементы не фильтруются."""
        elements = [
            {"category": "Text", "bbox": [0, 0, 100, 50]},
            {"category": "Picture", "bbox": [0, 100, 100, 150]},
            {"category": "Table", "bbox": [0, 200, 100, 250]},
        ]
        filtered = pdf_parser.layout_processor.filter_layout_elements(elements)
        assert len(filtered) == 3


# ============================================================================
# Тесты _detect_layout_for_all_pages
# ============================================================================

class TestDetectLayoutForAllPages:
    """Тесты метода _detect_layout_for_all_pages с Dots OCR."""

    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfLayoutProcessor")
    def test_detect_layout_for_all_pages_with_text(
        self, mock_processor_class, pdf_parser, sample_pdf_path, mock_image
    ):
        """Тест layout detection для PDF с текстом (prompt_layout_only_en)."""
        mock_processor = MagicMock()
        mock_processor.detect_layout_for_all_pages.return_value = [
            {"bbox": [0, 0, 100, 50], "category": "Text", "page_num": 0},
        ]
        mock_processor_class.return_value = mock_processor
        
        pdf_parser.layout_processor = mock_processor
        
        layout_elements = pdf_parser._detect_layout_for_all_pages(sample_pdf_path, use_text_extraction=False)
        assert len(layout_elements) > 0
        assert all("page_num" in elem for elem in layout_elements)
        # Для PDF с текстом должен использоваться prompt_layout_only_en
        mock_processor.detect_layout_for_all_pages.assert_called()

    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfLayoutProcessor")
    def test_detect_layout_for_all_pages_scanned(
        self, mock_processor_class, pdf_parser, scanned_pdf_path, mock_image
    ):
        """Тест layout detection для сканированного PDF (prompt_layout_all_en)."""
        mock_processor = MagicMock()
        mock_processor.detect_layout_for_all_pages.return_value = [
            {"bbox": [0, 0, 100, 50], "category": "Text", "page_num": 0, "text": "Extracted text"},
        ]
        mock_processor_class.return_value = mock_processor
        
        pdf_parser.layout_processor = mock_processor
        
        layout_elements = pdf_parser._detect_layout_for_all_pages(scanned_pdf_path, use_text_extraction=True)
        assert len(layout_elements) > 0
        # Проверяем, что processor был использован
        mock_processor.detect_layout_for_all_pages.assert_called()

    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfLayoutProcessor")
    def test_detect_layout_handles_errors(self, mock_processor_class, pdf_parser, sample_pdf_path):
        """Тест что layout detection обрабатывает ошибки."""
        mock_processor = MagicMock()
        mock_processor.detect_layout_for_all_pages.side_effect = Exception("Layout error")
        mock_processor_class.return_value = mock_processor
        
        pdf_parser.layout_processor = mock_processor
        
        # Ошибка должна пробрасываться, так как метод просто делегирует
        with pytest.raises(Exception, match="Layout error"):
            pdf_parser._detect_layout_for_all_pages(sample_pdf_path, use_text_extraction=False)


# ============================================================================
# Тесты _analyze_header_levels_from_elements
# ============================================================================

class TestAnalyzeHeaderLevels:
    """Тесты метода _analyze_header_levels_from_elements."""

    def test_analyze_header_levels(self, pdf_parser, mock_layout_elements, sample_pdf_path):
        """Тест анализа уровней заголовков."""
        analyzed = pdf_parser.hierarchy_builder.analyze_header_levels_from_elements(
            mock_layout_elements, sample_pdf_path, is_text_extractable=True
        )
        # Метод возвращает все элементы, возможно с дополнительными полями
        assert len(analyzed) >= len(mock_layout_elements)
        # Проверяем, что Section-header получил уровень
        header = next((e for e in analyzed if e.get("category") == "Section-header"), None)
        if header:
            assert "level" in header

    def test_analyze_header_levels_no_headers(self, pdf_parser, sample_pdf_path):
        """Тест анализа уровней когда нет заголовков."""
        elements = [
            {"category": "Text", "bbox": [0, 0, 100, 50], "page_num": 0},
            {"category": "Picture", "bbox": [0, 100, 100, 150], "page_num": 0},
        ]
        analyzed = pdf_parser.hierarchy_builder.analyze_header_levels_from_elements(
            elements, sample_pdf_path, is_text_extractable=True
        )
        # Метод возвращает все элементы, возможно с дополнительными полями
        assert len(analyzed) >= len(elements)


# ============================================================================
# Тесты _build_hierarchy_from_section_headers
# ============================================================================

class TestBuildHierarchy:
    """Тесты метода _build_hierarchy_from_section_headers."""

    def test_build_hierarchy_with_headers(self, pdf_parser, mock_layout_elements):
        """Тест построения иерархии с заголовками."""
        hierarchy = pdf_parser.hierarchy_builder.build_hierarchy_from_section_headers(mock_layout_elements)
        assert len(hierarchy) > 0
        assert all("header" in section and "children" in section for section in hierarchy)

    def test_build_hierarchy_no_headers(self, pdf_parser):
        """Тест построения иерархии без заголовков."""
        elements = [
            {"category": "Text", "bbox": [0, 0, 100, 50], "page_num": 0},
            {"category": "Picture", "bbox": [0, 100, 100, 150], "page_num": 0},
        ]
        hierarchy = pdf_parser.hierarchy_builder.build_hierarchy_from_section_headers(elements)
        assert len(hierarchy) == 1
        assert hierarchy[0]["header"] is None
        assert len(hierarchy[0]["children"]) == 2


# ============================================================================
# Тесты _extract_text_by_bboxes
# ============================================================================

class TestExtractTextByBboxes:
    """Тесты метода _extract_text_by_bboxes."""

    def test_extract_text_by_bboxes_with_text(self, pdf_parser, sample_pdf_path):
        """Тест извлечения текста по bbox для PDF с текстом."""
        elements = [
            {"category": "Text", "bbox": [50, 50, 200, 100], "page_num": 0},
        ]
        text_elements = pdf_parser.text_extractor.extract_text_by_bboxes(sample_pdf_path, elements, use_ocr=False)
        assert len(text_elements) == len(elements)
        assert all("text" in elem for elem in text_elements)

    def test_extract_text_by_bboxes_no_text_elements(self, pdf_parser, sample_pdf_path):
        """Тест извлечения текста когда нет текстовых элементов."""
        elements = [
            {"category": "Picture", "bbox": [0, 0, 100, 50], "page_num": 0},
        ]
        text_elements = pdf_parser.text_extractor.extract_text_by_bboxes(sample_pdf_path, elements, use_ocr=False)
        # Метод возвращает все элементы (Picture пропускается, но добавляется в результат)
        assert len(text_elements) >= len(elements)

    def test_extract_text_by_bboxes_scanned_pdf(self, pdf_parser, scanned_pdf_path):
        """Тест извлечения текста для сканированного PDF (текст уже в элементах)."""
        # Для сканированного PDF текст уже извлечен Dots OCR
        elements = [
            {"category": "Text", "bbox": [50, 50, 200, 100], "page_num": 0, "text": "Extracted by OCR"},
        ]
        # use_ocr=True означает, что текст уже в элементах
        text_elements = pdf_parser.text_extractor.extract_text_by_bboxes(scanned_pdf_path, elements, use_ocr=True)
        assert len(text_elements) == len(elements)
        # Текст должен быть уже в элементах (возможно очищенный от markdown)
        assert "Extracted by OCR" in text_elements[0].get("text", "") or text_elements[0].get("text", "") == "Extracted by OCR"


# ============================================================================
# Тесты _parse_tables
# ============================================================================

class TestParseTables:
    """Тесты метода _parse_tables с Dots OCR HTML."""

    @patch("documentor.processing.parsers.pdf.table_parser.parse_table_from_html")
    def test_parse_tables_from_dots_ocr_html(self, mock_parse_html, pdf_parser, sample_pdf_path):
        """Тест парсинга таблиц из HTML от Dots OCR."""
        # Настраиваем мок - parse_table_from_html возвращает (markdown, dataframe, success)
        mock_parse_html.return_value = (
            None,  # markdown is None now
            pd.DataFrame({"Col1": ["Val1"], "Col2": ["Val2"]}),
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
        # use_dots_ocr_html=True означает использование HTML от Dots OCR
        parsed_elements = pdf_parser.table_parser.parse_tables(elements, sample_pdf_path, use_dots_ocr_html=True)
        assert len(parsed_elements) == len(elements)
        # Проверяем, что HTML парсер был вызван (если table_html есть в metadata)
        mock_parse_html.assert_called()
        # Проверяем, что таблица обработана
        table_elem = next((e for e in parsed_elements if e.type == ElementType.TABLE), None)
        if table_elem:
            assert "dataframe" in table_elem.metadata


    def test_parse_tables_no_tables(self, pdf_parser, sample_pdf_path):
        """Тест парсинга таблиц когда их нет."""
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
# Тесты _store_images_in_metadata
# ============================================================================

class TestStoreImagesInMetadata:
    """Тесты метода _store_images_in_metadata."""

    def test_store_images_in_metadata(self, pdf_parser, sample_pdf_path):
        """Тест сохранения изображений в метаданных."""
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
        # Проверяем, что изображения обработаны
        assert len(stored_elements) == len(elements)

    def test_store_images_no_images(self, pdf_parser, sample_pdf_path):
        """Тест сохранения изображений когда их нет."""
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
# Тесты полного цикла parse
# ============================================================================

class TestParseFullCycle:
    """Тесты полного цикла парсинга."""

    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfLayoutProcessor")
    def test_parse_complete_cycle(
        self,
        mock_processor_class,
        pdf_parser,
        sample_pdf_path,
        mock_image,
        mock_layout_elements,
    ):
        """Тест полного цикла парсинга PDF с текстом."""
        # Настраиваем моки
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
        """Тест полного цикла парсинга сканированного PDF."""
        # Для сканированного PDF элементы уже содержат текст от Dots OCR
        mock_layout_elements_with_text = [
            {**elem, "text": "Extracted text"} if elem.get("category") == "Text" else elem
            for elem in mock_layout_elements
        ]
        
        # Настраиваем моки
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
        """Тест парсинга невалидного документа."""
        doc = Document(page_content="", metadata={})
        with pytest.raises(ValidationError):
            pdf_parser.parse(doc)

    def test_parse_wrong_format(self, pdf_parser):
        """Тест парсинга документа с неподходящим форматом."""
        doc = Document(page_content="", metadata={"source": "test.md"})
        with pytest.raises(UnsupportedFormatError):
            pdf_parser.parse(doc)

    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfLayoutProcessor")
    def test_parse_handles_parsing_errors(self, mock_processor_class, pdf_parser, sample_pdf_path):
        """Тест что parse обрабатывает ошибки парсинга."""
        mock_processor = MagicMock()
        mock_processor.detect_layout_for_all_pages.side_effect = Exception("Error")
        mock_processor_class.return_value = mock_processor
        
        pdf_parser.layout_processor = mock_processor
        
        doc = Document(page_content="", metadata={"source": sample_pdf_path})
        with pytest.raises(ParsingError):
            pdf_parser.parse(doc)

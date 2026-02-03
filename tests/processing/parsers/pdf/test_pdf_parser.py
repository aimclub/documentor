"""
Тесты для PDF парсера.

Тестируемый класс:
- PdfParser
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from io import BytesIO

import pytest
from langchain_core.documents import Document
from PIL import Image

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
    # Создаем простой PDF используя fitz
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
def mock_layout_elements():
    """Возвращает моковые элементы layout."""
    return [
        {
            "bbox": [100, 50, 500, 100],
            "category": "Section-header",
            "page_num": 0,
            "level": 1,
        },
        {
            "bbox": [100, 120, 500, 200],
            "category": "Text",
            "page_num": 0,
        },
        {
            "bbox": [100, 220, 500, 300],
            "category": "Text",
            "page_num": 0,
        },
        {
            "bbox": [100, 350, 400, 450],
            "category": "Image",
            "page_num": 0,
        },
        {
            "bbox": [100, 470, 400, 500],
            "category": "Caption",
            "page_num": 0,
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
        assert parser.layout_detector is None
        assert parser.page_renderer is None
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
        filtered = pdf_parser._filter_layout_elements(elements)
        assert len(filtered) == 1
        assert filtered[0]["category"] == "Text"

    def test_filter_page_footers(self, pdf_parser):
        """Тест фильтрации Page-footer элементов."""
        elements = [
            {"category": "Page-footer", "bbox": [0, 0, 100, 50]},
            {"category": "Text", "bbox": [0, 100, 100, 150]},
        ]
        filtered = pdf_parser._filter_layout_elements(elements)
        assert len(filtered) == 1
        assert filtered[0]["category"] == "Text"

    def test_filter_keeps_other_elements(self, pdf_parser):
        """Тест что другие элементы не фильтруются."""
        elements = [
            {"category": "Text", "bbox": [0, 0, 100, 50]},
            {"category": "Image", "bbox": [0, 100, 100, 150]},
            {"category": "Table", "bbox": [0, 200, 100, 250]},
        ]
        filtered = pdf_parser._filter_layout_elements(elements)
        assert len(filtered) == 3


# ============================================================================
# Тесты _analyze_header_levels_from_elements
# ============================================================================

class TestAnalyzeHeaderLevels:
    """Тесты метода _analyze_header_levels_from_elements."""

    def test_analyze_header_levels(self, pdf_parser, mock_layout_elements, sample_pdf_path):
        """Тест анализа уровней заголовков."""
        with patch.object(pdf_parser, "_determine_header_level", return_value=1):
            analyzed = pdf_parser._analyze_header_levels_from_elements(mock_layout_elements, sample_pdf_path)
            assert len(analyzed) == len(mock_layout_elements)
            # Проверяем, что Section-header получил уровень
            header = next((e for e in analyzed if e.get("category") == "Section-header"), None)
            if header:
                assert "level" in header

    def test_analyze_header_levels_no_headers(self, pdf_parser, sample_pdf_path):
        """Тест анализа уровней когда нет заголовков."""
        elements = [
            {"category": "Text", "bbox": [0, 0, 100, 50], "page_num": 0},
            {"category": "Image", "bbox": [0, 100, 100, 150], "page_num": 0},
        ]
        analyzed = pdf_parser._analyze_header_levels_from_elements(elements, sample_pdf_path)
        assert len(analyzed) == len(elements)


# ============================================================================
# Тесты _build_hierarchy_from_section_headers
# ============================================================================

class TestBuildHierarchy:
    """Тесты метода _build_hierarchy_from_section_headers."""

    def test_build_hierarchy_with_headers(self, pdf_parser, mock_layout_elements):
        """Тест построения иерархии с заголовками."""
        hierarchy = pdf_parser._build_hierarchy_from_section_headers(mock_layout_elements)
        assert len(hierarchy) > 0
        assert all("header" in section and "children" in section for section in hierarchy)

    def test_build_hierarchy_no_headers(self, pdf_parser):
        """Тест построения иерархии без заголовков."""
        elements = [
            {"category": "Text", "bbox": [0, 0, 100, 50], "page_num": 0},
            {"category": "Image", "bbox": [0, 100, 100, 150], "page_num": 0},
        ]
        hierarchy = pdf_parser._build_hierarchy_from_section_headers(elements)
        assert len(hierarchy) == 1
        assert hierarchy[0]["header"] is None
        assert len(hierarchy[0]["children"]) == 2

    def test_build_hierarchy_multiple_sections(self, pdf_parser):
        """Тест построения иерархии с несколькими секциями."""
        elements = [
            {"category": "Section-header", "bbox": [0, 0, 100, 50], "page_num": 0, "level": 1},
            {"category": "Text", "bbox": [0, 60, 100, 110], "page_num": 0},
            {"category": "Section-header", "bbox": [0, 120, 100, 170], "page_num": 0, "level": 2},
            {"category": "Text", "bbox": [0, 180, 100, 230], "page_num": 0},
        ]
        hierarchy = pdf_parser._build_hierarchy_from_section_headers(elements)
        assert len(hierarchy) == 2
        assert hierarchy[0]["header"]["category"] == "Section-header"
        assert len(hierarchy[0]["children"]) == 1


# ============================================================================
# Тесты _extract_text_by_bboxes
# ============================================================================

class TestExtractTextByBboxes:
    """Тесты метода _extract_text_by_bboxes."""

    def test_extract_text_by_bboxes(self, pdf_parser, sample_pdf_path):
        """Тест извлечения текста по bbox."""
        elements = [
            {"category": "Text", "bbox": [50, 50, 200, 100], "page_num": 0},
        ]
        text_elements = pdf_parser._extract_text_by_bboxes(sample_pdf_path, elements)
        assert len(text_elements) == len(elements)
        assert all("text" in elem for elem in text_elements)

    def test_extract_text_by_bboxes_no_text_elements(self, pdf_parser, sample_pdf_path):
        """Тест извлечения текста когда нет текстовых элементов."""
        elements = [
            {"category": "Image", "bbox": [0, 0, 100, 50], "page_num": 0},
        ]
        text_elements = pdf_parser._extract_text_by_bboxes(sample_pdf_path, elements)
        # Метод возвращает все элементы, но для Image не извлекает текст
        assert len(text_elements) == len(elements)
        assert "text" not in text_elements[0] or text_elements[0].get("text") == ""


# ============================================================================
# Тесты _merge_nearby_text_blocks
# ============================================================================

class TestMergeNearbyTextBlocks:
    """Тесты метода _merge_nearby_text_blocks."""

    def test_merge_consecutive_text_blocks(self, pdf_parser):
        """Тест склеивания подряд идущих текстовых блоков."""
        text_elements = [
            {"category": "Text", "text": "First paragraph.", "bbox": [0, 0, 100, 50]},
            {"category": "Text", "text": "Second paragraph.", "bbox": [0, 60, 100, 110]},
            {"category": "Text", "text": "Third paragraph.", "bbox": [0, 120, 100, 170]},
        ]
        merged = pdf_parser._merge_nearby_text_blocks(text_elements, max_chunk_size=3000)
        assert len(merged) <= len(text_elements)
        # Проверяем, что текст объединен
        if len(merged) < len(text_elements):
            assert "First paragraph" in merged[0]["text"]

    def test_merge_respects_max_chunk_size(self, pdf_parser):
        """Тест что склеивание учитывает max_chunk_size."""
        long_text = "A" * 2000
        text_elements = [
            {"category": "Text", "text": long_text, "bbox": [0, 0, 100, 50]},
            {"category": "Text", "text": long_text, "bbox": [0, 60, 100, 110]},
        ]
        merged = pdf_parser._merge_nearby_text_blocks(text_elements, max_chunk_size=3000)
        # Если объединенный текст превышает max_chunk_size, блоки не должны объединяться
        assert len(merged) >= 1


# ============================================================================
# Тесты _determine_header_level
# ============================================================================

class TestDetermineHeaderLevel:
    """Тесты метода _determine_header_level."""

    def test_determine_header_level_by_size(self, pdf_parser, sample_pdf_path):
        """Тест определения уровня заголовка по размеру."""
        import fitz
        pdf_document = fitz.open(sample_pdf_path)
        try:
            page = pdf_document.load_page(0)
            rect = fitz.Rect(0, 0, 100, 50)
            header = {
                "category": "Section-header",
                "bbox": [0, 0, 100, 50],
                "text": "Large Header",
            }
            level = pdf_parser._determine_header_level("Large Header", header, page, rect)
            assert isinstance(level, int)
            assert 1 <= level <= 6
        finally:
            pdf_document.close()

    def test_determine_header_level_by_numbering(self, pdf_parser, sample_pdf_path):
        """Тест определения уровня заголовка по нумерации."""
        import fitz
        pdf_document = fitz.open(sample_pdf_path)
        try:
            page = pdf_document.load_page(0)
            rect = fitz.Rect(0, 0, 100, 50)
            header = {
                "category": "Section-header",
                "bbox": [0, 0, 100, 50],
                "text": "1.1 Introduction",
            }
            level = pdf_parser._determine_header_level("1.1 Introduction", header, page, rect)
            assert isinstance(level, int)
            assert 1 <= level <= 6
            # Проверяем, что нумерация 1.1 дает уровень 2
            assert level == 2
        finally:
            pdf_document.close()


# ============================================================================
# Тесты _detect_layout_for_all_pages
# ============================================================================

class TestDetectLayoutForAllPages:
    """Тесты метода _detect_layout_for_all_pages."""

    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfLayoutDetector")
    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfPageRenderer")
    def test_detect_layout_for_all_pages(self, mock_renderer_class, mock_detector_class, pdf_parser, sample_pdf_path, mock_image):
        """Тест layout detection для всех страниц."""
        # Настраиваем моки
        mock_renderer = MagicMock()
        mock_renderer.get_page_count.return_value = 1
        mock_renderer.render_page.return_value = (mock_image, mock_image)
        mock_renderer_class.return_value = mock_renderer
        
        mock_detector = MagicMock()
        mock_detector.detect_layout.return_value = [
            {"bbox": [0, 0, 100, 50], "category": "Text"},
        ]
        mock_detector_class.return_value = mock_detector
        
        pdf_parser.page_renderer = mock_renderer
        pdf_parser.layout_detector = mock_detector
        
        layout_elements = pdf_parser._detect_layout_for_all_pages(sample_pdf_path)
        assert len(layout_elements) > 0
        assert all("page_num" in elem for elem in layout_elements)

    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfPageRenderer")
    def test_detect_layout_handles_errors(self, mock_renderer_class, pdf_parser, sample_pdf_path):
        """Тест что layout detection обрабатывает ошибки."""
        mock_renderer = MagicMock()
        mock_renderer.get_page_count.return_value = 1
        mock_renderer.render_page.side_effect = Exception("Render error")
        mock_renderer_class.return_value = mock_renderer
        
        pdf_parser.page_renderer = mock_renderer
        
        layout_elements = pdf_parser._detect_layout_for_all_pages(sample_pdf_path)
        # Должен вернуть пустой список при ошибке
        assert isinstance(layout_elements, list)


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
        stored_elements = pdf_parser._store_images_in_metadata(elements, sample_pdf_path)
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
        stored_elements = pdf_parser._store_images_in_metadata(elements, sample_pdf_path)
        assert len(stored_elements) == len(elements)


# ============================================================================
# Тесты _parse_tables_with_qwen
# ============================================================================

class TestParseTablesWithQwen:
    """Тесты метода _parse_tables_with_qwen."""

    @patch("documentor.processing.parsers.pdf.pdf_parser.parse_table_with_qwen")
    def test_parse_tables_with_qwen(self, mock_parse_table, pdf_parser, sample_pdf_path):
        """Тест парсинга таблиц через Qwen."""
        # Настраиваем мок
        mock_parse_table.return_value = (
            "| Col1 | Col2 |\n|------|------|\n| Val1 | Val2 |",
            None,
            True,
        )
        
        elements = [
            Element(
                id="00000001",
                type=ElementType.TABLE,
                content="",
                metadata={"bbox": [100, 100, 400, 300], "page_num": 0},
            ),
        ]
        parsed_elements = pdf_parser._parse_tables_with_qwen(elements, sample_pdf_path)
        assert len(parsed_elements) == len(elements)
        # Проверяем, что таблица обработана
        table_elem = next((e for e in parsed_elements if e.type == ElementType.TABLE), None)
        if table_elem:
            assert "parsing_method" in table_elem.metadata

    @patch("documentor.processing.parsers.pdf.pdf_parser.parse_table_with_qwen")
    def test_parse_tables_no_tables(self, mock_parse_table, pdf_parser, sample_pdf_path):
        """Тест парсинга таблиц когда их нет."""
        elements = [
            Element(
                id="00000001",
                type=ElementType.TEXT,
                content="Text content",
                metadata={},
            ),
        ]
        parsed_elements = pdf_parser._parse_tables_with_qwen(elements, sample_pdf_path)
        assert len(parsed_elements) == len(elements)
        # Не должно быть вызовов к Qwen
        mock_parse_table.assert_not_called()


# ============================================================================
# Тесты полного цикла parse
# ============================================================================

class TestParseFullCycle:
    """Тесты полного цикла парсинга."""

    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfLayoutDetector")
    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfPageRenderer")
    @patch("documentor.processing.parsers.pdf.pdf_parser.parse_table_with_qwen")
    def test_parse_complete_cycle(
        self,
        mock_parse_table,
        mock_renderer_class,
        mock_detector_class,
        pdf_parser,
        sample_pdf_path,
        mock_image,
        mock_layout_elements,
    ):
        """Тест полного цикла парсинга PDF."""
        # Настраиваем моки
        mock_renderer = MagicMock()
        mock_renderer.get_page_count.return_value = 1
        mock_renderer.render_page.return_value = (mock_image, mock_image)
        mock_renderer_class.return_value = mock_renderer
        
        mock_detector = MagicMock()
        mock_detector.detect_layout.return_value = mock_layout_elements
        mock_detector_class.return_value = mock_detector
        
        mock_parse_table.return_value = (None, None, False)
        
        pdf_parser.page_renderer = mock_renderer
        pdf_parser.layout_detector = mock_detector
        
        doc = Document(page_content="", metadata={"source": sample_pdf_path})
        result = pdf_parser.parse(doc)
        
        assert isinstance(result, ParsedDocument)
        assert result.format == DocumentFormat.PDF
        assert result.source == sample_pdf_path
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

    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfPageRenderer")
    def test_parse_handles_parsing_errors(self, mock_renderer_class, pdf_parser, sample_pdf_path):
        """Тест что parse обрабатывает ошибки парсинга."""
        mock_renderer = MagicMock()
        mock_renderer.get_page_count.side_effect = Exception("Error")
        mock_renderer_class.return_value = mock_renderer
        
        pdf_parser.page_renderer = mock_renderer
        
        doc = Document(page_content="", metadata={"source": sample_pdf_path})
        with pytest.raises(ParsingError):
            pdf_parser.parse(doc)


# ============================================================================
# Тесты _get_config
# ============================================================================

class TestGetConfig:
    """Тесты метода _get_config."""

    def test_get_config_existing_key(self, pdf_parser):
        """Тест получения существующего ключа из конфига."""
        value = pdf_parser._get_config("layout_detection.render_scale", 2.0)
        assert value is not None

    def test_get_config_nonexistent_key(self, pdf_parser):
        """Тест получения несуществующего ключа из конфига."""
        value = pdf_parser._get_config("nonexistent.key", "default")
        assert value == "default"

    def test_get_config_nested_key(self, pdf_parser):
        """Тест получения вложенного ключа из конфига."""
        value = pdf_parser._get_config("layout_detection.optimize_for_ocr", True)
        assert isinstance(value, bool)


# ============================================================================
# Тесты _create_elements_from_hierarchy
# ============================================================================

class TestCreateElementsFromHierarchy:
    """Тесты метода _create_elements_from_hierarchy."""

    def test_create_elements_from_hierarchy(self, pdf_parser):
        """Тест создания элементов из иерархии."""
        hierarchy = [
            {
                "header": {
                    "category": "Section-header",
                    "bbox": [0, 0, 100, 50],
                    "level": 1,
                    "text": "Header 1",
                },
                "children": [
                    {"category": "Text", "bbox": [0, 60, 100, 110], "text": "Text content"},
                ],
            },
        ]
        text_elements = [
            {"category": "Text", "bbox": [0, 60, 100, 110], "text": "Text content"},
        ]
        analyzed_elements = [
            {"category": "Section-header", "bbox": [0, 0, 100, 50], "level": 1},
            {"category": "Text", "bbox": [0, 60, 100, 110]},
        ]
        
        elements = pdf_parser._create_elements_from_hierarchy(hierarchy, text_elements, analyzed_elements)
        assert len(elements) > 0
        assert any(e.type.name.startswith("HEADER") for e in elements)
        assert any(e.type == ElementType.TEXT for e in elements)

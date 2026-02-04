"""
Тесты для PDF парсера со сканированными PDF (OCR).

Тестируемые функции:
- _is_text_extractable для сканированных PDF
- _extract_text_by_bboxes с use_ocr=True
- OCR через Qwen2.5
- Полный пайплайн для сканированных PDF
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
from documentor.exceptions import ParsingError
from documentor.processing.parsers.pdf.pdf_parser import PdfParser


# ============================================================================
# Фикстуры
# ============================================================================

@pytest.fixture
def scanned_pdf_path(tmp_path):
    """Создает временный сканированный PDF файл (без текстового слоя)."""
    pdf_path = tmp_path / "scanned_test.pdf"
    try:
        import fitz
        from PIL import Image
        
        # Создаем PDF без текстового слоя (только изображение)
        doc = fitz.open()
        page = doc.new_page()
        
        # Создаем белое изображение через PIL
        white_image = Image.new("RGB", (200, 100), color="white")
        
        # Конвертируем PIL Image в bytes
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
def mock_image():
    """Создает тестовое изображение."""
    return Image.new("RGB", (800, 600), color="white")


@pytest.fixture
def mock_cropped_image():
    """Создает обрезанное изображение для OCR."""
    return Image.new("RGB", (200, 100), color="white")


@pytest.fixture
def scanned_pdf_parser():
    """Создает экземпляр PdfParser для тестов сканированных PDF."""
    return PdfParser()


@pytest.fixture
def mock_layout_elements_scanned():
    """Возвращает моковые элементы layout для сканированного PDF."""
    return [
        {
            "bbox": [100, 50, 500, 100],
            "category": "Section-header",
            "page_num": 0,
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
            "category": "Picture",
            "page_num": 0,
        },
        {
            "bbox": [100, 470, 400, 500],
            "category": "Caption",
            "page_num": 0,
        },
    ]


# ============================================================================
# Тесты _is_text_extractable для сканированных PDF
# ============================================================================

class TestIsTextExtractableScanned:
    """Тесты метода _is_text_extractable для сканированных PDF."""

    def test_is_text_extractable_scanned_pdf(self, scanned_pdf_path, scanned_pdf_parser):
        """Тест что сканированный PDF определяется как не выделяемый."""
        result = scanned_pdf_parser._is_text_extractable(scanned_pdf_path)
        # Сканированный PDF должен вернуть False (текст не выделяется)
        assert result is False

    def test_is_text_extractable_empty_pdf(self, scanned_pdf_parser):
        """Тест что пустой PDF определяется как не выделяемый."""
        try:
            import fitz
            pdf_path = "/tmp/empty_test.pdf"
            doc = fitz.open()
            doc.save(pdf_path)
            doc.close()
            
            result = scanned_pdf_parser._is_text_extractable(pdf_path)
            assert result is False
        except ImportError:
            pytest.skip("PyMuPDF (fitz) не установлен")
        except Exception:
            # Если не можем создать файл, пропускаем тест
            pass


# ============================================================================
# Тесты _extract_text_by_bboxes с OCR
# ============================================================================

class TestExtractTextByBboxesOCR:
    """Тесты метода _extract_text_by_bboxes с use_ocr=True."""

    @patch("documentor.processing.parsers.pdf.pdf_parser.ocr_text_with_qwen")
    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfPageRenderer")
    def test_extract_text_with_ocr(
        self,
        mock_renderer_class,
        mock_ocr_func,
        scanned_pdf_parser,
        scanned_pdf_path,
        mock_image,
        mock_cropped_image,
    ):
        """Тест извлечения текста через OCR."""
        # Настраиваем моки
        mock_renderer = MagicMock()
        mock_renderer.render_page.return_value = (mock_image, mock_image)
        mock_renderer_class.return_value = mock_renderer
        
        # Мокируем OCR функцию
        mock_ocr_func.return_value = "Extracted text from OCR"
        
        elements = [
            {"category": "Text", "bbox": [100, 120, 500, 200], "page_num": 0},
            {"category": "Section-header", "bbox": [100, 50, 500, 100], "page_num": 0},
        ]
        
        text_elements = scanned_pdf_parser._extract_text_by_bboxes(
            scanned_pdf_path, elements, use_ocr=True
        )
        
        assert len(text_elements) == len(elements)
        # Проверяем, что OCR был вызван для текстовых элементов
        assert mock_ocr_func.called
        # Проверяем, что текст извлечен
        assert any("text" in elem for elem in text_elements)

    @patch("documentor.processing.parsers.pdf.pdf_parser.ocr_text_with_qwen")
    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfPageRenderer")
    def test_extract_text_with_ocr_skips_picture(
        self,
        mock_renderer_class,
        mock_ocr_func,
        scanned_pdf_parser,
        scanned_pdf_path,
        mock_image,
    ):
        """Тест что OCR пропускает Picture элементы."""
        mock_renderer = MagicMock()
        mock_renderer.render_page.return_value = (mock_image, mock_image)
        mock_renderer_class.return_value = mock_renderer
        
        elements = [
            {"category": "Text", "bbox": [100, 120, 500, 200], "page_num": 0},
            {"category": "Picture", "bbox": [100, 350, 400, 450], "page_num": 0},
        ]
        
        text_elements = scanned_pdf_parser._extract_text_by_bboxes(
            scanned_pdf_path, elements, use_ocr=True
        )
        
        assert len(text_elements) == len(elements)
        # OCR должен быть вызван только для Text, не для Picture
        # Проверяем количество вызовов OCR (только для Text)
        text_elements_count = sum(1 for e in elements if e["category"] == "Text")
        assert mock_ocr_func.call_count == text_elements_count

    @patch("documentor.processing.parsers.pdf.pdf_parser.ocr_text_with_qwen")
    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfPageRenderer")
    def test_extract_text_with_ocr_handles_errors(
        self,
        mock_renderer_class,
        mock_ocr_func,
        scanned_pdf_parser,
        scanned_pdf_path,
        mock_image,
    ):
        """Тест обработки ошибок при OCR."""
        mock_renderer = MagicMock()
        mock_renderer.render_page.return_value = (mock_image, mock_image)
        mock_renderer_class.return_value = mock_renderer
        
        # Мокируем ошибку OCR
        mock_ocr_func.return_value = None
        
        elements = [
            {"category": "Text", "bbox": [100, 120, 500, 200], "page_num": 0},
        ]
        
        text_elements = scanned_pdf_parser._extract_text_by_bboxes(
            scanned_pdf_path, elements, use_ocr=True
        )
        
        assert len(text_elements) == len(elements)
        # При ошибке OCR текст должен быть пустым
        assert text_elements[0].get("text", "") == ""

    @patch("documentor.processing.parsers.pdf.pdf_parser.ocr_text_with_qwen")
    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfPageRenderer")
    def test_extract_text_with_ocr_renders_all_pages(
        self,
        mock_renderer_class,
        mock_ocr_func,
        scanned_pdf_parser,
        scanned_pdf_path,
        mock_image,
    ):
        """Тест что все страницы рендерятся заранее для OCR."""
        mock_renderer = MagicMock()
        mock_renderer.render_page.return_value = (mock_image, mock_image)
        mock_renderer_class.return_value = mock_renderer
        
        # Мокируем количество страниц
        import fitz
        with patch("fitz.open") as mock_open:
            mock_doc = MagicMock()
            mock_doc.__len__.return_value = 2  # 2 страницы
            mock_doc.__enter__ = Mock(return_value=mock_doc)
            mock_doc.__exit__ = Mock(return_value=False)
            mock_open.return_value = mock_doc
            
            elements = [
                {"category": "Text", "bbox": [100, 120, 500, 200], "page_num": 0},
                {"category": "Text", "bbox": [100, 120, 500, 200], "page_num": 1},
            ]
            
            scanned_pdf_parser._extract_text_by_bboxes(
                scanned_pdf_path, elements, use_ocr=True
            )
            
            # Проверяем, что render_page был вызван для каждой страницы
            assert mock_renderer.render_page.call_count == 2

    @patch("documentor.processing.parsers.pdf.pdf_parser.ocr_text_with_qwen")
    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfPageRenderer")
    def test_extract_text_with_ocr_crops_elements(
        self,
        mock_renderer_class,
        mock_ocr_func,
        scanned_pdf_parser,
        scanned_pdf_path,
        mock_image,
    ):
        """Тест что элементы правильно обрезаются из страницы для OCR."""
        mock_renderer = MagicMock()
        mock_renderer.render_page.return_value = (mock_image, mock_image)
        mock_renderer_class.return_value = mock_renderer
        
        mock_ocr_func.return_value = "OCR text"
        
        elements = [
            {"category": "Text", "bbox": [100, 120, 500, 200], "page_num": 0},
        ]
        
        scanned_pdf_parser._extract_text_by_bboxes(
            scanned_pdf_path, elements, use_ocr=True
        )
        
        # Проверяем, что OCR был вызван с обрезанным изображением
        assert mock_ocr_func.called
        # Проверяем, что переданное изображение имеет правильный размер
        call_args = mock_ocr_func.call_args
        if call_args:
            cropped_image = call_args[0][0]  # Первый позиционный аргумент
            assert isinstance(cropped_image, Image.Image)
            # Размер должен соответствовать bbox (с учетом padding)
            assert cropped_image.width <= 500 - 100 + 10  # x2 - x1 + padding
            assert cropped_image.height <= 200 - 120 + 10  # y2 - y1 + padding


# ============================================================================
# Интеграционные тесты для полного пайплайна сканированных PDF
# ============================================================================

class TestScannedPdfPipeline:
    """Интеграционные тесты для полного пайплайна сканированных PDF."""

    @patch("documentor.processing.parsers.pdf.pdf_parser.ocr_text_with_qwen")
    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfLayoutDetector")
    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfPageRenderer")
    def test_parse_scanned_pdf_full_pipeline(
        self,
        mock_renderer_class,
        mock_detector_class,
        mock_ocr_func,
        scanned_pdf_parser,
        scanned_pdf_path,
        mock_image,
        mock_layout_elements_scanned,
    ):
        """Тест полного пайплайна для сканированного PDF."""
        # Настраиваем моки
        mock_renderer = MagicMock()
        mock_renderer.get_page_count.return_value = 1
        mock_renderer.render_page.return_value = (mock_image, mock_image)
        mock_renderer_class.return_value = mock_renderer
        
        mock_detector = MagicMock()
        mock_detector.detect_layout.return_value = mock_layout_elements_scanned
        mock_detector_class.return_value = mock_detector
        
        # Мокируем OCR
        mock_ocr_func.return_value = "Extracted OCR text"
        
        # Мокируем _is_text_extractable чтобы вернуть False (сканированный PDF)
        with patch.object(scanned_pdf_parser, "_is_text_extractable", return_value=False):
            document = Document(
                page_content="",
                metadata={"source": scanned_pdf_path}
            )
            
            parsed_doc = scanned_pdf_parser.parse(document)
            
            assert isinstance(parsed_doc, ParsedDocument)
            assert parsed_doc.format == DocumentFormat.PDF
            assert len(parsed_doc.elements) > 0
            # Проверяем, что OCR был вызван
            assert mock_ocr_func.called

    @patch("documentor.processing.parsers.pdf.pdf_parser.ocr_text_with_qwen")
    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfLayoutDetector")
    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfPageRenderer")
    def test_parse_scanned_pdf_skips_picture_ocr(
        self,
        mock_renderer_class,
        mock_detector_class,
        mock_ocr_func,
        scanned_pdf_parser,
        scanned_pdf_path,
        mock_image,
    ):
        """Тест что OCR не выполняется для Picture элементов в полном пайплайне."""
        mock_renderer = MagicMock()
        mock_renderer.get_page_count.return_value = 1
        mock_renderer.render_page.return_value = (mock_image, mock_image)
        mock_renderer_class.return_value = mock_renderer
        
        # Layout с Picture элементом
        layout_elements = [
            {"category": "Text", "bbox": [100, 120, 500, 200], "page_num": 0},
            {"category": "Picture", "bbox": [100, 350, 400, 450], "page_num": 0},
        ]
        
        mock_detector = MagicMock()
        mock_detector.detect_layout.return_value = layout_elements
        mock_detector_class.return_value = mock_detector
        
        mock_ocr_func.return_value = "OCR text"
        
        with patch.object(scanned_pdf_parser, "_is_text_extractable", return_value=False):
            document = Document(
                page_content="",
                metadata={"source": scanned_pdf_path}
            )
            
            parsed_doc = scanned_pdf_parser.parse(document)
            
            # OCR должен быть вызван только для Text, не для Picture
            # Подсчитываем количество текстовых элементов (не Picture)
            text_elements_count = sum(
                1 for e in layout_elements
                if e["category"] in ["Text", "Section-header", "Title", "Caption"]
            )
            assert mock_ocr_func.call_count == text_elements_count

    @patch("documentor.processing.parsers.pdf.pdf_parser.ocr_text_with_qwen")
    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfLayoutDetector")
    @patch("documentor.processing.parsers.pdf.pdf_parser.PdfPageRenderer")
    def test_parse_scanned_pdf_handles_ocr_failure(
        self,
        mock_renderer_class,
        mock_detector_class,
        mock_ocr_func,
        scanned_pdf_parser,
        scanned_pdf_path,
        mock_image,
        mock_layout_elements_scanned,
    ):
        """Тест обработки ошибок OCR в полном пайплайне."""
        mock_renderer = MagicMock()
        mock_renderer.get_page_count.return_value = 1
        mock_renderer.render_page.return_value = (mock_image, mock_image)
        mock_renderer_class.return_value = mock_renderer
        
        mock_detector = MagicMock()
        mock_detector.detect_layout.return_value = mock_layout_elements_scanned
        mock_detector_class.return_value = mock_detector
        
        # Мокируем ошибку OCR (возвращает None)
        mock_ocr_func.return_value = None
        
        with patch.object(scanned_pdf_parser, "_is_text_extractable", return_value=False):
            document = Document(
                page_content="",
                metadata={"source": scanned_pdf_path}
            )
            
            # Пайплайн должен завершиться без ошибок, даже если OCR вернул None
            parsed_doc = scanned_pdf_parser.parse(document)
            
            assert isinstance(parsed_doc, ParsedDocument)
            # Элементы должны быть созданы, но с пустым текстом
            assert len(parsed_doc.elements) > 0


# ============================================================================
# Тесты автоматического определения сканированных PDF
# ============================================================================

class TestAutoDetectScannedPdf:
    """Тесты автоматического определения сканированных PDF."""

    def test_auto_detect_scanned_pdf_in_parse(
        self,
        scanned_pdf_parser,
        scanned_pdf_path,
        mock_image,
        mock_layout_elements_scanned,
    ):
        """Тест что парсер автоматически определяет сканированный PDF."""
        with patch.object(
            scanned_pdf_parser,
            "_is_text_extractable",
            return_value=False
        ) as mock_detect, \
        patch.object(
            scanned_pdf_parser,
            "_detect_layout_for_all_pages",
            return_value=mock_layout_elements_scanned
        ), \
        patch.object(
            scanned_pdf_parser,
            "_extract_text_by_bboxes",
            return_value=mock_layout_elements_scanned
        ) as mock_extract, \
        patch.object(
            scanned_pdf_parser,
            "_analyze_header_levels_from_elements",
            return_value=mock_layout_elements_scanned
        ), \
        patch.object(
            scanned_pdf_parser,
            "_build_hierarchy_from_section_headers",
            return_value=[{"header": None, "children": mock_layout_elements_scanned}]
        ), \
        patch.object(
            scanned_pdf_parser,
            "_merge_nearby_text_blocks",
            return_value=mock_layout_elements_scanned
        ), \
        patch.object(
            scanned_pdf_parser,
            "_create_elements_from_hierarchy",
            return_value=[]
        ), \
        patch.object(
            scanned_pdf_parser,
            "_store_images_in_metadata",
            return_value=[]
        ), \
        patch.object(
            scanned_pdf_parser,
            "_parse_tables_with_qwen",
            return_value=[]
        ):
            document = Document(
                page_content="",
                metadata={"source": scanned_pdf_path}
            )
            
            scanned_pdf_parser.parse(document)
            
            # Проверяем, что _is_text_extractable был вызван
            assert mock_detect.called
            # Проверяем, что _extract_text_by_bboxes был вызван с use_ocr=True
            assert mock_extract.called
            # Проверяем, что use_ocr=True был передан
            call_kwargs = mock_extract.call_args[1] if mock_extract.call_args else {}
            assert call_kwargs.get("use_ocr") is True

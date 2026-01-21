"""
Тесты для document loader.

Тестируемые функции:
- detect_document_format()
- get_document_source()
- validate_document()
- normalize_metadata()
"""

from __future__ import annotations

import sys
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH для прямого запуска
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import shutil
import tempfile
import pytest
from langchain_core.documents import Document

from documentor.domain import DocumentFormat
from documentor.processing.loader.loader import (
    get_document_source,
    detect_document_format,
    validate_document,
    normalize_metadata,
    _detect_format_by_extension,
    _detect_format_by_mime_type,
    _detect_format_by_magic_bytes,
)


# Фикстуры для тестовых файлов
@pytest.fixture
def test_files_dir() -> Path:
    """Возвращает путь к директории с тестовыми файлами."""
    return Path(__file__).parent.parent.parent / "files_for_tests"


@pytest.fixture
def markdown_file(test_files_dir: Path) -> Path:
    """Путь к тестовому Markdown файлу."""
    return test_files_dir / "md.md"


@pytest.fixture
def pdf_file(test_files_dir: Path) -> Path:
    """Путь к тестовому PDF файлу."""
    return test_files_dir / "pdf.pdf"


@pytest.fixture
def image_pdf_file(test_files_dir: Path) -> Path:
    """Путь к тестовому PDF файлу с изображениями."""
    return test_files_dir / "image.pdf"


@pytest.fixture
def docx_file(test_files_dir: Path) -> Path:
    """Путь к тестовому DOCX файлу."""
    return test_files_dir / "docx.docx"


class TestGetDocumentSource:
    """Тесты для функции get_document_source()."""

    def test_source_from_source_key(self):
        """Тест получения source из ключа 'source'."""
        doc = Document(
            page_content="test",
            metadata={"source": "/path/to/file.md"}
        )
        assert get_document_source(doc) == "/path/to/file.md"

    def test_source_from_file_path_key(self):
        """Тест получения source из ключа 'file_path'."""
        doc = Document(
            page_content="test",
            metadata={"file_path": "/path/to/file.pdf"}
        )
        assert get_document_source(doc) == "/path/to/file.pdf"

    def test_source_from_path_key(self):
        """Тест получения source из ключа 'path'."""
        doc = Document(
            page_content="test",
            metadata={"path": "/path/to/file.docx"}
        )
        assert get_document_source(doc) == "/path/to/file.docx"

    def test_source_from_filename_key(self):
        """Тест получения source из ключа 'filename'."""
        doc = Document(
            page_content="test",
            metadata={"filename": "/path/to/file.md"}
        )
        assert get_document_source(doc) == "/path/to/file.md"

    def test_source_from_file_name_key(self):
        """Тест получения source из ключа 'file_name'."""
        doc = Document(
            page_content="test",
            metadata={"file_name": "/path/to/file.pdf"}
        )
        assert get_document_source(doc) == "/path/to/file.pdf"

    def test_source_priority_order(self):
        """Тест приоритета ключей (source имеет наивысший приоритет)."""
        doc = Document(
            page_content="test",
            metadata={
                "source": "/correct/path.md",
                "file_path": "/wrong/path.pdf",
                "path": "/also/wrong/path.docx"
            }
        )
        assert get_document_source(doc) == "/correct/path.md"

    def test_source_unknown_when_no_metadata(self):
        """Тест возврата 'unknown' когда метаданных нет."""
        doc = Document(page_content="test", metadata={})
        assert get_document_source(doc) == "unknown"

    def test_source_unknown_when_metadata_none(self):
        """Тест возврата 'unknown' когда metadata = None."""
        # LangChain Document не позволяет metadata=None, используем пустой словарь
        doc = Document(page_content="test", metadata={})
        assert get_document_source(doc) == "unknown"

    def test_source_unknown_when_no_relevant_keys(self):
        """Тест возврата 'unknown' когда нет релевантных ключей."""
        doc = Document(
            page_content="test",
            metadata={"other_key": "/path/to/file.md"}
        )
        assert get_document_source(doc) == "unknown"


class TestDetectFormatByExtension:
    """Тесты для функции _detect_format_by_extension()."""

    def test_detect_markdown_by_md_extension(self):
        """Тест определения Markdown по расширению .md."""
        assert _detect_format_by_extension("/path/to/file.md") == DocumentFormat.MARKDOWN

    def test_detect_markdown_by_markdown_extension(self):
        """Тест определения Markdown по расширению .markdown."""
        assert _detect_format_by_extension("/path/to/file.markdown") == DocumentFormat.MARKDOWN

    def test_detect_pdf_by_extension(self):
        """Тест определения PDF по расширению."""
        assert _detect_format_by_extension("/path/to/file.pdf") == DocumentFormat.PDF

    def test_detect_docx_by_extension(self):
        """Тест определения DOCX по расширению."""
        assert _detect_format_by_extension("/path/to/file.docx") == DocumentFormat.DOCX

    def test_case_insensitive_extension(self):
        """Тест нечувствительности к регистру расширения."""
        assert _detect_format_by_extension("/path/to/FILE.PDF") == DocumentFormat.PDF
        assert _detect_format_by_extension("/path/to/FILE.DOCX") == DocumentFormat.DOCX

    def test_unknown_extension_returns_none(self):
        """Тест возврата None для неизвестного расширения."""
        assert _detect_format_by_extension("/path/to/file.txt") is None
        assert _detect_format_by_extension("/path/to/file") is None

    def test_no_extension_returns_none(self):
        """Тест возврата None для файла без расширения."""
        assert _detect_format_by_extension("/path/to/file") is None


class TestDetectFormatByMimeType:
    """Тесты для функции _detect_format_by_mime_type()."""

    def test_detect_pdf_by_mime_type(self):
        """Тест определения PDF по MIME типу."""
        metadata = {"mime_type": "application/pdf"}
        assert _detect_format_by_mime_type(metadata) == DocumentFormat.PDF

    def test_detect_docx_by_mime_type(self):
        """Тест определения DOCX по MIME типу."""
        metadata = {"mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
        assert _detect_format_by_mime_type(metadata) == DocumentFormat.DOCX

    def test_detect_docx_template_by_mime_type(self):
        """Тест определения DOCX template по MIME типу."""
        metadata = {"mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.template"}
        assert _detect_format_by_mime_type(metadata) == DocumentFormat.DOCX

    def test_detect_markdown_by_mime_type(self):
        """Тест определения Markdown по MIME типу."""
        metadata = {"mime_type": "text/markdown"}
        assert _detect_format_by_mime_type(metadata) == DocumentFormat.MARKDOWN

    def test_detect_markdown_by_alternative_mime_type(self):
        """Тест определения Markdown по альтернативному MIME типу."""
        metadata = {"mime_type": "text/x-markdown"}
        assert _detect_format_by_mime_type(metadata) == DocumentFormat.MARKDOWN

    def test_unknown_mime_type_returns_none(self):
        """Тест возврата None для неизвестного MIME типа."""
        metadata = {"mime_type": "text/plain"}
        assert _detect_format_by_mime_type(metadata) is None

    def test_no_mime_type_returns_none(self):
        """Тест возврата None когда MIME типа нет."""
        metadata = {}
        assert _detect_format_by_mime_type(metadata) is None

    def test_empty_mime_type_returns_none(self):
        """Тест возврата None для пустого MIME типа."""
        metadata = {"mime_type": ""}
        assert _detect_format_by_mime_type(metadata) is None


class TestDetectFormatByMagicBytes:
    """Тесты для функции _detect_format_by_magic_bytes()."""

    def test_detect_pdf_by_magic_bytes(self, pdf_file: Path):
        """Тест определения PDF по magic bytes."""
        assert _detect_format_by_magic_bytes(str(pdf_file)) == DocumentFormat.PDF

    def test_detect_pdf_image_by_magic_bytes(self, image_pdf_file: Path):
        """Тест определения PDF с изображениями по magic bytes."""
        assert _detect_format_by_magic_bytes(str(image_pdf_file)) == DocumentFormat.PDF

    def test_detect_docx_by_magic_bytes(self, docx_file: Path):
        """Тест определения DOCX по magic bytes."""
        assert _detect_format_by_magic_bytes(str(docx_file)) == DocumentFormat.DOCX

    def test_nonexistent_file_returns_none(self):
        """Тест возврата None для несуществующего файла."""
        assert _detect_format_by_magic_bytes("/nonexistent/file.pdf") is None

    def test_directory_returns_none(self, test_files_dir: Path):
        """Тест возврата None для директории."""
        assert _detect_format_by_magic_bytes(str(test_files_dir)) is None

    def test_markdown_returns_none(self, markdown_file: Path):
        """Тест возврата None для Markdown (нет magic bytes для текстовых файлов)."""
        # Markdown - текстовый файл, magic bytes не определяются
        result = _detect_format_by_magic_bytes(str(markdown_file))
        # Может быть None или может быть определен по-другому
        assert result is None or result == DocumentFormat.UNKNOWN


class TestDetectDocumentFormat:
    """Тесты для функции detect_document_format()."""

    def test_detect_markdown_by_extension(self, markdown_file: Path):
        """Тест определения Markdown по расширению."""
        doc = Document(
            page_content="# Test",
            metadata={"source": str(markdown_file)}
        )
        assert detect_document_format(doc) == DocumentFormat.MARKDOWN

    def test_detect_pdf_by_extension(self, pdf_file: Path):
        """Тест определения PDF по расширению."""
        doc = Document(
            page_content="PDF content",
            metadata={"source": str(pdf_file)}
        )
        assert detect_document_format(doc) == DocumentFormat.PDF

    def test_detect_docx_by_extension(self, docx_file: Path):
        """Тест определения DOCX по расширению."""
        doc = Document(
            page_content="DOCX content",
            metadata={"source": str(docx_file)}
        )
        assert detect_document_format(doc) == DocumentFormat.DOCX

    def test_detect_by_mime_type_when_no_extension(self):
        """Тест определения формата по MIME типу когда нет расширения."""
        doc = Document(
            page_content="PDF content",
            metadata={
                "source": "/path/to/file",
                "mime_type": "application/pdf"
            }
        )
        assert detect_document_format(doc) == DocumentFormat.PDF

    def test_detect_by_magic_bytes_when_no_extension_or_mime(self, pdf_file: Path):
        """Тест определения формата по magic bytes когда нет расширения и MIME типа."""
        # Используем реальный путь к файлу, но без расширения в метаданных
        # Создаём временный файл без расширения, копируя содержимое PDF
        tmp_dir = tempfile.gettempdir()
        tmp_path = Path(tmp_dir) / f"test_pdf_{tempfile.gettempprefix()}"
        try:
            shutil.copy(pdf_file, tmp_path)
            doc = Document(
                page_content="PDF content",
                metadata={"source": str(tmp_path)}
            )
            # Должен определить по magic bytes
            assert detect_document_format(doc) == DocumentFormat.PDF
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_priority_extension_over_mime_type(self, markdown_file: Path):
        """Тест приоритета расширения над MIME типом."""
        doc = Document(
            page_content="# Test",
            metadata={
                "source": str(markdown_file),
                "mime_type": "application/pdf"  # Неправильный MIME тип
            }
        )
        # Должен определить по расширению, игнорируя MIME тип
        assert detect_document_format(doc) == DocumentFormat.MARKDOWN

    def test_priority_mime_type_over_magic_bytes(self, pdf_file: Path):
        """Тест приоритета MIME типа над magic bytes."""
        # Создаём документ с неправильным расширением, но правильным MIME типом
        doc = Document(
            page_content="PDF content",
            metadata={
                "source": str(pdf_file.with_suffix(".txt")),
                "mime_type": "application/pdf"
            }
        )
        # Должен определить по MIME типу
        assert detect_document_format(doc) == DocumentFormat.PDF

    def test_unknown_format_when_all_methods_fail(self):
        """Тест возврата UNKNOWN когда все методы не сработали."""
        doc = Document(
            page_content="Unknown content",
            metadata={"source": "/path/to/unknown.xyz"}
        )
        assert detect_document_format(doc) == DocumentFormat.UNKNOWN

    def test_raises_error_when_no_content_and_no_source(self):
        """Тест выброса ошибки когда нет ни контента, ни источника."""
        doc = Document(page_content="", metadata={})
        with pytest.raises(ValueError, match="Документ должен содержать page_content или source"):
            detect_document_format(doc)

    def test_works_with_only_source_no_content(self, markdown_file: Path):
        """Тест работы когда есть только source, но нет page_content."""
        doc = Document(
            page_content="",
            metadata={"source": str(markdown_file)}
        )
        assert detect_document_format(doc) == DocumentFormat.MARKDOWN

    def test_works_with_only_content_no_source(self):
        """Тест работы когда есть только page_content, но нет source."""
        doc = Document(
            page_content="# Markdown content",
            metadata={}
        )
        # Должен вернуть UNKNOWN, так как нет способа определить формат
        assert detect_document_format(doc) == DocumentFormat.UNKNOWN


class TestValidateDocument:
    """Тесты для функции validate_document()."""

    def test_valid_document_with_content(self):
        """Тест валидации корректного документа с контентом."""
        doc = Document(page_content="Test content", metadata={})
        # Не должно быть исключений
        validate_document(doc)

    def test_valid_document_with_source(self):
        """Тест валидации корректного документа с источником."""
        doc = Document(
            page_content="",
            metadata={"source": "/path/to/file.md"}
        )
        validate_document(doc)

    def test_valid_document_with_both(self):
        """Тест валидации корректного документа с контентом и источником."""
        doc = Document(
            page_content="Test content",
            metadata={"source": "/path/to/file.md"}
        )
        validate_document(doc)

    def test_raises_error_when_none(self):
        """Тест выброса ошибки когда документ None."""
        with pytest.raises(ValueError, match="Документ не может быть None"):
            validate_document(None)

    def test_raises_error_when_not_document(self):
        """Тест выброса ошибки когда передан не Document."""
        with pytest.raises(TypeError, match="Ожидается Document"):
            validate_document("not a document")

    def test_raises_error_when_no_content_and_no_source(self):
        """Тест выброса ошибки когда нет ни контента, ни источника."""
        doc = Document(page_content="", metadata={})
        with pytest.raises(ValueError, match="Документ должен содержать page_content или source"):
            validate_document(doc)

    def test_raises_error_when_content_not_string(self):
        """Тест выброса ошибки когда page_content не строка."""
        # LangChain Document не позволяет не-строку для page_content
        # Проверяем, что Document не создается
        with pytest.raises(Exception):  # Pydantic ValidationError
            Document(page_content=123, metadata={})

    def test_raises_error_when_metadata_not_dict(self):
        """Тест выброса ошибки когда metadata не словарь."""
        # LangChain Document не позволяет не-словарь для metadata
        # Проверяем, что Document не создается
        with pytest.raises(Exception):  # Pydantic ValidationError
            Document(page_content="test", metadata="not a dict")

    def test_valid_with_none_metadata(self):
        """Тест валидации документа с metadata = None."""
        # LangChain Document не позволяет metadata=None, используем пустой словарь
        doc = Document(page_content="test", metadata={})
        validate_document(doc)


class TestNormalizeMetadata:
    """Тесты для функции normalize_metadata()."""

    def test_adds_source_when_missing(self, markdown_file: Path):
        """Тест добавления source когда его нет."""
        doc = Document(
            page_content="# Test",
            metadata={"file_path": str(markdown_file)}
        )
        normalized = normalize_metadata(doc)
        assert "source" in normalized
        assert normalized["source"] == str(markdown_file)

    def test_adds_format_when_missing(self, markdown_file: Path):
        """Тест добавления format когда его нет."""
        doc = Document(
            page_content="# Test",
            metadata={"source": str(markdown_file)}
        )
        normalized = normalize_metadata(doc)
        assert "format" in normalized
        assert normalized["format"] == "markdown"

    def test_preserves_existing_source(self):
        """Тест сохранения существующего source."""
        doc = Document(
            page_content="test",
            metadata={"source": "/custom/path.md"}
        )
        normalized = normalize_metadata(doc)
        assert normalized["source"] == "/custom/path.md"

    def test_preserves_existing_format(self):
        """Тест сохранения существующего format."""
        doc = Document(
            page_content="test",
            metadata={"source": "/path/to/file.md", "format": "custom_format"}
        )
        normalized = normalize_metadata(doc)
        assert normalized["format"] == "custom_format"

    def test_preserves_all_existing_metadata(self):
        """Тест сохранения всех существующих метаданных."""
        doc = Document(
            page_content="test",
            metadata={
                "source": "/path/to/file.md",
                "author": "Test Author",
                "title": "Test Title"
            }
        )
        normalized = normalize_metadata(doc)
        assert normalized["author"] == "Test Author"
        assert normalized["title"] == "Test Title"
        assert "format" in normalized

    def test_handles_unknown_source(self):
        """Тест обработки неизвестного источника."""
        doc = Document(
            page_content="test",
            metadata={}
        )
        normalized = normalize_metadata(doc)
        # source не должен быть добавлен если он unknown
        assert "source" not in normalized or normalized.get("source") == "unknown"

    def test_handles_unknown_format_gracefully(self):
        """Тест корректной обработки когда формат не определяется."""
        doc = Document(
            page_content="test",
            metadata={"source": "/path/to/unknown.xyz"}
        )
        normalized = normalize_metadata(doc)
        # format может быть "unknown" или отсутствовать
        assert "format" not in normalized or normalized["format"] in ("unknown", "xyz")

    def test_creates_new_dict(self):
        """Тест создания нового словаря (не модификации исходного)."""
        doc = Document(
            page_content="test",
            metadata={"source": "/path/to/file.md"}
        )
        original_metadata = doc.metadata.copy()
        normalized = normalize_metadata(doc)
        # Исходные метаданные не должны измениться
        assert doc.metadata == original_metadata
        # Нормализованные должны быть новым словарём
        assert normalized is not doc.metadata

    def test_handles_none_metadata(self, markdown_file: Path):
        """Тест обработки metadata = None."""
        # LangChain Document не позволяет metadata=None, используем пустой словарь
        doc = Document(
            page_content="# Test",
            metadata={"file_path": str(markdown_file)}
        )
        normalized = normalize_metadata(doc)
        assert isinstance(normalized, dict)
        assert "source" in normalized

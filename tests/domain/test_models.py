"""
Тесты для доменных моделей.

Тестируемые классы:
- DocumentFormat (Enum)
- ElementType (Enum)
- Element (dataclass)
- ParsedDocument (dataclass)
- ElementIdGenerator
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH для прямого запуска
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest

from documentor.domain.models import (
    DocumentFormat,
    Element,
    ElementIdGenerator,
    ElementType,
    ParsedDocument,
)


# ============================================================================
# Тесты для DocumentFormat
# ============================================================================

class TestDocumentFormat:
    """Тесты для DocumentFormat enum."""

    def test_all_formats_exist(self):
        """Тест наличия всех ожидаемых форматов."""
        expected_formats = {"markdown", "pdf", "docx", "unknown"}
        actual_formats = {fmt.value for fmt in DocumentFormat}
        assert actual_formats == expected_formats

    def test_format_values(self):
        """Тест значений форматов."""
        assert DocumentFormat.MARKDOWN.value == "markdown"
        assert DocumentFormat.PDF.value == "pdf"
        assert DocumentFormat.DOCX.value == "docx"
        assert DocumentFormat.UNKNOWN.value == "unknown"

    def test_format_from_value(self):
        """Тест создания формата из значения."""
        assert DocumentFormat("markdown") == DocumentFormat.MARKDOWN
        assert DocumentFormat("pdf") == DocumentFormat.PDF
        assert DocumentFormat("docx") == DocumentFormat.DOCX
        assert DocumentFormat("unknown") == DocumentFormat.UNKNOWN

    def test_invalid_format_raises_error(self):
        """Тест ошибки при невалидном формате."""
        with pytest.raises(ValueError):
            DocumentFormat("invalid_format")


# ============================================================================
# Тесты для ElementType
# ============================================================================

class TestElementType:
    """Тесты для ElementType enum."""

    def test_all_types_exist(self):
        """Тест наличия всех ожидаемых типов элементов."""
        expected_types = {
            "title",
            "header_1",
            "header_2",
            "header_3",
            "header_4",
            "header_5",
            "header_6",
            "text",
            "image",
            "table",
            "formula",
            "list_item",
            "caption",
            "footnote",
            "page_header",
            "page_footer",
        }
        actual_types = {elem_type.value for elem_type in ElementType}
        assert actual_types == expected_types

    def test_header_levels(self):
        """Тест заголовков по уровням."""
        assert ElementType.HEADER_1.value == "header_1"
        assert ElementType.HEADER_2.value == "header_2"
        assert ElementType.HEADER_3.value == "header_3"
        assert ElementType.HEADER_4.value == "header_4"
        assert ElementType.HEADER_5.value == "header_5"
        assert ElementType.HEADER_6.value == "header_6"

    def test_type_from_value(self):
        """Тест создания типа из значения."""
        assert ElementType("title") == ElementType.TITLE
        assert ElementType("header_1") == ElementType.HEADER_1
        assert ElementType("text") == ElementType.TEXT

    def test_invalid_type_raises_error(self):
        """Тест ошибки при невалидном типе."""
        with pytest.raises(ValueError):
            ElementType("invalid_type")


# ============================================================================
# Тесты для Element
# ============================================================================

class TestElement:
    """Тесты для Element dataclass."""

    def test_create_valid_element(self):
        """Тест создания валидного элемента."""
        element = Element(
            id="001",
            type=ElementType.TITLE,
            content="Test Title",
        )
        assert element.id == "001"
        assert element.type == ElementType.TITLE
        assert element.content == "Test Title"
        assert element.parent_id is None
        assert element.metadata == {}

    def test_create_element_with_parent(self):
        """Тест создания элемента с parent_id."""
        element = Element(
            id="002",
            type=ElementType.HEADER_1,
            content="Header 1",
            parent_id="001",
        )
        assert element.parent_id == "001"

    def test_create_element_with_metadata(self):
        """Тест создания элемента с метаданными."""
        metadata = {"page": 1, "position": {"x": 10, "y": 20}}
        element = Element(
            id="003",
            type=ElementType.TEXT,
            content="Some text",
            metadata=metadata,
        )
        assert element.metadata == metadata

    def test_validate_empty_id_raises_error(self):
        """Тест валидации: пустой id вызывает ошибку."""
        with pytest.raises(ValueError, match="id must be a non-empty string"):
            Element(id="", type=ElementType.TEXT, content="test")

    def test_validate_whitespace_id_raises_error(self):
        """Тест валидации: id из пробелов вызывает ошибку."""
        with pytest.raises(ValueError, match="id must be a non-empty string"):
            Element(id="   ", type=ElementType.TEXT, content="test")

    def test_validate_invalid_type_raises_error(self):
        """Тест валидации: невалидный type вызывает ошибку."""
        with pytest.raises(ValueError, match="type must be ElementType"):
            Element(id="001", type="invalid", content="test")  # type: ignore

    def test_validate_none_content_raises_error(self):
        """Тест валидации: None content вызывает ошибку."""
        with pytest.raises(ValueError, match="content cannot be None"):
            Element(id="001", type=ElementType.TEXT, content=None)  # type: ignore

    def test_validate_non_string_content_raises_error(self):
        """Тест валидации: не-строка content вызывает ошибку."""
        with pytest.raises(ValueError, match="content must be a string"):
            Element(id="001", type=ElementType.TEXT, content=123)  # type: ignore

    def test_validate_invalid_metadata_raises_error(self):
        """Тест валидации: невалидный metadata вызывает ошибку."""
        with pytest.raises(ValueError, match="metadata must be a dict"):
            Element(id="001", type=ElementType.TEXT, content="test", metadata="invalid")  # type: ignore

    def test_validate_empty_parent_id_raises_error(self):
        """Тест валидации: пустой parent_id вызывает ошибку."""
        with pytest.raises(ValueError, match="parent_id must be a non-empty string or None"):
            Element(id="001", type=ElementType.TEXT, content="test", parent_id="")

    def test_validate_whitespace_parent_id_raises_error(self):
        """Тест валидации: parent_id из пробелов вызывает ошибку."""
        with pytest.raises(ValueError, match="parent_id must be a non-empty string or None"):
            Element(id="001", type=ElementType.TEXT, content="test", parent_id="   ")

    def test_repr(self):
        """Тест __repr__ метода."""
        element = Element(
            id="001",
            type=ElementType.TITLE,
            content="Test Title",
        )
        repr_str = repr(element)
        assert "Element" in repr_str
        assert "id='001'" in repr_str
        assert "type='title'" in repr_str
        assert "Test Title" in repr_str

    def test_repr_with_long_content(self):
        """Тест __repr__ с длинным контентом (обрезается)."""
        long_content = "A" * 100
        element = Element(id="001", type=ElementType.TEXT, content=long_content)
        repr_str = repr(element)
        assert len(repr_str) < len(long_content) + 50  # Должно быть обрезано
        assert "..." in repr_str

    def test_str(self):
        """Тест __str__ метода."""
        element = Element(
            id="001",
            type=ElementType.TITLE,
            content="Test Title",
        )
        str_repr = str(element)
        assert "title[001]" in str_repr
        assert "Test Title" in str_repr

    def test_str_with_parent(self):
        """Тест __str__ с parent_id."""
        element = Element(
            id="002",
            type=ElementType.HEADER_1,
            content="Header",
            parent_id="001",
        )
        str_repr = str(element)
        assert "parent: 001" in str_repr

    def test_to_dict_minimal(self):
        """Тест to_dict для минимального элемента."""
        element = Element(id="001", type=ElementType.TEXT, content="test")
        result = element.to_dict()
        assert result == {
            "id": "001",
            "type": "text",
            "content": "test",
        }

    def test_to_dict_with_parent(self):
        """Тест to_dict с parent_id."""
        element = Element(
            id="002",
            type=ElementType.HEADER_1,
            content="Header",
            parent_id="001",
        )
        result = element.to_dict()
        assert result["parent_id"] == "001"

    def test_to_dict_with_metadata(self):
        """Тест to_dict с метаданными."""
        metadata = {"page": 1, "key": "value"}
        element = Element(
            id="003",
            type=ElementType.TEXT,
            content="test",
            metadata=metadata,
        )
        result = element.to_dict()
        assert result["metadata"] == metadata

    def test_from_dict_minimal(self):
        """Тест from_dict для минимального элемента."""
        data = {
            "id": "001",
            "type": "text",
            "content": "test",
        }
        element = Element.from_dict(data)
        assert element.id == "001"
        assert element.type == ElementType.TEXT
        assert element.content == "test"
        assert element.parent_id is None
        assert element.metadata == {}

    def test_from_dict_with_parent(self):
        """Тест from_dict с parent_id."""
        data = {
            "id": "002",
            "type": "header_1",
            "content": "Header",
            "parent_id": "001",
        }
        element = Element.from_dict(data)
        assert element.parent_id == "001"

    def test_from_dict_with_metadata(self):
        """Тест from_dict с метаданными."""
        data = {
            "id": "003",
            "type": "text",
            "content": "test",
            "metadata": {"page": 1},
        }
        element = Element.from_dict(data)
        assert element.metadata == {"page": 1}

    def test_from_dict_missing_required_field(self):
        """Тест from_dict с отсутствующим обязательным полем."""
        data = {"id": "001", "type": "text"}  # Нет content
        with pytest.raises(ValueError, match="Missing required fields"):
            Element.from_dict(data)

    def test_from_dict_invalid_type(self):
        """Тест from_dict с невалидным типом."""
        data = {
            "id": "001",
            "type": "invalid_type",
            "content": "test",
        }
        with pytest.raises(ValueError, match="Invalid ElementType"):
            Element.from_dict(data)

    def test_from_dict_not_dict(self):
        """Тест from_dict с не-словарем."""
        with pytest.raises(ValueError, match="Expected dict"):
            Element.from_dict("not a dict")  # type: ignore

    def test_to_json(self):
        """Тест to_json метода."""
        element = Element(id="001", type=ElementType.TEXT, content="test")
        json_str = element.to_json()
        assert isinstance(json_str, str)
        data = json.loads(json_str)
        assert data["id"] == "001"
        assert data["type"] == "text"
        assert data["content"] == "test"

    def test_from_json(self):
        """Тест from_json метода."""
        json_str = '{"id": "001", "type": "text", "content": "test"}'
        element = Element.from_json(json_str)
        assert element.id == "001"
        assert element.type == ElementType.TEXT
        assert element.content == "test"

    def test_from_json_invalid_json(self):
        """Тест from_json с невалидным JSON."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            Element.from_json("not a json")

    def test_from_json_not_string(self):
        """Тест from_json с не-строкой."""
        with pytest.raises(ValueError, match="Expected str"):
            Element.from_json({"id": "001"})  # type: ignore

    def test_round_trip_dict(self):
        """Тест полного цикла: to_dict -> from_dict."""
        original = Element(
            id="001",
            type=ElementType.HEADER_1,
            content="Header",
            parent_id=None,
            metadata={"page": 1},
        )
        restored = Element.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.type == original.type
        assert restored.content == original.content
        assert restored.parent_id == original.parent_id
        assert restored.metadata == original.metadata

    def test_round_trip_json(self):
        """Тест полного цикла: to_json -> from_json."""
        original = Element(
            id="001",
            type=ElementType.TEXT,
            content="Test content",
            parent_id="000",
            metadata={"key": "value"},
        )
        restored = Element.from_json(original.to_json())
        assert restored.id == original.id
        assert restored.type == original.type
        assert restored.content == original.content
        assert restored.parent_id == original.parent_id
        assert restored.metadata == original.metadata


# ============================================================================
# Тесты для ParsedDocument
# ============================================================================

class TestParsedDocument:
    """Тесты для ParsedDocument dataclass."""

    @pytest.fixture
    def sample_elements(self):
        """Фикстура с примерными элементами."""
        return [
            Element(id="001", type=ElementType.TITLE, content="Title"),
            Element(id="002", type=ElementType.HEADER_1, content="Header 1", parent_id="001"),
            Element(id="003", type=ElementType.TEXT, content="Text", parent_id="002"),
        ]

    def test_create_valid_document(self, sample_elements):
        """Тест создания валидного документа."""
        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=sample_elements,
        )
        assert doc.source == "test.md"
        assert doc.format == DocumentFormat.MARKDOWN
        assert len(doc.elements) == 3
        assert doc.metadata == {}

    def test_create_document_with_metadata(self, sample_elements):
        """Тест создания документа с метаданными."""
        metadata = {"author": "Test", "version": "1.0"}
        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=sample_elements,
            metadata=metadata,
        )
        assert doc.metadata == metadata

    def test_validate_empty_source_raises_error(self, sample_elements):
        """Тест валидации: пустой source вызывает ошибку."""
        with pytest.raises(ValueError, match="source must be a non-empty string"):
            ParsedDocument(source="", format=DocumentFormat.MARKDOWN, elements=sample_elements)

    def test_validate_invalid_format_raises_error(self, sample_elements):
        """Тест валидации: невалидный format вызывает ошибку."""
        with pytest.raises(ValueError, match="format must be DocumentFormat"):
            ParsedDocument(source="test.md", format="invalid", elements=sample_elements)  # type: ignore

    def test_validate_empty_elements_raises_error(self):
        """Тест валидации: пустой список elements вызывает ошибку."""
        with pytest.raises(ValueError, match="must contain at least one element"):
            ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=[])

    def test_validate_non_list_elements_raises_error(self):
        """Тест валидации: elements не список вызывает ошибку."""
        with pytest.raises(ValueError, match="elements must be a list"):
            ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements="not a list")  # type: ignore

    def test_validate_non_element_in_list_raises_error(self):
        """Тест валидации: элемент не Element вызывает ошибку."""
        with pytest.raises(ValueError, match="must be Element instances"):
            ParsedDocument(
                source="test.md",
                format=DocumentFormat.MARKDOWN,
                elements=["not an element"],  # type: ignore
            )

    def test_validate_duplicate_ids_raises_error(self):
        """Тест валидации: дублирующиеся id вызывают ошибку."""
        elements = [
            Element(id="001", type=ElementType.TEXT, content="Text 1"),
            Element(id="001", type=ElementType.TEXT, content="Text 2"),  # Дубликат
        ]
        with pytest.raises(ValueError, match="Duplicate element ids"):
            ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=elements)

    def test_validate_hierarchy_nonexistent_parent(self):
        """Тест валидации иерархии: несуществующий parent_id."""
        elements = [
            Element(id="001", type=ElementType.TEXT, content="Text", parent_id="999"),  # Несуществующий родитель
        ]
        with pytest.raises(ValueError, match="references non-existent parent_id"):
            ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=elements)

    def test_validate_hierarchy_self_parent(self):
        """Тест валидации иерархии: элемент не может быть своим родителем."""
        elements = [
            Element(id="001", type=ElementType.TEXT, content="Text", parent_id="001"),  # Сам себе родитель
        ]
        with pytest.raises(ValueError, match="cannot be its own parent"):
            ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=elements)

    def test_validate_hierarchy_cycle_direct(self):
        """Тест валидации иерархии: прямой цикл."""
        elements = [
            Element(id="001", type=ElementType.TEXT, content="Text 1", parent_id="002"),
            Element(id="002", type=ElementType.TEXT, content="Text 2", parent_id="001"),  # Цикл
        ]
        with pytest.raises(ValueError, match="Cycle detected"):
            ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=elements)

    def test_validate_hierarchy_cycle_indirect(self):
        """Тест валидации иерархии: непрямой цикл (A -> B -> C -> A)."""
        elements = [
            Element(id="001", type=ElementType.TEXT, content="Text 1", parent_id="003"),
            Element(id="002", type=ElementType.TEXT, content="Text 2", parent_id="001"),
            Element(id="003", type=ElementType.TEXT, content="Text 3", parent_id="002"),  # Цикл
        ]
        with pytest.raises(ValueError, match="Cycle detected"):
            ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=elements)

    def test_validate_hierarchy_valid_tree(self):
        """Тест валидации иерархии: валидное дерево."""
        elements = [
            Element(id="001", type=ElementType.TITLE, content="Title"),
            Element(id="002", type=ElementType.HEADER_1, content="H1", parent_id="001"),
            Element(id="003", type=ElementType.HEADER_2, content="H2", parent_id="002"),
            Element(id="004", type=ElementType.TEXT, content="Text", parent_id="003"),
        ]
        # Не должно вызывать ошибку
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=elements)
        assert len(doc.elements) == 4

    def test_validate_hierarchy_header_reset_allowed(self):
        """Тест валидации иерархии: разрешен сброс иерархии заголовков."""
        # HEADER_1 после HEADER_2 без родителя - разрешено
        elements = [
            Element(id="001", type=ElementType.HEADER_1, content="H1"),
            Element(id="002", type=ElementType.HEADER_2, content="H2", parent_id="001"),
            Element(id="003", type=ElementType.HEADER_1, content="H1 again"),  # Сброс иерархии
        ]
        # Не должно вызывать ошибку
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=elements)
        assert len(doc.elements) == 3

    def test_repr(self, sample_elements):
        """Тест __repr__ метода."""
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=sample_elements)
        repr_str = repr(doc)
        assert "ParsedDocument" in repr_str
        assert "source='test.md'" in repr_str
        assert "format='markdown'" in repr_str
        assert "elements=3" in repr_str

    def test_str(self, sample_elements):
        """Тест __str__ метода."""
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=sample_elements)
        str_repr = str(doc)
        assert "ParsedDocument" in str_repr
        assert "markdown" in str_repr
        assert "test.md" in str_repr
        assert "3 elements" in str_repr

    def test_str_with_path(self, sample_elements):
        """Тест __str__ с путем к файлу."""
        doc = ParsedDocument(source="/path/to/test.md", format=DocumentFormat.MARKDOWN, elements=sample_elements)
        str_repr = str(doc)
        assert "test.md" in str_repr

    def test_to_dicts(self, sample_elements):
        """Тест to_dicts метода."""
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=sample_elements)
        dicts = doc.to_dicts()
        assert len(dicts) == 3
        assert all(isinstance(d, dict) for d in dicts)
        assert dicts[0]["id"] == "001"

    def test_to_dict(self, sample_elements):
        """Тест to_dict метода."""
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=sample_elements)
        result = doc.to_dict()
        assert result["source"] == "test.md"
        assert result["format"] == "markdown"
        assert len(result["elements"]) == 3
        assert "metadata" not in result  # Пустые metadata не включаются

    def test_to_dict_with_metadata(self, sample_elements):
        """Тест to_dict с метаданными."""
        metadata = {"author": "Test"}
        doc = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=sample_elements,
            metadata=metadata,
        )
        result = doc.to_dict()
        assert result["metadata"] == metadata

    def test_from_dict(self, sample_elements):
        """Тест from_dict метода."""
        data = {
            "source": "test.md",
            "format": "markdown",
            "elements": [elem.to_dict() for elem in sample_elements],
        }
        doc = ParsedDocument.from_dict(data)
        assert doc.source == "test.md"
        assert doc.format == DocumentFormat.MARKDOWN
        assert len(doc.elements) == 3

    def test_from_dict_with_metadata(self, sample_elements):
        """Тест from_dict с метаданными."""
        data = {
            "source": "test.md",
            "format": "markdown",
            "elements": [elem.to_dict() for elem in sample_elements],
            "metadata": {"author": "Test"},
        }
        doc = ParsedDocument.from_dict(data)
        assert doc.metadata == {"author": "Test"}

    def test_from_dict_missing_required_field(self):
        """Тест from_dict с отсутствующим обязательным полем."""
        data = {"source": "test.md", "format": "markdown"}  # Нет elements
        with pytest.raises(ValueError, match="Missing required fields"):
            ParsedDocument.from_dict(data)

    def test_from_dict_invalid_format(self, sample_elements):
        """Тест from_dict с невалидным форматом."""
        data = {
            "source": "test.md",
            "format": "invalid_format",
            "elements": [elem.to_dict() for elem in sample_elements],
        }
        with pytest.raises(ValueError, match="Invalid DocumentFormat"):
            ParsedDocument.from_dict(data)

    def test_from_dict_not_dict(self):
        """Тест from_dict с не-словарем."""
        with pytest.raises(ValueError, match="Expected dict"):
            ParsedDocument.from_dict("not a dict")  # type: ignore

    def test_to_json(self, sample_elements):
        """Тест to_json метода."""
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=sample_elements)
        json_str = doc.to_json()
        assert isinstance(json_str, str)
        data = json.loads(json_str)
        assert data["source"] == "test.md"
        assert data["format"] == "markdown"

    def test_from_json(self, sample_elements):
        """Тест from_json метода."""
        doc = ParsedDocument(source="test.md", format=DocumentFormat.MARKDOWN, elements=sample_elements)
        json_str = doc.to_json()
        restored = ParsedDocument.from_json(json_str)
        assert restored.source == doc.source
        assert restored.format == doc.format
        assert len(restored.elements) == len(doc.elements)

    def test_from_json_invalid_json(self):
        """Тест from_json с невалидным JSON."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            ParsedDocument.from_json("not a json")

    def test_from_json_not_string(self):
        """Тест from_json с не-строкой."""
        with pytest.raises(ValueError, match="Expected str"):
            ParsedDocument.from_json({"source": "test.md"})  # type: ignore

    def test_round_trip_dict(self, sample_elements):
        """Тест полного цикла: to_dict -> from_dict."""
        original = ParsedDocument(
            source="test.md",
            format=DocumentFormat.MARKDOWN,
            elements=sample_elements,
            metadata={"author": "Test"},
        )
        restored = ParsedDocument.from_dict(original.to_dict())
        assert restored.source == original.source
        assert restored.format == original.format
        assert len(restored.elements) == len(original.elements)
        assert restored.metadata == original.metadata

    def test_round_trip_json(self, sample_elements):
        """Тест полного цикла: to_json -> from_json."""
        original = ParsedDocument(
            source="test.md",
            format=DocumentFormat.PDF,
            elements=sample_elements,
            metadata={"version": "1.0"},
        )
        restored = ParsedDocument.from_json(original.to_json())
        assert restored.source == original.source
        assert restored.format == original.format
        assert len(restored.elements) == len(original.elements)
        assert restored.metadata == original.metadata


# ============================================================================
# Тесты для ElementIdGenerator
# ============================================================================

class TestElementIdGenerator:
    """Тесты для ElementIdGenerator."""

    def test_default_initialization(self):
        """Тест инициализации с параметрами по умолчанию."""
        generator = ElementIdGenerator()
        assert generator._counter == 1
        assert generator._width == 8

    def test_custom_initialization(self):
        """Тест инициализации с кастомными параметрами."""
        generator = ElementIdGenerator(start=10, width=4)
        assert generator._counter == 10
        assert generator._width == 4

    def test_next_id_default(self):
        """Тест генерации ID с параметрами по умолчанию."""
        generator = ElementIdGenerator()
        assert generator.next_id() == "00000001"
        assert generator.next_id() == "00000002"
        assert generator.next_id() == "00000003"

    def test_next_id_custom_width(self):
        """Тест генерации ID с кастомной шириной."""
        generator = ElementIdGenerator(start=1, width=4)
        assert generator.next_id() == "0001"
        assert generator.next_id() == "0002"

    def test_next_id_custom_start(self):
        """Тест генерации ID с кастомным стартом."""
        generator = ElementIdGenerator(start=100, width=6)
        assert generator.next_id() == "000100"
        assert generator.next_id() == "000101"

    def test_reset_to_default(self):
        """Тест сброса к значению по умолчанию."""
        generator = ElementIdGenerator()
        generator.next_id()
        generator.next_id()
        generator.reset()
        assert generator.next_id() == "00000001"

    def test_reset_to_custom(self):
        """Тест сброса к кастомному значению."""
        generator = ElementIdGenerator()
        generator.next_id()
        generator.next_id()
        generator.reset(50)
        assert generator.next_id() == "00000050"

    def test_repr(self):
        """Тест __repr__ метода."""
        generator = ElementIdGenerator(start=5, width=4)
        repr_str = repr(generator)
        assert "ElementIdGenerator" in repr_str
        assert "counter=5" in repr_str
        assert "width=4" in repr_str
        assert "next_id='0005'" in repr_str

    def test_str(self):
        """Тест __str__ метода."""
        generator = ElementIdGenerator(start=10, width=6)
        str_repr = str(generator)
        assert "ElementIdGenerator" in str_repr
        assert "width=6" in str_repr
        assert "next_id=000010" in str_repr

    def test_sequential_ids(self):
        """Тест последовательной генерации ID."""
        generator = ElementIdGenerator(start=1, width=3)
        ids = [generator.next_id() for _ in range(5)]
        assert ids == ["001", "002", "003", "004", "005"]

    def test_large_numbers(self):
        """Тест генерации больших чисел."""
        generator = ElementIdGenerator(start=999, width=4)
        assert generator.next_id() == "0999"
        assert generator.next_id() == "1000"
        assert generator.next_id() == "1001"

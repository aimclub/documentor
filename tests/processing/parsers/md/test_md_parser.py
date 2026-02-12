"""
Тесты для Markdown парсера.

Тестируемый класс:
- MarkdownParser
"""

import sys
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH для прямого запуска
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from langchain_core.documents import Document

from documentor.domain import DocumentFormat, Element, ElementIdGenerator, ElementType, ParsedDocument
from documentor.exceptions import ParsingError, UnsupportedFormatError, ValidationError
from documentor.processing.parsers.md.md_parser import MarkdownParser


class TestMarkdownParserInitialization:
    """Тесты инициализации MarkdownParser."""

    def test_default_initialization(self):
        """Тест инициализации с параметрами по умолчанию."""
        parser = MarkdownParser()
        assert parser.format == DocumentFormat.MARKDOWN
        assert isinstance(parser.id_generator, ElementIdGenerator)

    def test_custom_id_generator(self):
        """Тест инициализации с кастомным генератором ID."""
        custom_generator = ElementIdGenerator(start=100, width=4)
        parser = MarkdownParser(id_generator=custom_generator)
        assert parser.id_generator is custom_generator
        assert parser.id_generator._counter == 100


class TestMarkdownParserBasicParsing:
    """Тесты базового парсинга Markdown."""

    def test_parse_simple_text(self):
        """Тест парсинга простого текста."""
        parser = MarkdownParser()
        doc = Document(page_content="Простой текст", metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert isinstance(result, ParsedDocument)
        assert result.format == DocumentFormat.MARKDOWN
        assert result.source == "test.md"
        assert len(result.elements) == 1
        assert result.elements[0].type == ElementType.TEXT
        assert result.elements[0].content == "Простой текст"

    def test_parse_empty_document(self):
        """Тест парсинга пустого документа."""
        parser = MarkdownParser()
        doc = Document(page_content="", metadata={"source": "empty.md"})
        result = parser.parse(doc)

        assert isinstance(result, ParsedDocument)
        assert result.format == DocumentFormat.MARKDOWN
        assert len(result.elements) == 0

    def test_parse_multiple_paragraphs(self):
        """Тест парсинга нескольких параграфов."""
        parser = MarkdownParser()
        content = "Первый параграф.\n\nВторой параграф.\n\nТретий параграф."
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 3
        assert all(elem.type == ElementType.TEXT for elem in result.elements)
        assert result.elements[0].content == "Первый параграф."
        assert result.elements[1].content == "Второй параграф."
        assert result.elements[2].content == "Третий параграф."


class TestMarkdownParserHeadings:
    """Тесты парсинга заголовков."""

    def test_parse_h1_heading(self):
        """Тест парсинга заголовка H1."""
        parser = MarkdownParser()
        doc = Document(page_content="# Заголовок 1", metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 1
        assert result.elements[0].type == ElementType.HEADER_1
        assert result.elements[0].content == "Заголовок 1"
        assert result.elements[0].parent_id is None

    def test_parse_all_heading_levels(self):
        """Тест парсинга всех уровней заголовков."""
        parser = MarkdownParser()
        content = "# H1\n## H2\n### H3\n#### H4\n##### H5\n###### H6"
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 6
        assert result.elements[0].type == ElementType.HEADER_1
        assert result.elements[1].type == ElementType.HEADER_2
        assert result.elements[2].type == ElementType.HEADER_3
        assert result.elements[3].type == ElementType.HEADER_4
        assert result.elements[4].type == ElementType.HEADER_5
        assert result.elements[5].type == ElementType.HEADER_6

    def test_heading_hierarchy(self):
        """Тест построения иерархии заголовков."""
        parser = MarkdownParser()
        content = """# Заголовок 1
Текст под H1
## Заголовок 2
Текст под H2
### Заголовок 3
Текст под H3
## Заголовок 2 снова
Текст под H2 снова"""
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        # Проверяем структуру
        h1 = result.elements[0]
        text1 = result.elements[1]
        h2_1 = result.elements[2]
        text2 = result.elements[3]
        h3 = result.elements[4]
        text3 = result.elements[5]
        h2_2 = result.elements[6]
        text4 = result.elements[7]

        assert h1.type == ElementType.HEADER_1
        assert h1.parent_id is None

        assert text1.type == ElementType.TEXT
        assert text1.parent_id == h1.id

        assert h2_1.type == ElementType.HEADER_2
        assert h2_1.parent_id == h1.id

        assert text2.type == ElementType.TEXT
        assert text2.parent_id == h2_1.id

        assert h3.type == ElementType.HEADER_3
        assert h3.parent_id == h2_1.id

        assert text3.type == ElementType.TEXT
        assert text3.parent_id == h3.id

        assert h2_2.type == ElementType.HEADER_2
        assert h2_2.parent_id == h1.id  # Должен быть под H1, а не под H3

        assert text4.type == ElementType.TEXT
        assert text4.parent_id == h2_2.id


class TestMarkdownParserLists:
    """Тесты парсинга списков."""

    def test_parse_unordered_list(self):
        """Тест парсинга неупорядоченного списка."""
        parser = MarkdownParser()
        content = """- Элемент 1
- Элемент 2
- Элемент 3"""
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 3
        assert all(elem.type == ElementType.LIST_ITEM for elem in result.elements)
        assert result.elements[0].content == "Элемент 1"
        assert result.elements[1].content == "Элемент 2"
        assert result.elements[2].content == "Элемент 3"

    def test_parse_ordered_list(self):
        """Тест парсинга упорядоченного списка."""
        parser = MarkdownParser()
        content = """1. Первый
2. Второй
3. Третий"""
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 3
        assert all(elem.type == ElementType.LIST_ITEM for elem in result.elements)
        assert "Первый" in result.elements[0].content
        assert result.elements[0].metadata.get("list_type") == "ordered"

    def test_parse_nested_list(self):
        """Тест парсинга вложенных списков."""
        parser = MarkdownParser()
        content = """- Элемент 1
  - Вложенный 1
  - Вложенный 2
- Элемент 2
  - Вложенный 3
    - Глубоко вложенный"""
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        list_items = [e for e in result.elements if e.type == ElementType.LIST_ITEM]
        assert len(list_items) >= 6
        
        # Проверяем уровни вложенности
        first_level = [e for e in list_items if e.metadata.get("list_level", 0) == 0]
        second_level = [e for e in list_items if e.metadata.get("list_level", 0) == 1]
        third_level = [e for e in list_items if e.metadata.get("list_level", 0) == 2]
        
        assert len(first_level) >= 2  # Элемент 1, Элемент 2
        assert len(second_level) >= 3  # Вложенные элементы
        assert len(third_level) >= 1  # Глубоко вложенный

    def test_nested_list_hierarchy(self):
        """Тест иерархии вложенных списков."""
        parser = MarkdownParser()
        content = """- Родитель 1
  - Дочерний 1
  - Дочерний 2
- Родитель 2"""
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        list_items = [e for e in result.elements if e.type == ElementType.LIST_ITEM]
        
        # Находим элементы по содержимому
        parent1 = next((e for e in list_items if "Родитель 1" in e.content), None)
        child1 = next((e for e in list_items if "Дочерний 1" in e.content), None)
        child2 = next((e for e in list_items if "Дочерний 2" in e.content), None)
        
        assert parent1 is not None
        assert child1 is not None
        assert child2 is not None
        
        # Проверяем, что дочерние элементы ссылаются на родительский
        assert child1.parent_id == parent1.id
        assert child2.parent_id == parent1.id
        
        # Проверяем содержимое элементов
        assert "Дочерний 1" in child1.content
        assert "Дочерний 2" in child2.content
        assert "Родитель 1" in parent1.content


class TestMarkdownParserTables:
    """Тесты парсинга таблиц."""

    def test_parse_simple_table(self):
        """Тест парсинга простой таблицы."""
        parser = MarkdownParser()
        content = """| Заголовок 1 | Заголовок 2 |
|-------------|-------------|
| Ячейка 1    | Ячейка 2    |
| Ячейка 3    | Ячейка 4    |"""
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 1
        assert result.elements[0].type == ElementType.TABLE
        assert "Заголовок 1" in result.elements[0].content
        assert "Ячейка 1" in result.elements[0].content


class TestMarkdownParserCodeBlocks:
    """Тесты парсинга блоков кода."""

    def test_parse_code_block(self):
        """Тест парсинга блока кода."""
        parser = MarkdownParser()
        content = """```python
def hello():
    print("Hello, World!")
```"""
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 1
        assert result.elements[0].type == ElementType.CODE_BLOCK
        assert "def hello()" in result.elements[0].content
        assert result.elements[0].metadata.get("language") == "python"

    def test_parse_code_block_without_language(self):
        """Тест парсинга блока кода без указания языка."""
        parser = MarkdownParser()
        content = """```
Простой код
```"""
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 1
        assert result.elements[0].type == ElementType.CODE_BLOCK
        assert "Простой код" in result.elements[0].content
        assert result.elements[0].metadata.get("language") == "" or "language" not in result.elements[0].metadata


class TestMarkdownParserLinks:
    """Тесты парсинга ссылок."""

    def test_parse_standalone_link(self):
        """Тест парсинга отдельной ссылки."""
        parser = MarkdownParser()
        content = "[Текст ссылки](https://example.com)"
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        # Ссылка должна быть создана как отдельный элемент LINK
        link_elements = [e for e in result.elements if e.type == ElementType.LINK]
        assert len(link_elements) >= 1
        assert link_elements[0].content == "Текст ссылки"
        assert link_elements[0].metadata.get("href") == "https://example.com"

    def test_parse_link_in_text(self):
        """Тест парсинга ссылки внутри текста."""
        parser = MarkdownParser()
        content = "Вот [ссылка на Google](https://www.google.com) в тексте."
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        # Должны быть созданы элементы: LINK и TEXT
        link_elements = [e for e in result.elements if e.type == ElementType.LINK]
        text_elements = [e for e in result.elements if e.type == ElementType.TEXT]
        
        assert len(link_elements) >= 1
        assert link_elements[0].metadata.get("href") == "https://www.google.com"
        # Текст должен быть обработан отдельно
        assert len(text_elements) >= 1

    def test_parse_multiple_links(self):
        """Тест парсинга нескольких ссылок."""
        parser = MarkdownParser()
        content = "[Ссылка 1](https://example.com) и [Ссылка 2](https://github.com)"
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        link_elements = [e for e in result.elements if e.type == ElementType.LINK]
        assert len(link_elements) >= 2
        assert link_elements[0].metadata.get("href") == "https://example.com"
        assert link_elements[1].metadata.get("href") == "https://github.com"


class TestMarkdownParserImages:
    """Тесты парсинга изображений."""

    def test_parse_standalone_image(self):
        """Тест парсинга отдельного изображения."""
        parser = MarkdownParser()
        content = "![Альт текст](image.jpg)"
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        # Изображение должно быть создано как отдельный элемент IMAGE
        image_elements = [e for e in result.elements if e.type == ElementType.IMAGE]
        assert len(image_elements) >= 1
        assert image_elements[0].metadata.get("alt") == "Альт текст"
        assert image_elements[0].metadata.get("src") == "image.jpg"
        assert image_elements[0].content == "Альт текст"

    def test_parse_image_in_text(self):
        """Тест парсинга изображения внутри текста."""
        parser = MarkdownParser()
        content = "Вот ![картинка](image.png) в тексте."
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        # Должны быть созданы элементы: IMAGE и TEXT
        image_elements = [e for e in result.elements if e.type == ElementType.IMAGE]
        text_elements = [e for e in result.elements if e.type == ElementType.TEXT]
        
        assert len(image_elements) >= 1
        assert image_elements[0].metadata.get("src") == "image.png"
        # Текст должен быть обработан отдельно
        assert len(text_elements) >= 1

    def test_parse_image_without_alt(self):
        """Тест парсинга изображения без альтернативного текста."""
        parser = MarkdownParser()
        content = "![](image.jpg)"
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        image_elements = [e for e in result.elements if e.type == ElementType.IMAGE]
        assert len(image_elements) >= 1
        assert image_elements[0].metadata.get("src") == "image.jpg"
        assert image_elements[0].content == "image.jpg"  # Используется URL как content


class TestMarkdownParserQuotes:
    """Тесты парсинга цитат."""

    def test_parse_blockquote(self):
        """Тест парсинга цитаты."""
        parser = MarkdownParser()
        content = "> Это цитата"
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 1
        assert result.elements[0].type == ElementType.TEXT
        assert "Это цитата" in result.elements[0].content
        assert result.elements[0].metadata.get("quote") is True


class TestMarkdownParserComplexDocument:
    """Тесты парсинга сложных документов."""

    def test_parse_complex_document(self):
        """Тест парсинга документа с различными элементами."""
        parser = MarkdownParser()
        content = """# Главный заголовок

Это параграф с текстом.

## Подзаголовок

- Элемент списка 1
- Элемент списка 2

```python
code = "example"
```

| Таблица | Колонка |
|---------|---------|
| Данные  | Значение |

> Цитата

[Ссылка](https://example.com)
"""
        doc = Document(page_content=content, metadata={"source": "complex.md"})
        result = parser.parse(doc)

        assert isinstance(result, ParsedDocument)
        assert result.format == DocumentFormat.MARKDOWN
        assert len(result.elements) > 0

        # Проверяем наличие различных типов элементов
        types = [elem.type for elem in result.elements]
        assert ElementType.HEADER_1 in types
        assert ElementType.HEADER_2 in types
        assert ElementType.TEXT in types
        assert ElementType.LIST_ITEM in types
        assert ElementType.CODE_BLOCK in types
        assert ElementType.TABLE in types

    def test_parse_real_file(self):
        """Тест парсинга реального файла из tests/files_for_tests."""
        parser = MarkdownParser()
        test_file = Path(__file__).parent.parent.parent / "files_for_tests" / "md.md"

        if test_file.exists():
            content = test_file.read_text(encoding="utf-8")
            doc = Document(page_content=content, metadata={"source": str(test_file)})
            result = parser.parse(doc)

            assert isinstance(result, ParsedDocument)
            assert result.format == DocumentFormat.MARKDOWN
            assert len(result.elements) > 0


class TestMarkdownParserValidation:
    """Тесты валидации входных данных."""

    def test_validate_input_none_document(self):
        """Тест валидации None документа."""
        parser = MarkdownParser()
        with pytest.raises(ValidationError):
            parser.parse(None)  # type: ignore

    def test_validate_input_wrong_format(self):
        """Тест валидации документа неправильного формата."""
        parser = MarkdownParser()
        doc = Document(page_content="PDF content", metadata={"source": "test.pdf"})
        with pytest.raises(UnsupportedFormatError):
            parser.parse(doc)

    def test_validate_input_empty_content(self):
        """Тест валидации документа с пустым контентом."""
        parser = MarkdownParser()
        doc = Document(page_content="", metadata={"source": "test.md"})
        result = parser.parse(doc)
        # Пустой документ должен быть валидным, но без элементов
        assert isinstance(result, ParsedDocument)
        assert len(result.elements) == 0


class TestMarkdownParserErrorHandling:
    """Тесты обработки ошибок."""

    def test_parsing_error_handling(self):
        """Тест обработки ошибок парсинга."""
        parser = MarkdownParser()
        # Создаем документ, который может вызвать ошибку
        # (хотя mistune обычно обрабатывает большинство случаев)
        doc = Document(page_content="Нормальный текст", metadata={"source": "test.md"})
        # Должен успешно обработаться
        result = parser.parse(doc)
        assert isinstance(result, ParsedDocument)


class TestMarkdownParserIntegration:
    """Тесты интеграции с BaseParser."""

    def test_inherits_from_base_parser(self):
        """Тест наследования от BaseParser."""
        parser = MarkdownParser()
        assert hasattr(parser, "can_parse")
        assert hasattr(parser, "get_source")
        assert hasattr(parser, "parse")

    def test_can_parse_method(self):
        """Тест метода can_parse."""
        parser = MarkdownParser()
        doc_md = Document(page_content="# Test", metadata={"source": "test.md"})
        doc_pdf = Document(page_content="PDF", metadata={"source": "test.pdf"})

        assert parser.can_parse(doc_md) is True
        assert parser.can_parse(doc_pdf) is False

    def test_get_source_method(self):
        """Тест метода get_source."""
        parser = MarkdownParser()
        doc = Document(page_content="# Test", metadata={"source": "test.md"})
        assert parser.get_source(doc) == "test.md"

    def test_id_generation(self):
        """Тест генерации ID элементов."""
        parser = MarkdownParser()
        doc = Document(page_content="# H1\n## H2\n### H3", metadata={"source": "test.md"})
        result = parser.parse(doc)

        assert len(result.elements) == 3
        # Проверяем, что ID уникальны
        ids = [elem.id for elem in result.elements]
        assert len(ids) == len(set(ids))
        # Проверяем формат ID (должны быть последовательными)
        assert result.elements[0].id == "00000001"
        assert result.elements[1].id == "00000002"
        assert result.elements[2].id == "00000003"


class TestMarkdownParserFullDocument:
    """Тесты парсинга полного документа со всеми элементами."""


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
        assert "Второй" in result.elements[1].content
        assert "Третий" in result.elements[2].content


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

    def test_parse_link(self):
        """Тест парсинга ссылки."""
        parser = MarkdownParser()
        content = "[Текст ссылки](https://example.com)"
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        # Ссылки могут быть обработаны как отдельные элементы или внутри параграфа
        # Проверяем, что ссылка присутствует в результате
        assert len(result.elements) >= 1
        # Может быть как LINK элемент, так и TEXT с ссылкой внутри
        link_elements = [e for e in result.elements if e.type == ElementType.LINK]
        if link_elements:
            assert link_elements[0].content == "Текст ссылки"
            assert link_elements[0].metadata.get("href") == "https://example.com"


class TestMarkdownParserImages:
    """Тесты парсинга изображений."""

    def test_parse_image(self):
        """Тест парсинга изображения."""
        parser = MarkdownParser()
        content = "![Альт текст](image.jpg)"
        doc = Document(page_content=content, metadata={"source": "test.md"})
        result = parser.parse(doc)

        # Изображения могут быть обработаны как отдельные элементы
        image_elements = [e for e in result.elements if e.type == ElementType.IMAGE]
        if image_elements:
            assert image_elements[0].metadata.get("alt") == "Альт текст"
            assert image_elements[0].metadata.get("src") == "image.jpg"


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

    def test_parse_full_markdown_file(self):
        """Тест парсинга полного markdown файла со всеми элементами."""
        parser = MarkdownParser()
        # Путь от корня проекта (используем _project_root из начала файла)
        test_file = _project_root / "tests" / "files_for_tests" / "full_markdown.md"
        
        # Если файл не существует, пропускаем тест
        if not test_file.exists():
            pytest.skip(f"Тестовый файл не найден: {test_file}")
        
        # Читаем файл и парсим

        content = test_file.read_text(encoding="utf-8")
        doc = Document(page_content=content, metadata={"source": str(test_file)})
        result = parser.parse(doc)

        # Базовые проверки
        assert isinstance(result, ParsedDocument)
        assert result.format == DocumentFormat.MARKDOWN
        assert result.source == str(test_file)
        assert len(result.elements) > 0

        # Проверяем наличие всех типов элементов
        element_types = {elem.type for elem in result.elements}
        
        # Заголовки всех уровней
        assert ElementType.HEADER_1 in element_types
        assert ElementType.HEADER_2 in element_types
        assert ElementType.HEADER_3 in element_types
        assert ElementType.HEADER_4 in element_types
        assert ElementType.HEADER_5 in element_types
        assert ElementType.HEADER_6 in element_types
        
        # Другие элементы
        assert ElementType.TEXT in element_types
        assert ElementType.LIST_ITEM in element_types
        assert ElementType.TABLE in element_types
        assert ElementType.CODE_BLOCK in element_types
        assert ElementType.LINK in element_types
        assert ElementType.IMAGE in element_types

        # Проверяем конкретные элементы
        headers = [e for e in result.elements if e.type.name.startswith("HEADER_")]
        assert len(headers) >= 6  # Должно быть минимум 6 заголовков (H1-H6)

        # Проверяем заголовок H1
        h1 = next((e for e in result.elements if e.type == ElementType.HEADER_1), None)
        assert h1 is not None
        assert "Заголовок уровня 1" in h1.content
        assert h1.parent_id is None  # H1 не должен иметь родителя

        # Проверяем списки
        list_items = [e for e in result.elements if e.type == ElementType.LIST_ITEM]
        assert len(list_items) >= 5  # Должно быть минимум 5 элементов списка

        # Проверяем таблицу
        tables = [e for e in result.elements if e.type == ElementType.TABLE]
        assert len(tables) >= 1
        assert "Заголовок 1" in tables[0].content

        # Проверяем код-блоки
        code_blocks = [e for e in result.elements if e.type == ElementType.CODE_BLOCK]
        assert len(code_blocks) >= 2  # Должно быть минимум 2 блока кода
        python_block = next((e for e in code_blocks if e.metadata.get("language") == "python"), None)
        assert python_block is not None
        assert "def hello_world" in python_block.content

        # Проверяем ссылки
        links = [e for e in result.elements if e.type == ElementType.LINK]
        assert len(links) >= 2  # Должно быть минимум 2 ссылки
        google_link = next((e for e in links if "google.com" in e.metadata.get("href", "")), None)
        assert google_link is not None

        # Проверяем изображения
        images = [e for e in result.elements if e.type == ElementType.IMAGE]
        assert len(images) >= 2  # Должно быть минимум 2 изображения

        # Проверяем цитаты (обрабатываются как TEXT с metadata quote=True)
        quotes = [e for e in result.elements if e.metadata.get("quote") is True]
        assert len(quotes) >= 2  # Должно быть минимум 2 цитаты

        # Проверяем иерархию заголовков
        h2_elements = [e for e in result.elements if e.type == ElementType.HEADER_2]
        for h2 in h2_elements:
            # H2 должен иметь H1 как родителя (если есть H1 выше)
            if h2.parent_id:
                parent = next((e for e in result.elements if e.id == h2.parent_id), None)
                if parent:
                    assert parent.type in (ElementType.HEADER_1, ElementType.HEADER_2)

        # Проверяем, что элементы под заголовками имеют правильного родителя
        h2_markdown = next((e for e in result.elements if e.type == ElementType.HEADER_2 and "Маркированный список" in e.content), None)
        if h2_markdown:
            # Элементы после этого заголовка должны иметь его как родителя
            h2_index = result.elements.index(h2_markdown)
            next_elements = result.elements[h2_index + 1:h2_index + 4]  # Следующие несколько элементов
            for elem in next_elements:
                if elem.type != ElementType.HEADER_2:  # Пропускаем следующий H2
                    # Элемент должен быть под H2 или под другим заголовком
                    assert elem.parent_id is not None

        # Проверяем уникальность ID
        ids = [elem.id for elem in result.elements]
        assert len(ids) == len(set(ids)), "Все ID должны быть уникальными"

        # Проверяем, что все элементы валидны
        for elem in result.elements:
            elem.validate()  # Не должно вызывать исключений

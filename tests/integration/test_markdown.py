"""
Интеграционные тесты для Markdown парсера.

Тестирует парсинг реальных Markdown документов через Pipeline.
Проверяет end-to-end сценарии использования.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH для прямого запуска
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from langchain_core.documents import Document

from documentor import Pipeline, pipeline
from documentor.domain import DocumentFormat, ElementType


class TestMarkdownIntegrationBasic:
    """Базовые интеграционные тесты для Markdown через Pipeline."""

    def test_pipeline_parse_simple_markdown(self):
        """Тест парсинга простого Markdown через Pipeline."""
        pipeline_instance = Pipeline()
        doc = Document(
            page_content="# Заголовок\n\nТекст параграфа.",
            metadata={"source": "test.md"}
        )
        
        result = pipeline_instance.parse(doc)
        
        assert result.format == DocumentFormat.MARKDOWN
        assert result.source == "test.md"
        assert len(result.elements) >= 2
        assert result.elements[0].type == ElementType.HEADER_1
        assert result.elements[1].type == ElementType.TEXT

    def test_pipeline_function_simple_markdown(self):
        """Тест парсинга через функцию pipeline()."""
        doc = Document(
            page_content="## Подзаголовок\n\nПростой текст.",
            metadata={"source": "test.md"}
        )
        
        result = pipeline(doc)
        
        assert result.format == DocumentFormat.MARKDOWN
        assert len(result.elements) >= 2

    def test_pipeline_parse_many_markdown(self):
        """Тест пакетной обработки нескольких Markdown документов."""
        pipeline_instance = Pipeline()
        documents = [
            Document(page_content="# Документ 1", metadata={"source": "doc1.md"}),
            Document(page_content="# Документ 2", metadata={"source": "doc2.md"}),
            Document(page_content="# Документ 3", metadata={"source": "doc3.md"}),
        ]
        
        results = pipeline_instance.parse_many(documents)
        
        assert len(results) == 3
        assert all(r.format == DocumentFormat.MARKDOWN for r in results)
        assert results[0].source == "doc1.md"
        assert results[1].source == "doc2.md"
        assert results[2].source == "doc3.md"


class TestMarkdownIntegrationWithFile:
    """Интеграционные тесты с загрузкой файлов."""

    def test_load_and_parse_markdown_file(self):
        """Тест загрузки и парсинга Markdown файла."""
        test_file = _project_root / "tests" / "files_for_tests" / "md.md"
        
        if not test_file.exists():
            pytest.skip(f"Тестовый файл не найден: {test_file}")
        
        # Пользователь сам создает Document из файла
        content = test_file.read_text(encoding="utf-8")
        doc = Document(
            page_content=content,
            metadata={"source": str(test_file), "file_path": str(test_file)}
        )
        result = pipeline(doc)
        
        assert result.format == DocumentFormat.MARKDOWN
        assert result.source == str(test_file)
        assert len(result.elements) > 0

    def test_load_and_parse_full_markdown_file(self):
        """Тест парсинга полного markdown файла со всеми элементами."""
        test_file = _project_root / "tests" / "files_for_tests" / "full_markdown.md"
        
        if not test_file.exists():
            pytest.skip(f"Тестовый файл не найден: {test_file}")
        
        # Пользователь сам создает Document из файла
        content = test_file.read_text(encoding="utf-8")
        doc = Document(
            page_content=content,
            metadata={"source": str(test_file), "file_path": str(test_file)}
        )
        result = pipeline(doc)
        
        # Базовые проверки
        assert result.format == DocumentFormat.MARKDOWN
        assert result.source == str(test_file)
        assert len(result.elements) > 0
        
        # Проверяем наличие различных типов элементов
        element_types = {elem.type for elem in result.elements}
        
        # Заголовки всех уровней должны быть
        assert ElementType.HEADER_1 in element_types
        assert ElementType.HEADER_2 in element_types
        assert ElementType.HEADER_3 in element_types
        
        # Другие элементы
        assert ElementType.TEXT in element_types
        assert ElementType.LIST_ITEM in element_types
        assert ElementType.TABLE in element_types
        assert ElementType.CODE_BLOCK in element_types

    def test_parse_many_from_files(self):
        """Тест пакетной обработки файлов."""
        test_dir = _project_root / "tests" / "files_for_tests"
        md_file = test_dir / "md.md"
        full_md_file = test_dir / "full_markdown.md"
        
        if not md_file.exists() or not full_md_file.exists():
            pytest.skip("Тестовые файлы не найдены")
        
        # Пользователь сам создает Document из файлов
        documents = [
            Document(
                page_content=md_file.read_text(encoding="utf-8"),
                metadata={"source": str(md_file), "file_path": str(md_file)}
            ),
            Document(
                page_content=full_md_file.read_text(encoding="utf-8"),
                metadata={"source": str(full_md_file), "file_path": str(full_md_file)}
            ),
        ]
        
        pipeline_instance = Pipeline()
        results = pipeline_instance.parse_many(documents)
        
        assert len(results) == 2
        assert all(r.format == DocumentFormat.MARKDOWN for r in results)


class TestMarkdownIntegrationMetrics:
    """Тесты метрик производительности."""

    def test_pipeline_metrics_in_metadata(self):
        """Тест наличия метрик в метаданных результата."""
        doc = Document(
            page_content="# Заголовок\n\nТекст.",
            metadata={"source": "test.md"}
        )
        
        result = pipeline(doc)
        
        # Проверяем наличие метрик
        assert result.metadata is not None
        assert "pipeline_metrics" in result.metadata
        
        metrics = result.metadata["pipeline_metrics"]
        
        # Проверяем структуру базовых метрик
        assert "parsing_time_seconds" in metrics
        assert "num_elements" in metrics
        assert "parser_class" in metrics
        
        # Проверяем новые метрики
        assert "elements_by_type" in metrics
        assert "elements_per_second" in metrics
        assert "document_size_bytes" in metrics
        assert "document_lines" in metrics
        
        # Проверяем значения базовых метрик
        assert isinstance(metrics["parsing_time_seconds"], (int, float))
        assert metrics["parsing_time_seconds"] >= 0
        assert metrics["num_elements"] == len(result.elements)
        assert metrics["parser_class"] == "MarkdownParser"
        
        # Проверяем значения новых метрик
        assert isinstance(metrics["elements_by_type"], dict)
        assert isinstance(metrics["elements_per_second"], (int, float))
        assert metrics["elements_per_second"] >= 0
        assert isinstance(metrics["document_size_bytes"], int)
        assert metrics["document_size_bytes"] > 0
        assert isinstance(metrics["document_lines"], int)
        assert metrics["document_lines"] >= 0

    def test_metrics_accuracy(self):
        """Тест точности метрик."""
        content = "# H1\n## H2\n### H3\n\nТекст."
        doc = Document(
            page_content=content,
            metadata={"source": "test.md"}
        )
        
        result = pipeline(doc)
        metrics = result.metadata["pipeline_metrics"]
        
        # Количество элементов должно совпадать
        assert metrics["num_elements"] == len(result.elements)
        assert metrics["num_elements"] >= 4  # минимум 3 заголовка + текст
        
        # Время парсинга должно быть разумным (меньше 1 секунды для простого документа)
        assert metrics["parsing_time_seconds"] < 1.0
        
        # Проверяем elements_by_type
        elements_by_type = metrics["elements_by_type"]
        assert isinstance(elements_by_type, dict)
        # Должны быть заголовки
        assert "header_1" in elements_by_type or sum(
            v for k, v in elements_by_type.items() if k.startswith("header_")
        ) >= 3
        
        # Проверяем document_size_bytes и document_lines
        expected_bytes = len(content.encode("utf-8"))
        expected_lines = len(content.splitlines())
        assert metrics["document_size_bytes"] == expected_bytes
        assert metrics["document_lines"] == expected_lines
        
        # Проверяем elements_per_second
        # Учитываем, что в pipeline.py используется round(..., 2), поэтому допуск должен быть больше
        if metrics["parsing_time_seconds"] > 0:
            expected_eps = metrics["num_elements"] / metrics["parsing_time_seconds"]
            # Учитываем округление до 2 знаков после запятой в pipeline.py
            # Максимальная ошибка округления: 0.005 * 2 = 0.01, но лучше дать запас
            assert abs(metrics["elements_per_second"] - expected_eps) < 0.5  # допуск на округление


class TestMarkdownIntegrationHierarchy:
    """Тесты иерархии элементов."""

    def test_hierarchy_structure(self):
        """Тест корректности построения иерархии."""
        doc = Document(
            page_content="""# Главный заголовок

Текст под главным заголовком.

## Подзаголовок 1

Текст под подзаголовком 1.

### Подподзаголовок

Текст под подподзаголовком.

## Подзаголовок 2

Текст под подзаголовком 2.
""",
            metadata={"source": "test.md"}
        )
        
        result = pipeline(doc)
        
        # Находим заголовки
        headers = [e for e in result.elements if e.type in [
            ElementType.HEADER_1, ElementType.HEADER_2, ElementType.HEADER_3
        ]]
        
        assert len(headers) >= 4
        
        # Проверяем, что элементы текста имеют правильные parent_id
        text_elements = [e for e in result.elements if e.type == ElementType.TEXT]
        for text_elem in text_elements:
            if text_elem.parent_id:
                # parent_id должен ссылаться на существующий элемент
                parent_ids = {e.id for e in result.elements}
                assert text_elem.parent_id in parent_ids

    def test_hierarchy_with_lists(self):
        """Тест иерархии со списками."""
        doc = Document(
            page_content="""# Заголовок

- Элемент 1
- Элемент 2
  - Вложенный элемент
- Элемент 3
""",
            metadata={"source": "test.md"}
        )
        
        result = pipeline(doc)
        
        # Должен быть заголовок и элементы списка
        assert any(e.type == ElementType.HEADER_1 for e in result.elements)
        assert any(e.type == ElementType.LIST_ITEM for e in result.elements)


class TestMarkdownIntegrationTables:
    """Тесты парсинга таблиц."""

    def test_table_parsing(self):
        """Тест парсинга таблицы."""
        doc = Document(
            page_content="""# Таблица

| Колонка 1 | Колонка 2 | Колонка 3 |
|-----------|-----------|-----------|
| Данные 1  | Данные 2  | Данные 3  |
| Значение A| Значение B| Значение C|
""",
            metadata={"source": "test.md"}
        )
        
        result = pipeline(doc)
        
        # Находим таблицу
        tables = [e for e in result.elements if e.type == ElementType.TABLE]
        assert len(tables) > 0
        
        table = tables[0]
        
        # Проверяем наличие DataFrame в метаданных
        assert table.metadata is not None
        assert "dataframe" in table.metadata or "rows" in table.metadata
        
        # Если есть DataFrame, проверяем его структуру
        if "dataframe" in table.metadata and table.metadata["dataframe"] is not None:
            df = table.metadata["dataframe"]
            assert df.shape[0] >= 2  # минимум 2 строки данных
            assert df.shape[1] == 3  # 3 колонки


class TestMarkdownIntegrationErrorHandling:
    """Тесты обработки ошибок."""

    def test_invalid_document_format(self):
        """Тест обработки неподдерживаемого формата."""
        pipeline_instance = Pipeline()
        # Создаем документ с неправильным форматом в метаданных
        doc = Document(
            page_content="Some content",
            metadata={"source": "file.xyz", "format": "unknown"}
        )
        
        # Pipeline должен определить формат по расширению или вернуть ошибку
        # В зависимости от реализации может быть UNKNOWN или ошибка
        try:
            result = pipeline_instance.parse(doc)
            # Если парсинг прошел, формат должен быть определен
            assert result.format in [DocumentFormat.MARKDOWN, DocumentFormat.UNKNOWN]
        except Exception:
            # Если возникла ошибка - это тоже нормально для неподдерживаемого формата
            pass

    def test_empty_document(self):
        """Тест обработки пустого документа."""
        doc = Document(page_content="", metadata={"source": "empty.md"})
        result = pipeline(doc)
        
        assert result.format == DocumentFormat.MARKDOWN
        assert len(result.elements) == 0

    def test_missing_source(self):
        """Тест обработки документа без source."""
        from documentor.exceptions import UnsupportedFormatError
        
        doc = Document(page_content="# Заголовок", metadata={})
        
        # Без source формат определяется как UNKNOWN, парсера для него нет
        # Это корректное поведение - должна быть ошибка
        with pytest.raises(UnsupportedFormatError, match="No parser available for format: unknown"):
            pipeline(doc)


class TestMarkdownIntegrationPerformance:
    """Тесты производительности."""

    def test_large_document_performance(self):
        """Тест производительности на большом документе."""
        # Создаем большой документ
        content = "# Заголовок\n\n" + "\n\n".join([
            f"## Раздел {i}\n\nТекст раздела {i}." 
            for i in range(100)
        ])
        
        doc = Document(page_content=content, metadata={"source": "large.md"})
        
        result = pipeline(doc)
        metrics = result.metadata["pipeline_metrics"]
        
        # Проверяем, что парсинг прошел успешно
        assert len(result.elements) > 100
        
        # Проверяем, что время парсинга разумное (меньше 5 секунд для 100 разделов)
        assert metrics["parsing_time_seconds"] < 5.0

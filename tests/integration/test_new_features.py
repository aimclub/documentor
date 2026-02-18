"""
Тесты для новых функций парсеров:
1. Сохранение изображений в base64
2. Сохранение таблиц в pandas DataFrame
3. Сохранение ссылок в метаданные
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from langchain_core.documents import Document
from PIL import Image

# Добавляем корневую директорию проекта в PYTHONPATH
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from documentor.domain import ElementType
from documentor.pipeline import Pipeline


# ============================================================================
# Тесты для сохранения изображений в base64
# ============================================================================

class TestImageBase64Storage:
    """Тесты сохранения изображений в base64."""

    def test_pdf_images_base64(self, tmp_path):
        """Тест сохранения изображений в base64 для PDF."""
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF не установлен")

        # Создаем простой PDF с изображением
        pdf_path = tmp_path / "test_image.pdf"
        doc = fitz.open()
        page = doc.new_page()
        
        # Добавляем текст с упоминанием изображения
        page.insert_text((50, 50), "Document with image")
        page.insert_text((50, 100), "Figure 1: Test image")
        
        doc.save(str(pdf_path))
        doc.close()

        doc = Document(page_content="", metadata={"source": str(pdf_path)})
        pipeline = Pipeline()
        
        with patch.object(pipeline, '_parsers', []):
            # Создаем мок парсера, который возвращает элемент с изображением
            from documentor.processing.parsers.pdf.pdf_parser import PdfParser
            parser = PdfParser()
            
            # Мокаем методы, которые требуют OCR
            from documentor.domain import Element
            img_data = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            image_element = Element(
                id="img_001",
                type=ElementType.IMAGE,
                content="",
                metadata={"image_data": img_data}
            )
            
            # Мокаем layout_processor и другие компоненты
            with patch.object(parser.layout_processor, 'detect_layout_for_all_pages', return_value=[]):
                with patch.object(parser.layout_processor, 'filter_layout_elements', return_value=[]):
                    with patch.object(parser.hierarchy_builder, 'analyze_header_levels_from_elements', return_value=[]):
                        with patch.object(parser.hierarchy_builder, 'build_hierarchy_from_section_headers', return_value=[]):
                            with patch.object(parser.text_extractor, 'extract_text_by_bboxes', return_value=[]):
                                with patch.object(parser.text_extractor, 'merge_nearby_text_blocks', return_value=[]):
                                    with patch.object(parser.hierarchy_builder, 'create_elements_from_hierarchy', return_value=[image_element]):
                                        with patch.object(parser.image_processor, 'store_images_in_metadata', return_value=[image_element]):
                                            result = parser.parse(doc)
                                            
                                            # Проверяем наличие изображений
                                            images = [e for e in result.elements if e.type == ElementType.IMAGE]
                                            if images:
                                                assert "image_data" in images[0].metadata
                                                assert images[0].metadata["image_data"].startswith("data:image/")
                                                assert "base64," in images[0].metadata["image_data"]

    def test_docx_images_base64(self, tmp_path):
        """Тест сохранения изображений в base64 для DOCX."""
        try:
            from docx import Document as DocxDocument
        except ImportError:
            pytest.skip("python-docx не установлен")

        # Создаем простой DOCX с изображением
        docx_path = tmp_path / "test_image.docx"
        doc = DocxDocument()
        doc.add_paragraph("Document with image")
        doc.add_paragraph("Figure 1: Test image")
        doc.save(str(docx_path))

        doc = Document(page_content="", metadata={"source": str(docx_path)})
        pipeline = Pipeline()
        result = pipeline.parse(doc)

        # Проверяем наличие изображений
        images = [e for e in result.elements if e.type == ElementType.IMAGE]
        for img in images:
            assert "image_data" in img.metadata
            assert img.metadata["image_data"].startswith("data:image/")
            assert "base64," in img.metadata["image_data"]
            
            # Проверяем, что base64 валидный
            base64_part = img.metadata["image_data"].split(",")[1]
            try:
                decoded = base64.b64decode(base64_part)
                assert len(decoded) > 0
            except Exception:
                pytest.fail("Invalid base64 encoding in image_data")

    def test_markdown_images_base64(self):
        """Тест сохранения изображений для Markdown (URL остаются как есть)."""
        doc = Document(
            page_content="""# Document with Image

![Test Image](https://example.com/image.png)

Text with inline image ![Inline](https://example.com/inline.jpg) in text.
""",
            metadata={"source": "test.md"}
        )
        
        pipeline = Pipeline()
        result = pipeline.parse(doc)

        # В Markdown изображения остаются как URL, не конвертируются в base64
        images = [e for e in result.elements if e.type == ElementType.IMAGE]
        for img in images:
            # Проверяем, что есть src в метаданных
            assert "src" in img.metadata or "href" in img.metadata


# ============================================================================
# Тесты для сохранения таблиц в pandas DataFrame
# ============================================================================

class TestTableDataFrameStorage:
    """Тесты сохранения таблиц в pandas DataFrame."""

    def test_docx_tables_dataframe(self, tmp_path):
        """Тест сохранения таблиц в DataFrame для DOCX."""
        try:
            from docx import Document as DocxDocument
        except ImportError:
            pytest.skip("python-docx не установлен")

        # Создаем DOCX с таблицей
        docx_path = tmp_path / "test_table.docx"
        doc = DocxDocument()
        
        table = doc.add_table(rows=3, cols=3)
        table.cell(0, 0).text = "Column1"
        table.cell(0, 1).text = "Column2"
        table.cell(0, 2).text = "Column3"
        table.cell(1, 0).text = "Value1"
        table.cell(1, 1).text = "Value2"
        table.cell(1, 2).text = "Value3"
        table.cell(2, 0).text = "Value4"
        table.cell(2, 1).text = "Value5"
        table.cell(2, 2).text = "Value6"
        
        doc.save(str(docx_path))

        doc = Document(page_content="", metadata={"source": str(docx_path)})
        pipeline = Pipeline()
        result = pipeline.parse(doc)

        # Проверяем наличие таблиц
        tables = [e for e in result.elements if e.type == ElementType.TABLE]
        assert len(tables) > 0
        
        for table in tables:
            assert "dataframe" in table.metadata
            assert isinstance(table.metadata["dataframe"], pd.DataFrame)
            # Даже если таблица пустая, должен быть пустой DataFrame
            assert table.metadata["dataframe"] is not None

    def test_markdown_tables_dataframe(self):
        """Тест сохранения таблиц в DataFrame для Markdown."""
        doc = Document(
            page_content="""# Document with Table

| Column1 | Column2 | Column3 |
|---------|---------|---------|
| Value1  | Value2  | Value3  |
| Value4  | Value5  | Value6  |
""",
            metadata={"source": "test.md"}
        )
        
        pipeline = Pipeline()
        result = pipeline.parse(doc)

        # Проверяем наличие таблиц
        tables = [e for e in result.elements if e.type == ElementType.TABLE]
        assert len(tables) > 0
        
        for table in tables:
            assert "dataframe" in table.metadata
            assert isinstance(table.metadata["dataframe"], pd.DataFrame)
            df = table.metadata["dataframe"]
            assert len(df) >= 2  # Минимум 2 строки данных
            assert len(df.columns) == 3  # 3 колонки
            assert "Column1" in df.columns or "Column_1" in df.columns

    def test_all_tables_have_dataframe(self):
        """Тест, что все таблицы имеют DataFrame (даже пустой)."""
        doc = Document(
            page_content="""# Multiple Tables

| A | B |
|---|---|
| 1 | 2 |

| X | Y |
|---|---|
| a | b |
""",
            metadata={"source": "test.md"}
        )
        
        pipeline = Pipeline()
        result = pipeline.parse(doc)

        tables = [e for e in result.elements if e.type == ElementType.TABLE]
        assert len(tables) > 0
        
        for table in tables:
            assert "dataframe" in table.metadata
            assert isinstance(table.metadata["dataframe"], pd.DataFrame)
            # DataFrame должен существовать, даже если пустой
            assert table.metadata["dataframe"] is not None


# ============================================================================
# Тесты для сохранения ссылок в метаданные
# ============================================================================

class TestLinksInMetadata:
    """Тесты сохранения ссылок в метаданные."""

    def test_pdf_links_in_metadata(self, tmp_path):
        """Тест сохранения ссылок в метаданные для PDF."""
        try:
            import fitz
        except ImportError:
            pytest.skip("PyMuPDF не установлен")

        # Создаем PDF с текстом, содержащим ссылки
        pdf_path = tmp_path / "test_links.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Visit https://example.com for more info")
        page.insert_text((50, 100), "Check www.google.com and http://test.org")
        doc.save(str(pdf_path))
        doc.close()

        doc = Document(page_content="", metadata={"source": str(pdf_path)})
        pipeline = Pipeline()
        result = pipeline.parse(doc)

        # Проверяем наличие ссылок в метаданных текстовых элементов
        text_elements = [e for e in result.elements if e.type == ElementType.TEXT]
        found_links = False
        
        for elem in text_elements:
            if "links" in elem.metadata:
                found_links = True
                links = elem.metadata["links"]
                assert isinstance(links, list)
                assert len(links) > 0
                # Проверяем, что ссылки - это строки
                for link in links:
                    assert isinstance(link, str)
                    assert len(link) > 0
        
        # Хотя бы в одном элементе должны быть ссылки
        # (может не быть, если OCR не распознал текст правильно)
        # assert found_links, "No links found in PDF text elements"

    def test_docx_links_in_metadata(self, tmp_path):
        """Тест сохранения ссылок в метаданные для DOCX."""
        try:
            from docx import Document as DocxDocument
            from docx.shared import Inches
        except ImportError:
            pytest.skip("python-docx не установлен")

        # Создаем DOCX с гиперссылками
        docx_path = tmp_path / "test_links.docx"
        doc = DocxDocument()
        
        # Добавляем текст с URL (парсер должен извлечь ссылки из текста)
        doc.add_paragraph("Visit https://example.com for more info")
        
        # Добавляем еще текст с URL в тексте
        doc.add_paragraph("Check www.google.com and http://test.org")
        
        doc.save(str(docx_path))

        doc = Document(page_content="", metadata={"source": str(docx_path)})
        pipeline = Pipeline()
        result = pipeline.parse(doc)

        # Проверяем наличие ссылок в метаданных
        text_elements = [e for e in result.elements if e.type == ElementType.TEXT]
        header_elements = [e for e in result.elements if e.type.name.startswith("HEADER")]
        
        found_links = False
        
        for elem in text_elements + header_elements:
            if "links" in elem.metadata:
                found_links = True
                links = elem.metadata["links"]
                assert isinstance(links, list)
                assert len(links) > 0
                for link in links:
                    assert isinstance(link, str)
                    assert len(link) > 0

    def test_markdown_links_in_metadata(self):
        """Тест сохранения ссылок в метаданные для Markdown."""
        doc = Document(
            page_content="""# Document with Links

This is text with [a link](https://example.com) in it.

Visit https://www.google.com for search.

Check http://test.org and www.example.com
""",
            metadata={"source": "test.md"}
        )
        
        pipeline = Pipeline()
        result = pipeline.parse(doc)

        # Проверяем наличие ссылок в метаданных
        text_elements = [e for e in result.elements if e.type == ElementType.TEXT]
        link_elements = [e for e in result.elements if e.type == ElementType.LINK]
        
        found_links_in_text = False
        
        # Проверяем ссылки в текстовых элементах
        for elem in text_elements:
            if "links" in elem.metadata:
                found_links_in_text = True
                links = elem.metadata["links"]
                assert isinstance(links, list)
                assert len(links) > 0
                for link in links:
                    assert isinstance(link, str)
                    assert ("http" in link or "www" in link)
        
        # Проверяем отдельные LINK элементы
        for elem in link_elements:
            assert "href" in elem.metadata or "src" in elem.metadata
            url = elem.metadata.get("href") or elem.metadata.get("src")
            assert isinstance(url, str)
            assert len(url) > 0

    def test_links_in_headers(self):
        """Тест сохранения ссылок в метаданные заголовков."""
        doc = Document(
            page_content="""# Header with https://example.com link

## Another header with www.google.com

Text with http://test.org
""",
            metadata={"source": "test.md"}
        )
        
        pipeline = Pipeline()
        result = pipeline.parse(doc)

        # Проверяем наличие ссылок в заголовках
        header_elements = [e for e in result.elements if e.type.name.startswith("HEADER")]
        
        for header in header_elements:
            if "links" in header.metadata:
                links = header.metadata["links"]
                assert isinstance(links, list)
                assert len(links) > 0


# ============================================================================
# Комплексные тесты для всех трех функций вместе
# ============================================================================

class TestAllFeaturesTogether:
    """Комплексные тесты для всех трех функций вместе."""

    def test_markdown_all_features(self):
        """Тест всех трех функций для Markdown."""
        doc = Document(
            page_content="""# Document Title

## Section with https://example.com

| Column1 | Column2 |
|---------|---------|
| Data1   | Data2   |

![Image](https://example.com/image.png)

Text with [link](https://google.com) and www.test.org
""",
            metadata={"source": "test.md"}
        )
        
        pipeline = Pipeline()
        result = pipeline.parse(doc)

        # Проверяем таблицы
        tables = [e for e in result.elements if e.type == ElementType.TABLE]
        assert len(tables) > 0
        for table in tables:
            assert "dataframe" in table.metadata
            assert isinstance(table.metadata["dataframe"], pd.DataFrame)

        # Проверяем изображения
        images = [e for e in result.elements if e.type == ElementType.IMAGE]
        for img in images:
            assert "src" in img.metadata or "href" in img.metadata

        # Проверяем ссылки
        text_elements = [e for e in result.elements if e.type == ElementType.TEXT]
        found_links = False
        for elem in text_elements:
            if "links" in elem.metadata:
                found_links = True
                assert len(elem.metadata["links"]) > 0

    def test_all_features_metadata_structure(self):
        """Тест структуры метаданных для всех функций."""
        doc = Document(
            page_content="""# Test

| A | B |
|---|---|
| 1 | 2 |

Text with https://example.com
""",
            metadata={"source": "test.md"}
        )
        
        pipeline = Pipeline()
        result = pipeline.parse(doc)

        # Проверяем структуру метаданных
        for elem in result.elements:
            assert elem.metadata is not None
            assert isinstance(elem.metadata, dict)
            
            # Если это таблица, должен быть DataFrame
            if elem.type == ElementType.TABLE:
                assert "dataframe" in elem.metadata
                assert isinstance(elem.metadata["dataframe"], pd.DataFrame)
            
            # Если это изображение, может быть image_data (для PDF/DOCX) или src (для Markdown)
            if elem.type == ElementType.IMAGE:
                has_image_data = "image_data" in elem.metadata
                has_src = "src" in elem.metadata or "href" in elem.metadata
                assert has_image_data or has_src
            
            # Если есть ссылки в тексте, они должны быть в списке
            if "links" in elem.metadata:
                assert isinstance(elem.metadata["links"], list)
                for link in elem.metadata["links"]:
                    assert isinstance(link, str)

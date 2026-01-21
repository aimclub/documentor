"""
Парсер для DOCX документов.

Логика работы:
1. Извлечение текста и метаданных из DOCX (python-docx)
2. Разбиение текста на чанки с перекрытием (~3000 символов)
3. LLM семантический анализ для определения заголовков по смыслу
4. Проверка и корректировка разметки одним из двух способов:
   - Вариант 1: Проверка через встроенные стили DOCX (Heading 1-6)
   - Вариант 2: Проверка через LLM с XML разметкой DOCX
5. Построение иерархии элементов
6. Обработка структурных элементов (изображения, таблицы, формулы)
7. Разрешение ссылок на элементы (см. рис. 1, см. табл. 2)

Особенности:
- Всегда сначала используется LLM семантический анализ
- Затем проверка и корректировка через стили или XML через LLM
- Решение проблемы порядка изображений (исправление несоответствия порядка)
"""

from __future__ import annotations

from typing import List

from langchain_core.documents import Document

from ....domain import DocumentFormat, Element, ElementType, ParsedDocument
from ..base import BaseParser


class DocxParser(BaseParser):
    format = DocumentFormat.DOCX

    def parse(self, document: Document) -> ParsedDocument:
        source = self.get_source(document)
        elements: List[Element] = []
        text = (document.page_content or "").strip()

        if text:
            for paragraph in self._split_paragraphs(text):
                elements.append(
                    Element(
                        id=self.id_generator.next_id(),
                        type=ElementType.TEXT,
                        content=paragraph,
                        parent_id=None,
                        metadata={"parser_hint": "basic_text"},
                    )
                )

        return ParsedDocument(
            source=source,
            format=self.format,
            elements=elements,
            metadata={"parser": "docx", "status": "skeleton"},
        )

    def _split_paragraphs(self, text: str) -> List[str]:
        paragraphs = [block.strip() for block in text.split("\n\n")]
        return [paragraph for paragraph in paragraphs if paragraph]
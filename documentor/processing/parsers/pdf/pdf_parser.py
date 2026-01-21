"""
Парсер для PDF документов.

Поддерживает два пути обработки:
1. Извлекаемый текст: PdfPlumber → разбиение на чанки → LLM детектирование заголовков
2. OCR пайплайн: рендеринг страниц → Dots.OCR layout → Qwen OCR → структурирование

TODO: Реализовать полную логику:
- Определение типа PDF (текст или скан)
- Интеграция с PdfPlumber для извлечения текста
- Интеграция с OCR пайплайном (Dots.OCR + Qwen OCR)
- Построение иерархии элементов
"""

from __future__ import annotations

from typing import List

from langchain_core.documents import Document

from ....domain import DocumentFormat, Element, ElementType, ParsedDocument
from ..base import BaseParser


class PdfParser(BaseParser):
    format = DocumentFormat.PDF

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
            metadata={"parser": "pdf", "status": "skeleton"},
        )

    def _split_paragraphs(self, text: str) -> List[str]:
        paragraphs = [block.strip() for block in text.split("\n\n")]
        return [paragraph for paragraph in paragraphs if paragraph]
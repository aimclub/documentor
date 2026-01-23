"""
Парсер для PDF документов.

Поддерживает два пути обработки:
1. Извлекаемый текст: PdfPlumber → разбиение на чанки → LLM детектирование заголовков
2. OCR пайплайн: рендеринг страниц → Dots.OCR layout → Qwen OCR → структурирование

Текущий статус: Заглушка (базовая обработка текста)
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
from ....exceptions import ParsingError
from ..base import BaseParser


class PdfParser(BaseParser):
    """
    Парсер для PDF документов.

    Текущая реализация - заглушка, которая разбивает текст на параграфы.
    В будущем будет реализована полная логика с двумя путями обработки:
    - Текстовый путь (PdfPlumber + LLM)
    - OCR путь (Dots.OCR + Qwen OCR)
    """

    format = DocumentFormat.PDF

    def parse(self, document: Document) -> ParsedDocument:
        """
        Парсит PDF документ (заглушка).

        Args:
            document: LangChain Document с PDF контентом.

        Returns:
            ParsedDocument: Структурированное представление документа.

        Raises:
            ValidationError: Если входные данные невалидны.
            UnsupportedFormatError: Если формат документа не поддерживается.
            ParsingError: Если произошла ошибка при парсинге.
        """
        self._validate_input(document)

        source = self.get_source(document)
        self._log_parsing_start(source)

        try:
            text = (document.page_content or "").strip()
            elements: List[Element] = []

            if text:
                for paragraph in self._split_paragraphs(text):
                    element = self._create_element(
                        type=ElementType.TEXT,
                        content=paragraph,
                        metadata={"parser_hint": "basic_text", "status": "skeleton"},
                    )
                    elements.append(element)

            parsed_document = ParsedDocument(
                source=source,
                format=self.format,
                elements=elements,
                metadata={"parser": "pdf", "status": "skeleton"},
            )

            self._validate_parsed_document(parsed_document)
            self._log_parsing_end(source, len(elements))

            return parsed_document

        except Exception as e:
            error_msg = f"Ошибка при парсинге PDF документа (источник: {source})"
            self._logger.error(f"{error_msg}. Исходная ошибка: {e}")
            raise ParsingError(error_msg, source=source, original_error=e) from e

    def _split_paragraphs(self, text: str) -> List[str]:
        """
        Разбивает текст на параграфы.

        Args:
            text: Текст для разбиения.

        Returns:
            Список параграфов.
        """
        paragraphs = [block.strip() for block in text.split("\n\n")]
        return [paragraph for paragraph in paragraphs if paragraph]
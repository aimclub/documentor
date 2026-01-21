"""
Главный пайплайн обработки документов.

Содержит класс Pipeline и функцию pipeline для обработки документов
в формате LangChain Document.

Основная логика:
1. Определение формата документа
2. Выбор соответствующего парсера
3. Парсинг документа в структурированный формат
4. Возврат ParsedDocument с элементами и иерархией
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from langchain_core.documents import Document

from .domain import ParsedDocument
from .processing.loader.loader import detect_document_format
from .processing.parsers.base import BaseParser
from .processing.parsers.docx.docx_parser import DocxParser
from .processing.parsers.md.md_parser import MarkdownParser
from .processing.parsers.pdf.pdf_parser import PdfParser


class Pipeline:
    def __init__(self, parsers: Optional[Iterable[BaseParser]] = None) -> None:
        parser_list = list(parsers) if parsers is not None else [
            MarkdownParser(),
            DocxParser(),
            PdfParser(),
        ]
        self._parsers = parser_list
        self._parsers_by_format = {parser.format: parser for parser in parser_list}

    def parse(self, document: Document) -> ParsedDocument:
        format_ = detect_document_format(document)
        parser = self._parsers_by_format.get(format_)
        if parser is None:
            raise ValueError(f"Нет парсера для формата: {format_.value}")
        return parser.parse(document)

    def parse_many(self, documents: Iterable[Document]) -> List[ParsedDocument]:
        return [self.parse(document) for document in documents]


def pipeline(document: Document, pipeline_instance: Optional[Pipeline] = None) -> ParsedDocument:
    active_pipeline = pipeline_instance or Pipeline()
    return active_pipeline.parse(document)


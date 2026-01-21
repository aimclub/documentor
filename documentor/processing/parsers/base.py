"""
Базовый класс для всех парсеров документов.

Определяет интерфейс для парсинга документов различных форматов.
Все парсеры (MarkdownParser, PdfParser, DocxParser) наследуются от этого класса.

Основные методы:
- parse() - парсинг документа (абстрактный метод)
- can_parse() - проверка возможности парсинга документа
- get_source() - получение источника документа
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from langchain_core.documents import Document

from ...domain import DocumentFormat, ElementIdGenerator, ParsedDocument
from ..loader.loader import detect_document_format, get_document_source


class BaseParser(ABC):
    format: DocumentFormat = DocumentFormat.UNKNOWN

    def __init__(self, id_generator: Optional[ElementIdGenerator] = None) -> None:
        self._id_generator = id_generator or ElementIdGenerator()

    @property
    def id_generator(self) -> ElementIdGenerator:
        return self._id_generator

    def can_parse(self, document: Document) -> bool:
        return detect_document_format(document) == self.format

    def get_source(self, document: Document) -> str:
        return get_document_source(document)

    @abstractmethod
    def parse(self, document: Document) -> ParsedDocument:
        raise NotImplementedError
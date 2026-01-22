"""
Базовый класс для всех парсеров документов.

Определяет интерфейс для парсинга документов различных форматов.
Все парсеры (MarkdownParser, PdfParser, DocxParser) наследуются от этого класса.

Основные методы:
- parse() - парсинг документа (абстрактный метод)
- can_parse() - проверка возможности парсинга документа
- get_source() - получение источника документа
- Валидация входных данных
- Обработка ошибок
- Логирование
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from langchain_core.documents import Document

from ...domain import DocumentFormat, Element, ElementIdGenerator, ElementType, ParsedDocument
from ...exceptions import ParsingError, UnsupportedFormatError, ValidationError
from ..loader.loader import detect_document_format, get_document_source, validate_document

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """
    Базовый класс для всех парсеров документов.

    Предоставляет общий интерфейс и функциональность для парсинга документов
    различных форматов. Все конкретные парсеры должны наследоваться от этого класса.
    """

    format: DocumentFormat = DocumentFormat.UNKNOWN

    def __init__(self, id_generator: Optional[ElementIdGenerator] = None) -> None:
        """
        Инициализация базового парсера.

        Args:
            id_generator: Генератор ID для элементов. Если не указан, создается новый.
        """
        self._id_generator = id_generator or ElementIdGenerator()
        logger.debug(f"Инициализирован парсер для формата {self.format.value}")

    @property
    def id_generator(self) -> ElementIdGenerator:
        """Возвращает генератор ID для элементов."""
        return self._id_generator

    def can_parse(self, document: Document) -> bool:
        """
        Проверяет, может ли парсер обработать документ.

        Args:
            document: LangChain Document для проверки

        Returns:
            bool: True если парсер может обработать документ, False иначе
        """
        try:
            format_ = detect_document_format(document)
            result = format_ == self.format
            logger.debug(f"Проверка возможности парсинга: формат={format_.value}, парсер={self.format.value}, результат={result}")
            return result
        except Exception as e:
            logger.warning(f"Ошибка при проверке возможности парсинга: {e}")
            return False

    def get_source(self, document: Document) -> str:
        """
        Получает источник документа из метаданных.

        Args:
            document: LangChain Document

        Returns:
            str: Путь к источнику документа или "unknown" если не найден
        """
        return get_document_source(document)

    def _validate_input(self, document: Document) -> None:
        """
        Валидирует входные данные перед парсингом.

        Проверяет:
        - Документ не None
        - Документ является экземпляром Document
        - Документ валиден (через validate_document)
        - Формат документа соответствует формату парсера

        Args:
            document: LangChain Document для валидации

        Raises:
            ValidationError: Если документ невалиден
            UnsupportedFormatError: Если формат документа не поддерживается парсером
        """
        if document is None:
            raise ValidationError("Документ не может быть None")

        if not isinstance(document, Document):
            raise ValidationError(
                f"Ожидается Document, получен {type(document).__name__}",
                field="document",
            )

        # Валидация через loader
        try:
            validate_document(document)
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Документ невалиден: {e}", field="document") from e

        # Проверка формата
        try:
            format_ = detect_document_format(document)
            if format_ != self.format:
                raise UnsupportedFormatError(
                    format_value=format_.value,
                    message=f"Парсер {self.format.value} не может обработать формат {format_.value}",
                )
        except ValueError as e:
            raise ValidationError(f"Не удалось определить формат документа: {e}", field="format") from e

    def _create_element(
        self,
        type: ElementType,
        content: str,
        parent_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Element:
        """
        Создает элемент с автоматической генерацией ID.

        Вспомогательный метод для упрощения создания элементов в конкретных парсерах.

        Args:
            type: Тип элемента
            content: Содержимое элемента
            parent_id: ID родительского элемента (опционально)
            metadata: Метаданные элемента (опционально)

        Returns:
            Element: Созданный элемент с уникальным ID
        """
        element_id = self._id_generator.next_id()
        element = Element(
            id=element_id,
            type=type,
            content=content,
            parent_id=parent_id,
            metadata=metadata or {},
        )
        logger.debug(f"Создан элемент: id={element_id}, type={type.value}, parent_id={parent_id}")
        return element

    def _validate_parsed_document(self, parsed_document: ParsedDocument) -> None:
        """
        Валидирует результат парсинга перед возвратом.

        Args:
            parsed_document: Результат парсинга для валидации

        Raises:
            ValidationError: Если результат парсинга невалиден
        """
        try:
            parsed_document.validate()
            logger.debug(f"Валидация ParsedDocument прошла успешно: {len(parsed_document.elements)} элементов")
        except ValueError as e:
            raise ValidationError(f"Результат парсинга невалиден: {e}", field="parsed_document") from e

    def _log_parsing_start(self, source: str) -> None:
        """
        Логирует начало парсинга документа.

        Args:
            source: Источник документа
        """
        logger.info(f"Начало парсинга документа: источник={source}, формат={self.format.value}")

    def _log_parsing_end(self, source: str, elements_count: int) -> None:
        """
        Логирует завершение парсинга документа.

        Args:
            source: Источник документа
            elements_count: Количество извлеченных элементов
        """
        logger.info(f"Парсинг завершен: источник={source}, извлечено элементов={elements_count}")

    @abstractmethod
    def parse(self, document: Document) -> ParsedDocument:
        """
        Парсит документ и возвращает структурированное представление.

        Этот метод должен быть реализован в каждом конкретном парсере.
        Рекомендуется использовать вспомогательные методы базового класса:
        - _validate_input() - для валидации входных данных
        - _create_element() - для создания элементов
        - _validate_parsed_document() - для валидации результата
        - _log_parsing_start() / _log_parsing_end() - для логирования

        Args:
            document: LangChain Document для парсинга

        Returns:
            ParsedDocument: Структурированное представление документа

        Raises:
            ValidationError: Если входные данные невалидны
            UnsupportedFormatError: Если формат документа не поддерживается
            ParsingError: Если произошла ошибка при парсинге
        """
        raise NotImplementedError
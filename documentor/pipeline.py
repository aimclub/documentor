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

import logging
import time
from typing import Dict, Iterable, List, Optional

from langchain_core.documents import Document

from .domain import DocumentFormat, ParsedDocument
from .exceptions import ParsingError, UnsupportedFormatError, ValidationError
from .processing.loader.loader import detect_document_format, get_document_source
from .processing.parsers.base import BaseParser
from .processing.parsers.docx.docx_parser import DocxParser
from .processing.parsers.md.md_parser import MarkdownParser
from .processing.parsers.pdf.pdf_parser import PdfParser

logger = logging.getLogger(__name__)


class Pipeline:
    """
    Главный пайплайн для обработки документов различных форматов.

    Поддерживает:
    - Автоматическое определение формата документа
    - Выбор соответствующего парсера
    - Обработку ошибок с информативными сообщениями
    - Логирование всех операций
    - Метрики производительности

    Пример использования:
        ```python
        from langchain_core.documents import Document
        from documentor import Pipeline

        pipeline = Pipeline()
        doc = Document(page_content="# Заголовок", metadata={"source": "test.md"})
        result = pipeline.parse(doc)
        ```
    """

    def __init__(self, parsers: Optional[Iterable[BaseParser]] = None) -> None:
        """
        Инициализация Pipeline.

        Args:
            parsers: Список парсеров для использования. Если не указан,
                    создаются парсеры по умолчанию (Markdown, DOCX, PDF).
        """
        parser_list = list(parsers) if parsers is not None else [
            MarkdownParser(),
            DocxParser(),
            PdfParser(),
        ]
        self._parsers = parser_list
        self._parsers_by_format: Dict[DocumentFormat, BaseParser] = {
            parser.format: parser for parser in parser_list
        }
        self._logger = logging.getLogger(self.__class__.__name__)
        self._logger.info(f"Pipeline initialized with {len(parser_list)} parsers")

    def get_available_formats(self) -> List[DocumentFormat]:
        """
        Возвращает список поддерживаемых форматов.

        Returns:
            Список форматов, для которых есть парсеры.
        """
        return list(self._parsers_by_format.keys())

    def parse(self, document: Document) -> ParsedDocument:
        """
        Парсит документ и возвращает структурированное представление.

        Args:
            document: LangChain Document для парсинга.

        Returns:
            ParsedDocument: Структурированное представление документа.

        Raises:
            ValidationError: Если документ невалиден.
            UnsupportedFormatError: Если формат документа не поддерживается.
            ParsingError: Если произошла ошибка при парсинге.
        """
        start_time = time.time()
        source = get_document_source(document)

        self._logger.info(f"Starting parsing document: {source}")

        try:
            # Определение формата
            try:
                format_ = detect_document_format(document)
                self._logger.debug(f"Detected format: {format_.value} for source: {source}")
            except ValueError as e:
                error_msg = f"Failed to detect document format (источник: {source})"
                self._logger.error(f"{error_msg}. Исходная ошибка: {e}")
                raise ValidationError(error_msg, field="format") from e

            # Выбор парсера
            parser = self._parsers_by_format.get(format_)
            if parser is None:
                error_msg = f"No parser available for format: {format_.value}"
                self._logger.error(f"{error_msg} (источник: {source})")
                raise UnsupportedFormatError(format_value=format_.value, message=error_msg)

            self._logger.debug(f"Using parser: {parser.__class__.__name__} for format: {format_.value}")

            # Парсинг документа
            try:
                parsed_document = parser.parse(document)
                elapsed_time = time.time() - start_time

                # Логирование результата
                num_elements = len(parsed_document.elements)
                self._logger.info(
                    f"Successfully parsed document: {source}. "
                    f"Format: {format_.value}, Elements: {num_elements}, "
                    f"Time: {elapsed_time:.3f}s"
                )

                # Добавление метрик в метаданные
                if parsed_document.metadata is None:
                    parsed_document.metadata = {}
                parsed_document.metadata["pipeline_metrics"] = {
                    "parsing_time_seconds": round(elapsed_time, 3),
                    "num_elements": num_elements,
                    "parser_class": parser.__class__.__name__,
                }

                return parsed_document

            except (ValidationError, UnsupportedFormatError):
                # Пробрасываем исключения валидации и неподдерживаемого формата как есть
                raise
            except Exception as e:
                error_msg = f"Error during parsing (источник: {source}, формат: {format_.value})"
                self._logger.error(f"{error_msg}. Исходная ошибка: {type(e).__name__}: {e}", exc_info=True)
                raise ParsingError(error_msg, source=source, original_error=e) from e

        except (ValidationError, UnsupportedFormatError, ParsingError):
            # Пробрасываем наши кастомные исключения как есть
            raise
        except Exception as e:
            # Обрабатываем неожиданные ошибки
            error_msg = f"Unexpected error in pipeline (источник: {source})"
            self._logger.error(f"{error_msg}. Исходная ошибка: {type(e).__name__}: {e}", exc_info=True)
            raise ParsingError(error_msg, source=source, original_error=e) from e

    def parse_many(self, documents: Iterable[Document]) -> List[ParsedDocument]:
        """
        Парсит несколько документов.

        Args:
            documents: Итерируемый объект с LangChain Document.

        Returns:
            Список ParsedDocument для каждого документа.

        Raises:
            ParsingError: Если произошла ошибка при парсинге любого документа.
        """
        start_time = time.time()
        doc_list = list(documents)
        total_docs = len(doc_list)

        self._logger.info(f"Starting batch parsing of {total_docs} documents")

        results: List[ParsedDocument] = []
        errors: List[tuple[str, Exception]] = []

        for i, document in enumerate(doc_list, 1):
            source = get_document_source(document)
            try:
                result = self.parse(document)
                results.append(result)
                self._logger.debug(f"Parsed document {i}/{total_docs}: {source}")
            except Exception as e:
                error_info = (source, e)
                errors.append(error_info)
                self._logger.warning(f"Failed to parse document {i}/{total_docs}: {source}. Error: {e}")

        elapsed_time = time.time() - start_time
        success_count = len(results)
        error_count = len(errors)

        self._logger.info(
            f"Batch parsing completed. "
            f"Total: {total_docs}, Success: {success_count}, Errors: {error_count}, "
            f"Time: {elapsed_time:.3f}s"
        )

        if errors and not results:
            # Если все документы завершились ошибкой
            error_msg = f"All {total_docs} documents failed to parse"
            first_error = errors[0]
            raise ParsingError(
                error_msg,
                source=first_error[0],
                original_error=first_error[1],
            )

        if errors:
            # Если есть ошибки, но есть и успешные результаты
            self._logger.warning(
                f"{error_count} document(s) failed to parse: "
                f"{', '.join([err[0] for err in errors])}"
            )

        return results


def pipeline(document: Document, pipeline_instance: Optional[Pipeline] = None) -> ParsedDocument:
    """
    Удобная функция для парсинга одного документа.

    Args:
        document: LangChain Document для парсинга.
        pipeline_instance: Экземпляр Pipeline. Если не указан, создается новый.

    Returns:
        ParsedDocument: Структурированное представление документа.

    Raises:
        ValidationError: Если документ невалиден.
        UnsupportedFormatError: Если формат документа не поддерживается.
        ParsingError: Если произошла ошибка при парсинге.

    Пример:
        ```python
        from langchain_core.documents import Document
        from documentor import pipeline

        doc = Document(page_content="# Заголовок", metadata={"source": "test.md"})
        result = pipeline(doc)
        ```
    """
    active_pipeline = pipeline_instance or Pipeline()
    return active_pipeline.parse(document)


"""
Исключения для библиотеки documentor.

Содержит кастомные исключения для обработки ошибок парсинга документов,
неподдерживаемых форматов и других ошибок обработки.
"""

from __future__ import annotations


class DocumentorError(Exception):
    """Базовое исключение для всех ошибок библиотеки documentor."""

    pass


class UnsupportedFormatError(DocumentorError):
    """Ошибка неподдерживаемого формата документа."""

    def __init__(self, format_value: str, message: str | None = None) -> None:
        """
        Инициализация исключения.

        Args:
            format_value: Значение формата, который не поддерживается
            message: Дополнительное сообщение об ошибке
        """
        self.format_value = format_value
        default_message = f"Неподдерживаемый формат документа: {format_value}"
        super().__init__(message or default_message)


class ParsingError(DocumentorError):
    """Ошибка парсинга документа."""

    def __init__(self, message: str, source: str | None = None, original_error: Exception | None = None) -> None:
        """
        Инициализация исключения.

        Args:
            message: Сообщение об ошибке
            source: Источник документа (путь к файлу)
            original_error: Исходное исключение, которое вызвало ошибку
        """
        self.source = source
        self.original_error = original_error
        full_message = message
        if source:
            full_message = f"{message} (источник: {source})"
        if original_error:
            full_message = f"{full_message}. Исходная ошибка: {type(original_error).__name__}: {original_error}"
        super().__init__(full_message)


class OCRError(DocumentorError):
    """Ошибка OCR обработки."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        """
        Инициализация исключения.

        Args:
            message: Сообщение об ошибке
            original_error: Исходное исключение, которое вызвало ошибку
        """
        self.original_error = original_error
        full_message = message
        if original_error:
            full_message = f"{message}. Исходная ошибка: {type(original_error).__name__}: {original_error}"
        super().__init__(full_message)


class LLMError(DocumentorError):
    """Ошибка работы с LLM."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        """
        Инициализация исключения.

        Args:
            message: Сообщение об ошибке
            original_error: Исходное исключение, которое вызвало ошибку
        """
        self.original_error = original_error
        full_message = message
        if original_error:
            full_message = f"{message}. Исходная ошибка: {type(original_error).__name__}: {original_error}"
        super().__init__(full_message)


class ValidationError(DocumentorError):
    """Ошибка валидации данных."""

    def __init__(self, message: str, field: str | None = None) -> None:
        """
        Инициализация исключения.

        Args:
            message: Сообщение об ошибке
            field: Поле, которое не прошло валидацию
        """
        self.field = field
        full_message = message
        if field:
            full_message = f"Ошибка валидации поля '{field}': {message}"
        super().__init__(full_message)

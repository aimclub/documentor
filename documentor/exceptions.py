"""
Exceptions for documentor library.

Contains custom exceptions for handling document parsing errors,
unsupported formats and other processing errors.
"""

from __future__ import annotations


class DocumentorError(Exception):
    """Base exception for all documentor library errors."""

    pass


class UnsupportedFormatError(DocumentorError):
    """Unsupported document format error."""

    def __init__(self, format_value: str, message: str | None = None) -> None:
        """
        Initialize exception.

        Args:
            format_value: Format value that is not supported
            message: Additional error message
        """
        self.format_value = format_value
        default_message = f"Unsupported document format: {format_value}"
        super().__init__(message or default_message)


class ParsingError(DocumentorError):
    """Document parsing error."""

    def __init__(self, message: str, source: str | None = None, original_error: Exception | None = None) -> None:
        """
        Initialize exception.

        Args:
            message: Error message
            source: Document source (file path)
            original_error: Original exception that caused the error
        """
        self.source = source
        self.original_error = original_error
        full_message = message
        if source:
            full_message = f"{message} (source: {source})"
        if original_error:
            full_message = f"{full_message}. Original error: {type(original_error).__name__}: {original_error}"
        super().__init__(full_message)


class OCRError(DocumentorError):
    """OCR processing error."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        """
        Initialize exception.

        Args:
            message: Error message
            original_error: Original exception that caused the error
        """
        self.original_error = original_error
        full_message = message
        if original_error:
            full_message = f"{message}. Original error: {type(original_error).__name__}: {original_error}"
        super().__init__(full_message)


class LLMError(DocumentorError):
    """LLM processing error."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        """
        Initialize exception.

        Args:
            message: Error message
            original_error: Original exception that caused the error
        """
        self.original_error = original_error
        full_message = message
        if original_error:
            full_message = f"{message}. Original error: {type(original_error).__name__}: {original_error}"
        super().__init__(full_message)


class ValidationError(DocumentorError):
    """Data validation error."""

    def __init__(self, message: str, field: str | None = None) -> None:
        """
        Initialize exception.

        Args:
            message: Error message
            field: Field that failed validation
        """
        self.field = field
        full_message = message
        if field:
            full_message = f"Validation error for field '{field}': {message}"
        super().__init__(full_message)

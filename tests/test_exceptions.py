"""
Tests for exceptions.py.

Tested exception classes:
- DocumentorError
- UnsupportedFormatError
- ParsingError
- OCRError
- LLMError
- ValidationError
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to PYTHONPATH
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest

from documentor.exceptions import (
    DocumentorError,
    LLMError,
    OCRError,
    ParsingError,
    UnsupportedFormatError,
    ValidationError,
)


class TestDocumentorError:
    """Tests for DocumentorError base exception."""

    def test_documentor_error_basic(self):
        """Test basic DocumentorError creation."""
        error = DocumentorError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_documentor_error_inheritance(self):
        """Test that DocumentorError is a base exception."""
        assert issubclass(DocumentorError, Exception)


class TestUnsupportedFormatError:
    """Tests for UnsupportedFormatError."""

    def test_unsupported_format_error_basic(self):
        """Test basic UnsupportedFormatError creation."""
        error = UnsupportedFormatError("invalid_format")
        assert "invalid_format" in str(error)
        assert error.format_value == "invalid_format"
        assert isinstance(error, DocumentorError)

    def test_unsupported_format_error_with_message(self):
        """Test UnsupportedFormatError with custom message."""
        error = UnsupportedFormatError("invalid_format", "Custom message")
        assert "Custom message" in str(error)
        assert error.format_value == "invalid_format"

    def test_unsupported_format_error_default_message(self):
        """Test UnsupportedFormatError default message."""
        error = UnsupportedFormatError("xyz")
        assert "Unsupported document format: xyz" in str(error)


class TestParsingError:
    """Tests for ParsingError."""

    def test_parsing_error_basic(self):
        """Test basic ParsingError creation."""
        error = ParsingError("Parsing failed")
        assert "Parsing failed" in str(error)
        assert error.source is None
        assert error.original_error is None
        assert isinstance(error, DocumentorError)

    def test_parsing_error_with_source(self):
        """Test ParsingError with source."""
        error = ParsingError("Parsing failed", source="test.pdf")
        assert "Parsing failed" in str(error)
        assert "(source: test.pdf)" in str(error)
        assert error.source == "test.pdf"

    def test_parsing_error_with_original_error(self):
        """Test ParsingError with original error."""
        original = ValueError("Original error")
        error = ParsingError("Parsing failed", original_error=original)
        assert "Parsing failed" in str(error)
        assert "Original error" in str(error)
        assert error.original_error == original

    def test_parsing_error_with_all_params(self):
        """Test ParsingError with all parameters."""
        original = IOError("File not found")
        error = ParsingError("Parsing failed", source="test.pdf", original_error=original)
        assert "Parsing failed" in str(error)
        assert "(source: test.pdf)" in str(error)
        assert "Original error" in str(error)
        assert error.source == "test.pdf"
        assert error.original_error == original


class TestOCRError:
    """Tests for OCRError."""

    def test_ocr_error_basic(self):
        """Test basic OCRError creation."""
        error = OCRError("OCR failed")
        assert "OCR failed" in str(error)
        assert error.original_error is None
        assert isinstance(error, DocumentorError)

    def test_ocr_error_with_original_error(self):
        """Test OCRError with original error."""
        original = ConnectionError("Connection failed")
        error = OCRError("OCR failed", original_error=original)
        assert "OCR failed" in str(error)
        assert "Original error" in str(error)
        assert error.original_error == original


class TestLLMError:
    """Tests for LLMError."""

    def test_llm_error_basic(self):
        """Test basic LLMError creation."""
        error = LLMError("LLM failed")
        assert "LLM failed" in str(error)
        assert error.original_error is None
        assert isinstance(error, DocumentorError)

    def test_llm_error_with_original_error(self):
        """Test LLMError with original error."""
        original = TimeoutError("Request timeout")
        error = LLMError("LLM failed", original_error=original)
        assert "LLM failed" in str(error)
        assert "Original error" in str(error)
        assert error.original_error == original


class TestValidationError:
    """Tests for ValidationError."""

    def test_validation_error_basic(self):
        """Test basic ValidationError creation."""
        error = ValidationError("Invalid data")
        assert "Invalid data" in str(error)
        assert error.field is None
        assert isinstance(error, DocumentorError)

    def test_validation_error_with_field(self):
        """Test ValidationError with field."""
        error = ValidationError("Invalid data", field="email")
        assert "Invalid data" in str(error)
        assert "field 'email'" in str(error)
        assert error.field == "email"

    def test_validation_error_default_message_with_field(self):
        """Test ValidationError default message format with field."""
        error = ValidationError("Value is required", field="username")
        assert "Validation error for field 'username': Value is required" in str(error)

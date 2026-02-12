"""
Base class for all document parsers.

Defines interface for parsing documents of various formats.
All parsers (MarkdownParser, PdfParser, DocxParser) inherit from this class.

Main methods:
- parse() - document parsing (abstract method)
- can_parse() - check if parser can handle document
- get_source() - get document source
- Input validation
- Error handling
- Logging
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
    Base class for all document parsers.

    Provides common interface and functionality for parsing documents
    of various formats. All concrete parsers should inherit from this class.
    """

    format: DocumentFormat = DocumentFormat.UNKNOWN

    def __init__(self, id_generator: Optional[ElementIdGenerator] = None) -> None:
        """
        Initialize base parser.

        Args:
            id_generator: ID generator for elements. If not specified, a new one is created.
        """
        self._id_generator = id_generator or ElementIdGenerator()
        logger.debug(f"Initialized parser for format {self.format.value}")

    @property
    def id_generator(self) -> ElementIdGenerator:
        """Returns ID generator for elements."""
        return self._id_generator

    def can_parse(self, document: Document) -> bool:
        """
        Checks if parser can handle the document.

        Args:
            document: LangChain Document to check

        Returns:
            bool: True if parser can handle document, False otherwise
        """
        try:
            format_ = detect_document_format(document)
            result = format_ == self.format
            logger.debug(f"Parsing capability check: format={format_.value}, parser={self.format.value}, result={result}")
            return result
        except Exception as e:
            logger.warning(f"Error checking parsing capability: {e}")
            return False

    def get_source(self, document: Document) -> str:
        """
        Gets document source from metadata.

        Args:
            document: LangChain Document

        Returns:
            str: Path to document source or "unknown" if not found
        """
        return get_document_source(document)

    def _validate_input(self, document: Document) -> None:
        """
        Validates input data before parsing.

        Checks:
        - Document is not None
        - Document is an instance of Document
        - Document is valid (via validate_document)
        - Document format matches parser format

        Args:
            document: LangChain Document to validate

        Raises:
            ValidationError: If document is invalid
            UnsupportedFormatError: If document format is not supported by parser
        """
        if document is None:
            raise ValidationError("Document cannot be None")

        if not isinstance(document, Document):
            raise ValidationError(
                f"Expected Document, got {type(document).__name__}",
                field="document",
            )

        # Validation via loader
        try:
            validate_document(document)
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Document is invalid: {e}", field="document") from e

        # Format check
        try:
            format_ = detect_document_format(document)
            if format_ != self.format:
                raise UnsupportedFormatError(
                    format_value=format_.value,
                    message=f"Parser {self.format.value} cannot handle format {format_.value}",
                )
        except ValueError as e:
            raise ValidationError(f"Failed to detect document format: {e}", field="format") from e

    def _create_element(
        self,
        type: ElementType,
        content: str,
        parent_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Element:
        """
        Creates element with automatic ID generation.

        Helper method to simplify element creation in concrete parsers.

        Args:
            type: Element type
            content: Element content
            parent_id: Parent element ID (optional)
            metadata: Element metadata (optional)

        Returns:
            Element: Created element with unique ID
        """
        element_id = self._id_generator.next_id()
        element = Element(
            id=element_id,
            type=type,
            content=content,
            parent_id=parent_id,
            metadata=metadata or {},
        )
        logger.debug(f"Created element: id={element_id}, type={type.value}, parent_id={parent_id}")
        return element

    def _validate_parsed_document(self, parsed_document: ParsedDocument) -> None:
        """
        Validates parsing result before returning.

        Args:
            parsed_document: Parsing result to validate

        Raises:
            ValidationError: If parsing result is invalid
        """
        try:
            parsed_document.validate()
            logger.debug(f"ParsedDocument validation passed successfully: {len(parsed_document.elements)} elements")
        except ValueError as e:
            raise ValidationError(f"Parsing result is invalid: {e}", field="parsed_document") from e

    def _log_parsing_start(self, source: str) -> None:
        """
        Logs document parsing start.

        Args:
            source: Document source
        """
        logger.info(f"Starting document parsing: source={source}, format={self.format.value}")

    def _log_parsing_end(self, source: str, elements_count: int) -> None:
        """
        Logs document parsing completion.

        Args:
            source: Document source
            elements_count: Number of extracted elements
        """
        logger.info(f"Parsing completed: source={source}, extracted elements={elements_count}")

    @abstractmethod
    def parse(self, document: Document) -> ParsedDocument:
        """
        Parse document and return structured representation.

        This method must be implemented in each concrete parser.
        It is recommended to use helper methods from base class:
        - _validate_input() - for input validation
        - _create_element() - for element creation
        - _validate_parsed_document() - for result validation
        - _log_parsing_start() / _log_parsing_end() - for logging

        Args:
            document: LangChain Document to parse

        Returns:
            ParsedDocument: Structured document representation

        Raises:
            ValidationError: If input data is invalid
            UnsupportedFormatError: If document format is not supported
            ParsingError: If parsing error occurred
        """
        raise NotImplementedError
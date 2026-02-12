"""
Main document processing pipeline.

Contains Pipeline class and pipeline function for processing documents
in LangChain Document format.

Main logic:
1. Document format detection
2. Select appropriate parser
3. Parse document into structured format
4. Return ParsedDocument with elements and hierarchy
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Iterable, List, Optional

from langchain_core.documents import Document

from .domain import DocumentFormat, ParsedDocument
from .exceptions import ParsingError, UnsupportedFormatError, ValidationError
from .ocr.manager import DotsOCRManager
from .processing.loader.loader import detect_document_format, get_document_source
from .processing.parsers.base import BaseParser
from .processing.parsers.docx.docx_parser import DocxParser
from .processing.parsers.md.md_parser import MarkdownParser
from .processing.parsers.pdf.pdf_parser import PdfParser

logger = logging.getLogger(__name__)


class Pipeline:
    """
    Main pipeline for processing documents of various formats.

    Supports:
    - Automatic document format detection
    - Selection of appropriate parser
    - Error handling with informative messages
    - Logging of all operations
    - Performance metrics

    Usage example:
        ```python
        from langchain_core.documents import Document
        from documentor import Pipeline

        pipeline = Pipeline()
        doc = Document(page_content="# Header", metadata={"source": "test.md"})
        result = pipeline.parse(doc)
        ```
    """

    def __init__(self, parsers: Optional[Iterable[BaseParser]] = None) -> None:
        """
        Initialize Pipeline.

        Args:
            parsers: List of parsers to use. If not specified,
                    default parsers are created (Markdown, DOCX, PDF).
                    DotsOCRManager is automatically created from .env for parsers that need it.
        """
        # Automatically create manager from .env (if configured)
        try:
            self.ocr_manager = DotsOCRManager(auto_load_models=True)
            self._logger = logging.getLogger(self.__class__.__name__)
            self._logger.debug("DotsOCRManager initialized from .env")
        except Exception as e:
            # If .env is not configured or loading error - manager will be None
            self.ocr_manager = None
            self._logger = logging.getLogger(self.__class__.__name__)
            self._logger.debug(f"DotsOCRManager not initialized: {e}")
        
        parser_list = list(parsers) if parsers is not None else [
            MarkdownParser(),
            DocxParser(),
            PdfParser(ocr_manager=self.ocr_manager),
        ]
        self._parsers = parser_list
        self._parsers_by_format: Dict[DocumentFormat, BaseParser] = {
            parser.format: parser for parser in parser_list
        }
        if not hasattr(self, '_logger'):
            self._logger = logging.getLogger(self.__class__.__name__)
        self._logger.info(f"Pipeline initialized with {len(parser_list)} parsers")

    def get_available_formats(self) -> List[DocumentFormat]:
        """
        Returns list of supported formats.

        Returns:
            List of formats for which parsers are available.
        """
        return list(self._parsers_by_format.keys())

    def parse(self, document: Document) -> ParsedDocument:
        """
        Parse document and return structured representation.

        Args:
            document: LangChain Document to parse.

        Returns:
            ParsedDocument: Structured document representation.

        Raises:
            ValidationError: If document is invalid.
            UnsupportedFormatError: If document format is not supported.
            ParsingError: If parsing error occurred.
        """
        if document is None:
            raise ValidationError("Document cannot be None", field="document")
        
        start_time = time.time()
        source = get_document_source(document)

        self._logger.info(f"Starting parsing document: {source}")

        try:
            # Format detection
            try:
                format_ = detect_document_format(document)
                self._logger.debug(f"Detected format: {format_.value} for source: {source}")
            except ValueError as e:
                error_msg = f"Failed to detect document format (source: {source})"
                self._logger.error(f"{error_msg}. Original error: {e}")
                raise ValidationError(error_msg, field="format") from e

            # Parser selection
            parser = self._parsers_by_format.get(format_)
            if parser is None:
                error_msg = f"No parser available for format: {format_.value}"
                self._logger.error(f"{error_msg} (source: {source})")
                raise UnsupportedFormatError(format_value=format_.value, message=error_msg)

            self._logger.debug(f"Using parser: {parser.__class__.__name__} for format: {format_.value}")

            # Document parsing
            try:
                parsed_document = parser.parse(document)
                elapsed_time = time.time() - start_time

                # Log result
                num_elements = len(parsed_document.elements)
                self._logger.info(
                    f"Successfully parsed document: {source}. "
                    f"Format: {format_.value}, Elements: {num_elements}, "
                    f"Time: {elapsed_time:.3f}s"
                )

                # Add metrics to metadata
                if parsed_document.metadata is None:
                    parsed_document.metadata = {}
                
                # Calculate additional metrics
                # Element statistics by type
                elements_by_type: Dict[str, int] = {}
                for element in parsed_document.elements:
                    element_type = element.type.value
                    elements_by_type[element_type] = elements_by_type.get(element_type, 0) + 1
                
                # Document size
                document_content = document.page_content or ""
                document_size_bytes = len(document_content.encode("utf-8"))
                document_lines = len(document_content.splitlines())
                
                # Performance
                elements_per_second = (
                    round(num_elements / elapsed_time, 2) if elapsed_time > 0 else 0.0
                )
                
                parsed_document.metadata["pipeline_metrics"] = {
                    "parsing_time_seconds": round(elapsed_time, 3),
                    "num_elements": num_elements,
                    "parser_class": parser.__class__.__name__,
                    "elements_by_type": elements_by_type,
                    "elements_per_second": elements_per_second,
                    "document_size_bytes": document_size_bytes,
                    "document_lines": document_lines,
                }

                return parsed_document

            except (ValidationError, UnsupportedFormatError):
                # Re-raise validation and unsupported format exceptions as-is
                raise
            except Exception as e:
                error_msg = f"Error during parsing (source: {source}, format: {format_.value})"
                self._logger.error(f"{error_msg}. Original error: {type(e).__name__}: {e}", exc_info=True)
                raise ParsingError(error_msg, source=source, original_error=e) from e

        except (ValidationError, UnsupportedFormatError, ParsingError):
            # Re-raise our custom exceptions as-is
            raise
        except Exception as e:
            # Handle unexpected errors
            error_msg = f"Unexpected error in pipeline (source: {source})"
            self._logger.error(f"{error_msg}. Original error: {type(e).__name__}: {e}", exc_info=True)
            raise ParsingError(error_msg, source=source, original_error=e) from e

    def parse_many(self, documents: Iterable[Document]) -> List[ParsedDocument]:
        """
        Parse multiple documents.

        Args:
            documents: Iterable of LangChain Documents.

        Returns:
            List of ParsedDocument for each document.

        Raises:
            ParsingError: If error occurred while parsing any document.
        """
        # TODO: possibly rewrite into single parse function (think about it)
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
            # If all documents failed
            error_msg = f"All {total_docs} documents failed to parse"
            first_error = errors[0]
            raise ParsingError(
                error_msg,
                source=first_error[0],
                original_error=first_error[1],
            )

        if errors:
            # If there are errors but also successful results
            self._logger.warning(
                f"{error_count} document(s) failed to parse: "
                f"{', '.join([err[0] for err in errors])}"
            )

        return results


def pipeline(document: Document, pipeline_instance: Optional[Pipeline] = None) -> ParsedDocument:
    """
    Convenience function for parsing a single document.

    Args:
        document: LangChain Document to parse.
        pipeline_instance: Pipeline instance. If not specified, a new one is created.
                          DotsOCRManager is automatically initialized from .env.

    Returns:
        ParsedDocument: Structured document representation.

    Raises:
        ValidationError: If document is invalid.
        UnsupportedFormatError: If document format is not supported.
        ParsingError: If parsing error occurred.

    Example:
        ```python
        from langchain_core.documents import Document
        from documentor import pipeline

        doc = Document(page_content="# Header", metadata={"source": "test.md"})
        result = pipeline(doc)
        ```
        
    Note:
        For OCR functionality, ensure that .env file has:
        - DOTS_OCR_BASE_URL
        - DOTS_OCR_API_KEY
        - DOTS_OCR_MODEL_NAME
        and other necessary parameters.
    """
    active_pipeline = pipeline_instance or Pipeline()
    return active_pipeline.parse(document)


"""
Documentor (LangChain-first).

New package for document structuring pipeline for RAG.

Key goals:
- unified output contract (elements + hierarchy)
- integration with LangChain `Document`
- ability to reuse old parsers through adapters

Usage example:
    ```python
    from langchain_core.documents import Document
    from documentor import Pipeline

    pipeline = Pipeline()
    doc = Document(page_content="# Header", metadata={"source": "test.md"})
    result = pipeline.parse(doc)
    print(f"Parsed {len(result.elements)} elements")
    ```
"""

from .domain.models import DocumentFormat, Element, ElementType, ParsedDocument
from .exceptions import (
    DocumentorError,
    LLMError,
    OCRError,
    ParsingError,
    UnsupportedFormatError,
    ValidationError,
)
from .pipeline import Pipeline, pipeline

__all__ = [
    # Pipeline
    "Pipeline",
    "pipeline",
    # Domain models
    "DocumentFormat",
    "Element",
    "ElementType",
    "ParsedDocument",
    # Exceptions
    "DocumentorError",
    "ParsingError",
    "UnsupportedFormatError",
    "ValidationError",
    "OCRError",
    "LLMError",
]


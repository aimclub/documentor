"""
Documentor (LangChain-first).

Новый пакет под пайплайн структурирования документов для RAG.

Ключевые цели:
- единый контракт выходных данных (элементы + иерархия)
- интеграция с LangChain `Document`
- возможность переиспользовать старые парсеры через адаптеры

Пример использования:
    ```python
    from langchain_core.documents import Document
    from documentor import Pipeline

    pipeline = Pipeline()
    doc = Document(page_content="# Заголовок", metadata={"source": "test.md"})
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


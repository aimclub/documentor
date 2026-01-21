"""
Documentor (LangChain-first).

Новый пакет под пайплайн структурирования документов для RAG.

Ключевые цели:
- единый контракт выходных данных (элементы + иерархия)
- интеграция с LangChain `Document`
- возможность переиспользовать старые парсеры через адаптеры
"""

from .pipeline import Pipeline, pipeline
from .domain.models import Element, ElementType, ParsedDocument

__all__ = [
    "Pipeline",
    "pipeline",
    "Element",
    "ElementType",
    "ParsedDocument",
]


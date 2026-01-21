"""
Утилиты для работы с LangChain Document и определения формата.

Содержит функции для:
- Определения формата документа по расширению файла или MIME типу
- Получения источника документа из метаданных
- Валидации документов
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.documents import Document

from ...domain import DocumentFormat


def get_document_source(document: Document) -> str:
    metadata = document.metadata or {}
    for key in ("source", "file_path", "path", "filename"):
        value = metadata.get(key)
        if value:
            return str(value)
    return "unknown"


def detect_document_format(document: Document) -> DocumentFormat:
    source = get_document_source(document)
    extension = Path(source).suffix.lower().lstrip(".")

    if extension in {"md", "markdown"}:
        return DocumentFormat.MARKDOWN
    if extension == "pdf":
        return DocumentFormat.PDF
    if extension == "docx":
        return DocumentFormat.DOCX

    mime_type = (document.metadata or {}).get("mime_type", "")
    if mime_type == "application/pdf":
        return DocumentFormat.PDF
    if mime_type in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }:
        return DocumentFormat.DOCX
    if mime_type in {"text/markdown", "text/x-markdown"}:
        return DocumentFormat.MARKDOWN

    return DocumentFormat.UNKNOWN

def choose_parsers(documents: list[Document]) -> list[Document]:
    "Отправляет файл в парсеры"
    pass
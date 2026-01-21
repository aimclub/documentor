"""
Утилиты для работы с LangChain Document и определения формата.

Содержит функции для:
- Определения формата документа по расширению файла, MIME типу или magic bytes
- Получения источника документа из метаданных
- Валидации документов
- Нормализации метаданных
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from langchain_core.documents import Document

from ...domain import DocumentFormat

logger = logging.getLogger(__name__)

# Magic bytes для определения формата файла
MAGIC_BYTES = {
    b"%PDF": DocumentFormat.PDF,
    b"PK\x03\x04": DocumentFormat.DOCX,  # DOCX - это ZIP архив
}

# MIME типы для определения формата
MIME_TYPE_MAP = {
    "application/pdf": DocumentFormat.PDF,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocumentFormat.DOCX,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template": DocumentFormat.DOCX,
    "text/markdown": DocumentFormat.MARKDOWN,
    "text/x-markdown": DocumentFormat.MARKDOWN,
}

# Расширения файлов для определения формата
EXTENSION_MAP = {
    "md": DocumentFormat.MARKDOWN,
    "markdown": DocumentFormat.MARKDOWN,
    "pdf": DocumentFormat.PDF,
    "docx": DocumentFormat.DOCX,
}


def get_document_source(document: Document) -> str:
    """
    Получает источник документа из метаданных.
    
    Проверяет следующие ключи в порядке приоритета:
    - source
    - file_path
    - path
    - filename
    - file_name
    
    Args:
        document: LangChain Document
        
    Returns:
        str: Путь к источнику документа или "unknown" если не найден
    """
    metadata = document.metadata or {}
    for key in ("source", "file_path", "path", "filename", "file_name"):
        value = metadata.get(key)
        if value:
            source = str(value)
            logger.debug(f"Найден источник документа по ключу '{key}': {source}")
            return source
    
    logger.warning("Источник документа не найден в метаданных")
    return "unknown"


def _detect_format_by_extension(source: str) -> Optional[DocumentFormat]:
    """
    Определяет формат документа по расширению файла.
    
    Args:
        source: Путь к файлу
        
    Returns:
        DocumentFormat или None если не удалось определить
    """
    try:
        path = Path(source)
        extension = path.suffix.lower().lstrip(".")
        if extension:
            format_ = EXTENSION_MAP.get(extension)
            if format_:
                logger.debug(f"Формат определен по расширению '{extension}': {format_.value}")
                return format_
    except (ValueError, AttributeError) as e:
        logger.debug(f"Ошибка при определении формата по расширению: {e}")
    return None


def _detect_format_by_mime_type(metadata: dict) -> Optional[DocumentFormat]:
    """
    Определяет формат документа по MIME типу из метаданных.
    
    Args:
        metadata: Метаданные документа
        
    Returns:
        DocumentFormat или None если не удалось определить
    """
    mime_type = metadata.get("mime_type", "")
    if mime_type:
        format_ = MIME_TYPE_MAP.get(mime_type)
        if format_:
            logger.debug(f"Формат определен по MIME типу '{mime_type}': {format_.value}")
            return format_
    return None


def _detect_format_by_magic_bytes(source: str) -> Optional[DocumentFormat]:
    """
    Определяет формат документа по magic bytes (сигнатуре файла).
    
    Args:
        source: Путь к файлу
        
    Returns:
        DocumentFormat или None если не удалось определить
    """
    try:
        path = Path(source)
        if not path.exists() or not path.is_file():
            return None
        
        with open(path, "rb") as f:
            # Читаем первые 4 байта для проверки сигнатуры
            header = f.read(4)
            if len(header) < 4:
                return None
            
            # Проверяем magic bytes
            for magic, format_ in MAGIC_BYTES.items():
                if header.startswith(magic):
                    logger.debug(f"Формат определен по magic bytes: {format_.value}")
                    return format_
            
            # Для DOCX нужно проверить больше байт (ZIP сигнатура)
            if header.startswith(b"PK"):
                f.seek(0)
                # DOCX файлы имеют специфичную структуру ZIP
                # Проверяем наличие файла [Content_Types].xml в ZIP
                zip_header = f.read(30)
                if b"[Content_Types].xml" in zip_header or b"word/" in zip_header:
                    logger.debug("Формат определен по структуре ZIP (DOCX)")
                    return DocumentFormat.DOCX
                    
    except (OSError, IOError, ValueError) as e:
        logger.debug(f"Ошибка при чтении magic bytes: {e}")
    return None


def detect_document_format(document: Document) -> DocumentFormat:
    """
    Определяет формат документа.
    
    Использует несколько методов в порядке приоритета:
    1. Расширение файла
    2. MIME тип из метаданных
    3. Magic bytes (сигнатура файла)
    
    Args:
        document: LangChain Document
        
    Returns:
        DocumentFormat: Определенный формат документа
        
    Raises:
        ValueError: Если документ невалиден (нет page_content и source)
    """
    source = get_document_source(document)
    # Проверяем, что есть либо непустой page_content, либо валидный source
    has_content = bool(document.page_content and document.page_content.strip())
    has_source = source != "unknown"
    
    if not has_content and not has_source:
        raise ValueError("Документ должен содержать page_content или source в метаданных")
    
    metadata = document.metadata or {}
    
    # Метод 1: По расширению файла
    format_ = _detect_format_by_extension(source)
    if format_:
        return format_
    
    # Метод 2: По MIME типу
    format_ = _detect_format_by_mime_type(metadata)
    if format_:
        return format_
    
    # Метод 3: По magic bytes (только если source - это путь к файлу)
    if source != "unknown":
        format_ = _detect_format_by_magic_bytes(source)
        if format_:
            return format_
    
    logger.warning(f"Не удалось определить формат документа для источника: {source}")
    return DocumentFormat.UNKNOWN


def validate_document(document: Document) -> None:
    """
    Валидирует LangChain Document.
    
    Проверяет:
    - Документ не None
    - Есть page_content или source в метаданных
    - page_content - строка (если указан)
    
    Args:
        document: LangChain Document для валидации
        
    Raises:
        ValueError: Если документ невалиден
        TypeError: Если передан не Document объект
    """
    if document is None:
        raise ValueError("Документ не может быть None")
    
    if not isinstance(document, Document):
        raise TypeError(f"Ожидается Document, получен {type(document).__name__}")
    
    # Проверяем наличие контента или источника
    has_content = bool(document.page_content)
    has_source = bool(get_document_source(document) != "unknown")
    
    if not has_content and not has_source:
        raise ValueError("Документ должен содержать page_content или source в метаданных")
    
    # Проверяем тип page_content
    if document.page_content is not None and not isinstance(document.page_content, str):
        raise TypeError(
            f"page_content должен быть строкой, получен {type(document.page_content).__name__}"
        )
    
    # Проверяем тип metadata
    if document.metadata is not None and not isinstance(document.metadata, dict):
        raise TypeError(
            f"metadata должен быть словарем, получен {type(document.metadata).__name__}"
        )


def normalize_metadata(document: Document) -> dict:
    """
    Нормализует метаданные документа.
    
    Обеспечивает наличие стандартных ключей:
    - source: путь к файлу
    - format: определенный формат документа
    
    Args:
        document: LangChain Document
        
    Returns:
        dict: Нормализованные метаданные
    """
    metadata = dict(document.metadata or {})
    
    # Добавляем source если его нет
    if "source" not in metadata:
        source = get_document_source(document)
        if source != "unknown":
            metadata["source"] = source
    
    # Добавляем format если его нет
    if "format" not in metadata:
        try:
            format_ = detect_document_format(document)
            metadata["format"] = format_.value
        except ValueError:
            # Если не удалось определить формат, не добавляем его
            pass
    
    return metadata
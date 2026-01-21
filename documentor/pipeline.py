"""
Главный пайплайн обработки документов.

Содержит класс Pipeline и функцию pipeline для обработки документов
в формате LangChain Document.

Основная логика:
1. Определение формата документа
2. Выбор соответствующего парсера
3. Парсинг документа в структурированный формат
4. Возврат ParsedDocument с элементами и иерархией
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from langchain_core.documents import Document

from .domain import ParsedDocument
from .processing.loader.loader import detect_document_format
from .processing.parsers.base import BaseParser
from .processing.parsers.docx.docx_parser import DocxParser
from .processing.parsers.md.md_parser import MarkdownParser
from .processing.parsers.pdf.pdf_parser import PdfParser


class Pipeline:
    def __init__(self, parsers: Optional[Iterable[BaseParser]] = None) -> None:
        parser_list = list(parsers) if parsers is not None else [
            MarkdownParser(),
            DocxParser(),
            PdfParser(),
        ]
        self._parsers = parser_list
        self._parsers_by_format = {parser.format: parser for parser in parser_list}

    def parse(self, document: Document) -> ParsedDocument:
        format_ = detect_document_format(document)
        parser = self._parsers_by_format.get(format_)
        if parser is None:
            raise ValueError(f"Нет парсера для формата: {format_.value}")
        return parser.parse(document)

    def parse_many(self, documents: Iterable[Document]) -> List[ParsedDocument]:
        return [self.parse(document) for document in documents]


def pipeline(document: Document, pipeline_instance: Optional[Pipeline] = None) -> ParsedDocument:
    active_pipeline = pipeline_instance or Pipeline()
    return active_pipeline.parse(document)
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Optional, Sequence, Union

from langchain_core.documents import Document as LCDocument

from .adapters.documentor_old import DocumentorOldAdapter
from .domain.id_generator import SequentialIdGenerator
from .domain.models import Element, ParsedDocument
from .domain.source import DocumentFormat, SourceDocument
from .exceptions import InputResolutionError, UnsupportedFormatError
from .parsers.markdown import MarkdownParser
from .parsers.plain_text import PlainTextParser
from .parsers.registry import ParserRegistry
from .postprocessing.hierarchy import assign_parents_by_headers
from .storage.artifacts import LocalArtifactStore


def _detect_format_from_path(path: Path) -> DocumentFormat:
    ext = path.suffix.lower().lstrip(".")
    if ext == "pdf":
        return DocumentFormat.PDF
    if ext == "docx":
        return DocumentFormat.DOCX
    if ext == "doc":
        return DocumentFormat.DOC
    if ext in ("md", "markdown"):
        return DocumentFormat.MARKDOWN
    if ext in ("txt",):
        return DocumentFormat.TXT
    if ext in ("png", "jpg", "jpeg", "tiff", "tif", "webp"):
        return DocumentFormat.IMAGE
    return DocumentFormat.UNKNOWN


def _resolve_source(doc: LCDocument) -> SourceDocument:
    """
    Поддерживаем два сценария, которые уже встречаются в ваших доках:
    1) `Document(page_content="path/to/file.docx")`
    2) `Document(page_content="<markdown/text>", metadata={"source": "path/to/file.md"})`
    """

    meta = dict(doc.metadata or {})
    page_content = doc.page_content

    # Сценарий: page_content — путь
    maybe_path = Path(page_content)
    if page_content and len(page_content) < 512 and maybe_path.exists() and maybe_path.is_file():
        fmt = _detect_format_from_path(maybe_path)
        return SourceDocument(format=fmt, source_path=maybe_path, text=None, metadata=meta)

    # Сценарий: metadata["source"] — путь
    src = meta.get("source")
    if isinstance(src, str):
        src_path = Path(src)
        if src_path.exists() and src_path.is_file():
            fmt = _detect_format_from_path(src_path)
            return SourceDocument(format=fmt, source_path=src_path, text=page_content, metadata=meta)

    # Иначе считаем текстом; формат пытаемся угадать по content (пока минимально)
    # Если нужен более строгий детектор — вынесем в отдельный модуль.
    if isinstance(page_content, str) and page_content.strip().startswith("#"):
        return SourceDocument(format=DocumentFormat.MARKDOWN, source_path=None, text=page_content, metadata=meta)

    if isinstance(page_content, str) and page_content.strip():
        return SourceDocument(format=DocumentFormat.TXT, source_path=None, text=page_content, metadata=meta)

    raise InputResolutionError("Не удалось определить вход: ни путь к файлу, ни текст не распознаны")


@dataclass
class Pipeline:
    """
    Главный оркестратор.

    MVP:
    - Markdown парсится локально
    - Для file-based форматов используем documentor_old через адаптер
    - Затем нормализуем: ids + parent_id
    """

    registry: ParserRegistry
    old_adapter: DocumentorOldAdapter

    def run(self, doc: LCDocument) -> ParsedDocument:
        source = _resolve_source(doc)

        # Текстовые форматы (markdown/txt) — парсим локально.
        if source.text and source.format in (DocumentFormat.MARKDOWN, DocumentFormat.TXT):
            parser = self.registry.get(source)
            raw_elements = parser.parse(source)
        else:
            # file-based: пока используем старую реализацию (PDF/DOCX/DOC/IMG/TXT)
            if not source.source_path:
                raise UnsupportedFormatError(
                    f"Формат {source.format} без source_path пока не поддержан"
                )
            raw_elements = self.old_adapter.parse_file(source.source_path)

        normalized = self._normalize(raw_elements)
        return ParsedDocument(elements=normalized, source=source.metadata)

    def _normalize(self, elements: list[Element]) -> list[Element]:
        # 1) ids
        gen = SequentialIdGenerator()
        with_ids: list[Element] = []
        for el in elements:
            new_id = gen.next_id()
            with_ids.append(replace(el, id=new_id))

        # 2) hierarchy
        with_parents = assign_parents_by_headers(with_ids)
        return with_parents


def pipeline(document: LCDocument) -> list[dict]:
    """
    Функция “как в доках”: `from documentor import pipeline`.

    Возвращаем list[dict], чтобы результат было удобно сразу сохранить в json.
    """

    registry = ParserRegistry()
    registry.register(MarkdownParser())
    registry.register(PlainTextParser())

    p = Pipeline(
        registry=registry,
        old_adapter=DocumentorOldAdapter(artifact_store=LocalArtifactStore()),
    )
    return p.run(document).to_dicts()


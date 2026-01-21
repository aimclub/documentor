"""
Парсер для Markdown документов.

Содержит логику для:
- Токенизации Markdown текста (заголовки, таблицы, списки, цитаты, код-блоки)
- Построения иерархии элементов на основе заголовков
- Назначения parent_id элементам

Использует regex для определения типов блоков и header_stack для построения иерархии.
Не требует LLM - полностью локальный парсинг.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from langchain_core.documents import Document

from ....domain import DocumentFormat, Element, ElementType, ParsedDocument
from ..base import BaseParser


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
LIST_RE = re.compile(r"^(\s*)([-*+]|\d+\.)\s+(.*)$")
QUOTE_RE = re.compile(r"^>\s?(.*)$")
TABLE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$")


@dataclass(slots=True)
class MarkdownBlock:
    type: ElementType
    content: str


class MarkdownParser(BaseParser):
    format = DocumentFormat.MARKDOWN

    def parse(self, document: Document) -> ParsedDocument:
        source = self.get_source(document)
        blocks = self._tokenize(document.page_content or "")
        elements: List[Element] = []
        header_stack: List[Tuple[int, str]] = []

        for block in blocks:
            element_type = block.type
            parent_id: Optional[str] = header_stack[-1][1] if header_stack else None

            if element_type.name.startswith("HEADER_"):
                level = int(element_type.value.split("_")[-1])
                while header_stack and header_stack[-1][0] >= level:
                    header_stack.pop()
                parent_id = header_stack[-1][1] if header_stack else None

                element_id = self.id_generator.next_id()
                elements.append(
                    Element(
                        id=element_id,
                        type=element_type,
                        content=block.content,
                        parent_id=parent_id,
                        metadata={},
                    )
                )
                header_stack.append((level, element_id))
                continue

            elements.append(
                Element(
                    id=self.id_generator.next_id(),
                    type=element_type,
                    content=block.content,
                    parent_id=parent_id,
                    metadata={},
                )
            )

        return ParsedDocument(
            source=source,
            format=self.format,
            elements=elements,
            metadata={"parser": "markdown"},
        )

    def _tokenize(self, text: str) -> Iterable[MarkdownBlock]:
        lines = text.splitlines()
        buffer: List[str] = []
        in_code_block = False

        def flush_plain() -> Iterable[MarkdownBlock]:
            nonlocal buffer
            if not buffer:
                return []
            content = "\n".join(buffer).strip()
            buffer = []
            return [MarkdownBlock(ElementType.TEXT, content)] if content else []

        idx = 0
        while idx < len(lines):
            line = lines[idx]
            stripped = line.strip()

            if stripped.startswith("```"):
                if in_code_block:
                    code = "\n".join(buffer)
                    buffer = []
                    in_code_block = False
                    yield MarkdownBlock(ElementType.TEXT, code)
                else:
                    in_code_block = True
                idx += 1
                continue

            if in_code_block:
                buffer.append(line)
                idx += 1
                continue

            heading_match = HEADING_RE.match(line)
            if heading_match:
                yield from flush_plain()
                level = len(heading_match.group(1))
                content = heading_match.group(2).strip()
                yield MarkdownBlock(self._heading_type(level), content)
                idx += 1
                continue

            if TABLE_ROW_RE.match(line):
                yield from flush_plain()
                table_lines = [line]
                idx += 1
                while idx < len(lines) and TABLE_ROW_RE.match(lines[idx]):
                    table_lines.append(lines[idx])
                    idx += 1
                yield MarkdownBlock(ElementType.TABLE, "\n".join(table_lines).strip())
                continue

            list_match = LIST_RE.match(line)
            if list_match:
                yield from flush_plain()
                indent, marker, content = list_match.groups()
                metadata = f"{marker}{' ' if indent else ''}"
                yield MarkdownBlock(ElementType.LIST_ITEM, f"{metadata}{content.strip()}")
                idx += 1
                continue

            quote_match = QUOTE_RE.match(line)
            if quote_match:
                yield from flush_plain()
                yield MarkdownBlock(ElementType.TEXT, quote_match.group(1).strip())
                idx += 1
                continue

            if stripped:
                buffer.append(line)
            else:
                yield from flush_plain()
            idx += 1

        if in_code_block:
            yield MarkdownBlock(ElementType.TEXT, "\n".join(buffer).strip())
        else:
            yield from flush_plain()

    def _heading_type(self, level: int) -> ElementType:
        level = max(1, min(level, 6))
        return ElementType[f"HEADER_{level}"]
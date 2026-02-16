"""
Parser for Markdown documents.

Uses regular expressions for parsing Markdown and converts result
into structured elements with hierarchy.

Supported elements:
- Headers (HEADER_1-6)
- Lists (LIST_ITEM)
- Tables (TABLE)
- Images (IMAGE)
- Code blocks (CODE_BLOCK)
- Links (LINK)
- Quotes (TEXT with metadata)
- Text (TEXT)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

import pandas as pd
from langchain_core.documents import Document

from ....domain import DocumentFormat, Element, ElementType, ParsedDocument
from ....exceptions import ParsingError
from ..base import BaseParser

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MarkdownBlock:
    """Temporary structure for storing Markdown block."""

    type: ElementType
    content: str
    metadata: dict[str, Any] | None = None
    line_number: int = 0  # Line number for tracking order


class MarkdownParser(BaseParser):
    """
    Parser for Markdown documents.

    Uses regular expressions for parsing and converts result into structured elements.
    """

    format = DocumentFormat.MARKDOWN

    # Regular expressions for parsing
    HEADER_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    LIST_ITEM_PATTERN = re.compile(r'^(\s*)([-*+]\s+|\d+\.\s+)(.+)$', re.MULTILINE)
    TABLE_PATTERN = re.compile(r'^\s*\|.+\|\s*$', re.MULTILINE)
    IMAGE_PATTERN = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
    LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    CODE_BLOCK_PATTERN = re.compile(r'```([\w]*)\n([\s\S]*?)```')
    INLINE_CODE_PATTERN = re.compile(r'`([^`]+)`')
    BLOCKQUOTE_PATTERN = re.compile(r'^(\>+\s+)(.+)', re.MULTILINE)
    THEMATIC_BREAK_PATTERN = re.compile(r'^(\*{3,}|-{3,}|_{3,})\s*$', re.MULTILINE)

    def parse(self, document: Document) -> ParsedDocument:
        """
        Parse Markdown document and return structured representation.

        Args:
            document: LangChain Document with Markdown content

        Returns:
            ParsedDocument: Structured document representation

        Raises:
            ValidationError: If input data is invalid
            UnsupportedFormatError: If document format is not supported
            ParsingError: If parsing error occurred
        """
        # Input validation via BaseParser
        self._validate_input(document)

        source = self.get_source(document)
        self._log_parsing_start(source)

        try:
            # Load content from file if page_content is empty
            markdown_text = document.page_content or ""
            if not markdown_text.strip() and source != "unknown":
                try:
                    file_path = Path(source)
                    if file_path.exists() and file_path.is_file():
                        with open(file_path, "r", encoding="utf-8") as f:
                            markdown_text = f.read()
                        logger.debug(f"Loaded Markdown content from file: {source}")
                    else:
                        logger.warning(f"File not found: {source}")
                except Exception as e:
                    logger.warning(f"Failed to load file content from {source}: {e}")
                    # Continue with empty content

            # Parse document line by line
            blocks = self._parse_markdown(markdown_text)

            # Build hierarchy and create elements
            elements = self._build_elements(blocks)

            # Create ParsedDocument
            parsed_document = ParsedDocument(
                source=source,
                format=self.format,
                elements=elements,
                metadata={
                    "parser": "markdown",
                    "status": "completed",
                    "source_type": "regex",
                    "elements_count": len(elements),
                    "headers_count": len([e for e in elements if e.type.name.startswith("HEADER")]),
                    "tables_count": len([e for e in elements if e.type == ElementType.TABLE]),
                    "images_count": len([e for e in elements if e.type == ElementType.IMAGE]),
                },
            )

            # Result validation
            self._validate_parsed_document(parsed_document)

            self._log_parsing_end(source, len(elements))

            return parsed_document

        except Exception as e:
            error_msg = f"Error parsing Markdown document (source: {source})"
            logger.error(f"{error_msg}. Original error: {e}")
            raise ParsingError(error_msg, source=source) from e

    def _parse_markdown(self, text: str) -> List[MarkdownBlock]:
        """
        Parses Markdown text and returns list of blocks.

        Args:
            text: Markdown text

        Returns:
            List of MarkdownBlock
        """
        blocks: List[MarkdownBlock] = []
        lines = text.split('\n')
        i = 0
        line_count = len(lines)

        while i < line_count:
            line = lines[i]
            stripped = line.strip()

            # Skip empty lines
            if not stripped:
                i += 1
                continue

            # 1. Code blocks (multiline, higher priority)
            if stripped.startswith('```'):
                # Find end of code block
                language = stripped[3:].strip()
                i += 1
                code_lines = []
                # Collect lines until closing ```
                while i < line_count:
                    if lines[i].strip() == '```':
                        break
                    code_lines.append(lines[i])
                    i += 1
                # Skip closing ```
                if i < line_count:
                    i += 1
                code_content = '\n'.join(code_lines)
                metadata = {"source": "markdown"}
                if language:
                    metadata["language"] = language
                blocks.append(
                    MarkdownBlock(
                        type=ElementType.CODE_BLOCK,
                        content=code_content,
                        metadata=metadata,
                        line_number=i - len(code_lines) - 2,
                    )
                )
                continue

            # 2. Horizontal lines
            if self.THEMATIC_BREAK_PATTERN.match(line):
                blocks.append(
                    MarkdownBlock(
                        type=ElementType.TEXT,
                        content="---",
                        metadata={"source": "markdown", "separator": True},
                        line_number=i,
                    )
                )
                i += 1
                continue

            # 3. Headers
            header_match = self.HEADER_PATTERN.match(line)
            if header_match:
                level = len(header_match.group(1))
                content = header_match.group(2).strip()
                element_type = ElementType[f"HEADER_{level}"]
                blocks.append(
                    MarkdownBlock(
                        type=element_type,
                        content=content,
                        metadata={"source": "markdown", "level": level},
                        line_number=i
                    )
                )
                i += 1
                continue

            # 4. Tables
            if '|' in line and self.TABLE_PATTERN.match(line):
                # Collect all table rows
                table_lines = [line]
                i += 1
                # Skip delimiter (---)
                delimiter_line = None
                if i < line_count and '|' in lines[i] and re.match(r'^\s*\|[-:\s|]+\|\s*$', lines[i]):
                    delimiter_line = lines[i]
                    i += 1
                # Collect data rows
                while i < line_count and '|' in lines[i] and self.TABLE_PATTERN.match(lines[i]):
                    table_lines.append(lines[i])
                    i += 1
                table_content = '\n'.join(table_lines)
                
                # Parse table to DataFrame
                try:
                    df = self._parse_table_to_dataframe(table_lines, delimiter_line)
                    metadata = {
                        "source": "markdown",
                        "dataframe": df,
                        "rows_count": len(df),
                        "cols_count": len(df.columns),
                    }
                except Exception as e:
                    # If failed to parse to DataFrame, create empty DataFrame
                    logger.warning(f"Failed to parse table to DataFrame: {e}")
                    metadata = {
                        "source": "markdown",
                        "dataframe": pd.DataFrame(),  # Always create DataFrame, even if empty
                        "rows_count": 0,
                        "cols_count": 0,
                    }
                
                blocks.append(
                    MarkdownBlock(
                        type=ElementType.TABLE,
                        content=table_content,
                        metadata=metadata,
                        line_number=i - len(table_lines),
                    )
                )
                continue

            # 5. Quotes
            blockquote_match = self.BLOCKQUOTE_PATTERN.match(line)
            if blockquote_match:
                quote_content = blockquote_match.group(2).strip()
                # Collect multiline quotes
                i += 1
                while i < line_count and lines[i].strip().startswith('>'):
                    quote_content += ' ' + lines[i].strip().lstrip('>').strip()
                    i += 1
                blocks.append(
                    MarkdownBlock(
                        type=ElementType.TEXT,
                        content=quote_content,
                        metadata={"source": "markdown", "quote": True},
                        line_number=i - 1,
                    )
                )
                continue

            # 6. Lists (with nesting support)
            list_match = self.LIST_ITEM_PATTERN.match(line)
            if list_match:
                indent = len(list_match.group(1))  # Number of spaces for indentation
                content = list_match.group(3).strip()
                # Determine list type
                list_marker = list_match.group(2).strip()
                is_ordered = bool(re.match(r'\d+\.', list_marker))
                # Nesting level determined by indent (every 2-4 spaces = 1 level)
                # Markdown standard: 2 or 4 spaces per level
                list_level = indent // 2 if indent > 0 else 0
                metadata = {
                    "source": "markdown",
                    "list_type": "ordered" if is_ordered else "unordered",
                    "list_level": list_level,
                    "indent": indent,
                }
                blocks.append(
                    MarkdownBlock(
                        type=ElementType.LIST_ITEM,
                        content=content,
                        metadata=metadata,
                        line_number=i,
                    )
                )
                i += 1
                continue

            # 7. Images (standalone or inline)
            image_matches = list(self.IMAGE_PATTERN.finditer(line))
            if image_matches:
                # Remove images from line to check if text remains
                line_without_images = self.IMAGE_PATTERN.sub('', line).strip()
                
                for match in image_matches:
                    alt_text = match.group(1)
                    url = match.group(2)
                    metadata = {"source": "markdown", "alt": alt_text, "src": url}
                    blocks.append(
                        MarkdownBlock(
                            type=ElementType.IMAGE,
                            content=alt_text or url,
                            metadata=metadata,
                            line_number=i,
                        )
                    )
                
                # If text remains after removing images, process it separately
                if line_without_images:
                    # Check if there are links in remaining text
                    link_matches = list(self.LINK_PATTERN.finditer(line_without_images))
                    if link_matches:
                        for match in link_matches:
                            link_text = match.group(1)
                            url = match.group(2)
                            metadata = {"source": "markdown", "href": url}
                            blocks.append(
                                MarkdownBlock(
                                    type=ElementType.LINK,
                                    content=link_text or url,
                                    metadata=metadata,
                                    line_number=i,
                                )
                            )
                        line_without_images = self.LINK_PATTERN.sub(r'\1', line_without_images)
                    
                    # Add remaining text
                    clean_text = self.INLINE_CODE_PATTERN.sub(r'\1', line_without_images).strip()
                    if clean_text:
                        # Extract links from remaining text
                        remaining_links = list(self.LINK_PATTERN.finditer(clean_text))
                        links_in_text = [match.group(2) for match in remaining_links]
                        
                        metadata = {"source": "markdown"}
                        if links_in_text:
                            metadata["links"] = links_in_text
                        
                        blocks.append(
                            MarkdownBlock(
                                type=ElementType.TEXT,
                                content=clean_text,
                                metadata=metadata,
                                line_number=i
                            )
                        )
                i += 1
                continue

            # 8. Links (standalone or inline)
            link_matches = list(self.LINK_PATTERN.finditer(line))
            if link_matches:
                # Calculate total length of all links in line
                total_link_length = sum(match.end() - match.start() for match in link_matches)
                line_length = len(line.strip())
                
                # If line consists only of links (with spaces), create only link elements
                if total_link_length >= line_length * 0.8:  # 80% of line is links
                    # Line consists mostly of links
                    for match in link_matches:
                        link_text = match.group(1)
                        url = match.group(2)
                        metadata = {"source": "markdown", "href": url}
                        blocks.append(
                            MarkdownBlock(
                                type=ElementType.LINK,
                                content=link_text or url,
                                metadata=metadata,
                                line_number=i,
                            )
                        )
                    i += 1
                    continue
                else:
                    # There is text besides links - create link elements and process text
                    for match in link_matches:
                        link_text = match.group(1)
                        url = match.group(2)
                        metadata = {"source": "markdown", "href": url}
                        blocks.append(
                            MarkdownBlock(
                                type=ElementType.LINK,
                                content=link_text or url,
                                metadata=metadata,
                                line_number=i,
                            )
                        )
                    # Remove links from line and process remaining text
                    line_without_links = self.LINK_PATTERN.sub(r'\1', line).strip()
                    clean_text = self.INLINE_CODE_PATTERN.sub(r'\1', line_without_links).strip()
                    if clean_text:
                        # Extract any remaining links from text (if any escaped or malformed)
                        remaining_links = list(self.LINK_PATTERN.finditer(clean_text))
                        links_in_text = [match.group(2) for match in remaining_links]
                        
                        metadata = {"source": "markdown"}
                        if links_in_text:
                            metadata["links"] = links_in_text
                        
                        blocks.append(
                            MarkdownBlock(
                                type=ElementType.TEXT,
                                content=clean_text,
                                metadata=metadata,
                                line_number=i
                            )
                        )
                    i += 1
                    continue

            # 9. Regular text (paragraph)
            # Remove inline code from text for clarity
            clean_text = self.INLINE_CODE_PATTERN.sub(r'\1', line).strip()
            if clean_text:
                blocks.append(
                    MarkdownBlock(
                        type=ElementType.TEXT,
                        content=clean_text,
                        metadata={"source": "markdown"},
                        line_number=i
                    )
                )

            i += 1

        return blocks

    def _parse_table_to_dataframe(self, table_lines: List[str], delimiter_line: Optional[str] = None) -> pd.DataFrame:
        """
        Parses Markdown table to pandas DataFrame.

        Args:
            table_lines: List of table rows (including header and data)
            delimiter_line: Delimiter line (optional, not used but kept for compatibility)

        Returns:
            pandas.DataFrame: Parsed table

        Raises:
            ValueError: If table cannot be parsed
        """
        if not table_lines:
            raise ValueError("Table lines cannot be empty")

        # Parse table rows
        rows = []
        for line in table_lines:
            # Remove leading and trailing spaces
            stripped = line.strip()
            if not stripped.startswith('|') or not stripped.endswith('|'):
                continue
            
            # Split by | and process cells
            # Remove first and last |, then split
            cells = [cell.strip() for cell in stripped[1:-1].split('|')]
            rows.append(cells)

        if not rows:
            raise ValueError("No valid rows found in table")

        # First row is headers
        headers = rows[0]
        
        # Determine maximum number of columns (in case of mismatch)
        max_cols = max(len(row) for row in rows) if rows else 0
        
        # Normalize all rows to same number of columns
        normalized_rows = []
        for row in rows:
            # Pad with empty strings if columns are fewer
            while len(row) < max_cols:
                row.append("")
            # Truncate if columns are more (shouldn't happen, but just in case)
            normalized_rows.append(row[:max_cols])
        
        # Normalize headers
        if len(headers) < max_cols:
            headers.extend([f"Column_{i+1}" for i in range(len(headers), max_cols)])
        headers = headers[:max_cols]
        
        # Remaining rows are data (skip first row with headers)
        data_rows = normalized_rows[1:]

        # Create DataFrame
        df = pd.DataFrame(data_rows, columns=headers)

        return df

    def _build_elements(self, blocks: List[MarkdownBlock]) -> List[Element]:
        """
        Builds elements with hierarchy from blocks.

        Args:
            blocks: List of MarkdownBlock

        Returns:
            List of Element with built hierarchy
        """
        elements: List[Element] = []
        header_stack: List[tuple[int, str]] = []
        list_stack: List[tuple[int, str]] = []  # Stack for nested lists: (level, element_id)

        # Sort blocks by line number to preserve order
        sorted_blocks = sorted(blocks, key=lambda b: b.line_number)

        for block in sorted_blocks:
            element_type = block.type
            parent_id: Optional[str] = None

            # Header processing - update hierarchy stack
            if element_type.name.startswith("HEADER_"):
                level = int(element_type.name.split("_")[-1])
                # Remove headers with level >= current
                while header_stack and header_stack[-1][0] >= level:
                    header_stack.pop()
                # Parent is last header in stack
                parent_id = header_stack[-1][1] if header_stack else None
                # Clear list stack when encountering header
                list_stack.clear()

                # Create header element
                element = self._create_element(
                    type=element_type,
                    content=block.content,
                    parent_id=parent_id,
                    metadata=block.metadata or {},
                )
                elements.append(element)

                # Add to stack
                header_stack.append((level, element.id))
                continue

            # List item processing - build list hierarchy
            if element_type == ElementType.LIST_ITEM:
                list_level = block.metadata.get("list_level", 0) if block.metadata else 0
                
                # Remove list items with level >= current
                while list_stack and list_stack[-1][0] >= list_level:
                    list_stack.pop()
                
                # Parent determined by priority:
                # 1. Last list item of same or higher level
                # 2. Last header
                if list_stack:
                    # If there are list items in stack, parent is last item of same level
                    # or nearest item of higher level
                    parent_id = list_stack[-1][1]
                else:
                    # If list stack is empty, parent is last header
                    parent_id = header_stack[-1][1] if header_stack else None

                # Create list item element
                element = self._create_element(
                    type=element_type,
                    content=block.content,
                    parent_id=parent_id,
                    metadata=block.metadata or {},
                )
                elements.append(element)

                # Add to list stack
                list_stack.append((list_level, element.id))
                continue

            # For other elements (text, tables, code blocks, links, images)
            # Parent determined by priority:
            # 1. Last list item (if we're inside a list)
            # 2. Last header
            if list_stack:
                parent_id = list_stack[-1][1]
            else:
                parent_id = header_stack[-1][1] if header_stack else None

            element = self._create_element(
                type=element_type,
                content=block.content,
                parent_id=parent_id,
                metadata=block.metadata or {},
            )
            elements.append(element)

        return elements

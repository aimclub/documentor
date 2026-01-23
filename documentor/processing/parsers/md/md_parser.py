"""
Парсер для Markdown документов.

Использует регулярные выражения для парсинга Markdown и преобразует результат
в структурированные элементы с иерархией.

Поддерживаемые элементы:
- Заголовки (HEADER_1-6)
- Списки (LIST_ITEM)
- Таблицы (TABLE)
- Изображения (IMAGE)
- Код-блоки (CODE_BLOCK)
- Ссылки (LINK)
- Цитаты (TEXT с metadata)
- Текст (TEXT)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List, Optional

import pandas as pd
from langchain_core.documents import Document

from ....domain import DocumentFormat, Element, ElementType, ParsedDocument
from ....exceptions import ParsingError
from ..base import BaseParser


@dataclass(slots=True)
class MarkdownBlock:
    """Временная структура для хранения блока Markdown."""

    type: ElementType
    content: str
    metadata: dict[str, Any] | None = None
    line_number: int = 0  # Номер строки для отслеживания порядка


class MarkdownParser(BaseParser):
    """
    Парсер для Markdown документов.

    Использует регулярные выражения для парсинга и преобразует результат в структурированные элементы.
    """

    format = DocumentFormat.MARKDOWN

    # Регулярные выражения для парсинга
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
        Парсит Markdown документ и возвращает структурированное представление.

        Args:
            document: LangChain Document с Markdown контентом

        Returns:
            ParsedDocument: Структурированное представление документа

        Raises:
            ValidationError: Если входные данные невалидны
            UnsupportedFormatError: Если формат документа не поддерживается
            ParsingError: Если произошла ошибка при парсинге
        """
        # Валидация входных данных через BaseParser
        self._validate_input(document)

        source = self.get_source(document)
        self._log_parsing_start(source)

        try:
            markdown_text = document.page_content or ""

            # Парсим документ построчно
            blocks = self._parse_markdown(markdown_text)

            # Строим иерархию и создаем элементы
            elements = self._build_elements(blocks)

            # Создаем ParsedDocument
            parsed_document = ParsedDocument(
                source=source,
                format=self.format,
                elements=elements,
                metadata={"parser": "markdown", "source_type": "regex"},
            )

            # Валидация результата
            self._validate_parsed_document(parsed_document)

            self._log_parsing_end(source, len(elements))

            return parsed_document

        except Exception as e:
            error_msg = f"Ошибка при парсинге Markdown документа (источник: {source})"
            self._logger.error(f"{error_msg}. Исходная ошибка: {e}")
            raise ParsingError(error_msg, source=source) from e

    def _parse_markdown(self, text: str) -> List[MarkdownBlock]:
        """
        Парсит Markdown текст и возвращает список блоков.

        Args:
            text: Markdown текст

        Returns:
            Список MarkdownBlock
        """
        blocks: List[MarkdownBlock] = []
        lines = text.split('\n')
        i = 0
        line_count = len(lines)

        while i < line_count:
            line = lines[i]
            stripped = line.strip()

            # Пропускаем пустые строки
            if not stripped:
                i += 1
                continue

            # 1. Код-блоки (многострочные, приоритет выше)
            if stripped.startswith('```'):
                # Находим конец блока кода
                language = stripped[3:].strip()
                i += 1
                code_lines = []
                # Собираем строки до закрывающего ```
                while i < line_count:
                    if lines[i].strip() == '```':
                        break
                    code_lines.append(lines[i])
                    i += 1
                # Пропускаем закрывающий ```
                if i < line_count:
                    i += 1
                code_content = '\n'.join(code_lines)
                metadata = {"language": language} if language else {}
                blocks.append(
                    MarkdownBlock(
                        type=ElementType.CODE_BLOCK,
                        content=code_content,
                        metadata=metadata,
                        line_number=i - len(code_lines) - 2,
                    )
                )
                continue

            # 2. Горизонтальные линии
            if self.THEMATIC_BREAK_PATTERN.match(line):
                blocks.append(
                    MarkdownBlock(
                        type=ElementType.TEXT,
                        content="---",
                        metadata={"separator": True},
                        line_number=i,
                    )
                )
                i += 1
                continue

            # 3. Заголовки
            header_match = self.HEADER_PATTERN.match(line)
            if header_match:
                level = len(header_match.group(1))
                content = header_match.group(2).strip()
                element_type = ElementType[f"HEADER_{level}"]
                blocks.append(
                    MarkdownBlock(type=element_type, content=content, line_number=i)
                )
                i += 1
                continue

            # 4. Таблицы
            if '|' in line and self.TABLE_PATTERN.match(line):
                # Собираем все строки таблицы
                table_lines = [line]
                i += 1
                # Пропускаем разделитель (---)
                delimiter_line = None
                if i < line_count and '|' in lines[i] and re.match(r'^\s*\|[-:\s|]+\|\s*$', lines[i]):
                    delimiter_line = lines[i]
                    i += 1
                # Собираем строки данных
                while i < line_count and '|' in lines[i] and self.TABLE_PATTERN.match(lines[i]):
                    table_lines.append(lines[i])
                    i += 1
                table_content = '\n'.join(table_lines)
                
                # Парсим таблицу в DataFrame
                try:
                    df = self._parse_table_to_dataframe(table_lines, delimiter_line)
                    metadata = {"dataframe": df, "rows": len(df), "columns": len(df.columns)}
                except Exception as e:
                    # Если не удалось распарсить в DataFrame, сохраняем только текст
                    self._logger.warning(f"Failed to parse table to DataFrame: {e}")
                    metadata = {}
                
                blocks.append(
                    MarkdownBlock(
                        type=ElementType.TABLE,
                        content=table_content,
                        metadata=metadata,
                        line_number=i - len(table_lines),
                    )
                )
                continue

            # 5. Цитаты
            blockquote_match = self.BLOCKQUOTE_PATTERN.match(line)
            if blockquote_match:
                quote_content = blockquote_match.group(2).strip()
                # Собираем многострочные цитаты
                i += 1
                while i < line_count and lines[i].strip().startswith('>'):
                    quote_content += ' ' + lines[i].strip().lstrip('>').strip()
                    i += 1
                blocks.append(
                    MarkdownBlock(
                        type=ElementType.TEXT,
                        content=quote_content,
                        metadata={"quote": True},
                        line_number=i - 1,
                    )
                )
                continue

            # 6. Списки
            list_match = self.LIST_ITEM_PATTERN.match(line)
            if list_match:
                content = list_match.group(3).strip()
                # Определяем тип списка
                list_marker = list_match.group(2).strip()
                is_ordered = bool(re.match(r'\d+\.', list_marker))
                metadata = {"list_type": "ordered" if is_ordered else "unordered"}
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

            # 7. Изображения (inline, обрабатываем в тексте)
            image_matches = list(self.IMAGE_PATTERN.finditer(line))
            if image_matches:
                for match in image_matches:
                    alt_text = match.group(1)
                    url = match.group(2)
                    metadata = {"alt": alt_text, "src": url}
                    blocks.append(
                        MarkdownBlock(
                            type=ElementType.IMAGE,
                            content=alt_text or url,
                            metadata=metadata,
                            line_number=i,
                        )
                    )
                # Удаляем изображения из строки для дальнейшей обработки
                line = self.IMAGE_PATTERN.sub('', line)

            # 8. Ссылки (inline, обрабатываем в тексте)
            link_matches = list(self.LINK_PATTERN.finditer(line))
            if link_matches:
                for match in link_matches:
                    link_text = match.group(1)
                    url = match.group(2)
                    metadata = {"href": url}
                    blocks.append(
                        MarkdownBlock(
                            type=ElementType.LINK,
                            content=link_text or url,
                            metadata=metadata,
                            line_number=i,
                        )
                    )
                # Удаляем ссылки из строки для дальнейшей обработки
                line = self.LINK_PATTERN.sub(r'\1', line)

            # 9. Обычный текст (параграф)
            # Убираем inline код из текста для чистоты
            clean_text = self.INLINE_CODE_PATTERN.sub(r'\1', line).strip()
            if clean_text:
                blocks.append(
                    MarkdownBlock(type=ElementType.TEXT, content=clean_text, line_number=i)
                )

            i += 1

        return blocks

    def _parse_table_to_dataframe(self, table_lines: List[str], delimiter_line: Optional[str] = None) -> pd.DataFrame:
        """
        Парсит Markdown таблицу в pandas DataFrame.

        Args:
            table_lines: Список строк таблицы (включая заголовок и данные)
            delimiter_line: Строка-разделитель (опционально, не используется, но оставлена для совместимости)

        Returns:
            pandas.DataFrame: Распарсенная таблица

        Raises:
            ValueError: Если таблица не может быть распарсена
        """
        if not table_lines:
            raise ValueError("Table lines cannot be empty")

        # Парсим строки таблицы
        rows = []
        for line in table_lines:
            # Убираем начальные и конечные пробелы
            stripped = line.strip()
            if not stripped.startswith('|') or not stripped.endswith('|'):
                continue
            
            # Разбиваем по | и обрабатываем ячейки
            # Убираем первый и последний |, затем разбиваем
            cells = [cell.strip() for cell in stripped[1:-1].split('|')]
            rows.append(cells)

        if not rows:
            raise ValueError("No valid rows found in table")

        # Первая строка - заголовки
        headers = rows[0]
        
        # Определяем максимальное количество колонок (на случай несовпадения)
        max_cols = max(len(row) for row in rows) if rows else 0
        
        # Нормализуем все строки до одинакового количества колонок
        normalized_rows = []
        for row in rows:
            # Дополняем пустыми строками, если колонок меньше
            while len(row) < max_cols:
                row.append("")
            # Обрезаем, если колонок больше (не должно быть, но на всякий случай)
            normalized_rows.append(row[:max_cols])
        
        # Нормализуем заголовки
        if len(headers) < max_cols:
            headers.extend([f"Column_{i+1}" for i in range(len(headers), max_cols)])
        headers = headers[:max_cols]
        
        # Остальные строки - данные (пропускаем первую строку с заголовками)
        data_rows = normalized_rows[1:]

        # Создаем DataFrame
        df = pd.DataFrame(data_rows, columns=headers)

        return df

    def _build_elements(self, blocks: List[MarkdownBlock]) -> List[Element]:
        """
        Строит элементы с иерархией из блоков.

        Args:
            blocks: Список MarkdownBlock

        Returns:
            Список Element с построенной иерархией
        """
        elements: List[Element] = []
        header_stack: List[tuple[int, str]] = []

        # Сортируем блоки по номеру строки для сохранения порядка
        sorted_blocks = sorted(blocks, key=lambda b: b.line_number)

        for block in sorted_blocks:
            element_type = block.type
            parent_id: Optional[str] = header_stack[-1][1] if header_stack else None

            # Обработка заголовков - обновляем стек иерархии
            if element_type.name.startswith("HEADER_"):
                level = int(element_type.name.split("_")[-1])
                # Удаляем заголовки с уровнем >= текущего
                while header_stack and header_stack[-1][0] >= level:
                    header_stack.pop()
                # Родитель - последний заголовок в стеке
                parent_id = header_stack[-1][1] if header_stack else None

                # Создаем элемент заголовка
                element = self._create_element(
                    type=element_type,
                    content=block.content,
                    parent_id=parent_id,
                    metadata=block.metadata or {},
                )
                elements.append(element)

                # Добавляем в стек
                header_stack.append((level, element.id))
                continue

            # Для остальных элементов используем последний заголовок как родителя
            element = self._create_element(
                type=element_type,
                content=block.content,
                parent_id=parent_id,
                metadata=block.metadata or {},
            )
            elements.append(element)

        return elements

"""
Парсинг HTML таблиц из Dots OCR в markdown и pandas DataFrame.

Dots OCR возвращает таблицы в HTML формате согласно промпту prompt_layout_all_en.
Этот модуль конвертирует HTML в markdown и DataFrame для использования в парсере.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple
from io import StringIO

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    logging.warning("pandas not available, DataFrame conversion will be disabled")

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    logging.warning("beautifulsoup4 not available, HTML parsing will be disabled")

logger = logging.getLogger(__name__)


def parse_table_from_html(
    html_content: str,
    method: str = "markdown",
) -> Tuple[Optional[str], Optional[Any], bool]:
    """
    Парсит HTML таблицу из Dots OCR в markdown или DataFrame.
    
    Args:
        html_content: HTML строка с таблицей (может содержать одну или несколько таблиц)
        method: Метод парсинга ("markdown" или "dataframe")
    
    Returns:
        tuple[str, Any, bool]:
            - markdown_content: Markdown таблица или None
            - dataframe: pandas DataFrame или None
            - success: Статус успешности операции
    """
    if not html_content or not html_content.strip():
        logger.warning("Empty HTML content provided")
        return None, None, False
    
    if not HAS_BS4:
        logger.error("beautifulsoup4 is required for HTML table parsing")
        return None, None, False
    
    try:
        # Парсим HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Ищем все таблицы
        tables = soup.find_all('table')
        
        if not tables:
            logger.warning("No tables found in HTML content")
            return None, None, False
        
        # Берем первую таблицу (если несколько, можно расширить логику)
        table = tables[0]
        
        # Парсим таблицу в список строк
        rows = []
        for tr in table.find_all('tr'):
            cells = []
            for td in tr.find_all(['td', 'th']):
                # Извлекаем текст, сохраняя структуру
                cell_text = td.get_text(separator=' ', strip=True)
                # Обрабатываем merged cells (rowspan/colspan)
                rowspan = int(td.get('rowspan', 1))
                colspan = int(td.get('colspan', 1))
                
                # Для простоты пока игнорируем rowspan/colspan
                # В будущем можно добавить более сложную логику
                cells.append(cell_text)
            
            if cells:  # Игнорируем пустые строки
                rows.append(cells)
        
        if not rows:
            logger.warning("Table has no rows")
            return None, None, False
        
        # Создаем DataFrame
        if HAS_PANDAS:
            # Определяем, есть ли заголовок
            # Проверяем, есть ли th в первой строке или все строки имеют одинаковое количество колонок
            has_header = False
            if rows:
                # Проверяем первую строку на наличие th
                first_row_has_th = any(td.name == 'th' for tr in table.find_all('tr', limit=1) for td in tr.find_all(['td', 'th']))
                
                # Если первая строка имеет th или если строк больше 1 и первая строка выглядит как заголовок
                if first_row_has_th or (len(rows) > 1 and len(rows[0]) > 0):
                    # Проверяем, отличается ли первая строка от остальных (обычно заголовок короче или имеет другой формат)
                    if len(rows) > 1:
                        # Если первая строка имеет меньше колонок или все строки имеют одинаковое количество
                        if len(rows[0]) <= max(len(row) for row in rows[1:]) if rows[1:] else len(rows[0]):
                            has_header = True
                    else:
                        has_header = first_row_has_th
            
            try:
                if has_header and len(rows) > 1:
                    # Используем первую строку как заголовок
                    # Нормализуем количество колонок
                    max_cols = max(len(row) for row in rows)
                    header = list(rows[0]) + [''] * (max_cols - len(rows[0]))
                    data_rows = []
                    for row in rows[1:]:
                        normalized_row = list(row) + [''] * (max_cols - len(row))
                        data_rows.append(normalized_row[:max_cols])
                    df = pd.DataFrame(data_rows, columns=header[:max_cols])
                else:
                    # Нет заголовка, используем все строки как данные
                    max_cols = max(len(row) for row in rows) if rows else 0
                    normalized_rows = []
                    for row in rows:
                        normalized_row = list(row) + [''] * (max_cols - len(row))
                        normalized_rows.append(normalized_row[:max_cols])
                    df = pd.DataFrame(normalized_rows)
            except Exception as e:
                logger.warning(f"Error creating DataFrame: {e}, trying without header")
                # Fallback: создаем DataFrame без заголовка
                max_cols = max(len(row) for row in rows) if rows else 0
                normalized_rows = []
                for row in rows:
                    normalized_row = list(row) + [''] * (max_cols - len(row))
                    normalized_rows.append(normalized_row[:max_cols])
                df = pd.DataFrame(normalized_rows)
        else:
            df = None
        
        # Конвертируем в markdown
        if method == "markdown" or method == "both":
            markdown = _dataframe_to_markdown(rows, df if HAS_PANDAS else None)
        else:
            markdown = None
        
        return markdown, df, True
        
    except Exception as e:
        logger.error(f"Error parsing HTML table: {e}")
        return None, None, False


def _dataframe_to_markdown(rows: list, df: Optional[pd.DataFrame] = None) -> str:
    """
    Конвертирует таблицу в markdown формат.
    
    Args:
        rows: Список строк таблицы
        df: DataFrame (опционально, для использования встроенного метода)
    
    Returns:
        Markdown строка с таблицей
    """
    if df is not None and HAS_PANDAS:
        try:
            # Используем встроенный метод DataFrame
            return df.to_markdown(index=False)
        except Exception:
            # Fallback на ручную конвертацию
            pass
    
    # Ручная конвертация в markdown
    if not rows:
        return ""
    
    # Определяем количество колонок
    max_cols = max(len(row) for row in rows) if rows else 0
    
    # Нормализуем строки (добавляем пустые ячейки если нужно)
    normalized_rows = []
    for row in rows:
        normalized_row = list(row) + [''] * (max_cols - len(row))
        normalized_rows.append(normalized_row[:max_cols])
    
    if not normalized_rows:
        return ""
    
    # Создаем markdown таблицу
    markdown_lines = []
    
    # Заголовок (первая строка)
    header = normalized_rows[0]
    markdown_lines.append("| " + " | ".join(str(cell) for cell in header) + " |")
    
    # Разделитель
    markdown_lines.append("| " + " | ".join("---" for _ in header) + " |")
    
    # Данные
    for row in normalized_rows[1:]:
        markdown_lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    
    return "\n".join(markdown_lines)


def detect_merged_tables(markdown_content: str) -> list[str]:
    """
    Обнаруживает несколько таблиц в markdown контенте.
    
    Args:
        markdown_content: Markdown строка, возможно содержащая несколько таблиц
    
    Returns:
        Список отдельных таблиц в markdown формате
    """
    if not markdown_content:
        return []
    
    # Разделяем по двойным переносам строк (пустые строки между таблицами)
    parts = markdown_content.split('\n\n')
    
    tables = []
    current_table = []
    
    for part in parts:
        lines = part.strip().split('\n')
        # Проверяем, является ли это таблицей (содержит |)
        if any('|' in line for line in lines):
            if current_table:
                # Сохраняем предыдущую таблицу
                tables.append('\n'.join(current_table))
                current_table = []
            # Добавляем строки текущей таблицы
            current_table.extend(lines)
        else:
            if current_table:
                # Добавляем к текущей таблице
                current_table.extend(lines)
    
    # Добавляем последнюю таблицу
    if current_table:
        tables.append('\n'.join(current_table))
    
    # Если не нашли разделения, возвращаем как одну таблицу
    if not tables:
        tables = [markdown_content]
    
    return tables


def markdown_to_dataframe(markdown_content: str) -> Optional[pd.DataFrame]:
    """
    Конвертирует markdown таблицу в pandas DataFrame.
    
    Args:
        markdown_content: Markdown строка с таблицей
    
    Returns:
        pandas DataFrame или None в случае ошибки
    """
    if not HAS_PANDAS:
        logger.warning("pandas not available, cannot convert markdown to DataFrame")
        return None
    
    if not markdown_content or not markdown_content.strip():
        return None
    
    try:
        # Используем StringIO для чтения markdown
        from io import StringIO
        df = pd.read_csv(StringIO(markdown_content), sep='|', skipinitialspace=True)
        
        # Удаляем пустые колонки (которые могут появиться из-за разделителей |)
        df = df.dropna(axis=1, how='all')
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        
        return df
    except Exception as e:
        logger.warning(f"Error converting markdown to DataFrame: {e}")
        return None

"""
Парсинг таблиц через Qwen2.5 API.

Содержит функции для:
- Вызова Qwen API для парсинга таблиц из изображений
- Парсинга ответа в Markdown или DataFrame
- Обработки склеенных таблиц
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import openai
from PIL import Image

logger = logging.getLogger(__name__)


def _image_to_base64(image: Image.Image) -> str:
    """Конвертирует PIL Image в base64 data URL."""
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def parse_table_with_qwen(
    table_image: Image.Image,
    method: str = "markdown",
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    model_name: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Tuple[Optional[str], Optional[Any], bool]:
    """
    Парсит таблицу из изображения через Qwen2.5 API.
    
    Args:
        table_image: Изображение таблицы
        method: Метод парсинга ("markdown" или "dataframe")
        base_url: Базовый URL API (по умолчанию из env)
        api_key: API ключ (по умолчанию из env)
        temperature: Температура генерации (по умолчанию из env)
        max_tokens: Максимальное число токенов (по умолчанию из env)
        model_name: Имя модели (по умолчанию из env)
        timeout: Таймаут запроса в секундах (по умолчанию из env)
    
    Returns:
        tuple[str, Any, bool]:
            - markdown_content: Markdown таблица или None
            - dataframe: pandas DataFrame или None
            - success: Успешность операции
    """
    if base_url is None:
        base_url_raw = os.getenv("QWEN_BASE_URL")
        if base_url_raw:
            # Обрабатываем несколько URL (через запятую или перенос строки)
            # Берем первый валидный URL
            base_url = None
            for line in base_url_raw.split('\n'):
                for url in line.split(','):
                    url = url.strip()
                    if "#" in url:
                        url = url.split("#")[0].strip()
                    if url:
                        base_url = url
                        break
                if base_url:
                    break
    if api_key is None:
        api_key = os.getenv("QWEN_API_KEY")
    if temperature is None:
        temperature = float(os.getenv("QWEN_TEMPERATURE"))
    if max_tokens is None:
        max_tokens = int(os.getenv("QWEN_MAX_TOKENS"))
    if model_name is None:
        model_name = os.getenv("QWEN_MODEL_NAME")
    if timeout is None:
        timeout = int(os.getenv("QWEN_TIMEOUT"))
    
    if not base_url or not api_key:
        logger.error("QWEN_BASE_URL или QWEN_API_KEY не настроены")
        return None, None, False
    
    # Промпт для парсинга таблицы
    if method == "markdown":
        system_prompt = """You are Qwen, created by Alibaba Cloud. You are a helpful assistant.

Role: Table Structure Recognition (TSR) engine.
Task: extract ALL tables from the image and return them as GitHub-Flavored Markdown tables.

HARD OUTPUT RULES:
1) Output ONLY markdown tables. No explanations, numbering, titles, JSON, code, or code fences.
2) If there are multiple tables in the image, output multiple markdown tables separated by EXACTLY ONE blank line.
3) Do not hallucinate data: if a cell's text is unreadable, leave that cell empty but preserve the structure.
4) Preserve the exact row/column layout based on visible borders/alignment. Do not "reconstruct" missing structure.
5) Every row must have the same number of columns as the header. If cells are missing, pad with empty cells.
6) Header:
   - If a visual header exists (a distinct top row / styled header), use it.
   - Otherwise create a header: col1 | col2 | ... | colN.
7) Merged cells (rowspan/colspan):
   - Put the text into the top-left cell of the merged block.
   - Leave all covered cells empty, keeping the grid intact.
8) Encode line breaks inside a cell as <br>.
9) Escape the '|' character inside cell text as \\|.

QUALITY CHECK (internal only, do not output):
- Verify each row has a consistent number of '|' separators (N columns).
- Ensure the markdown separator row like | --- | --- | ... | is present for each table.

If no tables are present, output exactly:
<!-- NO_TABLE -->"""
        
        user_prompt = "Extract all tables from the image and return them strictly following the SYSTEM rules."
    else:
        system_prompt = None
        user_prompt = """Extract the table from this image and return it as a JSON array of arrays.

Requirements:
1. Each row should be an array of cell values
2. First row should contain headers
3. If multiple tables are merged, return an array of tables: [[table1], [table2]]
4. Handle merged cells by repeating the value or using null

Output only valid JSON, no additional text."""
    
    client = openai.OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
    )
    
    image_base64 = _image_to_base64(table_image)
    
    # Формируем messages с System и User ролями
    messages = []
    if system_prompt:
        messages.append({
            "role": "system",
            "content": system_prompt,
        })
    
    messages.append({
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": image_base64}},
            {"type": "text", "text": user_prompt},
        ],
    })
    
    try:
        request_params = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
        
        response = client.chat.completions.create(**request_params)
        content = response.choices[0].message.content
        
        if not content or len(content.strip()) == 0:
            logger.warning("Пустой ответ от Qwen для парсинга таблицы")
            return None, None, False
        
        # Проверяем, нет ли таблиц
        if "<!-- NO_TABLE -->" in content:
            logger.info("Qwen сообщил, что таблиц в изображении нет")
            return None, None, False
        
        # Парсим ответ
        if method == "markdown":
            markdown_content = content.strip()
            dataframe = markdown_to_dataframe(markdown_content)
            return markdown_content, dataframe, True
        else:
            try:
                data = json.loads(content)
                dataframe = _json_to_dataframe(data)
                markdown_content = _dataframe_to_markdown(dataframe) if dataframe is not None else None
                return markdown_content, dataframe, True
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка парсинга JSON от Qwen: {e}")
                return None, None, False
    
    except Exception as e:
        logger.error(f"Ошибка при вызове Qwen API для парсинга таблицы: {e}")
        return None, None, False


def markdown_to_dataframe(markdown: str) -> Optional[Any]:
    """Конвертирует Markdown таблицу в pandas DataFrame."""
    try:
        import pandas as pd
        
        lines = [line.strip() for line in markdown.split("\n") if line.strip()]
        if not lines:
            return None
        
        # Удаляем разделитель (вторую строку с |---|---|)
        filtered_lines = []
        for i, line in enumerate(lines):
            if i == 0 or not re.match(r'^\|[\s\-\|:]+\|$', line):
                filtered_lines.append(line)
        
        # Парсим строки
        rows = []
        for line in filtered_lines:
            if line.startswith("|") and line.endswith("|"):
                cells = [cell.strip() for cell in line[1:-1].split("|")]
                rows.append(cells)
        
        if len(rows) < 2:
            return None
        
        # Первая строка - заголовки
        headers = rows[0]
        data_rows = rows[1:]
        
        df = pd.DataFrame(data_rows, columns=headers)
        return df
    
    except Exception as e:
        logger.warning(f"Ошибка при конвертации Markdown в DataFrame: {e}")
        return None


def _json_to_dataframe(data: Any) -> Optional[Any]:
    """Конвертирует JSON данные в pandas DataFrame."""
    try:
        import pandas as pd
        
        if isinstance(data, list) and len(data) > 0:
            # Если первый элемент - тоже список, значит это одна таблица
            if isinstance(data[0], list):
                if len(data) < 2:
                    return None
                headers = data[0]
                rows = data[1:]
                df = pd.DataFrame(rows, columns=headers)
                return df
            # Если первый элемент - словарь, значит это массив таблиц
            elif isinstance(data[0], dict):
                # Берем первую таблицу
                first_table = data[0]
                if "headers" in first_table and "rows" in first_table:
                    df = pd.DataFrame(first_table["rows"], columns=first_table["headers"])
                    return df
        
        return None
    
    except Exception as e:
        logger.warning(f"Ошибка при конвертации JSON в DataFrame: {e}")
        return None


def _dataframe_to_markdown(df: Any) -> Optional[str]:
    """Конвертирует pandas DataFrame в Markdown таблицу."""
    try:
        if df is None:
            return None
        
        markdown_lines = []
        
        # Заголовки
        headers = list(df.columns)
        header_line = "| " + " | ".join(str(h) for h in headers) + " |"
        markdown_lines.append(header_line)
        
        # Разделитель
        separator = "| " + " | ".join(["---"] * len(headers)) + " |"
        markdown_lines.append(separator)
        
        # Данные
        for _, row in df.iterrows():
            row_line = "| " + " | ".join(str(val) for val in row.values) + " |"
            markdown_lines.append(row_line)
        
        return "\n".join(markdown_lines)
    
    except Exception as e:
        logger.warning(f"Ошибка при конвертации DataFrame в Markdown: {e}")
        return None


def detect_merged_tables(markdown: str) -> List[str]:
    """
    Определяет, содержит ли Markdown несколько склеенных таблиц.
    
    Args:
        markdown: Markdown таблица
    
    Returns:
        Список отдельных таблиц (если найдены) или список с одной таблицей
    """
    lines = [line.strip() for line in markdown.split("\n") if line.strip()]
    
    if len(lines) < 3:
        return [markdown]
    
    # Ищем повторяющиеся заголовки (признак склеенных таблиц)
    tables: List[List[str]] = []
    current_table: List[str] = []
    
    for i, line in enumerate(lines):
        if line.startswith("|") and line.endswith("|"):
            # Проверяем, является ли это заголовком (следующая строка - разделитель)
            if i + 1 < len(lines) and re.match(r'^\|[\s\-\|:]+\|$', lines[i + 1]):
                # Если уже есть таблица и текущая строка похожа на заголовок предыдущей
                if current_table and len(current_table) > 2:
                    # Проверяем, похож ли заголовок
                    prev_header = current_table[0]
                    if line == prev_header:
                        # Начинаем новую таблицу
                        tables.append(current_table)
                        current_table = [line]
                        continue
                
                current_table.append(line)
            else:
                current_table.append(line)
        else:
            # Пустая строка или не таблица - возможный разделитель
            if current_table and len(current_table) > 2:
                tables.append(current_table)
                current_table = []
    
    if current_table:
        tables.append(current_table)
    
    # Если найдено несколько таблиц, возвращаем их
    if len(tables) > 1:
        return ["\n".join(table) for table in tables]
    
    return [markdown]

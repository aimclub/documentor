"""
Table parsing via Qwen2.5 API.

Contains functions for:
- Calling Qwen API to parse tables from images
- Parsing response to Markdown or DataFrame
- Processing merged tables
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openai
import yaml
from PIL import Image

logger = logging.getLogger(__name__)

# Cache for OCR config
_ocr_config_cache: Optional[dict] = None


def _load_ocr_config() -> dict:
    """Loads OCR configuration from ocr_config.yaml."""
    global _ocr_config_cache
    if _ocr_config_cache is not None:
        return _ocr_config_cache
    
    config_path = Path(__file__).parent.parent.parent.parent.parent / "config" / "ocr_config.yaml"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                _ocr_config_cache = config or {}
                return _ocr_config_cache
        except Exception as e:
            logger.warning(f"Failed to load OCR config from {config_path}: {e}")
            _ocr_config_cache = {}
            return _ocr_config_cache
    else:
        _ocr_config_cache = {}
        return _ocr_config_cache


def _get_config_value(key_path: str, env_var: Optional[str] = None, default: Optional[Any] = None) -> Any:
    """
    Gets configuration value with priority: config file → env var → default.
    
    Args:
        key_path: Dot-separated path in config (e.g., "qwen_ocr.recognition.timeout")
        env_var: Environment variable name (optional)
        default: Default value if not found
    
    Returns:
        Configuration value
    """
    config = _load_ocr_config()
    
    # Try config file first
    keys = key_path.split(".")
    value = config
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            value = None
            break
        if value is None:
            break
    
    if value is not None:
        return value
    
    # Fallback to environment variable
    if env_var:
        env_value = os.getenv(env_var)
        if env_value is not None:
            try:
                # Try to convert to appropriate type
                if isinstance(default, int):
                    return int(env_value)
                elif isinstance(default, float):
                    return float(env_value)
                elif isinstance(default, bool):
                    return env_value.lower() in ("true", "1", "yes", "on")
                return env_value
            except (ValueError, TypeError):
                logger.warning(f"Failed to convert env var {env_var}={env_value} to {type(default).__name__}")
    
    # Return default
    return default


def _image_to_base64(image: Image.Image) -> str:
    """Converts PIL Image to base64 data URL."""
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
    Parses table from image via Qwen2.5 API.
    
    Args:
        table_image: Table image
        method: Parsing method ("markdown" or "dataframe")
        base_url: API base URL (default from env)
        api_key: API key (default from env)
        temperature: Generation temperature (default from env)
        max_tokens: Maximum number of tokens (default from env)
        model_name: Model name (default from env)
        timeout: Request timeout in seconds (default from env)
    
    Returns:
        tuple[str, Any, bool]:
            - markdown_content: Markdown table or None
            - dataframe: pandas DataFrame or None
            - success: Operation success status
    """
    if base_url is None:
        base_url_raw = os.getenv("QWEN_BASE_URL")
        if base_url_raw:
            # Process multiple URLs (via comma or newline)
            # Take the first valid URL
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
    # Secret parameters: only from env
    if api_key is None:
        api_key = os.getenv("QWEN_API_KEY")
    
    # Non-secret parameters: from config → env → default
    if temperature is None:
        temperature = _get_config_value(
            "qwen_ocr.recognition.temperature",
            "QWEN_TEMPERATURE",
            0.1
        )
    if max_tokens is None:
        max_tokens = _get_config_value(
            "qwen_ocr.recognition.max_tokens",
            "QWEN_MAX_TOKENS",
            4096
        )
    if model_name is None:
        model_name = _get_config_value(
            "qwen_ocr.model",
            "QWEN_MODEL_NAME",
            None
        )
    if timeout is None:
        timeout = _get_config_value(
            "qwen_ocr.recognition.timeout",
            "QWEN_TIMEOUT",
            180
        )
    
    if not base_url or not api_key:
        logger.error("QWEN_BASE_URL or QWEN_API_KEY not configured")
        return None, None, False
    
    if not model_name:
        logger.error("QWEN_MODEL_NAME is not set (neither in config nor in env)")
        return None, None, False
    
    # Prompt for table parsing
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
    
    # Form messages with System and User roles
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
            logger.warning("Empty response from Qwen for table parsing")
            return None, None, False
        
        # Check if there are no tables
        if "<!-- NO_TABLE -->" in content:
            logger.info("Qwen reported that there are no tables in the image")
            return None, None, False
        
        # Parse response
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
                logger.error(f"Error parsing JSON from Qwen: {e}")
                return None, None, False
    
    except Exception as e:
        logger.error(f"Error calling Qwen API for table parsing: {e}")
        return None, None, False


def markdown_to_dataframe(markdown: str) -> Optional[Any]:
    """Converts Markdown table to pandas DataFrame."""
    try:
        import pandas as pd
        
        lines = [line.strip() for line in markdown.split("\n") if line.strip()]
        if not lines:
            return None
        
        # Remove separator (second line with |---|---|)
        filtered_lines = []
        for i, line in enumerate(lines):
            if i == 0 or not re.match(r'^\|[\s\-\|:]+\|$', line):
                filtered_lines.append(line)
        
        # Parse rows
        rows = []
        for line in filtered_lines:
            if line.startswith("|") and line.endswith("|"):
                cells = [cell.strip() for cell in line[1:-1].split("|")]
                rows.append(cells)
        
        if len(rows) < 2:
            return None
        
        # First row is headers
        headers = rows[0]
        data_rows = rows[1:]
        
        df = pd.DataFrame(data_rows, columns=headers)
        return df
    
    except Exception as e:
        logger.warning(f"Error converting Markdown to DataFrame: {e}")
        return None


def _json_to_dataframe(data: Any) -> Optional[Any]:
    """Converts JSON data to pandas DataFrame."""
    try:
        import pandas as pd
        
        if isinstance(data, list) and len(data) > 0:
            # If first element is also a list, it's a single table
            if isinstance(data[0], list):
                if len(data) < 2:
                    return None
                headers = data[0]
                rows = data[1:]
                df = pd.DataFrame(rows, columns=headers)
                return df
            # If first element is a dict, it's an array of tables
            elif isinstance(data[0], dict):
                # Take first table
                first_table = data[0]
                if "headers" in first_table and "rows" in first_table:
                    df = pd.DataFrame(first_table["rows"], columns=first_table["headers"])
                    return df
        
        return None
    
    except Exception as e:
        logger.warning(f"Error converting JSON to DataFrame: {e}")
        return None


def _dataframe_to_markdown(df: Any) -> Optional[str]:
    """Converts pandas DataFrame to Markdown table."""
    try:
        if df is None:
            return None
        
        markdown_lines = []
        
        # Headers
        headers = list(df.columns)
        header_line = "| " + " | ".join(str(h) for h in headers) + " |"
        markdown_lines.append(header_line)
        
        # Separator
        separator = "| " + " | ".join(["---"] * len(headers)) + " |"
        markdown_lines.append(separator)
        
        # Data
        for _, row in df.iterrows():
            row_line = "| " + " | ".join(str(val) for val in row.values) + " |"
            markdown_lines.append(row_line)
        
        return "\n".join(markdown_lines)
    
    except Exception as e:
        logger.warning(f"Error converting DataFrame to Markdown: {e}")
        return None


def detect_merged_tables(markdown: str) -> List[str]:
    """
    Determines if Markdown contains multiple merged tables.
    
    Args:
        markdown: Markdown table
    
    Returns:
        List of separate tables (if found) or list with one table
    """
    lines = [line.strip() for line in markdown.split("\n") if line.strip()]
    
    if len(lines) < 3:
        return [markdown]
    
    # Look for repeating headers (sign of merged tables)
    tables: List[List[str]] = []
    current_table: List[str] = []
    
    for i, line in enumerate(lines):
        if line.startswith("|") and line.endswith("|"):
            # Check if this is a header (next line is separator)
            if i + 1 < len(lines) and re.match(r'^\|[\s\-\|:]+\|$', lines[i + 1]):
                # If table already exists and current line is similar to previous header
                if current_table and len(current_table) > 2:
                    # Check if header is similar
                    prev_header = current_table[0]
                    if line == prev_header:
                        # Start new table
                        tables.append(current_table)
                        current_table = [line]
                        continue
                
                current_table.append(line)
            else:
                current_table.append(line)
        else:
            # Empty line or not a table - possible separator
            if current_table and len(current_table) > 2:
                tables.append(current_table)
                current_table = []
    
    if current_table:
        tables.append(current_table)
    
    # If multiple tables found, return them
    if len(tables) > 1:
        return ["\n".join(table) for table in tables]
    
    return [markdown]

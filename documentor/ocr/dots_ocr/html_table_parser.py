"""
HTML table parsing from Dots.OCR.

Dots.OCR returns tables in HTML format according to prompt_layout_all_en.
This module validates HTML tables from Dots OCR.
Tables are stored as HTML strings in element.content.

This module is specific to Dots.OCR HTML format.
For other OCR models, create similar parsers in their respective modules.
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
) -> Tuple[Optional[str], bool]:
    """
    Parse HTML table from Dots OCR and return HTML.
    
    Args:
        html_content: HTML string with table (may contain one or more tables)
    
    Returns:
        tuple[str, bool]:
            - html_content: HTML string or None
            - success: Operation success status
    """
    if not html_content or not html_content.strip():
        logger.warning("Empty HTML content provided")
        return None, False
    
    if not HAS_BS4:
        logger.error("beautifulsoup4 is required for HTML table parsing")
        return None, False
    
    try:
        # Parse HTML to validate it's a valid table
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all tables
        tables = soup.find_all('table')
        
        if not tables:
            logger.warning("No tables found in HTML content")
            return None, False
        
        # Return the HTML as-is (validated)
        return html_content, True
        
    except Exception as e:
        logger.error(f"Error parsing HTML table: {e}")
        return None, None, False


# NOTE: Function no longer used as markdown parsing is disabled
def _dataframe_to_markdown(rows: list, df: Optional[pd.DataFrame] = None) -> str:
    """
    Convert table to markdown format.
    
    Args:
        rows: List of table rows
        df: DataFrame (optional, for using built-in method)
    
    Returns:
        Markdown string with table
    """
    if df is not None and HAS_PANDAS:
        try:
            # Use built-in DataFrame method
            return df.to_markdown(index=False)
        except Exception:
            # Fallback to manual conversion
            pass
    
    # Manual conversion to markdown
    if not rows:
        return ""
    
    # Determine number of columns
    max_cols = max(len(row) for row in rows) if rows else 0
    
    # Normalize rows (add empty cells if needed)
    normalized_rows = []
    for row in rows:
        normalized_row = list(row) + [''] * (max_cols - len(row))
        normalized_rows.append(normalized_row[:max_cols])
    
    if not normalized_rows:
        return ""
    
    # Create markdown table
    markdown_lines = []
    
    # Header (first row)
    header = normalized_rows[0]
    markdown_lines.append("| " + " | ".join(str(cell) for cell in header) + " |")
    
    # Separator
    markdown_lines.append("| " + " | ".join("---" for _ in header) + " |")
    
    # Data
    for row in normalized_rows[1:]:
        markdown_lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    
    return "\n".join(markdown_lines)


def detect_merged_tables(markdown_content: str) -> list[str]:
    """
    Detect multiple tables in markdown content.
    
    Args:
        markdown_content: Markdown string, possibly containing multiple tables
    
    Returns:
        List of separate tables in markdown format
    """
    if not markdown_content:
        return []
    
    # Split by double line breaks (empty lines between tables)
    parts = markdown_content.split('\n\n')
    
    tables = []
    current_table = []
    
    for part in parts:
        lines = part.strip().split('\n')
        # Check if this is a table (contains |)
        if any('|' in line for line in lines):
            if current_table:
                # Save previous table
                tables.append('\n'.join(current_table))
                current_table = []
            # Add lines of current table
            current_table.extend(lines)
        else:
            if current_table:
                # Add to current table
                current_table.extend(lines)
    
    # Add last table
    if current_table:
        tables.append('\n'.join(current_table))
    
    # If no separation found, return as single table
    if not tables:
        tables = [markdown_content]
    
    return tables


def markdown_to_dataframe(markdown_content: str) -> Optional[pd.DataFrame]:
    """
    Convert markdown table to pandas DataFrame.
    
    Args:
        markdown_content: Markdown string with table
    
    Returns:
        pandas DataFrame or None on error
    """
    if not HAS_PANDAS:
        logger.warning("pandas not available, cannot convert markdown to DataFrame")
        return None
    
    if not markdown_content or not markdown_content.strip():
        return None
    
    try:
        # Use StringIO to read markdown
        from io import StringIO
        df = pd.read_csv(StringIO(markdown_content), sep='|', skipinitialspace=True)
        
        # Remove empty columns (which may appear due to | separators)
        df = df.dropna(axis=1, how='all')
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        
        return df
    except Exception as e:
        logger.warning(f"Error converting markdown to DataFrame: {e}")
        return None

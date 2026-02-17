"""
HTML table parsing from Dots OCR to markdown and pandas DataFrame.

Dots OCR returns tables in HTML format according to prompt_layout_all_en.
This module converts HTML to markdown and DataFrame for use in the parser.
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
    Parse HTML table from Dots OCR to markdown or DataFrame.
    
    Args:
        html_content: HTML string with table (may contain one or more tables)
        method: Parsing method ("markdown" or "dataframe")
    
    Returns:
        tuple[str, Any, bool]:
            - markdown_content: Markdown table or None
            - dataframe: pandas DataFrame or None
            - success: Operation success status
    """
    if not html_content or not html_content.strip():
        logger.warning("Empty HTML content provided")
        return None, None, False
    
    if not HAS_BS4:
        logger.error("beautifulsoup4 is required for HTML table parsing")
        return None, None, False
    
    try:
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all tables
        tables = soup.find_all('table')
        
        if not tables:
            logger.warning("No tables found in HTML content")
            return None, None, False
        
        # Take first table (if multiple, logic can be extended)
        table = tables[0]
        
        # Parse table into list of rows
        rows = []
        for tr in table.find_all('tr'):
            cells = []
            for td in tr.find_all(['td', 'th']):
                # Extract text, preserving structure
                cell_text = td.get_text(separator=' ', strip=True)
                # Handle merged cells (rowspan/colspan)
                rowspan = int(td.get('rowspan', 1))
                colspan = int(td.get('colspan', 1))
                
                # For simplicity, ignore rowspan/colspan for now
                # More complex logic can be added in the future
                cells.append(cell_text)
            
            if cells:  # Ignore empty rows
                rows.append(cells)
        
        if not rows:
            logger.warning("Table has no rows")
            return None, None, False
        
        # Create DataFrame
        if HAS_PANDAS:
            # Determine if there is a header
            # Check if first row has th or all rows have same number of columns
            has_header = False
            if rows:
                # Check first row for th
                first_row_has_th = any(td.name == 'th' for tr in table.find_all('tr', limit=1) for td in tr.find_all(['td', 'th']))
                
                # If first row has th or if there are more than 1 rows and first row looks like header
                if first_row_has_th or (len(rows) > 1 and len(rows[0]) > 0):
                    # Check if first row differs from others (usually header is shorter or has different format)
                    if len(rows) > 1:
                        # If first row has fewer columns or all rows have same number
                        if len(rows[0]) <= max(len(row) for row in rows[1:]) if rows[1:] else len(rows[0]):
                            has_header = True
                    else:
                        has_header = first_row_has_th
            
            try:
                if has_header and len(rows) > 1:
                    # Use first row as header
                    # Normalize number of columns
                    max_cols = max(len(row) for row in rows)
                    header = list(rows[0]) + [''] * (max_cols - len(rows[0]))
                    data_rows = []
                    for row in rows[1:]:
                        normalized_row = list(row) + [''] * (max_cols - len(row))
                        data_rows.append(normalized_row[:max_cols])
                    df = pd.DataFrame(data_rows, columns=header[:max_cols])
                else:
                    # No header, use all rows as data
                    max_cols = max(len(row) for row in rows) if rows else 0
                    normalized_rows = []
                    for row in rows:
                        normalized_row = list(row) + [''] * (max_cols - len(row))
                        normalized_rows.append(normalized_row[:max_cols])
                    df = pd.DataFrame(normalized_rows)
            except Exception as e:
                logger.warning(f"Error creating DataFrame: {e}, trying without header")
                # Fallback: create DataFrame without header
                max_cols = max(len(row) for row in rows) if rows else 0
                normalized_rows = []
                for row in rows:
                    normalized_row = list(row) + [''] * (max_cols - len(row))
                    normalized_rows.append(normalized_row[:max_cols])
                df = pd.DataFrame(normalized_rows)
        else:
            df = None
        
        # Convert to markdown
        # NOTE: Only DataFrame is used
        # if method == "markdown" or method == "both":
        #     markdown = _dataframe_to_markdown(rows, df if HAS_PANDAS else None)
        # else:
        #     markdown = None
        markdown = None
        
        return markdown, df, True
        
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

"""
Utility for merging split tables across pages.

Handles detection and merging of tables that are broken across multiple pages
in both DOCX and PDF documents.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def compare_table_structures(
    table1_data: List[List[str]],
    table2_data: List[List[str]],
    similarity_threshold: float = 0.7
) -> float:
    """
    Compares two table structures by comparing their headers and column counts.
    
    Args:
        table1_data: First table data (list of rows, each row is list of cells)
        table2_data: Second table data (list of rows, each row is list of cells)
        similarity_threshold: Minimum similarity to consider tables as matching
    
    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not table1_data or not table2_data:
        return 0.0
    
    # Compare column counts
    cols1 = max(len(row) for row in table1_data) if table1_data else 0
    cols2 = max(len(row) for row in table2_data) if table2_data else 0
    
    if cols1 != cols2:
        return 0.0
    
    if cols1 == 0:
        return 0.0
    
    # Compare headers (first row)
    header1 = table1_data[0] if table1_data else []
    header2 = table2_data[0] if table2_data else []
    
    if len(header1) != len(header2):
        return 0.0
    
    # Normalize headers for comparison
    matches = 0
    total = len(header1)
    
    for h1, h2 in zip(header1, header2):
        h1_clean = h1.strip().lower() if h1 else ""
        h2_clean = h2.strip().lower() if h2 else ""
        
        if h1_clean == h2_clean:
            matches += 1
        elif h1_clean and h2_clean:
            # Check if one is substring of another (for partial matches)
            if h1_clean in h2_clean or h2_clean in h1_clean:
                matches += 0.5
    
    similarity = matches / total if total > 0 else 0.0
    return similarity


def extract_table_data_from_html(html_content: str) -> Optional[List[List[str]]]:
    """
    Extracts table data from HTML content.
    
    Args:
        html_content: HTML string containing table
    
    Returns:
        List of rows, each row is list of cell texts, or None if parsing fails
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        table = soup.find('table')
        
        if not table:
            return None
        
        rows = []
        for tr in table.find_all('tr'):
            cells = []
            for td in tr.find_all(['td', 'th']):
                cell_text = td.get_text(separator=' ', strip=True)
                cells.append(cell_text)
            
            if cells:
                rows.append(cells)
        
        return rows if rows else None
    except Exception as e:
        logger.debug(f"Error extracting table data from HTML: {e}")
        return None


def merge_table_html(html1: str, html2: str) -> Optional[str]:
    """
    Merges two HTML tables into one.
    
    Args:
        html1: First table HTML
        html2: Second table HTML
    
    Returns:
        Merged HTML table or None if merging fails
    """
    try:
        soup1 = BeautifulSoup(html1, 'html.parser')
        soup2 = BeautifulSoup(html2, 'html.parser')
        
        table1 = soup1.find('table')
        table2 = soup2.find('table')
        
        if not table1 or not table2:
            return None
        
        # Get all rows from second table (skip header if it's the same)
        rows2 = table2.find_all('tr')
        
        # Check if first row of table2 matches first row of table1 (header)
        if rows2:
            header1_cells = [td.get_text(strip=True).lower() for td in table1.find('tr').find_all(['td', 'th'])]
            header2_cells = [td.get_text(strip=True).lower() for td in rows2[0].find_all(['td', 'th'])]
            
            # If headers match, skip header row from table2
            start_idx = 1 if header1_cells == header2_cells else 0
        else:
            start_idx = 0
        
        # Append rows from table2 to table1
        for row in rows2[start_idx:]:
            table1.append(row)
        
        return str(soup1)
    except Exception as e:
        logger.debug(f"Error merging HTML tables: {e}")
        return None


def merge_docx_tables(
    docx_tables: List[Dict[str, Any]],
    all_xml_elements: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Merges split DOCX tables that are broken across pages.
    
    Strategy:
    1. Find tables that end near the end of a page
    2. Find tables that start near the beginning of the next page
    3. Compare their structures (column count, headers)
    4. Merge if structures match
    
    Args:
        docx_tables: List of table dictionaries from XML parser
        all_xml_elements: All XML elements for context
    
    Returns:
        List of merged tables
    """
    if len(docx_tables) < 2:
        return docx_tables
    
    # Sort tables by XML position
    sorted_tables = sorted(docx_tables, key=lambda t: t.get('xml_position', 0))
    
    merged_tables = []
    i = 0
    
    while i < len(sorted_tables):
        current_table = sorted_tables[i]
        merged = False
        
        # Check if we can merge with next table
        if i + 1 < len(sorted_tables):
            next_table = sorted_tables[i + 1]
            
            # Get table positions
            current_pos = current_table.get('xml_position', 0)
            next_pos = next_table.get('xml_position', 0)
            
            # Check if tables are close in XML position (within reasonable range)
            # This indicates they might be on consecutive pages
            position_gap = next_pos - current_pos
            
            # Check if there are other table elements between them
            has_other_tables_between = False
            for elem in all_xml_elements:
                elem_pos = elem.get('xml_position', 0)
                elem_type = elem.get('type')
                if current_pos < elem_pos < next_pos and elem_type == 'table':
                    has_other_tables_between = True
                    break
            
            # If tables are close and no other tables between, check structure
            if not has_other_tables_between and position_gap < 100:
                # Compare table structures
                table1_data = current_table.get('data', [])
                table2_data = next_table.get('data', [])
                
                if table1_data and table2_data:
                    similarity = compare_table_structures(table1_data, table2_data)
                    
                    if similarity >= 0.7:
                        # Merge tables
                        logger.debug(
                            f"Merging DOCX tables at positions {current_pos} and {next_pos} "
                            f"(similarity: {similarity:.2f})"
                        )
                        
                        # Merge data
                        merged_data = table1_data.copy()
                        
                        # Check if headers match - if so, skip header row from table2
                        if len(table1_data) > 0 and len(table2_data) > 0:
                            header1 = [cell.strip().lower() for cell in table1_data[0]]
                            header2 = [cell.strip().lower() for cell in table2_data[0]]
                            
                            if header1 == header2:
                                # Skip header row
                                merged_data.extend(table2_data[1:])
                            else:
                                # Include all rows
                                merged_data.extend(table2_data)
                        else:
                            merged_data.extend(table2_data)
                        
                        # Create merged table
                        merged_table = current_table.copy()
                        merged_table['data'] = merged_data
                        merged_table['rows_count'] = len(merged_data)
                        merged_table['merged_with'] = next_table.get('xml_position')
                        merged_table['is_merged'] = True
                        
                        merged_tables.append(merged_table)
                        i += 2  # Skip both tables
                        merged = True
        
        if not merged:
            merged_tables.append(current_table)
            i += 1
    
    logger.info(f"Merged DOCX tables: {len(docx_tables)} -> {len(merged_tables)}")
    return merged_tables


def merge_pdf_tables(
    elements: List[Any],
    page_height: Optional[float] = None,
    end_threshold: float = 0.9,
    start_threshold: float = 0.1
) -> List[Any]:
    """
    Merges split PDF tables that are broken across pages.
    
    Strategy:
    1. Find tables that end near the bottom of a page
    2. Find tables that start near the top of the next page
    3. Compare their structures (column count, headers from HTML)
    4. Merge if structures match
    
    Args:
        elements: List of Element objects
        page_height: Height of PDF page (for determining if table is at end/start)
        end_threshold: Threshold for considering table at end of page (0.0-1.0)
        start_threshold: Threshold for considering table at start of page (0.0-1.0)
    
    Returns:
        List of elements with merged tables
    """
    from ..domain import Element, ElementType
    
    # Filter table elements
    table_elements = [(i, e) for i, e in enumerate(elements) if e.type == ElementType.TABLE]
    
    if len(table_elements) < 2:
        return elements
    
    # Sort by page number and Y coordinate
    sorted_tables = sorted(
        table_elements,
        key=lambda x: (
            x[1].metadata.get('page_num', 0),
            x[1].metadata.get('bbox', [0, 0, 0, 0])[1] if len(x[1].metadata.get('bbox', [])) >= 2 else 0
        )
    )
    
    merged_indices = set()
    
    # Process tables sequentially, merging consecutive matching tables
    idx = 0
    while idx < len(sorted_tables) - 1:
        if idx in merged_indices:
            idx += 1
            continue
        
        i1, table1_elem = sorted_tables[idx]
        # Get actual element from elements list to update it
        table1 = elements[i1]
        
        merged_pages = [table1.metadata.get('page_num', 0)]
        merged_html = table1.content or ""
        merged_count = 0
        
        # Try to merge with following tables
        next_idx = idx + 1
        while next_idx < len(sorted_tables):
            if next_idx in merged_indices:
                next_idx += 1
                continue
            
            i2, table2_elem = sorted_tables[next_idx]
            table2 = elements[i2]
            
            # Get page numbers and bboxes
            page1 = merged_pages[-1]  # Last page of current merged table
            page2 = table2.metadata.get('page_num', 0)
            
            bbox1 = table1.metadata.get('bbox', [])
            bbox2 = table2.metadata.get('bbox', [])
            
            if len(bbox1) < 4 or len(bbox2) < 4:
                break
            
            # Check if tables are on consecutive pages or close (within 2 pages)
            page_gap = page2 - page1
            if page_gap > 2:
                # Too far apart, stop merging
                break
            
            # Check if there are other tables between them
            has_other_tables_between = False
            if page_gap > 1:
                # Check elements between i1 and i2 for other tables
                for j in range(i1 + 1, i2):
                    if j < len(elements) and elements[j].type == ElementType.TABLE:
                        has_other_tables_between = True
                        break
            
            if has_other_tables_between:
                break
            
            # Check if table1 ends near bottom of page (for first merge) or table2 is on next page
            should_check_position = (page_gap == 1)
            is_at_end = True
            is_at_start = True
            
            if should_check_position and page_height is not None:
                y1_end = bbox1[3]  # Bottom Y coordinate
                y2_start = bbox2[1]  # Top Y coordinate
                
                normalized_y_end = y1_end / page_height if page_height > 0 else 0
                normalized_y_start = y2_start / page_height if page_height > 0 else 0
                
                is_at_end = normalized_y_end >= end_threshold
                is_at_start = normalized_y_start <= start_threshold
            
            # If tables are on consecutive pages or close, check structure
            if page_gap <= 2 and (not should_check_position or (is_at_end and is_at_start)):
                # Extract table data from HTML
                html2 = table2.content or ""
                
                if html2:
                    data1 = extract_table_data_from_html(merged_html)
                    data2 = extract_table_data_from_html(html2)
                    
                    if data1 and data2:
                        similarity = compare_table_structures(data1, data2)
                        
                        if similarity >= 0.7:
                            # Merge tables
                            logger.debug(
                                f"Merging PDF tables: page {page1 + 1} with page {page2 + 1} "
                                f"(similarity: {similarity:.2f})"
                            )
                            
                            # Merge HTML
                            new_merged_html = merge_table_html(merged_html, html2)
                            
                            if new_merged_html:
                                merged_html = new_merged_html
                                merged_pages.append(page2)
                                merged_count += 1
                                
                                # Mark this table for removal
                                merged_indices.add(next_idx)
                                next_idx += 1
                                continue
            
            # No match, stop merging
            break
        
        # Update first table if we merged any
        if merged_count > 0:
            table1.content = merged_html
            table1.metadata['is_merged'] = True
            table1.metadata['merged_pages'] = merged_pages
            table1.metadata['merged_count'] = merged_count
            logger.debug(f"Merged {merged_count + 1} table parts across pages {merged_pages}")
        
        idx += 1
    
    # Remove merged tables (second table in each merged pair)
    result_elements = []
    merged_table_indices = set()
    for j in merged_indices:
        if j < len(sorted_tables):
            # Get the index of the second table in the merged pair
            _, second_table = sorted_tables[j]
            # Find index of this table in original elements list
            for i, elem in enumerate(elements):
                if elem.id == second_table.id:
                    merged_table_indices.add(i)
                    break
    
    # Build result list, skipping merged tables
    for i, elem in enumerate(elements):
        if i not in merged_table_indices:
            result_elements.append(elem)
    
    logger.info(f"Merged PDF tables: {len(table_elements)} -> {len([e for e in result_elements if e.type == ElementType.TABLE])}")
    return result_elements

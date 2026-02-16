"""
Building document hierarchy from XML elements.
"""

from __future__ import annotations

import base64
import json
import re
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import pandas as pd
from PIL import Image

from ....domain import Element, ElementType
from .header_finder import extract_paragraph_properties


def _table_data_to_dataframe(table_data: Dict[str, Any]) -> Optional[pd.DataFrame]:
    """
    Converts table data from XML format to pandas DataFrame.
    
    Args:
        table_data: Dictionary with table data from XML parser
        
    Returns:
        pandas.DataFrame or None if DataFrame creation failed
    """
    try:
        data = table_data.get('data', [])
        if not data:
            return None
        
        # Determine maximum number of columns
        max_cols = max(len(row) for row in data) if data else 0
        if max_cols == 0:
            return None
        
        # Normalize all rows to same number of columns
        normalized_rows = []
        for row in data:
            # Pad with empty strings if columns are fewer
            normalized_row = list(row)
            while len(normalized_row) < max_cols:
                normalized_row.append("")
            # Truncate if columns are more
            normalized_rows.append(normalized_row[:max_cols])
        
        # Determine if first row is header
        # Heuristic: if first row contains short non-empty values
        # and there is at least one data row, use first row as headers
        first_row = normalized_rows[0] if normalized_rows else []
        use_first_row_as_header = False
        
        if len(normalized_rows) > 1 and first_row:
            # Check if first row looks like headers
            non_empty_cells = [cell.strip() for cell in first_row if cell.strip()]
            if non_empty_cells:
                # If majority of cells are non-empty and short, consider as headers
                avg_length = sum(len(cell) for cell in non_empty_cells) / len(non_empty_cells) if non_empty_cells else 0
                non_empty_ratio = len(non_empty_cells) / len(first_row) if first_row else 0
                
                # Headers are usually: short (avg length < 50), majority of cells filled (> 50%)
                use_first_row_as_header = (
                    avg_length < 50 and
                    non_empty_ratio > 0.5
                )
        
        if use_first_row_as_header:
            # First row is headers
            headers = []
            for i, cell in enumerate(first_row):
                cell_text = cell.strip() if cell else ""
                if cell_text:
                    headers.append(cell_text)
                else:
                    headers.append(f"Column_{i+1}")
            data_rows = normalized_rows[1:]
        else:
            # Use standard column names
            headers = [f"Column_{i+1}" for i in range(max_cols)]
            data_rows = normalized_rows
        
        # Create DataFrame
        df = pd.DataFrame(data_rows, columns=headers)
        
        return df
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Error converting table to DataFrame: {e}")
        return None


def _is_table_caption(text: str) -> bool:
    """Checks if text is a table caption."""
    text_stripped = text.strip()
    if text_stripped.endswith(':'):
        return False
    
    text_lower = text_stripped.lower()
    patterns = [
        r'^таблица\s+\d+',
        r'^table\s+\d+',
        r'^табл\.\s*\d+',
        r'^tbl\.\s*\d+',
    ]
    return any(re.search(pattern, text_lower) for pattern in patterns)


def _is_image_caption(text: str) -> bool:
    """Checks if text is an image caption."""
    text_stripped = text.strip()
    if text_stripped.endswith(':'):
        return False
    
    text_lower = text_stripped.lower()
    patterns = [
        r'^рис\.\s*\d+',
        r'^рисунок\s+\d+',
        r'^figure\s+\d+',
        r'^fig\.\s*\d+',
        r'^изображение\s+\d+',
    ]
    return any(re.search(pattern, text_lower) for pattern in patterns)


def _is_structural_keyword(text: str) -> bool:
    """Checks if text is a structural keyword."""
    text_stripped = text.strip().lower()
    structural_keywords = [
        'введение', 'заключение', 'список литературы',
        'список использованных источников', 'библиографический список',
        'литература', 'приложение', 'приложения', 'содержание', 'оглавление',
        'термины и определения', 'перечень сокращений и обозначений',
        'аннотация', 'реферат', 'abstract', 'referat',
        'introduction', 'conclusion', 'references', 'bibliography',
        'appendix', 'appendices', 'contents', 'table of contents'
    ]
    return text_stripped in structural_keywords


def _determine_header_level(
    text: str,
    properties: Dict[str, Any],
    header_data: Optional[Dict[str, Any]] = None,
    header_stack: List[Tuple[int, str, bool]] = None
) -> int:
    """Determines header level."""
    if header_stack is None:
        header_stack = []
    
    if _is_structural_keyword(text):
        return 1
    
    text_lower = text.strip().lower()
    chapter_patterns = [
        r'^глава\s+\d+', r'^часть\s+\d+', r'^раздел\s+\d+',
        r'^chapter\s+\d+', r'^part\s+\d+', r'^section\s+\d+',
    ]
    for pattern in chapter_patterns:
        if re.match(pattern, text_lower):
            return 1
    
    numbered_match = re.match(r'^(\d+)(?:\s|\.|$)', text.strip())
    if numbered_match:
        full_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text.strip())
        if full_match:
            if not full_match.group(2) and not full_match.group(3):
                return 1
    
    style = properties.get('style')
    if style and style.isdigit():
        return int(style)
    
    if properties.get('is_heading_style') and properties.get('level'):
        return properties['level']
    
    numbered_level = None
    match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text.strip())
    if match:
        if match.group(3):
            numbered_level = 3
        elif match.group(2):
            numbered_level = 2
        elif match.group(1):
            numbered_level = 1
    
    if numbered_level == 1:
        return 1
    
    if numbered_level is not None:
        return numbered_level
    
    if header_data and header_data.get('level') is not None:
        lvl = header_data.get('level')
        if isinstance(lvl, str):
            try:
                lvl = int(lvl)
            except Exception:
                lvl = None
        if lvl and lvl != 'unknown':
            return lvl
    
    if header_stack:
        is_current_numbered = bool(re.match(r'^\d+', text.strip()))
        if not is_current_numbered:
            for stack_level, _, stack_is_numbered in reversed(header_stack):
                if stack_is_numbered:
                    return min(stack_level + 1, 6)
            return header_stack[-1][0]
        else:
            last_level = header_stack[-1][0]
            return min(last_level + 1, 6)
    
    return 1


def build_hierarchy(
    all_headers: List[Dict[str, Any]],
    all_xml_elements: List[Dict[str, Any]],
    docx_tables: List[Dict[str, Any]],
    docx_images: List[Dict[str, Any]],
    docx_path: Path,
    id_generator,
    max_text_block_size: int = 3000,
    max_paragraphs_per_block: int = 10
) -> List[Element]:
    """
    Builds complete document hierarchy from XML elements.
    
    Args:
        all_headers: List of found headers
        all_xml_elements: All XML elements
        docx_tables: List of tables
        docx_images: List of images
        docx_path: Path to DOCX file
        id_generator: ID generator for elements
        
    Returns:
        List of elements with hierarchy
    """
    elements: List[Element] = []
    header_stack: List[Tuple[int, str, bool]] = []
    
    header_by_pos = {}
    for h in all_headers:
        pos = h.get('xml_position')
        if pos is not None:
            header_by_pos[pos] = h
    
    tables_by_position = {t.get('xml_position'): t for t in docx_tables}
    images_by_position = {img.get('xml_position'): img for img in docx_images}
    
    properties_cache = {}
    
    def get_properties(pos):
        if pos not in properties_cache:
            properties_cache[pos] = extract_paragraph_properties(docx_path, pos)
        return properties_cache[pos]
    
    current_text_block = []
    current_text_positions = []
    current_text_size = 0
    
    def flush_text_block():
        nonlocal current_text_block, current_text_positions, current_text_size
        if not current_text_block:
            return
        
        text_content = '\n\n'.join(current_text_block)
        if text_content.strip():
            # Collect links from all text positions
            all_links = []
            for pos in current_text_positions:
                if pos < len(all_xml_elements):
                    elem = all_xml_elements[pos]
                    elem_links = elem.get('links', [])
                    if elem_links:
                        all_links.extend(elem_links)
            
            # Remove duplicates
            all_links = list(set(all_links)) if all_links else []
            
            metadata = {
                'source': 'xml',
                'position': list(current_text_positions),
                'size': len(text_content)
            }
            
            # Add links to metadata if found
            if all_links:
                metadata['links'] = all_links
            
            text_element = Element(
                id=id_generator.next_id(),
                type=ElementType.TEXT,
                content=text_content,
                parent_id=header_stack[-1][1] if header_stack else None,
                metadata=metadata
            )
            elements.append(text_element)
        
        current_text_block = []
        current_text_positions = []
        current_text_size = 0
    
    def add_header_element(text: str, level: int, xml_pos: int, ocr_header: Optional[Dict] = None):
        nonlocal header_stack
        flush_text_block()
        
        header_type_map = {
            1: ElementType.HEADER_1, 2: ElementType.HEADER_2,
            3: ElementType.HEADER_3, 4: ElementType.HEADER_4,
            5: ElementType.HEADER_5, 6: ElementType.HEADER_6,
        }
        element_type = header_type_map.get(level, ElementType.HEADER_1)
        
        while header_stack and header_stack[-1][0] >= level:
            header_stack.pop()
        
        parent_id = header_stack[-1][1] if header_stack else None
        
        # Extract links from header element
        header_links = []
        if xml_pos < len(all_xml_elements):
            header_elem = all_xml_elements[xml_pos]
            header_links = header_elem.get('links', [])
        
        if ocr_header:
            source = 'ocr_then_xml'
            metadata = {
                'source': source,
                'position': xml_pos,
                'level': level,
                'bbox': ocr_header.get('bbox', []),
                'page_num': ocr_header.get('page_num', 0),
            }
        else:
            source = 'xml'
            metadata = {
                'source': source,
                'position': xml_pos,
                'level': level,
            }
        
        # Add links to metadata if found
        if header_links:
            metadata['links'] = list(set(header_links))  # Remove duplicates
        
        header_element = Element(
            id=id_generator.next_id(),
            type=element_type,
            content=text,
            parent_id=parent_id,
            metadata=metadata
        )
        elements.append(header_element)
        is_numbered = bool(re.match(r'^\d+', text.strip()))
        header_stack.append((level, header_element.id, is_numbered))
    
    for xml_elem in all_xml_elements:
        xml_pos = xml_elem.get('xml_position', 0)
        elem_type = xml_elem.get('type')
        
        if elem_type == 'table':
            flush_text_block()
            table_data = tables_by_position.get(xml_pos)
            if table_data:
                # Convert table to DataFrame
                dataframe = _table_data_to_dataframe(table_data)
                
                # Create metadata
                metadata = {
                    'source': 'xml',
                    'position': xml_pos,
                    'table_index': table_data.get('index', 0),
                    'rows_count': table_data.get('rows_count', 0),
                    'cols_count': table_data.get('cols_count', 0),
                }
                
                # Always add DataFrame to metadata (create empty if parsing failed)
                if dataframe is not None:
                    metadata['dataframe'] = dataframe
                else:
                    # Create empty DataFrame if parsing failed
                    metadata['dataframe'] = pd.DataFrame()
                
                elements.append(Element(
                    id=id_generator.next_id(),
                    type=ElementType.TABLE,
                    content=json.dumps(table_data, ensure_ascii=False, default=str, indent=2),
                    parent_id=header_stack[-1][1] if header_stack else None,
                    metadata=metadata
                ))
            continue
        
        if elem_type != 'paragraph':
            continue
        
        text = xml_elem.get('text', '').strip()
        text_raw = xml_elem.get('text', '')
        text_size = len(text_raw)
        has_image = xml_elem.get('has_image', False)
        
        if xml_pos in images_by_position:
            flush_text_block()
            image_data = images_by_position[xml_pos]
            image_path = image_data.get('image_path', '')
            image_bytes = image_data.get('image_bytes')
            
            # Convert image to base64
            image_base64 = None
            if image_bytes:
                try:
                    # Determine image format from bytes or path
                    image_format = 'png'  # Default
                    
                    # Try to determine format from image bytes
                    try:
                        img = Image.open(BytesIO(image_bytes))
                        image_format = img.format.lower() if img.format else 'png'
                        # Normalize format names
                        if image_format in ['jpg', 'jpeg']:
                            image_format = 'jpeg'
                        elif image_format not in ['png', 'gif', 'webp', 'bmp']:
                            image_format = 'png'  # Fallback to PNG
                    except Exception:
                        # If PIL can't determine format, try from path
                        if image_path:
                            ext = Path(image_path).suffix.lower()
                            if ext in ['.jpg', '.jpeg']:
                                image_format = 'jpeg'
                            elif ext == '.gif':
                                image_format = 'gif'
                            elif ext == '.webp':
                                image_format = 'webp'
                            elif ext == '.bmp':
                                image_format = 'bmp'
                    
                    img_base64_encoded = base64.b64encode(image_bytes).decode("utf-8")
                    image_base64 = f"data:image/{image_format};base64,{img_base64_encoded}"
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Error converting image to base64: {e}")
            
            elements.append(Element(
                id=id_generator.next_id(),
                type=ElementType.IMAGE,
                content=Path(image_path).name if image_path else '',
                parent_id=header_stack[-1][1] if header_stack else None,
                metadata={
                    'source': 'xml',
                    'position': xml_pos,
                    'image_index': image_data.get('index', 0),
                    'image_path': image_path,  # Keep for backward compatibility
                    'image_data': image_base64,  # Base64 encoded image
                    'width': image_data.get('width'),
                    'height': image_data.get('height'),
                }
            ))
            continue
        
        if not text and not has_image:
            continue
        
        props = get_properties(xml_pos)
        
        if xml_pos in header_by_pos:
            header_data = header_by_pos[xml_pos]
            header_text = text if text else header_data.get('text', '').strip()
            
            if not (header_text.endswith(':') or _is_table_caption(header_text) or _is_image_caption(header_text)):
                level = _determine_header_level(header_text, props, header_data, header_stack)
                add_header_element(
                    header_text, level, xml_pos,
                    ocr_header=header_data.get('ocr_header')
                )
                continue
        
        if _is_table_caption(text) or _is_image_caption(text):
            flush_text_block()
            caption_type = 'table' if _is_table_caption(text) else 'image'
            elements.append(Element(
                id=id_generator.next_id(),
                type=ElementType.CAPTION,
                content=text,
                parent_id=header_stack[-1][1] if header_stack else None,
                metadata={
                    'source': 'xml',
                    'position': xml_pos,
                    'caption_type': caption_type,
                }
            ))
            continue
        
        if props.get('is_list_item'):
            flush_text_block()
            elements.append(Element(
                id=id_generator.next_id(),
                type=ElementType.LIST_ITEM,
                content=text,
                parent_id=header_stack[-1][1] if header_stack else None,
                metadata={
                    'source': 'xml',
                    'position': xml_pos,
                    'list_type': props.get('list_type', 'unknown'),
                }
            ))
            continue
        
        if current_text_size + text_size > max_text_block_size or len(current_text_block) >= max_paragraphs_per_block:
            flush_text_block()
        
        current_text_block.append(text_raw)
        current_text_positions.append(xml_pos)
        current_text_size += text_size
    
    flush_text_block()
    
    for i, elem in enumerate(elements):
        if elem.type == ElementType.IMAGE:
            if i + 1 < len(elements) and elements[i + 1].type == ElementType.CAPTION and _is_image_caption(elements[i + 1].content):
                elem.parent_id = elements[i + 1].id
                elements[i + 1].metadata['image'] = {
                    'image_path': elem.metadata.get('image_path', ''),  # Keep for backward compatibility
                    'image_data': elem.metadata.get('image_data'),  # Base64 encoded image
                    'image_index': elem.metadata.get('image_index', 0),
                    'content': elem.content
                }
        elif elem.type == ElementType.TABLE:
            if i > 0 and elements[i - 1].type == ElementType.CAPTION and _is_table_caption(elements[i - 1].content):
                elem.parent_id = elements[i - 1].id
                elements[i - 1].metadata['has_table'] = True
    
    return elements

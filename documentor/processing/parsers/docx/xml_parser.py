"""
Parsing DOCX XML markup for extracting document structure.
"""

from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Any, Optional
from io import BytesIO

from PIL import Image

# URL pattern for extracting links from text
URL_PATTERN = re.compile(
    r'(?:https?://|www\.|ftp://)[^\s<>"{}|\\^`\[\]]+[^\s<>"{}|\\^`\[\].,;:!?]',
    re.IGNORECASE
)


NAMESPACES = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
    'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
    'rels': 'http://schemas.openxmlformats.org/package/2006/relationships'
}


def extract_text_from_element(elem: ET.Element, namespaces: Dict[str, str]) -> str:
    """Extracts all text from element."""
    texts = []
    for text_elem in elem.findall('.//w:t', namespaces):
        if text_elem.text:
            texts.append(text_elem.text)
    return ''.join(texts).strip()


def extract_hyperlinks_from_element(elem: ET.Element, namespaces: Dict[str, str], docx_path: Path) -> List[str]:
    """
    Extracts hyperlinks from DOCX element.
    
    Args:
        elem: XML element to extract links from.
        namespaces: XML namespaces dictionary.
        docx_path: Path to DOCX file for resolving relationships.
        
    Returns:
        List of hyperlink URIs.
    """
    links = []
    try:
        # Find all hyperlink elements
        hyperlinks = elem.findall('.//w:hyperlink', namespaces)
        
        # Load relationships if needed
        rels = {}
        try:
            with zipfile.ZipFile(docx_path, 'r') as zip_file:
                try:
                    rels_xml = zip_file.read('word/_rels/document.xml.rels')
                    root = ET.fromstring(rels_xml)
                    
                    for rel in root.findall('.//{*}Relationship'):
                        rel_id = rel.get('Id')
                        rel_type = rel.get('Type', '')
                        target = rel.get('Target')
                        if rel_id and target and 'hyperlink' in rel_type.lower():
                            rels[rel_id] = target
                except KeyError:
                    pass
        except Exception:
            pass
        
        for hyperlink in hyperlinks:
            # Get relationship ID
            r_id = hyperlink.get(f'{{{namespaces["r"]}}}id')
            if r_id and r_id in rels:
                links.append(rels[r_id])
            # Also check for direct anchor attribute
            anchor = hyperlink.get('w:anchor')
            if anchor:
                links.append(anchor)
    except Exception:
        pass
    
    return links


class DocxXmlParser:
    """Parser for DOCX document XML markup."""
    
    def __init__(self, docx_path: Path) -> None:
        """
        Initialize parser.
        
        Args:
            docx_path: Path to DOCX file
        """
        self.docx_path = docx_path
        self._image_rels: Optional[Dict[str, str]] = None
    
    def _load_image_relationships(self) -> Dict[str, str]:
        """Loads image relationships from word/_rels/document.xml.rels."""
        if self._image_rels is not None:
            return self._image_rels
        
        rels = {}
        try:
            with zipfile.ZipFile(self.docx_path, 'r') as zip_file:
                try:
                    rels_xml = zip_file.read('word/_rels/document.xml.rels')
                    root = ET.fromstring(rels_xml)
                    
                    for rel in root.findall('.//{*}Relationship'):
                        rel_type = rel.get('Type', '')
                        if 'image' in rel_type.lower():
                            rel_id = rel.get('Id')
                            target = rel.get('Target')
                            if rel_id and target:
                                rels[rel_id] = target
                except KeyError:
                    pass
        except Exception:
            pass
        
        self._image_rels = rels
        return rels
    
    def extract_all_elements(self) -> List[Dict[str, Any]]:
        """
        Extracts all elements from DOCX XML in order of appearance.
        
        Returns:
            List of elements with type, text and position
        """
        elements = []
        
        try:
            with zipfile.ZipFile(self.docx_path, 'r') as zip_file:
                doc_xml = zip_file.read('word/document.xml')
                root = ET.fromstring(doc_xml)
                
                body = root.find('w:body', NAMESPACES)
                if body is None:
                    return elements
                
                all_elements = list(body)
                
                for xml_pos, elem in enumerate(all_elements):
                    elem_type = None
                    text = ''
                    has_image = False
                    links = []
                    
                    if elem.tag.endswith('}p'):
                        elem_type = 'paragraph'
                        text = extract_text_from_element(elem, NAMESPACES)
                        
                        blips = elem.findall('.//a:blip', NAMESPACES)
                        if blips:
                            has_image = True
                        
                        # Extract hyperlinks from element
                        hyperlinks = extract_hyperlinks_from_element(elem, NAMESPACES, self.docx_path)
                        links.extend(hyperlinks)
                        
                        # Also extract URLs from text
                        text_urls = URL_PATTERN.findall(text)
                        links.extend(text_urls)
                    
                    elif elem.tag.endswith('}tbl'):
                        elem_type = 'table'
                    
                    if elem_type:
                        elements.append({
                            'xml_position': xml_pos,
                            'type': elem_type,
                            'text': text,
                            'has_image': has_image,
                            'links': list(set(links)) if links else [],  # Remove duplicates
                            'element': elem
                        })
        
        except Exception as e:
            raise RuntimeError(f"Error parsing XML: {e}") from e
        
        return elements
    
    def extract_images(self) -> List[Dict[str, Any]]:
        """
        Extracts all images from DOCX.
        
        Returns:
            List of images with data and XML position
        """
        images_data = []
        rels = self._load_image_relationships()
        
        try:
            with zipfile.ZipFile(self.docx_path, 'r') as zip_file:
                doc_xml = zip_file.read('word/document.xml')
                root = ET.fromstring(doc_xml)
                
                body = root.find('w:body', NAMESPACES)
                if body is None:
                    return images_data
                
                all_elements = list(body)
                paragraphs = body.findall('.//w:p', NAMESPACES)
                image_counter = 0
                
                for para_idx, para in enumerate(paragraphs):
                    blips = para.findall('.//a:blip', NAMESPACES)
                    
                    for blip in blips:
                        r_embed = blip.get(f'{{{NAMESPACES["r"]}}}embed')
                        if not r_embed:
                            continue
                        
                        image_path = rels.get(r_embed)
                        if not image_path:
                            continue
                        
                        try:
                            if not image_path.startswith('word/'):
                                zip_path = f'word/{image_path}'
                            else:
                                zip_path = image_path
                            
                            image_bytes = zip_file.read(zip_path)
                            
                            if not image_bytes or len(image_bytes) == 0:
                                continue
                            
                            try:
                                image = Image.open(BytesIO(image_bytes))
                                if image.mode != 'RGB':
                                    image = image.convert('RGB')
                                width, height = image.size
                            except Exception:
                                width, height = None, None
                            
                            xml_pos = None
                            for xml_idx, elem in enumerate(all_elements):
                                if para in elem.findall('.//w:p', NAMESPACES) or elem == para:
                                    xml_pos = xml_idx
                                    break
                            
                            image_counter += 1
                            images_data.append({
                                'index': image_counter,
                                'xml_position': xml_pos,
                                'image_path': image_path,
                                'image_bytes': image_bytes,
                                'width': width,
                                'height': height
                            })
                        except Exception:
                            continue
        
        except Exception as e:
            raise RuntimeError(f"Error extracting images: {e}") from e
        
        return images_data
    
    def extract_tables(self) -> List[Dict[str, Any]]:
        """
        Extracts all tables from DOCX.
        
        Returns:
            List of tables with data and XML position
        """
        tables_data = []
        
        try:
            with zipfile.ZipFile(self.docx_path, 'r') as zip_file:
                doc_xml = zip_file.read('word/document.xml')
                root = ET.fromstring(doc_xml)
                
                body = root.find('w:body', NAMESPACES)
                if body is None:
                    return tables_data
                
                all_elements = list(body)
                tables = body.findall('.//w:tbl', NAMESPACES)
                
                for table_idx, table_elem in enumerate(tables):
                    table_xml_position = None
                    for xml_idx, elem in enumerate(all_elements):
                        if table_elem in elem.findall('.//w:tbl', NAMESPACES) or elem == table_elem:
                            table_xml_position = xml_idx
                            break
                    
                    table_info = {
                        'index': table_idx,
                        'xml_position': table_xml_position,
                        'rows': [],
                        'rows_count': 0,
                        'cols_count': 0,
                        'merged_cells': [],
                        'estimated_page': max(1, ((table_xml_position or 0) // 50) + 1)
                    }
                    
                    rows = table_elem.findall('.//w:tr', NAMESPACES)
                    table_info['rows_count'] = len(rows)
                    max_cols = 0
                    
                    for row_idx, row_elem in enumerate(rows):
                        row_data = {
                            'row_index': row_idx,
                            'cells': [],
                            'cells_count': 0
                        }
                        
                        cells = row_elem.findall('.//w:tc', NAMESPACES)
                        col_idx = 0
                        
                        for cell_elem in cells:
                            cell_text = extract_text_from_element(cell_elem, NAMESPACES)
                            
                            cell_props = cell_elem.find('w:tcPr', NAMESPACES)
                            colspan = 1
                            rowspan = 1
                            is_merged = False
                            
                            if cell_props is not None:
                                grid_span = cell_props.find('w:gridSpan', NAMESPACES)
                                if grid_span is not None:
                                    val = grid_span.get(f'{{{NAMESPACES["w"]}}}val') or grid_span.get('val')
                                    if val:
                                        colspan = int(val)
                                        is_merged = True
                                
                                v_merge = cell_props.find('w:vMerge', NAMESPACES)
                                if v_merge is not None:
                                    val = v_merge.get(f'{{{NAMESPACES["w"]}}}val') or v_merge.get('val')
                                    if val == 'restart':
                                        rowspan = 2
                                        is_merged = True
                                    else:
                                        rowspan = 0
                                        is_merged = True
                            
                            cell_info = {
                                'cell_index': col_idx,
                                'row': row_idx,
                                'col': col_idx,
                                'text': cell_text,
                                'text_length': len(cell_text),
                                'is_merged': is_merged,
                                'colspan': colspan,
                                'rowspan': rowspan
                            }
                            
                            row_data['cells'].append(cell_info)
                            
                            if rowspan > 0:
                                col_idx += colspan
                                max_cols = max(max_cols, col_idx)
                                
                                if is_merged:
                                    table_info['merged_cells'].append({
                                        'row': row_idx,
                                        'col': col_idx - colspan,
                                        'colspan': colspan,
                                        'rowspan': rowspan
                                    })
                        
                        row_data['cells_count'] = len([c for c in row_data['cells'] if c['rowspan'] > 0])
                        table_info['rows'].append(row_data)
                    
                    table_info['cols_count'] = max_cols
                    
                    table_data = []
                    for row_info in table_info['rows']:
                        row_cells = [cell['text'] for cell in row_info['cells'] if cell['rowspan'] > 0]
                        table_data.append(row_cells)
                    
                    table_info['data'] = table_data
                    tables_data.append(table_info)
        
        except Exception as e:
            raise RuntimeError(f"Error extracting tables: {e}") from e
        
        return tables_data

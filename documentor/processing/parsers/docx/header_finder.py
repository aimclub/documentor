"""
Finding headers in DOCX and building rules for finding missed headers.
"""

from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Any, Optional

from .xml_parser import NAMESPACES


def extract_paragraph_properties(docx_path: Path, xml_position: int) -> Dict[str, Any]:
    """Extracts paragraph properties from XML."""
    properties = {
        'font_name': None,
        'font_size': None,
        'is_bold': False,
        'is_italic': False,
        'style': None,
        'level': None,
        'is_list_item': False,
        'list_type': None,
        'is_heading_style': False,
        'alignment': None,
    }
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zip_file:
            doc_xml = zip_file.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            
            body = root.find('w:body', NAMESPACES)
            if body is None:
                return properties
            
            all_elements = list(body)
            if xml_position >= len(all_elements):
                return properties
            
            elem = all_elements[xml_position]
            if not elem.tag.endswith('}p'):
                return properties
            
            pPr = elem.find('w:pPr', NAMESPACES)
            if pPr is not None:
                jc = pPr.find('w:jc', NAMESPACES)
                if jc is not None:
                    alignment_val = jc.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '')
                    if alignment_val:
                        properties['alignment'] = alignment_val
                
                numPr = pPr.find('w:numPr', NAMESPACES)
                if numPr is not None:
                    properties['is_list_item'] = True
                    numId = numPr.find('w:numId', NAMESPACES)
                    if numId is not None:
                        ilvl = numPr.find('w:ilvl', NAMESPACES)
                        if ilvl is not None:
                            properties['list_type'] = 'numbered'
                        else:
                            properties['list_type'] = 'bulleted'
                
                pStyle = pPr.find('w:pStyle', NAMESPACES)
                if pStyle is not None:
                    style_val = pStyle.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '')
                    properties['style'] = style_val
                    
                    if style_val.isdigit():
                        properties['is_heading_style'] = True
                        properties['level'] = int(style_val)
                    elif 'Heading' in style_val or 'heading' in style_val.lower():
                        properties['is_heading_style'] = True
                        match = re.search(r'(\d+)', style_val)
                        if match:
                            properties['level'] = int(match.group(1))
                    elif style_val == 'Title':
                        properties['is_heading_style'] = True
                        properties['level'] = 1
                    elif any(keyword in style_val.lower() for keyword in ['заголовок', 'header', 'title', 'heading']):
                        properties['is_heading_style'] = True
                        match = re.search(r'(\d+)', style_val)
                        if match:
                            properties['level'] = int(match.group(1))
                        else:
                            properties['level'] = 1
            
            bold_runs = 0
            total_runs = 0
            total_text_len = 0
            bold_text_len = 0
            
            for r in elem.findall('.//w:r', NAMESPACES):
                total_runs += 1
                run_text = ''
                for t_el in r.findall('.//w:t', NAMESPACES):
                    if t_el.text:
                        run_text += t_el.text
                run_len = len(run_text.strip())
                total_text_len += run_len
                
                is_run_bold = False
                rPr = r.find('w:rPr', NAMESPACES)
                if rPr is not None:
                    rFonts = rPr.find('w:rFonts', NAMESPACES)
                    if rFonts is not None:
                        font_name = rFonts.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ascii', '')
                        if font_name and not properties['font_name']:
                            properties['font_name'] = font_name
                    
                    sz = rPr.find('w:sz', NAMESPACES)
                    if sz is not None:
                        sz_val = sz.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '')
                        if sz_val and not properties['font_size']:
                            properties['font_size'] = int(sz_val) / 2.0
                    
                    b = rPr.find('w:b', NAMESPACES)
                    if b is not None:
                        val_attr = b.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '')
                        if val_attr.lower() not in ['false', '0', 'off']:
                            is_run_bold = True
                    
                    if not is_run_bold:
                        bCs = rPr.find('w:bCs', NAMESPACES)
                        if bCs is not None:
                            val_attr = bCs.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '')
                            if val_attr.lower() not in ['false', '0', 'off']:
                                is_run_bold = True
                    
                    i_el = rPr.find('w:i', NAMESPACES)
                    if i_el is not None:
                        properties['is_italic'] = True
                
                if is_run_bold:
                    bold_runs += 1
                    bold_text_len += run_len
            
            if total_text_len > 0:
                properties['is_bold'] = (bold_text_len / total_text_len) >= 0.95
            elif total_runs > 0:
                properties['is_bold'] = (bold_runs / total_runs) >= 0.95
            else:
                properties['is_bold'] = False
    
    except Exception:
        pass
    
    return properties


def find_header_in_xml(
    header_text: str,
    all_xml_elements: List[Dict[str, Any]],
    start_from: int = 0
) -> Optional[int]:
    """Finds header in XML by text."""
    header_text_normalized = re.sub(r'\s+', ' ', header_text.lower().strip())
    
    if len(header_text_normalized) < 3:
        for elem in all_xml_elements:
            if elem.get('xml_position', 0) < start_from:
                continue
            if elem.get('type') == 'paragraph':
                xml_text = elem.get('text', '')
                xml_text_normalized = re.sub(r'\s+', ' ', xml_text.lower().strip())
                if header_text_normalized == xml_text_normalized:
                    return elem.get('xml_position')
        return None
    
    header_words = header_text_normalized.split()[:5]
    header_keywords = ' '.join(header_words) if header_words else header_text_normalized
    
    min_startswith_len = max(5, min(30, len(header_text_normalized)))
    
    for elem in all_xml_elements:
        if elem.get('xml_position', 0) < start_from:
            continue
        if elem.get('type') == 'paragraph':
            xml_text = elem.get('text', '')
            xml_text_normalized = re.sub(r'\s+', ' ', xml_text.lower().strip())
            
            if not xml_text_normalized:
                continue
            
            if header_text_normalized == xml_text_normalized:
                return elem.get('xml_position')
            
            if (xml_text_normalized.startswith(header_text_normalized[:min_startswith_len]) or
                header_text_normalized.startswith(xml_text_normalized[:min_startswith_len])):
                return elem.get('xml_position')
            
            if len(header_keywords) > 10:
                xml_words = xml_text_normalized.split()[:5]
                xml_keywords = ' '.join(xml_words) if xml_words else xml_text_normalized
                
                header_set = set(header_keywords.split())
                xml_set = set(xml_keywords.split())
                
                if header_set and xml_set:
                    intersection = len(header_set & xml_set)
                    union = len(header_set | xml_set)
                    similarity = intersection / union if union > 0 else 0
                    
                    if similarity > 0.7:
                        return elem.get('xml_position')
    
    return None


def build_header_rules(docx_path: Path, header_positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Builds rules for finding headers based on found headers."""
    rules = {
        'by_level': {},
        'common_properties': {}
    }
    
    if not header_positions:
        return rules
    
    all_properties = []
    for header_info in header_positions:
        xml_pos = header_info.get('xml_position')
        if xml_pos is None:
            continue
        
        properties = extract_paragraph_properties(docx_path, xml_pos)
        is_heading_style = properties.get('is_heading_style', False)
        is_numbered_header = header_info.get('is_numbered_header', False)
        
        if properties.get('is_list_item') and not is_numbered_header and not is_heading_style:
            continue
        
        if not properties.get('is_bold') and not is_numbered_header and not is_heading_style:
            continue
        
        level = properties.get('level')
        
        if not level:
            text = header_info.get('text', '')
            match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text.strip())
            if match:
                if match.group(3):
                    level = 3
                elif match.group(2):
                    level = 2
                elif match.group(1):
                    level = 1
        
        if not level:
            level = 'unknown'
        
        properties['xml_position'] = xml_pos
        properties['text'] = header_info.get('text', '')
        properties['detected_level'] = level
        all_properties.append(properties)
        
        level_key = str(level)
        if level_key not in rules['by_level']:
            rules['by_level'][level_key] = []
        rules['by_level'][level_key].append(properties)
    
    for level, props_list in rules['by_level'].items():
        if not props_list:
            continue
        
        font_names = [p.get('font_name') for p in props_list if p.get('font_name')]
        font_sizes = [p.get('font_size') for p in props_list if p.get('font_size')]
        bold_count = sum(1 for p in props_list if p.get('is_bold'))
        styles = [p.get('style') for p in props_list if p.get('style')]
        heading_style_count = sum(1 for p in props_list if p.get('is_heading_style'))
        
        most_common_style = None
        if styles:
            most_common_style = max(set(styles), key=styles.count)
        
        level_rules = {
            'font_name': max(set(font_names), key=font_names.count) if font_names else None,
            'font_size': sum(font_sizes) / len(font_sizes) if font_sizes else None,
            'font_size_range': (min(font_sizes), max(font_sizes)) if font_sizes else None,
            'is_bold': bold_count > len(props_list) / 2,
            'style_pattern': most_common_style,
            'is_heading_style': heading_style_count > len(props_list) / 2,
            'count': len(props_list)
        }
        
        rules['by_level'][level] = level_rules
    
    return rules

"""
Finding headers in DOCX and building rules for finding missed headers.
"""

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


def _is_document_metadata(text: str) -> bool:
    """Checks if text is document metadata.
    
    Examples:
    - "Отчет 98 с., 1 кн., 16 рис., 34 табл., 33 источн., 14 прил."
    - "Отчет X страниц, Y таблиц, Z рисунков"
    """
    text_stripped = text.strip()
    if not text_stripped:
        return False
    
    text_lower = text_stripped.lower()
    
    metadata_patterns = [
        r'отчет\s+\d+',
        r'\d+\s+с\.',
        r'\d+\s+кн\.',
        r'\d+\s+рис\.',
        r'\d+\s+табл\.',
        r'\d+\s+источн\.',
        r'\d+\s+прил\.',
        r'страниц',
        r'таблиц',
        r'рисунков',
    ]
    
    matches = sum(1 for pattern in metadata_patterns if re.search(pattern, text_lower))
    return matches >= 2


def _is_list_header(text: str) -> bool:
    """Checks if text is a list header (not a real header).
    
    Examples:
    - "На этапе 1 выполнены следующие работы."
    - "Выполнены следующие работы:"
    """
    text_stripped = text.strip()
    if not text_stripped:
        return False
    
    text_lower = text_stripped.lower()
    
    list_header_patterns = [
        r'на\s+этапе\s+\d+\s+выполнены',
        r'на\s+отчетном\s+этапе\s+выполнены',
        r'выполнены\s+следующие\s+работы',
        r'следующие\s+работы',
        r'список\s+включает',
        r'включает\s+следующие\s+пункты',
    ]
    
    return any(re.search(pattern, text_lower) for pattern in list_header_patterns)


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
        italic_count = sum(1 for p in props_list if p.get('is_italic'))
        styles = [p.get('style') for p in props_list if p.get('style')]
        heading_style_count = sum(1 for p in props_list if p.get('is_heading_style'))
        alignments = [p.get('alignment') for p in props_list if p.get('alignment')]
        
        # Check Caps Lock (70%+ uppercase letters) for headers
        caps_lock_count = 0
        for p in props_list:
            text = p.get('text', '')
            if text:
                letters = [c for c in text if c.isalpha()]
                if len(letters) >= 3:
                    uppercase_count = sum(1 for c in letters if c.isupper())
                    if uppercase_count / len(letters) >= 0.7:
                        caps_lock_count += 1
        
        # Check letters at the beginning (A., B., I., II., etc.)
        starts_with_letter_count = 0
        for p in props_list:
            text = p.get('text', '').strip()
            if text:
                # Patterns: "A. ", "B. ", "I. ", "II. ", "а) ", "б) ", etc.
                if re.match(r'^[А-ЯЁA-Z]\.\s+', text) or re.match(r'^[IVX]+\.\s+', text) or \
                   re.match(r'^[а-яёa-z]\)\s+', text) or re.match(r'^[А-ЯЁA-Z]\)\s+', text):
                    starts_with_letter_count += 1
        
        most_common_style = None
        if styles:
            most_common_style = max(set(styles), key=styles.count)
        
        most_common_alignment = None
        if alignments:
            most_common_alignment = max(set(alignments), key=alignments.count)
        
        level_rules = {
            'font_name': max(set(font_names), key=font_names.count) if font_names else None,
            'font_size': sum(font_sizes) / len(font_sizes) if font_sizes else None,
            'font_size_range': (min(font_sizes), max(font_sizes)) if font_sizes else None,
            'is_bold': bold_count > len(props_list) / 2,
            'is_italic': italic_count > len(props_list) / 2,  # Majority are italic
            'style_pattern': most_common_style,
            'is_heading_style': heading_style_count > len(props_list) / 2,
            'alignment': most_common_alignment,
            'is_caps_lock': caps_lock_count > len(props_list) / 2,  # Majority in Caps Lock
            'starts_with_letter': starts_with_letter_count > len(props_list) / 2,  # Majority start with letter
            'count': len(props_list)
        }
        
        rules['by_level'][level] = level_rules
    
    # Add common_header if all headers are unknown level
    if all_properties and len(rules['by_level']) == 1 and 'unknown' in rules['by_level']:
        all_font_names = [p.get('font_name') for p in all_properties if p.get('font_name')]
        all_font_sizes = [p.get('font_size') for p in all_properties if p.get('font_size')]
        all_bold_count = sum(1 for p in all_properties if p.get('is_bold'))
        all_styles = [p.get('style') for p in all_properties if p.get('style')]
        all_heading_style_count = sum(1 for p in all_properties if p.get('is_heading_style'))
        
        if all_font_names or all_font_sizes or all_styles:
            most_common_style = None
            if all_styles:
                most_common_style = max(set(all_styles), key=all_styles.count)
            
            all_alignments = [p.get('alignment') for p in all_properties if p.get('alignment')]
            most_common_alignment = max(set(all_alignments), key=all_alignments.count) if all_alignments else None
            
            # Check Caps Lock for all headers
            all_caps_lock_count = 0
            for p in all_properties:
                text = p.get('text', '')
                if text:
                    letters = [c for c in text if c.isalpha()]
                    if len(letters) >= 3:
                        uppercase_count = sum(1 for c in letters if c.isupper())
                        if uppercase_count / len(letters) >= 0.7:
                            all_caps_lock_count += 1
            
            # Check letters at the beginning for all headers
            all_starts_with_letter_count = 0
            for p in all_properties:
                text = p.get('text', '').strip()
                if text:
                    if re.match(r'^[А-ЯЁA-Z]\.\s+', text) or re.match(r'^[IVX]+\.\s+', text) or \
                       re.match(r'^[а-яёa-z]\)\s+', text) or re.match(r'^[А-ЯЁA-Z]\)\s+', text):
                        all_starts_with_letter_count += 1
            
            rules['common_header'] = {
                'font_name': max(set(all_font_names), key=all_font_names.count) if all_font_names else None,
                'font_size': sum(all_font_sizes) / len(all_font_sizes) if all_font_sizes else None,
                'font_size_range': (min(all_font_sizes), max(all_font_sizes)) if all_font_sizes else None,
                'is_bold': all_bold_count > len(all_properties) / 2,
                'style_pattern': most_common_style,
                'is_heading_style': all_heading_style_count > len(all_properties) / 2,
                'alignment': most_common_alignment,
                'is_caps_lock': all_caps_lock_count > len(all_properties) / 2,
                'starts_with_letter': all_starts_with_letter_count > len(all_properties) / 2,
            }
    
    return rules


def find_missing_headers_by_rules(
    docx_path: Path,
    all_xml_elements: List[Dict[str, Any]],
    header_rules: Dict[str, Any],
    found_positions: List[int],
    found_texts: set = None,
    header_positions: List[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Finds missing headers in XML using rules based on found headers.
    
    This function searches for headers that were missed by OCR but match
    the patterns and properties of found headers.
    
    Args:
        docx_path: Path to DOCX file
        all_xml_elements: All XML elements from DOCX
        header_rules: Rules built from found headers
        found_positions: List of XML positions already found
        found_texts: Set of normalized texts already found
        header_positions: List of header positions for sequence checking
    
    Returns:
        List of found missing headers with metadata
    """
    import logging
    from .hierarchy_builder import _is_table_caption, _is_image_caption
    from .header_processor import _is_definition_pattern, _is_separator_line, _is_list_item_pattern
    
    logger = logging.getLogger(__name__)
    
    found_headers = []
    found_positions_set = set(found_positions)
    if found_texts is None:
        found_texts = set()
    
    rules_by_level = header_rules.get('by_level', {})
    common_header = header_rules.get('common_header', {})
    
    if not rules_by_level and not common_header:
        return found_headers
    
    for i, elem in enumerate(all_xml_elements):
        if elem.get('type') != 'paragraph':
            continue
        
        xml_pos = elem.get('xml_position')
        if xml_pos in found_positions_set:
            continue
        
        text = elem.get('text', '').strip()
        
        # Calculate adaptive header length threshold based on found headers
        if found_texts:
            avg_header_length = sum(len(t) for t in found_texts) / len(found_texts) if found_texts else 100
            max_header_length = max(50, min(int(avg_header_length * 2.5), 300))
        else:
            max_header_length = 200
        
        if not text or len(text) < 1:
            continue
        
        if len(text) > max(max_header_length, 500):
            continue
        
        # Check if already found by text
        normalized_text = re.sub(r'\s+', ' ', text.lower().strip())
        if normalized_text in found_texts:
            continue
        
        # Filter out non-headers
        if text.endswith(':'):
            continue
        
        if _is_table_caption(text) or _is_image_caption(text):
            continue
        
        if _is_definition_pattern(text):
            continue
        
        if _is_separator_line(text):
            continue
        
        if _is_list_item_pattern(text):
            continue
        
        if _is_document_metadata(text):
            continue
        
        if _is_list_header(text):
            continue
        
        # Check if part of list sequence (1., 2., 3., ...)
        text_match = re.match(r'^(\d+)\.\s+(.+)$', text)
        if text_match:
            curr_num = int(text_match.group(1))
            
            # Check previous element
            if i > 0:
                prev_elem = all_xml_elements[i - 1]
                if prev_elem.get('type') == 'paragraph':
                    prev_text = prev_elem.get('text', '').strip()
                    prev_match = re.match(r'^(\d+)\.\s+(.+)$', prev_text)
                    if prev_match:
                        prev_num = int(prev_match.group(1))
                        if prev_num == curr_num - 1:
                            logger.debug(f"Skipped element (part of list sequence): '{text[:50]}...' at position {xml_pos}")
                            continue
            
            # Check next element
            if i + 1 < len(all_xml_elements):
                next_elem = all_xml_elements[i + 1]
                if next_elem.get('type') == 'paragraph':
                    next_text = next_elem.get('text', '').strip()
                    next_match = re.match(r'^(\d+)\.\s+(.+)$', next_text)
                    if next_match:
                        next_num = int(next_match.group(1))
                        if next_num == curr_num + 1:
                            logger.debug(f"Skipped element (part of list sequence): '{text[:50]}...' at position {xml_pos}")
                            continue
        
        properties = extract_paragraph_properties(docx_path, xml_pos)
        
        is_heading_style = properties.get('is_heading_style', False)
        heading_level_from_style = properties.get('level') if is_heading_style else None
        
        # Calculate adaptive thresholds
        if found_texts:
            avg_header_length = sum(len(t) for t in found_texts) / len(found_texts) if found_texts else 50
            short_text_threshold = max(30, min(int(avg_header_length * 1.2), 150))
        else:
            short_text_threshold = 100
        
        min_font_size = 10
        if header_rules.get('by_level'):
            font_sizes = []
            for level_rules in header_rules['by_level'].values():
                if level_rules.get('font_size'):
                    font_sizes.append(level_rules['font_size'])
            if font_sizes:
                min_font_size = max(10, min(font_sizes) - 2)
        
        # Check numbered header
        # Support variants with and without space: "1Анализ", "1.1Актуальность", "1. Анализ", "1.1. Актуальность"
        is_list_item = properties.get('is_list_item', False)
        is_numbered_header = False
        if not is_list_item or is_heading_style:
            is_numbered_header = any(re.match(pattern, text.strip()) for pattern in [
                r'^\d+(?:\.\s*)?[А-ЯЁA-Z]',  # "1Заголовок" or "1. Заголовок"
                r'^\d+\.\d+(?:\.\s*)?[А-ЯЁA-Z]',  # "1.1Заголовок" or "1.1. Заголовок"
                r'^\d+\.\d+\.\d+(?:\.\s*)?[А-ЯЁA-Z]',  # "1.1.1Заголовок" or "1.1.1. Заголовок"
            ])
        
        bold_text_threshold = max(short_text_threshold, 100)
        is_short_bold_text = (
            len(text) <= bold_text_threshold and
            properties.get('is_bold') and
            properties.get('font_size') and properties.get('font_size') >= min_font_size
        )
        
        detected_level = None
        if heading_level_from_style:
            detected_level = heading_level_from_style
        # Support variants with and without space: "1Анализ", "1.1Актуальность"
        match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.?\s*)?', text.strip())
        if match:
            if match.group(3):
                detected_level = 3
            elif match.group(2):
                detected_level = 2
            elif match.group(1):
                detected_level = 1
        
        # Match against rules
        best_match = None
        best_score = 0
        
        for level, level_rules in rules_by_level.items():
            matches = 0
            total_checks = 0
            
            if level_rules.get('font_name'):
                total_checks += 1
                if properties.get('font_name') == level_rules['font_name']:
                    matches += 1
            
            if level_rules.get('font_size'):
                total_checks += 1
                font_size = properties.get('font_size')
                if font_size:
                    target_size = level_rules['font_size']
                    if abs(font_size - target_size) <= 1.0:
                        matches += 1
            
            if level_rules.get('is_bold') is not None:
                total_checks += 1
                if properties.get('is_bold') == level_rules['is_bold']:
                    matches += 1
            
            # style_pattern has higher weight (scale = 3.0)
            if level_rules.get('style_pattern'):
                total_checks += 3
                if properties.get('style') == level_rules['style_pattern']:
                    matches += 3
            
            if level_rules.get('is_heading_style') is not None:
                total_checks += 1
                if properties.get('is_heading_style') == level_rules['is_heading_style']:
                    matches += 1
            
            # Check alignment
            if level_rules.get('alignment'):
                total_checks += 1
                if properties.get('alignment') == level_rules['alignment']:
                    matches += 1
            
            # Check Caps Lock (70%+ uppercase letters)
            if level_rules.get('is_caps_lock') is not None:
                total_checks += 1
                text_letters = [c for c in text if c.isalpha()]
                is_caps_lock = False
                if len(text_letters) >= 3:
                    uppercase_count = sum(1 for c in text_letters if c.isupper())
                    is_caps_lock = (uppercase_count / len(text_letters)) >= 0.7
                if is_caps_lock == level_rules['is_caps_lock']:
                    matches += 1
            
            # Check letter at the beginning (A., B., I., II., etc.)
            if level_rules.get('starts_with_letter') is not None:
                total_checks += 1
                starts_with_letter = bool(
                    re.match(r'^[А-ЯЁA-Z]\.\s+', text.strip()) or 
                    re.match(r'^[IVX]+\.\s+', text.strip()) or
                    re.match(r'^[а-яёa-z]\)\s+', text.strip()) or
                    re.match(r'^[А-ЯЁA-Z]\)\s+', text.strip())
                )
                if starts_with_letter == level_rules['starts_with_letter']:
                    matches += 1
            
            if total_checks > 0:
                score = matches / total_checks
                if detected_level and str(detected_level) == level:
                    score += 0.2
                
                if score > best_score:
                    best_score = score
                    best_match = {
                        'level': level,
                        'score': score,
                        'matches': matches,
                        'total_checks': total_checks
                    }
        
        # Check common_header
        if not best_match and common_header:
            matches = 0
            total_checks = 0
            
            if common_header.get('font_name'):
                total_checks += 1
                if properties.get('font_name') == common_header['font_name']:
                    matches += 1
            
            if common_header.get('font_size'):
                total_checks += 1
                font_size = properties.get('font_size')
                if font_size:
                    target_size = common_header['font_size']
                    if abs(font_size - target_size) <= 1.0:
                        matches += 1
            
            if common_header.get('is_bold') is not None:
                total_checks += 1
                if properties.get('is_bold') == common_header['is_bold']:
                    matches += 1
            
            if common_header.get('style_pattern'):
                total_checks += 1
                if properties.get('style') == common_header['style_pattern']:
                    matches += 1
            
            if common_header.get('is_heading_style') is not None:
                total_checks += 1
                if properties.get('is_heading_style') == common_header['is_heading_style']:
                    matches += 1
            
            # Check alignment
            if common_header.get('alignment'):
                total_checks += 1
                if properties.get('alignment') == common_header['alignment']:
                    matches += 1
            
            # Check Caps Lock (70%+ uppercase letters)
            if common_header.get('is_caps_lock') is not None:
                total_checks += 1
                text_letters = [c for c in text if c.isalpha()]
                is_caps_lock = False
                if len(text_letters) >= 3:
                    uppercase_count = sum(1 for c in text_letters if c.isupper())
                    is_caps_lock = (uppercase_count / len(text_letters)) >= 0.7
                if is_caps_lock == common_header['is_caps_lock']:
                    matches += 1
            
            # Check letter at the beginning (A., B., I., II., etc.)
            if common_header.get('starts_with_letter') is not None:
                total_checks += 1
                starts_with_letter = bool(
                    re.match(r'^[А-ЯЁA-Z]\.\s+', text.strip()) or 
                    re.match(r'^[IVX]+\.\s+', text.strip()) or
                    re.match(r'^[а-яёa-z]\)\s+', text.strip()) or
                    re.match(r'^[А-ЯЁA-Z]\)\s+', text.strip())
                )
                if starts_with_letter == common_header['starts_with_letter']:
                    matches += 1
            
            if total_checks > 0:
                score = matches / total_checks
                if detected_level:
                    score += 0.3
                
                if score > best_score:
                    best_score = score
                    best_match = {
                        'level': detected_level if detected_level else 'unknown',
                        'score': score,
                        'matches': matches,
                        'total_checks': total_checks
                    }
        
        # Priority: heading style
        if is_heading_style and heading_level_from_style:
            best_match = {
                'level': str(heading_level_from_style),
                'score': 1.0,
                'matches': 1,
                'total_checks': 1
            }
        # Numbered header with confirmation
        elif not best_match and is_numbered_header and (properties.get('is_bold') or is_heading_style):
            match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text.strip())
            if match:
                if match.group(3):
                    detected_level = 3
                elif match.group(2):
                    detected_level = 2
                elif match.group(1):
                    detected_level = 1
            else:
                detected_level = 1
            
            best_match = {
                'level': str(detected_level),
                'score': 0.8,
                'matches': 1,
                'total_checks': 1
            }
        # Short bold text
        elif (not best_match or best_match['score'] < 0.5) and is_short_bold_text:
            font_size = properties.get('font_size', 12)
            
            if header_rules.get('by_level'):
                font_sizes_by_level = {}
                for level, level_rules in header_rules['by_level'].items():
                    if level_rules.get('font_size'):
                        try:
                            font_sizes_by_level[int(level)] = level_rules['font_size']
                        except (ValueError, TypeError):
                            pass
                
                if font_sizes_by_level:
                    sorted_levels = sorted(font_sizes_by_level.items(), key=lambda x: x[1], reverse=True)
                    if len(sorted_levels) >= 2:
                        level1_size = sorted_levels[0][1] if len(sorted_levels) > 0 else 16
                        level2_size = sorted_levels[1][1] if len(sorted_levels) > 1 else 14
                        level3_size = sorted_levels[2][1] if len(sorted_levels) > 2 else 12
                        
                        if font_size >= level1_size:
                            detected_level = 1
                        elif font_size >= level2_size:
                            detected_level = 2
                        elif font_size >= level3_size:
                            detected_level = 3
                        else:
                            detected_level = 3
                    else:
                        base_size = sorted_levels[0][1]
                        if font_size >= base_size:
                            detected_level = 1
                        elif font_size >= base_size - 2:
                            detected_level = 2
                        else:
                            detected_level = 3
                else:
                    if font_size >= 16:
                        detected_level = 1
                    elif font_size >= 14:
                        detected_level = 2
                    else:
                        detected_level = 3
            else:
                if font_size >= 16:
                    detected_level = 1
                elif font_size >= 14:
                    detected_level = 2
                else:
                    detected_level = 3
            
            best_match = {
                'level': str(detected_level),
                'score': 0.8,
                'matches': 3,
                'total_checks': 3
            }
        
        # Final filtering
        if best_match and best_match['score'] >= 0.5:
            text_stripped = text.strip()
            # Support variants with and without space: "1Анализ", "1.1Актуальность"
            numbered_patterns = [
                r'^\d+(?:\.\s*)?[А-ЯЁA-Z]',  # "1Заголовок" or "1. Заголовок"
                r'^\d+\.\d+(?:\.\s*)?[А-ЯЁA-Z]',  # "1.1Заголовок" or "1.1. Заголовок"
                r'^\d+\.\d+\.\d+(?:\.\s*)?[А-ЯЁA-Z]',  # "1.1.1Заголовок" or "1.1.1. Заголовок"
            ]
            is_numbered_header_check = any(re.match(pattern, text_stripped) for pattern in numbered_patterns)
            
            is_heading_style_check = properties.get('is_heading_style', False)
            
            # Filter list items
            if properties.get('is_list_item') and not is_heading_style_check:
                logger.debug(f"Skipped list item (not header): '{text[:50]}...' at position {xml_pos}")
                continue
            
            # Check bold requirement
            if found_texts:
                avg_header_length = sum(len(t) for t in found_texts) / len(found_texts) if found_texts else 50
                short_text_threshold_check = max(30, min(int(avg_header_length * 1.2), 150))
            else:
                short_text_threshold_check = 50
            
            min_font_size_check = 10
            if header_rules.get('by_level'):
                font_sizes = []
                for level_rules in header_rules['by_level'].values():
                    if level_rules.get('font_size'):
                        font_sizes.append(level_rules['font_size'])
                if font_sizes:
                    min_font_size_check = max(10, min(font_sizes) - 2)
            
            is_short_text_with_style = (
                len(text) <= short_text_threshold_check and
                (is_heading_style_check or (properties.get('font_size') and properties.get('font_size') >= min_font_size_check))
            )
            
            if not properties.get('is_bold') and not is_numbered_header_check and not is_heading_style_check and not is_short_bold_text and not is_short_text_with_style:
                logger.debug(f"Skipped non-bold text (not header): '{text[:50]}...' at position {xml_pos}")
                continue
            
            if text.strip().endswith(':'):
                continue
            
            # Check numbering sequence violation
            text_match_seq = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text.strip())
            if text_match_seq and header_positions:
                curr_num = int(text_match_seq.group(1))
                curr_sub = text_match_seq.group(2)
                
                curr_level_from_match = 1
                if text_match_seq.group(3):
                    curr_level_from_match = 3
                elif text_match_seq.group(2):
                    curr_level_from_match = 2
                
                try:
                    curr_level = int(best_match.get('level', curr_level_from_match))
                except (ValueError, TypeError):
                    curr_level = curr_level_from_match
                
                # Find previous numbered header
                all_prev_headers = []
                if header_positions:
                    all_prev_headers.extend(header_positions)
                all_prev_headers.extend(found_headers)
                all_prev_headers = sorted(all_prev_headers, key=lambda h: h.get('xml_position', 0))
                
                prev_numbered_header = None
                for prev_header in reversed(all_prev_headers):
                    if prev_header.get('xml_position', 0) < xml_pos:
                        prev_text = prev_header.get('text', '').strip()
                        prev_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', prev_text)
                        if prev_match:
                            prev_level_from_match = 1
                            if prev_match.group(3):
                                prev_level_from_match = 3
                            elif prev_match.group(2):
                                prev_level_from_match = 2
                            
                            prev_level = prev_header.get('level', prev_level_from_match)
                            try:
                                prev_level = int(prev_level)
                            except (ValueError, TypeError):
                                prev_level = prev_level_from_match
                            
                            prev_numbered_header = {
                                'text': prev_text,
                                'num': int(prev_match.group(1)),
                                'sub': prev_match.group(2),
                                'level': prev_level,
                                'xml_position': prev_header.get('xml_position', 0)
                            }
                            break
                
                if prev_numbered_header:
                    prev_num = prev_numbered_header['num']
                    prev_sub = prev_numbered_header['sub']
                    prev_level = prev_numbered_header['level']
                    prev_xml_pos = prev_numbered_header['xml_position']
                    
                    if properties.get('is_list_item'):
                        logger.debug(f"Skipped header (is_list_item in XML): '{text[:50]}...' at position {xml_pos}")
                        continue
                    
                    # Check sequential numbering (list)
                    if (curr_level == prev_level and
                        (xml_pos - prev_xml_pos) <= 10 and
                        not prev_sub and not curr_sub and
                        curr_num == prev_num + 1):
                        has_other_headers_between = False
                        for other_header in all_prev_headers:
                            other_pos = other_header.get('xml_position', 0)
                            if prev_xml_pos < other_pos < xml_pos:
                                other_text = other_header.get('text', '').strip()
                                other_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', other_text)
                                if other_match:
                                    has_other_headers_between = True
                                    break
                        
                        if not has_other_headers_between:
                            logger.debug(f"Skipped header (sequential list numbering): '{prev_numbered_header['text'][:30]}...' ({prev_num}.) → '{text[:30]}...' ({curr_num}.) at position {xml_pos}")
                            continue
                    
                    # Check sequence violation
                    is_sequence_violation = False
                    
                    if curr_num < prev_num:
                        if prev_num - curr_num > 1:
                            is_sequence_violation = True
                        elif prev_num - curr_num == 1 and prev_sub:
                            is_sequence_violation = True
                    elif curr_num == prev_num and prev_sub and curr_sub:
                        if int(curr_sub) < int(prev_sub):
                            is_sequence_violation = True
                    elif curr_num == 1 and prev_num > 1:
                        is_sequence_violation = True
                    
                    if is_sequence_violation and curr_level >= prev_level:
                        logger.debug(f"Skipped header (sequence violation): '{prev_numbered_header['text'][:30]}...' ({prev_num}.{prev_sub or ''}, level {prev_level}) → '{text[:30]}...' ({curr_num}.{curr_sub or ''}, level {curr_level}) at position {xml_pos}")
                        continue
            
            found_headers.append({
                'xml_position': xml_pos,
                'text': text,
                'level': best_match['level'],
                'properties': properties,
                'match_score': best_match['score']
            })
            found_positions_set.add(xml_pos)
            logger.debug(f"Found missing header (level {best_match['level']}): '{text[:50]}...' at position {xml_pos}")
    
    # Post-filter: remove chains of 3+ consecutive headers of same level
    if found_headers:
        all_header_positions = sorted(found_positions)
        all_candidates = sorted(found_headers, key=lambda h: h['xml_position'])
        
        positions_to_remove = set()
        i = 0
        while i < len(all_candidates):
            chain = [all_candidates[i]]
            j = i + 1
            while j < len(all_candidates):
                prev_pos = chain[-1]['xml_position']
                curr_pos = all_candidates[j]['xml_position']
                curr_level = all_candidates[j]['level']
                prev_level = chain[-1]['level']
                prev_text = chain[-1]['text']
                curr_text = all_candidates[j]['text']
                
                prev_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', prev_text.strip())
                curr_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', curr_text.strip())
                
                is_sequential = False
                if prev_match and curr_match:
                    prev_num = int(prev_match.group(1))
                    curr_num = int(curr_match.group(1))
                    prev_sub = prev_match.group(2)
                    curr_sub = curr_match.group(2)
                    
                    try:
                        prev_level_int = int(prev_level)
                        curr_level_int = int(curr_level)
                    except (ValueError, TypeError):
                        prev_level_int = 1
                        curr_level_int = 1
                    
                    if curr_level_int == prev_level_int and curr_num == prev_num + 1:
                        if not prev_sub and not curr_sub:
                            is_sequential = True
                elif not prev_match and not curr_match:
                    try:
                        prev_level_int = int(prev_level)
                        curr_level_int = int(curr_level)
                    except (ValueError, TypeError):
                        prev_level_int = 1
                        curr_level_int = 1
                    is_sequential = (curr_level_int == prev_level_int)
                
                try:
                    prev_level_int = int(prev_level)
                    curr_level_int = int(curr_level)
                except (ValueError, TypeError):
                    prev_level_int = 1
                    curr_level_int = 1
                
                if curr_level_int == prev_level_int and (curr_pos - prev_pos) <= 2 and is_sequential:
                    chain.append(all_candidates[j])
                    j += 1
                else:
                    break
            
            if len(chain) >= 2:
                is_numbered_sequence = True
                for k in range(len(chain) - 1):
                    prev_text = chain[k]['text'].strip()
                    curr_text = chain[k + 1]['text'].strip()
                    prev_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', prev_text)
                    curr_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', curr_text)
                    if prev_match and curr_match:
                        prev_num = int(prev_match.group(1))
                        curr_num = int(curr_match.group(1))
                        prev_sub = prev_match.group(2)
                        curr_sub = curr_match.group(2)
                        if curr_num != prev_num + 1 or prev_sub or curr_sub:
                            is_numbered_sequence = False
                            break
                    else:
                        is_numbered_sequence = False
                        break
                
                if is_numbered_sequence:
                    for item in chain:
                        positions_to_remove.add(item['xml_position'])
                        logger.debug(f"Removed chain element (sequential list numbering): level {item['level']}, '{item['text'][:50]}...' at position {item['xml_position']}")
                else:
                    for item in chain:
                        if item['xml_position'] not in set(found_positions):
                            positions_to_remove.add(item['xml_position'])
                            logger.debug(f"Removed chain element (not header, list): level {item['level']}, '{item['text'][:50]}...' at position {item['xml_position']}")
            
            i = j
        
        if positions_to_remove:
            found_headers = [h for h in found_headers if h['xml_position'] not in positions_to_remove]
            logger.info(f"Removed {len(positions_to_remove)} false headers (chain enumerations)")
    
    return found_headers

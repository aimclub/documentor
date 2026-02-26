"""
Parsing table of contents from DOCX documents.
"""

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Any, Optional

from .xml_parser import NAMESPACES, extract_text_from_element


def _get_paragraph_text_from_xml(p: ET.Element) -> str:
    """Extracts all text from XML paragraph."""
    texts = []
    for elem in p.iter():
        if elem.tag == f'{{{NAMESPACES["w"]}}}t':
            if elem.text:
                texts.append(elem.text)
        elif elem.tag == f'{{{NAMESPACES["w"]}}}tab':
            texts.append('\t')
        elif elem.tag == f'{{{NAMESPACES["w"]}}}br':
            texts.append(' ')
    return ''.join(texts).strip()


def _get_paragraph_style_from_xml(p: ET.Element) -> Optional[str]:
    """Gets paragraph style from XML."""
    p_pr = p.find('w:pPr', NAMESPACES)
    if p_pr is not None:
        p_style = p_pr.find('w:pStyle', NAMESPACES)
        if p_style is not None:
            return p_style.get(f'{{{NAMESPACES["w"]}}}val') or p_style.get('val')
    return None


def _find_bookmark_text_in_xml(root: ET.Element, bookmark_name: str) -> Optional[Dict[str, Any]]:
    """Finds bookmark by name and extracts header text."""
    body = root.find('w:body', NAMESPACES)
    if body is None:
        return None
    
    for para in body.findall('w:p', NAMESPACES):
        bookmark_starts = para.findall('.//w:bookmarkStart', NAMESPACES)
        for bs in bookmark_starts:
            bs_name = bs.get(f'{{{NAMESPACES["w"]}}}name') or bs.get('name')
            if bs_name == bookmark_name:
                title = _get_paragraph_text_from_xml(para)
                if not title or not title.strip():
                    continue
                
                level = 1
                style = _get_paragraph_style_from_xml(para)
                if style:
                    if style.isdigit():
                        level = int(style)
                    elif style.upper().startswith('HEADING'):
                        try:
                            level = int(style.replace('Heading', '').replace('heading', '').strip())
                        except Exception:
                            pass
                
                level_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', title.strip())
                if level_match:
                    if level_match.group(3):
                        level = 3
                    elif level_match.group(2):
                        level = 2
                    else:
                        level = 1
                
                return {
                    'title': title.strip(),
                    'level': level,
                    'style': style,
                    'bookmark_name': bookmark_name
                }
    
    return None


def _parse_toc_from_field(root: ET.Element) -> List[Dict[str, Any]]:
    """Parses table of contents from TOC fields via PAGEREF."""
    toc_entries = []
    
    body = root.find('w:body', NAMESPACES)
    if body is None:
        return toc_entries
    
    all_paras = list(body.findall('w:p', NAMESPACES))
    all_instr_texts = root.findall('.//w:instrText', NAMESPACES)
    
    pageref_bookmarks = []
    for instr in all_instr_texts:
        if instr.text and 'PAGEREF' in instr.text.upper():
            bookmark_match = re.search(r'PAGEREF\s+(_Toc\d+)', instr.text, re.IGNORECASE)
            if bookmark_match:
                bookmark_name = bookmark_match.group(1)
                parent_para = None
                for para in all_paras:
                    if instr in para.findall('.//w:instrText', NAMESPACES):
                        parent_para = para
                        break
                
                para_text = ""
                page_num = None
                if parent_para is not None:
                    para_text = _get_paragraph_text_from_xml(parent_para)
                    page_match = re.search(r'(\d+)\s*$', para_text)
                    if page_match:
                        page_num = int(page_match.group(1))
                
                pageref_bookmarks.append({
                    'bookmark_name': bookmark_name,
                    'para_text': para_text,
                    'page_num': page_num
                })
    
    for pageref_info in pageref_bookmarks:
        bookmark_name = pageref_info['bookmark_name']
        page_num = pageref_info['page_num']
        bookmark_data = _find_bookmark_text_in_xml(root, bookmark_name)
        
        if bookmark_data:
            title = bookmark_data['title']
            level = bookmark_data['level']
            if page_num is None:
                page_match = re.search(r'(\d+)\s*$', pageref_info['para_text'])
                if page_match:
                    page_num = int(page_match.group(1))
            
            if len(title) >= 3 and re.search(r'[а-яёa-z]', title, re.IGNORECASE):
                is_technical_term = bool(
                    re.match(r'^[a-zA-Z]+$', title) and len(title) < 30 and 
                    not re.search(r'[а-яё]', title, re.IGNORECASE) and ' ' not in title
                )
                if not is_technical_term:
                    toc_entries.append({
                        'title': title,
                        'page': page_num,
                        'level': level,
                        'bookmark_name': bookmark_name
                    })
    
    return toc_entries


def _parse_toc_from_styles(root: ET.Element) -> List[Dict[str, Any]]:
    """Parses table of contents from paragraphs with TOC1, TOC2, TOC3 styles."""
    toc_entries = []
    
    body = root.find('w:body', NAMESPACES)
    if body is None:
        return toc_entries
    
    in_toc_section = False
    toc_start_found = False
    
    for para in body.findall('w:p', NAMESPACES):
        text = _get_paragraph_text_from_xml(para)
        style = _get_paragraph_style_from_xml(para)
        
        if not toc_start_found:
            text_lower = text.lower().strip()
            if text_lower in ['содержание', 'оглавление', 'contents', 'table of contents']:
                toc_start_found = True
                in_toc_section = True
                continue
        
        if in_toc_section:
            if style and style.upper().startswith('TOC'):
                level = 1
                if len(style) > 3:
                    try:
                        level = int(style[3:])
                    except Exception:
                        pass
                
                page_num = None
                title = text
                page_match = re.search(r'(\d+)\s*$', text)
                if page_match:
                    page_num = int(page_match.group(1))
                    title = re.sub(r'[.\s\-]+?\d+\s*$', '', text).strip()
                
                if title and len(title) >= 3:
                    toc_entries.append({
                        'title': title.strip(),
                        'page': page_num,
                        'level': level,
                        'style': style
                    })
            elif text and len(text) > 0:
                text_lower = text.lower().strip()
                if text_lower in ['введение', 'introduction', '1.', '1 ', 'глава', 'часть']:
                    if len(toc_entries) > 0:
                        break
    
    return toc_entries


def _parse_toc_from_paragraphs(
    all_elements: List[Dict[str, Any]],
    toc_header_xml_pos: int,
    next_header_xml_pos: int
) -> List[Dict[str, Any]]:
    """Parses table of contents from paragraphs between 'CONTENTS' header and next header."""
    toc_entries = []
    
    for elem in all_elements:
        xml_pos = elem.get('xml_position', -1)
        if toc_header_xml_pos < xml_pos < next_header_xml_pos:
            elem_type = elem.get('type', '')
            text = elem.get('text', '').strip()
            
            if elem_type == 'paragraph' and text:
                text_lower = text.lower().strip()
                if text_lower in ['содержание', 'оглавление', 'contents', 'table of contents']:
                    continue
                
                clean_text = re.sub(r'\.{2,}', '\t', text)
                parts = re.split(r'\t|\s{3,}', clean_text.strip())
                
                if len(parts) >= 2:
                    title_part = parts[0].strip()
                    page_part = parts[-1].strip()
                    
                    match = re.match(r'^(\d+(?:\.\d+)*)\.?\s+(.+)$', title_part)
                    if match:
                        number = match.group(1)
                        title = match.group(2).strip().rstrip('\t.').strip()
                        level = number.count('.') + 1
                        
                        page_num = None
                        try:
                            page_num = int(page_part)
                        except ValueError:
                            page_match = re.search(r'(\d+)\s*$', text)
                            if page_match:
                                try:
                                    page_num = int(page_match.group(1))
                                except ValueError:
                                    pass
                        
                        if len(title) >= 3 and re.search(r'[а-яёa-z]', title, re.IGNORECASE):
                            is_technical_term = bool(
                                re.match(r'^[a-zA-Z]+$', title) and len(title) < 30 and 
                                not re.search(r'[а-яё]', title, re.IGNORECASE) and ' ' not in title
                            )
                            if not is_technical_term:
                                toc_entries.append({
                                    'title': title,
                                    'page': page_num,
                                    'level': level,
                                    'number': number
                                })
    
    return toc_entries


def parse_toc_from_docx(docx_path: Path, all_xml_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Parses table of contents from DOCX file.
    
    Args:
        docx_path: Path to DOCX file
        all_xml_elements: All XML document elements
        
    Returns:
        List of headers from table of contents
    """
    toc_entries = []
    
    try:
        with zipfile.ZipFile(docx_path, 'r') as zip_file:
            doc_xml = zip_file.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            
            toc_from_field = _parse_toc_from_field(root)
            if toc_from_field:
                return toc_from_field
            
            toc_from_styles = _parse_toc_from_styles(root)
            if toc_from_styles:
                return toc_from_styles
            
            toc_header_pos = None
            next_header_pos = None
            
            for i, elem in enumerate(all_xml_elements):
                text = elem.get('text', '').strip().lower()
                if (text in ['содержание', 'оглавление', 'contents', 'table of contents'] or
                    text.startswith('содержание') or text.startswith('оглавление')):
                    toc_header_pos = elem.get('xml_position', -1)
                    toc_entries_found = 0
                    
                    for j in range(i + 1, min(i + 100, len(all_xml_elements))):
                        next_elem = all_xml_elements[j]
                        next_text = next_elem.get('text', '').strip()
                        
                        if not next_text:
                            continue
                        
                        has_page_num = bool(re.search(r'\d+\s*$', next_text))
                        has_separators = bool(re.search(r'[.\-]{3,}', next_text))
                        has_numbering = bool(re.match(r'^\d+(?:\.\d+)*\s+', next_text))
                        is_toc_entry = has_page_num and (has_separators or has_numbering)
                        
                        if is_toc_entry:
                            toc_entries_found += 1
                            continue
                        
                        if toc_entries_found > 0:
                            if (len(next_text) > 3 and
                                (re.match(r'^\d+[.\s]', next_text) or 
                                 next_text.lower() in ['введение', 'introduction', 'глава', 'часть', 'раздел', 'заключение']) and
                                not (has_page_num and has_separators)):
                                next_header_pos = next_elem.get('xml_position', -1)
                                break
                        
                        if toc_entries_found == 0 and len(next_text) > 3:
                            if (re.match(r'^\d+[.\s]', next_text) or 
                                next_text.lower() in ['введение', 'introduction', 'глава', 'часть', 'раздел']):
                                break
                    
                    if toc_header_pos is not None:
                        break
            
            if toc_header_pos is not None:
                toc_from_paragraphs = _parse_toc_from_paragraphs(
                    all_xml_elements,
                    toc_header_pos,
                    next_header_pos if next_header_pos else 999999
                )
                if toc_from_paragraphs:
                    return toc_from_paragraphs
    
    except Exception as e:
        pass
    
    return toc_entries

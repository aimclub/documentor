"""
DOCX header processing.

Handles header detection, level determination, and matching with XML.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from tqdm import tqdm

from .header_finder import (
    build_header_rules,
    extract_paragraph_properties,
    find_header_in_xml,
    find_missing_headers_by_rules,
    _is_document_metadata,
    _is_list_header,
)

logger = logging.getLogger(__name__)


def _is_numbered_header(text: str) -> bool:
    """Check if header has explicit numbering."""
    text_stripped = text.strip()
    patterns = [
        r'^\d+\.\d+',  # "1.2" or "1.2Актуальность"
        r'^\d+\.',  # "1." or "1Анализ"
        r'^\d+[А-ЯЁA-Z]',  # "1Анализ" (without dot and space)
        r'^[IVX]+\.',  # "I.", "II."
        r'^[A-Z]\.\d+',  # "A.1"
        r'^[A-Z]\.',  # "A."
    ]
    for pattern in patterns:
        if re.match(pattern, text_stripped, re.IGNORECASE):
            return True
    return False


def _is_definition_pattern(text: str) -> bool:
    """Check if text matches definition pattern (e.g., 'Term:' or 'Term —')."""
    text_stripped = text.strip()
    if text_stripped.endswith(':') or text_stripped.endswith('—') or text_stripped.endswith('–'):
        return True
    return False


def _is_separator_line(text: str) -> bool:
    """Check if text is a separator line (e.g., '---', '___')."""
    text_stripped = text.strip()
    if len(text_stripped) <= 3 and all(c in '-_=*' for c in text_stripped):
        return True
    return False


def _is_list_item_pattern(text: str) -> bool:
    """
    Check if text matches list item pattern.
    
    Patterns:
    - Bullet lists: "* ", "- ", "• "
    - Numbered lists: "1. текст", "2. текст" (but NOT "1. Заголовок" with capital letter)
    """
    text_stripped = text.strip()
    
    # Bullet lists
    if text_stripped.startswith('* ') or text_stripped.startswith('- ') or text_stripped.startswith('• '):
        return True
    
    # Numbered lists: "1. текст" (lowercase after number) vs "1. Заголовок" (uppercase = header)
    # Check pattern "number. space text" where text starts with lowercase letter
    numbered_list_match = re.match(r'^(\d+)\.\s+([а-яёa-z])', text_stripped)
    if numbered_list_match:
        return True
    
    return False


class DocxHeaderProcessor:
    """
    Processor for DOCX header detection and processing.
    
    Handles:
    - Header detection from OCR
    - Matching headers with XML
    - Level determination
    - TOC validation
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize header processor.
        
        Args:
            config: Configuration dictionary.
        """
        self.config = config

    def process_headers(
        self,
        headers_with_text: List[Dict[str, Any]],
        all_xml_elements: List[Dict[str, Any]],
        toc_headers_map: Dict[str, Dict[str, Any]],
        docx_path: Path,
    ) -> List[Dict[str, Any]]:
        """
        Processes headers: matches with XML, determines levels, validates via TOC.
        
        Args:
            headers_with_text: List of headers with extracted text.
            all_xml_elements: List of all XML elements from DOCX.
            toc_headers_map: Dictionary mapping normalized titles to TOC info.
            docx_path: Path to DOCX file.
        
        Returns:
            List of header positions with metadata.
        """
        sorted_headers = sorted(
            headers_with_text,
            key=lambda h: (h.get('page_num', 0), h.get('bbox', [0, 0, 0, 0])[1] if h.get('bbox') else 0)
        )
        
        header_positions = []
        for header in tqdm(sorted_headers, desc="Processing headers", unit="header", leave=False):
            header_text = header.get('text', '')
            if not header_text:
                continue
            
            start_from = header_positions[-1]['xml_position'] + 1 if header_positions else 0
            xml_pos = find_header_in_xml(header_text, all_xml_elements, start_from)
            
            if xml_pos is None and start_from > 0:
                xml_pos = find_header_in_xml(header_text, all_xml_elements, 0)
            
            if xml_pos is not None:
                properties = extract_paragraph_properties(docx_path, xml_pos)
                is_heading_style = properties.get('is_heading_style', False)
                is_list_item = properties.get('is_list_item', False)
                
                text_stripped = header_text.strip()
                is_numbered_header = _is_numbered_header(text_stripped)
                
                # IMPORTANT: If this is a list item in XML (is_list_item = True),
                # and it's NOT a numbered header (like "1. Заголовок" with capital letter),
                # and it's NOT a heading style - this is definitely a list item, not a header
                if is_list_item:
                    # Check if this is a numbered header
                    # Numbered header: "1. Заголовок" or "1Заголовок" (capital letter after number)
                    # List item: "1. текст" or "1текст" (lowercase letter after number)
                    is_numbered_header_with_capital = bool(re.match(r'^\d+(?:\.\s*)?[А-ЯЁA-Z]', text_stripped))
                    
                    # If it's NOT a numbered header with capital letter and NOT a heading style - skip
                    if not is_numbered_header_with_capital and not is_heading_style:
                        continue
                
                if _is_definition_pattern(header_text) and not is_heading_style:
                    continue
                
                if _is_separator_line(header_text) and not is_heading_style:
                    continue
                
                # Check list pattern (bullet lists and numbered lists with lowercase letter)
                if _is_list_item_pattern(header_text) and not is_heading_style:
                    continue
                
                # Additional filters
                if _is_document_metadata(header_text) and not is_heading_style:
                    continue
                
                if _is_list_header(header_text) and not is_heading_style:
                    continue
                
                detected_level = self._determine_header_level(
                    header_text, properties, toc_headers_map, text_stripped
                )
                
                header_positions.append({
                    'ocr_header': header,
                    'xml_position': xml_pos,
                    'text': header_text,
                    'is_numbered_header': is_numbered_header,
                    'level': detected_level,
                    'from_toc': False
                })
            else:
                # Try to find via TOC
                normalized_header_text = re.sub(r'\s+', ' ', header_text.lower().strip())
                if normalized_header_text in toc_headers_map:
                    toc_info = toc_headers_map[normalized_header_text]
                    original_title = toc_info['original_title']
                    
                    xml_pos_from_toc = find_header_in_xml(original_title, all_xml_elements, 0)
                    
                    if xml_pos_from_toc is not None:
                        detected_level = toc_info['level']
                        
                        header_positions.append({
                            'ocr_header': None,
                            'xml_position': xml_pos_from_toc,
                            'text': original_title,
                            'is_numbered_header': _is_numbered_header(original_title.strip()),
                            'level': detected_level,
                            'from_toc': True
                        })
        
        # Validate via TOC - find missing headers
        if toc_headers_map:
            for normalized_title, toc_info in tqdm(toc_headers_map.items(), desc="Validating via TOC", unit="header", leave=False):
                found_texts = {re.sub(r'\s+', ' ', h.get('text', '').lower().strip()) for h in header_positions}
                if normalized_title not in found_texts:
                    original_title = toc_info['original_title']
                    level = toc_info['level']
                    
                    xml_pos_from_toc = find_header_in_xml(original_title, all_xml_elements, 0)
                    
                    if xml_pos_from_toc is not None:
                        found_positions = [h['xml_position'] for h in header_positions]
                        if xml_pos_from_toc not in found_positions:
                            properties = extract_paragraph_properties(docx_path, xml_pos_from_toc)
                            
                            if (not properties.get('is_list_item') or properties.get('is_heading_style')):
                                if not _is_definition_pattern(original_title) and not _is_separator_line(original_title):
                                    header_positions.append({
                                        'ocr_header': None,
                                        'xml_position': xml_pos_from_toc,
                                        'text': original_title,
                                        'is_numbered_header': _is_numbered_header(original_title.strip()),
                                        'level': level,
                                        'from_toc': True,
                                        'found_by_toc': True
                                    })
        
        header_positions.sort(key=lambda h: h['xml_position'])
        
        # Find missing headers using rules
        if header_positions:
            header_rules = build_header_rules(docx_path, header_positions)
            found_positions = [h['xml_position'] for h in header_positions]
            found_texts = {re.sub(r'\s+', ' ', h.get('text', '').lower().strip()) for h in header_positions}
            
            missing_headers = find_missing_headers_by_rules(
                docx_path,
                all_xml_elements,
                header_rules,
                found_positions,
                found_texts,
                header_positions
            )
            
            for missing_header in missing_headers:
                # Check level from TOC if available
                normalized_missing_text = re.sub(r'\s+', ' ', missing_header['text'].lower().strip())
                if normalized_missing_text in toc_headers_map:
                    toc_info = toc_headers_map[normalized_missing_text]
                    missing_header['level'] = toc_info['level']
                    missing_header['from_toc'] = True
                
                header_positions.append({
                    'ocr_header': None,
                    'xml_position': missing_header['xml_position'],
                    'text': missing_header['text'],
                    'level': missing_header['level'],
                    'found_by_rules': True,
                    'from_toc': normalized_missing_text in toc_headers_map if 'from_toc' in missing_header else False
                })
            
            header_positions.sort(key=lambda h: h['xml_position'])
        
        return header_positions

    def _determine_header_level(
        self,
        header_text: str,
        properties: Dict[str, Any],
        toc_headers_map: Dict[str, Dict[str, Any]],
        text_stripped: str,
    ) -> int:
        """
        Determines header level based on various factors.
        
        Priority order (same as hierarchy_builder._determine_header_level):
        1. TOC (if available)
        2. Style = number ("1", "2", "3") - IMPORTANT: priority over everything
        3. Heading style
        4. Numbering pattern
        
        Args:
            header_text: Header text.
            properties: Paragraph properties from XML.
            toc_headers_map: TOC headers mapping.
            text_stripped: Stripped header text.
        
        Returns:
            Header level (1-6).
        """
        normalized_header_text = re.sub(r'\s+', ' ', header_text.lower().strip())
        
        # Priority 1: Check TOC first (if available)
        if normalized_header_text in toc_headers_map:
            toc_info = toc_headers_map[normalized_header_text]
            return toc_info['level']
        
        # Priority 2: Style = number ("1", "2", "3") - IMPORTANT: priority over everything else
        # If style = number, this is definitely the header level, regardless of context
        style = properties.get('style')
        if style and style.isdigit():
            return int(style)
        
        # Priority 3: Heading style
        if properties.get('is_heading_style') and properties.get('level'):
            return properties.get('level')
        
        # Priority 4: Check numbering pattern
        # Support variants with and without space: "1Анализ", "1.1Актуальность", "1. Анализ", "1.1. Актуальность"
        match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.?\s*)?', text_stripped)
        if match:
            if match.group(3):
                return 3
            elif match.group(2):
                return 2
            elif match.group(1):
                return 1
        
        # Default to level 1
        return 1

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
)

logger = logging.getLogger(__name__)


def _is_numbered_header(text: str) -> bool:
    """Check if header has explicit numbering."""
    text_stripped = text.strip()
    patterns = [
        r'^\d+\.\d+',  # "1.2"
        r'^\d+\.',  # "1."
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
    """Check if text matches list item pattern."""
    text_stripped = text.strip()
    if text_stripped.startswith('* ') or text_stripped.startswith('- ') or text_stripped.startswith('• '):
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
                
                text_stripped = header_text.strip()
                is_numbered_header = _is_numbered_header(text_stripped)
                
                if properties.get('is_list_item') and not is_numbered_header and not is_heading_style:
                    continue
                
                if _is_definition_pattern(header_text) and not is_heading_style:
                    continue
                
                if _is_separator_line(header_text) and not is_heading_style:
                    continue
                
                if _is_list_item_pattern(header_text) and not is_heading_style:
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
        
        Args:
            header_text: Header text.
            properties: Paragraph properties from XML.
            toc_headers_map: TOC headers mapping.
            text_stripped: Stripped header text.
        
        Returns:
            Header level (1-6).
        """
        normalized_header_text = re.sub(r'\s+', ' ', header_text.lower().strip())
        
        # Check TOC first
        if normalized_header_text in toc_headers_map:
            toc_info = toc_headers_map[normalized_header_text]
            return toc_info['level']
        
        # Check heading style
        if properties.get('is_heading_style') and properties.get('level'):
            return properties.get('level')
        
        # Check numbering pattern
        match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text_stripped)
        if match:
            if match.group(3):
                return 3
            elif match.group(2):
                return 2
            elif match.group(1):
                return 1
        
        # Default to level 1
        return 1

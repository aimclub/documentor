"""
Finding captions for tables and images from OCR headers.

Uses Dots OCR headers and captions to match with tables and images from XML.
Also matches tables by comparing their structure (top row/headers) from OCR and XML.
"""

import logging
import re
from typing import Dict, List, Any, Optional
from html.parser import HTMLParser

try:
    import fitz
except ImportError:
    fitz = None

logger = logging.getLogger(__name__)


class TableHTMLParser(HTMLParser):
    """Parser for extracting table structure from HTML."""
    
    def __init__(self):
        super().__init__()
        self.rows = []
        self.current_row = []
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.current_cell_text = []
    
    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.in_table = True
        elif tag == 'tr' and self.in_table:
            self.in_row = True
            self.current_row = []
        elif tag in ['td', 'th'] and self.in_row:
            self.in_cell = True
            self.current_cell_text = []
    
    def handle_endtag(self, tag):
        if tag == 'table':
            self.in_table = False
        elif tag == 'tr' and self.in_row:
            self.in_row = False
            if self.current_row:
                self.rows.append(self.current_row)
        elif tag in ['td', 'th'] and self.in_cell:
            self.in_cell = False
            cell_text = ' '.join(self.current_cell_text).strip()
            self.current_row.append(cell_text)
    
    def handle_data(self, data):
        if self.in_cell:
            self.current_cell_text.append(data.strip())


def extract_table_structure_from_xml(docx_table: Dict[str, Any]) -> Optional[List[str]]:
    """
    Extracts table structure (top row/headers) from XML table.
    
    Args:
        docx_table: Table data from XML parser
    
    Returns:
        List of header cell texts (first row) or None
    """
    table_data = docx_table.get('data', [])
    if not table_data:
        return None
    
    # Get first row as headers
    first_row = table_data[0] if table_data else []
    # Keep all cells (including empty ones) to preserve structure
    # But filter out trailing empty cells
    headers = []
    last_non_empty = -1
    for i, cell in enumerate(first_row):
        cell_text = cell.strip() if cell else ""
        headers.append(cell_text)
        if cell_text:
            last_non_empty = i
    
    # Remove trailing empty cells
    if last_non_empty >= 0:
        headers = headers[:last_non_empty + 1]
    
    # Return only if we have at least some non-empty headers
    if any(h for h in headers):
        return headers
    
    return None


def extract_table_structure_from_ocr(
    ocr_table: Dict[str, Any],
    pdf_doc: Any,
    render_scale: float = 2.0
) -> Optional[List[str]]:
    """
    Extracts table structure (top row/headers) from OCR table.
    
    Tries multiple methods:
    1. Parse HTML from table_html metadata (if available from Dots OCR)
    2. Extract text from table bbox and try to parse structure
    
    Args:
        ocr_table: Table element from OCR
        pdf_doc: PyMuPDF document
        render_scale: Render scale used for rendering
    
    Returns:
        List of header cell texts (first row) or None
    """
    if fitz is None:
        return None
    
    # Method 1: Try to parse HTML if available
    table_html = ocr_table.get('table_html') or ocr_table.get('html')
    if table_html:
        try:
            parser = TableHTMLParser()
            parser.feed(table_html)
            if parser.rows:
                # Get first row as headers
                first_row = parser.rows[0]
                headers = [cell.strip() for cell in first_row if cell.strip()]
                if headers:
                    return headers
        except Exception as e:
            logger.debug(f"Error parsing table HTML: {e}")
    
    # Method 2: Extract text from table bbox and try to parse
    bbox = ocr_table.get('bbox', [])
    page_num = ocr_table.get('page_num', 0)
    
    if not bbox or len(bbox) < 4 or page_num >= len(pdf_doc):
        return None
    
    try:
        page = pdf_doc[page_num]
        # Convert coordinates to original PDF scale
        x1, y1, x2, y2 = (
            bbox[0] / render_scale,
            bbox[1] / render_scale,
            bbox[2] / render_scale,
            bbox[3] / render_scale,
        )
        rect = fitz.Rect(x1, y1, x2, y2)
        
        # Extract text from table area
        text = page.get_text("text", clip=rect).strip()
        
        if not text:
            return None
        
        # Try to parse first row from text
        # Split by newlines and take first few lines
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if not lines:
            return None
        
        # First line might be headers
        first_line = lines[0]
        # Try to split by tabs, multiple spaces, or common separators
        headers = re.split(r'\s{2,}|\t', first_line)
        headers = [h.strip() for h in headers if h.strip()]
        
        if headers:
            return headers
    
    except Exception as e:
        logger.debug(f"Error extracting table structure from OCR: {e}")
    
    return None


def compare_table_structures(
    xml_headers: List[str],
    ocr_headers: List[str],
    similarity_threshold: float = 0.7
) -> float:
    """
    Compares table structures (headers) from XML and OCR.
    
    Args:
        xml_headers: Headers from XML table
        ocr_headers: Headers from OCR table
        similarity_threshold: Minimum similarity to consider match
    
    Returns:
        Similarity score (0.0 to 1.0)
    """
    if not xml_headers or not ocr_headers:
        return 0.0
    
    # Normalize headers: lowercase, remove extra spaces
    xml_normalized = [re.sub(r'\s+', ' ', h.lower().strip()) for h in xml_headers]
    ocr_normalized = [re.sub(r'\s+', ' ', h.lower().strip()) for h in ocr_headers]
    
    # If lengths are very different, unlikely to match
    if abs(len(xml_normalized) - len(ocr_normalized)) > max(len(xml_normalized), len(ocr_normalized)) * 0.3:
        return 0.0
    
    # Compare headers
    matches = 0
    total = max(len(xml_normalized), len(ocr_normalized))
    
    # Try to match headers (allowing for some reordering)
    used_ocr_indices = set()
    for xml_h in xml_normalized:
        best_match_score = 0.0
        best_match_idx = -1
        
        for i, ocr_h in enumerate(ocr_normalized):
            if i in used_ocr_indices:
                continue
            
            # Exact match
            if xml_h == ocr_h:
                best_match_score = 1.0
                best_match_idx = i
                break
            
            # Partial match (one contains the other)
            if xml_h in ocr_h or ocr_h in xml_h:
                score = min(len(xml_h), len(ocr_h)) / max(len(xml_h), len(ocr_h))
                if score > best_match_score:
                    best_match_score = score
                    best_match_idx = i
            
            # Word overlap
            xml_words = set(xml_h.split())
            ocr_words = set(ocr_h.split())
            if xml_words and ocr_words:
                overlap = len(xml_words & ocr_words) / len(xml_words | ocr_words)
                if overlap > best_match_score:
                    best_match_score = overlap
                    best_match_idx = i
        
        if best_match_score >= similarity_threshold and best_match_idx >= 0:
            matches += best_match_score
            used_ocr_indices.add(best_match_idx)
    
    similarity = matches / total if total > 0 else 0.0
    return similarity


def match_table_by_structure(
    docx_table: Dict[str, Any],
    ocr_tables: List[Dict[str, Any]],
    pdf_doc: Any,
    render_scale: float = 2.0,
    similarity_threshold: float = 0.7
) -> Optional[Dict[str, Any]]:
    """
    Matches DOCX table with OCR table by comparing their structures (top row/headers).
    
    Args:
        docx_table: Table from DOCX XML
        ocr_tables: List of tables from OCR
        pdf_doc: PyMuPDF document
        render_scale: Render scale used for rendering
        similarity_threshold: Minimum similarity to consider match
    
    Returns:
        Matched OCR table info or None
    """
    # Extract structure from XML table
    xml_headers = extract_table_structure_from_xml(docx_table)
    if not xml_headers:
        return None
    
    best_match = None
    best_similarity = 0.0
    
    # Compare with all OCR tables
    for ocr_table in ocr_tables:
        ocr_headers = extract_table_structure_from_ocr(ocr_table, pdf_doc, render_scale)
        if not ocr_headers:
            continue
        
        similarity = compare_table_structures(xml_headers, ocr_headers, similarity_threshold)
        
        if similarity > best_similarity and similarity >= similarity_threshold:
            best_similarity = similarity
            best_match = {
                'ocr_table': ocr_table,
                'similarity': similarity,
                'xml_headers': xml_headers,
                'ocr_headers': ocr_headers
            }
    
    return best_match


def find_table_caption_in_ocr_headers(
    ocr_headers: List[Dict[str, Any]],
    ocr_captions: List[Dict[str, Any]],
    table_bbox: List[float],
    table_page: int,
    pdf_doc: Any,
    element_text: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Finds table caption in Section-header or Caption from OCR.
    
    Args:
        ocr_headers: List of headers from OCR
        ocr_captions: List of captions from OCR
        table_bbox: Table coordinates
        table_page: Table page number
        pdf_doc: PyMuPDF document
        element_text: Optional pre-extracted text from element (if available)
    
    Returns:
        Caption information or None
    """
    if fitz is None:
        logger.warning("PyMuPDF not available, cannot find table captions")
        return None
    
    if not table_bbox or len(table_bbox) < 4:
        return None
    
    # First search in Caption (more accurate), then in headers
    all_candidates = ocr_captions + ocr_headers
    
    # Find nearest Caption/Section-header before table
    matching_element = None
    min_distance = float('inf')
    
    for candidate in all_candidates:
        candidate_page = candidate.get('page_num')
        if candidate_page <= table_page and candidate_page >= max(0, table_page - 2):
            candidate_bbox = candidate.get('bbox', [])
            if candidate_bbox and len(candidate_bbox) >= 4:
                if candidate_page == table_page:
                    # On same page - check position
                    if candidate_bbox[3] < table_bbox[1]:  # Element above table
                        # Calculate distance
                        distance = table_bbox[1] - candidate_bbox[3]
                        if distance < min_distance:
                            min_distance = distance
                            matching_element = candidate
                else:
                    # On previous page - lower priority
                    if matching_element is None or matching_element.get('page_num') == table_page:
                        matching_element = candidate
    
    if matching_element:
        try:
            element_page_num = matching_element.get('page_num')
            page = pdf_doc[element_page_num]
            element_bbox = matching_element.get('bbox', [])
            
            if element_bbox and len(element_bbox) >= 4:
                # Use pre-extracted text if available, otherwise extract from PDF
                if element_text:
                    caption_text = element_text
                else:
                    rect = fitz.Rect(element_bbox)
                    caption_text = page.get_text("text", clip=rect).strip()
                    
                    # If text is empty, expand area
                    if not caption_text:
                        expanded_rect = fitz.Rect(
                            max(0, element_bbox[0] - 50),
                            max(0, element_bbox[1] - 20),
                            min(page.rect.width, element_bbox[2] + 50),
                            min(page.rect.height, element_bbox[3] + 20)
                        )
                        caption_text = page.get_text("text", clip=expanded_rect).strip()
                
                # Search for table mention
                table_match = re.search(r'(таблица|table)\s*(\d+)', caption_text, re.IGNORECASE)
                if table_match:
                    table_number = int(table_match.group(2))
                    return {
                        'text': caption_text,
                        'table_number': table_number,
                        'bbox': element_bbox,
                        'page': element_page_num,
                        'type': 'caption' if matching_element in ocr_captions else 'header'
                    }
        except Exception as e:
            logger.debug(f"Error extracting table caption: {e}")
    
    return None


def find_image_caption_in_ocr_headers(
    ocr_headers: List[Dict[str, Any]],
    ocr_captions: List[Dict[str, Any]],
    image_bbox: List[float],
    image_page: int,
    pdf_doc: Any,
    element_text: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Finds image caption in Section-header or Caption from OCR.
    
    Args:
        ocr_headers: List of headers from OCR
        ocr_captions: List of captions from OCR
        image_bbox: Image coordinates
        image_page: Image page number
        pdf_doc: PyMuPDF document
        element_text: Optional pre-extracted text from element (if available)
    
    Returns:
        Caption information or None
    """
    if fitz is None:
        logger.warning("PyMuPDF not available, cannot find image captions")
        return None
    
    if not image_bbox or len(image_bbox) < 4:
        return None
    
    # First search in Caption (more accurate), then in headers
    all_candidates = ocr_captions + ocr_headers
    
    # Find nearest Caption/Section-header before/after image
    matching_element = None
    min_distance = float('inf')
    
    for candidate in all_candidates:
        candidate_page = candidate.get('page_num')
        if candidate_page == image_page:
            candidate_bbox = candidate.get('bbox', [])
            if candidate_bbox and len(candidate_bbox) >= 4:
                # Element can be above or below image
                if candidate_bbox[3] < image_bbox[1]:  # Above image
                    distance = image_bbox[1] - candidate_bbox[3]
                elif candidate_bbox[1] > image_bbox[3]:  # Below image
                    distance = candidate_bbox[1] - image_bbox[3]
                else:
                    continue  # Intersects - skip
                
                if distance < min_distance:
                    min_distance = distance
                    matching_element = candidate
    
    if matching_element:
        try:
            element_page_num = matching_element.get('page_num')
            page = pdf_doc[element_page_num]
            element_bbox = matching_element.get('bbox', [])
            
            if element_bbox and len(element_bbox) >= 4:
                # Use pre-extracted text if available, otherwise extract from PDF
                if element_text:
                    caption_text = element_text
                else:
                    rect = fitz.Rect(element_bbox)
                    caption_text = page.get_text("text", clip=rect).strip()
                    
                    if not caption_text:
                        expanded_rect = fitz.Rect(
                            max(0, element_bbox[0] - 50),
                            max(0, element_bbox[1] - 20),
                            min(page.rect.width, element_bbox[2] + 50),
                            min(page.rect.height, element_bbox[3] + 20)
                        )
                        caption_text = page.get_text("text", clip=expanded_rect).strip()
                
                # Search for figure/image mention
                if re.search(r'(рисунок|рис\.|figure|image|изображение)', caption_text, re.IGNORECASE):
                    # Try to extract number
                    number_match = re.search(r'(\d+)', caption_text)
                    image_number = int(number_match.group(1)) if number_match else None
                    
                    return {
                        'text': caption_text,
                        'image_number': image_number,
                        'bbox': element_bbox,
                        'page': element_page_num,
                        'type': 'caption' if matching_element in ocr_captions else 'header'
                    }
        except Exception as e:
            logger.debug(f"Error extracting image caption: {e}")
    
    return None


def match_table_with_caption(
    docx_table: Dict[str, Any],
    ocr_headers: List[Dict[str, Any]],
    ocr_captions: List[Dict[str, Any]],
    pdf_doc: Any,
    all_xml_elements: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Matches DOCX table with caption from OCR headers.
    
    Strategy:
    1. Check if table has caption in XML (before table position)
    2. If found, search for matching OCR header/caption with same text
    3. If not found in XML, search OCR headers/captions near table position
    
    Args:
        docx_table: Table from DOCX XML
        ocr_headers: List of headers from OCR
        ocr_captions: List of captions from OCR
        pdf_doc: PyMuPDF document
        all_xml_elements: All XML elements for context
    
    Returns:
        Matched caption info or None
    """
    if fitz is None:
        return None
    
    table_xml_pos = docx_table.get('xml_position')
    if table_xml_pos is None:
        return None
    
    # First, try to find caption in XML before table
    caption_text = None
    caption_xml_pos = None
    
    # Search up to 5 elements before table
    for i in range(max(0, table_xml_pos - 5), table_xml_pos):
        if i < len(all_xml_elements):
            elem = all_xml_elements[i]
            if elem.get('type') == 'paragraph':
                text = elem.get('text', '').strip()
                text_lower = text.lower()
                
                # Check if it's a table caption pattern
                if re.search(r'(таблица|table)\s*\d+', text_lower, re.IGNORECASE):
                    caption_text = text
                    caption_xml_pos = i
                    break
    
    # If we found caption in XML, try to match it with OCR
    if caption_text:
        # Search for matching OCR header/caption with similar text
        all_candidates = ocr_captions + ocr_headers
        
        for candidate in all_candidates:
            candidate_text = candidate.get('text', '').strip()
            if candidate_text:
                # Normalize texts for comparison
                normalized_caption = re.sub(r'\s+', ' ', caption_text.lower().strip())
                normalized_candidate = re.sub(r'\s+', ' ', candidate_text.lower().strip())
                
                # Check if texts are similar (exact match or contains key parts)
                if normalized_caption == normalized_candidate:
                    # Exact match - return it
                    table_match = re.search(r'(таблица|table)\s*(\d+)', candidate_text, re.IGNORECASE)
                    if table_match:
                        return {
                            'text': candidate_text,
                            'table_number': int(table_match.group(2)),
                            'bbox': candidate.get('bbox', []),
                            'page': candidate.get('page_num', 0),
                            'type': 'caption' if candidate in ocr_captions else 'header',
                            'matched_from_xml': True
                        }
                elif normalized_caption in normalized_candidate or normalized_candidate in normalized_caption:
                    # Partial match - might be the same caption
                    table_match = re.search(r'(таблица|table)\s*(\d+)', candidate_text, re.IGNORECASE)
                    if table_match:
                        return {
                            'text': candidate_text,
                            'table_number': int(table_match.group(2)),
                            'bbox': candidate.get('bbox', []),
                            'page': candidate.get('page_num', 0),
                            'type': 'caption' if candidate in ocr_captions else 'header',
                            'matched_from_xml': True
                        }
    
    # If no match found via XML, try to find caption by position (bbox-based)
    # This requires table bbox from OCR, which we might not have here
    # So we return None and let the caller handle it
    
    return None

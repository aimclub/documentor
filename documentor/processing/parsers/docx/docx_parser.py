"""
Parser for DOCX documents.

Uses combined approach:
1. DOTS OCR for detecting structural elements (headers, captions)
2. PyMuPDF for extracting text from PDF by bbox (faster and more accurate for text PDFs)
3. XML parsing for extracting full content (text, tables, images)
4. Table of Contents parsing for validation and improving results
5. Building complete document hierarchy
6. Automatic detection of scanned documents and processing via PdfParser with OCR
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional
from io import BytesIO

import fitz
import yaml
from langchain_core.documents import Document
from PIL import Image
from tqdm import tqdm

from ....domain import DocumentFormat, Element, ElementType, ParsedDocument
from ....exceptions import ParsingError
from ..base import BaseParser
from ..pdf.pdf_parser import PdfParser
from ..pdf.ocr.dots_ocr_client import process_layout_detection
from ..pdf.ocr.page_renderer import PdfPageRenderer
from .converter import convert_docx_to_pdf
from .xml_parser import DocxXmlParser
from .toc_parser import parse_toc_from_docx
from .header_finder import find_header_in_xml, build_header_rules, extract_paragraph_properties
from .hierarchy_builder import build_hierarchy

logger = logging.getLogger(__name__)


def _extract_text_from_pdf_by_bbox(
    ocr_elements: List[Dict[str, Any]],
    pdf_doc: fitz.Document,
    render_scale: float = 2.0
) -> List[Dict[str, Any]]:
    """Extracts text from PDF by bbox found via DOTS OCR, using PyMuPDF."""
    results = []
    
    for element in tqdm(ocr_elements, desc="Extracting text from PDF", unit="element", leave=False):
        category = element.get("category", "")
        bbox = element.get("bbox", [])
        page_num = element.get("page_num", 0)
        
        if category not in ["Section-header", "Caption"]:
            continue
        
        if not bbox or len(bbox) < 4:
            continue
        
        if page_num >= len(pdf_doc):
            continue
        
        try:
            page = pdf_doc[page_num]
            page_rect = page.rect
            
            # Convert bbox from image coordinates to PDF page coordinates
            # bbox from DOTS OCR is in image coordinates, rendered with render_scale
            # So coordinates need to be divided by render_scale
            x1, y1, x2, y2 = bbox
            
            # Scale coordinates back to PDF page coordinates
            pdf_x1 = x1 / render_scale
            pdf_y1 = y1 / render_scale
            pdf_x2 = x2 / render_scale
            pdf_y2 = y2 / render_scale
            
            # Create rectangle for text extraction in PDF coordinates
            rect = fitz.Rect(pdf_x1, pdf_y1, pdf_x2, pdf_y2)
            
            # Extract text from rectangle
            text = page.get_textbox(rect)
            
            # If get_textbox didn't work, try another method
            if not text or len(text.strip()) < 2:
                # Try to get all page text and find text in the required area
                text_dict = page.get_text("dict")
                text_parts = []
                
                for block in text_dict.get("blocks", []):
                    if "lines" not in block:
                        continue
                    for line in block["lines"]:
                        for span in line.get("spans", []):
                            span_bbox = span.get("bbox", [])
                            if len(span_bbox) >= 4:
                                # Check intersection of span bbox with our bbox
                                span_rect = fitz.Rect(span_bbox)
                                if rect.intersects(span_rect):
                                    text_parts.append(span.get("text", ""))
                
                text = " ".join(text_parts)
            
            if text and text.strip():
                element_result = {
                    "category": category,
                    "bbox": bbox,
                    "page_num": page_num,
                    "text": text.strip(),
                    "text_length": len(text.strip())
                }
                results.append(element_result)
        except Exception as e:
            logger.debug(f"Error extracting text from PDF: {e}")
            continue
    
    return results


def _is_numbered_header(text: str) -> bool:
    """Checks if text is a numbered header."""
    text_stripped = text.strip()
    patterns = [
        r'^\d+\.\s+[А-ЯЁA-Z]',
        r'^\d+\.\d+\.\s+[А-ЯЁA-Z]',
        r'^\d+\.\d+\.\d+\.\s+[А-ЯЁA-Z]',
    ]
    return any(re.match(pattern, text_stripped) for pattern in patterns)


def _is_definition_pattern(text: str) -> bool:
    """Checks if text is a definition."""
    text_stripped = text.strip()
    if not text_stripped or re.match(r'^\d+', text_stripped):
        return False
    
    dash_patterns = [' – ', ' — ', ' - ']
    for dash in dash_patterns:
        idx = text_stripped.find(dash)
        if idx > 0:
            term = text_stripped[:idx].strip()
            definition = text_stripped[idx + len(dash):].strip()
            term_words = len(term.split())
            if 1 <= term_words <= 5 and len(definition) > 0:
                return True
    
    return False


def _is_separator_line(text: str) -> bool:
    """Checks if text is a separator line."""
    text_stripped = text.strip()
    if not text_stripped or len(text_stripped) < 3:
        return False
    
    separator_chars = {'.', '–', '—', '-', '_', '=', '…', ' '}
    non_separator_chars = set(text_stripped) - separator_chars
    
    if len(non_separator_chars) == 0:
        return True
    
    if re.match(r'^[.\-–—_=…\s]+[\d]+$', text_stripped):
        return True
    
    return False


def _is_list_item_pattern(text: str) -> bool:
    """Checks if text is a list item."""
    text_stripped = text.strip()
    if not text_stripped:
        return False
    
    list_patterns = [
        r'^[а-яёa-z]\)\s+',
        r'^[А-ЯЁA-Z]\)\s+',
        r'^\d+\)\s+',
        r'^[-•·▪▫]\s+',
    ]
    
    for pattern in list_patterns:
        if re.match(pattern, text_stripped, re.IGNORECASE):
            return True
    
    if text_stripped.startswith(('- ', '• ', '· ', '▪ ', '▫ ')):
        return True
    
    return False


def _check_docx_text_content(docx_path: Path) -> Dict[str, Any]:
    """
    Checks for text content in DOCX document.
    
    Returns:
        Dictionary with information about text and images:
        - has_text: bool - whether text exists
        - text_length: int - total text length
        - text_paragraphs: int - number of text paragraphs
        - images_count: int - number of images
        - is_scanned: bool - whether document is scanned
    """
    xml_parser = DocxXmlParser(docx_path)
    all_elements = xml_parser.extract_all_elements()
    images = xml_parser.extract_images()
    
    text_length = 0
    text_paragraphs = 0
    
    for elem in all_elements:
        text = elem.get('text', '').strip()
        if text and len(text) > 10:
            text_length += len(text)
            text_paragraphs += 1
    
    images_count = len(images)
    has_text = text_length > 100
    
    is_scanned = False
    if not has_text or (images_count > 0 and text_length < 500 and images_count > text_paragraphs * 2):
        is_scanned = True
    
    return {
        'has_text': has_text,
        'text_length': text_length,
        'text_paragraphs': text_paragraphs,
        'images_count': images_count,
        'is_scanned': is_scanned
    }


class DocxParser(BaseParser):
    """Parser for DOCX documents."""

    format = DocumentFormat.DOCX

    def __init__(self) -> None:
        """Initialize parser."""
        super().__init__()
        self._config: Optional[Dict[str, Any]] = None
        self._load_config()

    def _load_config(self) -> None:
        """Loads configuration from docx_config.yaml."""
        config_path = Path(__file__).parent.parent.parent.parent / "config" / "docx_config.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                self._config = config.get("docx_parser", {})
        else:
            self._config = {}
            logger.warning(f"Configuration file not found: {config_path}, using default values")

    def _get_config(self, key: str, default: Any = None) -> Any:
        """Gets value from configuration."""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value if value is not None else default

    def parse(self, document: Document) -> ParsedDocument:
        """
        Parse DOCX document.

        Args:
            document: LangChain Document with DOCX content.

        Returns:
            ParsedDocument: Structured document representation.

        Raises:
            ValidationError: If input data is invalid.
            UnsupportedFormatError: If document format is not supported.
            ParsingError: If parsing error occurred.
        """
        self._validate_input(document)

        source = self.get_source(document)
        self._log_parsing_start(source)

        try:
            docx_path = Path(source)
            if not docx_path.exists():
                raise ParsingError(f"DOCX file not found: {source}", source=source)

            content_info = _check_docx_text_content(docx_path)
            
            if content_info['is_scanned']:
                logger.info(
                    f"DOCX document identified as scanned "
                    f"(text: {content_info['text_length']} characters, "
                    f"images: {content_info['images_count']}). "
                    f"Using PdfParser with OCR."
                )
                
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_pdf_path = Path(temp_dir) / "temp.pdf"
                    convert_docx_to_pdf(docx_path, temp_pdf_path)
                    
                    pdf_document = Document(page_content="", metadata={"source": str(temp_pdf_path)})
                    pdf_parser = PdfParser()
                    parsed_document = pdf_parser.parse(pdf_document)
                    
                    parsed_document.source = source
                    parsed_document.format = DocumentFormat.DOCX
                    parsed_document.metadata.update({
                        'parser': 'docx',
                        'original_format': 'DOCX',
                        'processing_method': 'scanned_docx_to_pdf_ocr',
                        'content_info': content_info,
                    })
                    
                    self._validate_parsed_document(parsed_document)
                    self._log_parsing_end(source, len(parsed_document.elements))
                    
                    return parsed_document

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_pdf_path = Path(temp_dir) / "temp.pdf"
                
                convert_docx_to_pdf(docx_path, temp_pdf_path)
                
                render_scale = self._get_config("layout_detection.render_scale", 2.0)
                renderer = PdfPageRenderer(render_scale=render_scale)
                pdf_doc = fitz.open(str(temp_pdf_path))
                
                try:
                    total_pages = len(pdf_doc)
                    
                    ocr_elements = []
                    page_images = {}
                    
                    for page_num in tqdm(range(total_pages), desc="Processing PDF pages", unit="page", leave=False):
                        page_image = renderer.render_page(temp_pdf_path, page_num)
                        if page_image is None:
                            continue
                        
                        page_images[page_num] = page_image
                        
                        try:
                            layout_cells, _, success = process_layout_detection(
                                image=page_image,
                                origin_image=page_image
                            )
                            
                            if success and layout_cells:
                                for element in layout_cells:
                                    element["page_num"] = page_num
                                    ocr_elements.append(element)
                        except Exception:
                            continue
                    
                    section_headers = [e for e in ocr_elements if e.get("category") == "Section-header"]
                    captions = [e for e in ocr_elements if e.get("category") == "Caption"]
                    
                    elements_to_extract = section_headers + captions
                    ocr_results = _extract_text_from_pdf_by_bbox(elements_to_extract, pdf_doc, render_scale)
                    
                    headers_with_text = [r for r in ocr_results if r.get("category") == "Section-header"]
                    captions_with_text = [r for r in ocr_results if r.get("category") == "Caption"]
                    
                    xml_parser = DocxXmlParser(docx_path)
                    all_xml_elements = xml_parser.extract_all_elements()
                    docx_tables = xml_parser.extract_tables()
                    docx_images = xml_parser.extract_images()
                    
                    toc_entries = parse_toc_from_docx(docx_path, all_xml_elements)
                    toc_headers_map = {}
                    if toc_entries:
                        for toc_entry in tqdm(toc_entries, desc="Parsing table of contents", unit="entry", leave=False):
                            title = toc_entry.get('title', '').strip()
                            if title:
                                normalized_title = re.sub(r'\s+', ' ', title.lower().strip())
                                level = toc_entry.get('level', 1)
                                toc_headers_map[normalized_title] = {
                                    'level': level,
                                    'page': toc_entry.get('page'),
                                    'original_title': title
                                }
                    
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
                            
                            detected_level = None
                            normalized_header_text = re.sub(r'\s+', ' ', header_text.lower().strip())
                            if normalized_header_text in toc_headers_map:
                                toc_info = toc_headers_map[normalized_header_text]
                                detected_level = toc_info['level']
                            elif is_heading_style and properties.get('level'):
                                detected_level = properties.get('level')
                            else:
                                match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', text_stripped)
                                if match:
                                    if match.group(3):
                                        detected_level = 3
                                    elif match.group(2):
                                        detected_level = 2
                                    elif match.group(1):
                                        detected_level = 1
                            
                            header_positions.append({
                                'ocr_header': header,
                                'xml_position': xml_pos,
                                'text': header_text,
                                'is_numbered_header': is_numbered_header,
                                'level': detected_level,
                                'from_toc': normalized_header_text in toc_headers_map
                            })
                        else:
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
                    
                    max_text_block_size = self._get_config("hierarchy.max_text_block_size", 3000)
                    max_paragraphs_per_block = self._get_config("hierarchy.max_paragraphs_per_block", 10)
                    
                    elements = build_hierarchy(
                        header_positions,
                        all_xml_elements,
                        docx_tables,
                        docx_images,
                        docx_path,
                        self._id_generator,
                        max_text_block_size=max_text_block_size,
                        max_paragraphs_per_block=max_paragraphs_per_block
                    )
                    
                    parsed_document = ParsedDocument(
                        source=source,
                        format=self.format,
                        elements=elements,
                        metadata={
                            "parser": "docx",
                            "status": "completed",
                            "processing_method": "layout_based",
                            "total_pages": total_pages,
                            "elements_count": len(elements),
                            "headers_count": len([e for e in elements if e.type.name.startswith("HEADER")]),
                            "tables_count": len([e for e in elements if e.type == ElementType.TABLE]),
                            "images_count": len([e for e in elements if e.type == ElementType.IMAGE]),
                        }
                    )

                    self._validate_parsed_document(parsed_document)
                    self._log_parsing_end(source, len(elements))

                    return parsed_document
                finally:
                    pdf_doc.close()

        except Exception as e:
            error_msg = f"Error parsing DOCX document (source: {source})"
            logger.error(f"{error_msg}. Original error: {e}", exc_info=True)
            raise ParsingError(error_msg, source=source, original_error=e) from e
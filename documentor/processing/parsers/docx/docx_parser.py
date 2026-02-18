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
from pathlib import Path
from typing import Dict, List, Any, Optional

import tempfile
from langchain_core.documents import Document
from tqdm import tqdm

try:
    import fitz
except ImportError:
    fitz = None

from ....domain import DocumentFormat, Element, ElementType, ParsedDocument
from ....exceptions import ParsingError
from ....utils.config_loader import ConfigLoader
from ..base import BaseParser
from ..pdf.pdf_parser import PdfParser
from .converter_wrapper import DocxConverter
from .header_processor import DocxHeaderProcessor
from .layout_detector import DocxLayoutDetector
from .xml_parser import DocxXmlParser
from .toc_parser import parse_toc_from_docx
from .hierarchy_builder import build_hierarchy
from .caption_finder import (
    match_table_with_caption,
    find_table_caption_in_ocr_headers,
    find_image_caption_in_ocr_headers,
    match_table_by_structure
)

logger = logging.getLogger(__name__)


def _check_docx_text_content(
    docx_path: Path,
    min_text_length: int = 100,
    min_text_for_non_scanned: int = 500,
    images_to_text_ratio: float = 2.0
) -> Dict[str, Any]:
    """
    Checks for text content in DOCX document.
    
    Args:
        docx_path: Path to DOCX file
        min_text_length: Minimum text length to determine text presence
        min_text_for_non_scanned: Minimum text length for non-scanned document
        images_to_text_ratio: If images count > text_paragraphs * ratio, document is considered scanned
    
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
    tables = xml_parser.extract_tables()
    
    text_length = 0
    text_paragraphs = 0
    
    # Count text from paragraphs
    for elem in all_elements:
        text = elem.get('text', '').strip()
        if text and len(text) > 10:
            text_length += len(text)
            text_paragraphs += 1
    
    # Count text from tables
    for table in tables:
        rows = table.get('rows', [])
        for row in rows:
            cells = row.get('cells', [])
            for cell in cells:
                cell_text = cell.get('text', '').strip()
                if cell_text:
                    text_length += len(cell_text)
                    # Count table rows as text paragraphs for ratio calculation
                    if len(cell_text) > 10:
                        text_paragraphs += 1
    
    images_count = len(images)
    tables_count = len(tables)
    has_text = text_length > min_text_length
    
    # Documents with tables should not be considered scanned, as tables contain structured text
    is_scanned = False
    if tables_count > 0:
        # If document has tables, it's likely not scanned (tables contain structured text)
        is_scanned = False
    elif not has_text or (images_count > 0 and text_length < min_text_for_non_scanned and images_count > text_paragraphs * images_to_text_ratio):
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
        
        # Initialize specialized processors
        self.converter = DocxConverter()
        self.layout_detector = DocxLayoutDetector(config=self._config)
        self.header_processor = DocxHeaderProcessor(config=self._config)

    def _load_config(self) -> None:
        """Loads configuration from config.yaml."""
        self._config = ConfigLoader.load_config("docx_parser")

    def _get_config(self, key: str, default: Any = None) -> Any:
        """Gets value from configuration."""
        return ConfigLoader.get_config_value(self._config, key, default)

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
        
        # Reset ID generator for each new document
        self._reset_id_generator()

        source = self.get_source(document)
        self._log_parsing_start(source)

        try:
            docx_path = Path(source)
            if not docx_path.exists():
                raise ParsingError(f"DOCX file not found: {source}", source=source)

            # Get scanned detection parameters from config
            min_text_length = self._get_config("scanned_detection.min_text_length", 100)
            min_text_for_non_scanned = self._get_config("scanned_detection.min_text_for_non_scanned", 500)
            images_to_text_ratio = self._get_config("scanned_detection.images_to_text_ratio", 2.0)
            
            content_info = _check_docx_text_content(
                docx_path,
                min_text_length=min_text_length,
                min_text_for_non_scanned=min_text_for_non_scanned,
                images_to_text_ratio=images_to_text_ratio
            )
            
            if content_info['is_scanned']:
                logger.info(
                    f"DOCX document identified as scanned "
                    f"(text: {content_info['text_length']} characters, "
                    f"images: {content_info['images_count']}). "
                    f"Using PdfParser with OCR."
                )
                
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_pdf_path = Path(temp_dir) / "temp.pdf"
                    try:
                        self.converter.convert_to_pdf(docx_path, temp_pdf_path)
                        
                        # Conversion successful, use PDF parser
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
                    except Exception as e:
                        logger.warning(
                            f"Failed to convert DOCX to PDF for OCR processing: {e}. "
                            f"Falling back to regular DOCX parsing."
                        )
                        # Fallback to regular parsing if conversion fails
                        # Continue with regular parsing below

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_pdf_path = Path(temp_dir) / "temp.pdf"
                
                self.converter.convert_to_pdf(docx_path, temp_pdf_path)
                
                # Layout detection
                ocr_elements, page_images = self.layout_detector.detect_layout_for_all_pages(temp_pdf_path)
                
                pdf_doc = fitz.open(str(temp_pdf_path))
                try:
                    total_pages = len(pdf_doc)
                    
                    render_scale = self._get_config("layout_detection.render_scale", 2.0)
                    
                    section_headers = [e for e in ocr_elements if e.get("category") == "Section-header"]
                    captions = [e for e in ocr_elements if e.get("category") == "Caption"]
                    
                    elements_to_extract = section_headers + captions
                    ocr_results = self.layout_detector.extract_text_from_pdf_by_bbox(
                        elements_to_extract, pdf_doc, render_scale
                    )
                    
                    headers_with_text = [r for r in ocr_results if r.get("category") == "Section-header"]
                    captions_with_text = [r for r in ocr_results if r.get("category") == "Caption"]
                    
                    xml_parser = DocxXmlParser(docx_path)
                    all_xml_elements = xml_parser.extract_all_elements()
                    docx_tables = xml_parser.extract_tables()
                    docx_images = xml_parser.extract_images()
                    
                    # Match tables by comparing their structure (top row/headers) from OCR and XML
                    # This is the primary method: compare table structures to identify same tables
                    if fitz is not None:
                        # Find OCR tables
                        ocr_tables = [e for e in ocr_elements if e.get("category") == "Table"]
                        
                        # Match each DOCX table with OCR table by structure comparison
                        for docx_table in docx_tables:
                            # Match by structure (top row/headers comparison)
                            structure_match = match_table_by_structure(
                                docx_table,
                                ocr_tables,
                                pdf_doc,
                                render_scale=render_scale,
                                similarity_threshold=0.7
                            )
                            
                            if structure_match:
                                # Found matching table by structure
                                ocr_table = structure_match['ocr_table']
                                similarity = structure_match['similarity']
                                
                                # Store OCR table info for reference
                                docx_table['ocr_match'] = {
                                    'ocr_table_bbox': ocr_table.get('bbox', []),
                                    'ocr_table_page': ocr_table.get('page_num', 0),
                                    'similarity': similarity,
                                    'xml_headers': structure_match['xml_headers'],
                                    'ocr_headers': structure_match['ocr_headers']
                                }
                                
                                logger.debug(
                                    f"Matched table {docx_table.get('index')} with OCR table "
                                    f"(similarity: {similarity:.2f}, page: {ocr_table.get('page_num', 0) + 1})"
                                )
                                
                                # Also try to find caption for this matched table
                                ocr_table_bbox = ocr_table.get('bbox', [])
                                ocr_table_page = ocr_table.get('page_num', 0)
                                
                                if ocr_table_bbox and len(ocr_table_bbox) >= 4:
                                    caption_info = find_table_caption_in_ocr_headers(
                                        headers_with_text,
                                        captions_with_text,
                                        ocr_table_bbox,
                                        ocr_table_page,
                                        pdf_doc
                                    )
                                    
                                    if caption_info:
                                        if 'captions' not in docx_table:
                                            docx_table['captions'] = []
                                        docx_table['captions'].append(caption_info)
                                        logger.debug(f"Found caption for table {docx_table.get('index')}: {caption_info.get('text', '')[:50]}")
                            else:
                                # Fallback: try to match via caption if structure matching failed
                                caption_info = match_table_with_caption(
                                    docx_table,
                                    headers_with_text,
                                    captions_with_text,
                                    pdf_doc,
                                    all_xml_elements
                                )
                                
                                if caption_info:
                                    if 'captions' not in docx_table:
                                        docx_table['captions'] = []
                                    docx_table['captions'].append(caption_info)
                                    logger.debug(f"Matched table {docx_table.get('index')} with caption: {caption_info.get('text', '')[:50]}")
                        
                        # Match images with captions
                        ocr_images = [e for e in ocr_elements if e.get("category") == "Picture"]
                        
                        for docx_image in docx_images:
                            # Try to find via OCR image bbox
                            for ocr_image in ocr_images:
                                ocr_image_bbox = ocr_image.get('bbox', [])
                                ocr_image_page = ocr_image.get('page_num', 0)
                                
                                if ocr_image_bbox and len(ocr_image_bbox) >= 4:
                                    caption_info = find_image_caption_in_ocr_headers(
                                        headers_with_text,
                                        captions_with_text,
                                        ocr_image_bbox,
                                        ocr_image_page,
                                        pdf_doc
                                    )
                                    
                                    if caption_info:
                                        if 'captions' not in docx_image:
                                            docx_image['captions'] = []
                                        docx_image['captions'].append(caption_info)
                                        logger.debug(f"Matched image {docx_image.get('index')} with caption: {caption_info.get('text', '')[:50]}")
                                        break
                    
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
                    
                    # Process headers
                    header_positions = self.header_processor.process_headers(
                        headers_with_text,
                        all_xml_elements,
                        toc_headers_map,
                        docx_path,
                    )
                    
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
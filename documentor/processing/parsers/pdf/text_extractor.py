"""
PDF text extraction processor.

Handles text extraction from PDF documents using PyMuPDF or Dots OCR.
"""

import logging
import re
from typing import Any, Dict, List, Optional

import fitz
from tqdm import tqdm

from documentor.config.loader import ConfigLoader
from ...pdf.text_extractor_util import PdfTextExtractorUtil

logger = logging.getLogger(__name__)


class PdfTextExtractor:
    """
    Processor for PDF text extraction.
    
    Handles:
    - Text extraction via PyMuPDF (for extractable text)
    - Text extraction from OCR (for scanned PDFs)
    - Text merging and normalization
    """

    def __init__(self, config: Dict[str, Any], text_extractor: Optional[Any] = None) -> None:
        """
        Initialize text extractor.
        
        Args:
            config: Configuration dictionary.
            text_extractor: Custom text extractor implementing BaseTextExtractor.
                          If None, uses default (PyMuPDF for extractable text, OCR text for scanned PDFs).
        """
        self.config = config
        self.custom_text_extractor = text_extractor

    def _get_config(self, key: str, default: Any = None) -> Any:
        """Gets value from configuration."""
        return ConfigLoader.get_config_value(self.config, key, default)

    def extract_text_by_bboxes(
        self, source: str, layout_elements: List[Dict[str, Any]], use_ocr: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Extracts text via PyMuPDF by coordinates from layout elements.
        For scanned PDFs (use_ocr=True), text is already extracted by Dots OCR (prompt_layout_all_en).

        Args:
            source: Path to PDF file.
            layout_elements: List of layout elements with bbox.
            use_ocr: If True, text is already in elements from Dots OCR, just use it.
                     If False, extracts text via PyMuPDF.

        Returns:
            List of elements with extracted text.
        """
        pdf_document = fitz.open(source)
        try:
            text_elements: List[Dict[str, Any]] = []
            render_scale = self._get_config("layout_detection.render_scale", 2.0)
            
            if use_ocr:
                # For scanned PDFs, text is already extracted by OCR
                # Just use the text from layout_elements
                logger.info("Using text from OCR")
                
                for element in tqdm(layout_elements, desc="Processing text from Dots OCR", unit="element", leave=False):
                    category = element.get("category", "")
                    
                    # Skip Picture - no text for images
                    if category == "Picture":
                        text_elements.append(element)
                        continue
                    
                    # For text elements, use text from Dots OCR if available
                    if category in ["Text", "Section-header", "Title", "Caption", "Formula", "List-item"]:
                        # Text should already be in element from Dots OCR
                        # Clean and normalize if needed
                        text = element.get("text", "")
                        if text:
                            # Remove markdown formatting (**text** or __text__) from Dots OCR output
                            # BUT: Do NOT apply to Formula - LaTeX may contain *, **, _, __ as part of syntax
                            # Note: This is Dots OCR specific - custom layout detectors may not return markdown
                            if category != "Formula":
                                # Use Dots OCR utility for markdown removal
                                # This assumes text comes from Dots OCR (default behavior)
                                try:
                                    from documentor.ocr.dots_ocr.markdown_formatting import remove_markdown_formatting
                                    text = remove_markdown_formatting(text)
                                except ImportError:
                                    # Fallback if utils not available
                                    text = self._remove_markdown_formatting(text)
                            # Remove extra whitespace but preserve structure
                            element["text"] = text.strip()
                        else:
                            element["text"] = ""
                    
                    text_elements.append(element)
            else:
                # For PDFs with extractable text, use PyMuPDF
                for element in tqdm(layout_elements, desc="Extracting text via PyMuPDF", unit="element", leave=False):
                    category = element.get("category", "")
                    bbox = element.get("bbox", [])
                    page_num = element.get("page_num", 0)
                    
                    # Skip Picture - don't extract text for images
                    if category == "Picture":
                        text_elements.append(element)
                        continue
                    
                    # Extract text only for text elements
                    if category not in ["Text", "Section-header", "Title", "Caption"]:
                        text_elements.append(element)
                        continue
                    
                    if len(bbox) >= 4 and page_num < len(pdf_document):
                        try:
                            # Use custom text extractor if provided
                            if self.custom_text_extractor and use_ocr:
                                # For scanned PDFs, render image and use custom extractor
                                page = pdf_document.load_page(page_num)
                                mat = fitz.Matrix(render_scale, render_scale)
                                pix = page.get_pixmap(matrix=mat)
                                from PIL import Image
                                from io import BytesIO
                                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                                # Crop to bbox
                                x1, y1, x2, y2 = bbox
                                cropped_img = img.crop((int(x1), int(y1), int(x2), int(y2)))
                                text = self.custom_text_extractor.extract_text(
                                    cropped_img, bbox, category
                                )
                                element["text"] = text
                            else:
                                # Use PyMuPDF for extractable text
                                page = pdf_document.load_page(page_num)
                                text = PdfTextExtractorUtil.extract_text_by_bbox(page, bbox, render_scale)
                                element["text"] = text
                        except Exception as e:
                            logger.warning(f"Error extracting text for element: {e}")
                            element["text"] = ""
                    else:
                        element["text"] = ""
                    
                    text_elements.append(element)
            
            return text_elements
        finally:
            pdf_document.close()

    def _remove_markdown_formatting(self, text: str) -> str:
        """
        Remove markdown formatting (**text**, __text__, *text*) from text.
        Preserves single asterisks (*) used as list markers at the start of lines.
        
        Args:
            text: Text with potential markdown formatting
            
        Returns:
            Text with markdown formatting removed
        """
        if not text:
            return text
        
        # First, remove **text** (bold) -> text
        cleaned_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        # Remove __text__ (bold) -> text
        cleaned_text = re.sub(r'__([^_]+)__', r'\1', cleaned_text)
        
        # Remove *text* (italic) but preserve list markers (* at start of line or after newline)
        # Split by lines to handle list markers correctly
        lines = cleaned_text.split('\n')
        cleaned_lines = []
        for line in lines:
            # If line starts with "* " (list marker), preserve it and remove *text* from the rest
            if line.strip().startswith('* '):
                # Keep the "* " prefix, remove *text* from the rest
                prefix = line[:line.find('* ') + 2]  # "* " + everything before it
                rest = line[line.find('* ') + 2:]
                # Remove *text* from the rest
                rest_cleaned = re.sub(r'\*([^*]+)\*', r'\1', rest)
                cleaned_lines.append(prefix + rest_cleaned)
            else:
                # Remove all *text* (italic) from the line
                cleaned_line = re.sub(r'\*([^*]+)\*', r'\1', line)
                cleaned_lines.append(cleaned_line)
        
        cleaned_text = '\n'.join(cleaned_lines)
        
        return cleaned_text.strip()

    def merge_nearby_text_blocks(
        self, text_elements: List[Dict[str, Any]], max_chunk_size: int
    ) -> List[Dict[str, Any]]:
        """
        Merges consecutive Text elements.

        If text elements follow each other, merge them.

        Args:
            text_elements: List of text elements.
            max_chunk_size: Maximum block size in characters.

        Returns:
            List of merged elements.
        """
        if not text_elements:
            return []
        
        merged: List[Dict[str, Any]] = []
        current_block: Optional[Dict[str, Any]] = None
        
        # Sort by page and Y coordinate
        sorted_elements = sorted(
            text_elements,
            key=lambda e: (
                e.get("page_num", 0),
                e.get("bbox", [1, 0])[1] if len(e.get("bbox", [])) >= 2 else 0,
            ),
        )
        
        for element in sorted_elements:
            category = element.get("category", "")
            text = element.get("text", "")
            
            # Merge only Text elements
            if category != "Text":
                if current_block is not None:
                    merged.append(current_block)
                    current_block = None
                merged.append(element)
                continue
            
            if current_block is None:
                current_block = element.copy()
                continue
            
            # If current block is Text and next element is also Text, merge
            current_text = current_block.get("text", "")
            combined_text = f"{current_text} {text}".strip()
            
            # Check size
            if len(combined_text) <= max_chunk_size:
                current_block["text"] = combined_text
                # Update bbox
                current_bbox = current_block.get("bbox", [])
                element_bbox = element.get("bbox", [])
                if len(current_bbox) >= 4 and len(element_bbox) >= 4:
                    current_block["bbox"] = [
                        min(current_bbox[0], element_bbox[0]),
                        min(current_bbox[1], element_bbox[1]),
                        max(current_bbox[2], element_bbox[2]),
                        max(current_bbox[3], element_bbox[3]),
                    ]
                continue
            
            # Cannot merge (size exceeded) - save current block and start new
            merged.append(current_block)
            current_block = element.copy()
        
        # Add last block
        if current_block is not None:
            merged.append(current_block)
        
        logger.debug(f"Text merging: {len(text_elements)} -> {len(merged)} elements")
        return merged

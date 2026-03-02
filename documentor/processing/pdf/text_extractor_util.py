"""
PDF text extraction utility.

Provides common functions for extracting text from PDF by bounding box coordinates.
"""

import logging
from typing import Any, Dict, List, Optional

import fitz

logger = logging.getLogger(__name__)


class PdfTextExtractorUtil:
    """
    Utility class for extracting text from PDF documents by bounding box.
    
    Provides common functionality to avoid code duplication between parsers.
    """

    @staticmethod
    def extract_text_by_bbox(
        page: fitz.Page,
        bbox: List[float],
        render_scale: float = 2.0,
    ) -> str:
        """
        Extracts text from PDF page by bounding box coordinates.
        
        Args:
            page: PyMuPDF page object.
            bbox: Bounding box in image coordinates [x1, y1, x2, y2].
            render_scale: Scale used for rendering (to convert coordinates).
        
        Returns:
            Extracted text string.
        """
        if len(bbox) < 4:
            return ""
        
        try:
            # Convert bbox from image coordinates to PDF page coordinates
            x1, y1, x2, y2 = (
                bbox[0] / render_scale,
                bbox[1] / render_scale,
                bbox[2] / render_scale,
                bbox[3] / render_scale,
            )
            
            # Create rectangle for text extraction in PDF coordinates
            rect = fitz.Rect(x1, y1, x2, y2)
            
            # Try get_textbox first - more accurate method
            text = page.get_textbox(rect).strip()
            
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
                
                text = " ".join(text_parts).strip()
            
            # If that didn't help, use old method as fallback
            if not text or len(text.strip()) < 2:
                text = page.get_text("text", clip=rect).strip()
            
            return text
        except Exception as e:
            logger.debug(f"Error extracting text from PDF by bbox: {e}")
            return ""

    @staticmethod
    def extract_text_for_elements(
        elements: List[Dict[str, Any]],
        pdf_doc: fitz.Document,
        render_scale: float = 2.0,
        allowed_categories: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Extracts text for multiple elements from PDF.
        
        Args:
            elements: List of elements with bbox and page_num.
            pdf_doc: PyMuPDF document.
            render_scale: Render scale used for rendering.
            allowed_categories: List of categories to process. If None, processes all.
        
        Returns:
            List of elements with extracted text.
        """
        if allowed_categories is None:
            allowed_categories = ["Section-header", "Caption", "Text", "Title"]
        
        results = []
        
        for element in elements:
            category = element.get("category", "")
            bbox = element.get("bbox", [])
            page_num = element.get("page_num", 0)
            
            if category not in allowed_categories:
                results.append(element)
                continue
            
            if not bbox or len(bbox) < 4:
                element["text"] = ""
                results.append(element)
                continue
            
            if page_num >= len(pdf_doc):
                element["text"] = ""
                results.append(element)
                continue
            
            try:
                page = pdf_doc[page_num]
                text = PdfTextExtractorUtil.extract_text_by_bbox(page, bbox, render_scale)
                element["text"] = text
            except Exception as e:
                logger.warning(f"Error extracting text for element: {e}")
                element["text"] = ""
            
            results.append(element)
        
        return results

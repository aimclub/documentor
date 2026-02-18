"""
PDF table parsing processor.

Handles table parsing from Dots OCR HTML output.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import fitz
import pandas as pd
from PIL import Image
from tqdm import tqdm

from ....domain import Element, ElementType
from ....utils.config_loader import ConfigLoader
from ....utils.image_utils import ImageUtils
from documentor.ocr.dots_ocr.html_table_parser import parse_table_from_html

logger = logging.getLogger(__name__)


class PdfTableParser:
    """
    Processor for PDF table parsing.
    
    Handles:
    - Parsing HTML tables from OCR
    - Converting to DataFrame
    - Storing table images
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize table parser.
        
        Args:
            config: Configuration dictionary.
        """
        self.config = config

    def _get_config(self, key: str, default: Any = None) -> Any:
        """Gets value from configuration."""
        return ConfigLoader.get_config_value(self.config, key, default)

    def parse_tables(
        self, elements: List[Element], source: str, use_dots_ocr_html: bool = True
    ) -> List[Element]:
        """
        Parses tables from OCR HTML.

        Args:
            elements: List of elements.
            source: Path to PDF file.
            use_dots_ocr_html: If True, uses HTML from OCR.
                              Always True now.

        Returns:
            List of elements with parsed tables.
        """
        table_elements = [e for e in elements if e.type == ElementType.TABLE]
        
        if not table_elements:
            return elements
        
        pdf_document = fitz.open(source)
        try:
            render_scale = self._get_config("layout_detection.render_scale", 2.0)
            
            for element in tqdm(table_elements, desc="Parsing tables", unit="table", leave=False):
                bbox = element.metadata.get("bbox", [])
                page_num = element.metadata.get("page_num", 0)
                
                if len(bbox) < 4 or page_num >= len(pdf_document):
                    logger.warning(f"Skipping table with invalid bbox or page_num: {element.id}")
                    continue
                
                try:
                    page = pdf_document.load_page(page_num)
                    # Convert coordinates to original PDF scale
                    x1, y1, x2, y2 = (
                        bbox[0] / render_scale,
                        bbox[1] / render_scale,
                        bbox[2] / render_scale,
                        bbox[3] / render_scale,
                    )
                    rect = fitz.Rect(x1, y1, x2, y2)
                    
                    # Render table area for image storage
                    mat = fitz.Matrix(2.0, 2.0)  # Increase for better quality
                    pix = page.get_pixmap(matrix=mat, clip=rect)
                    
                    # Convert to PIL Image and encode to base64
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    img_base64 = ImageUtils.process_and_encode_image(img, max_dimension=1280, format="PNG", quality=75)
                    element.metadata["image_data"] = img_base64
                    
                    # Parse table: use HTML from OCR
                    dataframe = None
                    success = False
                    
                    # Try to get HTML from element metadata (stored during element creation)
                    table_html = element.metadata.get("table_html")
                    if table_html:
                        # Parse HTML table from OCR
                        _, dataframe, success = parse_table_from_html(
                            table_html,
                            method="dataframe",  # Use only DataFrame
                        )
                        if success:
                            logger.debug(f"Table {element.id} parsed from OCR HTML")
                    
                    if not success:
                        logger.warning(f"Failed to parse table {element.id} - no HTML from OCR")
                        element.content = ""
                        element.metadata["parsing_error"] = "Failed to parse table: no HTML from Dots OCR"
                        # Create empty DataFrame
                        element.metadata["dataframe"] = pd.DataFrame()
                        element.metadata["rows_count"] = 0
                        element.metadata["cols_count"] = 0
                        continue
                    
                    # Use only DataFrame
                    element.content = ""  # NOTE: markdown is no longer saved
                    if dataframe is not None:
                        element.metadata["dataframe"] = dataframe
                        element.metadata["rows_count"] = len(dataframe)
                        element.metadata["cols_count"] = len(dataframe.columns) if len(dataframe) > 0 else 0
                        element.metadata["parsing_method"] = "dots_ocr_html"
                    else:
                        element.metadata["parsing_error"] = "DataFrame creation failed"
                        element.metadata["dataframe"] = pd.DataFrame()
                        element.metadata["rows_count"] = 0
                        element.metadata["cols_count"] = 0
                
                except Exception as e:
                    logger.error(f"Error parsing table {element.id}: {e}")
                    element.content = ""
                    element.metadata["parsing_error"] = str(e)
                    element.metadata["dataframe"] = pd.DataFrame()
                    element.metadata["rows_count"] = 0
                    element.metadata["cols_count"] = 0
            
            return elements
        finally:
            pdf_document.close()

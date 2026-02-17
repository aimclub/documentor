"""
PDF image processing processor.

Handles image extraction and storage from PDF documents.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import fitz
from PIL import Image
from tqdm import tqdm

from ....domain import Element, ElementType
from ....utils.config_loader import ConfigLoader
from ....utils.image_utils import ImageUtils

logger = logging.getLogger(__name__)


class PdfImageProcessor:
    """
    Processor for PDF image processing.
    
    Handles:
    - Image extraction from PDF
    - Image optimization and compression
    - Base64 encoding
    - Linking images to captions
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize image processor.
        
        Args:
            config: Configuration dictionary.
        """
        self.config = config

    def _get_config(self, key: str, default: Any = None) -> Any:
        """Gets value from configuration."""
        return ConfigLoader.get_config_value(self.config, key, default)

    def store_images_in_metadata(
        self, elements: List[Element], source: str
    ) -> List[Element]:
        """
        Stores images in Caption element metadata.
        
        Logic:
        - Finds IMAGE elements
        - Finds corresponding CAPTION elements (by bbox proximity)
        - Saves image in CAPTION metadata
        - CAPTION is already linked to Header via parent_id

        Args:
            elements: List of elements.
            source: Path to PDF file.

        Returns:
            List of elements with updated metadata.
        """
        pdf_document = fitz.open(source)
        try:
            render_scale = self._get_config("layout_detection.render_scale", 2.0)
            
            image_elements = [e for e in elements if e.type == ElementType.IMAGE]
            caption_elements = [e for e in elements if e.type == ElementType.CAPTION]
            
            for image_element in tqdm(image_elements, desc="Processing images", unit="image", leave=False):
                image_bbox = image_element.metadata.get("bbox", [])
                image_page = image_element.metadata.get("page_num", 0)
                
                if len(image_bbox) < 4:
                    logger.warning(f"Image {image_element.id} has invalid bbox: {image_bbox}")
                    continue
                
                if image_page >= len(pdf_document):
                    logger.warning(f"Image {image_element.id} has invalid page number: {image_page} (max: {len(pdf_document) - 1})")
                    continue
                
                try:
                    # Extract image
                    page = pdf_document.load_page(image_page)
                    
                    # Convert coordinates: bbox is in render_scale coordinates, need to convert to PDF coordinates
                    x1, y1, x2, y2 = (
                        image_bbox[0] / render_scale,
                        image_bbox[1] / render_scale,
                        image_bbox[2] / render_scale,
                        image_bbox[3] / render_scale,
                    )
                    
                    # Ensure coordinates are within page bounds
                    page_rect = page.rect
                    x1 = max(0, min(x1, page_rect.width))
                    y1 = max(0, min(y1, page_rect.height))
                    x2 = max(x1, min(x2, page_rect.width))
                    y2 = max(y1, min(y2, page_rect.height))
                    
                    # Validate that rect has positive area
                    if x2 <= x1 or y2 <= y1:
                        logger.warning(f"Image {image_element.id} has invalid rect after conversion: ({x1}, {y1}, {x2}, {y2})")
                        continue
                    
                    rect = fitz.Rect(x1, y1, x2, y2)
                    
                    # Calculate image dimensions in PDF coordinates
                    img_width = x2 - x1
                    img_height = y2 - y1
                    
                    # Limit maximum image size to avoid huge base64 strings
                    # Target: max 1280px on the longest side, maintain aspect ratio
                    max_dimension = 1280
                    scale_factor = 1.0
                    
                    if img_width > max_dimension or img_height > max_dimension:
                        if img_width > img_height:
                            scale_factor = max_dimension / img_width
                        else:
                            scale_factor = max_dimension / img_height
                    
                    # Render image with reasonable quality
                    render_scale_img = max(1.0, min(1.5, scale_factor * 1.5))
                    mat = fitz.Matrix(render_scale_img, render_scale_img)
                    pix = page.get_pixmap(matrix=mat, clip=rect)
                    
                    if pix is None or pix.width == 0 or pix.height == 0:
                        logger.warning(f"Image {image_element.id} rendered as empty pixmap")
                        continue
                    
                    # Convert to PIL Image for compression
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    
                    # Optimize and encode to base64
                    img_base64 = ImageUtils.process_and_encode_image(img, max_dimension=1280, format="JPEG", quality=75)
                    
                    # Find best matching caption (by bbox proximity on same page)
                    best_caption = None
                    min_distance = float("inf")
                    
                    for caption in caption_elements:
                        caption_bbox = caption.metadata.get("bbox", [])
                        caption_page = caption.metadata.get("page_num", 0)
                        
                        if caption_page != image_page or len(caption_bbox) < 4:
                            continue
                        
                        # Calculate distance between image and caption
                        # Use center points for distance calculation
                        img_center_x = (image_bbox[0] + image_bbox[2]) / 2
                        img_center_y = (image_bbox[1] + image_bbox[3]) / 2
                        caption_center_x = (caption_bbox[0] + caption_bbox[2]) / 2
                        caption_center_y = (caption_bbox[1] + caption_bbox[3]) / 2
                        
                        # Check if caption is below image (typical case)
                        if caption_bbox[1] > image_bbox[3]:
                            distance = (
                                (img_center_x - caption_center_x) ** 2 +
                                (image_bbox[3] - caption_bbox[1]) ** 2
                            ) ** 0.5
                            
                            if distance < min_distance:
                                min_distance = distance
                                best_caption = caption
                    
                    # Store image in best caption metadata
                    if best_caption:
                        best_caption.metadata["image_data"] = img_base64
                        best_caption.metadata["image_id"] = image_element.id
                        logger.debug(f"Image {image_element.id} stored in caption {best_caption.id}")
                    else:
                        # No caption found - store in image element itself
                        image_element.metadata["image_data"] = img_base64
                        logger.debug(f"Image {image_element.id} stored in image element (no caption found)")
                
                except Exception as e:
                    logger.error(f"Error processing image {image_element.id}: {e}")
                    continue
            
            return elements
        finally:
            pdf_document.close()

"""
Integration with Dots.OCR for layout detection.

Contains classes for:
- Page structure detection (layout detection)
- Element type detection (Text, Picture, Caption, Table, etc.)
- Element coordinate extraction (bbox)

Uses strict prompts from official Dots.OCR documentation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path
from PIL import Image
import yaml

from ..processing.parsers.docx.ocr.layout_dots import LayoutTypeDotsOCR


# Strict prompts from Dots.OCR (official)
DOTS_OCR_PROMPTS = {
    # Full layout extraction with text in JSON format
    "prompt_layout_all_en": """Please output the layout information from the PDF image, including each layout element's bbox, its category, and the corresponding text content within the bbox.

1. Bbox format: [x1, y1, x2, y2]

2. Layout Categories: The possible categories are ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title'].

3. Text Extraction & Formatting Rules:
    - Picture: For the 'Picture' category, the text field should be omitted.
    - Formula: Format its text as LaTeX.
    - Table: Format its text as HTML.
    - All Others (Text, Title, etc.): Format their text as Markdown.

4. Constraints:
    - The output text must be the original text from the image, with no translation.
    - All layout elements must be sorted according to human reading order.

5. Final Output: The entire output must be a single JSON object.
""",

    # Layout detection only without text
    "prompt_layout_only_en": """Please output the layout information from this PDF image, including each layout's bbox and its category. The bbox should be in the format [x1, y1, x2, y2]. The layout categories for the PDF document include ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title']. Do not output the corresponding text. The layout result should be in JSON format.""",

    # Text extraction from image (except Page-header and Page-footer)
    "prompt_ocr": """Extract the text content from this image.""",

    # Text extraction from given bounding box
    "prompt_grounding_ocr": """Extract text from the given bounding box on the image (format: [x1, y1, x2, y2]).
Bounding Box:
""",
}


def load_prompts_from_config(config_path: Optional[Path] = None) -> Dict[str, str]:
    """
    Load prompts from configuration file.
    
    Args:
        config_path: Path to ocr_config.yaml (if None - uses standard path)
    
    Returns:
        Dict[str, str]: Dictionary of prompts
    """
    if config_path is None:
        # Standard configuration path
        config_path = Path(__file__).parent.parent / "config" / "ocr_config.yaml"
    
    if not config_path.exists():
        # If configuration doesn't exist, return standard prompts
        return DOTS_OCR_PROMPTS.copy()
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # Extract prompts from configuration
    dots_ocr_config = config.get("dots_ocr", {})
    prompts_config = dots_ocr_config.get("prompts", {})
    
    # Merge with standard prompts (configuration has priority)
    prompts = DOTS_OCR_PROMPTS.copy()
    prompts.update(prompts_config)
    
    return prompts


def get_system_prompt(image_width: int, image_height: int) -> str:
    """
    Returns system prompt for layout detection.
    
    Args:
        image_width: Image width in pixels
        image_height: Image height in pixels
    
    Returns:
        str: System prompt with image size information
    """
    return f"You are a precise document layout analyzer. The input image is exactly {image_width}x{image_height} pixels."


class DotsOCRLayoutDetector:
    """
    Layout detector for Dots.OCR.
    
    Uses strict prompts from official Dots.OCR documentation
    for page structure detection.
    
    Prompts can be loaded from configuration (ocr_config.yaml) or use standard ones.
    """
    
    def __init__(
        self,
        endpoint: Optional[str] = None,
        timeout: int = 60,
        prompt_mode: str = "prompt_layout_all_en",
        prompts: Optional[Dict[str, str]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        """
        Initialize detector.
        
        Args:
            endpoint: URL or path to Dots.OCR service (if None - local)
            timeout: Request timeout in seconds
            prompt_mode: Prompt mode (prompt_layout_all_en, prompt_layout_only_en, prompt_ocr, prompt_grounding_ocr)
            prompts: Custom prompts (if None - loaded from configuration or use standard)
            config_path: Path to configuration file (if None - uses standard)
        """
        self.endpoint = endpoint
        self.timeout = timeout
        self.prompt_mode = prompt_mode
        
        # Load prompts: first from config_path, then from prompts, then standard
        if prompts is None:
            self.prompts = load_prompts_from_config(config_path)
        else:
            self.prompts = prompts
    
    def get_prompt(self, mode: Optional[str] = None) -> str:
        """
        Get prompt for specified mode.
        
        Args:
            mode: Prompt mode (if None - uses self.prompt_mode)
        
        Returns:
            str: Prompt text
        """
        mode = mode or self.prompt_mode
        if mode not in self.prompts:
            raise ValueError(f"Unknown prompt mode: {mode}. Available: {list(self.prompts.keys())}")
        return self.prompts[mode]
    
    def detect_layout(
        self,
        image: Image.Image,
        mode: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Detect page layout.
        
        Args:
            image: Page image
            mode: Prompt mode (if None - uses self.prompt_mode)
        
        Returns:
            List[Dict[str, Any]]: List of layout elements with fields:
                - bbox: [x1, y1, x2, y2]
                - category: element type (LayoutTypeDotsOCR)
                - text: element text (if available)
        
        TODO: Implement Dots.OCR API call
        """
        prompt = self.get_prompt(mode)
        # TODO: Implement Dots.OCR API call using prompt
        # TODO: Parse JSON response
        # TODO: Validate and normalize results
        raise NotImplementedError("detect_layout() method requires implementation")
    
    def get_element_types(self, layout_result: List[Dict[str, Any]]) -> List[LayoutTypeDotsOCR]:
        """
        Get element types from layout detection result.
        
        Args:
            layout_result: Result of detect_layout()
        
        Returns:
            List[LayoutTypeDotsOCR]: List of element types
        """
        types = []
        for element in layout_result:
            category = element.get("category", "Unknown")
            try:
                # Map string to LayoutTypeDotsOCR
                layout_type = LayoutTypeDotsOCR(category)
                types.append(layout_type)
            except ValueError:
                types.append(LayoutTypeDotsOCR.UNKNOWN)
        return types
    
    def get_bboxes(self, layout_result: List[Dict[str, Any]]) -> List[List[int]]:
        """
        Get element coordinates from layout detection result.
        
        Args:
            layout_result: Result of detect_layout()
        
        Returns:
            List[List[int]]: List of bbox in format [[x1, y1, x2, y2], ...]
        """
        bboxes = []
        for element in layout_result:
            bbox = element.get("bbox", [])
            if len(bbox) == 4:
                bboxes.append(bbox)
        return bboxes

"""
Prompts for Dots.OCR.

Contains standard prompts and functions for loading prompts from configuration.
Uses strict prompts from official Dots.OCR documentation.
"""

from typing import Dict, Optional
from pathlib import Path
import yaml


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
        config_path = Path(__file__).parent.parent.parent / "config" / "ocr_config.yaml"
    
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

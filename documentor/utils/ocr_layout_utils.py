"""
Utilities for processing OCR layout results.
"""

import json
from typing import Dict, List

from PIL import Image

from documentor.utils.ocr_image_utils import smart_resize
from documentor.utils.ocr_consts import MIN_PIXELS, MAX_PIXELS


def post_process_cells(
    origin_image: Image.Image, 
    cells: List[Dict], 
    input_width,  # server input width, also has smart_resize in server
    input_height,
    factor: int = 28,
    min_pixels: int = 3136, 
    max_pixels: int = 11289600
) -> List[Dict]:
    """
    Post-processes cell bounding boxes, converting coordinates from the resized dimensions back to the original dimensions.
    
    Args:
        origin_image: The original PIL Image.
        cells: A list of cells containing bounding box information.
        input_width: The width of the input image sent to the server.
        input_height: The height of the input image sent to the server.
        factor: Resizing factor.
        min_pixels: Minimum number of pixels.
        max_pixels: Maximum number of pixels.
        
    Returns:
        A list of post-processed cells.
    """
    assert isinstance(cells, list) and len(cells) > 0 and isinstance(cells[0], dict)
    min_pixels = min_pixels or MIN_PIXELS
    max_pixels = max_pixels or MAX_PIXELS
    original_width, original_height = origin_image.size

    input_height, input_width = smart_resize(input_height, input_width, min_pixels=min_pixels, max_pixels=max_pixels)
    
    scale_x = input_width / original_width
    scale_y = input_height / original_height
    
    cells_out = []
    for cell in cells:
        bbox = cell['bbox']
        bbox_resized = [
            int(float(bbox[0]) / scale_x), 
            int(float(bbox[1]) / scale_y),
            int(float(bbox[2]) / scale_x), 
            int(float(bbox[3]) / scale_y)
        ]
        cell_copy = cell.copy()
        cell_copy['bbox'] = bbox_resized
        cells_out.append(cell_copy)
    
    return cells_out


def post_process_output(response, prompt_mode, origin_image, input_image, min_pixels=None, max_pixels=None):
    """
    Post-processes OCR model response.
    
    Args:
        response: Raw model response (string or list)
        prompt_mode: Prompt mode
        origin_image: Original image
        input_image: Image sent to server
        min_pixels: Minimum number of pixels
        max_pixels: Maximum number of pixels
        
    Returns:
        Tuple[Union[List[Dict], str], bool]: Processed data and filtering flag
    """
    if prompt_mode in ["prompt_ocr", "prompt_table_html", "prompt_table_latex", "prompt_formula_latex"]:
        return response

    json_load_failed = False
    cells = response
    try:
        cells = json.loads(cells)
        cells = post_process_cells(
            origin_image, 
            cells,
            input_image.width,
            input_image.height,
            min_pixels=min_pixels,
            max_pixels=max_pixels
        )
        return cells, False
    except Exception as e:
        print(f"cells post process error: {e}, when using {prompt_mode}")
        json_load_failed = True

    if json_load_failed:
        from documentor.utils.ocr_output_cleaner import OutputCleaner
        cleaner = OutputCleaner()
        response_clean = cleaner.clean_model_output(cells)
        if isinstance(response_clean, list):
            response_clean = "\n\n".join([cell['text'] for cell in response_clean if 'text' in cell])
        return response_clean, True

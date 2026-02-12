"""
Client for direct Dots.OCR API calls.

Contains functions for working with Dots.OCR API directly,
using the same approach as in pdf_pipeline_dots_ocr.py.
"""

from __future__ import annotations

import os
import time
from typing import Optional, Tuple
from io import BytesIO

from PIL import Image
import openai
import base64

# Load environment variables from .env file
from documentor.core.load_env import load_env_file
load_env_file()

# Import utilities from documentor.utils
from documentor.utils.ocr_consts import MIN_PIXELS, MAX_PIXELS
from documentor.utils.ocr_image_utils import fetch_image
from documentor.utils.ocr_layout_utils import post_process_output


def _image_to_base64(image: Image.Image) -> str:
    """Converts PIL Image to base64 data URL."""
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def run_inference(
    input_image: Image.Image,
    prompt: str,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    model_name: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Optional[str]:
    """
    Performs inference via dots.ocr API.
    
    Args:
        input_image: Image for processing
        prompt: Prompt text
        base_url: API base URL (default from env)
        api_key: API key (default from env)
        temperature: Generation temperature (default from env)
        max_tokens: Maximum number of tokens (default from env)
        model_name: Model name (default from env)
        timeout: Request timeout in seconds (default from env)
    
    Returns:
        String with model response or None in case of error
    """
    if base_url is None:
        base_url = os.getenv("DOTS_OCR_BASE_URL")
    if api_key is None:
        api_key = os.getenv("DOTS_OCR_API_KEY")
    if temperature is None:
        temperature = float(os.getenv("DOTS_OCR_TEMPERATURE", "0.1"))
    if max_tokens is None:
        max_tokens = int(os.getenv("DOTS_OCR_MAX_TOKENS", "10000"))
    if model_name is None:
        model_name = os.getenv("DOTS_OCR_MODEL_NAME")
    if timeout is None:
        timeout = int(os.getenv("DOTS_OCR_TIMEOUT", "120"))
    
    # Remove spaces and check base_url
    if base_url:
        base_url = base_url.strip()
        # Ensure URL ends with /v1 without spaces
        if base_url.endswith(" "):
            base_url = base_url.rstrip()
        if not base_url.endswith("/v1"):
            if base_url.endswith("/v1 "):
                base_url = base_url.rstrip()
            elif not base_url.endswith("/"):
                base_url = f"{base_url}/v1"
            else:
                base_url = f"{base_url}v1"
    
    if not base_url:
        raise ValueError("DOTS_OCR_BASE_URL is not set or empty")
    
    client = openai.OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
    )
    image_base64 = _image_to_base64(input_image)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_base64}},
                {"type": "text", "text": f"<|img|><|imgpad|><|endofimg|>{prompt}"},
            ],
        }
    ]
    try:
        request_params = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }

        response = client.chat.completions.create(**request_params)
        content = response.choices[0].message.content
        return content
    except openai.BadRequestError as exc:
        message = str(exc)
        if ("max_completion_tokens" in message or "max_tokens" in message) and "maximum context length" in message:
            reduced_tokens = max(256, max_tokens - 1024)
            if reduced_tokens >= max_tokens:
                raise
            retry_params = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_completion_tokens": reduced_tokens,
            }
            response = client.chat.completions.create(**retry_params)
            return response.choices[0].message.content
        raise
    except Exception as exc:
        raise


def process_layout_detection(
    image: Image.Image,
    origin_image: Optional[Image.Image] = None,
    prompt: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    model_name: Optional[str] = None,
    timeout: Optional[int] = None,
    min_pixels: Optional[int] = None,
    max_pixels: Optional[int] = None,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> Tuple[Optional[list], Optional[str], bool]:
    """
    Performs layout detection for an image.
    
    Args:
        image: Image to process (already prepared via smart_resize)
        origin_image: Original image (for post_process_output)
        prompt: Prompt for layout detection
        base_url: API base URL
        api_key: API key
        temperature: Generation temperature
        max_tokens: Maximum number of tokens
        model_name: Model name
        timeout: Request timeout
        min_pixels: Minimum number of pixels
        max_pixels: Maximum number of pixels
        max_retries: Maximum number of retries on empty response
        retry_delay: Delay between retries
    
    Returns:
        tuple[Optional[list], Optional[str], bool]:
            - layout_cells: List of layout elements or None
            - raw_response: Raw response from model or None
            - success: Operation success status
    """
    if prompt is None:
        prompt = "Please output the layout information from this PDF image, including each layout's bbox and its category. The bbox should be in the format [x1, y1, x2, y2]. The layout categories for the PDF document include ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title']. Do not output the corresponding text. The layout result should be in JSON format."
    
    if origin_image is None:
        origin_image = image
    
    if min_pixels is None:
        min_pixels = MIN_PIXELS
    if max_pixels is None:
        max_pixels = MAX_PIXELS
    
    raw_response = None
    for attempt in range(max_retries):
        raw_response = run_inference(
            image,
            prompt,
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            model_name=model_name,
            timeout=timeout,
        )
        
        if raw_response and len(raw_response.strip()) > 0:
            break
        else:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    
    if raw_response is None or len(raw_response.strip()) == 0:
        return None, None, False
    
    parsed_cells, filtered = post_process_output(
        raw_response,
        "prompt_layout_only_en",
        origin_image,
        image,
        min_pixels=min_pixels,
        max_pixels=max_pixels,
    )
    
    if isinstance(parsed_cells, list):
        return parsed_cells, raw_response, True
    else:
        return None, raw_response, False

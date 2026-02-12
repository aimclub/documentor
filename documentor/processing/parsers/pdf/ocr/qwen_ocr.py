"""
OCR via Qwen2.5 for extracting text from images.

Used for scanned PDFs without extractable text.
"""

from __future__ import annotations

import base64
import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

import openai
import yaml
from PIL import Image

from documentor.utils.ocr_image_utils import fetch_image

logger = logging.getLogger(__name__)

# Cache for OCR config
_ocr_config_cache: Optional[dict] = None


def _load_ocr_config() -> dict:
    """Loads OCR configuration from ocr_config.yaml."""
    global _ocr_config_cache
    if _ocr_config_cache is not None:
        return _ocr_config_cache
    
    config_path = Path(__file__).parent.parent.parent.parent.parent / "config" / "ocr_config.yaml"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                _ocr_config_cache = config or {}
                return _ocr_config_cache
        except Exception as e:
            logger.warning(f"Failed to load OCR config from {config_path}: {e}")
            _ocr_config_cache = {}
            return _ocr_config_cache
    else:
        _ocr_config_cache = {}
        return _ocr_config_cache


def _get_config_value(key_path: str, env_var: Optional[str] = None, default: Optional[Any] = None) -> Any:
    """
    Gets configuration value with priority: config file → env var → default.
    
    Args:
        key_path: Dot-separated path in config (e.g., "qwen_ocr.recognition.timeout")
        env_var: Environment variable name (optional)
        default: Default value if not found
    
    Returns:
        Configuration value
    """
    config = _load_ocr_config()
    
    # Try config file first
    keys = key_path.split(".")
    value = config
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            value = None
            break
        if value is None:
            break
    
    if value is not None:
        return value
    
    # Fallback to environment variable
    if env_var:
        env_value = os.getenv(env_var)
        if env_value is not None:
            try:
                # Try to convert to appropriate type
                if isinstance(default, int):
                    return int(env_value)
                elif isinstance(default, float):
                    return float(env_value)
                elif isinstance(default, bool):
                    return env_value.lower() in ("true", "1", "yes", "on")
                return env_value
            except (ValueError, TypeError):
                logger.warning(f"Failed to convert env var {env_var}={env_value} to {type(default).__name__}")
    
    # Return default
    return default


def _image_to_base64(image: Image.Image) -> str:
    """Converts PIL Image to base64 data URL."""
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def ocr_text_with_qwen(
    element_image: Image.Image,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    model_name: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Optional[str]:
    """
    Performs OCR of element via Qwen2.5 API.
    
    Args:
        element_image: Element image for OCR
        base_url: API base URL (default from env)
        api_key: API key (default from env)
        temperature: Generation temperature (default from env)
        max_tokens: Maximum number of tokens (default from env)
        model_name: Model name (default from env)
        timeout: Request timeout in seconds (default from env)
    
    Returns:
        Extracted text or None in case of error
    """
    if base_url is None:
        base_url_raw = os.getenv("QWEN_BASE_URL")
        if base_url_raw:
            for line in base_url_raw.split('\n'):
                for url in line.split(','):
                    url = url.strip()
                    if "#" in url:
                        url = url.split("#")[0].strip()
                    if url:
                        base_url = url
                        break
                if base_url:
                    break
    # Secret parameters: only from env
    if api_key is None:
        api_key = os.getenv("QWEN_API_KEY")
    
    # Non-secret parameters: from config → env → default
    if temperature is None:
        temperature = _get_config_value(
            "qwen_ocr.recognition.temperature",
            "QWEN_TEMPERATURE",
            0.1
        )
    if max_tokens is None:
        max_tokens = _get_config_value(
            "qwen_ocr.recognition.max_tokens",
            "QWEN_MAX_TOKENS",
            4096
        )
    if model_name is None:
        model_name = _get_config_value(
            "qwen_ocr.model",
            "QWEN_MODEL_NAME",
            None
        )
    if timeout is None:
        timeout = _get_config_value(
            "qwen_ocr.recognition.timeout",
            "QWEN_TIMEOUT",
            180
        )
    
    if not base_url:
        raise ValueError("QWEN_BASE_URL is not set")
    if not base_url.endswith("/v1"):
        if base_url.endswith("/"):
            base_url = f"{base_url}v1"
        else:
            base_url = f"{base_url}/v1"
    
    prompt = """Extract all text from this image with high accuracy. Follow these guidelines:
1. Preserve the exact reading order (left-to-right, top-to-bottom)
2. Maintain line breaks exactly as they appear in the image
3. Do not skip any words or text elements
4. Keep the original spacing and formatting
5. If text is in multiple columns, read each column completely before moving to the next
6. Output only the extracted text, no additional comments or descriptions

Extract the text:"""
    
    # Prepare image
    optimized_image = fetch_image(
        element_image,
        min_pixels=None,
        max_pixels=None,
    )
    
    image_base64 = _image_to_base64(optimized_image)
    
    client = openai.OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
    )
    
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_base64}},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_tokens,
        )
        content = response.choices[0].message.content
        return content.strip() if content else None
    except Exception as e:
        logger.error(f"OCR error via Qwen: {e}")
        return None

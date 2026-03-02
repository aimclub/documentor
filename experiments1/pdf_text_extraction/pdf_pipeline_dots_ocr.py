"""
Модуль для работы с dots.ocr в PDF пайплайне.

Содержит функции для layout detection через dots.ocr, которые можно использовать
в основном пайплайне documentor для обработки PDF файлов.

Для PDF: увеличение 2x делается на стадии рендеринга через fitz.Matrix(2.0, 2.0),
затем применяется smart_resize через fetch_image для приведения к размеру кратному 28
в рамках MIN/MAX_PIXELS.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from io import BytesIO

from PIL import Image
import openai
import fitz

_dots_ocr_path = Path(__file__).resolve().parents[2] / "dots.ocr"
if _dots_ocr_path.exists():
    sys.path.insert(0, str(_dots_ocr_path))

try:
    from dots_ocr.utils.consts import MIN_PIXELS, MAX_PIXELS
    from dots_ocr.utils.image_utils import fetch_image
    from dots_ocr.utils.layout_utils import draw_layout_on_image, post_process_output
except ImportError as exc:
    raise SystemExit(
        f"Не удалось импортировать dots_ocr. Проверьте путь { _dots_ocr_path }: {exc}"
    ) from exc

DEFAULT_PROMPT_TEXT = "Please output the layout information from this PDF image, including each layout's bbox and its category. The bbox should be in the format [x1, y1, x2, y2]. The layout categories for the PDF document include ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title']. Do not output the corresponding text. The layout result should be in JSON format."

DOTS_OCR_BASE_URL = os.getenv("DOTS_OCR_BASE_URL", "http://10.32.2.11:8069/v1")
DOTS_OCR_API_KEY = os.getenv("DOTS_OCR_API_KEY", "security-token-abc123")
_model_name_from_env = os.getenv("DOTS_OCR_MODEL_NAME", "")
if _model_name_from_env and _model_name_from_env != "правильное_имя_модели":
    DOTS_OCR_MODEL_NAME = _model_name_from_env
else:
    DOTS_OCR_MODEL_NAME = "/model"
DOTS_OCR_TEMPERATURE = float(os.getenv("DOTS_OCR_TEMPERATURE", "0.1"))
DOTS_OCR_MAX_TOKENS = int(os.getenv("DOTS_OCR_MAX_TOKENS", "10000"))
DOTS_OCR_TIMEOUT = int(os.getenv("DOTS_OCR_TIMEOUT", "120"))


def load_pdf_page_as_image(pdf_path: Path, page_num: int = 0) -> Image.Image:
    """Загружает страницу PDF как изображение с увеличением 2x на стадии рендеринга."""
    pdf_document = fitz.open(str(pdf_path))
    try:
        page = pdf_document.load_page(page_num)
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("ppm")
        image = Image.open(BytesIO(img_data)).convert("RGB")
        return image
    finally:
        pdf_document.close()


def prepare_image(
    image: Image.Image, min_pixels: Optional[int] = None, max_pixels: Optional[int] = None
) -> Image.Image:
    """Подготавливает изображение для обработки через smart_resize."""
    if min_pixels is None:
        min_pixels = MIN_PIXELS
    if max_pixels is None:
        max_pixels = MAX_PIXELS
    
    input_image = fetch_image(
        image,
        min_pixels=min_pixels,
        max_pixels=max_pixels,
    )
    return input_image


def image_to_base64(image: Image.Image) -> str:
    """Конвертирует PIL Image в base64 data URL."""
    import base64

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
    Выполняет inference через dots.ocr API.
    
    Args:
        input_image: Изображение для обработки
        prompt: Текст промпта
        base_url: Базовый URL API (по умолчанию из env)
        api_key: API ключ (по умолчанию из env)
        temperature: Температура генерации (по умолчанию из env)
        max_tokens: Максимальное число токенов (по умолчанию из env)
        model_name: Имя модели (по умолчанию из env)
        timeout: Таймаут запроса в секундах (по умолчанию из env)
    
    Returns:
        Строка с ответом от модели или None в случае ошибки
    """
    if base_url is None:
        base_url = DOTS_OCR_BASE_URL
    if api_key is None:
        api_key = DOTS_OCR_API_KEY
    if temperature is None:
        temperature = DOTS_OCR_TEMPERATURE
    if max_tokens is None:
        max_tokens = DOTS_OCR_MAX_TOKENS
    if model_name is None:
        model_name = DOTS_OCR_MODEL_NAME
    if timeout is None:
        timeout = DOTS_OCR_TIMEOUT
    
    client = openai.OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
    )
    image_base64 = image_to_base64(input_image)
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


def process_pdf_page(
    pdf_path: Path,
    page_num: int,
    prompt_text: Optional[str] = None,
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
) -> Dict[str, object]:
    """
    Обрабатывает одну страницу PDF через dots.ocr.
    
    Args:
        pdf_path: Путь к PDF файлу
        page_num: Номер страницы (0-based)
        prompt_text: Промпт для layout detection (по умолчанию DEFAULT_PROMPT_TEXT)
        base_url: Базовый URL API (по умолчанию из env)
        api_key: API ключ (по умолчанию из env)
        temperature: Температура генерации (по умолчанию из env)
        max_tokens: Максимальное число токенов (по умолчанию из env)
        model_name: Имя модели (по умолчанию из env)
        timeout: Таймаут запроса в секундах (по умолчанию из env)
        min_pixels: Минимальное число пикселей при ресайзе (по умолчанию MIN_PIXELS)
        max_pixels: Максимальное число пикселей при ресайзе (по умолчанию MAX_PIXELS)
        max_retries: Максимальное число попыток при пустом ответе
        retry_delay: Задержка между попытками в секундах
    
    Returns:
        Словарь с результатами обработки:
        {
            "success": bool,
            "error": Optional[str],
            "raw_response": Optional[str],
            "layout_cells": Optional[List[Dict]],
            "origin_image": Image.Image,
            "input_image": Image.Image,
            "processing_time_seconds": float,
            "empty_response": bool,
        }
    """
    if prompt_text is None:
        prompt_text = DEFAULT_PROMPT_TEXT
    if min_pixels is None:
        min_pixels = MIN_PIXELS
    if max_pixels is None:
        max_pixels = MAX_PIXELS
    
    result: Dict[str, object] = {
        "success": False,
        "error": None,
        "raw_response": None,
        "layout_cells": None,
        "origin_image": None,
        "input_image": None,
        "processing_time_seconds": None,
        "empty_response": False,
    }
    
    start_time = time.time()
    try:
        origin_image = load_pdf_page_as_image(pdf_path, page_num=page_num)
        input_image = prepare_image(origin_image, min_pixels=min_pixels, max_pixels=max_pixels)
        
        result["origin_image"] = origin_image
        result["input_image"] = input_image
        
        raw_response = None
        for attempt in range(max_retries):
            raw_response = run_inference(
                input_image,
                prompt_text,
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
            result["error"] = f"Пустой ответ от сервера после {max_retries} попыток"
            result["empty_response"] = True
            result["processing_time_seconds"] = time.time() - start_time
            return result
        
        result["raw_response"] = raw_response
        
        parsed_cells, filtered = post_process_output(
            raw_response,
            "prompt_layout_only_en",
            origin_image,
            input_image,
            min_pixels=min_pixels,
            max_pixels=max_pixels,
        )
        
        if isinstance(parsed_cells, list):
            result["layout_cells"] = parsed_cells
            result["success"] = True
        else:
            result["error"] = "Не удалось распарсить JSON из ответа модели"
            result["filtered"] = filtered
            result["cleaned_output"] = parsed_cells
        
        result["processing_time_seconds"] = time.time() - start_time
        return result
    except Exception as exc:
        error_type = type(exc).__name__
        error_msg = str(exc)
        result["error"] = f"{error_type}: {error_msg}"
        result["processing_time_seconds"] = time.time() - start_time
        return result

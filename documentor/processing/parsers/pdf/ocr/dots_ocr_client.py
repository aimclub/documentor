"""
Клиент для прямого вызова Dots.OCR API.

Содержит функции для работы с Dots.OCR API напрямую,
используя тот же подход, что и в pdf_pipeline_dots_ocr.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Tuple
from io import BytesIO

from PIL import Image
import openai
import base64

# Загружаем переменные окружения из .env файла
from documentor.core.load_env import load_env_file
load_env_file()

# Импортируем утилиты из dots.ocr если доступны
try:
    _dots_ocr_path = Path(__file__).resolve().parents[5] / "dots.ocr"
    if _dots_ocr_path.exists():
        sys.path.insert(0, str(_dots_ocr_path))
    
    from dots_ocr.utils.consts import MIN_PIXELS, MAX_PIXELS
    from dots_ocr.utils.image_utils import fetch_image
    from dots_ocr.utils.layout_utils import post_process_output
except ImportError:
    MIN_PIXELS = None
    MAX_PIXELS = None
    fetch_image = None
    post_process_output = None


def _image_to_base64(image: Image.Image) -> str:
    """Конвертирует PIL Image в base64 data URL."""
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
    
    # Удаляем пробелы и проверяем base_url
    if base_url:
        base_url = base_url.strip()
        # Убеждаемся, что URL заканчивается на /v1 без пробелов
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
        raise ValueError("DOTS_OCR_BASE_URL не установлен или пуст")
    
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
    Выполняет layout detection для изображения.
    
    Args:
        image: Изображение для обработки (уже подготовленное через smart_resize)
        origin_image: Оригинальное изображение (для post_process_output)
        prompt: Промпт для layout detection
        base_url: Базовый URL API
        api_key: API ключ
        temperature: Температура генерации
        max_tokens: Максимальное число токенов
        model_name: Имя модели
        timeout: Таймаут запроса
        min_pixels: Минимальное число пикселей
        max_pixels: Максимальное число пикселей
        max_retries: Максимальное число попыток при пустом ответе
        retry_delay: Задержка между попытками
    
    Returns:
        tuple[Optional[list], Optional[str], bool]:
            - layout_cells: Список элементов layout или None
            - raw_response: Сырой ответ от модели или None
            - success: Успешность операции
    """
    import time
    
    if prompt is None:
        prompt = "Please output the layout information from this PDF image, including each layout's bbox and its category. The bbox should be in the format [x1, y1, x2, y2]. The layout categories for the PDF document include ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title']. Do not output the corresponding text. The layout result should be in JSON format."
    
    if origin_image is None:
        origin_image = image
    
    if min_pixels is None:
        min_pixels = MIN_PIXELS if MIN_PIXELS is not None else 100000
    if max_pixels is None:
        max_pixels = MAX_PIXELS if MAX_PIXELS is not None else 5000000
    
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
    
    if post_process_output is not None:
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
    else:
        # Если post_process_output недоступен, возвращаем сырой ответ
        return None, raw_response, False

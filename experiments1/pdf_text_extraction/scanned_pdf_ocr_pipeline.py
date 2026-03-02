"""
Пайплайн для OCR сканированных PDF.

1. DOTS OCR делает layout detection
2. Qwen2.5 получает на вход вырезанные элементы (заголовки, текст, таблицы) и делает OCR
3. Пропускаем page header (те же правила, что и для невыделяемого текста)
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from io import BytesIO

import fitz
from PIL import Image
import openai
import base64
from tqdm import tqdm

# Добавляем корень проекта в sys.path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


def load_env_file(env_file: Optional[Path] = None) -> None:
    """Загружает переменные окружения из .env файла."""
    if env_file is None:
        current_dir = Path.cwd()
        for parent in [current_dir] + list(current_dir.parents):
            env_file = parent / ".env"
            if env_file.exists():
                break
        else:
            return
    
    if not env_file.exists():
        return
    
    with open(env_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                if '#' in line:
                    line = line.split('#')[0].strip()
                    if not line:
                        continue
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                value = value.strip()
                if key and value and key not in os.environ:
                    os.environ[key] = value


load_env_file()

# Константы для OCR
MIN_PIXELS = 3136
MAX_PIXELS = 11289600
IMAGE_FACTOR = 28


def round_by_factor(number: int, factor: int) -> int:
    """Returns the closest integer to 'number' that is divisible by 'factor'."""
    return round(number / factor) * factor


def ceil_by_factor(number: int, factor: int) -> int:
    """Returns the smallest integer greater than or equal to 'number' that is divisible by 'factor'."""
    import math
    return math.ceil(number / factor) * factor


def floor_by_factor(number: int, factor: int) -> int:
    """Returns the largest integer less than or equal to 'number' that is divisible by 'factor'."""
    import math
    return math.floor(number / factor) * factor


def smart_resize(
    height: int,
    width: int,
    factor: int = 28,
    min_pixels: int = 3136,
    max_pixels: int = 11289600,
):
    """Rescales the image so that both dimensions are divisible by 'factor' and total pixels are within range."""
    import math
    if max(height, width) / min(height, width) > 200:
        raise ValueError(
            f"absolute aspect ratio must be smaller than 200, got {max(height, width) / min(height, width)}"
        )
    h_bar = max(factor, round_by_factor(height, factor))
    w_bar = max(factor, round_by_factor(width, factor))
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = max(factor, floor_by_factor(height / beta, factor))
        w_bar = max(factor, floor_by_factor(width / beta, factor))
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = ceil_by_factor(height * beta, factor)
        w_bar = ceil_by_factor(width * beta, factor)
        if h_bar * w_bar > max_pixels:
            beta = math.sqrt((h_bar * w_bar) / max_pixels)
            h_bar = max(factor, floor_by_factor(h_bar / beta, factor))
            w_bar = max(factor, floor_by_factor(w_bar / beta, factor))
    return h_bar, w_bar


def to_rgb(pil_image: Image.Image) -> Image.Image:
    """Конвертирует изображение в RGB формат."""
    if pil_image.mode == 'RGBA':
        white_background = Image.new("RGB", pil_image.size, (255, 255, 255))
        white_background.paste(pil_image, mask=pil_image.split()[3])
        return white_background
    else:
        return pil_image.convert("RGB")


def fetch_image(
    image, 
    min_pixels=None,
    max_pixels=None,
    resized_height=None,
    resized_width=None,
) -> Image.Image:
    """Загружает и обрабатывает изображение для OCR."""
    import copy
    import requests
    assert image is not None, f"image not found, maybe input format error: {image}"
    image_obj = None
    if isinstance(image, Image.Image):
        image_obj = image
    elif isinstance(image, str) and (image.startswith("http://") or image.startswith("https://")):
        with requests.get(image, stream=True) as response:
            response.raise_for_status()
            with BytesIO(response.content) as bio:
                image_obj = copy.deepcopy(Image.open(bio))
    elif isinstance(image, str) and image.startswith("file://"):
        image_obj = Image.open(image[7:])
    elif isinstance(image, str) and image.startswith("data:image"):
        if "base64," in image:
            _, base64_data = image.split("base64,", 1)
            data = base64.b64decode(base64_data)
            with BytesIO(data) as bio:
                image_obj = copy.deepcopy(Image.open(bio))
    elif isinstance(image, str):
        image_obj = Image.open(image)
    if image_obj is None:
        raise ValueError(f"Unrecognized image input, support local path, http url, base64 and PIL.Image, got {image}")
    image = to_rgb(image_obj)
    if resized_height and resized_width:
        resized_height, resized_width = smart_resize(
            resized_height,
            resized_width,
            factor=IMAGE_FACTOR,
        )
        assert resized_height>0 and resized_width>0, f"resized_height: {resized_height}, resized_width: {resized_width}"
        image = image.resize((resized_width, resized_height))
    elif min_pixels or max_pixels:
        width, height = image.size
        if not min_pixels:
            min_pixels = MIN_PIXELS
        if not max_pixels:
            max_pixels = MAX_PIXELS
        resized_height, resized_width = smart_resize(
            height,
            width,
            factor=IMAGE_FACTOR,
            min_pixels=min_pixels,
            max_pixels=max_pixels,
        )
        assert resized_height>0 and resized_width>0, f"resized_height: {resized_height}, resized_width: {resized_width}"
        image = image.resize((resized_width, resized_height))
    return image


def post_process_cells(
    origin_image: Image.Image, 
    cells: List[Dict], 
    input_width,
    input_height,
    factor: int = 28,
    min_pixels: int = 3136, 
    max_pixels: int = 11289600
) -> List[Dict]:
    """Post-processes cell bounding boxes, converting coordinates from resized to original dimensions."""
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
    """Пост-обработка ответа от OCR модели."""
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
        if logger:
            logger.error(f"cells post process error: {e}, when using {prompt_mode}")
        json_load_failed = True
    if json_load_failed:
        if logger:
            logger.warning(f"Не удалось распарсить JSON ответ, возвращаем исходный ответ")
    return response, True

logger = None
try:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
except:
    pass


class PdfPageRenderer:
    """Рендерер страниц PDF в изображения."""
    
    def __init__(
        self,
        render_scale: float = 2.0,
        optimize_for_ocr: bool = True,
        min_pixels: Optional[int] = None,
        max_pixels: Optional[int] = None,
    ) -> None:
        self.render_scale = render_scale
        self.optimize_for_ocr = optimize_for_ocr
        if min_pixels is None:
            min_pixels = MIN_PIXELS
        if max_pixels is None:
            max_pixels = MAX_PIXELS
        self.min_pixels = min_pixels
        self.max_pixels = max_pixels
    
    def render_page(
        self,
        pdf_path: Path,
        page_num: int,
        return_original: bool = False,
    ) -> Union[Image.Image, Tuple[Image.Image, Image.Image]]:
        """Рендерит одну страницу PDF в изображение."""
        pdf_document = fitz.open(str(pdf_path))
        try:
            page = pdf_document.load_page(page_num)
            mat = fitz.Matrix(self.render_scale, self.render_scale)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("ppm")
            original_image = Image.open(BytesIO(img_data)).convert("RGB")
            
            if self.optimize_for_ocr:
                optimized_image = fetch_image(
                    original_image,
                    min_pixels=self.min_pixels,
                    max_pixels=self.max_pixels,
                )
            else:
                optimized_image = original_image
            
            if return_original:
                return original_image, optimized_image
            return optimized_image
        finally:
            pdf_document.close()


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
    """Выполняет layout detection для изображения."""
    if prompt is None:
        prompt = "Please output the layout information from this PDF image, including each layout's bbox and its category. The bbox should be in the format [x1, y1, x2, y2]. The layout categories for the PDF document include ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title']. Do not output the corresponding text. The layout result should be in JSON format."
    
    if origin_image is None:
        origin_image = image
    
    if min_pixels is None:
        min_pixels = MIN_PIXELS
    if max_pixels is None:
        max_pixels = MAX_PIXELS
    
    # Получаем параметры из env
    if base_url is None:
        base_url_raw = os.getenv("DOTS_OCR_BASE_URL")
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
    
    if not base_url:
        raise ValueError("DOTS_OCR_BASE_URL не установлен")
    if not base_url.endswith("/v1"):
        if base_url.endswith("/"):
            base_url = f"{base_url}v1"
        else:
            base_url = f"{base_url}/v1"
    
    image_base64 = _image_to_base64(image)
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
    
    raw_response = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_completion_tokens=max_tokens,
            )
            raw_response = response.choices[0].message.content
            if raw_response and len(raw_response.strip()) > 0:
                break
        except Exception as e:
            if logger:
                logger.error(f"Ошибка layout detection (попытка {attempt + 1}): {e}")
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


def _image_to_base64(image: Image.Image) -> str:
    """Конвертирует PIL Image в base64 data URL."""
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def _crop_element_from_image(
    image: Image.Image,
    bbox: List[float],
    padding: int = 5
) -> Image.Image:
    """
    Вырезает элемент из изображения по bbox с небольшим отступом.
    
    Args:
        image: Исходное изображение
        bbox: [x1, y1, x2, y2] координаты
        padding: Отступ в пикселях
    
    Returns:
        Вырезанное изображение
    """
    x1, y1, x2, y2 = bbox
    
    # Добавляем отступы
    x1 = max(0, int(x1) - padding)
    y1 = max(0, int(y1) - padding)
    x2 = min(image.width, int(x2) + padding)
    y2 = min(image.height, int(y2) + padding)
    
    # Вырезаем
    cropped = image.crop((x1, y1, x2, y2))
    return cropped


def _ocr_element_with_qwen(
    element_image: Image.Image,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    model_name: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Optional[str]:
    """
    Выполняет OCR элемента через Qwen2.5 API.
    
    Args:
        element_image: Изображение элемента для OCR
        base_url: Базовый URL API (по умолчанию из env)
        api_key: API ключ (по умолчанию из env)
        temperature: Температура генерации (по умолчанию из env)
        max_tokens: Максимальное число токенов (по умолчанию из env)
        model_name: Имя модели (по умолчанию из env)
        timeout: Таймаут запроса в секундах (по умолчанию из env)
    
    Returns:
        Извлеченный текст или None в случае ошибки
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
    if api_key is None:
        api_key = os.getenv("QWEN_API_KEY")
    if temperature is None:
        temperature = float(os.getenv("QWEN_TEMPERATURE", "0.1"))
    if max_tokens is None:
        max_tokens = int(os.getenv("QWEN_MAX_TOKENS", "4096"))
    if model_name is None:
        model_name = os.getenv("QWEN_MODEL_NAME")
    if timeout is None:
        timeout = int(os.getenv("QWEN_TIMEOUT", "180"))
    
    if not base_url:
        raise ValueError("QWEN_BASE_URL не установлен")
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
    
    # Подготавливаем изображение
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
        if logger:
            logger.error(f"Ошибка OCR через Qwen: {e}")
        return None


def _filter_page_headers(layout_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Фильтрует Page-header элементы.
    
    Args:
        layout_elements: Список элементов layout
    
    Returns:
        Отфильтрованный список
    """
    filtered = []
    for element in layout_elements:
        category = element.get("category", "")
        if category == "Page-header":
            continue
        filtered.append(element)
    return filtered


def process_scanned_pdf(
    pdf_path: Path,
    output_dir: Path,
    render_scale: float = 2.0,
) -> Dict[str, any]:
    """
    Обрабатывает сканированный PDF через DOTS OCR + Qwen2.5 OCR.
    
    Args:
        pdf_path: Путь к PDF файлу
        output_dir: Директория для сохранения результатов
        render_scale: Масштаб рендеринга страниц
    
    Returns:
        Словарь с результатами обработки
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Инициализация компонентов
    renderer = PdfPageRenderer(
        render_scale=render_scale,
        optimize_for_ocr=True,
    )
    
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    doc.close()
    
    all_results = []
    all_elements = []
    
    print(f"Обработка PDF: {pdf_path.name}")
    print(f"Страниц: {total_pages}")
    print()
    
    # Обрабатываем каждую страницу
    for page_num in tqdm(range(total_pages), desc="Обработка страниц"):
        # Рендерим страницу
        original_image, optimized_image = renderer.render_page(
            pdf_path,
            page_num,
            return_original=True,
        )
        
        # Layout detection через DOTS OCR
        layout_elements, raw_response, success = process_layout_detection(
            image=optimized_image,
            origin_image=original_image,
        )
        
        if not success or not layout_elements:
            print(f"  Страница {page_num + 1}: не удалось получить layout")
            continue
        
        # Фильтруем page headers
        filtered_elements = _filter_page_headers(layout_elements)
        
        page_results = {
            "page_num": page_num + 1,
            "total_elements": len(layout_elements),
            "filtered_elements": len(filtered_elements),
            "elements": [],
        }
        
        # Обрабатываем каждый элемент
        for element in tqdm(filtered_elements, desc=f"  Страница {page_num + 1} OCR", leave=False):
            category = element.get("category", "")
            bbox = element.get("bbox", [])
            
            if not bbox or len(bbox) != 4:
                continue
            
            # Вырезаем элемент из оригинального изображения
            cropped_image = _crop_element_from_image(original_image, bbox)
            
            # OCR через Qwen2.5
            ocr_text = _ocr_element_with_qwen(cropped_image)
            
            element_result = {
                "category": category,
                "bbox": bbox,
                "text": ocr_text,
                "text_length": len(ocr_text) if ocr_text else 0,
            }
            
            page_results["elements"].append(element_result)
            all_elements.append({
                "page_num": page_num + 1,
                **element_result,
            })
        
        all_results.append(page_results)
    
    # Сохраняем результаты
    results_file = output_dir / f"{pdf_path.stem}_ocr_results.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    # Сохраняем все элементы в одном файле
    elements_file = output_dir / f"{pdf_path.stem}_all_elements.json"
    with open(elements_file, "w", encoding="utf-8") as f:
        json.dump(all_elements, f, ensure_ascii=False, indent=2)
    
    # Сохраняем полный текст
    full_text = "\n\n".join([
        elem.get("text", "") for elem in all_elements if elem.get("text")
    ])
    text_file = output_dir / f"{pdf_path.stem}_full_text.txt"
    with open(text_file, "w", encoding="utf-8") as f:
        f.write(full_text)
    
    # Статистика
    stats = {
        "total_pages": total_pages,
        "total_elements": len(all_elements),
        "elements_with_text": sum(1 for e in all_elements if e.get("text")),
        "total_text_length": sum(e.get("text_length", 0) for e in all_elements),
        "by_category": {},
    }
    
    for element in all_elements:
        category = element.get("category", "Unknown")
        if category not in stats["by_category"]:
            stats["by_category"][category] = {
                "count": 0,
                "with_text": 0,
                "total_text_length": 0,
            }
        stats["by_category"][category]["count"] += 1
        if element.get("text"):
            stats["by_category"][category]["with_text"] += 1
            stats["by_category"][category]["total_text_length"] += element.get("text_length", 0)
    
    stats_file = output_dir / f"{pdf_path.stem}_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    print()
    print("=" * 80)
    print("Результаты обработки:")
    print(f"  Страниц обработано: {stats['total_pages']}")
    print(f"  Всего элементов: {stats['total_elements']}")
    print(f"  Элементов с текстом: {stats['elements_with_text']}")
    print(f"  Общая длина текста: {stats['total_text_length']} символов")
    print()
    print("По категориям:")
    for category, cat_stats in stats["by_category"].items():
        print(f"  {category}: {cat_stats['count']} элементов, "
              f"{cat_stats['with_text']} с текстом, "
              f"{cat_stats['total_text_length']} символов")
    print()
    print(f"Результаты сохранены в: {output_dir}")
    
    return {
        "results": all_results,
        "elements": all_elements,
        "stats": stats,
    }


if __name__ == "__main__":
    pdf_path = Path("experiments/pdf_text_extraction/test_files/scanned_2506.10204v1.pdf")
    output_dir = Path("experiments/pdf_text_extraction/results/scanned_pdf_ocr")
    
    if not pdf_path.exists():
        print(f"Файл не найден: {pdf_path}")
        sys.exit(1)
    
    result = process_scanned_pdf(
        pdf_path=pdf_path,
        output_dir=output_dir,
    )

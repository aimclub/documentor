"""
Эксперимент для сравнения разных масштабов изображений при обработке через DOTS OCR.

Сравнивает три варианта:
- Оригинальный размер (x1)
- Увеличение в 2 раза (x2)
- Увеличение в 3 раза (x3)

Метрики сравнения:
- Количество найденных элементов
- Распределение по категориям
- Покрытие изображения bbox
- Средний размер bbox
- Время обработки
"""

import json
import os
import sys
import time

# Настройка кодировки для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from collections import Counter, defaultdict
from io import BytesIO

from PIL import Image
import openai
import base64

# Добавляем путь к dots.ocr в sys.path для импорта
_dots_ocr_path = Path(__file__).parent.parent.parent / "dots.ocr"
if _dots_ocr_path.exists():
    sys.path.insert(0, str(_dots_ocr_path))

try:
    from dots_ocr.utils.prompts import dict_promptmode_to_prompt
    HAS_PROMPTS = True
except ImportError:
    HAS_PROMPTS = False
    print("[WARNING] Не удалось импортировать dots_ocr.utils.prompts")

# Конфигурация из переменных окружения
DOTS_OCR_BASE_URL = os.getenv("DOTS_OCR_BASE_URL", "http://10.32.2.11:8069/v1")
DOTS_OCR_API_KEY = os.getenv("DOTS_OCR_API_KEY", "security-token-abc123")
_model_name_from_env = os.getenv("DOTS_OCR_MODEL_NAME", "")
if _model_name_from_env and _model_name_from_env != "правильное_имя_модели":
    DOTS_OCR_MODEL_NAME = _model_name_from_env
else:
    DOTS_OCR_MODEL_NAME = "/model"
DOTS_OCR_TEMPERATURE = float(os.getenv("DOTS_OCR_TEMPERATURE", "0.1"))
DOTS_OCR_MAX_TOKENS = int(os.getenv("DOTS_OCR_MAX_TOKENS", "65000"))
DOTS_OCR_TIMEOUT = int(os.getenv("DOTS_OCR_TIMEOUT", "120"))

# Промпт для layout detection
if HAS_PROMPTS:
    DEFAULT_PROMPT = dict_promptmode_to_prompt.get(
        "prompt_layout_only_en",
        "Please output the layout information from this PDF image, including each layout's bbox and its category. The bbox should be in the format [x1, y1, x2, y2]. The layout categories for the PDF document include ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title']. Do not output the corresponding text. The layout result should be in JSON format."
    )
else:
    DEFAULT_PROMPT = "Please output the layout information from this PDF image, including each layout's bbox and its category. The bbox should be in the format [x1, y1, x2, y2]. The layout categories for the PDF document include ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title']. Do not output the corresponding text. The layout result should be in JSON format."


def resize_image(image: Image.Image, scale: float) -> Image.Image:
    """Увеличивает изображение в указанное количество раз."""
    width, height = image.size
    new_size = (int(width * scale), int(height * scale))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def image_to_base64(image: Image.Image) -> str:
    """Конвертирует PIL Image в base64 data URL."""
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def send_image_to_dots_ocr(
    image: Image.Image,
    prompt: str = None,
) -> Dict[str, Any]:
    """
    Отправляет изображение в DOTS OCR API.
    
    Returns:
        dict с ключами:
        - success: bool
        - data: распарсенные данные layout
        - raw_response: сырой ответ от API
        - processing_time: время обработки в секундах
        - error: сообщение об ошибке (если success=False)
    """
    if prompt is None:
        prompt = DEFAULT_PROMPT
    
    # Создаем клиент
    client = openai.OpenAI(
        base_url=DOTS_OCR_BASE_URL,
        api_key=DOTS_OCR_API_KEY,
        timeout=DOTS_OCR_TIMEOUT
    )
    
    # Конвертируем изображение в base64
    image_base64 = image_to_base64(image)
    
    # Формируем сообщения
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_base64
                    }
                },
                {
                    "type": "text",
                    "text": f"<|img|><|imgpad|><|endofimg|>{prompt}"
                }
            ]
        }
    ]
    
    start_time = time.time()
    
    try:
        print(f"      Вызов API: model={DOTS_OCR_MODEL_NAME}, timeout={DOTS_OCR_TIMEOUT}с", flush=True)
        response = client.chat.completions.create(
            model=DOTS_OCR_MODEL_NAME,
            messages=messages,
            temperature=DOTS_OCR_TEMPERATURE,
            max_tokens=DOTS_OCR_MAX_TOKENS
        )
        print(f"      API ответ получен", flush=True)
        content = response.choices[0].message.content
        processing_time = time.time() - start_time
        
        # Парсим JSON ответ
        try:
            # Пытаемся найти JSON в ответе
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                layout_data = json.loads(json_str)
            else:
                # Если не нашли JSON, пытаемся распарсить весь ответ
                layout_data = json.loads(content)
        except json.JSONDecodeError:
            # Пытаемся найти JSON массив
            json_start = content.find('[')
            json_end = content.rfind(']') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                layout_data = json.loads(json_str)
            else:
                raise
        
        return {
            "success": True,
            "data": layout_data,
            "raw_response": content,
            "processing_time": processing_time
        }
        
    except openai.APIError as e:
        status_code = getattr(e, 'status_code', None)
        message = getattr(e, 'message', str(e))
        error_type = type(e).__name__
        processing_time = time.time() - start_time
        
        return {
            "success": False,
            "error": f"API Error ({error_type}): {status_code or ''} - {message}",
            "error_type": error_type,
            "status_code": status_code,
            "raw_response": "",
            "processing_time": processing_time
        }
    except Exception as e:
        processing_time = time.time() - start_time
        return {
            "success": False,
            "error": f"Error: {type(e).__name__}: {str(e)}",
            "error_type": type(e).__name__,
            "raw_response": "",
            "processing_time": processing_time
        }


def parse_layout_data(data: Any) -> List[Dict[str, Any]]:
    """Парсит данные layout из разных форматов ответа."""
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        # Ищем массив элементов в различных возможных ключах
        elements = data.get('elements', [])
        if not elements:
            elements = data.get('layout', [])
        if not elements:
            # Если это объект с одним ключом, который содержит массив
            for key, value in data.items():
                if isinstance(value, list):
                    return value
        return elements
    return []


def calculate_metrics(
    elements: List[Dict[str, Any]],
    image_size: Tuple[int, int]
) -> Dict[str, Any]:
    """Вычисляет метрики для найденных элементов."""
    if not elements:
        return {
            "total_elements": 0,
            "categories": {},
            "coverage_percent": 0.0,
            "avg_bbox_area": 0.0,
            "avg_bbox_width": 0.0,
            "avg_bbox_height": 0.0,
            "total_bbox_area": 0.0
        }
    
    image_width, image_height = image_size
    image_area = image_width * image_height
    
    categories = Counter()
    total_bbox_area = 0.0
    bbox_areas = []
    bbox_widths = []
    bbox_heights = []
    
    for elem in elements:
        if isinstance(elem, dict):
            category = elem.get('category', 'Unknown')
            categories[category] += 1
            
            bbox = elem.get('bbox', [])
            if len(bbox) == 4:
                x1, y1, x2, y2 = bbox
                width = max(0, x2 - x1)
                height = max(0, y2 - y1)
                area = width * height
                
                total_bbox_area += area
                bbox_areas.append(area)
                bbox_widths.append(width)
                bbox_heights.append(height)
    
    coverage_percent = (total_bbox_area / image_area * 100) if image_area > 0 else 0.0
    avg_bbox_area = sum(bbox_areas) / len(bbox_areas) if bbox_areas else 0.0
    avg_bbox_width = sum(bbox_widths) / len(bbox_widths) if bbox_widths else 0.0
    avg_bbox_height = sum(bbox_heights) / len(bbox_heights) if bbox_heights else 0.0
    
    return {
        "total_elements": len(elements),
        "categories": dict(categories),
        "coverage_percent": round(coverage_percent, 2),
        "avg_bbox_area": round(avg_bbox_area, 2),
        "avg_bbox_width": round(avg_bbox_width, 2),
        "avg_bbox_height": round(avg_bbox_height, 2),
        "total_bbox_area": round(total_bbox_area, 2),
        "image_area": image_area
    }


def process_image_with_scale(
    image_path: Path,
    scale: float,
    scale_name: str
) -> Dict[str, Any]:
    """Обрабатывает изображение с указанным масштабом."""
    print(f"  Обработка с масштабом {scale_name} (x{scale})...", flush=True)
    
    # Загружаем оригинальное изображение
    original_image = Image.open(image_path)
    original_size = original_image.size
    print(f"    Загружено изображение: {original_size[0]}x{original_size[1]}", flush=True)
    
    # Масштабируем изображение
    if scale == 1.0:
        scaled_image = original_image
    else:
        scaled_image = resize_image(original_image, scale)
    
    scaled_size = scaled_image.size
    print(f"    Масштабировано до: {scaled_size[0]}x{scaled_size[1]}", flush=True)
    
    # Отправляем в API
    print(f"    Отправка в DOTS OCR API...", flush=True)
    result = send_image_to_dots_ocr(scaled_image)
    print(f"    Получен ответ от API", flush=True)
    
    if not result["success"]:
        return {
            "scale": scale,
            "scale_name": scale_name,
            "success": False,
            "error": result.get("error", "Unknown error"),
            "processing_time": result.get("processing_time", 0.0),
            "original_size": original_size,
            "scaled_size": scaled_size
        }
    
    # Парсим данные
    layout_data = result["data"]
    elements = parse_layout_data(layout_data)
    
    # Вычисляем метрики
    metrics = calculate_metrics(elements, scaled_size)
    
    return {
        "scale": scale,
        "scale_name": scale_name,
        "success": True,
        "original_size": original_size,
        "scaled_size": scaled_size,
        "elements": elements,
        "metrics": metrics,
        "processing_time": result.get("processing_time", 0.0),
        "raw_response": result.get("raw_response", "")
    }


def compare_scales_for_image(image_path: Path, output_dir: Path) -> Dict[str, Any]:
    """Сравнивает три масштаба для одного изображения."""
    print(f"\nОбработка изображения: {image_path.name}", flush=True)
    
    scales = [
        (1.0, "original"),
        (2.0, "x2"),
        (3.0, "x3")
    ]
    
    results = {}
    
    for scale, scale_name in scales:
        print(f"  Начинаю обработку масштаба {scale_name}...", flush=True)
        result = process_image_with_scale(image_path, scale, scale_name)
        results[scale_name] = result
        
        if result["success"]:
            metrics = result["metrics"]
            print(f"    [OK] {scale_name}: {metrics['total_elements']} элементов, "
                  f"покрытие {metrics['coverage_percent']}%, "
                  f"время {result['processing_time']:.2f}с")
        else:
            print(f"    [ERROR] {scale_name}: Ошибка - {result.get('error', 'Unknown')}")
    
    # Сохраняем результаты
    image_stem = image_path.stem
    output_file = output_dir / f"{image_stem}_scale_comparison.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"  Результаты сохранены: {output_file}")
    
    return results


def create_summary_report(all_results: List[Dict[str, Any]], output_dir: Path):
    """Создает сводный отчет по всем изображениям."""
    summary = {
        "total_images": len(all_results),
        "scales": ["original", "x2", "x3"],
        "comparison": {
            "original": {"metrics": defaultdict(list), "success_count": 0},
            "x2": {"metrics": defaultdict(list), "success_count": 0},
            "x3": {"metrics": defaultdict(list), "success_count": 0}
        },
        "detailed_results": []
    }
    
    for image_result in all_results:
        image_name = image_result.get("image_name", "unknown")
        image_summary = {
            "image_name": image_name,
            "scales": {}
        }
        
        for scale_name in ["original", "x2", "x3"]:
            scale_result = image_result.get(scale_name, {})
            
            if scale_result.get("success", False):
                summary["comparison"][scale_name]["success_count"] += 1
                metrics = scale_result.get("metrics", {})
                
                # Собираем метрики для статистики
                summary["comparison"][scale_name]["metrics"]["total_elements"].append(
                    metrics.get("total_elements", 0)
                )
                summary["comparison"][scale_name]["metrics"]["coverage_percent"].append(
                    metrics.get("coverage_percent", 0.0)
                )
                summary["comparison"][scale_name]["metrics"]["processing_time"].append(
                    scale_result.get("processing_time", 0.0)
                )
                
                # Детальная информация для изображения
                image_summary["scales"][scale_name] = {
                    "success": True,
                    "total_elements": metrics.get("total_elements", 0),
                    "coverage_percent": metrics.get("coverage_percent", 0.0),
                    "categories": metrics.get("categories", {}),
                    "processing_time": scale_result.get("processing_time", 0.0),
                    "scaled_size": scale_result.get("scaled_size", (0, 0))
                }
            else:
                image_summary["scales"][scale_name] = {
                    "success": False,
                    "error": scale_result.get("error", "Unknown error")
                }
        
        summary["detailed_results"].append(image_summary)
    
    # Вычисляем средние значения
    for scale_name in ["original", "x2", "x3"]:
        scale_data = summary["comparison"][scale_name]
        metrics = scale_data["metrics"]
        
        if metrics["total_elements"]:
            scale_data["avg_total_elements"] = round(
                sum(metrics["total_elements"]) / len(metrics["total_elements"]), 2
            )
            scale_data["max_total_elements"] = max(metrics["total_elements"])
            scale_data["min_total_elements"] = min(metrics["total_elements"])
        
        if metrics["coverage_percent"]:
            scale_data["avg_coverage_percent"] = round(
                sum(metrics["coverage_percent"]) / len(metrics["coverage_percent"]), 2
            )
            scale_data["max_coverage_percent"] = round(max(metrics["coverage_percent"]), 2)
            scale_data["min_coverage_percent"] = round(min(metrics["coverage_percent"]), 2)
        
        if metrics["processing_time"]:
            scale_data["avg_processing_time"] = round(
                sum(metrics["processing_time"]) / len(metrics["processing_time"]), 2
            )
            scale_data["max_processing_time"] = round(max(metrics["processing_time"]), 2)
            scale_data["min_processing_time"] = round(min(metrics["processing_time"]), 2)
    
    # Сохраняем сводный отчет
    summary_file = output_dir / "scale_comparison_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print("СВОДНЫЙ ОТЧЕТ")
    print(f"{'='*60}")
    print(f"Всего изображений: {summary['total_images']}")
    print()
    
    for scale_name in ["original", "x2", "x3"]:
        scale_data = summary["comparison"][scale_name]
        print(f"Масштаб {scale_name}:")
        print(f"  Успешно обработано: {scale_data['success_count']}/{summary['total_images']}")
        if scale_data.get("avg_total_elements") is not None:
            print(f"  Среднее количество элементов: {scale_data['avg_total_elements']}")
            print(f"    (мин: {scale_data['min_total_elements']}, макс: {scale_data['max_total_elements']})")
        if scale_data.get("avg_coverage_percent") is not None:
            print(f"  Среднее покрытие: {scale_data['avg_coverage_percent']}%")
            print(f"    (мин: {scale_data['min_coverage_percent']}%, макс: {scale_data['max_coverage_percent']}%)")
        if scale_data.get("avg_processing_time") is not None:
            print(f"  Среднее время обработки: {scale_data['avg_processing_time']}с")
            print(f"    (мин: {scale_data['min_processing_time']}с, макс: {scale_data['max_processing_time']}с)")
        print()
    
    print(f"Полный отчет сохранен: {summary_file}")
    print(f"{'='*60}")


def main():
    """Основная функция для запуска эксперимента."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Сравнение разных масштабов изображений для DOTS OCR"
    )
    parser.add_argument(
        "input_dir",
        type=str,
        help="Путь к директории с изображениями для обработки"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Путь к директории для сохранения результатов (по умолчанию: input_dir/../scale_comparison_results)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Ограничить количество обрабатываемых изображений"
    )
    
    args = parser.parse_args()
    
    # Определяем базовую директорию скрипта
    script_dir = Path(__file__).parent.resolve()
    
    # Обрабатываем входной путь
    input_dir_str = args.input_dir
    input_dir = None
    
    # Пробуем разные варианты пути
    candidates = []
    
    # 1. Как абсолютный путь
    candidates.append(Path(input_dir_str).resolve())
    
    # 2. Относительно текущей рабочей директории
    candidates.append(Path.cwd() / input_dir_str)
    
    # 3. Относительно директории скрипта
    candidates.append(script_dir / input_dir_str)
    
    # 4. Относительно директории results (если запускаем из корня проекта)
    project_root = script_dir.parent.parent
    if "results" in input_dir_str:
        # Если путь содержит results/, пробуем относительно корня проекта
        if "results/" in input_dir_str:
            candidates.append(project_root / input_dir_str)
            # Или относительно директории скрипта
            rel_path = input_dir_str.split("results/", 1)[-1]
            candidates.append(script_dir / "results" / rel_path)
        else:
            candidates.append(project_root / input_dir_str)
    
    # Ищем первый существующий путь
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            input_dir = candidate
            break
    
    if input_dir is None:
        print(f"Ошибка: директория '{input_dir_str}' не найдена")
        print(f"Проверялись следующие пути:")
        for i, cand in enumerate(candidates, 1):
            exists = "[OK]" if cand.exists() else "[NOT FOUND]"
            print(f"  {i}. {exists} {cand}")
        print(f"\nТекущая рабочая директория: {Path.cwd()}")
        print(f"Директория скрипта: {script_dir}")
        return
    
    # Обрабатываем выходной путь
    if args.output_dir:
        output_dir = Path(args.output_dir)
        if not output_dir.is_absolute():
            output_dir = script_dir / output_dir
    else:
        # По умолчанию создаем в родительской директории входной директории
        output_dir = input_dir.parent / "scale_comparison_results"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Находим все изображения
    image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
    image_files = [
        f for f in input_dir.iterdir()
        if f.suffix.lower() in image_extensions and f.is_file()
    ]
    
    if not image_files:
        print(f"Ошибка: не найдено изображений в директории {input_dir}")
        return
    
    if args.limit:
        image_files = image_files[:args.limit]
    
    print(f"Найдено изображений: {len(image_files)}", flush=True)
    print(f"Выходная директория: {output_dir}", flush=True)
    print(f"Используемая модель: {DOTS_OCR_MODEL_NAME}", flush=True)
    print(f"API URL: {DOTS_OCR_BASE_URL}", flush=True)
    print(flush=True)
    
    all_results = []
    
    for i, image_path in enumerate(image_files, 1):
        print(f"[{i}/{len(image_files)}]", flush=True)
        results = compare_scales_for_image(image_path, output_dir)
        results["image_name"] = image_path.name
        all_results.append(results)
    
    # Создаем сводный отчет
    create_summary_report(all_results, output_dir)
    
    print("\nЭксперимент завершен!")


if __name__ == "__main__":
    main()

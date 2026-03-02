"""
Скрипт для layout detection через dots.ocr.

На вход: изображения или PDF файлы из директории.
На выход: изображение с bbox, JSON с layout, raw-ответ от LLM.

Для PDF: увеличение 2x делается на стадии рендеринга через fitz.Matrix(2.0, 2.0),
затем применяется smart_resize через fetch_image для приведения к размеру кратному 28
в рамках MIN/MAX_PIXELS.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from io import BytesIO

from PIL import Image
import openai
import fitz
_dots_ocr_path = Path(__file__).resolve().parents[2] / "dots.ocr"
if _dots_ocr_path.exists():
    sys.path.insert(0, str(_dots_ocr_path))

try:
    from dots_ocr.utils.consts import image_extensions, MIN_PIXELS, MAX_PIXELS
    from dots_ocr.utils.image_utils import fetch_image
    from dots_ocr.utils.layout_utils import draw_layout_on_image, post_process_output
except ImportError as exc:
    raise SystemExit(
        f"Не удалось импортировать dots_ocr. Проверьте путь { _dots_ocr_path }: {exc}"
    ) from exc

DEFAULT_INPUT_DIR = (
    Path(__file__).parent / "results" / "dots_ocr_test" / "temp_images"
)
DEFAULT_OUTPUT_DIR = (
    Path(__file__).parent / "results" / "dots_ocr_test" / "layout_detection"
)

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


def _iter_files(input_dir: Path) -> Iterable[Path]:
    """Итерирует по изображениям и PDF файлам в директории."""
    patterns = []
    for ext in image_extensions:
        if ext.startswith("."):
            patterns.append(f"*{ext}")
        else:
            patterns.append(f"*.{ext}")
    patterns.append("*.pdf")
    
    for pattern in patterns:
        for path in sorted(input_dir.glob(pattern)):
            if path.is_file():
                yield path




def _save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text)


def _save_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _load_pdf_page_as_image(pdf_path: Path, page_num: int = 0) -> Image.Image:
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


def _prepare_images(
    file_path: Path, min_pixels: Optional[int], max_pixels: Optional[int]
) -> Tuple[Image.Image, Image.Image]:
    """Подготавливает изображение для обработки. Для PDF рендерит с увеличением 2x, затем применяет smart_resize."""
    if file_path.suffix.lower() == ".pdf":
        origin_image = _load_pdf_page_as_image(file_path, page_num=0)
    else:
        origin_image = Image.open(file_path).convert("RGB")
    
    input_image = fetch_image(
        origin_image,
        min_pixels=min_pixels,
        max_pixels=max_pixels,
    )
    return origin_image, input_image


def _run_inference(
    input_image: Image.Image,
    prompt: str,
    base_url: str,
    api_key: str,
    temperature: float,
    max_tokens: int,
    model_name: str,
    timeout: int,
) -> Optional[str]:
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
        usage = getattr(response, 'usage', None)
        completion_tokens = getattr(usage, 'completion_tokens', None) if usage else None
        prompt_tokens = getattr(usage, 'prompt_tokens', None) if usage else None
        finish_reason = getattr(response.choices[0], 'finish_reason', None)
        
        if not content or len(content.strip()) == 0:
            print(f"[WARN] Пустой ответ от сервера!")
            print(f"  - Content length: {len(content) if content else 0} chars")
            print(f"  - Completion tokens: {completion_tokens} (если 1, значит модель сразу выдала EOS)")
            print(f"  - Prompt tokens: {prompt_tokens}")
            print(f"  - Finish reason: {finish_reason}")
        else:
            print(f"[DEBUG] Response: {len(content)} chars, completion_tokens={completion_tokens}")
        
        return content
    except openai.BadRequestError as exc:
        message = str(exc)
        print(f"[ERROR] BadRequestError: {message}")
        if ("max_completion_tokens" in message or "max_tokens" in message) and "maximum context length" in message:
            reduced_tokens = max(256, max_tokens - 1024)
            if reduced_tokens >= max_tokens:
                raise
            print(
                f"[WARN] max_completion_tokens слишком большой ({max_tokens}). "
                f"Повторяем с {reduced_tokens}."
            )
            retry_params = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_completion_tokens": reduced_tokens,
            }

            response = client.chat.completions.create(**retry_params)
            return response.choices[0].message.content
        raise
    except openai.APITimeoutError as exc:
        print(f"[ERROR] TimeoutError: {exc}")
        print(f"  - Таймаут: {timeout} секунд")
        raise
    except Exception as exc:
        print(f"[ERROR] Неожиданная ошибка в _run_inference: {type(exc).__name__}: {exc}")
        raise


def _image_to_base64(image: Image.Image) -> str:
    import base64

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def _process_image(
    image_path: Path,
    output_dir: Path,
    prompt_text: str,
    base_url: str,
    api_key: str,
    temperature: float,
    max_tokens: int,
    model_name: str,
    timeout: int,
    min_pixels: Optional[int],
    max_pixels: Optional[int],
) -> Dict[str, object]:
    image_stem = image_path.stem
    result: Dict[str, object] = {
        "image_path": str(image_path),
        "success": False,
        "error": None,
        "output": {},
        "processing_time_seconds": None,
        "empty_response": False,
    }

    start_time = time.time()
    try:
        print(f"\n[INFO] Обработка: {image_path.name}")
        file_type = "PDF" if image_path.suffix.lower() == ".pdf" else "Image"
        print(f"  - Тип файла: {file_type}")
        
        origin_image, input_image = _prepare_images(
            image_path, min_pixels=min_pixels, max_pixels=max_pixels
        )
        print(f"  - Размер после рендеринга (PDF 2x) / загрузки: {origin_image.size}")
        print(f"  - Размер после smart_resize (fetch_image): {input_image.size}")
        
        prompt = prompt_text or DEFAULT_PROMPT_TEXT

        max_retries = 3
        retry_delay = 2
        raw_response = None
        
        for attempt in range(max_retries):
            raw_response = _run_inference(
                input_image,
                prompt,
                base_url=base_url,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                model_name=model_name,
                timeout=timeout,
            )
            
            if raw_response and len(raw_response.strip()) > 0:
                if attempt > 0:
                    print(f"[INFO] Успешный ответ получен с попытки {attempt + 1}")
                break
            else:
                if attempt < max_retries - 1:
                    print(f"[WARN] Пустой ответ, повторная попытка {attempt + 2}/{max_retries} через {retry_delay} сек...")
                    time.sleep(retry_delay)
                else:
                    print(f"[ERROR] Все {max_retries} попыток завершились пустым ответом")
        
        if raw_response is None or len(raw_response.strip()) == 0:
            result["error"] = f"Пустой ответ от сервера после {max_retries} попыток (content: {repr(raw_response)})"
            result["empty_response"] = True
            result["processing_time_seconds"] = time.time() - start_time
            print(f"[ERROR] {result['error']}")
            return result

        raw_dir = output_dir / "raw"
        json_dir = output_dir / "json"
        images_dir = output_dir / "images"
        raw_dir.mkdir(parents=True, exist_ok=True)
        json_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)

        raw_path = raw_dir / f"{image_stem}_raw.txt"
        _save_text(raw_path, raw_response)

        parsed_cells, filtered = post_process_output(
            raw_response,
            "prompt_layout_only_en",
            origin_image,
            input_image,
            min_pixels=min_pixels,
            max_pixels=max_pixels,
        )

        json_path = json_dir / f"{image_stem}_layout.json"
        if isinstance(parsed_cells, list):
            _save_json(json_path, parsed_cells)
            cells_for_draw = parsed_cells
        else:
            _save_json(
                json_path,
                {
                    "error": "json_parse_failed",
                    "filtered": filtered,
                    "cleaned_output": parsed_cells,
                },
            )
            cells_for_draw = []

        image_output_path = images_dir / f"{image_stem}_with_bbox.png"
        if cells_for_draw:
            image_with_bbox = draw_layout_on_image(origin_image, cells_for_draw)
            image_with_bbox.save(image_output_path)
        else:
            origin_image.save(image_output_path)

        result["success"] = True
        result["output"] = {
            "image_with_bbox": str(image_output_path),
            "json": str(json_path),
            "raw_response": str(raw_path),
        }
        result["filtered"] = filtered
        result["processing_time_seconds"] = time.time() - start_time
        return result
    except Exception as exc:
        error_type = type(exc).__name__
        error_msg = str(exc)
        result["error"] = f"{error_type}: {error_msg}"
        result["processing_time_seconds"] = time.time() - start_time
        print(f"[ERROR] Ошибка при обработке {image_path.name}: {result['error']}")
        import traceback
        print(f"[ERROR] Traceback:\n{traceback.format_exc()}")
        return result


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Layout detection через dots.ocr для папки с изображениями или PDF файлами"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Входная директория с изображениями или PDF файлами",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Выходная директория",
    )
    parser.add_argument(
        "--prompt-text",
        type=str,
        default=DEFAULT_PROMPT_TEXT,
        help="Промпт для layout detection (по умолчанию: layout-only без текста)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=DOTS_OCR_BASE_URL,
        help="Базовый URL API dots.ocr, например http://host:8069/v1",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=DOTS_OCR_API_KEY,
        help="API key для dots.ocr",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default=DOTS_OCR_MODEL_NAME,
    )
    parser.add_argument("--temperature", type=float, default=DOTS_OCR_TEMPERATURE)
    parser.add_argument("--max-tokens", type=int, default=DOTS_OCR_MAX_TOKENS)
    parser.add_argument("--timeout", type=int, default=DOTS_OCR_TIMEOUT)
    parser.add_argument(
        "--min-pixels",
        type=int,
        default=MIN_PIXELS,
        help="Минимальное число пикселей при ресайзе",
    )
    parser.add_argument(
        "--max-pixels",
        type=int,
        default=MAX_PIXELS,
        help="Максимальное число пикселей при ресайзе",
    )
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()

    input_dir = args.input_dir
    output_dir = args.output_dir
    prompt_text = args.prompt_text.strip() if args.prompt_text else DEFAULT_PROMPT_TEXT

    if not input_dir.exists():
        raise SystemExit(f"Входная директория не найдена: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    files = list(_iter_files(input_dir))
    if not files:
        raise SystemExit(f"В директории нет изображений или PDF: {input_dir}")

    print(f"[INFO] Найдено файлов: {len(files)}")
    print(f"[INFO] Вход: {input_dir}")
    print(f"[INFO] Выход: {output_dir}")

    total_start_time = time.time()
    results: List[Dict[str, object]] = []
    for file_path in files:
        result = _process_image(
            image_path=file_path,
            output_dir=output_dir,
            prompt_text=prompt_text,
            base_url=args.base_url,
            api_key=args.api_key,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            model_name=args.model_name,
            timeout=args.timeout,
            min_pixels=args.min_pixels,
            max_pixels=args.max_pixels,
        )
        results.append(result)
        processing_time = result.get("processing_time_seconds")
        time_str = f" ({processing_time:.2f}s)" if processing_time else ""
        if result["success"]:
            print(f"[OK] {file_path.name}{time_str}")
        else:
            print(f"[FAIL] {file_path.name}{time_str}: {result.get('error')}")

    total_time = time.time() - total_start_time
    
    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    empty_responses = [r for r in results if r.get("empty_response", False)]
    
    failed_files = [r["image_path"] for r in failed]
    
    total_processing_time = sum(
        r.get("processing_time_seconds", 0) for r in results 
        if r.get("processing_time_seconds") is not None
    )
    avg_processing_time = total_processing_time / len(results) if results else 0
    
    metrics = {
        "total": len(files),
        "successful": len(successful),
        "failed": len(failed),
        "empty_responses": len(empty_responses),
        "total_time_seconds": round(total_time, 2),
        "total_processing_time_seconds": round(total_processing_time, 2),
        "average_processing_time_seconds": round(avg_processing_time, 2),
        "failed_files": failed_files,
    }
    
    print("\n" + "=" * 60)
    print("[METRICS] Сводка выполнения:")
    print(f"  Всего файлов: {metrics['total']}")
    print(f"  Успешно: {metrics['successful']}")
    print(f"  Ошибок: {metrics['failed']}")
    print(f"  Пустых ответов: {metrics['empty_responses']}")
    print(f"  Общее время выполнения: {metrics['total_time_seconds']:.2f} сек")
    print(f"  Суммарное время обработки: {metrics['total_processing_time_seconds']:.2f} сек")
    print(f"  Среднее время на файл: {metrics['average_processing_time_seconds']:.2f} сек")
    if failed_files:
        print(f"\n  Ошибочные файлы ({len(failed_files)}):")
        for file_path in failed_files:
            print(f"    - {Path(file_path).name}")
    print("=" * 60)

    summary_path = output_dir / "summary.json"
    _save_json(summary_path, {
        "metrics": metrics,
        "results": results
    })
    print(f"[INFO] Сводка сохранена в {summary_path}")


if __name__ == "__main__":
    main()

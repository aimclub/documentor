#!/usr/bin/env python3
"""
Пайплайн для сравнения двух методов извлечения текста:
1. Метод 1: prompt_layout_all_en - Dots OCR извлекает layout и текст
2. Метод 2: prompt_layout_only_en - Dots OCR извлекает только layout, затем Qwen OCR извлекает текст

Сравнение с ground truth (текст из PDF по координатам).
Вычисление метрик CER (Character Error Rate) и WER (Word Error Rate).
"""

import sys
import json
import io
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image
from tqdm import tqdm

# Добавляем путь к корню проекта
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import fitz  # PyMuPDF
from documentor.ocr.dots_ocr import load_prompts_from_config
from documentor.processing.parsers.pdf.ocr.dots_ocr_client import process_layout_detection
from documentor.processing.parsers.pdf.ocr.qwen_ocr import ocr_text_with_qwen

# Для вычисления метрик
try:
    import jiwer
    HAS_JIWER = True
except ImportError:
    HAS_JIWER = False
    print("Предупреждение: jiwer не установлен. Установите: pip install jiwer")


def normalize_text(text: str) -> str:
    """
    Нормализует текст для более справедливого сравнения.
    
    Удаляет:
    - Markdown форматирование (**bold**, *italic*)
    - Лишние пробелы и переносы строк
    - Приводит к единому формату
    
    Args:
        text: Исходный текст
    
    Returns:
        Нормализованный текст
    """
    if not text:
        return ""
    
    # Удаляем markdown форматирование
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # **bold** -> bold
    text = re.sub(r'\*([^*]+)\*', r'\1', text)      # *italic* -> italic
    text = re.sub(r'__([^_]+)__', r'\1', text)      # __bold__ -> bold
    text = re.sub(r'_([^_]+)_', r'\1', text)        # _italic_ -> italic
    
    # Заменяем переносы строк на пробелы
    text = text.replace('\n', ' ')
    text = text.replace('\r', ' ')
    
    # Нормализуем пробелы (множественные -> один)
    text = re.sub(r'\s+', ' ', text)
    
    # Убираем пробелы в начале и конце
    text = text.strip()
    
    return text


def extract_ground_truth_text(
    pdf_path: Path,
    bbox: List[float],
    page_num: int,
    render_scale: float = 2.0
) -> str:
    """
    Извлекает текст из PDF по координатам (ground truth).
    
    Args:
        pdf_path: Путь к PDF файлу
        bbox: Координаты [x1, y1, x2, y2] в масштабе render_scale
        page_num: Номер страницы (0-based)
        render_scale: Масштаб рендеринга для координат
    
    Returns:
        Извлеченный текст
    """
    pdf_doc = fitz.open(str(pdf_path))
    try:
        if page_num >= len(pdf_doc):
            return ""
        
        page = pdf_doc[page_num]
        
        # Конвертируем координаты из render_scale в PDF координаты
        x1, y1, x2, y2 = bbox
        pdf_x1 = x1 / render_scale
        pdf_y1 = y1 / render_scale
        pdf_x2 = x2 / render_scale
        pdf_y2 = y2 / render_scale
        
        rect = fitz.Rect(pdf_x1, pdf_y1, pdf_x2, pdf_y2)
        
        # Пытаемся извлечь текст
        text = page.get_textbox(rect).strip()
        
        # Если не получилось, пробуем другой метод
        if not text or len(text) < 2:
            text_dict = page.get_text("dict", clip=rect)
            text_parts = []
            
            for block in text_dict.get("blocks", []):
                if "lines" not in block:
                    continue
                for line in block["lines"]:
                    for span in line.get("spans", []):
                        text_parts.append(span.get("text", ""))
            
            text = " ".join(text_parts).strip()
        
        # Последний fallback
        if not text or len(text) < 2:
            text = page.get_text("text", clip=rect).strip()
        
        return text
    finally:
        pdf_doc.close()


def method1_layout_all(
    pdf_path: Path,
    render_scale: float = 2.0
) -> List[Dict[str, Any]]:
    """
    Метод 1: Использует prompt_layout_all_en.
    Dots OCR извлекает layout и текст одновременно.
    
    Args:
        pdf_path: Путь к PDF файлу
        render_scale: Масштаб рендеринга
    
    Returns:
        Список элементов с текстом
    """
    # Загружаем промпт
    config_path = project_root / "documentor" / "config" / "ocr_config.yaml"
    prompts = load_prompts_from_config(config_path)
    prompt = prompts.get("prompt_layout_all_en")
    
    if not prompt:
        raise ValueError("Промпт prompt_layout_all_en не найден в конфиге")
    
    pdf_doc = fitz.open(str(pdf_path))
    results = []
    
    try:
        for page_num in tqdm(range(len(pdf_doc)), desc="Метод 1: обработка страниц", leave=False):
            # Рендерим страницу
            page = pdf_doc[page_num]
            mat = fitz.Matrix(render_scale, render_scale)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            page_image = Image.open(io.BytesIO(img_data))
            
            # Вызываем layout detection с промптом layout_all
            layout_cells, raw_response, success = process_layout_detection(
                image=page_image,
                origin_image=page_image,
                prompt=prompt,
            )
            
            if not success or layout_cells is None:
                tqdm.write(f"  ⚠ Ошибка на странице {page_num + 1}")
                continue
            
            # Фильтруем только текстовые блоки
            for elem in layout_cells:
                category = elem.get("category", "")
                if category == "Text":
                    bbox = elem.get("bbox", [])
                    text = elem.get("text", "")
                    
                    results.append({
                        "page_num": page_num,
                        "bbox": bbox,
                        "text": text,
                        "method": "layout_all_en"
                    })
    finally:
        pdf_doc.close()
    
    return results


def method2_layout_only_qwen(
    pdf_path: Path,
    render_scale: float = 2.0
) -> List[Dict[str, Any]]:
    """
    Метод 2: Использует prompt_layout_only_en + Qwen OCR.
    Dots OCR извлекает только layout, затем Qwen OCR извлекает текст.
    
    Args:
        pdf_path: Путь к PDF файлу
        render_scale: Масштаб рендеринга
    
    Returns:
        Список элементов с текстом
    """
    # Загружаем промпт
    config_path = project_root / "documentor" / "config" / "ocr_config.yaml"
    prompts = load_prompts_from_config(config_path)
    prompt = prompts.get("prompt_layout_only_en")
    
    if not prompt:
        raise ValueError("Промпт prompt_layout_only_en не найден в конфиге")
    
    pdf_doc = fitz.open(str(pdf_path))
    results = []
    
    try:
        for page_num in tqdm(range(len(pdf_doc)), desc="Метод 2: обработка страниц", leave=False):
            # Рендерим страницу
            page = pdf_doc[page_num]
            mat = fitz.Matrix(render_scale, render_scale)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            page_image = Image.open(io.BytesIO(img_data))
            
            # Вызываем layout detection с промптом layout_only
            layout_cells, raw_response, success = process_layout_detection(
                image=page_image,
                origin_image=page_image,
                prompt=prompt,
            )
            
            if not success or layout_cells is None:
                tqdm.write(f"  ⚠ Ошибка на странице {page_num + 1}")
                continue
            
            # Фильтруем только текстовые блоки и извлекаем текст через Qwen OCR
            text_blocks = [elem for elem in layout_cells if elem.get("category", "") == "Text"]
            
            for elem in tqdm(text_blocks, desc=f"  Страница {page_num + 1}: OCR", leave=False):
                bbox = elem.get("bbox", [])
                
                # Обрезаем область из изображения
                x1, y1, x2, y2 = bbox
                padding = 5
                x1_crop = max(0, int(x1) - padding)
                y1_crop = max(0, int(y1) - padding)
                x2_crop = min(page_image.width, int(x2) + padding)
                y2_crop = min(page_image.height, int(y2) + padding)
                
                cropped_image = page_image.crop((x1_crop, y1_crop, x2_crop, y2_crop))
                
                # OCR через Qwen с увеличенным таймаутом
                text = ocr_text_with_qwen(cropped_image, timeout=300)  # 300 секунд = 5 минут
                text = text.strip() if text else ""
                
                results.append({
                    "page_num": page_num,
                    "bbox": bbox,
                    "text": text,
                    "method": "layout_only_en_qwen"
                })
    finally:
        pdf_doc.close()
    
    return results


def calculate_metrics(
    ground_truth: str,
    predicted: str
) -> Dict[str, float]:
    """
    Вычисляет метрики CER и WER.
    
    Args:
        ground_truth: Ground truth текст (уже нормализованный)
        predicted: Предсказанный текст (уже нормализованный)
    
    Returns:
        Словарь с метриками
    """
    # Нормализуем тексты перед сравнением
    gt_norm = normalize_text(ground_truth)
    pred_norm = normalize_text(predicted)
    
    if HAS_JIWER:
        # Используем jiwer для вычисления метрик
        # CER (Character Error Rate)
        cer = jiwer.cer(gt_norm, pred_norm)
        
        # WER (Word Error Rate)
        wer = jiwer.wer(gt_norm, pred_norm)
        
        return {
            "cer": cer,
            "wer": wer
        }
    else:
        # Простая реализация без jiwer
        # CER - отношение неправильных символов к общему количеству
        from difflib import SequenceMatcher
        similarity = SequenceMatcher(None, gt_norm, pred_norm).ratio()
        cer = 1.0 - similarity
        
        return {
            "cer": cer,
            "wer": None  # WER требует токенизации
        }


def process_pdf(
    pdf_path: Path,
    output_dir: Path,
    render_scale: float = 2.0
) -> Dict[str, Any]:
    """
    Обрабатывает PDF файл обоими методами и вычисляет метрики.
    
    Args:
        pdf_path: Путь к PDF файлу
        output_dir: Директория для сохранения результатов
        render_scale: Масштаб рендеринга
    
    Returns:
        Словарь с результатами
    """
    print(f"\n{'='*60}")
    print(f"Обработка: {pdf_path.name}")
    print(f"{'='*60}")
    
    start_time_total = time.time()
    
    # Метод 1
    print("\nМетод 1: prompt_layout_all_en...")
    start_time_method1 = time.time()
    method1_results = method1_layout_all(pdf_path, render_scale)
    time_method1 = time.time() - start_time_method1
    print(f"  Найдено текстовых блоков: {len(method1_results)}")
    print(f"  Время выполнения: {time_method1:.2f} сек ({time_method1/60:.2f} мин)")
    
    # Метод 2
    print("\nМетод 2: prompt_layout_only_en + Qwen OCR...")
    start_time_method2 = time.time()
    method2_results = method2_layout_only_qwen(pdf_path, render_scale)
    time_method2 = time.time() - start_time_method2
    print(f"  Найдено текстовых блоков: {len(method2_results)}")
    print(f"  Время выполнения: {time_method2:.2f} сек ({time_method2/60:.2f} мин)")
    
    # Извлекаем ground truth для всех блоков
    print("\nИзвлечение ground truth...")
    all_bboxes = set()
    for result in method1_results + method2_results:
        bbox_tuple = tuple(result["bbox"])
        all_bboxes.add((result["page_num"], bbox_tuple))
    
    start_time_gt = time.time()
    ground_truth_data = {}
    for page_num, bbox in tqdm(all_bboxes, desc="Извлечение ground truth"):
        gt_text = extract_ground_truth_text(pdf_path, list(bbox), page_num, render_scale)
        ground_truth_data[(page_num, bbox)] = gt_text
    time_gt = time.time() - start_time_gt
    print(f"  Извлечено ground truth для {len(ground_truth_data)} блоков")
    print(f"  Время выполнения: {time_gt:.2f} сек")
    
    # Вычисляем метрики для метода 1
    print("\nВычисление метрик для метода 1...")
    start_time_metrics1 = time.time()
    method1_metrics = []
    for result in tqdm(method1_results, desc="Обработка блоков метода 1", leave=False):
        bbox_tuple = tuple(result["bbox"])
        gt_text = ground_truth_data.get((result["page_num"], bbox_tuple), "")
        pred_text = result["text"]
        
        if gt_text:  # Только если есть ground truth
            metrics = calculate_metrics(gt_text, pred_text)
            metrics["page_num"] = result["page_num"]
            metrics["bbox"] = result["bbox"]
            metrics["ground_truth"] = gt_text
            metrics["predicted"] = pred_text
            method1_metrics.append(metrics)
    time_metrics1 = time.time() - start_time_metrics1
    print(f"  Время вычисления метрик: {time_metrics1:.2f} сек")
    
    # Вычисляем метрики для метода 2
    print("Вычисление метрик для метода 2...")
    start_time_metrics2 = time.time()
    method2_metrics = []
    for result in tqdm(method2_results, desc="Обработка блоков метода 2", leave=False):
        bbox_tuple = tuple(result["bbox"])
        gt_text = ground_truth_data.get((result["page_num"], bbox_tuple), "")
        pred_text = result["text"]
        
        if gt_text:  # Только если есть ground truth
            metrics = calculate_metrics(gt_text, pred_text)
            metrics["page_num"] = result["page_num"]
            metrics["bbox"] = result["bbox"]
            metrics["ground_truth"] = gt_text
            metrics["predicted"] = pred_text
            method2_metrics.append(metrics)
    time_metrics2 = time.time() - start_time_metrics2
    print(f"  Время вычисления метрик: {time_metrics2:.2f} сек")
    
    # Агрегированные метрики
    def aggregate_metrics(metrics_list):
        if not metrics_list:
            return {}
        
        avg_cer = sum(m["cer"] for m in metrics_list) / len(metrics_list)
        avg_wer_list = [m["wer"] for m in metrics_list if m.get("wer") is not None]
        avg_wer = sum(avg_wer_list) / len(avg_wer_list) if avg_wer_list else None
        
        return {
            "avg_cer": avg_cer,
            "avg_wer": avg_wer,
            "total_blocks": len(metrics_list)
        }
    
    method1_agg = aggregate_metrics(method1_metrics)
    method2_agg = aggregate_metrics(method2_metrics)
    
    # Общее время
    time_total = time.time() - start_time_total
    
    # Сохраняем результаты
    pdf_name = pdf_path.stem
    results = {
        "pdf_file": pdf_path.name,
        "timing": {
            "method1_seconds": time_method1,
            "method2_seconds": time_method2,
            "ground_truth_seconds": time_gt,
            "metrics1_seconds": time_metrics1,
            "metrics2_seconds": time_metrics2,
            "total_seconds": time_total,
            "method1_minutes": time_method1 / 60,
            "method2_minutes": time_method2 / 60,
            "total_minutes": time_total / 60
        },
        "method1": {
            "results": method1_results,
            "metrics": method1_metrics,
            "aggregated": method1_agg,
            "timing_seconds": time_method1
        },
        "method2": {
            "results": method2_results,
            "metrics": method2_metrics,
            "aggregated": method2_agg,
            "timing_seconds": time_method2
        },
        "ground_truth": {
            str(k): v for k, v in ground_truth_data.items()
        }
    }
    
    # Сохраняем JSON
    json_path = output_dir / f"{pdf_name}_results.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Результаты сохранены: {json_path}")
    
    # Выводим сводку
    print(f"\n{'='*60}")
    print("СВОДКА МЕТРИК И ВРЕМЕНИ")
    print(f"{'='*60}")
    print(f"\nМетод 1 (layout_all_en):")
    print(f"  Средний CER: {method1_agg.get('avg_cer', 0):.4f}")
    print(f"  Средний WER: {method1_agg.get('avg_wer', 'N/A')}")
    print(f"  Всего блоков: {method1_agg.get('total_blocks', 0)}")
    print(f"  Время выполнения: {time_method1:.2f} сек ({time_method1/60:.2f} мин)")
    if method1_agg.get('total_blocks', 0) > 0:
        print(f"  Время на блок: {time_method1/method1_agg.get('total_blocks', 1):.2f} сек")
    
    print(f"\nМетод 2 (layout_only_en + Qwen):")
    print(f"  Средний CER: {method2_agg.get('avg_cer', 0):.4f}")
    print(f"  Средний WER: {method2_agg.get('avg_wer', 'N/A')}")
    print(f"  Всего блоков: {method2_agg.get('total_blocks', 0)}")
    print(f"  Время выполнения: {time_method2:.2f} сек ({time_method2/60:.2f} мин)")
    if method2_agg.get('total_blocks', 0) > 0:
        print(f"  Время на блок: {time_method2/method2_agg.get('total_blocks', 1):.2f} сек")
    
    print(f"\nОбщее время обработки: {time_total:.2f} сек ({time_total/60:.2f} мин)")
    print(f"  - Метод 1: {time_method1:.2f} сек ({time_method1/time_total*100:.1f}%)")
    print(f"  - Метод 2: {time_method2:.2f} сек ({time_method2/time_total*100:.1f}%)")
    print(f"  - Ground truth: {time_gt:.2f} сек ({time_gt/time_total*100:.1f}%)")
    print(f"  - Вычисление метрик: {time_metrics1 + time_metrics2:.2f} сек ({(time_metrics1 + time_metrics2)/time_total*100:.1f}%)")
    
    return results


def main():
    """Главная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Сравнение методов извлечения текста из PDF"
    )
    parser.add_argument(
        "pdf_path",
        type=Path,
        help="Путь к PDF файлу"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/dots_ocr_text_comparison/results"),
        help="Директория для сохранения результатов"
    )
    parser.add_argument(
        "--render-scale",
        type=float,
        default=2.0,
        help="Масштаб рендеринга (по умолчанию 2.0)"
    )
    
    args = parser.parse_args()
    
    # Проверяем существование PDF
    if not args.pdf_path.exists():
        print(f"Ошибка: Файл не найден: {args.pdf_path}")
        sys.exit(1)
    
    # Создаем директорию для результатов
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Обрабатываем PDF
    results = process_pdf(args.pdf_path, args.output_dir, args.render_scale)
    
    print(f"\n✓ Обработка завершена")


if __name__ == "__main__":
    main()

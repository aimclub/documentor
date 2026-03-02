#!/usr/bin/env python3
"""
Пайплайн для сравнения двух методов извлечения таблиц из PDF:
1. Метод 1: prompt_layout_all_en - один запрос, сразу получаем layout + текст (включая HTML таблиц)
2. Метод 2: prompt_layout_only_en сначала, если найдена таблица, то еще раз prompt_layout_all_en для этой таблицы

Измеряется только время выполнения.
"""

import sys
import json
import io
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
from documentor.utils.ocr_image_utils import fetch_image
from documentor.utils.ocr_consts import MIN_PIXELS, MAX_PIXELS


def crop_table_image(page_image: Image.Image, bbox: List[float], padding: int = 10) -> Image.Image:
    """
    Обрезает изображение таблицы по bbox.
    
    Args:
        page_image: Изображение страницы
        bbox: [x1, y1, x2, y2]
        padding: Отступ в пикселях
    
    Returns:
        Обрезанное изображение таблицы
    """
    x1, y1, x2, y2 = bbox
    x1_crop = max(0, int(x1) - padding)
    y1_crop = max(0, int(y1) - padding)
    x2_crop = min(page_image.width, int(x2) + padding)
    y2_crop = min(page_image.height, int(y2) + padding)
    
    return page_image.crop((x1_crop, y1_crop, x2_crop, y2_crop))


def method1_layout_all(
    pdf_path: Path,
    prompts: Dict[str, str],
    render_scale: float = 2.0
) -> Tuple[List[Dict[str, Any]], float]:
    """
    Метод 1: Использует prompt_layout_all_en для всех страниц.
    
    Args:
        pdf_path: Путь к PDF файлу
        prompts: Словарь промптов
        render_scale: Масштаб рендеринга
    
    Returns:
        tuple: (список таблиц, время выполнения в секундах)
    """
    start_time = time.time()
    
    pdf_doc = fitz.open(str(pdf_path))
    all_tables = []
    
    try:
        prompt = prompts.get("prompt_layout_all_en")
        if not prompt:
            raise ValueError("prompt_layout_all_en not found in prompts")
        
        for page_num in tqdm(range(len(pdf_doc)), desc="Метод 1: обработка страниц", leave=False):
            # Рендерим страницу
            page = pdf_doc[page_num]
            mat = fitz.Matrix(render_scale, render_scale)
            pix = page.get_pixmap(matrix=mat)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            
            # Подготавливаем изображение
            prepared_image = fetch_image(img, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)
            
            # Layout detection с текстом
            layout_cells, raw_response, success = process_layout_detection(
                image=prepared_image,
                origin_image=img,
                prompt=prompt,
            )
            
            if not success or layout_cells is None:
                tqdm.write(f"  ⚠ Ошибка на странице {page_num + 1}")
                continue
            
            # Ищем таблицы
            for elem in layout_cells:
                if elem.get("category") == "Table":
                    table_data = {
                        "page_num": page_num,
                        "bbox": elem.get("bbox", []),
                        "text": elem.get("text", ""),  # HTML из Dots OCR
                    }
                    all_tables.append(table_data)
        
        elapsed_time = time.time() - start_time
        return all_tables, elapsed_time
    
    finally:
        pdf_doc.close()


def method2_layout_only_then_all(
    pdf_path: Path,
    prompts: Dict[str, str],
    render_scale: float = 2.0
) -> Tuple[List[Dict[str, Any]], float]:
    """
    Метод 2: Использует prompt_layout_only_en сначала, если найдена таблица,
    то еще раз prompt_layout_all_en для этой таблицы.
    
    Args:
        pdf_path: Путь к PDF файлу
        prompts: Словарь промптов
        render_scale: Масштаб рендеринга
    
    Returns:
        tuple: (список таблиц, время выполнения в секундах)
    """
    start_time = time.time()
    
    pdf_doc = fitz.open(str(pdf_path))
    all_tables = []
    
    try:
        prompt_only = prompts.get("prompt_layout_only_en")
        prompt_all = prompts.get("prompt_layout_all_en")
        
        if not prompt_only or not prompt_all:
            raise ValueError("Required prompts not found")
        
        for page_num in tqdm(range(len(pdf_doc)), desc="Метод 2: обработка страниц", leave=False):
            # Рендерим страницу
            page = pdf_doc[page_num]
            mat = fitz.Matrix(render_scale, render_scale)
            pix = page.get_pixmap(matrix=mat)
            page_image = Image.open(io.BytesIO(pix.tobytes("png")))
            
            # Подготавливаем изображение
            prepared_image = fetch_image(page_image, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)
            
            # Первый запрос: layout only
            layout_cells, raw_response, success = process_layout_detection(
                image=prepared_image,
                origin_image=page_image,
                prompt=prompt_only,
            )
            
            if not success or layout_cells is None:
                tqdm.write(f"  ⚠ Ошибка на странице {page_num + 1} (layout only)")
                continue
            
            # Ищем таблицы
            tables_found = [elem for elem in layout_cells if elem.get("category") == "Table"]
            
            if not tables_found:
                # Нет таблиц на странице
                continue
            
            # Для каждой найденной таблицы делаем второй запрос с prompt_layout_all_en
            for table_elem in tqdm(tables_found, desc=f"  Страница {page_num + 1}: извлечение таблиц", leave=False):
                bbox = table_elem.get("bbox", [])
                if len(bbox) < 4:
                    continue
                
                # Обрезаем изображение таблицы
                table_image = crop_table_image(page_image, bbox)
                prepared_table_image = fetch_image(table_image, min_pixels=MIN_PIXELS, max_pixels=MAX_PIXELS)
                
                # Второй запрос: layout + текст для таблицы
                table_layout, _, table_success = process_layout_detection(
                    image=prepared_table_image,
                    origin_image=table_image,
                    prompt=prompt_all,
                )
                
                if table_success and table_layout:
                    # Ищем таблицу в результатах
                    for elem in table_layout:
                        if elem.get("category") == "Table":
                            table_data = {
                                "page_num": page_num,
                                "bbox": bbox,
                                "text": elem.get("text", ""),  # HTML из Dots OCR
                            }
                            all_tables.append(table_data)
                            break  # Берем первую найденную таблицу
        
        elapsed_time = time.time() - start_time
        return all_tables, elapsed_time
    
    finally:
        pdf_doc.close()


def process_pdf(
    pdf_path: Path,
    output_dir: Path,
    render_scale: float = 2.0
) -> Dict[str, Any]:
    """
    Обрабатывает PDF файл обоими методами и сохраняет результаты.
    
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
    
    # Загружаем промпты
    config_path = Path(__file__).parent.parent.parent / "documentor" / "config" / "ocr_config.yaml"
    prompts = load_prompts_from_config(config_path)
    
    if "prompt_layout_all_en" not in prompts or "prompt_layout_only_en" not in prompts:
        raise ValueError("Required prompts not found in ocr_config.yaml")
    
    # Метод 1
    print("\nМетод 1: prompt_layout_all_en...")
    method1_tables, time_method1 = method1_layout_all(pdf_path, prompts, render_scale)
    print(f"  Найдено таблиц: {len(method1_tables)}")
    print(f"  Время выполнения: {time_method1:.2f} сек ({time_method1/60:.2f} мин)")
    
    # Метод 2
    print("\nМетод 2: prompt_layout_only_en + prompt_layout_all_en для таблиц...")
    method2_tables, time_method2 = method2_layout_only_then_all(pdf_path, prompts, render_scale)
    print(f"  Найдено таблиц: {len(method2_tables)}")
    print(f"  Время выполнения: {time_method2:.2f} сек ({time_method2/60:.2f} мин)")
    
    # Сохраняем результаты
    pdf_name = pdf_path.stem
    results = {
        "pdf_file": pdf_path.name,
        "timing": {
            "method1_seconds": time_method1,
            "method2_seconds": time_method2,
            "method1_minutes": time_method1 / 60,
            "method2_minutes": time_method2 / 60,
            "speedup": time_method2 / time_method1 if time_method1 > 0 else None,
            "time_saved_seconds": time_method2 - time_method1,
            "time_saved_percent": ((time_method2 - time_method1) / time_method2 * 100) if time_method2 > 0 else None,
        },
        "tables_count": {
            "method1": len(method1_tables),
            "method2": len(method2_tables),
        },
        "method1": {
            "tables": method1_tables,
            "timing_seconds": time_method1,
        },
        "method2": {
            "tables": method2_tables,
            "timing_seconds": time_method2,
        },
    }
    
    # Сохраняем в JSON
    output_file = output_dir / f"{pdf_name}_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print("СВОДКА")
    print(f"{'='*60}")
    print(f"\nМетод 1 (layout_all_en):")
    print(f"  Таблиц: {len(method1_tables)}")
    print(f"  Время: {time_method1:.2f} сек ({time_method1/60:.2f} мин)")
    
    print(f"\nМетод 2 (layout_only + layout_all для таблиц):")
    print(f"  Таблиц: {len(method2_tables)}")
    print(f"  Время: {time_method2:.2f} сек ({time_method2/60:.2f} мин)")
    
    if time_method1 > 0:
        speedup = time_method2 / time_method1
        print(f"\nСравнение:")
        print(f"  Ускорение: {speedup:.2f}x")
        if speedup > 1:
            print(f"  Метод 1 быстрее на {((speedup - 1) * 100):.1f}%")
        else:
            print(f"  Метод 2 быстрее на {((1 - speedup) * 100):.1f}%")
    
    print(f"\nРезультаты сохранены в: {output_file}")
    
    return results


if __name__ == "__main__":
    import io
    import argparse
    
    parser = argparse.ArgumentParser(description="Сравнение методов извлечения таблиц из PDF")
    parser.add_argument("pdf_path", type=Path, help="Путь к PDF файлу")
    parser.add_argument("--output-dir", type=Path, default=None, help="Директория для результатов")
    parser.add_argument("--render-scale", type=float, default=2.0, help="Масштаб рендеринга")
    
    args = parser.parse_args()
    
    if not args.pdf_path.exists():
        print(f"Ошибка: Файл не найден: {args.pdf_path}")
        sys.exit(1)
    
    if args.output_dir is None:
        args.output_dir = Path(__file__).parent / "results"
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    process_pdf(args.pdf_path, args.output_dir, args.render_scale)

#!/usr/bin/env python3
"""
Скрипт для тестирования двух промптов Dots OCR:
- prompt_layout_all_en (полный промпт с текстом)
- prompt_layout_only_en (только layout без текста)

Пропускает PDF через оба промпта, визуализирует результаты
и сохраняет изображения для сравнения.
"""

import sys
import json
import io
from pathlib import Path
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont
import yaml

# Добавляем путь к корню проекта
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import fitz  # PyMuPDF
from documentor.ocr.dots_ocr import load_prompts_from_config
from documentor.processing.parsers.pdf.ocr.dots_ocr_client import process_layout_detection

# Цвета для типов элементов
ELEMENT_COLORS = {
    "Title": (255, 0, 0),  # Красный
    "Section-header": (255, 102, 0),  # Оранжевый
    "Text": (0, 204, 255),  # Голубой
    "Table": (153, 0, 255),  # Фиолетовый
    "Picture": (255, 0, 255),  # Розовый
    "List-item": (0, 255, 153),  # Зелено-голубой
    "Caption": (255, 0, 153),  # Розово-красный
    "Formula": (0, 153, 255),  # Синий
    "Footnote": (102, 102, 102),  # Серый
    "Page-header": (200, 200, 200),  # Светло-серый
    "Page-footer": (200, 200, 200),  # Светло-серый
}

# Цвет по умолчанию для неизвестных типов
DEFAULT_COLOR = (128, 128, 128)


def render_pdf_page(pdf_path: Path, page_num: int, scale: float = 2.0) -> Image.Image:
    """
    Рендерит страницу PDF в изображение.
    
    Args:
        pdf_path: Путь к PDF файлу
        page_num: Номер страницы (0-based)
        scale: Масштаб рендеринга
    
    Returns:
        PIL Image
    """
    pdf_doc = fitz.open(str(pdf_path))
    try:
        page = pdf_doc[page_num]
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        return Image.open(io.BytesIO(img_data))
    finally:
        pdf_doc.close()


def visualize_layout(image: Image.Image, layout_elements: List[Dict[str, Any]], 
                     title: str = "") -> Image.Image:
    """
    Визуализирует layout элементы на изображении.
    
    Args:
        image: Исходное изображение
        layout_elements: Список элементов layout
        title: Заголовок для отображения
    
    Returns:
        PIL Image с нарисованными боксами
    """
    # Создаем копию изображения
    vis_image = image.copy()
    draw = ImageDraw.Draw(vis_image)
    
    # Пытаемся загрузить шрифт
    try:
        font = ImageFont.truetype("arial.ttf", 16)
        font_small = ImageFont.truetype("arial.ttf", 12)
    except:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        except:
            font = ImageFont.load_default()
            font_small = ImageFont.load_default()
    
    # Рисуем заголовок
    if title:
        draw.rectangle([0, 0, vis_image.width, 30], fill=(255, 255, 255, 200))
        draw.text((10, 5), title, fill=(0, 0, 0), font=font)
    
    # Рисуем боксы для каждого элемента
    for i, elem in enumerate(layout_elements):
        bbox = elem.get("bbox", [])
        if len(bbox) != 4:
            continue
        
        x1, y1, x2, y2 = bbox
        category = elem.get("category", "Unknown")
        
        # Получаем цвет для категории
        color = ELEMENT_COLORS.get(category, DEFAULT_COLOR)
        
        # Рисуем прямоугольник
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        
        # Рисуем метку с категорией
        label = f"{category}"
        if "text" in elem and elem["text"]:
            # Обрезаем текст для метки
            text_preview = elem["text"][:30] + "..." if len(elem["text"]) > 30 else elem["text"]
            label = f"{category}: {text_preview}"
        
        # Фон для текста
        text_bbox = draw.textbbox((x1, y1 - 20), label, font=font_small)
        if text_bbox:
            draw.rectangle(text_bbox, fill=(255, 255, 255, 200))
            draw.text((x1, y1 - 20), label, fill=color, font=font_small)
    
    return vis_image


def process_pdf_with_prompt(
    pdf_path: Path,
    prompt: str,
    prompt_name: str,
    output_dir: Path,
    max_pages: Optional[int] = None
) -> Dict[str, Any]:
    """
    Обрабатывает PDF с заданным промптом.
    
    Args:
        pdf_path: Путь к PDF файлу
        prompt: Промпт для Dots OCR
        prompt_name: Имя промпта (для сохранения файлов)
        output_dir: Директория для сохранения результатов
        max_pages: Максимальное количество страниц для обработки (None = все)
    
    Returns:
        Словарь с результатами обработки
    """
    print(f"\n{'='*60}")
    print(f"Обработка с промптом: {prompt_name}")
    print(f"{'='*60}")
    
    pdf_doc = fitz.open(str(pdf_path))
    total_pages = len(pdf_doc)
    if max_pages:
        total_pages = min(total_pages, max_pages)
    
    results = {
        "prompt_name": prompt_name,
        "total_pages": total_pages,
        "pages": []
    }
    
    # Создаем директорию для результатов
    prompt_output_dir = output_dir / prompt_name
    prompt_output_dir.mkdir(parents=True, exist_ok=True)
    
    for page_num in range(total_pages):
        print(f"\nОбработка страницы {page_num + 1}/{total_pages}...")
        
        try:
            # Рендерим страницу
            page = pdf_doc[page_num]
            mat = fitz.Matrix(2.0, 2.0)  # render_scale = 2.0
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            page_image = Image.open(io.BytesIO(img_data))
            
            # Вызываем layout detection
            print(f"  Вызов Dots OCR...")
            layout_cells, raw_response, success = process_layout_detection(
                image=page_image,
                origin_image=page_image,
                prompt=prompt,
            )
            
            if not success or layout_cells is None:
                print(f"  ⚠ Ошибка на странице {page_num + 1}")
                results["pages"].append({
                    "page_num": page_num,
                    "success": False,
                    "error": "Layout detection failed"
                })
                continue
            
            print(f"  ✓ Найдено элементов: {len(layout_cells)}")
            
            # Статистика по типам
            type_counts = {}
            for elem in layout_cells:
                cat = elem.get("category", "Unknown")
                type_counts[cat] = type_counts.get(cat, 0) + 1
            
            print(f"  Типы элементов: {type_counts}")
            
            # Визуализируем
            vis_image = visualize_layout(
                page_image,
                layout_cells,
                title=f"Page {page_num + 1} - {prompt_name}"
            )
            
            # Сохраняем визуализацию
            vis_path = prompt_output_dir / f"page_{page_num + 1:03d}.png"
            vis_image.save(vis_path)
            print(f"  ✓ Сохранено: {vis_path.name}")
            
            # Сохраняем результаты
            results["pages"].append({
                "page_num": page_num,
                "success": True,
                "element_count": len(layout_cells),
                "type_counts": type_counts,
                "elements": layout_cells
            })
            
        except Exception as e:
            print(f"  ✗ Ошибка на странице {page_num + 1}: {e}")
            import traceback
            traceback.print_exc()
            results["pages"].append({
                "page_num": page_num,
                "success": False,
                "error": str(e)
            })
    
    pdf_doc.close()
    
    # Сохраняем JSON с результатами
    json_path = prompt_output_dir / "results.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Результаты сохранены в: {prompt_output_dir}")
    
    return results


def main():
    """Главная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Тестирование двух промптов Dots OCR"
    )
    parser.add_argument(
        "pdf_path",
        type=Path,
        help="Путь к PDF файлу из test_files_for_metrics"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/metrics/dots_ocr_comparison"),
        help="Директория для сохранения результатов"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Максимальное количество страниц для обработки (по умолчанию - все)"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Путь к ocr_config.yaml (по умолчанию - стандартный)"
    )
    
    args = parser.parse_args()
    
    # Проверяем существование PDF
    if not args.pdf_path.exists():
        print(f"Ошибка: Файл не найден: {args.pdf_path}")
        sys.exit(1)
    
    # Загружаем промпты из конфига
    if args.config is None:
        config_path = project_root / "documentor" / "config" / "ocr_config.yaml"
    else:
        config_path = args.config
    
    print(f"Загрузка промптов из: {config_path}")
    prompts = load_prompts_from_config(config_path)
    
    # Получаем два нужных промпта
    prompt_all = prompts.get("prompt_layout_all_en")
    prompt_only = prompts.get("prompt_layout_only_en")
    
    if not prompt_all:
        print("Ошибка: Промпт 'prompt_layout_all_en' не найден в конфиге")
        sys.exit(1)
    
    if not prompt_only:
        print("Ошибка: Промпт 'prompt_layout_only_en' не найден в конфиге")
        sys.exit(1)
    
    print(f"\nПромпт 1 (layout_all_en): {len(prompt_all)} символов")
    print(f"Промпт 2 (layout_only_en): {len(prompt_only)} символов")
    
    # Создаем директорию для результатов
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    pdf_name = args.pdf_path.stem
    pdf_output_dir = output_dir / pdf_name
    pdf_output_dir.mkdir(parents=True, exist_ok=True)
    
    # Обрабатываем с первым промптом
    results_all = process_pdf_with_prompt(
        args.pdf_path,
        prompt_all,
        "prompt_layout_all_en",
        pdf_output_dir,
        max_pages=args.max_pages
    )
    
    # Обрабатываем со вторым промптом
    results_only = process_pdf_with_prompt(
        args.pdf_path,
        prompt_only,
        "prompt_layout_only_en",
        pdf_output_dir,
        max_pages=args.max_pages
    )
    
    # Создаем сводный отчет
    print(f"\n{'='*60}")
    print("СВОДНЫЙ ОТЧЕТ")
    print(f"{'='*60}")
    
    print(f"\nПромпт: prompt_layout_all_en")
    print(f"  Успешно обработано страниц: {sum(1 for p in results_all['pages'] if p.get('success'))}")
    print(f"  Всего элементов: {sum(p.get('element_count', 0) for p in results_all['pages'] if p.get('success'))}")
    
    print(f"\nПромпт: prompt_layout_only_en")
    print(f"  Успешно обработано страниц: {sum(1 for p in results_only['pages'] if p.get('success'))}")
    print(f"  Всего элементов: {sum(p.get('element_count', 0) for p in results_only['pages'] if p.get('success'))}")
    
    print(f"\n✓ Результаты сохранены в: {pdf_output_dir}")
    print(f"\nДля сравнения откройте изображения в:")
    print(f"  - {pdf_output_dir / 'prompt_layout_all_en'}")
    print(f"  - {pdf_output_dir / 'prompt_layout_only_en'}")


if __name__ == "__main__":
    main()

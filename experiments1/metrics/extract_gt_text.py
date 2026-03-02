"""
Скрипт для пакетного извлечения ground truth текста из PDF файлов
и обновления аннотаций.

Аннотации для pdf и scanned.pdf одинаковые, но текст нужно извлечь
из обычного PDF (не scanned) по координатам bbox.
"""

import json
import fitz
from pathlib import Path
from typing import Dict, List, Any
from tqdm import tqdm


def extract_text_from_pdf_by_bbox(
    pdf_path: Path,
    bbox: List[float],
    page_number: int,
    render_scale: float = 2.0
) -> str:
    """
    Извлекает текст из PDF по координатам bbox.
    
    Args:
        pdf_path: Путь к PDF файлу
        bbox: Координаты bbox [x1, y1, x2, y2]
        page_number: Номер страницы (1-based)
        render_scale: Масштаб, используемый при создании bbox
        
    Returns:
        Извлеченный текст
    """
    if len(bbox) < 4:
        return ""
    
    try:
        pdf_doc = fitz.open(str(pdf_path))
        page_num = page_number - 1  # Конвертируем в 0-based
        
        if page_num < 0 or page_num >= len(pdf_doc):
            pdf_doc.close()
            return ""
        
        page = pdf_doc[page_num]
        
        # Конвертируем координаты из render_scale в оригинальный масштаб PDF
        x1, y1, x2, y2 = (
            bbox[0] / render_scale,
            bbox[1] / render_scale,
            bbox[2] / render_scale,
            bbox[3] / render_scale,
        )
        
        rect = fitz.Rect(x1, y1, x2, y2)
        
        # Пробуем get_textbox - более точный метод
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
        
        # Если всё ещё нет текста, пробуем простой метод
        if not text or len(text) < 2:
            text = page.get_text("text", clip=rect).strip()
        
        pdf_doc.close()
        return text
    
    except Exception as e:
        print(f"Ошибка при извлечении текста: {e}")
        return ""


def find_corresponding_pdf(annotation_path: Path) -> Path:
    """
    Находит соответствующий PDF файл для аннотации.
    
    Аннотации для pdf и scanned.pdf одинаковые, но текст нужно извлечь
    из обычного PDF (не scanned) по координатам bbox.
    
    Args:
        annotation_path: Путь к файлу аннотации
        
    Returns:
        Путь к PDF файлу или None
    """
    annotation_name = annotation_path.stem.replace("_annotation", "")
    annotation_dir = annotation_path.parent
    
    # Убираем _scanned из имени, если есть
    # Аннотации одинаковые, но текст всегда извлекаем из обычного PDF
    regular_name = annotation_name.replace("_scanned", "").replace("scanned", "").strip()
    
    # Ищем обычный .pdf (не scanned)
    possible_paths = [
        annotation_dir.parent / "test_files_for_metrics" / f"{regular_name}.pdf",
        annotation_dir.parent.parent / "test_files_for_metrics" / f"{regular_name}.pdf",
        annotation_dir / f"{regular_name}.pdf",
        Path(annotation_path.parent.parent) / "test_files_for_metrics" / f"{regular_name}.pdf",
    ]
    
    for path in possible_paths:
        if path.exists() and path.suffix.lower() == '.pdf' and "scanned" not in path.name.lower():
            return path
    
    return None


def update_annotation_with_gt_text(annotation_path: Path, pdf_path: Path) -> Dict[str, Any]:
    """
    Обновляет аннотацию, заменяя текст элементов на ground truth из PDF.
    
    Args:
        annotation_path: Путь к файлу аннотации
        pdf_path: Путь к PDF файлу с выделяемым текстом
        
    Returns:
        Обновленная аннотация
    """
    # Загружаем аннотацию
    with open(annotation_path, 'r', encoding='utf-8') as f:
        annotation = json.load(f)
    
    elements = annotation.get("elements", [])
    elements_with_bbox = [e for e in elements if len(e.get('bbox', [])) >= 4]
    
    if not elements_with_bbox:
        print(f"[WARNING] Нет элементов с bbox в {annotation_path.name}")
        return annotation
    
    updated_count = 0
    
    # Извлекаем текст для каждого элемента
    for elem in tqdm(elements_with_bbox, desc=f"Обработка {annotation_path.name}", leave=False):
        bbox = elem.get('bbox', [])
        page_number = elem.get('page_number', 1)
        
        text = extract_text_from_pdf_by_bbox(pdf_path, bbox, page_number)
        
        if text:
            elem['content'] = text
            updated_count += 1
    
    print(f"[OK] Обновлено {updated_count} из {len(elements_with_bbox)} элементов в {annotation_path.name}")
    
    return annotation


def process_annotations(annotations_dir: Path, output_dir: Path = None):
    """
    Обрабатывает все аннотации в директории.
    
    Args:
        annotations_dir: Директория с аннотациями
        output_dir: Директория для сохранения (если None, перезаписывает исходные)
    """
    annotations_dir = Path(annotations_dir)
    
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = annotations_dir
    
    # Находим все файлы аннотаций
    annotation_files = list(annotations_dir.glob("*_annotation.json"))
    
    if not annotation_files:
        print(f"[ERROR] Не найдено файлов аннотаций в {annotations_dir}")
        return
    
    print(f"[INFO] Найдено {len(annotation_files)} файлов аннотаций")
    
    processed = 0
    skipped = 0
    
    for ann_path in tqdm(annotation_files, desc="Обработка аннотаций"):
        # Находим соответствующий PDF
        pdf_path = find_corresponding_pdf(ann_path)
        
        if not pdf_path or not pdf_path.exists():
            print(f"[WARNING] Не найден PDF для {ann_path.name}, пропускаем")
            skipped += 1
            continue
        
        # Обновляем аннотацию
        updated_annotation = update_annotation_with_gt_text(ann_path, pdf_path)
        
        # Сохраняем обновленную аннотацию
        output_path = output_dir / ann_path.name
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(updated_annotation, f, ensure_ascii=False, indent=2)
        
        processed += 1
    
    print(f"\n[OK] Обработано: {processed}")
    print(f"[WARNING] Пропущено: {skipped}")


def main():
    """Главная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Извлекает ground truth текст из PDF и обновляет аннотации"
    )
    parser.add_argument(
        "--annotations-dir",
        type=str,
        default="annotations",
        help="Директория с аннотациями (по умолчанию: annotations)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Директория для сохранения (если не указана, перезаписывает исходные)"
    )
    
    args = parser.parse_args()
    
    annotations_dir = Path(args.annotations_dir).resolve()
    
    if not annotations_dir.exists():
        print(f"[ERROR] Директория не найдена: {annotations_dir}")
        return
    
    process_annotations(annotations_dir, args.output_dir)


if __name__ == "__main__":
    main()

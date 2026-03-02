"""
Скрипт для копирования всех элементов из PDF аннотации в scanned аннотацию.
Копирует все поля из PDF, но использует bbox из scanned аннотации (с возможным offset).
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict


def normalize_text(text: str) -> str:
    """Нормализует текст для сравнения."""
    if not text:
        return ""
    return text.strip().lower().replace("\n", " ").replace("\r", " ")


def find_matching_scanned_element(
    pdf_elem: Dict[str, Any],
    scanned_elements: List[Dict[str, Any]],
    used_indices: set
) -> Optional[Tuple[int, Dict[str, Any]]]:
    """
    Находит соответствующий элемент в scanned аннотации для PDF элемента.
    
    Returns:
        Tuple (index, element) или None
    """
    pdf_type = pdf_elem.get('type', '').lower()
    pdf_content = normalize_text(pdf_elem.get('content', ''))
    pdf_page = pdf_elem.get('page_number') or pdf_elem.get('page_num', 0)
    if pdf_page == 0 and 'page_num' in pdf_elem:
        pdf_page = pdf_elem.get('page_num', 0) + 1
    
    best_match = None
    best_score = 0.0
    best_idx = None
    
    for idx, scanned_elem in enumerate(scanned_elements):
        if idx in used_indices:
            continue
        
        scanned_type = scanned_elem.get('type', '').lower()
        scanned_content = normalize_text(scanned_elem.get('content', ''))
        scanned_page = scanned_elem.get('page_number') or scanned_elem.get('page_num', 0)
        if scanned_page == 0 and 'page_num' in scanned_elem:
            scanned_page = scanned_elem.get('page_num', 0) + 1
        
        # Вычисляем score совпадения
        score = 0.0
        
        # Тип должен совпадать
        if pdf_type == scanned_type:
            score += 0.3
        else:
            continue  # Тип не совпадает - пропускаем
        
        # Страница должна совпадать (или быть близкой)
        if pdf_page == scanned_page:
            score += 0.2
        elif abs(pdf_page - scanned_page) <= 1:
            score += 0.1
        
        # Содержимое должно совпадать
        if pdf_content:
            if pdf_content == scanned_content:
                score += 0.5
            elif pdf_content in scanned_content or scanned_content in pdf_content:
                score += 0.3
            elif len(pdf_content) > 20 and len(scanned_content) > 20:
                # Для длинных текстов проверяем первые 50 символов
                if pdf_content[:50] == scanned_content[:50]:
                    score += 0.2
        
        if score > best_score:
            best_score = score
            best_match = scanned_elem
            best_idx = idx
    
    # Минимальный порог для совпадения
    if best_score >= 0.5:
        return (best_idx, best_match)
    
    return None


def calculate_bbox_offset(
    pdf_elements: List[Dict[str, Any]],
    scanned_elements: List[Dict[str, Any]]
) -> Optional[Tuple[float, float, float, float]]:
    """
    Вычисляет среднее смещение bbox между PDF и scanned аннотациями.
    
    Returns:
        Tuple (offset_x1, offset_y1, offset_x2, offset_y2) или None
    """
    offsets = []
    
    # Сортируем для сопоставления
    pdf_sorted = sorted(pdf_elements, key=lambda e: e.get('order', 0))
    scanned_sorted = sorted(scanned_elements, key=lambda e: e.get('order', 0))
    
    scanned_matched = set()
    
    for pdf_elem in pdf_sorted:
        match = find_matching_scanned_element(pdf_elem, scanned_sorted, scanned_matched)
        
        if match:
            scanned_idx, scanned_elem = match
            scanned_matched.add(scanned_idx)
            
            pdf_bbox = pdf_elem.get('bbox', [])
            scanned_bbox = scanned_elem.get('bbox', [])
            
            if len(pdf_bbox) >= 4 and len(scanned_bbox) >= 4:
                # Вычисляем смещение
                offset = [
                    scanned_bbox[0] - pdf_bbox[0],  # x1 offset
                    scanned_bbox[1] - pdf_bbox[1],  # y1 offset
                    scanned_bbox[2] - pdf_bbox[2],  # x2 offset
                    scanned_bbox[3] - pdf_bbox[3]     # y2 offset
                ]
                offsets.append(offset)
    
    if not offsets:
        return None
    
    # Вычисляем среднее смещение
    avg_offset = [
        sum(o[0] for o in offsets) / len(offsets),
        sum(o[1] for o in offsets) / len(offsets),
        sum(o[2] for o in offsets) / len(offsets),
        sum(o[3] for o in offsets) / len(offsets)
    ]
    
    return tuple(avg_offset)


def copy_pdf_to_scanned_with_bbox(
    pdf_annotation_path: Path,
    scanned_annotation_path: Path,
    output_path: Optional[Path] = None,
    bbox_offset: Optional[Tuple[float, float]] = None,
    auto_calculate_offset: bool = True
) -> Dict[str, Any]:
    """
    Копирует все элементы из PDF аннотации в scanned аннотацию.
    Использует bbox из scanned аннотации (с возможным offset).
    
    Args:
        pdf_annotation_path: Путь к PDF аннотации
        scanned_annotation_path: Путь к scanned аннотации
        output_path: Путь для сохранения (если None, перезаписывает scanned)
        bbox_offset: Опциональный offset для bbox (dx, dy) - применяется к scanned bbox
        auto_calculate_offset: Автоматически вычислять среднее смещение для элементов без соответствия
        
    Returns:
        Обновленная аннотация
    """
    # Загружаем аннотации
    with open(pdf_annotation_path, 'r', encoding='utf-8') as f:
        pdf_annotation = json.load(f)
    
    with open(scanned_annotation_path, 'r', encoding='utf-8') as f:
        scanned_annotation = json.load(f)
    
    pdf_elements = pdf_annotation.get('elements', [])
    scanned_elements = scanned_annotation.get('elements', [])
    
    print(f"Обработка: {pdf_annotation_path.name} -> {scanned_annotation_path.name}")
    print(f"  PDF элементов: {len(pdf_elements)}")
    print(f"  Scanned элементов: {len(scanned_elements)}")
    
    # Вычисляем среднее смещение, если нужно
    avg_bbox_offset = None
    if auto_calculate_offset:
        avg_bbox_offset = calculate_bbox_offset(pdf_elements, scanned_elements)
        if avg_bbox_offset:
            print(f"  Вычислено среднее смещение bbox: {avg_bbox_offset}")
    
    # Сортируем элементы по order для более точного сопоставления
    pdf_sorted = sorted(pdf_elements, key=lambda e: e.get('order', 0))
    scanned_sorted = sorted(scanned_elements, key=lambda e: e.get('order', 0))
    
    # Сопоставляем элементы и копируем из PDF с bbox из scanned
    scanned_matched = set()
    copied_elements = []
    bbox_applied_count = 0
    bbox_missing_count = 0
    bbox_offset_applied_count = 0
    
    for pdf_elem in pdf_sorted:
        # Копируем элемент из PDF
        copied_elem = pdf_elem.copy()
        
        # Ищем соответствующий элемент в scanned для получения bbox
        match = find_matching_scanned_element(pdf_elem, scanned_sorted, scanned_matched)
        
        if match:
            scanned_idx, scanned_elem = match
            scanned_matched.add(scanned_idx)
            
            # Берем bbox из scanned
            scanned_bbox = scanned_elem.get('bbox', [])
            
            if scanned_bbox and len(scanned_bbox) >= 4:
                # Применяем offset, если указан
                if bbox_offset:
                    dx, dy = bbox_offset
                    scanned_bbox = [
                        scanned_bbox[0] + dx,
                        scanned_bbox[1] + dy,
                        scanned_bbox[2] + dx,
                        scanned_bbox[3] + dy
                    ]
                
                copied_elem['bbox'] = scanned_bbox
                bbox_applied_count += 1
            else:
                # Если bbox нет в scanned, применяем среднее смещение к PDF bbox
                pdf_bbox = pdf_elem.get('bbox', [])
                if pdf_bbox and len(pdf_bbox) >= 4 and avg_bbox_offset:
                    offset_bbox = [
                        pdf_bbox[0] + avg_bbox_offset[0],
                        pdf_bbox[1] + avg_bbox_offset[1],
                        pdf_bbox[2] + avg_bbox_offset[2],
                        pdf_bbox[3] + avg_bbox_offset[3]
                    ]
                    copied_elem['bbox'] = offset_bbox
                    bbox_offset_applied_count += 1
                else:
                    bbox_missing_count += 1
        else:
            # Если не нашли соответствие, применяем среднее смещение к PDF bbox
            pdf_bbox = pdf_elem.get('bbox', [])
            if pdf_bbox and len(pdf_bbox) >= 4 and avg_bbox_offset:
                offset_bbox = [
                    pdf_bbox[0] + avg_bbox_offset[0],
                    pdf_bbox[1] + avg_bbox_offset[1],
                    pdf_bbox[2] + avg_bbox_offset[2],
                    pdf_bbox[3] + avg_bbox_offset[3]
                ]
                copied_elem['bbox'] = offset_bbox
                bbox_offset_applied_count += 1
            else:
                bbox_missing_count += 1
        
        # Обновляем page_number и page_num
        page_number = copied_elem.get('page_number') or copied_elem.get('page_num', 0)
        if page_number == 0 and 'page_num' in copied_elem:
            page_number = copied_elem.get('page_num', 0) + 1
        
        copied_elem['page_number'] = page_number
        copied_elem['page_num'] = page_number - 1 if page_number > 0 else 0
        
        # Удаляем page_number, если оно было как page_num (0-based)
        if 'page_number' in copied_elem and copied_elem['page_number'] == 0:
            copied_elem['page_number'] = 1
        
        copied_elements.append(copied_elem)
    
    print(f"  Скопировано элементов: {len(copied_elements)}")
    print(f"  Bbox применен из scanned: {bbox_applied_count}")
    print(f"  Bbox из PDF (не найдено соответствие): {bbox_missing_count}")
    
    # Создаем обновленную аннотацию на основе scanned
    updated_annotation = scanned_annotation.copy()
    updated_annotation['elements'] = copied_elements
    
    # Обновляем метаданные
    updated_annotation['document_id'] = scanned_annotation.get('document_id', pdf_annotation.get('document_id', ''))
    updated_annotation['source_file'] = scanned_annotation.get('source_file', '')
    updated_annotation['document_format'] = scanned_annotation.get('document_format', 'pdf')
    
    # Обновляем статистику
    if 'statistics' in updated_annotation:
        updated_annotation['statistics']['total_elements'] = len(copied_elements)
        # Пересчитываем по типам
        elements_by_type = {}
        for elem in copied_elements:
            elem_type = elem.get('type', 'unknown')
            elements_by_type[elem_type] = elements_by_type.get(elem_type, 0) + 1
        updated_annotation['statistics']['elements_by_type'] = elements_by_type
    
    # Сохраняем
    if output_path is None:
        output_path = scanned_annotation_path
    
    # Создаем резервную копию
    backup_path = scanned_annotation_path.parent / f"{scanned_annotation_path.stem}_backup_before_copy.json"
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(scanned_annotation, f, ensure_ascii=False, indent=2)
    print(f"  Создана резервная копия: {backup_path.name}")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(updated_annotation, f, ensure_ascii=False, indent=2)
    
    print(f"  Сохранено: {output_path}")
    
    return updated_annotation


def main():
    """Основная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Копирование всех элементов из PDF аннотации в scanned аннотацию с bbox из scanned"
    )
    
    script_dir = Path(__file__).parent
    default_annotations_dir = script_dir / "annotations"
    
    parser.add_argument(
        "--pdf",
        type=str,
        required=True,
        help="Путь к PDF аннотации"
    )
    parser.add_argument(
        "--scanned",
        type=str,
        required=True,
        help="Путь к scanned аннотации"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Путь для сохранения (если не указан, перезаписывает scanned)"
    )
    parser.add_argument(
        "--bbox-offset-x",
        type=float,
        default=0.0,
        help="Offset по X для bbox (по умолчанию 0)"
    )
    parser.add_argument(
        "--bbox-offset-y",
        type=float,
        default=0.0,
        help="Offset по Y для bbox (по умолчанию 0)"
    )
    
    args = parser.parse_args()
    
    pdf_path = Path(args.pdf)
    scanned_path = Path(args.scanned)
    output_path = Path(args.output) if args.output else None
    
    bbox_offset = None
    if args.bbox_offset_x != 0.0 or args.bbox_offset_y != 0.0:
        bbox_offset = (args.bbox_offset_x, args.bbox_offset_y)
    
    if not pdf_path.exists():
        print(f"Ошибка: файл не найден: {pdf_path}")
        return
    
    if not scanned_path.exists():
        print(f"Ошибка: файл не найден: {scanned_path}")
        return
    
    print("=" * 80)
    print("КОПИРОВАНИЕ PDF АННОТАЦИИ В SCANNED АННОТАЦИЮ")
    print("=" * 80)
    print()
    
    copy_pdf_to_scanned_with_bbox(
        pdf_path,
        scanned_path,
        output_path,
        bbox_offset
    )
    
    print()
    print("Готово!")


if __name__ == "__main__":
    main()

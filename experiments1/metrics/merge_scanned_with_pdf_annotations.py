"""
Скрипт для объединения scanned и обычных PDF аннотаций.

Берет bbox из scanned аннотаций (они правильные),
а текст, тип элемента, parent_id, order и т.д. из обычных PDF аннотаций.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional


def match_elements_by_order(
    scanned_elements: List[Dict[str, Any]],
    pdf_elements: List[Dict[str, Any]]
) -> Dict[str, str]:
    """
    Сопоставляет элементы по порядку (order).
    
    Args:
        scanned_elements: Элементы из scanned аннотации
        pdf_elements: Элементы из PDF аннотации
        
    Returns:
        Dict mapping scanned_element_id -> pdf_element_id
    """
    matches = {}
    
    # Сортируем по order
    scanned_sorted = sorted(scanned_elements, key=lambda e: e.get('order', 0))
    pdf_sorted = sorted(pdf_elements, key=lambda e: e.get('order', 0))
    
    # Сопоставляем по порядку
    min_len = min(len(scanned_sorted), len(pdf_sorted))
    for i in range(min_len):
        scanned_id = scanned_sorted[i].get('id')
        pdf_id = pdf_sorted[i].get('id')
        if scanned_id and pdf_id:
            matches[scanned_id] = pdf_id
    
    return matches


def match_elements_by_type_and_order(
    scanned_elements: List[Dict[str, Any]],
    pdf_elements: List[Dict[str, Any]]
) -> Dict[str, str]:
    """
    Сопоставляет элементы по типу и порядку.
    
    Args:
        scanned_elements: Элементы из scanned аннотации
        pdf_elements: Элементы из PDF аннотации
        
    Returns:
        Dict mapping scanned_element_id -> pdf_element_id
    """
    matches = {}
    used_pdf_ids = set()
    
    # Группируем по типу
    scanned_by_type = {}
    for elem in scanned_elements:
        elem_type = elem.get('type', '').lower()
        if elem_type not in scanned_by_type:
            scanned_by_type[elem_type] = []
        scanned_by_type[elem_type].append(elem)
    
    pdf_by_type = {}
    for elem in pdf_elements:
        elem_type = elem.get('type', '').lower()
        if elem_type not in pdf_by_type:
            pdf_by_type[elem_type] = []
        pdf_by_type[elem_type].append(elem)
    
    # Сопоставляем элементы каждого типа по порядку
    for elem_type, scanned_elems in scanned_by_type.items():
        if elem_type not in pdf_by_type:
            continue
        
        scanned_sorted = sorted(scanned_elems, key=lambda e: e.get('order', 0))
        pdf_sorted = sorted(pdf_by_type[elem_type], key=lambda e: e.get('order', 0))
        
        min_len = min(len(scanned_sorted), len(pdf_sorted))
        for i in range(min_len):
            scanned_id = scanned_sorted[i].get('id')
            pdf_id = pdf_sorted[i].get('id')
            
            if scanned_id and pdf_id and pdf_id not in used_pdf_ids:
                matches[scanned_id] = pdf_id
                used_pdf_ids.add(pdf_id)
    
    return matches


def merge_annotations(
    scanned_annotation_path: Path,
    pdf_annotation_path: Path,
    output_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Объединяет scanned и PDF аннотации.
    
    Берет bbox из scanned, остальное из PDF.
    
    Args:
        scanned_annotation_path: Путь к scanned аннотации
        pdf_annotation_path: Путь к PDF аннотации
        output_path: Путь для сохранения (если None, перезаписывает scanned)
        
    Returns:
        Объединенная аннотация
    """
    # Загружаем аннотации
    with open(scanned_annotation_path, 'r', encoding='utf-8') as f:
        scanned_ann = json.load(f)
    
    with open(pdf_annotation_path, 'r', encoding='utf-8') as f:
        pdf_ann = json.load(f)
    
    scanned_elements = scanned_ann.get('elements', [])
    pdf_elements = pdf_ann.get('elements', [])
    
    print(f"Обработка: {scanned_annotation_path.name}")
    print(f"  Scanned элементов: {len(scanned_elements)}")
    print(f"  PDF элементов: {len(pdf_elements)}")
    
    # Сопоставляем элементы
    # Сначала пробуем по типу и порядку
    matches = match_elements_by_type_and_order(scanned_elements, pdf_elements)
    
    # Если не все сопоставлены, пробуем просто по порядку
    if len(matches) < min(len(scanned_elements), len(pdf_elements)):
        print(f"  Предупреждение: сопоставлено только {len(matches)} элементов, пробуем по порядку")
        matches_order = match_elements_by_order(scanned_elements, pdf_elements)
        # Добавляем недостающие сопоставления
        for scanned_id, pdf_id in matches_order.items():
            if scanned_id not in matches:
                matches[scanned_id] = pdf_id
    
    print(f"  Сопоставлено элементов: {len(matches)}")
    
    # Создаем словарь PDF элементов для быстрого доступа
    pdf_elements_dict = {elem['id']: elem for elem in pdf_elements}
    
    # Обновляем scanned элементы
    merged_elements = []
    updated_count = 0
    
    for scanned_elem in scanned_elements:
        scanned_id = scanned_elem.get('id')
        
        # Берем bbox из scanned
        bbox = scanned_elem.get('bbox', [])
        
        # Получаем page_number из scanned и конвертируем в page_num (0-based)
        page_number = scanned_elem.get('page_number', 1)
        page_num = page_number - 1 if page_number > 0 else 0
        
        # Ищем соответствующий PDF элемент
        pdf_id = matches.get(scanned_id)
        
        if pdf_id and pdf_id in pdf_elements_dict:
            pdf_elem = pdf_elements_dict[pdf_id]
            
            # Создаем объединенный элемент
            merged_elem = {
                'id': scanned_id,  # Сохраняем ID из scanned
                'type': pdf_elem.get('type', scanned_elem.get('type')),
                'content': pdf_elem.get('content', scanned_elem.get('content', '')),
                'parent_id': pdf_elem.get('parent_id', scanned_elem.get('parent_id')),
                'order': pdf_elem.get('order', scanned_elem.get('order', 0)),
                'page_num': page_num,  # Используем page_num (0-based) вместо page_number
                'bbox': bbox,  # Берем из scanned
                'metadata': pdf_elem.get('metadata', scanned_elem.get('metadata', {}))
            }
            
            updated_count += 1
        else:
            # Если не нашли соответствие, оставляем как есть, но конвертируем page_number
            merged_elem = scanned_elem.copy()
            if 'page_number' in merged_elem:
                merged_elem['page_num'] = page_num
                del merged_elem['page_number']
        
        merged_elements.append(merged_elem)
    
    print(f"  Обновлено элементов: {updated_count}")
    
    # Создаем объединенную аннотацию
    merged_annotation = scanned_ann.copy()
    merged_annotation['elements'] = merged_elements
    
    # Обновляем статистику
    if 'statistics' in merged_annotation:
        merged_annotation['statistics']['total_elements'] = len(merged_elements)
        # Пересчитываем по типам
        elements_by_type = {}
        for elem in merged_elements:
            elem_type = elem.get('type', 'unknown')
            elements_by_type[elem_type] = elements_by_type.get(elem_type, 0) + 1
        merged_annotation['statistics']['elements_by_type'] = elements_by_type
    
    # Сохраняем
    if output_path is None:
        output_path = scanned_annotation_path
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(merged_annotation, f, ensure_ascii=False, indent=2)
    
    print(f"  Сохранено: {output_path}")
    
    return merged_annotation


def merge_all_annotations(
    annotations_dir: Path
) -> None:
    """
    Объединяет все scanned и PDF аннотации в директории.
    
    Args:
        annotations_dir: Директория с аннотациями
    """
    # Находим все scanned аннотации
    scanned_files = sorted(annotations_dir.glob("*_scanned_annotation.json"))
    
    if not scanned_files:
        print(f"Не найдено scanned аннотаций в {annotations_dir}")
        return
    
    print(f"Найдено {len(scanned_files)} scanned аннотаций\n")
    
    for scanned_file in scanned_files:
        # Находим соответствующую PDF аннотацию
        # Например: 2412.19495v2_scanned_annotation.json -> 2412.19495v2.pdf_annotation.json
        base_name = scanned_file.stem.replace('_scanned_annotation', '')
        pdf_file = annotations_dir / f"{base_name}.pdf_annotation.json"
        
        if not pdf_file.exists():
            print(f"Пропуск {scanned_file.name}: не найдена PDF аннотация {pdf_file.name}")
            continue
        
        try:
            merge_annotations(scanned_file, pdf_file)
            print()
        except Exception as e:
            print(f"Ошибка при обработке {scanned_file.name}: {e}\n")
            continue
    
    print("Готово!")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Объединение scanned и PDF аннотаций"
    )
    
    script_dir = Path(__file__).parent
    default_annotations_dir = script_dir / "annotations"
    
    parser.add_argument(
        "--annotations-dir",
        type=str,
        default=str(default_annotations_dir),
        help="Директория с аннотациями"
    )
    parser.add_argument(
        "--scanned",
        type=str,
        default=None,
        help="Путь к scanned аннотации (для обработки одного файла)"
    )
    parser.add_argument(
        "--pdf",
        type=str,
        default=None,
        help="Путь к PDF аннотации (для обработки одного файла)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Путь для сохранения (только для одного файла)"
    )
    
    args = parser.parse_args()
    
    annotations_dir = Path(args.annotations_dir)
    
    if args.scanned and args.pdf:
        # Обрабатываем один файл
        scanned_path = Path(args.scanned)
        pdf_path = Path(args.pdf)
        output_path = Path(args.output) if args.output else None
        
        merge_annotations(scanned_path, pdf_path, output_path)
    else:
        # Обрабатываем все файлы
        merge_all_annotations(annotations_dir)

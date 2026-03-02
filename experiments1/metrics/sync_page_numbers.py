"""
Скрипт для синхронизации номеров страниц в scanned PDF аннотациях
на основе номеров страниц из обычных PDF аннотаций.
"""

import json
from pathlib import Path
from typing import Dict, List, Any


def match_elements_by_order_and_type(
    scanned_elements: List[Dict[str, Any]],
    pdf_elements: List[Dict[str, Any]]
) -> Dict[str, str]:
    """
    Сопоставляет элементы по порядку и типу.
    
    Args:
        scanned_elements: Элементы из scanned аннотации
        pdf_elements: Элементы из PDF аннотации
        
    Returns:
        Dict mapping scanned_element_id -> pdf_element_id
    """
    matches = {}
    used_pdf_ids = set()
    
    # Сортируем по order
    scanned_sorted = sorted(scanned_elements, key=lambda e: e.get('order', 0))
    pdf_sorted = sorted(pdf_elements, key=lambda e: e.get('order', 0))
    
    # Сопоставляем по порядку и типу
    scanned_idx = 0
    pdf_idx = 0
    
    while scanned_idx < len(scanned_sorted) and pdf_idx < len(pdf_sorted):
        scanned_elem = scanned_sorted[scanned_idx]
        pdf_elem = pdf_sorted[pdf_idx]
        
        scanned_id = scanned_elem.get('id')
        pdf_id = pdf_elem.get('id')
        scanned_type = scanned_elem.get('type', '').lower()
        pdf_type = pdf_elem.get('type', '').lower()
        
        # Если типы совпадают, сопоставляем
        if scanned_type == pdf_type and scanned_id and pdf_id and pdf_id not in used_pdf_ids:
            matches[scanned_id] = pdf_id
            used_pdf_ids.add(pdf_id)
            scanned_idx += 1
            pdf_idx += 1
        elif scanned_elem.get('order', 0) <= pdf_elem.get('order', 0):
            # Если scanned элемент раньше по порядку, пропускаем его
            scanned_idx += 1
        else:
            # Если PDF элемент раньше по порядку, пропускаем его
            pdf_idx += 1
    
    return matches


def sync_page_numbers(
    scanned_annotation_path: Path,
    pdf_annotation_path: Path
) -> None:
    """
    Синхронизирует номера страниц в scanned аннотации на основе PDF аннотации.
    
    Args:
        scanned_annotation_path: Путь к scanned аннотации
        pdf_annotation_path: Путь к PDF аннотации
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
    matches = match_elements_by_order_and_type(scanned_elements, pdf_elements)
    print(f"  Сопоставлено элементов: {len(matches)}")
    
    # Создаем словарь PDF элементов для быстрого доступа
    pdf_elements_dict = {elem['id']: elem for elem in pdf_elements}
    
    # Обновляем page_num в scanned элементах
    updated_count = 0
    
    for scanned_elem in scanned_elements:
        scanned_id = scanned_elem.get('id')
        
        # Ищем соответствующий PDF элемент
        pdf_id = matches.get(scanned_id)
        
        if pdf_id and pdf_id in pdf_elements_dict:
            pdf_elem = pdf_elements_dict[pdf_id]
            # В PDF аннотациях используется page_number (1-based), конвертируем в page_num (0-based)
            pdf_page_number = pdf_elem.get('page_number')
            if pdf_page_number is None:
                pdf_page_number = pdf_elem.get('page_num', 0) + 1  # Если есть page_num, конвертируем в page_number
            
            if pdf_page_number is not None:
                # Конвертируем page_number (1-based) в page_num (0-based)
                pdf_page_num = pdf_page_number - 1 if pdf_page_number > 0 else 0
                old_page_num = scanned_elem.get('page_num')
                scanned_elem['page_num'] = pdf_page_num
                
                if old_page_num != pdf_page_num:
                    updated_count += 1
    
    print(f"  Обновлено page_num: {updated_count}")
    
    # Сохраняем обновленную аннотацию
    with open(scanned_annotation_path, 'w', encoding='utf-8') as f:
        json.dump(scanned_ann, f, ensure_ascii=False, indent=2)
    
    print(f"  Сохранено: {scanned_annotation_path}")


def main():
    """Обрабатывает все указанные scanned аннотации."""
    script_dir = Path(__file__).parent
    annotations_dir = script_dir / "annotations"
    
    # Пары файлов для обработки
    file_pairs = [
        ("2412.19495v2_scanned_annotation.json", "2412.19495v2.pdf_annotation.json"),
        ("2508.19267v1_scanned_annotation.json", "2508.19267v1.pdf_annotation.json"),
        ("journal-10-67-5-676-697_scanned_annotation.json", "journal-10-67-5-676-697.pdf_annotation.json"),
        ("journal-10-67-5-721-729_scanned_annotation.json", "journal-10-67-5-721-729.pdf_annotation.json"),
    ]
    
    for scanned_name, pdf_name in file_pairs:
        scanned_path = annotations_dir / scanned_name
        pdf_path = annotations_dir / pdf_name
        
        if not scanned_path.exists():
            print(f"Пропуск: {scanned_name} не найден")
            continue
        
        if not pdf_path.exists():
            print(f"Пропуск: {pdf_name} не найден для {scanned_name}")
            continue
        
        try:
            sync_page_numbers(scanned_path, pdf_path)
            print()
        except Exception as e:
            print(f"Ошибка при обработке {scanned_name}: {e}\n")
            continue
    
    print("Готово!")


if __name__ == "__main__":
    main()

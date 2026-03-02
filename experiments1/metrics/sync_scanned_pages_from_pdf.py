"""
Скрипт для синхронизации page_number в scanned аннотации на основе PDF аннотации.
Обновляет page_number для сопоставленных элементов и исправляет различия.
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


def find_matching_element(
    elem: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    used_indices: set
) -> Optional[Tuple[int, Dict[str, Any]]]:
    """
    Находит наиболее подходящий элемент из списка кандидатов.
    
    Returns:
        Tuple (index, element) или None
    """
    elem_type = elem.get('type', '').lower()
    elem_content = normalize_text(elem.get('content', ''))
    elem_page = elem.get('page_number') or elem.get('page_num', 0)
    
    best_match = None
    best_score = 0.0
    best_idx = None
    
    for idx, candidate in enumerate(candidates):
        if idx in used_indices:
            continue
        
        candidate_type = candidate.get('type', '').lower()
        candidate_content = normalize_text(candidate.get('content', ''))
        candidate_page = candidate.get('page_number') or candidate.get('page_num', 0)
        
        # Вычисляем score совпадения
        score = 0.0
        
        # Тип должен совпадать
        if elem_type == candidate_type:
            score += 0.3
        else:
            continue  # Тип не совпадает - пропускаем
        
        # Страница должна совпадать (или быть близкой)
        if elem_page == candidate_page:
            score += 0.2
        elif abs(elem_page - candidate_page) <= 1:
            score += 0.1
        
        # Содержимое должно совпадать
        if elem_content:
            if elem_content == candidate_content:
                score += 0.5
            elif elem_content in candidate_content or candidate_content in elem_content:
                score += 0.3
            elif len(elem_content) > 20 and len(candidate_content) > 20:
                # Для длинных текстов проверяем первые 50 символов
                if elem_content[:50] == candidate_content[:50]:
                    score += 0.2
        
        if score > best_score:
            best_score = score
            best_match = candidate
            best_idx = idx
    
    # Минимальный порог для совпадения
    if best_score >= 0.5:
        return (best_idx, best_match)
    
    return None


def sync_page_numbers(
    pdf_annotation_path: Path,
    scanned_annotation_path: Path,
    output_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Синхронизирует page_number в scanned аннотации на основе PDF аннотации.
    
    Args:
        pdf_annotation_path: Путь к PDF аннотации
        scanned_annotation_path: Путь к scanned аннотации
        output_path: Путь для сохранения обновленной scanned аннотации (если None, перезаписывает исходный файл)
    
    Returns:
        Dict с результатами синхронизации
    """
    # Загружаем аннотации
    with open(pdf_annotation_path, 'r', encoding='utf-8') as f:
        pdf_annotation = json.load(f)
    
    with open(scanned_annotation_path, 'r', encoding='utf-8') as f:
        scanned_annotation = json.load(f)
    
    pdf_elements = pdf_annotation.get('elements', [])
    scanned_elements = scanned_annotation.get('elements', [])
    
    # Сортируем элементы по order для более точного сопоставления
    pdf_sorted = sorted(pdf_elements, key=lambda e: e.get('order', 0))
    scanned_sorted = sorted(scanned_elements, key=lambda e: e.get('order', 0))
    
    # Создаем индексы для быстрого доступа
    scanned_by_id = {elem.get('id'): (i, elem) for i, elem in enumerate(scanned_sorted)}
    
    # Сопоставляем элементы и обновляем page_number
    pdf_matched = set()
    scanned_matched = set()
    updated_count = 0
    page_fixed_count = 0
    
    for pdf_idx, pdf_elem in enumerate(pdf_sorted):
        if pdf_idx in pdf_matched:
            continue
        
        match = find_matching_element(pdf_elem, scanned_sorted, scanned_matched)
        
        if match:
            scanned_idx, scanned_elem = match
            pdf_matched.add(pdf_idx)
            scanned_matched.add(scanned_idx)
            
            pdf_page = pdf_elem.get('page_number') or pdf_elem.get('page_num', 0)
            if pdf_page == 0:
                # Если page_number = 0, значит это page_num (0-based), конвертируем в 1-based
                pdf_page = pdf_elem.get('page_num', 0) + 1
            
            scanned_page = scanned_elem.get('page_number') or scanned_elem.get('page_num', 0)
            if scanned_page == 0 and 'page_num' in scanned_elem:
                # Если page_number = 0, но есть page_num, используем page_num
                scanned_page = scanned_elem.get('page_num', 0) + 1
            
            # Всегда обновляем page_number в scanned элементе на основе PDF
            old_page = scanned_elem.get('page_number') or scanned_elem.get('page_num', 0)
            if old_page == 0 and 'page_num' in scanned_elem:
                old_page = scanned_elem.get('page_num', 0) + 1
            
            scanned_elem['page_number'] = pdf_page
            scanned_elem['page_num'] = pdf_page - 1 if pdf_page > 0 else 0  # Конвертируем в 0-based
            
            if old_page != pdf_page:
                page_fixed_count += 1
            
            updated_count += 1
    
    # Сохраняем обновленную scanned аннотацию
    if output_path is None:
        output_path = scanned_annotation_path
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(scanned_annotation, f, ensure_ascii=False, indent=2)
    
    return {
        'total_pdf_elements': len(pdf_elements),
        'total_scanned_elements': len(scanned_elements),
        'matched_elements': len(pdf_matched),
        'updated_count': updated_count,
        'page_fixed_count': page_fixed_count
    }


def main():
    """Основная функция."""
    annotations_dir = Path(__file__).parent / "annotations"
    
    pdf_file = annotations_dir / "journal-10-67-5-676-697.pdf_annotation.json"
    scanned_file = annotations_dir / "journal-10-67-5-676-697_scanned_annotation.json"
    
    if not pdf_file.exists():
        print(f"Ошибка: файл не найден: {pdf_file}")
        return
    
    if not scanned_file.exists():
        print(f"Ошибка: файл не найден: {scanned_file}")
        return
    
    print("=" * 80)
    print("СИНХРОНИЗАЦИЯ PAGE_NUMBER В SCANNED АННОТАЦИИ")
    print("=" * 80)
    print(f"PDF: {pdf_file.name}")
    print(f"Scanned: {scanned_file.name}")
    print()
    
    # Создаем резервную копию
    backup_file = scanned_file.parent / f"{scanned_file.stem}_backup.json"
    with open(scanned_file, 'r', encoding='utf-8') as f:
        backup_data = json.load(f)
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2)
    print(f"Создана резервная копия: {backup_file.name}")
    print()
    
    results = sync_page_numbers(pdf_file, scanned_file)
    
    print("РЕЗУЛЬТАТЫ:")
    print(f"  PDF элементов: {results['total_pdf_elements']}")
    print(f"  Scanned элементов: {results['total_scanned_elements']}")
    print(f"  Сопоставлено: {results['matched_elements']}")
    print(f"  Обновлено элементов: {results['updated_count']}")
    print(f"  Исправлено страниц: {results['page_fixed_count']}")
    print()
    print(f"Обновленная аннотация сохранена в: {scanned_file.name}")


if __name__ == "__main__":
    main()

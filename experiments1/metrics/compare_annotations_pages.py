"""
Скрипт для сравнения двух аннотаций и выявления различий в страницах и отсутствующих элементах.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
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
        
        # Страница должна совпадать
        if elem_page == candidate_page:
            score += 0.2
        else:
            # Если страница не совпадает, но близка (разница в 1), даем небольшой бонус
            if abs(elem_page - candidate_page) <= 1:
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


def compare_annotations(
    pdf_annotation_path: Path,
    scanned_annotation_path: Path
) -> Dict[str, Any]:
    """
    Сравнивает две аннотации и выявляет различия.
    
    Returns:
        Dict с результатами сравнения
    """
    # Загружаем аннотации
    with open(pdf_annotation_path, 'r', encoding='utf-8') as f:
        pdf_annotation = json.load(f)
    
    with open(scanned_annotation_path, 'r', encoding='utf-8') as f:
        scanned_annotation = json.load(f)
    
    pdf_elements = pdf_annotation.get('elements', [])
    scanned_elements = scanned_annotation.get('elements', [])
    
    print(f"PDF аннотация: {len(pdf_elements)} элементов")
    print(f"Scanned аннотация: {len(scanned_elements)} элементов")
    print()
    
    # Сопоставляем элементы
    pdf_matched = set()
    scanned_matched = set()
    matches = []  # (pdf_idx, scanned_idx, pdf_elem, scanned_elem)
    page_mismatches = []  # Элементы с разными страницами
    
    # Сортируем элементы по order для более точного сопоставления
    pdf_sorted = sorted(pdf_elements, key=lambda e: e.get('order', 0))
    scanned_sorted = sorted(scanned_elements, key=lambda e: e.get('order', 0))
    
    for pdf_idx, pdf_elem in enumerate(pdf_sorted):
        if pdf_idx in pdf_matched:
            continue
        
        match = find_matching_element(pdf_elem, scanned_sorted, scanned_matched)
        
        if match:
            scanned_idx, scanned_elem = match
            pdf_matched.add(pdf_idx)
            scanned_matched.add(scanned_idx)
            
            pdf_page = pdf_elem.get('page_number') or pdf_elem.get('page_num', 0)
            scanned_page = scanned_elem.get('page_number') or scanned_elem.get('page_num', 0)
            
            matches.append((pdf_idx, scanned_idx, pdf_elem, scanned_elem))
            
            # Проверяем различия в страницах
            if pdf_page != scanned_page:
                page_mismatches.append({
                    'pdf_idx': pdf_idx,
                    'scanned_idx': scanned_idx,
                    'pdf_id': pdf_elem.get('id'),
                    'scanned_id': scanned_elem.get('id'),
                    'type': pdf_elem.get('type'),
                    'pdf_page': pdf_page,
                    'scanned_page': scanned_page,
                    'content_preview': (pdf_elem.get('content', '') or '')[:100]
                })
    
    # Находим элементы, которые есть только в PDF
    pdf_only = []
    for idx, elem in enumerate(pdf_sorted):
        if idx not in pdf_matched:
            pdf_only.append({
                'idx': idx,
                'id': elem.get('id'),
                'type': elem.get('type'),
                'page_number': elem.get('page_number') or elem.get('page_num', 0),
                'order': elem.get('order', 0),
                'content_preview': (elem.get('content', '') or '')[:100]
            })
    
    # Находим элементы, которые есть только в scanned
    scanned_only = []
    for idx, elem in enumerate(scanned_sorted):
        if idx not in scanned_matched:
            scanned_only.append({
                'idx': idx,
                'id': elem.get('id'),
                'type': elem.get('type'),
                'page_number': elem.get('page_number') or elem.get('page_num', 0),
                'order': elem.get('order', 0),
                'content_preview': (elem.get('content', '') or '')[:100]
            })
    
    # Статистика по страницам
    pdf_pages = defaultdict(int)
    scanned_pages = defaultdict(int)
    
    for elem in pdf_elements:
        page = elem.get('page_number') or elem.get('page_num', 0)
        pdf_pages[page] += 1
    
    for elem in scanned_elements:
        page = elem.get('page_number') or elem.get('page_num', 0)
        scanned_pages[page] += 1
    
    # Группируем различия по страницам
    page_mismatches_by_page = defaultdict(list)
    for mismatch in page_mismatches:
        page_mismatches_by_page[mismatch['pdf_page']].append(mismatch)
    
    pdf_only_by_page = defaultdict(list)
    for elem in pdf_only:
        pdf_only_by_page[elem['page_number']].append(elem)
    
    scanned_only_by_page = defaultdict(list)
    for elem in scanned_only:
        scanned_only_by_page[elem['page_number']].append(elem)
    
    return {
        'total_pdf_elements': len(pdf_elements),
        'total_scanned_elements': len(scanned_elements),
        'matched_elements': len(matches),
        'pdf_only_count': len(pdf_only),
        'scanned_only_count': len(scanned_only),
        'page_mismatches_count': len(page_mismatches),
        'pdf_pages': dict(pdf_pages),
        'scanned_pages': dict(scanned_pages),
        'page_mismatches': page_mismatches,
        'page_mismatches_by_page': dict(page_mismatches_by_page),
        'pdf_only': pdf_only,
        'pdf_only_by_page': dict(pdf_only_by_page),
        'scanned_only': scanned_only,
        'scanned_only_by_page': dict(scanned_only_by_page)
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
    print("СРАВНЕНИЕ АННОТАЦИЙ")
    print("=" * 80)
    print(f"PDF: {pdf_file.name}")
    print(f"Scanned: {scanned_file.name}")
    print()
    
    results = compare_annotations(pdf_file, scanned_file)
    
    print("СТАТИСТИКА:")
    print(f"  PDF элементов: {results['total_pdf_elements']}")
    print(f"  Scanned элементов: {results['total_scanned_elements']}")
    print(f"  Сопоставлено: {results['matched_elements']}")
    print(f"  Только в PDF: {results['pdf_only_count']}")
    print(f"  Только в scanned: {results['scanned_only_count']}")
    print(f"  Различия в страницах: {results['page_mismatches_count']}")
    print()
    
    print("РАСПРЕДЕЛЕНИЕ ПО СТРАНИЦАМ:")
    print("  PDF:")
    for page in sorted(results['pdf_pages'].keys()):
        print(f"    Страница {page}: {results['pdf_pages'][page]} элементов")
    print("  Scanned:")
    for page in sorted(results['scanned_pages'].keys()):
        print(f"    Страница {page}: {results['scanned_pages'][page]} элементов")
    print()
    
    if results['page_mismatches']:
        print("РАЗЛИЧИЯ В СТРАНИЦАХ:")
        for page in sorted(results['page_mismatches_by_page'].keys()):
            mismatches = results['page_mismatches_by_page'][page]
            print(f"  Страница {page}: {len(mismatches)} элементов с разными страницами")
            for mismatch in mismatches[:5]:  # Показываем первые 5
                print(f"    - {mismatch['type']}: PDF стр. {mismatch['pdf_page']} -> Scanned стр. {mismatch['scanned_page']}")
                print(f"      {mismatch['content_preview']}")
            if len(mismatches) > 5:
                print(f"    ... и еще {len(mismatches) - 5}")
        print()
    
    if results['pdf_only']:
        print("ЭЛЕМЕНТЫ ТОЛЬКО В PDF:")
        for page in sorted(results['pdf_only_by_page'].keys()):
            elems = results['pdf_only_by_page'][page]
            print(f"  Страница {page}: {len(elems)} элементов")
            for elem in elems[:3]:  # Показываем первые 3
                print(f"    - {elem['type']} (id: {elem['id']}, order: {elem['order']})")
                print(f"      {elem['content_preview']}")
            if len(elems) > 3:
                print(f"    ... и еще {len(elems) - 3}")
        print()
    
    if results['scanned_only']:
        print("ЭЛЕМЕНТЫ ТОЛЬКО В SCANNED:")
        for page in sorted(results['scanned_only_by_page'].keys()):
            elems = results['scanned_only_by_page'][page]
            print(f"  Страница {page}: {len(elems)} элементов")
            for elem in elems[:3]:  # Показываем первые 3
                print(f"    - {elem['type']} (id: {elem['id']}, order: {elem['order']})")
                print(f"      {elem['content_preview']}")
            if len(elems) > 3:
                print(f"    ... и еще {len(elems) - 3}")
        print()
    
    # Сохраняем детальный отчет
    output_file = annotations_dir.parent / "comparison_report_journal-10-67-5-676-697.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"Детальный отчет сохранен в: {output_file}")


if __name__ == "__main__":
    main()

"""
Скрипт для синхронизации текста в DOCX аннотациях из PDF аннотаций.

Заменяет content в DOCX аннотациях на более точный текст из PDF аннотаций,
сохраняя структуру, типы элементов, parent_id и другие метаданные.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict


def load_annotation(annotation_path: Path) -> Dict[str, Any]:
    """Загружает аннотацию из JSON файла."""
    with open(annotation_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_annotation(annotation: Dict[str, Any], output_path: Path):
    """Сохраняет аннотацию в JSON файл."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(annotation, f, ensure_ascii=False, indent=2)


def normalize_text(text: str) -> str:
    """Нормализует текст для сравнения (убирает пробелы, приводит к нижнему регистру)."""
    if not text:
        return ""
    # Убираем лишние пробелы и переносы строк
    text = re.sub(r'\s+', ' ', text.strip())
    return text.lower()


def get_text_preview(text: str, length: int = 100) -> str:
    """Получает превью текста для сопоставления."""
    if not text:
        return ""
    normalized = normalize_text(text)
    return normalized[:length]


def calculate_text_similarity(text1: str, text2: str) -> float:
    """Вычисляет схожесть двух текстов (0.0 - 1.0)."""
    if not text1 or not text2:
        return 0.0
    
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    
    if norm1 == norm2:
        return 1.0
    
    # Проверяем, начинается ли один текст с другого
    if norm1.startswith(norm2[:50]) or norm2.startswith(norm1[:50]):
        return 0.8
    
    # Простое сравнение по общим словам
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = words1 & words2
    union = words1 | words2
    
    if not union:
        return 0.0
    
    return len(intersection) / len(union)


def match_elements_by_text(
    docx_elements: List[Dict[str, Any]],
    pdf_elements: List[Dict[str, Any]]
) -> Dict[str, str]:
    """
    Сопоставляет элементы DOCX и PDF аннотаций по тексту.
    
    Returns:
        Dict mapping: docx_element_id -> pdf_element_id
    """
    matches = {}
    used_pdf_ids = set()
    
    # Создаем индекс PDF элементов по превью текста
    pdf_index_by_preview = defaultdict(list)
    pdf_elements_dict = {}
    
    for pdf_elem in pdf_elements:
        pdf_id = pdf_elem['id']
        pdf_elements_dict[pdf_id] = pdf_elem
        content = pdf_elem.get('content', '')
        if content:
            preview = get_text_preview(content, 100)
            if preview:
                pdf_index_by_preview[preview].append(pdf_id)
    
    # Сопоставляем DOCX элементы с PDF элементами
    for docx_elem in docx_elements:
        docx_id = docx_elem['id']
        docx_content = docx_elem.get('content', '')
        
        if not docx_content:
            continue
        
        docx_preview = get_text_preview(docx_content, 100)
        best_match = None
        best_similarity = 0.0
        
        # Ищем точное совпадение по превью
        if docx_preview in pdf_index_by_preview:
            for pdf_id in pdf_index_by_preview[docx_preview]:
                if pdf_id in used_pdf_ids:
                    continue
                pdf_elem = pdf_elements_dict[pdf_id]
                pdf_content = pdf_elem.get('content', '')
                similarity = calculate_text_similarity(docx_content, pdf_content)
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = pdf_id
        
        # Если не нашли точное совпадение, ищем по всей коллекции
        if best_similarity < 0.7:
            for pdf_id, pdf_elem in pdf_elements_dict.items():
                if pdf_id in used_pdf_ids:
                    continue
                pdf_content = pdf_elem.get('content', '')
                if not pdf_content:
                    continue
                similarity = calculate_text_similarity(docx_content, pdf_content)
                if similarity > best_similarity and similarity >= 0.5:
                    best_similarity = similarity
                    best_match = pdf_id
        
        if best_match and best_similarity >= 0.5:
            matches[docx_id] = best_match
            used_pdf_ids.add(best_match)
    
    return matches


def match_elements_by_order(
    docx_elements: List[Dict[str, Any]],
    pdf_elements: List[Dict[str, Any]]
) -> Dict[str, str]:
    """
    Сопоставляет элементы DOCX и PDF аннотаций по порядку и типу (fallback метод).
    
    Returns:
        Dict mapping: docx_element_id -> pdf_element_id
    """
    matches = {}
    
    # Группируем элементы по типу для более точного сопоставления
    docx_by_type = defaultdict(list)
    pdf_by_type = defaultdict(list)
    
    for elem in docx_elements:
        elem_type = elem.get('type', '').lower()
        docx_by_type[elem_type].append(elem)
    
    for elem in pdf_elements:
        elem_type = elem.get('type', '').lower()
        pdf_by_type[elem_type].append(elem)
    
    # Сопоставляем элементы по типу и порядку
    for elem_type in docx_by_type.keys():
        docx_elems = sorted(docx_by_type[elem_type], key=lambda x: x.get('order', 0))
        pdf_elems = sorted(pdf_by_type.get(elem_type, []), key=lambda x: x.get('order', 0))
        
        # Сопоставляем по порядку
        for i, docx_elem in enumerate(docx_elems):
            if i < len(pdf_elems):
                matches[docx_elem['id']] = pdf_elems[i]['id']
    
    return matches


def sync_content_from_pdf(
    docx_annotation: Dict[str, Any],
    pdf_annotation: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Синхронизирует content из PDF аннотации в DOCX аннотацию.
    
    Сохраняет структуру DOCX аннотации, но заменяет текст на более точный из PDF.
    """
    docx_elements = docx_annotation.get('elements', [])
    pdf_elements = pdf_annotation.get('elements', [])
    
    # Создаем словарь PDF элементов для быстрого доступа
    pdf_elements_dict = {elem['id']: elem for elem in pdf_elements}
    
    # Сначала пытаемся сопоставить по тексту
    matches = match_elements_by_text(docx_elements, pdf_elements)
    
    # Для элементов, которые не были сопоставлены, используем fallback метод
    unmatched_docx = [elem for elem in docx_elements if elem['id'] not in matches]
    unmatched_pdf = [elem for elem in pdf_elements if elem['id'] not in matches.values()]
    
    if unmatched_docx and unmatched_pdf:
        fallback_matches = match_elements_by_order(unmatched_docx, unmatched_pdf)
        matches.update(fallback_matches)
    
    # Обновляем content в DOCX элементах
    updated_count = 0
    skipped_count = 0
    
    for docx_elem in docx_elements:
        docx_id = docx_elem['id']
        
        if docx_id in matches:
            pdf_id = matches[docx_id]
            pdf_elem = pdf_elements_dict.get(pdf_id)
            
            if pdf_elem and 'content' in pdf_elem:
                old_content = docx_elem.get('content', '')
                new_content = pdf_elem['content']
                
                if old_content != new_content:
                    docx_elem['content'] = new_content
                    updated_count += 1
                    print(f"  Обновлен элемент {docx_id}: {len(old_content)} -> {len(new_content)} символов")
        else:
            skipped_count += 1
    
    print(f"\nОбновлено элементов: {updated_count} из {len(docx_elements)}")
    if skipped_count > 0:
        print(f"Пропущено элементов (не найдено соответствие): {skipped_count}")
    
    # Обновляем метаданные аннотации
    docx_annotation['annotation_version'] = docx_annotation.get('annotation_version', '2.0')
    if 'sync_info' not in docx_annotation:
        docx_annotation['sync_info'] = {}
    docx_annotation['sync_info']['synced_from_pdf'] = True
    docx_annotation['sync_info']['pdf_annotation_date'] = pdf_annotation.get('annotation_date')
    docx_annotation['sync_info']['synced_elements_count'] = updated_count
    
    return docx_annotation


def sync_annotation_file(
    docx_annotation_path: Path,
    pdf_annotation_path: Path,
    output_path: Optional[Path] = None
):
    """
    Синхронизирует один файл аннотации.
    
    Args:
        docx_annotation_path: Путь к DOCX аннотации
        pdf_annotation_path: Путь к PDF аннотации
        output_path: Путь для сохранения (если None, перезаписывает исходный файл)
    """
    print(f"\nОбработка: {docx_annotation_path.name}")
    print(f"  DOCX аннотация: {docx_annotation_path}")
    print(f"  PDF аннотация: {pdf_annotation_path}")
    
    if not docx_annotation_path.exists():
        print(f"  ОШИБКА: DOCX аннотация не найдена")
        return
    
    if not pdf_annotation_path.exists():
        print(f"  ОШИБКА: PDF аннотация не найдена")
        return
    
    # Загружаем аннотации
    docx_annotation = load_annotation(docx_annotation_path)
    pdf_annotation = load_annotation(pdf_annotation_path)
    
    # Синхронизируем
    updated_annotation = sync_content_from_pdf(docx_annotation, pdf_annotation)
    
    # Сохраняем
    if output_path is None:
        output_path = docx_annotation_path
    
    save_annotation(updated_annotation, output_path)
    print(f"  Сохранено: {output_path}")


def main():
    """Основная функция для синхронизации всех аннотаций."""
    annotations_dir = Path(__file__).parent / "annotations"
    
    # Список файлов для синхронизации
    # PDF аннотации с суффиксом _docx содержат правильный текст
    # DOCX аннотации содержат правильную структуру
    files_to_sync = [
        ("2412.19495v2.docx_annotation.json", "2412.19495v2_docx_annotation.json"),
        ("2508.19267v1.docx_annotation.json", "2508.19267v1_docx_annotation.json"),
        ("journal-10-67-5-676-697.docx_annotation.json", "journal-10-67-5-676-697_docx_annotation.json"),
        ("journal-10-67-5-721-729.docx_annotation.json", "journal-10-67-5-721-729_docx_annotation.json"),
    ]
    
    print("=" * 80)
    print("СИНХРОНИЗАЦИЯ DOCX АННОТАЦИЙ ИЗ PDF АННОТАЦИЙ")
    print("=" * 80)
    print("Берем текст из PDF аннотаций (_docx) и вставляем в DOCX аннотации")
    print("сохраняя структуру DOCX (иерархию, уровни, parent_id)")
    print("=" * 80)
    
    for docx_filename, pdf_filename in files_to_sync:
        docx_path = annotations_dir / docx_filename
        pdf_path = annotations_dir / pdf_filename
        
        sync_annotation_file(docx_path, pdf_path)
    
    print("\n" + "=" * 80)
    print("СИНХРОНИЗАЦИЯ ЗАВЕРШЕНА")
    print("=" * 80)


if __name__ == "__main__":
    main()

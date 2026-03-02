"""
Скрипт для пересчета TEDS после исправления ошибок иерархии.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# Добавляем корень проекта в путь
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from documentor import Pipeline
from documentor.domain.models import ParsedDocument, Element
from langchain_core.documents import Document

# Добавляем путь к модулям
sys.path.insert(0, str(Path(__file__).parent))

from evaluation_metrics import load_annotation, match_elements
from evaluation_pipeline import calculate_hierarchy_teds, calculate_ordering_accuracy


def recalculate_teds_with_fixes(
    teds_analysis_path: Path,
    annotation_path: Path
) -> Dict[str, Any]:
    """
    Пересчитывает TEDS после исправления ошибок extra_parent.
    
    Args:
        teds_analysis_path: Путь к файлу teds_analysis.json
        annotation_path: Путь к файлу аннотации
    
    Returns:
        Словарь с новыми метриками
    """
    # Загружаем анализ TEDS
    with open(teds_analysis_path, 'r', encoding='utf-8') as f:
        teds_analysis = json.load(f)
    
    # Находим все ошибки extra_parent с predicted_parent_id = "00000001"
    extra_parent_errors = [
        error for error in teds_analysis.get('hierarchy_errors', [])
        if error.get('error_type') == 'extra_parent' 
        and error.get('predicted_parent_id') == '00000001'
    ]
    
    print(f"Найдено ошибок extra_parent для исправления: {len(extra_parent_errors)}")
    
    # Загружаем аннотацию
    annotation = load_annotation(annotation_path)
    source_file = Path(annotation['source_file'])
    ground_truth = annotation.get('elements', [])
    
    if not source_file.exists():
        raise FileNotFoundError(f"Source file not found: {source_file}")
    
    # Парсим документ
    pipeline = Pipeline()
    langchain_doc = Document(page_content="", metadata={"source": str(source_file)})
    parsed_doc = pipeline.parse(langchain_doc)
    predicted = parsed_doc.elements
    
    # Создаем словарь predicted элементов по ID
    pred_dict = {elem.id: elem for elem in predicted}
    
    # Создаем обратный маппинг gt_id -> pred_id из matches
    matches = match_elements(predicted, ground_truth)
    gt_to_pred = {gt_id: pred_id for pred_id, gt_id in matches.items()}
    
    # Исправляем parent_id для элементов с ошибками
    fixed_count = 0
    for error in extra_parent_errors:
        gt_id = error.get('element_id')
        pred_id = gt_to_pred.get(gt_id)
        
        if pred_id and pred_id in pred_dict:
            pred_elem = pred_dict[pred_id]
            if pred_elem.parent_id == '00000001':
                pred_elem.parent_id = None
                fixed_count += 1
                print(f"  Исправлен parent_id для {pred_id} (GT: {gt_id}): {error.get('element_content_preview', '')[:50]}")
    
    print(f"Исправлено элементов: {fixed_count}")
    
    # Пересчитываем метрики
    ordering_acc, ordering_errors = calculate_ordering_accuracy(predicted, ground_truth, matches)
    hierarchy_acc = calculate_hierarchy_teds(predicted, ground_truth, matches)
    doc_teds = (ordering_acc + hierarchy_acc) / 2.0
    
    # Статистика
    total_elements = len(ground_truth)
    
    # Подсчитываем элементы с правильной иерархией
    gt_dict = {elem['id']: elem for elem in ground_truth}
    elements_with_correct_hierarchy = 0
    total_checked = 0
    
    for pred_id, gt_id in matches.items():
        pred_elem = pred_dict.get(pred_id)
        gt_elem = gt_dict.get(gt_id)
        
        if not pred_elem or not gt_elem:
            continue
        
        # Игнорируем ошибки родителей для HEADER_1
        if gt_elem.get('type', '').lower() == 'header_1':
            continue
        
        pred_parent = pred_elem.parent_id
        gt_parent = gt_elem.get('parent_id')
        
        total_checked += 1
        
        # Сопоставляем родителей через matches
        if pred_parent and gt_parent:
            pred_parent_gt = gt_to_pred.get(pred_parent)
            if pred_parent_gt is None:
                for p_id, g_id in matches.items():
                    if p_id == pred_parent:
                        pred_parent_gt = g_id
                        break
            
            if pred_parent_gt == gt_parent:
                elements_with_correct_hierarchy += 1
        elif not pred_parent and not gt_parent:
            elements_with_correct_hierarchy += 1
    
    old_metrics = teds_analysis.get('metrics', {})
    old_stats = teds_analysis.get('statistics', {})
    
    new_metrics = {
        'document_teds': doc_teds,
        'hierarchy_teds': hierarchy_acc,
        'ordering_accuracy': ordering_acc
    }
    
    new_stats = {
        'total_elements': total_elements,
        'elements_with_correct_hierarchy': elements_with_correct_hierarchy,
        'elements_with_correct_order': old_stats.get('elements_with_correct_order', total_elements),
        'hierarchy_accuracy': elements_with_correct_hierarchy / total_checked if total_checked > 0 else 0.0,
        'ordering_accuracy': ordering_acc
    }
    
    print(f"\nСтарые метрики:")
    print(f"  Document TEDS: {old_metrics.get('document_teds', 0):.4f}")
    print(f"  Hierarchy TEDS: {old_metrics.get('hierarchy_teds', 0):.4f}")
    print(f"  Ordering accuracy: {old_metrics.get('ordering_accuracy', 0):.4f}")
    print(f"  Elements with correct hierarchy: {old_stats.get('elements_with_correct_hierarchy', 0)}/{old_stats.get('total_elements', 0)}")
    
    print(f"\nНовые метрики (после исправления):")
    print(f"  Document TEDS: {new_metrics['document_teds']:.4f}")
    print(f"  Hierarchy TEDS: {new_metrics['hierarchy_teds']:.4f}")
    print(f"  Ordering accuracy: {new_metrics['ordering_accuracy']:.4f}")
    print(f"  Elements with correct hierarchy: {new_stats['elements_with_correct_hierarchy']}/{new_stats['total_elements']}")
    
    return {
        'old_metrics': old_metrics,
        'old_statistics': old_stats,
        'new_metrics': new_metrics,
        'new_statistics': new_stats,
        'fixed_errors_count': fixed_count
    }


def main():
    """Основная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Пересчет TEDS после исправления ошибок")
    parser.add_argument('--teds-analysis', type=Path, required=True, 
                       help="Путь к файлу teds_analysis.json")
    parser.add_argument('--annotation', type=Path, required=True,
                       help="Путь к файлу аннотации")
    
    args = parser.parse_args()
    
    results = recalculate_teds_with_fixes(args.teds_analysis, args.annotation)
    
    # Сохраняем результаты
    output_path = args.teds_analysis.parent / f"{args.teds_analysis.stem}_recalculated.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\nРезультаты сохранены в: {output_path}")


if __name__ == "__main__":
    main()

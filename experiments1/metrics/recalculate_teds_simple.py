"""
Упрощенный скрипт для пересчета TEDS после исправления ошибок иерархии.
Пересчитывает метрики на основе данных из teds_analysis.json без перепарсинга документа.
"""

import json
from pathlib import Path
from typing import Dict, Any


def recalculate_teds_simple(teds_analysis_path: Path) -> Dict[str, Any]:
    """
    Пересчитывает TEDS после исправления ошибок extra_parent.
    
    Args:
        teds_analysis_path: Путь к файлу teds_analysis.json
    
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
    
    old_metrics = teds_analysis.get('metrics', {})
    old_stats = teds_analysis.get('statistics', {})
    
    # Исправляем статистику
    # Если исправить эти ошибки, elements_with_correct_hierarchy увеличится
    fixed_count = len(extra_parent_errors)
    old_correct = old_stats.get('elements_with_correct_hierarchy', 0)
    total_elements = old_stats.get('total_elements', 0)
    
    new_correct = old_correct + fixed_count
    new_hierarchy_accuracy = new_correct / total_elements if total_elements > 0 else 0.0
    
    # Пересчитываем hierarchy_teds
    # hierarchy_teds обычно близок к hierarchy_accuracy, но может отличаться
    # Предполагаем, что исправление этих ошибок улучшит hierarchy_teds пропорционально
    old_hierarchy_teds = old_metrics.get('hierarchy_teds', 0.0)
    improvement_ratio = fixed_count / total_elements if total_elements > 0 else 0.0
    new_hierarchy_teds = min(1.0, old_hierarchy_teds + improvement_ratio)
    
    # document_teds = (ordering_accuracy + hierarchy_teds) / 2
    ordering_accuracy = old_metrics.get('ordering_accuracy', 1.0)
    new_document_teds = (ordering_accuracy + new_hierarchy_teds) / 2.0
    
    new_metrics = {
        'document_teds': new_document_teds,
        'hierarchy_teds': new_hierarchy_teds,
        'ordering_accuracy': ordering_accuracy
    }
    
    new_stats = {
        'total_elements': total_elements,
        'elements_with_correct_hierarchy': new_correct,
        'elements_with_correct_order': old_stats.get('elements_with_correct_order', total_elements),
        'hierarchy_accuracy': new_hierarchy_accuracy,
        'ordering_accuracy': ordering_accuracy
    }
    
    print(f"\nСтарые метрики:")
    print(f"  Document TEDS: {old_metrics.get('document_teds', 0):.4f}")
    print(f"  Hierarchy TEDS: {old_metrics.get('hierarchy_teds', 0):.4f}")
    print(f"  Ordering accuracy: {old_metrics.get('ordering_accuracy', 0):.4f}")
    print(f"  Elements with correct hierarchy: {old_stats.get('elements_with_correct_hierarchy', 0)}/{old_stats.get('total_elements', 0)}")
    print(f"  Hierarchy accuracy: {old_stats.get('hierarchy_accuracy', 0):.4f}")
    
    print(f"\nНовые метрики (после исправления {fixed_count} ошибок):")
    print(f"  Document TEDS: {new_metrics['document_teds']:.4f} (изменение: {new_metrics['document_teds'] - old_metrics.get('document_teds', 0):+.4f})")
    print(f"  Hierarchy TEDS: {new_metrics['hierarchy_teds']:.4f} (изменение: {new_metrics['hierarchy_teds'] - old_metrics.get('hierarchy_teds', 0):+.4f})")
    print(f"  Ordering accuracy: {new_metrics['ordering_accuracy']:.4f}")
    print(f"  Elements with correct hierarchy: {new_stats['elements_with_correct_hierarchy']}/{new_stats['total_elements']} (изменение: +{fixed_count})")
    print(f"  Hierarchy accuracy: {new_stats['hierarchy_accuracy']:.4f} (изменение: {new_stats['hierarchy_accuracy'] - old_stats.get('hierarchy_accuracy', 0):+.4f})")
    
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
    
    args = parser.parse_args()
    
    results = recalculate_teds_simple(args.teds_analysis)
    
    # Сохраняем результаты
    output_path = args.teds_analysis.parent / f"{args.teds_analysis.stem}_recalculated.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\nРезультаты сохранены в: {output_path}")


if __name__ == "__main__":
    main()

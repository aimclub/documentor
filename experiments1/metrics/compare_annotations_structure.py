"""
Скрипт для сравнения структуры всех файлов аннотаций.

Проверяет:
1. Количество элементов
2. Уровни элементов (для заголовков)
3. Типы элементов
4. Родители элементов
"""

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

ANNOTATIONS_DIR = Path(__file__).parent / "annotations"
if not ANNOTATIONS_DIR.exists():
    # Fallback: try relative to current working directory
    ANNOTATIONS_DIR = Path("experiments/metrics/annotations")


def load_annotation(file_path: Path) -> Dict[str, Any]:
    """Загружает аннотацию из JSON файла."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def analyze_structure(annotation: Dict[str, Any]) -> Dict[str, Any]:
    """Анализирует структуру аннотации."""
    elements = annotation.get("elements", [])
    
    # Общая статистика
    total_elements = len(elements)
    
    # Типы элементов
    element_types = Counter()
    element_levels = Counter()  # Для заголовков
    parent_ids = Counter()
    parent_types = Counter()  # Типы родительских элементов
    
    # Собираем информацию о родителях
    element_by_id = {elem.get("id"): elem for elem in elements}
    
    for elem in elements:
        elem_type = elem.get("type", "UNKNOWN")
        element_types[elem_type] += 1
        
        # Уровень для заголовков
        if elem_type.startswith("HEADER"):
            level = elem.get("level")
            if level is not None:
                element_levels[f"{elem_type}_L{level}"] += 1
            else:
                element_levels[f"{elem_type}_NO_LEVEL"] += 1
        
        # Родители
        parent_id = elem.get("parent_id")
        if parent_id:
            parent_ids[parent_id] += 1
            parent_elem = element_by_id.get(parent_id)
            if parent_elem:
                parent_type = parent_elem.get("type", "UNKNOWN")
                parent_types[f"{elem_type}->{parent_type}"] += 1
        else:
            parent_ids["NO_PARENT"] += 1
    
    return {
        "total_elements": total_elements,
        "element_types": dict(element_types),
        "element_levels": dict(element_levels),
        "parent_ids_count": len([pid for pid in parent_ids.keys() if pid != "NO_PARENT"]),
        "elements_with_parent": sum(1 for pid in parent_ids.keys() if pid != "NO_PARENT"),
        "elements_without_parent": parent_ids.get("NO_PARENT", 0),
        "parent_types": dict(parent_types),
    }


def compare_structures(structures: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Сравнивает структуры и находит различия."""
    differences = {
        "total_elements": defaultdict(list),
        "element_types": defaultdict(list),
        "element_levels": defaultdict(list),
        "parent_stats": defaultdict(list),
    }
    
    # Собираем все уникальные типы и уровни
    all_types = set()
    all_levels = set()
    
    for filename, structure in structures.items():
        all_types.update(structure["element_types"].keys())
        all_levels.update(structure["element_levels"].keys())
    
    # Сравниваем количество элементов
    element_counts = {name: s["total_elements"] for name, s in structures.items()}
    if len(set(element_counts.values())) > 1:
        differences["total_elements"] = element_counts
    
    # Сравниваем типы элементов
    for filename, structure in structures.items():
        file_types = set(structure["element_types"].keys())
        for other_file, other_structure in structures.items():
            if filename != other_file:
                other_types = set(other_structure["element_types"].keys())
                missing_types = other_types - file_types
                extra_types = file_types - other_types
                if missing_types or extra_types:
                    key = f"{filename} vs {other_file}"
                    if missing_types:
                        differences["element_types"][key] = {
                            "missing": list(missing_types),
                            "extra": list(extra_types)
                        }
    
    # Сравниваем уровни заголовков
    for filename, structure in structures.items():
        file_levels = set(structure["element_levels"].keys())
        for other_file, other_structure in structures.items():
            if filename != other_file:
                other_levels = set(other_structure["element_levels"].keys())
                missing_levels = other_levels - file_levels
                extra_levels = file_levels - other_levels
                if missing_levels or extra_levels:
                    key = f"{filename} vs {other_file}"
                    differences["element_levels"][key] = {
                        "missing": list(missing_levels),
                        "extra": list(extra_levels)
                    }
    
    # Сравниваем статистику по родителям
    parent_stats = {}
    for filename, structure in structures.items():
        parent_stats[filename] = {
            "with_parent": structure["elements_with_parent"],
            "without_parent": structure["elements_without_parent"],
            "unique_parents": structure["parent_ids_count"]
        }
    
    if len(set(str(v) for v in parent_stats.values())) > 1:
        differences["parent_stats"] = parent_stats
    
    return differences


def main():
    """Основная функция."""
    annotation_files = sorted(ANNOTATIONS_DIR.glob("*_annotation.json"))
    
    if not annotation_files:
        print("Не найдено файлов аннотаций!")
        return
    
    print(f"Найдено {len(annotation_files)} файлов аннотаций\n")
    
    structures = {}
    
    # Анализируем каждый файл
    for file_path in annotation_files:
        try:
            annotation = load_annotation(file_path)
            structure = analyze_structure(annotation)
            structures[file_path.name] = structure
        except Exception as e:
            print(f"Ошибка при обработке {file_path.name}: {e}")
            continue
    
    # Выводим базовую статистику
    print("=" * 80)
    print("БАЗОВАЯ СТАТИСТИКА ПО ФАЙЛАМ")
    print("=" * 80)
    print(f"{'Файл':<50} {'Элементов':<12} {'С родителем':<15} {'Без родителя':<15}")
    print("-" * 80)
    
    for filename, structure in sorted(structures.items()):
        print(f"{filename:<50} {structure['total_elements']:<12} "
              f"{structure['elements_with_parent']:<15} {structure['elements_without_parent']:<15}")
    
    # Сравниваем структуры
    differences = compare_structures(structures)
    
    # Выводим различия
    print("\n" + "=" * 80)
    print("РАЗЛИЧИЯ В СТРУКТУРЕ")
    print("=" * 80)
    
    has_differences = False
    
    # Количество элементов
    if differences["total_elements"]:
        has_differences = True
        print("\n1. РАЗЛИЧИЯ В КОЛИЧЕСТВЕ ЭЛЕМЕНТОВ:")
        print("-" * 80)
        for filename, count in sorted(differences["total_elements"].items()):
            print(f"  {filename}: {count} элементов")
    
    # Типы элементов
    if differences["element_types"]:
        has_differences = True
        print("\n2. РАЗЛИЧИЯ В ТИПАХ ЭЛЕМЕНТОВ:")
        print("-" * 80)
        for comparison, diff in differences["element_types"].items():
            print(f"  {comparison}:")
            if diff.get("missing"):
                print(f"    Отсутствуют типы: {', '.join(diff['missing'])}")
            if diff.get("extra"):
                print(f"    Лишние типы: {', '.join(diff['extra'])}")
    
    # Уровни заголовков
    if differences["element_levels"]:
        has_differences = True
        print("\n3. РАЗЛИЧИЯ В УРОВНЯХ ЗАГОЛОВКОВ:")
        print("-" * 80)
        for comparison, diff in differences["element_levels"].items():
            print(f"  {comparison}:")
            if diff.get("missing"):
                print(f"    Отсутствуют уровни: {', '.join(diff['missing'])}")
            if diff.get("extra"):
                print(f"    Лишние уровни: {', '.join(diff['extra'])}")
    
    # Статистика по родителям
    if differences["parent_stats"]:
        has_differences = True
        print("\n4. РАЗЛИЧИЯ В СТАТИСТИКЕ ПО РОДИТЕЛЯМ:")
        print("-" * 80)
        print(f"{'Файл':<50} {'С родителем':<15} {'Без родителя':<15} {'Уникальных родителей':<20}")
        print("-" * 80)
        for filename, stats in sorted(differences["parent_stats"].items()):
            print(f"{filename:<50} {stats['with_parent']:<15} {stats['without_parent']:<15} {stats['unique_parents']:<20}")
    
    # Детальная статистика по типам элементов
    print("\n" + "=" * 80)
    print("ДЕТАЛЬНАЯ СТАТИСТИКА ПО ТИПАМ ЭЛЕМЕНТОВ")
    print("=" * 80)
    
    # Собираем все типы
    all_types = set()
    for structure in structures.values():
        all_types.update(structure["element_types"].keys())
    
    print(f"\n{'Тип элемента':<30} ", end="")
    for filename in sorted(structures.keys()):
        print(f"{filename[:20]:<22}", end="")
    print()
    print("-" * 80)
    
    for elem_type in sorted(all_types):
        print(f"{elem_type:<30} ", end="")
        for filename in sorted(structures.keys()):
            count = structures[filename]["element_types"].get(elem_type, 0)
            print(f"{count:<22}", end="")
        print()
    
    # Детальная статистика по уровням заголовков
    print("\n" + "=" * 80)
    print("ДЕТАЛЬНАЯ СТАТИСТИКА ПО УРОВНЯМ ЗАГОЛОВКОВ")
    print("=" * 80)
    
    all_levels = set()
    for structure in structures.values():
        all_levels.update(structure["element_levels"].keys())
    
    if all_levels:
        print(f"\n{'Уровень заголовка':<30} ", end="")
        for filename in sorted(structures.keys()):
            print(f"{filename[:20]:<22}", end="")
        print()
        print("-" * 80)
        
        for level in sorted(all_levels):
            print(f"{level:<30} ", end="")
            for filename in sorted(structures.keys()):
                count = structures[filename]["element_levels"].get(level, 0)
                print(f"{count:<22}", end="")
            print()
    
    if not has_differences:
        print("\n[OK] Все файлы имеют одинаковую структуру!")
    else:
        print("\n[WARNING] Обнаружены различия в структуре файлов")


if __name__ == "__main__":
    main()

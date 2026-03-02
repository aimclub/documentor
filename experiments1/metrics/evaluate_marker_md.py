"""
Скрипт для оценки качества MD файлов от marker по ground truth аннотациям.

Парсит MD файлы в структуру элементов и вычисляет метрики:
- CER (Character Error Rate)
- WER (Word Error Rate)
- TEDS (Tree-Edit-Distance-based Similarity)
- Ordering accuracy
- Hierarchy accuracy
- Class detection accuracy
"""

import json
import re
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

import sys
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

# Копируем необходимые классы, чтобы избежать импорта documentor
class ElementType(str, Enum):
    TITLE = "title"
    HEADER_1 = "header_1"
    HEADER_2 = "header_2"
    HEADER_3 = "header_3"
    HEADER_4 = "header_4"
    HEADER_5 = "header_5"
    HEADER_6 = "header_6"
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
    FORMULA = "formula"
    LIST_ITEM = "list_item"
    CAPTION = "caption"
    FOOTNOTE = "footnote"
    PAGE_HEADER = "page_header"
    PAGE_FOOTER = "page_footer"
    LINK = "link"
    CODE_BLOCK = "code_block"

@dataclass
class Element:
    id: str
    type: ElementType
    content: str
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

# Упрощенные функции для работы с аннотациями
def load_annotation(annotation_path: Path) -> Dict[str, Any]:
    """Загружает разметку из JSON файла."""
    with open(annotation_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def normalize_content(content: str) -> str:
    """Нормализует текст для сравнения."""
    if not content:
        return ""
    return " ".join(content.split())

def match_elements_simple(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    threshold: float = 0.5
) -> Dict[str, str]:
    """Упрощенное сопоставление элементов по тексту."""
    matches = {}
    used_gt = set()
    
    for pred_elem in predicted:
        best_match = None
        best_score = 0.0
        
        for gt_elem in ground_truth:
            gt_id = gt_elem['id']
            if gt_id in used_gt:
                continue
            
            # Проверяем тип
            type_match = (pred_elem.type.value.lower() == gt_elem['type'].lower())
            if not type_match:
                continue
            
            # Вычисляем схожесть контента
            pred_content = normalize_content(pred_elem.content)
            gt_content = normalize_content(gt_elem['content'])
            
            if not pred_content and not gt_content:
                score = 1.0
            elif not pred_content or not gt_content:
                score = 0.0
            else:
                # Простая метрика схожести
                common_words = set(pred_content.lower().split()) & set(gt_content.lower().split())
                total_words = set(pred_content.lower().split()) | set(gt_content.lower().split())
                score = len(common_words) / len(total_words) if total_words else 0.0
            
            if score > best_score and score >= threshold:
                best_score = score
                best_match = gt_id
        
        if best_match:
            matches[pred_elem.id] = best_match
            used_gt.add(best_match)
    
    return matches

def calculate_ordering_accuracy_simple(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> float:
    """Упрощенная точность порядка элементов."""
    if not matches:
        return 0.0
    
    # Создаем списки порядков
    pred_order = []
    gt_order = []
    
    for pred_elem in predicted:
        if pred_elem.id in matches:
            pred_order.append(pred_elem.id)
    
    for gt_elem in ground_truth:
        if gt_elem['id'] in matches.values():
            gt_order.append(gt_elem['id'])
    
    if len(pred_order) != len(gt_order):
        return 0.0
    
    # Считаем количество правильных порядков
    correct = sum(1 for p, g in zip(pred_order, gt_order) if matches.get(p) == g)
    return correct / len(pred_order) if pred_order else 0.0

def calculate_hierarchy_accuracy_simple(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> float:
    """Упрощенная точность иерархии элементов."""
    if not matches:
        return 0.0
    
    correct = 0
    total = 0
    
    for pred_elem in predicted:
        if pred_elem.id not in matches:
            continue
        
        gt_id = matches[pred_elem.id]
        gt_elem = next((e for e in ground_truth if e['id'] == gt_id), None)
        
        if not gt_elem:
            continue
        
        total += 1
        
        # Проверяем совпадение parent_id
        pred_parent = pred_elem.parent_id
        gt_parent = gt_elem.get('parent_id')
        
        # Если оба None или оба не None и совпадают
        if pred_parent == gt_parent:
            correct += 1
        elif pred_parent and gt_parent:
            # Проверяем, сопоставлены ли родители
            pred_parent_matched = None
            for p_id, g_id in matches.items():
                if p_id == pred_parent:
                    pred_parent_matched = g_id
                    break
            
            if pred_parent_matched == gt_parent:
                correct += 1
    
    return correct / total if total > 0 else 0.0


def parse_markdown_to_elements(md_content: str, document_id: str) -> List[Element]:
    """
    Парсит Markdown файл в список элементов.
    
    Args:
        md_content: Содержимое MD файла
        document_id: ID документа
    
    Returns:
        Список элементов
    """
    elements = []
    element_counter = 0
    
    lines = md_content.split('\n')
    current_parent_id = None
    parent_stack = []  # Стек для отслеживания иерархии заголовков
    
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        
        # Пропускаем пустые строки
        if not line.strip():
            i += 1
            continue
        
        # Определяем тип элемента
        elem_type = ElementType.TEXT
        content = line
        level = None
        
        # Проверяем заголовки (# Header)
        header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if header_match:
            level = len(header_match.group(1))
            content = header_match.group(2).strip()
            
            # Определяем тип заголовка
            if level == 1:
                elem_type = ElementType.HEADER_1
            elif level == 2:
                elem_type = ElementType.HEADER_2
            elif level == 3:
                elem_type = ElementType.HEADER_3
            elif level == 4:
                elem_type = ElementType.HEADER_4
            elif level == 5:
                elem_type = ElementType.HEADER_5
            elif level == 6:
                elem_type = ElementType.HEADER_6
            
            # Обновляем стек родительских элементов
            # Удаляем все заголовки с уровнем >= текущего
            while parent_stack and parent_stack[-1][1] >= level:
                parent_stack.pop()
            
            # Устанавливаем родителя
            if parent_stack:
                current_parent_id = parent_stack[-1][0]
            else:
                current_parent_id = None
            
            # Добавляем текущий заголовок в стек
            elem_id = f"md_elem_{element_counter:04d}"
            parent_stack.append((elem_id, level))
        
        # Проверяем таблицы (начинаются с |)
        elif line.strip().startswith('|') and '|' in line:
            # Собираем всю таблицу
            table_lines = [line]
            i += 1
            # Пропускаем разделитель таблицы (|---|---|)
            if i < len(lines) and '|' in lines[i] and re.match(r'^\|[\s\-:]+\|', lines[i]):
                i += 1
            # Собираем строки таблицы
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].rstrip())
                i += 1
            i -= 1  # Откатываем на одну строку, так как цикл for увеличит i
            
            content = '\n'.join(table_lines)
            elem_type = ElementType.TABLE
        
        # Проверяем формулы ($$ ... $$ или $ ... $)
        elif re.match(r'^\$\$', line) or (line.strip().startswith('$') and line.strip().endswith('$')):
            # Собираем всю формулу
            formula_lines = [line]
            if line.strip().startswith('$$'):
                # Блочная формула
                i += 1
                while i < len(lines) and not lines[i].strip().endswith('$$'):
                    formula_lines.append(lines[i].rstrip())
                    i += 1
                if i < len(lines):
                    formula_lines.append(lines[i].rstrip())
            else:
                # Инлайн формула
                pass
            
            content = '\n'.join(formula_lines)
            elem_type = ElementType.FORMULA
        
        # Проверяем изображения (![alt](url))
        elif re.match(r'^!\[.*?\]\(.*?\)', line):
            elem_type = ElementType.IMAGE
            # Извлекаем URL изображения
            img_match = re.search(r'\(([^)]+)\)', line)
            if img_match:
                content = img_match.group(1)
            else:
                content = line
        
        # Проверяем списки (- или *)
        elif re.match(r'^[\-\*\+]\s+', line):
            elem_type = ElementType.LIST_ITEM
            content = re.sub(r'^[\-\*\+]\s+', '', line)
        
        # Обычный текст
        else:
            # Собираем несколько строк текста вместе
            text_lines = [line]
            i += 1
            while i < len(lines):
                next_line = lines[i].rstrip()
                # Останавливаемся на заголовке, таблице, формуле, изображении, списке
                if (not next_line.strip() or
                    re.match(r'^(#{1,6})\s+', next_line) or
                    next_line.strip().startswith('|') or
                    re.match(r'^\$\$', next_line) or
                    re.match(r'^!\[.*?\]\(.*?\)', next_line) or
                    re.match(r'^[\-\*\+]\s+', next_line)):
                    i -= 1
                    break
                text_lines.append(next_line)
                i += 1
            
            content = '\n'.join(text_lines)
            elem_type = ElementType.TEXT
        
        # Создаем элемент только если есть контент
        if content.strip():
            elem_id = f"md_elem_{element_counter:04d}"
            element_counter += 1
            
            # Если это заголовок, обновляем current_parent_id
            if header_match:
                current_parent_id = elem_id if not parent_stack else parent_stack[-2][0] if len(parent_stack) > 1 else None
            
            element = Element(
                id=elem_id,
                type=elem_type,
                content=content,
                parent_id=current_parent_id,
                metadata={
                    'source': 'marker_md',
                    'document_id': document_id,
                }
            )
            
            elements.append(element)
        
        i += 1
    
    return elements


def load_markdown_file(md_path: Path) -> str:
    """Загружает содержимое MD файла."""
    with open(md_path, 'r', encoding='utf-8') as f:
        return f.read()


def calculate_cer(reference: str, hypothesis: str) -> float:
    """Вычисляет Character Error Rate (CER)."""
    if not reference:
        return 1.0 if hypothesis else 0.0
    
    ref_norm = normalize_content(reference).lower()
    hyp_norm = normalize_content(hypothesis).lower()
    
    if not ref_norm:
        return 1.0 if hyp_norm else 0.0
    
    ref_chars = list(ref_norm)
    hyp_chars = list(hyp_norm)
    
    m, n = len(ref_chars), len(hyp_chars)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_chars[i-1] == hyp_chars[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
    
    edit_distance = dp[m][n]
    return min(1.0, edit_distance / len(ref_chars)) if ref_chars else 0.0


def calculate_wer(reference: str, hypothesis: str) -> float:
    """Вычисляет Word Error Rate (WER)."""
    if not reference:
        return 1.0 if hypothesis else 0.0
    
    ref_norm = normalize_content(reference).lower()
    hyp_norm = normalize_content(hypothesis).lower()
    
    ref_words = ref_norm.split()
    hyp_words = hyp_norm.split()
    
    if not ref_words:
        return 1.0 if hyp_words else 0.0
    
    m, n = len(ref_words), len(hyp_words)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_words[i-1] == hyp_words[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
    
    edit_distance = dp[m][n]
    return min(1.0, edit_distance / len(ref_words)) if ref_words else 0.0


@dataclass
class DocumentMetrics:
    """Метрики для одного документа."""
    document_id: str
    cer: float
    wer: float
    ordering_accuracy: float
    hierarchy_accuracy: float
    document_teds: float
    hierarchy_teds: float
    total_elements_gt: int
    total_elements_pred: int
    matched_elements: int
    processing_time: float


def process_markdown_file(
    md_path: Path,
    annotation_path: Path
) -> DocumentMetrics:
    """
    Обрабатывает один MD файл и вычисляет метрики.
    
    Args:
        md_path: Путь к MD файлу
        annotation_path: Путь к ground truth аннотации
    
    Returns:
        DocumentMetrics с результатами
    """
    start_time = time.time()
    
    # Загружаем MD файл
    md_content = load_markdown_file(md_path)
    
    # Парсим MD в элементы
    document_id = md_path.stem
    predicted = parse_markdown_to_elements(md_content, document_id)
    
    # Загружаем ground truth аннотацию
    gt_data = load_annotation(annotation_path)
    gt_elements = gt_data.get('elements', [])
    
    # Сопоставляем элементы
    matches = match_elements_simple(predicted, gt_elements)
    
    # Вычисляем CER и WER
    total_cer = 0.0
    total_wer = 0.0
    matched_pairs = 0
    
    for pred_id, gt_id in matches.items():
        pred_elem = next((e for e in predicted if e.id == pred_id), None)
        gt_elem = next((e for e in gt_elements if e['id'] == gt_id), None)
        
        if pred_elem and gt_elem:
            cer = calculate_cer(gt_elem['content'], pred_elem.content)
            wer = calculate_wer(gt_elem['content'], pred_elem.content)
            total_cer += cer
            total_wer += wer
            matched_pairs += 1
    
    avg_cer = total_cer / matched_pairs if matched_pairs > 0 else 1.0
    avg_wer = total_wer / matched_pairs if matched_pairs > 0 else 1.0
    
    # Вычисляем ordering accuracy
    ordering_accuracy = calculate_ordering_accuracy_simple(predicted, gt_elements, matches)
    
    # Вычисляем hierarchy accuracy
    hierarchy_accuracy = calculate_hierarchy_accuracy_simple(predicted, gt_elements, matches)
    
    # Вычисляем TEDS (упрощенная версия)
    # Для полного TEDS нужна библиотека, но можно использовать hierarchy_accuracy как приближение
    hierarchy_teds = 1.0 - hierarchy_accuracy
    document_teds = (hierarchy_teds + (1.0 - ordering_accuracy)) / 2.0
    
    processing_time = time.time() - start_time
    
    return DocumentMetrics(
        document_id=document_id,
        cer=avg_cer,
        wer=avg_wer,
        ordering_accuracy=ordering_accuracy,
        hierarchy_accuracy=hierarchy_accuracy,
        document_teds=document_teds,
        hierarchy_teds=hierarchy_teds,
        total_elements_gt=len(gt_elements),
        total_elements_pred=len(predicted),
        matched_elements=len(matches),
        processing_time=processing_time
    )


def find_matching_annotation(md_path: Path, annotations_dir: Path) -> Optional[Path]:
    """
    Находит соответствующую аннотацию для MD файла.
    
    Args:
        md_path: Путь к MD файлу
        annotations_dir: Директория с аннотациями
    
    Returns:
        Путь к аннотации или None
    """
    md_stem = md_path.stem
    
    # Убираем суффикс _scanned если есть
    base_name = md_stem.replace('_scanned', '')
    
    # Ищем соответствующие аннотации
    # Приоритет: pdf_annotation.json > scanned_annotation.json
    pdf_annotation = annotations_dir / f"{base_name}.pdf_annotation.json"
    scanned_annotation = annotations_dir / f"{base_name}_scanned_annotation.json"
    
    if pdf_annotation.exists():
        return pdf_annotation
    elif scanned_annotation.exists():
        return scanned_annotation
    else:
        # Пробуем найти по части имени
        for ann_file in annotations_dir.glob("*_annotation.json"):
            ann_stem = ann_file.stem.replace('_annotation', '')
            if base_name.startswith(ann_stem) or ann_stem.startswith(base_name):
                return ann_file
    
    return None


def main():
    """Основная функция для обработки всех MD файлов."""
    script_dir = Path(__file__).parent
    md_dir = script_dir / "marker_md_output"
    annotations_dir = script_dir / "annotations"
    output_file = script_dir / "marker_md_metrics.json"
    
    if not md_dir.exists():
        print(f"[ERROR] Папка {md_dir} не найдена")
        sys.exit(1)
    
    if not annotations_dir.exists():
        print(f"[ERROR] Папка {annotations_dir} не найдена")
        sys.exit(1)
    
    # Находим все MD файлы
    md_files = sorted(md_dir.glob("*.md"))
    
    if not md_files:
        print(f"[ERROR] MD файлы не найдены в {md_dir}")
        sys.exit(1)
    
    print(f"Найдено {len(md_files)} MD файлов для обработки")
    print("-" * 80)
    
    results = {}
    all_metrics = []
    
    # Обрабатываем каждый файл
    for i, md_file in enumerate(md_files, 1):
        print(f"\n[{i}/{len(md_files)}] Обработка: {md_file.name}")
        
        # Находим соответствующую аннотацию
        annotation_path = find_matching_annotation(md_file, annotations_dir)
        
        if not annotation_path:
            print(f"  [ERROR] Аннотация не найдена для {md_file.name}")
            continue
        
        print(f"  Используется аннотация: {annotation_path.name}")
        
        try:
            metrics = process_markdown_file(md_file, annotation_path)
            all_metrics.append(metrics)
            
            results[md_file.name] = {
                'document_id': metrics.document_id,
                'cer': metrics.cer,
                'wer': metrics.wer,
                'ordering_accuracy': metrics.ordering_accuracy,
                'hierarchy_accuracy': metrics.hierarchy_accuracy,
                'document_teds': metrics.document_teds,
                'hierarchy_teds': metrics.hierarchy_teds,
                'total_elements_gt': metrics.total_elements_gt,
                'total_elements_pred': metrics.total_elements_pred,
                'matched_elements': metrics.matched_elements,
                'processing_time': metrics.processing_time
            }
            
            print(f"  [OK] CER: {metrics.cer:.4f}")
            print(f"  [OK] WER: {metrics.wer:.4f}")
            print(f"  [OK] Ordering accuracy: {metrics.ordering_accuracy:.4f}")
            print(f"  [OK] Hierarchy accuracy: {metrics.hierarchy_accuracy:.4f}")
            print(f"  [OK] Document TEDS: {metrics.document_teds:.4f}")
            print(f"  [OK] Время: {metrics.processing_time:.2f} сек")
            
        except Exception as e:
            print(f"  [ERROR] Ошибка: {e}")
            import traceback
            traceback.print_exc()
    
    # Вычисляем средние метрики
    if all_metrics:
        avg_cer = sum(m.cer for m in all_metrics) / len(all_metrics)
        avg_wer = sum(m.wer for m in all_metrics) / len(all_metrics)
        avg_ordering = sum(m.ordering_accuracy for m in all_metrics) / len(all_metrics)
        avg_hierarchy = sum(m.hierarchy_accuracy for m in all_metrics) / len(all_metrics)
        avg_document_teds = sum(m.document_teds for m in all_metrics) / len(all_metrics)
        avg_hierarchy_teds = sum(m.hierarchy_teds for m in all_metrics) / len(all_metrics)
        
        results['_summary'] = {
            'total_files': len(all_metrics),
            'avg_cer': avg_cer,
            'avg_wer': avg_wer,
            'avg_ordering_accuracy': avg_ordering,
            'avg_hierarchy_accuracy': avg_hierarchy,
            'avg_document_teds': avg_document_teds,
            'avg_hierarchy_teds': avg_hierarchy_teds,
        }
        
        print("\n" + "=" * 80)
        print("ИТОГОВАЯ СТАТИСТИКА")
        print("=" * 80)
        print(f"\nОбработано файлов: {len(all_metrics)}")
        print(f"Средний CER: {avg_cer:.4f}")
        print(f"Средний WER: {avg_wer:.4f}")
        print(f"Средняя Ordering accuracy: {avg_ordering:.4f}")
        print(f"Средняя Hierarchy accuracy: {avg_hierarchy:.4f}")
        print(f"Средний Document TEDS: {avg_document_teds:.4f}")
        print(f"Средний Hierarchy TEDS: {avg_hierarchy_teds:.4f}")
    
    # Сохраняем результаты
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\nРезультаты сохранены в: {output_file}")


if __name__ == "__main__":
    main()

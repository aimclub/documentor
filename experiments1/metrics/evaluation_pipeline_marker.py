"""
Пайплайн для оценки качества парсинга документов с использованием Marker.

Обрабатывает все размеченные PDF файлы и вычисляет метрики:
- CER (Character Error Rate)
- WER (Word Error Rate)
- Время на страницу
- Время на документ
- TEDS для документа
- TEDS для иерархии
- Точность детекции классов
"""

import json
import time
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from documentor.domain.models import Element, ElementType
from dataclasses import dataclass, field
from collections import defaultdict
import statistics

# Добавляем путь к marker
marker_path = Path(__file__).parent.parent / "pdf_text_extraction" / "marker_local"
sys.path.insert(0, str(marker_path))

# Сначала добавляем путь к модулям оценки
sys.path.insert(0, str(Path(__file__).parent))

# Импортируем только то, что нужно для работы скрипта
# Откладываем импорт evaluation_metrics и evaluation_pipeline до проверки marker
# чтобы избежать проблем с импортом documentor

# Импорты marker с обработкой ошибок (используем тот же подход, что и в convert_pdf_to_md_marker.py)
try:
    # Пытаемся импортировать marker из venv_marker, если он существует
    base_dir = Path(__file__).parent.parent / "pdf_text_extraction"
    venv_marker_path = base_dir / "venv_marker"
    if venv_marker_path.exists():
        venv_site_packages = venv_marker_path / "Lib" / "site-packages"
        if venv_site_packages.exists():
            sys.path.insert(0, str(venv_site_packages))
    
    # Также добавляем путь к marker_local, если он существует
    marker_local_path = base_dir / "marker_local"
    if marker_local_path.exists():
        sys.path.insert(0, str(marker_local_path))
    
    from marker.models import create_model_dict
    from marker.converters.pdf import PdfConverter
    from marker.renderers.json import JSONRenderer
    from marker.schema import BlockTypes
    MARKER_AVAILABLE = True
except ImportError as e:
    MARKER_AVAILABLE = False
    MARKER_ERROR = str(e)
    print(f"ВНИМАНИЕ: Не удалось импортировать marker: {e}")
    print("\nДля работы скрипта необходимо:")
    print("1. Установить marker-pdf в venv_marker:")
    print("   cd experiments/pdf_text_extraction")
    print("   venv_marker\\Scripts\\activate")
    print("   pip install marker-pdf")
    print("\n2. Или использовать окружение marker_local:")
    print("   cd experiments/pdf_text_extraction/marker_local")
    print("   poetry install  # или pip install -r requirements.txt")
    print("   poetry shell  # или активировать виртуальное окружение")
    print("   python ../../metrics/evaluation_pipeline_marker.py")


def marker_block_type_to_element_type(block_type: str, section_hierarchy: Optional[Dict] = None):
    """Преобразует тип блока marker в ElementType."""
    # Импортируем ElementType здесь, чтобы избежать проблем с импортом documentor
    # если marker недоступен
    # Добавляем путь к корню проекта для импорта documentor
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    from documentor.domain.models import ElementType
    
    block_type_lower = block_type.lower()
    
    # Если это SectionHeader, пытаемся определить уровень из section_hierarchy
    if block_type_lower == 'sectionheader' or 'section' in block_type_lower:
        if section_hierarchy:
            # section_hierarchy может содержать информацию об уровне
            # Например: {1: "Introduction", 2: "Methods"}
            # Ключ - это уровень заголовка
            if isinstance(section_hierarchy, dict) and section_hierarchy:
                # Берем максимальный уровень из ключей
                max_level = max([int(k) for k in section_hierarchy.keys() if str(k).isdigit()], default=1)
                # Ограничиваем уровень от 1 до 6
                level = min(max(1, max_level), 6)
                # Возвращаем соответствующий тип заголовка
                header_types = {
                    1: ElementType.HEADER_1,
                    2: ElementType.HEADER_2,
                    3: ElementType.HEADER_3,
                    4: ElementType.HEADER_4,
                    5: ElementType.HEADER_5,
                    6: ElementType.HEADER_6
                }
                return header_types.get(level, ElementType.HEADER_1)
        return ElementType.HEADER_1
    
    # Маппинг типов marker -> documentor
    type_mapping = {
        'text': ElementType.TEXT,
        'table': ElementType.TABLE,
        'picture': ElementType.IMAGE,
        'figure': ElementType.IMAGE,
        'equation': ElementType.FORMULA,
        'listitem': ElementType.LIST_ITEM,
        'caption': ElementType.CAPTION,
        'code': ElementType.CODE_BLOCK,  # Исправлено: CODE -> CODE_BLOCK
        'footnote': ElementType.FOOTNOTE,
        'reference': ElementType.LINK,  # Исправлено: REFERENCE -> LINK
        'pageheader': ElementType.PAGE_HEADER,  # Исправлено: HEADER_1 -> PAGE_HEADER
        'pagefooter': ElementType.PAGE_FOOTER,  # Исправлено: TEXT -> PAGE_FOOTER
    }
    
    # Проверяем точное совпадение
    if block_type_lower in type_mapping:
        return type_mapping[block_type_lower]
    
    # По умолчанию TEXT
    return ElementType.TEXT


def extract_text_from_html(html: str) -> str:
    """Извлекает текст из HTML."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        return soup.get_text(separator=' ', strip=True)
    except:
        # Если BeautifulSoup недоступен, используем простую замену
        import re
        # Удаляем HTML теги
        text = re.sub(r'<[^>]+>', '', html)
        # Заменяем HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        return text.strip()


def marker_json_to_elements(
    json_output: Any,
    page_offset: int = 0
) -> List['Element']:
    """
    Преобразует JSONOutput marker в список Element.
    
    Args:
        json_output: JSONOutput из marker
        page_offset: Смещение для номеров страниц (0-based)
    
    Returns:
        Список Element
    """
    # Импортируем Element и ElementType здесь, чтобы избежать проблем с импортом documentor
    # если marker недоступен
    # Добавляем путь к корню проекта для импорта documentor
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    from documentor.domain.models import Element, ElementType
    
    elements = []
    element_counter = 0
    
    def process_block(block: Any, parent_id: Optional[str] = None, page_num: int = 0) -> None:
        """Рекурсивно обрабатывает блоки marker."""
        nonlocal element_counter
        
        # Преобразуем Pydantic модель в словарь если нужно
        if hasattr(block, 'model_dump'):
            block = block.model_dump()
        elif hasattr(block, 'dict'):
            block = block.dict()
        elif not isinstance(block, dict):
            # Пытаемся получить атрибуты напрямую
            block = {
                'block_type': str(getattr(block, 'block_type', '')),
                'id': str(getattr(block, 'id', '')),
                'html': getattr(block, 'html', ''),
                'bbox': getattr(block, 'bbox', []),
                'children': getattr(block, 'children', []),
                'section_hierarchy': getattr(block, 'section_hierarchy', {})
            }
        
        block_type = block.get('block_type', '')
        block_id = block.get('id', '')
        html = block.get('html', '')
        bbox = block.get('bbox', [])
        children = block.get('children', [])
        section_hierarchy = block.get('section_hierarchy', {})
        
        # Извлекаем текст из HTML
        content = extract_text_from_html(html)
        
        # Определяем тип элемента (передаем section_hierarchy для определения уровня заголовка)
        elem_type = marker_block_type_to_element_type(block_type, section_hierarchy)
        
        # Определяем номер страницы из block_id или используем переданный
        # В marker block_id может содержать информацию о странице (например, "page_0_block_1")
        current_page = page_num
        if 'page' in block_id.lower():
            try:
                # Пытаемся извлечь номер страницы из ID
                # Формат может быть: "page_0_block_1" или "Page_0_Block_1"
                import re
                page_match = re.search(r'page[_\s]*(\d+)', block_id.lower())
                if page_match:
                    current_page = int(page_match.group(1)) + page_offset
            except:
                pass
        
        # Создаем элемент только если есть контент или это важный тип (таблица, изображение)
        if content or elem_type in (ElementType.TABLE, ElementType.IMAGE, ElementType.FORMULA):
            elem_id = f"marker_elem_{element_counter:04d}"
            element_counter += 1
            
            # Подготавливаем метаданные
            metadata = {
                'page_num': current_page,
                'page_number': current_page + 1,  # 1-based
            }
            
            # Добавляем bbox если есть
            if bbox and len(bbox) >= 4:
                metadata['bbox'] = bbox
            
            # Добавляем информацию о section hierarchy если есть
            if section_hierarchy:
                metadata['section_hierarchy'] = section_hierarchy
            
            # Определяем parent_id
            elem_parent_id = parent_id
            
            # Создаем элемент
            element = Element(
                id=elem_id,
                type=elem_type,
                content=content,
                parent_id=elem_parent_id,
                metadata=metadata
            )
            
            elements.append(element)
            
            # Обрабатываем дочерние элементы
            if children:
                for child in children:
                    process_block(child, parent_id=elem_id, page_num=current_page)
        else:
            # Если нет контента, но есть дети, обрабатываем только детей
            if children:
                for child in children:
                    process_block(child, parent_id=parent_id, page_num=current_page)
    
    # Обрабатываем все страницы
    # JSONOutput может быть Pydantic моделью или словарем
    if hasattr(json_output, 'children'):
        pages = json_output.children
    elif isinstance(json_output, dict) and 'children' in json_output:
        pages = json_output['children']
    else:
        pages = []
    
    for page_idx, page_block in enumerate(pages):
        # Преобразуем Pydantic модель в словарь если нужно
        if hasattr(page_block, 'model_dump'):
            page_block = page_block.model_dump()
        elif hasattr(page_block, 'dict'):
            page_block = page_block.dict()
        elif not isinstance(page_block, dict):
            # Пытаемся получить атрибуты напрямую
            page_block = {
                'block_type': getattr(page_block, 'block_type', ''),
                'id': getattr(page_block, 'id', ''),
                'html': getattr(page_block, 'html', ''),
                'bbox': getattr(page_block, 'bbox', []),
                'children': getattr(page_block, 'children', []),
                'section_hierarchy': getattr(page_block, 'section_hierarchy', {})
            }
        process_block(page_block, parent_id=None, page_num=page_idx)
    
    return elements


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
    return min(1.0, edit_distance / len(ref_chars))


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
    return min(1.0, edit_distance / len(ref_words))


def calculate_hierarchy_teds(
    predicted: List['Element'],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> float:
    """Вычисляет TEDS для иерархии элементов."""
    if not matches:
        return 0.0
    
    pred_dict = {elem.id: elem for elem in predicted}
    gt_dict = {elem['id']: elem for elem in ground_truth}
    gt_to_pred = {gt_id: pred_id for pred_id, gt_id in matches.items()}
    
    correct_parents = 0
    total_checked = 0
    
    for pred_id, gt_id in matches.items():
        pred_elem = pred_dict.get(pred_id)
        gt_elem = gt_dict.get(gt_id)
        
        if not pred_elem or not gt_elem:
            continue
        
        if gt_elem.get('type', '').lower() == 'header_1':
            continue
        
        pred_parent = pred_elem.parent_id
        gt_parent = gt_elem.get('parent_id')
        
        total_checked += 1
        
        if pred_parent and gt_parent:
            pred_parent_gt = gt_to_pred.get(pred_parent)
            if pred_parent_gt is None:
                for p_id, g_id in matches.items():
                    if p_id == pred_parent:
                        pred_parent_gt = g_id
                        break
            
            if pred_parent_gt == gt_parent:
                correct_parents += 1
        elif not pred_parent and not gt_parent:
            correct_parents += 1
    
    if total_checked == 0:
        return 1.0
    
    return correct_parents / total_checked


# Копируем функции из evaluation_pipeline, чтобы избежать импорта fitz
# (который конфликтует с неправильным пакетом fitz в venv_marker)

@dataclass
class DocumentErrors:
    """Детальная информация об ошибках для анализа."""
    missing_elements: List[Dict[str, Any]] = field(default_factory=list)
    extra_elements: List[Dict[str, Any]] = field(default_factory=list)
    ordering_errors: List[Dict[str, Any]] = field(default_factory=list)
    hierarchy_errors: List[Dict[str, Any]] = field(default_factory=list)
    high_error_elements: List[Dict[str, Any]] = field(default_factory=list)
    type_mismatch_elements: List[Dict[str, Any]] = field(default_factory=list)


def calculate_class_detection_accuracy(
    predicted: List['Element'],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> Dict[str, Dict[str, float]]:
    """Вычисляет точность детекции классов."""
    gt_by_class = defaultdict(list)
    pred_by_class = defaultdict(list)
    matched_by_class = defaultdict(int)
    matched_gt_by_class = defaultdict(set)
    
    for gt_elem in ground_truth:
        elem_type = gt_elem.get('type', '').lower()
        gt_by_class[elem_type].append(gt_elem['id'])
    
    for pred_elem in predicted:
        elem_type = pred_elem.type.value.lower()
        pred_by_class[elem_type].append(pred_elem.id)
    
    for pred_id, gt_id in matches.items():
        pred_elem = next((e for e in predicted if e.id == pred_id), None)
        gt_elem = next((e for e in ground_truth if e['id'] == gt_id), None)
        
        if pred_elem and gt_elem:
            pred_type = pred_elem.type.value.lower()
            gt_type = gt_elem.get('type', '').lower()
            
            if pred_type == gt_type:
                matched_gt_by_class[pred_type].add(gt_id)
                matched_by_class[pred_type] += 1
    
    results = {}
    all_classes = set(list(gt_by_class.keys()) + list(pred_by_class.keys()))
    
    for class_name in all_classes:
        count_gt = len(gt_by_class[class_name])
        count_pred = len(pred_by_class[class_name])
        count_matched_pred = matched_by_class[class_name]
        count_matched_gt = len(matched_gt_by_class[class_name])
        
        precision = count_matched_pred / count_pred if count_pred > 0 else 0.0
        recall = count_matched_gt / count_gt if count_gt > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        
        results[class_name] = {
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'count_gt': count_gt,
            'count_pred': count_pred,
            'count_matched': count_matched_gt
        }
    
    return results


def calculate_type_substitutions(
    predicted: List['Element'],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> Dict[str, Any]:
    """Вычисляет метрики по заменам типов элементов."""
    substitutions_by_type = defaultdict(lambda: defaultdict(int))
    total_substitutions = 0
    total_matched = len(matches)
    
    pred_dict = {elem.id: elem for elem in predicted}
    gt_dict = {elem['id']: elem for elem in ground_truth}
    pred_by_gt = defaultdict(list)
    
    for pred_id, gt_id in matches.items():
        pred_by_gt[gt_id].append(pred_id)
    
    for gt_id, pred_ids in pred_by_gt.items():
        gt_elem = gt_dict.get(gt_id)
        if not gt_elem:
            continue
        
        gt_type = gt_elem.get('type', '').lower()
        
        if pred_ids:
            first_pred_id = pred_ids[0]
            pred_elem = pred_dict.get(first_pred_id)
            if pred_elem:
                pred_type = pred_elem.type.value.lower()
                
                if pred_type != gt_type:
                    total_substitutions += 1
                    substitutions_by_type[gt_type][pred_type] += 1
    
    substitution_rate = total_substitutions / total_matched if total_matched > 0 else 0.0
    
    return {
        'total_substitutions': total_substitutions,
        'substitution_rate': substitution_rate,
        'substitutions_by_type': dict(substitutions_by_type),
        'substitution_matrix': dict(substitutions_by_type)
    }


def calculate_header_level_substitutions(
    predicted: List['Element'],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> Dict[str, Any]:
    """Вычисляет метрики по заменам уровней заголовков."""
    substitutions_by_level = defaultdict(lambda: defaultdict(int))
    header_count_gt = defaultdict(int)
    header_count_pred = defaultdict(int)
    header_count_matched = defaultdict(int)
    total_header_substitutions = 0
    total_headers_matched = 0
    
    pred_dict = {elem.id: elem for elem in predicted}
    gt_dict = {elem['id']: elem for elem in ground_truth}
    
    for gt_elem in ground_truth:
        gt_type = gt_elem.get('type', '').lower()
        if gt_type.startswith('header_'):
            header_count_gt[gt_type] += 1
    
    for pred_elem in predicted:
        pred_type = pred_elem.type.value.lower()
        if pred_type.startswith('header_'):
            header_count_pred[pred_type] += 1
    
    pred_by_gt = defaultdict(list)
    for pred_id, gt_id in matches.items():
        pred_by_gt[gt_id].append(pred_id)
    
    for gt_id, pred_ids in pred_by_gt.items():
        gt_elem = gt_dict.get(gt_id)
        if not gt_elem:
            continue
        
        gt_type = gt_elem.get('type', '').lower()
        
        if not gt_type.startswith('header_'):
            continue
        
        total_headers_matched += 1
        header_count_matched[gt_type] += 1
        
        if pred_ids:
            first_pred_id = pred_ids[0]
            pred_elem = pred_dict.get(first_pred_id)
            if pred_elem:
                pred_type = pred_elem.type.value.lower()
                
                if pred_type.startswith('header_'):
                    if pred_type != gt_type:
                        total_header_substitutions += 1
                        substitutions_by_level[gt_type][pred_type] += 1
    
    header_substitution_rate = total_header_substitutions / total_headers_matched if total_headers_matched > 0 else 0.0
    
    return {
        'total_header_substitutions': total_header_substitutions,
        'header_substitution_rate': header_substitution_rate,
        'substitutions_by_level': dict(substitutions_by_level),
        'header_count_gt': dict(header_count_gt),
        'header_count_pred': dict(header_count_pred),
        'header_count_matched': dict(header_count_matched)
    }


def collect_errors(
    predicted: List['Element'],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> DocumentErrors:
    """Собирает детальную информацию об ошибках для анализа."""
    errors = DocumentErrors()
    
    pred_dict = {elem.id: elem for elem in predicted}
    gt_dict = {elem['id']: elem for elem in ground_truth}
    gt_to_pred = {gt_id: pred_id for pred_id, gt_id in matches.items()}
    
    matched_gt_ids = set(matches.values())
    for gt_elem in ground_truth:
        gt_id = gt_elem['id']
        if gt_id not in matched_gt_ids:
            errors.missing_elements.append({
                'id': gt_id,
                'type': gt_elem.get('type', 'unknown'),
                'content_preview': (gt_elem.get('content', '') or '')[:100],
                'page_number': gt_elem.get('page_number', 0),
                'order': gt_elem.get('order', 0)
            })
    
    matched_pred_ids = set(matches.keys())
    pred_by_gt = {}
    for pred_id, gt_id in matches.items():
        if gt_id not in pred_by_gt:
            pred_by_gt[gt_id] = []
        pred_by_gt[gt_id].append(pred_id)
    
    for pred_elem in predicted:
        pred_id = pred_elem.id
        if pred_id not in matched_pred_ids:
            errors.extra_elements.append({
                'id': pred_id,
                'type': pred_elem.type.value,
                'content_preview': (pred_elem.content or '')[:100],
                'page_number': pred_elem.metadata.get('page_number', 0),
                'order': pred_elem.metadata.get('order', 0)
            })
    
    pred_with_order = [(pred_id, pred_dict[pred_id]) for pred_id in matches.keys()]
    pred_with_order.sort(key=lambda x: x[1].metadata.get('order', 0))
    
    gt_with_order = [(gt_id, gt_dict[gt_id]) for gt_id in matches.values()]
    gt_with_order.sort(key=lambda x: x[1].get('order', 0))
    
    for i, (pred_id, pred_elem) in enumerate(pred_with_order):
        if i < len(gt_with_order):
            gt_id, gt_elem = gt_with_order[i]
            if pred_id in matches and matches[pred_id] != gt_id:
                errors.ordering_errors.append({
                    'predicted_id': pred_id,
                    'predicted_type': pred_elem.type.value,
                    'predicted_order': pred_elem.metadata.get('order', 0),
                    'expected_id': gt_id,
                    'expected_type': gt_elem.get('type', 'unknown'),
                    'expected_order': gt_elem.get('order', 0),
                    'position': i
                })
    
    for pred_id, gt_id in matches.items():
        pred_elem = pred_dict.get(pred_id)
        gt_elem = gt_dict.get(gt_id)
        
        if not pred_elem or not gt_elem:
            continue
        
        if gt_elem.get('type', '').lower() == 'header_1':
            continue
        
        pred_parent = pred_elem.parent_id
        gt_parent = gt_elem.get('parent_id')
        
        if pred_parent and gt_parent:
            pred_parent_gt = gt_to_pred.get(pred_parent)
            if pred_parent_gt is None:
                for p_id, g_id in matches.items():
                    if p_id == pred_parent:
                        pred_parent_gt = g_id
                        break
            
            if pred_parent_gt != gt_parent:
                errors.hierarchy_errors.append({
                    'element_id': pred_id,
                    'predicted_parent_id': pred_parent,
                    'expected_parent_id': gt_parent,
                    'element_type': pred_elem.type.value
                })
        elif pred_parent and not gt_parent:
            errors.hierarchy_errors.append({
                'element_id': pred_id,
                'predicted_parent_id': pred_parent,
                'expected_parent_id': None,
                'element_type': pred_elem.type.value
            })
        elif not pred_parent and gt_parent:
            errors.hierarchy_errors.append({
                'element_id': pred_id,
                'predicted_parent_id': None,
                'expected_parent_id': gt_parent,
                'element_type': pred_elem.type.value
            })
    
    return errors


@dataclass
class DocumentMetrics:
    """Метрики для одного документа."""
    document_id: str
    source_file: str
    document_format: str
    
    cer: float = 0.0
    wer: float = 0.0
    
    time_per_page: float = 0.0
    time_per_document: float = 0.0
    total_pages: int = 0
    
    document_teds: float = 0.0
    hierarchy_teds: float = 0.0
    
    class_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    total_elements_gt: int = 0
    total_elements_pred: int = 0
    matched_elements: int = 0
    
    bbox_precision: float = 0.0
    bbox_recall: float = 0.0
    bbox_f1: float = 0.0
    bbox_matched_count: int = 0
    
    type_substitutions: Dict[str, Any] = field(default_factory=dict)
    header_level_substitutions: Dict[str, Any] = field(default_factory=dict)


def process_document_with_marker(
    annotation_path: Path,
    marker_config: Optional[Dict[str, Any]] = None
) -> DocumentMetrics:
    """
    Обрабатывает один документ с использованием marker и вычисляет метрики.
    """
    if not MARKER_AVAILABLE:
        raise RuntimeError(
            f"Marker недоступен. Ошибка импорта: {MARKER_ERROR}\n"
            "Пожалуйста, настройте окружение marker согласно инструкциям выше."
        )
    
    # Импортируем функции оценки здесь, чтобы избежать проблем с импортом documentor
    # если marker недоступен
    # Добавляем путь к корню проекта для импорта documentor
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    # Импортируем evaluation_metrics (может требовать langchain_core и другие зависимости documentor)
    # ВАЖНО: В venv_marker может быть конфликт с пакетом 'fitz' (неправильный пакет)
    # Нужно удалить его и установить правильный PyMuPDF
    try:
        from evaluation_metrics import (
            load_annotation,
            match_elements,
            calculate_ordering_accuracy,
            calculate_hierarchy_accuracy,
            normalize_content,
            match_elements_by_bbox,
        )
    except (ImportError, AttributeError) as e:
        error_msg = str(e)
        if 'fitz' in error_msg or 'Page' in error_msg or 'Rect' in error_msg:
            raise ImportError(
                f"Конфликт с пакетом 'fitz' в venv_marker: {e}\n\n"
                "ИСПРАВЛЕНИЕ:\n"
                "1. Активируйте venv_marker:\n"
                "   cd experiments/pdf_text_extraction\n"
                "   venv_marker\\Scripts\\activate  # Windows\n"
                "   # или: source venv_marker/bin/activate  # Linux/Mac\n"
                "2. Удалите неправильный пакет 'fitz':\n"
                "   pip uninstall fitz -y\n"
                "3. Установите правильный PyMuPDF:\n"
                "   pip install pymupdf\n"
                "4. Установите недостающие зависимости documentor:\n"
                "   pip install langchain-core\n"
                "\n"
                "Или установите все зависимости из requirements.txt:\n"
                "   pip install -r ../../requirements.txt"
            )
        elif 'langchain_core' in error_msg or 'langchain' in error_msg:
            raise ImportError(
                f"Не удалось импортировать evaluation_metrics: {e}\n\n"
                "Установите недостающие зависимости documentor в venv_marker:\n"
                "  pip install langchain-core\n"
                "Или установите все зависимости из requirements.txt:\n"
                "  pip install -r ../../requirements.txt"
            )
        raise
    # Функции calculate_class_detection_accuracy, calculate_type_substitutions,
    # calculate_header_level_substitutions и collect_errors уже определены выше
    # (скопированы из evaluation_pipeline, чтобы избежать импорта fitz)
    from documentor.domain.models import Element, ElementType
    
    # Импортируем PyMuPDF правильно (может быть конфликт с другим пакетом fitz)
    try:
        import fitz  # PyMuPDF
    except ImportError:
        try:
            import pymupdf as fitz  # Альтернативное имя
        except ImportError:
            raise ImportError(
                "PyMuPDF не установлен. Установите: pip install pymupdf\n"
                "Внимание: в venv_marker может быть установлен конфликтующий пакет 'fitz'.\n"
                "Удалите его: pip uninstall fitz"
            )
    
    # Импортируем visualize_comparison и teds_analysis условно (они тоже импортируют fitz)
    # Также они могут требовать langchain_core и другие зависимости documentor
    visualize_comparison = None
    create_teds_visualizations_and_report = None
    
    try:
        from visualize_comparison import visualize_comparison
        from teds_analysis import create_teds_visualizations_and_report
    except ImportError as e:
        print(f"  Предупреждение: не удалось импортировать visualize_comparison или teds_analysis: {e}")
        print("  Визуализации и детальный анализ TEDS будут пропущены")
        print("  Для полной функциональности установите недостающие зависимости:")
        print("    pip install langchain-core")
    
    # Загружаем аннотацию
    annotation = load_annotation(annotation_path)
    source_file = Path(annotation['source_file'])
    document_id = annotation.get('document_id', source_file.stem)
    document_format = annotation.get('document_format', 'unknown')
    ground_truth = annotation.get('elements', [])
    
    if not source_file.exists():
        raise FileNotFoundError(f"Source file not found: {source_file}")
    
    # Проверяем, что это PDF файл
    if source_file.suffix.lower() != '.pdf':
        raise ValueError(f"Marker supports only PDF files, got: {source_file.suffix}")
    
    # Инициализируем marker (используем тот же подход, что и в convert_pdf_to_md_marker.py)
    models = create_model_dict()
    
    # Создаем converter с минимальной конфигурацией (как в convert_pdf_to_md_marker.py)
    # Используем JSONRenderer для получения структурированных данных
    # PdfConverter ожидает строку с полным путем к классу, а не объект
    converter = PdfConverter(
        artifact_dict=models,
        renderer="marker.renderers.json.JSONRenderer",
    )
    
    # Парсим документ и замеряем время
    start_time = time.time()
    try:
        rendered = converter(str(source_file))
    except Exception as e:
        raise RuntimeError(f"Marker failed to process document: {e}")
    end_time = time.time()
    
    processing_time = end_time - start_time
    
    # Получаем количество страниц из PDF
    try:
        pdf_doc = fitz.open(str(source_file))
        total_pages = len(pdf_doc)
        pdf_doc.close()
    except:
        total_pages = 1
    
    time_per_page = processing_time / total_pages if total_pages > 0 else processing_time
    
    # Преобразуем результат marker в элементы
    try:
        predicted = marker_json_to_elements(rendered)
    except Exception as e:
        raise RuntimeError(f"Failed to convert marker output to elements: {e}")
    
    # Сопоставляем элементы
    matches = match_elements(predicted, ground_truth)
    
    # Сопоставляем элементы по bbox
    predicted_with_bbox = [e for e in predicted if len(e.metadata.get('bbox', [])) >= 4]
    ground_truth_with_bbox = [e for e in ground_truth if len(e.get('bbox', [])) >= 4]
    
    is_scanned = (
        document_format == 'scanned_pdf' or
        '_scanned' in str(source_file).lower() or
        '_scanned' in str(document_id).lower()
    )
    
    if is_scanned:
        initial_iou_threshold = 0.2
        fallback_thresholds = [0.1, 0.05]
    else:
        initial_iou_threshold = 0.5
        fallback_thresholds = [0.3, 0.1]
    
    bbox_matches = match_elements_by_bbox(
        predicted_with_bbox,
        ground_truth_with_bbox,
        iou_threshold=initial_iou_threshold,
        normalize_coordinates=True,
        pdf_path=source_file,
        render_scale=2.0
    )
    
    for fallback_threshold in fallback_thresholds:
        if len(bbox_matches) == 0 and predicted_with_bbox and ground_truth_with_bbox:
            bbox_matches = match_elements_by_bbox(
                predicted_with_bbox,
                ground_truth_with_bbox,
                iou_threshold=fallback_threshold,
                normalize_coordinates=True,
                pdf_path=source_file,
                render_scale=2.0
            )
            if len(bbox_matches) > 0:
                break
    
    bbox_matched_count = len(bbox_matches)
    bbox_precision = bbox_matched_count / len(predicted_with_bbox) if predicted_with_bbox else 0.0
    bbox_recall = bbox_matched_count / len(ground_truth_with_bbox) if ground_truth_with_bbox else 0.0
    bbox_f1 = 2 * (bbox_precision * bbox_recall) / (bbox_precision + bbox_recall) if (bbox_precision + bbox_recall) > 0 else 0.0
    
    # Собираем информацию об ошибках
    errors = collect_errors(predicted, ground_truth, matches)
    
    # Вычисляем CER и WER
    cer_scores = []
    wer_scores = []
    
    pred_by_gt = {}
    for pred_id, gt_id in matches.items():
        if gt_id not in pred_by_gt:
            pred_by_gt[gt_id] = []
        pred_by_gt[gt_id].append(pred_id)
    
    for gt_id, pred_ids in pred_by_gt.items():
        gt_elem = next((e for e in ground_truth if e['id'] == gt_id), None)
        if not gt_elem:
            continue
        
        elem_type = gt_elem.get('type', '').lower()
        if elem_type in ('text', 'title', 'header_1', 'header_2', 'header_3',
                       'header_4', 'header_5', 'header_6', 'caption', 'list_item'):
            gt_content = gt_elem.get('content', '') or ""
            
            if gt_content:
                if len(pred_ids) > 1:
                    pred_contents = []
                    for pred_id in pred_ids:
                        pred_elem = next((e for e in predicted if e.id == pred_id), None)
                        if pred_elem and pred_elem.content:
                            pred_contents.append(pred_elem.content)
                    pred_content = " ".join(pred_contents)
                else:
                    pred_elem = next((e for e in predicted if e.id == pred_ids[0]), None)
                    pred_content = pred_elem.content or "" if pred_elem else ""
                
                if pred_content:
                    cer = calculate_cer(gt_content, pred_content)
                    wer = calculate_wer(gt_content, pred_content)
                    cer_scores.append(cer)
                    wer_scores.append(wer)
    
    avg_cer = statistics.mean(cer_scores) if cer_scores else 0.0
    avg_wer = statistics.mean(wer_scores) if wer_scores else 0.0
    
    # Вычисляем TEDS
    ordering_acc, _ = calculate_ordering_accuracy(predicted, ground_truth, matches)
    hierarchy_acc = calculate_hierarchy_teds(predicted, ground_truth, matches)
    doc_teds = (ordering_acc + hierarchy_acc) / 2.0
    hierarchy_teds = calculate_hierarchy_teds(predicted, ground_truth, matches)
    
    # Создаём детальный анализ TEDS (если функция доступна)
    if create_teds_visualizations_and_report is not None:
        try:
            annotations_dir = annotation_path.parent
            annotation_name = annotation_path.stem
            teds_analysis_dir = annotations_dir.parent / "teds_analysis_marker" / annotation_name
            teds_analysis_dir.mkdir(parents=True, exist_ok=True)
            
            json_path, image_paths = create_teds_visualizations_and_report(
                predicted=predicted,
                ground_truth=ground_truth,
                matches=matches,
                document_id=document_id,
                document_teds=doc_teds,
                hierarchy_teds=hierarchy_teds,
                ordering_accuracy=ordering_acc,
                output_dir=teds_analysis_dir,
                document_format=document_format
            )
            
            print(f"  Создан анализ TEDS: {json_path}")
        except Exception as e:
            print(f"  Предупреждение: не удалось создать анализ TEDS: {e}")
    else:
        print(f"  Пропущен анализ TEDS (функция недоступна)")
    
    # Вычисляем метрики детекции классов
    class_metrics = calculate_class_detection_accuracy(predicted, ground_truth, matches)
    
    # Вычисляем метрики по заменам типов
    type_substitutions = calculate_type_substitutions(predicted, ground_truth, matches)
    
    # Вычисляем метрики по заменам уровней заголовков
    header_level_substitutions = calculate_header_level_substitutions(predicted, ground_truth, matches)
    
    # Создаем визуализацию сравнения (если функция доступна)
    if visualize_comparison is not None:
        try:
            annotations_dir = annotation_path.parent
            visualizations_dir = annotations_dir.parent / "visualizations_marker" / document_id
            visualizations_dir.mkdir(parents=True, exist_ok=True)
            
            saved_images = visualize_comparison(
                pdf_path=source_file,
                predicted=predicted,
                ground_truth=ground_truth,
                bbox_matches=bbox_matches,
                output_dir=visualizations_dir,
                render_scale=2.0
            )
            
            print(f"  Создано {len(saved_images)} изображений визуализации в {visualizations_dir}")
        except Exception as e:
            print(f"  Предупреждение: не удалось создать визуализацию: {e}")
    else:
        print(f"  Пропущена визуализация (функция недоступна)")
    
    return DocumentMetrics(
        document_id=document_id,
        source_file=str(source_file),
        document_format=document_format,
        cer=avg_cer,
        wer=avg_wer,
        time_per_page=time_per_page,
        time_per_document=processing_time,
        total_pages=total_pages,
        document_teds=doc_teds,
        hierarchy_teds=hierarchy_teds,
        class_metrics=class_metrics,
        total_elements_gt=len(ground_truth),
        total_elements_pred=len(predicted),
        matched_elements=len(matches),
        bbox_precision=bbox_precision,
        bbox_recall=bbox_recall,
        bbox_f1=bbox_f1,
        bbox_matched_count=bbox_matched_count,
        type_substitutions=type_substitutions,
        header_level_substitutions=header_level_substitutions
    )


def run_evaluation_pipeline_marker(
    annotations_dir: Path,
    output_file: Optional[Path] = None,
    marker_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Запускает пайплайн оценки для всех PDF аннотаций с использованием marker.
    
    Args:
        annotations_dir: Директория с аннотациями
        output_file: Путь для сохранения результатов (JSON)
        marker_config: Конфигурация для marker (опционально)
    
    Returns:
        Словарь с результатами
    """
    if not MARKER_AVAILABLE:
        raise RuntimeError(
            f"Marker недоступен. Ошибка импорта: {MARKER_ERROR}\n\n"
            "Для работы скрипта необходимо настроить окружение marker:\n"
            "1. Перейдите в директорию marker:\n"
            "   cd experiments/pdf_text_extraction/marker_local\n"
            "2. Установите зависимости:\n"
            "   poetry install  # или pip install -r requirements.txt\n"
            "3. Активируйте окружение:\n"
            "   poetry shell  # или активируйте виртуальное окружение\n"
            "4. Запустите скрипт из этого окружения:\n"
            "   python ../../metrics/evaluation_pipeline_marker.py\n\n"
            "Альтернативно, установите marker-pdf в текущее окружение:\n"
            "   pip install marker-pdf"
        )
    
    if isinstance(annotations_dir, str):
        annotations_dir = Path(annotations_dir)
    
    if not annotations_dir.exists():
        raise ValueError(f"Annotations directory does not exist: {annotations_dir}")
    
    # Находим все PDF аннотации
    # Файлы могут быть в формате: *.pdf_annotation.json или *_pdf_annotation.json
    annotation_files = sorted(
        list(annotations_dir.glob("*.pdf_annotation.json")) + 
        list(annotations_dir.glob("*_pdf_annotation.json"))
    )
    # Убираем дубликаты
    annotation_files = sorted(set(annotation_files))
    
    if not annotation_files:
        raise ValueError(f"No PDF annotation files found in {annotations_dir}")
    
    print(f"Найдено {len(annotation_files)} PDF файлов аннотаций")
    
    # Обрабатываем каждый документ
    all_metrics = []
    
    for i, ann_file in enumerate(annotation_files, 1):
        print(f"\n[{i}/{len(annotation_files)}] Обработка: {ann_file.name}")
        
        try:
            metrics = process_document_with_marker(ann_file, marker_config)
            all_metrics.append(metrics)
            print(f"  ✓ CER: {metrics.cer:.4f}, WER: {metrics.wer:.4f}")
            print(f"  ✓ Время: {metrics.time_per_document:.2f}s (документ), {metrics.time_per_page:.2f}s/страница (страниц: {metrics.total_pages})")
            print(f"  ✓ TEDS документ: {metrics.document_teds:.4f}, иерархия: {metrics.hierarchy_teds:.4f}")
            print(f"  ✓ Bbox: Precision={metrics.bbox_precision:.4f}, Recall={metrics.bbox_recall:.4f}, F1={metrics.bbox_f1:.4f} (найдено {metrics.bbox_matched_count}/{metrics.total_elements_gt})")
            
            type_subs = metrics.type_substitutions
            if type_subs:
                total_subs = type_subs.get('total_substitutions', 0)
                sub_rate = type_subs.get('substitution_rate', 0.0)
                print(f"  ✓ Замены типов: {total_subs} (доля: {sub_rate:.4f})")
            
            header_subs = metrics.header_level_substitutions
            if header_subs:
                total_header_subs = header_subs.get('total_header_substitutions', 0)
                header_sub_rate = header_subs.get('header_substitution_rate', 0.0)
                print(f"  ✓ Замены уровней заголовков: {total_header_subs} (доля: {header_sub_rate:.4f})")
        except Exception as e:
            print(f"  ✗ Ошибка: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Вычисляем агрегированные метрики
    if not all_metrics:
        raise ValueError("No documents processed successfully")
    
    # Группируем метрики по типу документа
    metrics_by_format = defaultdict(list)
    for m in all_metrics:
        format_name = m.document_format
        is_scanned = (
            format_name == 'scanned_pdf' or
            '_scanned' in m.source_file.lower() or
            '_scanned' in str(m.document_id).lower()
        )
        
        if format_name == 'pdf' or format_name == 'pdf_regular' or format_name == 'scanned_pdf':
            if is_scanned:
                format_name = 'scanned_pdf'
            else:
                format_name = 'pdf_regular'
        metrics_by_format[format_name].append(m)
    
    # Средние метрики (общие)
    avg_cer = statistics.mean([m.cer for m in all_metrics])
    avg_wer = statistics.mean([m.wer for m in all_metrics])
    avg_time_per_page = statistics.mean([m.time_per_page for m in all_metrics])
    avg_time_per_doc = statistics.mean([m.time_per_document for m in all_metrics])
    avg_doc_teds = statistics.mean([m.document_teds for m in all_metrics])
    avg_hierarchy_teds = statistics.mean([m.hierarchy_teds for m in all_metrics])
    
    # Агрегируем метрики по заменам типов
    total_type_substitutions = sum([m.type_substitutions.get('total_substitutions', 0) for m in all_metrics])
    avg_substitution_rate = statistics.mean([m.type_substitutions.get('substitution_rate', 0.0) for m in all_metrics])
    
    # Агрегируем метрики по заменам уровней заголовков
    total_header_substitutions = sum([m.header_level_substitutions.get('total_header_substitutions', 0) for m in all_metrics])
    avg_header_substitution_rate = statistics.mean([m.header_level_substitutions.get('header_substitution_rate', 0.0) for m in all_metrics])
    
    # Метрики по типам документов
    format_metrics = {}
    for format_name, format_metrics_list in metrics_by_format.items():
        if format_metrics_list:
            format_metrics[format_name] = {
                'count': len(format_metrics_list),
                'avg_cer': statistics.mean([m.cer for m in format_metrics_list]),
                'avg_wer': statistics.mean([m.wer for m in format_metrics_list]),
                'avg_time_per_page': statistics.mean([m.time_per_page for m in format_metrics_list]),
                'avg_time_per_document': statistics.mean([m.time_per_document for m in format_metrics_list]),
                'avg_document_teds': statistics.mean([m.document_teds for m in format_metrics_list]),
                'avg_hierarchy_teds': statistics.mean([m.hierarchy_teds for m in format_metrics_list]),
                'avg_bbox_precision': statistics.mean([m.bbox_precision for m in format_metrics_list]),
                'avg_bbox_recall': statistics.mean([m.bbox_recall for m in format_metrics_list]),
                'avg_bbox_f1': statistics.mean([m.bbox_f1 for m in format_metrics_list]),
                'total_type_substitutions': sum([m.type_substitutions.get('total_substitutions', 0) for m in format_metrics_list]),
                'avg_substitution_rate': statistics.mean([m.type_substitutions.get('substitution_rate', 0.0) for m in format_metrics_list]),
                'total_header_substitutions': sum([m.header_level_substitutions.get('total_header_substitutions', 0) for m in format_metrics_list]),
                'avg_header_substitution_rate': statistics.mean([m.header_level_substitutions.get('header_substitution_rate', 0.0) for m in format_metrics_list])
            }
    
    # Агрегируем метрики классов
    all_class_metrics = defaultdict(lambda: {
        'precision': [],
        'recall': [],
        'f1': [],
        'count_gt': 0,
        'count_pred': 0,
        'count_matched': 0
    })
    
    class_metrics_by_format = defaultdict(lambda: defaultdict(lambda: {
        'precision': [],
        'recall': [],
        'f1': [],
        'count_gt': 0,
        'count_pred': 0,
        'count_matched': 0
    }))
    
    for m in all_metrics:
        format_name = m.document_format
        is_scanned = (
            format_name == 'scanned_pdf' or
            '_scanned' in m.source_file.lower() or
            '_scanned' in str(m.document_id).lower()
        )
        
        if format_name == 'pdf' or format_name == 'pdf_regular' or format_name == 'scanned_pdf':
            if is_scanned:
                format_name = 'scanned_pdf'
            else:
                format_name = 'pdf_regular'
        
        for class_name, class_metric in m.class_metrics.items():
            all_class_metrics[class_name]['precision'].append(class_metric['precision'])
            all_class_metrics[class_name]['recall'].append(class_metric['recall'])
            all_class_metrics[class_name]['f1'].append(class_metric['f1'])
            all_class_metrics[class_name]['count_gt'] += class_metric['count_gt']
            all_class_metrics[class_name]['count_pred'] += class_metric['count_pred']
            all_class_metrics[class_name]['count_matched'] += class_metric['count_matched']
            
            class_metrics_by_format[format_name][class_name]['precision'].append(class_metric['precision'])
            class_metrics_by_format[format_name][class_name]['recall'].append(class_metric['recall'])
            class_metrics_by_format[format_name][class_name]['f1'].append(class_metric['f1'])
            class_metrics_by_format[format_name][class_name]['count_gt'] += class_metric['count_gt']
            class_metrics_by_format[format_name][class_name]['count_pred'] += class_metric['count_pred']
            class_metrics_by_format[format_name][class_name]['count_matched'] += class_metric['count_matched']
    
    # Вычисляем средние метрики классов
    avg_class_metrics = {}
    for class_name, metrics_list in all_class_metrics.items():
        if metrics_list['precision']:
            avg_class_metrics[class_name] = {
                'precision': statistics.mean(metrics_list['precision']),
                'recall': statistics.mean(metrics_list['recall']),
                'f1': statistics.mean(metrics_list['f1']),
                'count_gt': metrics_list['count_gt'],
                'count_pred': metrics_list['count_pred'],
                'count_matched': metrics_list['count_matched']
            }
    
    avg_class_metrics_by_format = {}
    for format_name, format_class_metrics in class_metrics_by_format.items():
        avg_class_metrics_by_format[format_name] = {}
        for class_name, metrics_list in format_class_metrics.items():
            if metrics_list['precision']:
                avg_class_metrics_by_format[format_name][class_name] = {
                    'precision': statistics.mean(metrics_list['precision']),
                    'recall': statistics.mean(metrics_list['recall']),
                    'f1': statistics.mean(metrics_list['f1']),
                    'count_gt': metrics_list['count_gt'],
                    'count_pred': metrics_list['count_pred'],
                    'count_matched': metrics_list['count_matched']
                }
    
    # Формируем результаты
    results = {
        'evaluation_date': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_documents': len(all_metrics),
        'overall_metrics': {
            'avg_cer': avg_cer,
            'avg_wer': avg_wer,
            'avg_time_per_page': avg_time_per_page,
            'avg_time_per_document': avg_time_per_doc,
            'avg_document_teds': avg_doc_teds,
            'avg_hierarchy_teds': avg_hierarchy_teds,
            'total_type_substitutions': total_type_substitutions,
            'avg_substitution_rate': avg_substitution_rate,
            'total_header_substitutions': total_header_substitutions,
            'avg_header_substitution_rate': avg_header_substitution_rate
        },
        'format_metrics': format_metrics,
        'class_metrics': avg_class_metrics,
        'class_metrics_by_format': avg_class_metrics_by_format,
        'document_metrics': [
            {
                'document_id': m.document_id,
                'source_file': m.source_file,
                'document_format': m.document_format,
                'cer': m.cer,
                'wer': m.wer,
                'time_per_page': m.time_per_page,
                'time_per_document': m.time_per_document,
                'total_pages': m.total_pages,
                'document_teds': m.document_teds,
                'hierarchy_teds': m.hierarchy_teds,
                'bbox_precision': m.bbox_precision,
                'bbox_recall': m.bbox_recall,
                'bbox_f1': m.bbox_f1,
                'bbox_matched_count': m.bbox_matched_count,
                'total_elements_gt': m.total_elements_gt,
                'total_elements_pred': m.total_elements_pred,
                'matched_elements': m.matched_elements,
                'type_substitutions': m.type_substitutions,
                'header_level_substitutions': m.header_level_substitutions,
                'class_metrics': m.class_metrics
            }
            for m in all_metrics
        ]
    }
    
    # Сохраняем результаты
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n✓ Результаты сохранены в: {output_file}")
    
    # Выводим сводку
    print("\n" + "="*80)
    print("СВОДКА МЕТРИК (Marker)")
    print("="*80)
    print(f"Всего документов: {len(all_metrics)}")
    print(f"\nОбщие метрики:")
    print(f"  CER: {avg_cer:.4f}")
    print(f"  WER: {avg_wer:.4f}")
    print(f"  Время на страницу: {avg_time_per_page:.2f}s")
    print(f"  Время на документ: {avg_time_per_doc:.2f}s")
    print(f"  Document TEDS: {avg_doc_teds:.4f}")
    print(f"  Hierarchy TEDS: {avg_hierarchy_teds:.4f}")
    print(f"  Замены типов: {total_type_substitutions} (доля: {avg_substitution_rate:.4f})")
    print(f"  Замены уровней заголовков: {total_header_substitutions} (доля: {avg_header_substitution_rate:.4f})")
    
    for format_name, fmt_metrics in format_metrics.items():
        print(f"\nМетрики для {format_name} ({fmt_metrics['count']} документов):")
        print(f"  CER: {fmt_metrics['avg_cer']:.4f}")
        print(f"  WER: {fmt_metrics['avg_wer']:.4f}")
        print(f"  Document TEDS: {fmt_metrics['avg_document_teds']:.4f}")
        print(f"  Hierarchy TEDS: {fmt_metrics['avg_hierarchy_teds']:.4f}")
        print(f"  Bbox Precision: {fmt_metrics['avg_bbox_precision']:.4f}")
        print(f"  Bbox Recall: {fmt_metrics['avg_bbox_recall']:.4f}")
        print(f"  Bbox F1: {fmt_metrics['avg_bbox_f1']:.4f}")
    
    print("\n" + "="*80)
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Evaluate PDF parsing quality using Marker")
    parser.add_argument(
        "--annotations_dir",
        type=str,
        default="annotations",
        help="Directory with annotation files (default: annotations)"
    )
    parser.add_argument(
        "--output_file",
        type=str,
        default="evaluation_results_marker.json",
        help="Output JSON file (default: evaluation_results_marker.json)"
    )
    parser.add_argument(
        "--use_llm",
        action="store_true",
        help="Use LLM for higher quality processing"
    )
    
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent
    
    # Правильно разрешаем пути
    # Если путь абсолютный, используем его как есть
    # Если относительный, разрешаем относительно текущей рабочей директории
    if Path(args.annotations_dir).is_absolute():
        annotations_dir = Path(args.annotations_dir)
    else:
        # Пробуем относительно script_dir, затем относительно текущей директории
        annotations_dir = (script_dir / args.annotations_dir).resolve()
        if not annotations_dir.exists():
            annotations_dir = Path(args.annotations_dir).resolve()
    
    if Path(args.output_file).is_absolute():
        output_file = Path(args.output_file)
    else:
        output_file = (script_dir / args.output_file).resolve()
    
    marker_config = {}
    if args.use_llm:
        marker_config['use_llm'] = True
    
    results = run_evaluation_pipeline_marker(
        annotations_dir=annotations_dir,
        output_file=output_file,
        marker_config=marker_config
    )
    
    print(f"\n✓ Оценка завершена. Результаты сохранены в: {output_file}")

"""
Модуль для детального анализа TEDS (Tree-Edit-Distance-based Similarity).

Включает:
- Детальный анализ ошибок иерархии
- Визуализацию структуры документа
- JSON отчеты с описанием ошибок
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from collections import defaultdict

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
    import networkx as nx
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

from documentor.domain.models import Element, ElementType


@dataclass
class HierarchyError:
    """Детальная информация об ошибке в иерархии."""
    element_id: str
    element_type: str
    element_content_preview: str
    predicted_parent_id: Optional[str]
    predicted_parent_content: Optional[str]
    ground_truth_parent_id: Optional[str]
    ground_truth_parent_content: Optional[str]
    page_number: int
    error_type: str  # 'wrong_parent', 'missing_parent', 'extra_parent', 'orphan'


@dataclass
class StructureError:
    """Детальная информация об ошибке в структуре."""
    element_id: str
    element_type: str
    element_content_preview: str
    predicted_order: Optional[int]
    ground_truth_order: Optional[int]
    page_number: int
    error_type: str  # 'order_mismatch', 'missing', 'extra'


@dataclass
class TEDSAnalysis:
    """Детальный анализ TEDS для документа."""
    document_id: str
    document_teds: float
    hierarchy_teds: float
    ordering_accuracy: float
    
    # Детальные ошибки
    hierarchy_errors: List[HierarchyError] = field(default_factory=list)
    structure_errors: List[StructureError] = field(default_factory=list)
    
    # Статистика
    total_elements: int = 0
    elements_with_correct_hierarchy: int = 0
    elements_with_correct_order: int = 0
    
    # Информация о дереве
    predicted_tree: Dict[str, Any] = field(default_factory=dict)
    ground_truth_tree: Dict[str, Any] = field(default_factory=dict)


def analyze_hierarchy_errors(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str],
    document_format: Optional[str] = None
) -> List[HierarchyError]:
    """
    Анализирует ошибки в иерархии элементов.
    
    Args:
        predicted: Список предсказанных элементов
        ground_truth: Список элементов из ground truth
        matches: Словарь сопоставлений pred_id -> gt_id
        document_format: Формат документа ('docx', 'pdf', и т.д.)
    
    Returns:
        Список детальных ошибок иерархии
    """
    errors = []
    
    # Создаём словари для быстрого доступа
    pred_dict = {elem.id: elem for elem in predicted}
    gt_dict = {elem['id']: elem for elem in ground_truth}
    
    # Обратный маппинг (gt_id -> pred_id)
    gt_to_pred = {gt_id: pred_id for pred_id, gt_id in matches.items()}
    pred_to_gt = matches  # pred_id -> gt_id
    
    # Создаём маппинг для родителей
    pred_parent_map = {}  # pred_id -> pred_parent_id
    gt_parent_map = {}  # gt_id -> gt_parent_id
    
    for pred_elem in predicted:
        pred_parent_map[pred_elem.id] = pred_elem.parent_id
    
    for gt_elem in ground_truth:
        gt_parent_map[gt_elem['id']] = gt_elem.get('parent_id')
    
    # Анализируем каждый сопоставленный элемент
    matched_gt_ids = set()
    for pred_id, gt_id in matches.items():
        matched_gt_ids.add(gt_id)
        pred_elem = pred_dict.get(pred_id)
        gt_elem = gt_dict.get(gt_id)
        
        if not pred_elem or not gt_elem:
            continue
        
        # Игнорируем HEADER_1 (они могут быть без родителей)
        if gt_elem.get('type', '').lower() == 'header_1':
            continue
        
        pred_parent_id = pred_elem.parent_id
        gt_parent_id = gt_elem.get('parent_id')
        
        # Получаем контент для предпросмотра
        pred_content = (pred_elem.content or '')[:100]
        gt_content = (gt_elem.get('content', '') or '')[:100]
        
        page_num = gt_elem.get('page_number', 0)
        
        # Проверяем соответствие родителей
        if pred_parent_id and gt_parent_id:
            # Оба имеют родителей - проверяем соответствие
            pred_parent_gt_id = pred_to_gt.get(pred_parent_id)
            
            if pred_parent_gt_id != gt_parent_id:
                # Неправильный родитель
                # ИГНОРИРУЕМ ошибки для TEXT элементов в DOCX (слипание текстовых элементов)
                if document_format == 'docx' and gt_elem.get('type', '').lower() == 'text':
                    continue
                
                pred_parent_elem = pred_dict.get(pred_parent_id)
                gt_parent_elem = gt_dict.get(gt_parent_id)
                
                pred_parent_content = (pred_parent_elem.content or '')[:100] if pred_parent_elem else None
                gt_parent_content = (gt_parent_elem.get('content', '') or '')[:100] if gt_parent_elem else None
                
                # Если родитель не найден в маппинге, но содержимое совпадает - это не ошибка
                # (родитель правильный, просто не был сопоставлен по bbox/тексту)
                if pred_parent_gt_id is None and pred_parent_content and gt_parent_content:
                    # Нормализуем содержимое для сравнения (убираем пробелы, приводим к нижнему регистру)
                    pred_content_normalized = pred_parent_content.strip().lower()
                    gt_content_normalized = gt_parent_content.strip().lower()
                    
                    # Если содержимое совпадает (или очень похоже), пропускаем ошибку
                    if pred_content_normalized == gt_content_normalized:
                        continue
                    # Также проверяем, если одно содержимое является началом другого
                    if (pred_content_normalized and gt_content_normalized and 
                        (pred_content_normalized.startswith(gt_content_normalized[:50]) or 
                         gt_content_normalized.startswith(pred_content_normalized[:50]))):
                        continue
                
                errors.append(HierarchyError(
                    element_id=gt_id,
                    element_type=gt_elem.get('type', 'unknown'),
                    element_content_preview=gt_content,
                    predicted_parent_id=pred_parent_id,
                    predicted_parent_content=pred_parent_content,
                    ground_truth_parent_id=gt_parent_id,
                    ground_truth_parent_content=gt_parent_content,
                    page_number=page_num,
                    error_type='wrong_parent'
                ))
        elif pred_parent_id and not gt_parent_id:
            # У предсказания есть родитель, у GT нет
            # ИГНОРИРУЕМ ошибки для TEXT элементов в DOCX (слипание текстовых элементов)
            if document_format == 'docx' and gt_elem.get('type', '').lower() == 'text':
                continue
            
            pred_parent_elem = pred_dict.get(pred_parent_id)
            pred_parent_content = (pred_parent_elem.content or '')[:100] if pred_parent_elem else None
            
            errors.append(HierarchyError(
                element_id=gt_id,
                element_type=gt_elem.get('type', 'unknown'),
                element_content_preview=gt_content,
                predicted_parent_id=pred_parent_id,
                predicted_parent_content=pred_parent_content,
                ground_truth_parent_id=None,
                ground_truth_parent_content=None,
                page_number=page_num,
                error_type='extra_parent'
            ))
        elif not pred_parent_id and gt_parent_id:
            # У предсказания нет родителя, у GT есть
            # ИГНОРИРУЕМ ошибки для TEXT элементов в DOCX (слипание текстовых элементов)
            if document_format == 'docx' and gt_elem.get('type', '').lower() == 'text':
                continue
            
            gt_parent_elem = gt_dict.get(gt_parent_id)
            gt_parent_content = (gt_parent_elem.get('content', '') or '')[:100] if gt_parent_elem else None
            
            errors.append(HierarchyError(
                element_id=gt_id,
                element_type=gt_elem.get('type', 'unknown'),
                element_content_preview=gt_content,
                predicted_parent_id=None,
                predicted_parent_content=None,
                ground_truth_parent_id=gt_parent_id,
                ground_truth_parent_content=gt_parent_content,
                page_number=page_num,
                error_type='missing_parent'
            ))
    
    # Также проверяем элементы GT, которые не были сопоставлены
    # Они могут иметь проблемы с родителями
    for gt_elem in ground_truth:
        gt_id = gt_elem['id']
        if gt_id not in matched_gt_ids:
            # Элемент не был сопоставлен - это тоже ошибка
            gt_parent_id = gt_elem.get('parent_id')
            gt_content = (gt_elem.get('content', '') or '')[:100]
            page_num = gt_elem.get('page_number', 0)
            
            # Проверяем, есть ли у родителя проблемы
            if gt_parent_id:
                gt_parent_elem = gt_dict.get(gt_parent_id)
                gt_parent_content = (gt_parent_elem.get('content', '') or '')[:100] if gt_parent_elem else None
                
                # Проверяем, сопоставлен ли родитель
                if gt_parent_id not in matched_gt_ids:
                    # Родитель тоже не сопоставлен - это ошибка
                    # ИГНОРИРУЕМ ошибки для TEXT элементов в DOCX (слипание текстовых элементов)
                    if document_format == 'docx' and gt_elem.get('type', '').lower() == 'text':
                        continue
                    
                    errors.append(HierarchyError(
                        element_id=gt_id,
                        element_type=gt_elem.get('type', 'unknown'),
                        element_content_preview=gt_content,
                        predicted_parent_id=None,
                        predicted_parent_content=None,
                        ground_truth_parent_id=gt_parent_id,
                        ground_truth_parent_content=gt_parent_content,
                        page_number=page_num,
                        error_type='missing_parent'
                    ))
    
    return errors


def analyze_structure_errors(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> List[StructureError]:
    """
    Анализирует ошибки в порядке элементов.
    
    Returns:
        Список детальных ошибок структуры
    """
    errors = []
    
    # Создаём словари для быстрого доступа
    pred_dict = {elem.id: elem for elem in predicted}
    gt_dict = {elem['id']: elem for elem in ground_truth}
    
    # Создаём списки элементов в порядке появления
    # Для предсказаний используем порядок в списке
    pred_ordered = [(i, elem) for i, elem in enumerate(predicted)]
    
    # Для GT используем поле order, если оно есть
    gt_ordered = []
    for gt_elem in ground_truth:
        order = gt_elem.get('order')
        if order is not None:
            gt_ordered.append((order, gt_elem))
        else:
            # Если order нет, используем порядок в списке
            gt_ordered.append((len(gt_ordered), gt_elem))
    
    gt_ordered.sort(key=lambda x: x[0])
    
    # Создаём маппинг pred_id -> order в предсказаниях
    pred_order_map = {}
    for order, pred_elem in enumerate(predicted):
        pred_order_map[pred_elem.id] = order
    
    # Создаём маппинг gt_id -> order в GT
    gt_order_map = {}
    for order, gt_elem in gt_ordered:
        gt_order_map[gt_elem['id']] = order
    
    # Анализируем порядок для сопоставленных элементов
    matched_pred_orders = []
    matched_gt_orders = []
    
    for pred_id, gt_id in matches.items():
        pred_order = pred_order_map.get(pred_id)
        gt_order = gt_order_map.get(gt_id)
        
        if pred_order is not None and gt_order is not None:
            matched_pred_orders.append((pred_order, pred_id, gt_id))
            matched_gt_orders.append((gt_order, pred_id, gt_id))
    
    # Сортируем по порядку
    matched_pred_orders.sort(key=lambda x: x[0])
    matched_gt_orders.sort(key=lambda x: x[0])
    
    # Проверяем соответствие порядка
    for i, (pred_order, pred_id, gt_id) in enumerate(matched_pred_orders):
        gt_order = gt_order_map.get(gt_id)
        gt_elem = gt_dict.get(gt_id)
        
        if gt_elem and gt_order is not None:
            # Проверяем, соответствует ли порядок
            expected_gt_order = matched_gt_orders[i][0] if i < len(matched_gt_orders) else None
            
            if expected_gt_order is not None and gt_order != expected_gt_order:
                # Порядок не совпадает
                errors.append(StructureError(
                    element_id=gt_id,
                    element_type=gt_elem.get('type', 'unknown'),
                    element_content_preview=(gt_elem.get('content', '') or '')[:100],
                    predicted_order=pred_order,
                    ground_truth_order=gt_order,
                    page_number=gt_elem.get('page_number', 0),
                    error_type='order_mismatch'
                ))
    
    # Находим элементы, которые есть в GT, но нет в предсказаниях
    # Но сначала проверяем, не сопоставлен ли элемент с другим элементом
    # (это может быть проблема уровня, а не отсутствие)
    matched_gt_ids = set(matches.values())
    
    # Проверяем, есть ли похожие элементы в predicted по содержимому
    pred_content_map = {}
    for pred_elem in predicted:
        content_key = (pred_elem.content or '').strip()[:100].lower()
        if content_key:
            if content_key not in pred_content_map:
                pred_content_map[content_key] = []
            pred_content_map[content_key].append(pred_elem.id)
    
    for gt_elem in ground_truth:
        gt_id = gt_elem['id']
        if gt_id not in matched_gt_ids:
            gt_content = (gt_elem.get('content', '') or '').strip()[:100].lower()
            gt_order = gt_order_map.get(gt_id)
            
            # Проверяем, есть ли похожий элемент в predicted по содержимому
            similar_found = False
            if gt_content and gt_content in pred_content_map:
                # Найден похожий элемент - это не "missing", а проблема уровня/родителя
                # Не добавляем как "missing", так как элемент фактически присутствует
                similar_found = True
            
            if not similar_found:
                # Элемент действительно отсутствует
                errors.append(StructureError(
                    element_id=gt_id,
                    element_type=gt_elem.get('type', 'unknown'),
                    element_content_preview=(gt_elem.get('content', '') or '')[:100],
                    predicted_order=None,
                    ground_truth_order=gt_order,
                    page_number=gt_elem.get('page_number', 0),
                    error_type='missing'
                ))
    
    # Находим элементы, которые есть в предсказаниях, но нет в GT
    matched_pred_ids = set(matches.keys())
    for pred_elem in predicted:
        pred_id = pred_elem.id
        if pred_id not in matched_pred_ids:
            errors.append(StructureError(
                element_id=pred_id,
                element_type=pred_elem.type.value if hasattr(pred_elem.type, 'value') else str(pred_elem.type),
                element_content_preview=(pred_elem.content or '')[:100],
                predicted_order=pred_order_map.get(pred_id),
                ground_truth_order=None,
                page_number=pred_elem.metadata.get('page_num', 0),
                error_type='extra'
            ))
    
    return errors


def build_tree_structure(
    elements: List[Any],
    is_predicted: bool = True
) -> Dict[str, Any]:
    """
    Строит структуру дерева из элементов.
    
    Args:
        elements: Список элементов (Element или Dict)
        is_predicted: True если это предсказания, False если GT
    
    Returns:
        Словарь с информацией о дереве:
        {
            'nodes': [...],
            'edges': [...],
            'root_nodes': [...],
            'max_depth': int
        }
    """
    nodes = []
    edges = []
    parent_map = {}
    
    # Создаём узлы
    for elem in elements:
        if is_predicted:
            elem_id = elem.id
            elem_type = elem.type.value if hasattr(elem.type, 'value') else str(elem.type)
            elem_content = (elem.content or '')[:50]
            parent_id = elem.parent_id
            page_num = elem.metadata.get('page_num', 0)
        else:
            elem_id = elem['id']
            elem_type = elem.get('type', 'unknown')
            elem_content = (elem.get('content', '') or '')[:50]
            parent_id = elem.get('parent_id')
            page_num = elem.get('page_number', 0)
        
        nodes.append({
            'id': elem_id,
            'type': elem_type,
            'content_preview': elem_content,
            'page_number': page_num
        })
        
        if parent_id:
            parent_map[elem_id] = parent_id
    
    # Создаём рёбра
    root_nodes = []
    for node in nodes:
        node_id = node['id']
        parent_id = parent_map.get(node_id)
        
        if parent_id:
            edges.append({
                'from': parent_id,
                'to': node_id
            })
        else:
            root_nodes.append(node_id)
    
    # Вычисляем максимальную глубину
    def get_depth(node_id: str, visited: Set[str] = None) -> int:
        if visited is None:
            visited = set()
        
        if node_id in visited:
            return 0  # Цикл
        
        visited.add(node_id)
        
        children = [edge['to'] for edge in edges if edge['from'] == node_id]
        if not children:
            return 1
        
        max_child_depth = max([get_depth(child_id, visited.copy()) for child_id in children], default=0)
        return 1 + max_child_depth
    
    max_depth = max([get_depth(root_id) for root_id in root_nodes], default=0) if root_nodes else 0
    
    return {
        'nodes': nodes,
        'edges': edges,
        'root_nodes': root_nodes,
        'max_depth': max_depth,
        'total_nodes': len(nodes)
    }


def create_detailed_teds_analysis(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str],
    document_id: str,
    document_teds: float,
    hierarchy_teds: float,
    ordering_accuracy: float,
    document_format: Optional[str] = None
) -> TEDSAnalysis:
    """
    Создаёт детальный анализ TEDS для документа.
    
    Args:
        predicted: Список предсказанных элементов
        ground_truth: Список элементов из ground truth
        matches: Словарь сопоставлений pred_id -> gt_id
        document_id: ID документа
        document_teds: TEDS для документа
        hierarchy_teds: TEDS для иерархии
        ordering_accuracy: Точность порядка
        document_format: Формат документа ('docx', 'pdf', и т.д.)
    
    Returns:
        TEDSAnalysis с детальной информацией
    """
    # Анализируем ошибки
    hierarchy_errors = analyze_hierarchy_errors(predicted, ground_truth, matches, document_format)
    structure_errors = analyze_structure_errors(predicted, ground_truth, matches)
    
    # Строим деревья
    predicted_tree = build_tree_structure(predicted, is_predicted=True)
    ground_truth_tree = build_tree_structure(ground_truth, is_predicted=False)
    
    # Подсчитываем статистику
    total_elements = len(ground_truth)
    elements_with_correct_hierarchy = total_elements - len(hierarchy_errors)
    elements_with_correct_order = total_elements - len([e for e in structure_errors if e.error_type != 'extra'])
    
    return TEDSAnalysis(
        document_id=document_id,
        document_teds=document_teds,
        hierarchy_teds=hierarchy_teds,
        ordering_accuracy=ordering_accuracy,
        hierarchy_errors=hierarchy_errors,
        structure_errors=structure_errors,
        total_elements=total_elements,
        elements_with_correct_hierarchy=elements_with_correct_hierarchy,
        elements_with_correct_order=elements_with_correct_order,
        predicted_tree=predicted_tree,
        ground_truth_tree=ground_truth_tree
    )


def visualize_hierarchy_tree(
    tree_data: Dict[str, Any],
    title: str,
    output_path: Path,
    errors: Optional[List[HierarchyError]] = None,
    matches: Optional[Dict[str, str]] = None
) -> bool:
    """
    Визуализирует иерархию элементов в виде иерархического списка с отступами.
    
    Args:
        tree_data: Данные дерева из build_tree_structure
        title: Заголовок визуализации
        output_path: Путь для сохранения изображения
        errors: Список ошибок для выделения
    
    Returns:
        True если успешно, False иначе
    """
    if not HAS_MATPLOTLIB:
        return False
    
    try:
        if len(tree_data['nodes']) == 0:
            return False
        
        # Создаём словари для быстрого доступа
        nodes_dict = {node['id']: node for node in tree_data['nodes']}
        edges_dict = defaultdict(list)
        for edge in tree_data['edges']:
            edges_dict[edge['from']].append(edge['to'])
        
        # Создаём маппинг родитель -> дети
        children_map = defaultdict(list)
        for edge in tree_data['edges']:
            children_map[edge['from']].append(edge['to'])
        
        # Находим корневые узлы
        all_children = set()
        for children in children_map.values():
            all_children.update(children)
        
        root_nodes = [node['id'] for node in tree_data['nodes'] if node['id'] not in all_children]
        if not root_nodes:
            # Если нет явных корней, используем все узлы без родителей
            root_nodes = [node['id'] for node in tree_data['nodes']]
        
        # Создаём список ошибок для быстрого поиска
        error_ids = set()
        error_info = {}
        if errors:
            # Используем element_id из ошибок напрямую
            error_ids = {e.element_id for e in errors}
            error_info = {e.element_id: e for e in errors}
            
            # Если есть matches, также добавляем ошибки по альтернативным ID
            if matches:
                # Создаём обратный маппинг для поиска ошибок по альтернативным ID
                gt_to_pred_map = {gt_id: pred_id for pred_id, gt_id in matches.items()}
                pred_to_gt_map = matches  # pred_id -> gt_id
                
                for error in errors:
                    error_element_id = error.element_id
                    
                    # Если error.element_id это gt_id, добавляем соответствующий pred_id
                    if error_element_id in gt_to_pred_map:
                        pred_id = gt_to_pred_map[error_element_id]
                        error_ids.add(pred_id)
                        if pred_id not in error_info:
                            error_info[pred_id] = error
                    
                    # Если error.element_id это pred_id, добавляем соответствующий gt_id
                    if error_element_id in pred_to_gt_map:
                        gt_id = pred_to_gt_map[error_element_id]
                        error_ids.add(gt_id)
                        if gt_id not in error_info:
                            error_info[gt_id] = error
        
        # Функция для построения иерархического списка
        def build_hierarchy_list(node_id: str, depth: int = 0, visited: Set[str] = None) -> List[Tuple[int, Dict[str, Any]]]:
            if visited is None:
                visited = set()
            
            if node_id in visited:
                return []
            
            visited.add(node_id)
            node = nodes_dict.get(node_id)
            if not node:
                return []
            
            result = [(depth, node)]
            
            # Добавляем детей
            children = sorted(children_map.get(node_id, []), 
                           key=lambda x: nodes_dict.get(x, {}).get('page_number', 0))
            
            for child_id in children:
                result.extend(build_hierarchy_list(child_id, depth + 1, visited))
            
            return result
        
        # Строим полный список
        hierarchy_list = []
        for root_id in sorted(root_nodes, key=lambda x: nodes_dict.get(x, {}).get('page_number', 0)):
            hierarchy_list.extend(build_hierarchy_list(root_id, 0))
        
        # Цвета для типов элементов
        type_colors = {
            'title': '#FFD700',  # Золотой
            'header_1': '#4A90E2',  # Синий
            'header_2': '#7BB3F0',  # Светло-синий
            'header_3': '#A8D0F0',  # Еще светлее
            'text': '#E8F5E9',  # Светло-зеленый
            'table': '#FFF9C4',  # Светло-желтый
            'image': '#F8BBD0',  # Светло-розовый
            'default': '#F5F5F5'  # Светло-серый
        }
        
        # Сначала вычисляем позиции всех элементов с учетом их высоты
        element_heights = []
        total_height = 0
        spacing = 3  # Отступ между элементами
        
        for depth, node in hierarchy_list:
            node_id = node['id']
            node_type = node.get('type', 'unknown').lower()
            content = node.get('content_preview', '')[:80]
            is_error = node_id in error_ids
            
            # Вычисляем количество строк текста
            type_text = f"[{node_type.upper()}]" if node_type != 'unknown' else ""
            page_text = f" (стр. {node.get('page_number', 0)})" if node.get('page_number', 0) > 0 else ""
            full_text = f"{type_text} {content}{page_text}"
            
            error_text = ""
            error_details = ""
            if is_error and node_id in error_info:
                error = error_info[node_id]
                if error.error_type == 'wrong_parent':
                    gt_parent = (error.ground_truth_parent_content or error.ground_truth_parent_id or "нет")[:50]
                    pred_parent = (error.predicted_parent_content or error.predicted_parent_id or "нет")[:50]
                    error_text = "ОШИБКА ИЕРАРХИИ"
                    error_details = f"ПРАВИЛЬНО: '{gt_parent}' | НАЙДЕНО: '{pred_parent}'"
                elif error.error_type == 'missing_parent':
                    gt_parent = (error.ground_truth_parent_content or error.ground_truth_parent_id or "неизвестен")[:50]
                    error_text = "ОШИБКА: ОТСУТСТВУЕТ РОДИТЕЛЬ"
                    error_details = f"Должен быть родитель: '{gt_parent}'"
                elif error.error_type == 'extra_parent':
                    pred_parent = (error.predicted_parent_content or error.predicted_parent_id or "неизвестен")[:50]
                    error_text = "ОШИБКА: ЛИШНИЙ РОДИТЕЛЬ"
                    error_details = f"Найден лишний родитель: '{pred_parent}'"
                else:
                    error_text = f"ОШИБКА: {error.error_type.upper()}"
                    error_details = ""
            
            # Подсчитываем количество строк
            max_chars_per_line = 150
            text_lines_count = max(1, (len(full_text) + len(error_text)) // max_chars_per_line + (1 if error_text else 0))
            line_height = 11
            block_height = max(22, text_lines_count * line_height + 4)
            
            element_heights.append((depth, node, block_height, full_text, error_text, error_details))
            total_height += block_height + spacing
        
        # Создаём фигуру с динамическим размером после вычисления total_height
        estimated_height = max(12, total_height / 20)  # Примерная высота в дюймах
        fig, ax = plt.subplots(figsize=(20, estimated_height))
        
        # Отладочная информация
        if errors:
            print(f"    Визуализация: Всего ошибок передано: {len(errors)}")
            print(f"    Визуализация: error_ids содержит {len(error_ids)} ID")
            print(f"    Визуализация: Примеры error_ids: {list(error_ids)[:5]}")
            print(f"    Визуализация: Всего узлов в дереве: {len(tree_data['nodes'])}")
            print(f"    Визуализация: Примеры node_id из дерева: {[n['id'] for n in tree_data['nodes'][:5]]}")
        
        # Рисуем элементы
        current_y = 0
        error_count_in_visualization = 0
        for depth, node, block_height, full_text, error_text, error_details in element_heights:
            node_id = node['id']
            node_type = node.get('type', 'unknown').lower()
            content = node.get('content_preview', '')[:80]
            page_num = node.get('page_number', 0)
            is_error = node_id in error_ids
            
            if is_error:
                error_count_in_visualization += 1
            
            # Определяем цвет фона
            bg_color = type_colors.get(node_type, type_colors['default'])
            if is_error:
                bg_color = '#FF6B6B'  # Красный для ошибок
            
            # Создаём отступ
            indent = depth * 30
            x_start = 10 + indent
            x_end = 980
            y_start = current_y
            y_end = y_start + block_height
            
            # Рисуем фон
            rect = mpatches.FancyBboxPatch(
                (x_start, y_start), x_end - x_start, y_end - y_start,
                boxstyle="round,pad=2", 
                facecolor=bg_color,
                edgecolor='#FF0000' if is_error else '#CCCCCC',
                linewidth=2 if is_error else 1,
                alpha=0.8
            )
            ax.add_patch(rect)
            
            # Разбиваем основной текст на строки
            max_width = x_end - x_start - 10
            max_chars_per_line = int(max_width / 6)  # Примерно 6 пикселей на символ для fontsize=9
            text_lines = []
            
            # Разбиваем основной текст
            words = full_text.split()
            current_line = ""
            for word in words:
                test_line = current_line + (" " if current_line else "") + word
                if len(test_line) > max_chars_per_line and current_line:
                    text_lines.append(current_line)
                    current_line = word
                else:
                    current_line = test_line
            if current_line:
                text_lines.append(current_line)
            
            # Если есть ошибка, увеличиваем высоту блока для размещения информации об ошибке
            if is_error and error_text:
                # Добавляем место для блока с ошибкой
                block_height = max(block_height, len(text_lines) * 11 + 30)
            
            y_end = y_start + block_height
            
            # Рисуем фон с правильной высотой
            rect = mpatches.FancyBboxPatch(
                (x_start, y_start), x_end - x_start, block_height,
                boxstyle="round,pad=2", 
                facecolor=bg_color,
                edgecolor='#FF0000' if is_error else '#CCCCCC',
                linewidth=3 if is_error else 1,
                alpha=0.9 if is_error else 0.8
            )
            ax.add_patch(rect)
            
            # Добавляем индикатор ошибки слева
            if is_error:
                # Красный индикатор
                error_indicator = mpatches.Rectangle(
                    (x_start - 8, y_start), 6, block_height,
                    facecolor='#FF0000',
                    edgecolor='#FF0000',
                    linewidth=2,
                    alpha=1.0
                )
                ax.add_patch(error_indicator)
                
                # Добавляем восклицательный знак
                ax.text(x_start - 5, y_start + block_height / 2, '!',
                       fontsize=14, fontweight='bold', color='#FFFFFF',
                       ha='center', va='center')
            
            # Рисуем основной текст построчно
            line_height = 11
            start_y = y_start + (block_height - (30 if is_error and error_text else 0)) / 2 - (len(text_lines) - 1) * line_height / 2
            
            for i, line in enumerate(text_lines):
                y_pos_line = start_y + i * line_height
                text_color = '#000000' if not is_error else '#FFFFFF'
                weight = 'bold' if is_error else 'normal'
                
                # Экранируем символы $ для предотвращения интерпретации как LaTeX
                line_escaped = line.replace('$', '\\$')
                ax.text(x_start + 5, y_pos_line, line_escaped,
                       fontsize=9, va='center', ha='left',
                       color=text_color,
                       weight=weight)
            
            # Если есть ошибка, добавляем детальную информацию об ошибке внизу блока
            if is_error and error_text:
                error_y = y_start + block_height - 15
                
                # Рисуем фон для текста ошибки
                error_bg = mpatches.FancyBboxPatch(
                    (x_start + 2, error_y - 12), x_end - x_start - 4, 25,
                    boxstyle="round,pad=1",
                    facecolor='#FF0000',
                    edgecolor='#FFFFFF',
                    linewidth=2,
                    alpha=0.95
                )
                ax.add_patch(error_bg)
                
                # Текст типа ошибки (экранируем $)
                error_text_escaped = error_text.replace('$', '\\$')
                ax.text(x_start + 5, error_y, error_text_escaped,
                       fontsize=10, va='center', ha='left',
                       color='#FFFFFF',
                       weight='bold')
                
                # Детали ошибки (экранируем $)
                if error_details:
                    error_details_escaped = error_details.replace('$', '\\$')
                    ax.text(x_start + 5, error_y - 10, error_details_escaped,
                           fontsize=8, va='center', ha='left',
                           color='#FFFF00',
                           weight='normal',
                           style='italic')
            
            # Если есть ошибка, добавляем детальную информацию об ошибке
            if is_error and error_text:
                error_y = y_start + block_height - 8
                
                # Рисуем фон для текста ошибки
                error_bg = mpatches.FancyBboxPatch(
                    (x_start + 2, error_y - 10), x_end - x_start - 4, 20,
                    boxstyle="round,pad=1",
                    facecolor='#FF0000',
                    edgecolor='#FFFFFF',
                    linewidth=1,
                    alpha=0.9
                )
                ax.add_patch(error_bg)
                
                # Текст типа ошибки
                ax.text(x_start + 5, error_y, error_text,
                       fontsize=10, va='center', ha='left',
                       color='#FFFFFF',
                       weight='bold')
                
                # Детали ошибки
                if error_details:
                    ax.text(x_start + 5, error_y - 8, error_details,
                           fontsize=8, va='center', ha='left',
                           color='#FFFF00',
                           weight='normal',
                           style='italic')
            
            current_y += block_height + spacing
        
        # Настраиваем оси
        ax.set_xlim(0, 1000)
        ax.set_ylim(-20, total_height + 40)
        ax.invert_yaxis()
        ax.axis('off')
        
        # Добавляем заголовок (экранируем $)
        title_escaped = title.replace('$', '\\$')
        ax.text(500, -10, title_escaped, fontsize=16, fontweight='bold', 
               ha='center', va='top')
        
        # Добавляем легенду
        legend_y = total_height + 10
        legend_items = [
            ('Title', '#FFD700'),
            ('Header 1', '#4A90E2'),
            ('Header 2', '#7BB3F0'),
            ('Text', '#E8F5E9'),
            ('Table', '#FFF9C4'),
            ('ОШИБКА', '#FF6B6B')
        ]
        
        legend_x = 10
        for label, color in legend_items:
            rect = mpatches.Rectangle((legend_x, legend_y), 15, 15, 
                                     facecolor=color, edgecolor='#CCCCCC', linewidth=1)
            ax.add_patch(rect)
            label_escaped = label.replace('$', '\\$')
            ax.text(legend_x + 20, legend_y + 7.5, label_escaped, 
                   fontsize=9, va='center', ha='left')
            legend_x += 120
        
        # Добавляем статистику
        total_nodes = len(tree_data['nodes'])
        error_count = len(error_ids)
        stats_text = f"Всего элементов: {total_nodes} | Элементов с ошибками: {error_count} | Отображено ошибок: {error_count_in_visualization}"
        stats_text_escaped = stats_text.replace('$', '\\$')
        ax.text(500, legend_y + 20, stats_text_escaped, fontsize=10, 
               ha='center', va='bottom', style='italic')
        
        if errors:
            print(f"    Визуализация: Отображено элементов с ошибками: {error_count_in_visualization} из {error_count}")
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        return True
    except Exception as e:
        print(f"Ошибка при создании визуализации дерева: {e}")
        import traceback
        traceback.print_exc()
        return False


def save_teds_analysis_json(
    analysis: TEDSAnalysis,
    output_path: Path
) -> None:
    """
    Сохраняет детальный анализ TEDS в JSON файл.
    
    Args:
        analysis: TEDSAnalysis объект
        output_path: Путь для сохранения JSON
    """
    # Конвертируем в словарь
    data = {
        'document_id': analysis.document_id,
        'metrics': {
            'document_teds': analysis.document_teds,
            'hierarchy_teds': analysis.hierarchy_teds,
            'ordering_accuracy': analysis.ordering_accuracy
        },
        'statistics': {
            'total_elements': analysis.total_elements,
            'elements_with_correct_hierarchy': analysis.elements_with_correct_hierarchy,
            'elements_with_correct_order': analysis.elements_with_correct_order,
            'hierarchy_accuracy': (analysis.elements_with_correct_hierarchy / analysis.total_elements 
                                  if analysis.total_elements > 0 else 0.0),
            'ordering_accuracy': (analysis.elements_with_correct_order / analysis.total_elements 
                                if analysis.total_elements > 0 else 0.0)
        },
        'hierarchy_errors': [
            {
                'element_id': e.element_id,
                'element_type': e.element_type,
                'element_content_preview': e.element_content_preview,
                'predicted_parent_id': e.predicted_parent_id,
                'predicted_parent_content': e.predicted_parent_content,
                'ground_truth_parent_id': e.ground_truth_parent_id,
                'ground_truth_parent_content': e.ground_truth_parent_content,
                'page_number': e.page_number,
                'error_type': e.error_type
            }
            for e in analysis.hierarchy_errors
        ],
        'structure_errors': [
            {
                'element_id': e.element_id,
                'element_type': e.element_type,
                'element_content_preview': e.element_content_preview,
                'predicted_order': e.predicted_order,
                'ground_truth_order': e.ground_truth_order,
                'page_number': e.page_number,
                'error_type': e.error_type
            }
            for e in analysis.structure_errors
        ],
        'predicted_tree': analysis.predicted_tree,
        'ground_truth_tree': analysis.ground_truth_tree
    }
    
    # Сохраняем в JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def create_tree_markdown(
    tree_data: Dict[str, Any],
    title: str,
    output_path: Path,
    errors: Optional[List[HierarchyError]] = None,
    matches: Optional[Dict[str, str]] = None
) -> bool:
    """
    Создает markdown файл с деревом элементов в стиле структуры директорий.
    
    Args:
        tree_data: Данные дерева из build_tree_structure
        title: Заголовок документа
        output_path: Путь для сохранения markdown файла
        errors: Список ошибок для выделения
        matches: Словарь сопоставлений (для predicted_tree)
    
    Returns:
        True если успешно, False иначе
    """
    try:
        if len(tree_data['nodes']) == 0:
            return False
        
        # Создаём словари для быстрого доступа
        nodes_dict = {node['id']: node for node in tree_data['nodes']}
        children_map = defaultdict(list)
        for edge in tree_data['edges']:
            children_map[edge['from']].append(edge['to'])
        
        # Находим корневые узлы
        all_children = set()
        for children in children_map.values():
            all_children.update(children)
        
        root_nodes = [node['id'] for node in tree_data['nodes'] if node['id'] not in all_children]
        if not root_nodes:
            root_nodes = [node['id'] for node in tree_data['nodes']]
        
        # Создаём список ошибок для быстрого поиска
        error_ids = set()
        error_info = {}
        if errors:
            error_ids = {e.element_id for e in errors}
            error_info = {e.element_id: e for e in errors}
            
            # Если есть matches, также добавляем ошибки по альтернативным ID
            if matches:
                gt_to_pred_map = {gt_id: pred_id for pred_id, gt_id in matches.items()}
                pred_to_gt_map = matches
                
                for error in errors:
                    error_element_id = error.element_id
                    
                    if error_element_id in gt_to_pred_map:
                        pred_id = gt_to_pred_map[error_element_id]
                        error_ids.add(pred_id)
                        if pred_id not in error_info:
                            error_info[pred_id] = error
                    
                    if error_element_id in pred_to_gt_map:
                        gt_id = pred_to_gt_map[error_element_id]
                        error_ids.add(gt_id)
                        if gt_id not in error_info:
                            error_info[gt_id] = error
        
        # Функция для построения дерева
        def build_tree_markdown(node_id: str, prefix: str = "", is_last: bool = True, visited: Set[str] = None) -> List[str]:
            if visited is None:
                visited = set()
            
            if node_id in visited:
                return []
            
            visited.add(node_id)
            node = nodes_dict.get(node_id)
            if not node:
                return []
            
            lines = []
            
            # Обрабатываем случай, когда visited передается извне (для корневых узлов)
            # Создаем новый visited для каждого корневого узла, чтобы избежать циклов
            
            # Определяем символы для дерева
            connector = "└── " if is_last else "├── "
            extension = "    " if is_last else "│   "
            
            # Получаем информацию об элементе
            node_type = node.get('type', 'unknown')
            content = node.get('content_preview', '')[:60]
            page_num = node.get('page_number', 0)
            is_error = node_id in error_ids
            
            # Формируем строку элемента
            type_marker = f"[{node_type.upper()}]"
            page_marker = f" (стр. {page_num})" if page_num > 0 else ""
            content_text = f" {content}" if content else ""
            
            # Добавляем маркер ошибки
            error_marker = ""
            if is_error and node_id in error_info:
                error = error_info[node_id]
                if error.error_type == 'wrong_parent':
                    # Проверяем, что родители действительно разные
                    gt_parent = (error.ground_truth_parent_content or error.ground_truth_parent_id or "").strip()
                    pred_parent = (error.predicted_parent_content or error.predicted_parent_id or "").strip()
                    if gt_parent and pred_parent and gt_parent != pred_parent:
                        error_marker = " ❌ [ОШИБКА: неправильный родитель]"
                    else:
                        # Родители совпадают или один из них пустой - не показываем ошибку
                        is_error = False
                        error_marker = ""
                elif error.error_type == 'missing_parent':
                    error_marker = " ⚠️ [ОШИБКА: отсутствует родитель]"
                elif error.error_type == 'extra_parent':
                    error_marker = " ⚠️ [ОШИБКА: лишний родитель]"
                elif error.error_type in ['missing', 'extra', 'order_mismatch']:
                    error_type_name = {
                        'missing': 'отсутствует элемент',
                        'extra': 'лишний элемент',
                        'order_mismatch': 'неправильный порядок'
                    }.get(error.error_type, error.error_type)
                    # Для "missing" проверяем, может быть это проблема уровня
                    if error.error_type == 'missing':
                        # Если элемент помечен как missing, но есть похожий в predicted,
                        # это скорее проблема уровня, а не отсутствие
                        # Но мы уже отфильтровали такие случаи в analyze_structure_errors
                        error_marker = f" ❌ [ОШИБКА: {error_type_name}]"
                    else:
                        error_marker = f" ❌ [ОШИБКА: {error_type_name}]"
                else:
                    error_marker = f" ❌ [ОШИБКА: {error.error_type}]"
            
            # Формируем строку с переносом
            line = f"{prefix}{connector}{type_marker}{content_text}{page_marker}{error_marker}\n"
            lines.append(line)
            
            # Добавляем детали ошибки, если есть
            if is_error and node_id in error_info:
                error = error_info[node_id]
                if error.error_type == 'wrong_parent':
                    gt_parent = (error.ground_truth_parent_content or error.ground_truth_parent_id or "нет")[:50]
                    pred_parent = (error.predicted_parent_content or error.predicted_parent_id or "нет")[:50]
                    error_detail = f"{prefix}{extension}   └─ ПРАВИЛЬНО: '{gt_parent}' | НАЙДЕНО: '{pred_parent}'\n"
                    lines.append(error_detail)
                elif error.error_type == 'missing_parent':
                    gt_parent = (error.ground_truth_parent_content or error.ground_truth_parent_id or "неизвестен")[:50]
                    error_detail = f"{prefix}{extension}   └─ Должен быть родитель: '{gt_parent}'\n"
                    lines.append(error_detail)
                elif error.error_type == 'extra_parent':
                    pred_parent = (error.predicted_parent_content or error.predicted_parent_id or "неизвестен")[:50]
                    error_detail = f"{prefix}{extension}   └─ Найден лишний родитель: '{pred_parent}'\n"
                    lines.append(error_detail)
            
            # Добавляем детей
            children = sorted(children_map.get(node_id, []), 
                           key=lambda x: nodes_dict.get(x, {}).get('page_number', 0))
            
            for i, child_id in enumerate(children):
                is_last_child = (i == len(children) - 1)
                child_lines = build_tree_markdown(child_id, prefix + extension, is_last_child, visited)
                lines.extend(child_lines)
            
            return lines
        
        # Строим markdown
        markdown_lines = [f"# {title}\n"]
        markdown_lines.append(f"\nВсего элементов: {len(tree_data['nodes'])}\n")
        
        if errors:
            error_count = len(error_ids)
            markdown_lines.append(f"Элементов с ошибками: {error_count}\n")
        
        markdown_lines.append("\n## Структура документа\n\n")
        markdown_lines.append("```\n")
        
        # Строим дерево для каждого корневого узла
        all_visited = set()
        sorted_root_nodes = sorted(root_nodes, key=lambda x: nodes_dict.get(x, {}).get('page_number', 0))
        for i, root_id in enumerate(sorted_root_nodes):
            if root_id not in all_visited:
                is_last_root = (i == len(sorted_root_nodes) - 1)
                tree_lines = build_tree_markdown(root_id, "", is_last_root, all_visited)
                markdown_lines.extend(tree_lines)
        
        markdown_lines.append("```\n")
        
        # Добавляем легенду
        markdown_lines.append("\n## Легенда\n\n")
        markdown_lines.append("- `[TYPE]` - тип элемента\n")
        markdown_lines.append("- `❌` - ошибка иерархии\n")
        markdown_lines.append("- `⚠️` - предупреждение\n")
        
        # Добавляем статистику по ошибкам
        if errors:
            markdown_lines.append("\n## Статистика ошибок\n\n")
            error_types = defaultdict(int)
            for error in errors:
                error_types[error.error_type] += 1
            
            for error_type, count in sorted(error_types.items()):
                error_type_name = {
                    'wrong_parent': 'Неправильный родитель',
                    'missing_parent': 'Отсутствует родитель',
                    'extra_parent': 'Лишний родитель'
                }.get(error_type, error_type)
                markdown_lines.append(f"- **{error_type_name}**: {count}\n")
        
        # Сохраняем markdown
        with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
            f.writelines(markdown_lines)
        
        print(f"    Создан markdown файл: {output_path}")
        return True
    except Exception as e:
        print(f"Ошибка при создании markdown дерева: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_teds_visualizations_and_report(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str],
    document_id: str,
    document_teds: float,
    hierarchy_teds: float,
    ordering_accuracy: float,
    output_dir: Path,
    document_format: Optional[str] = None
) -> Tuple[Optional[Path], List[Path]]:
    """
    Создаёт визуализации и JSON отчет для анализа TEDS.
    
    Args:
        predicted: Список предсказанных элементов
        ground_truth: Список элементов из GT
        matches: Словарь сопоставлений pred_id -> gt_id
        document_id: ID документа
        document_teds: TEDS для документа
        hierarchy_teds: TEDS для иерархии
        ordering_accuracy: Точность порядка
        output_dir: Директория для сохранения результатов
        document_format: Формат документа ('docx', 'pdf', и т.д.)
    
    Returns:
        Tuple (json_path, [image_paths])
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Создаём детальный анализ
    analysis = create_detailed_teds_analysis(
        predicted=predicted,
        ground_truth=ground_truth,
        matches=matches,
        document_id=document_id,
        document_teds=document_teds,
        hierarchy_teds=hierarchy_teds,
        ordering_accuracy=ordering_accuracy,
        document_format=document_format
    )
    
    # Сохраняем JSON отчет
    json_path = output_dir / f"{document_id}_teds_analysis.json"
    save_teds_analysis_json(analysis, json_path)
    
    # Создаём маппинги для сопоставления ошибок с ID в деревьях
    # Для predicted_tree: ошибки должны быть сопоставлены с pred_id
    # Для ground_truth_tree: ошибки уже имеют gt_id
    
    # Создаём обратный маппинг gt_id -> pred_id
    gt_to_pred = {gt_id: pred_id for pred_id, gt_id in matches.items()}
    
    # Создаём маппинг gt_id -> pred_id для ошибок в predicted_tree
    pred_errors_for_predicted_tree = []
    for error in analysis.hierarchy_errors:
        # Находим pred_id для этого gt_id
        pred_id = gt_to_pred.get(error.element_id)
        
        if pred_id:
            # Создаём ошибку с pred_id для predicted_tree
            pred_error = HierarchyError(
                element_id=pred_id,  # Используем pred_id для predicted_tree
                element_type=error.element_type,
                element_content_preview=error.element_content_preview,
                predicted_parent_id=error.predicted_parent_id,
                predicted_parent_content=error.predicted_parent_content,
                ground_truth_parent_id=error.ground_truth_parent_id,
                ground_truth_parent_content=error.ground_truth_parent_content,
                page_number=error.page_number,
                error_type=error.error_type
            )
            pred_errors_for_predicted_tree.append(pred_error)
        # Если элемент не сопоставлен, но есть ошибка - это тоже важно показать
        # Но в predicted_tree его не будет, так что пропускаем
    
    # Отладочная информация
    print(f"  Всего ошибок иерархии: {len(analysis.hierarchy_errors)}")
    print(f"  Ошибок для predicted_tree: {len(pred_errors_for_predicted_tree)}")
    if len(analysis.hierarchy_errors) > 0 and len(pred_errors_for_predicted_tree) == 0:
        print(f"  ВНИМАНИЕ: Ошибки не сопоставлены! Примеры GT ID из ошибок: {[e.element_id for e in analysis.hierarchy_errors[:3]]}")
        print(f"  Примеры matches: {list(matches.items())[:5]}")
    
    # Объединяем hierarchy_errors и structure_errors для полного списка ошибок в GT дереве
    all_errors_for_gt = analysis.hierarchy_errors.copy()
    
    # Добавляем structure_errors как hierarchy_errors для отображения
    for struct_error in analysis.structure_errors:
        # Все structure_errors должны быть отображены
        hierarchy_error = HierarchyError(
            element_id=struct_error.element_id,
            element_type=struct_error.element_type,
            element_content_preview=struct_error.element_content_preview,
            predicted_parent_id=None,
            predicted_parent_content=None,
            ground_truth_parent_id=None,
            ground_truth_parent_content=None,
            page_number=struct_error.page_number,
            error_type=struct_error.error_type
        )
        all_errors_for_gt.append(hierarchy_error)
    
    # Создаём визуализации
    image_paths = []
    markdown_paths = []
    
    # Markdown визуализация предсказанного дерева
    pred_tree_md_path = output_dir / f"{document_id}_predicted_tree.md"
    if create_tree_markdown(
        tree_data=analysis.predicted_tree,
        title=f"Предсказанная иерархия: {document_id}",
        output_path=pred_tree_md_path,
        errors=pred_errors_for_predicted_tree,
        matches=matches
    ):
        markdown_paths.append(pred_tree_md_path)
    
    # Markdown визуализация GT дерева
    # В ground truth дереве НЕ показываем ошибки, так как это эталон
    # Ошибки показываются только в predicted_tree для сравнения
    gt_tree_md_path = output_dir / f"{document_id}_ground_truth_tree.md"
    if create_tree_markdown(
        tree_data=analysis.ground_truth_tree,
        title=f"Эталонная иерархия: {document_id}",
        output_path=gt_tree_md_path,
        errors=None  # Не показываем ошибки в эталонном дереве
    ):
        markdown_paths.append(gt_tree_md_path)
    
    # PNG визуализация предсказанного дерева
    pred_tree_path = output_dir / f"{document_id}_predicted_tree.png"
    if visualize_hierarchy_tree(
        tree_data=analysis.predicted_tree,
        title=f"Предсказанная иерархия: {document_id}",
        output_path=pred_tree_path,
        errors=pred_errors_for_predicted_tree,
        matches=matches
    ):
        image_paths.append(pred_tree_path)
    
    # PNG визуализация GT дерева
    # В ground truth дереве НЕ показываем ошибки, так как это эталон
    gt_tree_path = output_dir / f"{document_id}_ground_truth_tree.png"
    if visualize_hierarchy_tree(
        tree_data=analysis.ground_truth_tree,
        title=f"Эталонная иерархия: {document_id}",
        output_path=gt_tree_path,
        errors=None  # Не показываем ошибки в эталонном дереве
    ):
        image_paths.append(gt_tree_path)
    
    return json_path, image_paths + markdown_paths

"""
Скрипт для оценки качества парсинга документов через dedoc по ground truth аннотациям.

Использует dedoc для парсинга PDF файлов и вычисляет метрики:
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

# Попытка импортировать requests для Docker API
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

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

def calculate_cer(reference: str, hypothesis: str) -> float:
    """Вычисляет Character Error Rate."""
    if not reference:
        return 1.0 if hypothesis else 0.0
    
    ref_norm = normalize_content(reference)
    hyp_norm = normalize_content(hypothesis)
    
    # Простая реализация CER через расстояние Левенштейна
    def levenshtein_distance(s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    distance = levenshtein_distance(ref_norm, hyp_norm)
    return distance / len(ref_norm) if ref_norm else 1.0

def calculate_wer(reference: str, hypothesis: str) -> float:
    """Вычисляет Word Error Rate."""
    if not reference:
        return 1.0 if hypothesis else 0.0
    
    ref_words = normalize_content(reference).split()
    hyp_words = normalize_content(hypothesis).split()
    
    if not ref_words:
        return 1.0 if hyp_words else 0.0
    
    # Простая реализация WER через расстояние Левенштейна на словах
    def word_levenshtein_distance(words1: List[str], words2: List[str]) -> int:
        if len(words1) < len(words2):
            return word_levenshtein_distance(words2, words1)
        if len(words2) == 0:
            return len(words1)
        
        previous_row = range(len(words2) + 1)
        for i, w1 in enumerate(words1):
            current_row = [i + 1]
            for j, w2 in enumerate(words2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (w1 != w2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    distance = word_levenshtein_distance(ref_words, hyp_words)
    return distance / len(ref_words) if ref_words else 1.0

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
    """Вычисляет точность порядка элементов."""
    if not matches:
        return 0.0
    
    # Создаем списки индексов для сопоставленных элементов
    pred_indices = []
    gt_indices = []
    
    for i, pred_elem in enumerate(predicted):
        if pred_elem.id in matches:
            pred_indices.append(i)
            gt_id = matches[pred_elem.id]
            gt_idx = next((j for j, gt_elem in enumerate(ground_truth) if gt_elem['id'] == gt_id), None)
            if gt_idx is not None:
                gt_indices.append(gt_idx)
    
    if len(pred_indices) != len(gt_indices) or len(pred_indices) < 2:
        return 1.0 if len(pred_indices) <= 1 else 0.0
    
    # Проверяем, сохраняется ли порядок
    correct_order = 0
    total_pairs = 0
    
    for i in range(len(pred_indices) - 1):
        for j in range(i + 1, len(pred_indices)):
            total_pairs += 1
            if (pred_indices[i] < pred_indices[j]) == (gt_indices[i] < gt_indices[j]):
                correct_order += 1
    
    return correct_order / total_pairs if total_pairs > 0 else 1.0

def calculate_hierarchy_accuracy_simple(
    predicted: List[Element],
    ground_truth: List[Dict[str, Any]],
    matches: Dict[str, str]
) -> float:
    """Вычисляет точность иерархии элементов."""
    if not matches:
        return 0.0
    
    correct_hierarchy = 0
    total_matched = 0
    
    # Создаем словари для быстрого доступа
    pred_dict = {elem.id: elem for elem in predicted}
    gt_dict = {elem['id']: elem for elem in ground_truth}
    
    for pred_id, gt_id in matches.items():
        pred_elem = pred_dict.get(pred_id)
        gt_elem = gt_dict.get(gt_id)
        
        if not pred_elem or not gt_elem:
            continue
        
        total_matched += 1
        
        # Проверяем parent_id
        pred_parent = pred_elem.parent_id
        gt_parent = gt_elem.get('parent_id')
        
        if pred_parent is None and gt_parent is None:
            correct_hierarchy += 1
        elif pred_parent and gt_parent:
            # Проверяем, сопоставлены ли родители
            pred_parent_gt = matches.get(pred_parent)
            if pred_parent_gt == gt_parent:
                correct_hierarchy += 1
    
    return correct_hierarchy / total_matched if total_matched > 0 else 0.0

def dedoc_structure_to_element_type(structure_type: str) -> ElementType:
    """Преобразует тип структуры dedoc в ElementType."""
    structure_lower = structure_type.lower()
    
    if 'title' in structure_lower:
        return ElementType.TITLE
    elif 'heading' in structure_lower or 'header' in structure_lower:
        # Пытаемся определить уровень заголовка
        if '1' in structure_type or 'first' in structure_lower:
            return ElementType.HEADER_1
        elif '2' in structure_type or 'second' in structure_lower:
            return ElementType.HEADER_2
        elif '3' in structure_type or 'third' in structure_lower:
            return ElementType.HEADER_3
        elif '4' in structure_type:
            return ElementType.HEADER_4
        elif '5' in structure_type:
            return ElementType.HEADER_5
        elif '6' in structure_type:
            return ElementType.HEADER_6
        else:
            return ElementType.HEADER_1  # По умолчанию
    elif 'table' in structure_lower:
        return ElementType.TABLE
    elif 'list' in structure_lower:
        return ElementType.LIST_ITEM
    elif 'image' in structure_lower or 'picture' in structure_lower:
        return ElementType.IMAGE
    elif 'formula' in structure_lower or 'equation' in structure_lower:
        return ElementType.FORMULA
    elif 'caption' in structure_lower:
        return ElementType.CAPTION
    elif 'footnote' in structure_lower:
        return ElementType.FOOTNOTE
    elif 'code' in structure_lower:
        return ElementType.CODE_BLOCK
    else:
        return ElementType.TEXT

def parse_dedoc_structure(
    dedoc_result: Dict[str, Any],
    document_id: str
) -> List[Element]:
    """
    Парсит результат dedoc в список элементов.
    
    Структура dedoc:
    {
        "content": {
            "structure": {
                "node_id": "0",
                "text": "",
                "metadata": {"paragraph_type": "root", "page_id": 0},
                "subparagraphs": [...]
            }
        }
    }
    
    Args:
        dedoc_result: Результат парсинга dedoc
        document_id: ID документа
    
    Returns:
        Список элементов
    """
    elements = []
    element_counter = 0
    
    # Dedoc возвращает структурированные данные
    if not isinstance(dedoc_result, dict):
        print(f"  [WARNING] dedoc_result не является словарем: {type(dedoc_result)}")
        return elements
    
    # Извлекаем структуру из content.structure
    content = dedoc_result.get('content', {})
    if not isinstance(content, dict):
        print(f"  [WARNING] content не является словарем: {type(content)}")
        return elements
    
    structure = content.get('structure')
    if not structure or not isinstance(structure, dict):
        print(f"  [WARNING] structure не найден или не является словарем")
        return elements
    
    # Создаем словарь для отслеживания parent_id
    id_mapping = {}  # dedoc_node_id -> our_id
    
    def get_element_type_from_paragraph_type(paragraph_type: str, text: str) -> ElementType:
        """Определяет тип элемента на основе paragraph_type и текста."""
        if not paragraph_type or paragraph_type == "root":
            # Пытаемся определить по тексту
            text_lower = text.lower().strip()
            if any(keyword in text_lower for keyword in ['abstract', 'introduction', 'conclusion']):
                return ElementType.HEADER_1
            return ElementType.TEXT
        
        paragraph_type_lower = paragraph_type.lower()
        
        # Заголовки
        if 'header' in paragraph_type_lower or 'title' in paragraph_type_lower:
            if '1' in paragraph_type_lower or 'title' in paragraph_type_lower:
                return ElementType.HEADER_1
            elif '2' in paragraph_type_lower:
                return ElementType.HEADER_2
            elif '3' in paragraph_type_lower:
                return ElementType.HEADER_3
            elif '4' in paragraph_type_lower:
                return ElementType.HEADER_4
            elif '5' in paragraph_type_lower:
                return ElementType.HEADER_5
            elif '6' in paragraph_type_lower:
                return ElementType.HEADER_6
            return ElementType.HEADER_1
        
        # Списки
        if 'list' in paragraph_type_lower:
            return ElementType.LIST_ITEM
        
        # Таблицы
        if 'table' in paragraph_type_lower:
            return ElementType.TABLE
        
        # По умолчанию - текст
        return ElementType.TEXT
    
    def process_node(node: Dict[str, Any], parent_id: Optional[str] = None) -> None:
        nonlocal element_counter
        
        # Проверяем, что node - словарь
        if not isinstance(node, dict):
            return
        
        # Извлекаем данные узла
        node_id = node.get('node_id')
        text = node.get('text', '')
        metadata = node.get('metadata', {})
        paragraph_type = metadata.get('paragraph_type', 'raw_text')
        page_id = metadata.get('page_id', 0)
        
        # Пропускаем корневой узел без текста
        if paragraph_type == 'root' and not text.strip():
            # Обрабатываем только дочерние элементы
            subparagraphs = node.get('subparagraphs', [])
            for subpara in subparagraphs:
                process_node(subpara, parent_id)
            return
        
        # Определяем тип элемента
        elem_type = get_element_type_from_paragraph_type(paragraph_type, text)
        
        # Создаем элемент только если есть текст
        if text.strip():
            elem_id = f"dedoc_elem_{element_counter:04d}"
            element_counter += 1
            
            # Сохраняем маппинг ID
            if node_id:
                id_mapping[node_id] = elem_id
            
            # Определяем parent_id
            our_parent_id = None
            if parent_id and parent_id in id_mapping:
                our_parent_id = id_mapping[parent_id]
            
            element = Element(
                id=elem_id,
                type=elem_type,
                content=text.strip(),
                parent_id=our_parent_id,
                metadata={
                    'source': 'dedoc',
                    'document_id': document_id,
                    'dedoc_node_id': node_id,
                    'dedoc_paragraph_type': paragraph_type,
                    'page_id': page_id,
                }
            )
            
            elements.append(element)
        
        # Обрабатываем дочерние элементы (subparagraphs)
        subparagraphs = node.get('subparagraphs', [])
        current_parent_id = node_id if node_id else parent_id
        for subpara in subparagraphs:
            process_node(subpara, current_parent_id)
    
    # Обрабатываем корневой узел структуры
    process_node(structure)
    
    # Если структура пустая, пытаемся извлечь текст напрямую
    if not elements:
        # Выводим отладочную информацию о структуре ответа
        print(f"  [DEBUG] Структура ответа dedoc: ключи = {list(dedoc_result.keys())[:10]}")
        
        text = dedoc_result.get('text', '') or dedoc_result.get('content', '')
        # Проверяем, что text - это строка, а не словарь
        if isinstance(text, dict):
            # Если text - словарь, пытаемся извлечь строку из него
            print(f"  [DEBUG] text является словарем: {list(text.keys())[:5]}")
            text = text.get('text', '') or text.get('content', '') or str(text)
        elif not isinstance(text, str):
            # Если это не строка и не словарь, преобразуем в строку
            print(f"  [DEBUG] text имеет тип: {type(text)}")
            text = str(text) if text else ''
        
        if text and isinstance(text, str):
            # Разбиваем текст на параграфы
            paragraphs = text.split('\n\n')
            for para in paragraphs:
                if para.strip():
                    elem_id = f"dedoc_elem_{element_counter:04d}"
                    element_counter += 1
                    elements.append(Element(
                        id=elem_id,
                        type=ElementType.TEXT,
                        content=para.strip(),
                        parent_id=None,
                        metadata={'source': 'dedoc', 'document_id': document_id}
                    ))
        else:
            print(f"  [WARNING] Не удалось извлечь текст из ответа dedoc")
    
    return elements

def check_docker_dedoc_available() -> bool:
    """Проверяет, доступен ли dedoc через Docker API."""
    if not REQUESTS_AVAILABLE:
        return False
    
    # Пробуем несколько вариантов проверки
    endpoints_to_try = [
        'http://localhost:1231/api/v1/health',
        'http://localhost:1231/health',
        'http://localhost:1231/',
    ]
    
    for endpoint in endpoints_to_try:
        try:
            response = requests.get(endpoint, timeout=2)
            # Если получили любой ответ (не 404), значит сервер работает
            if response.status_code != 404:
                return True
        except requests.exceptions.ConnectionError:
            # Сервер не доступен
            continue
        except Exception:
            # Другие ошибки - пропускаем
            continue
    
    # Если ничего не сработало, пробуем напрямую parse endpoint
    try:
        # Просто проверяем, что порт открыт и сервер отвечает
        response = requests.get('http://localhost:1231/api/v1/parse', timeout=1)
        # Если получили ответ от сервера (даже 404 или 405), значит сервер работает
        # 404 = Not Found (endpoint не поддерживает GET, что нормально для POST endpoint)
        # 405 = Method Not Allowed (сервер работает, но метод не разрешен)
        # Любой ответ означает, что сервер работает
        return True
    except requests.exceptions.ConnectionError:
        # ConnectionError означает, что сервер недоступен
        return False
    except Exception:
        # Если получили другой ответ (не ConnectionError), значит сервер работает
        return True

def parse_with_docker_dedoc(pdf_path: Path) -> Dict[str, Any]:
    """Парсит документ через Docker API dedoc."""
    if not REQUESTS_AVAILABLE:
        raise ImportError("requests не установлен. Установите: pip install requests")
    
    api_url = 'http://localhost:1231/upload'
    
    with open(pdf_path, 'rb') as f:
        files = {'file': (pdf_path.name, f, 'application/pdf')}
        # Dedoc может требовать параметры в другом формате
        # Попробуем без параметров сначала
        response = requests.post(api_url, files=files, timeout=300)
        response.raise_for_status()
        
        return response.json()

def parse_with_local_dedoc(pdf_path: Path) -> Dict[str, Any]:
    """Парсит документ через локальную установку dedoc."""
    # Импортируем dedoc
    # Попробуем разные варианты импорта
    try:
        from dedoc import DedocManager
    except ImportError:
        try:
            from dedoc.dedoc_manager import DedocManager
        except ImportError:
            try:
                import dedoc
                DedocManager = dedoc.DedocManager
            except (ImportError, AttributeError):
                raise ImportError("Не удалось импортировать DedocManager. Установите dedoc: pip install dedoc")
    
    # Создаем менеджер dedoc
    manager = DedocManager()
    
    # Парсим документ
    with open(pdf_path, 'rb') as f:
        file_content = f.read()
    
    # Пытаемся разные варианты вызова API
    try:
        result = manager.parse(
            file_content=file_content,
            file_name=pdf_path.name,
            parameters={}
        )
    except TypeError:
        # Возможно, нужен другой формат параметров
        try:
            result = manager.parse(file_content=file_content, file_name=pdf_path.name)
        except Exception:
            # Попробуем через путь к файлу
            try:
                result = manager.parse_file(file_path=str(pdf_path))
            except Exception as e:
                print(f"  [WARNING] Не удалось распарсить через стандартный API. Ошибка: {e}")
                raise
    
    return result

def load_saved_dedoc_result(dedoc_output_dir: Path, document_id: str) -> Optional[Dict[str, Any]]:
    """Загружает сохраненный результат dedoc из JSON файла."""
    json_path = dedoc_output_dir / f"{document_id}_dedoc.json"
    if json_path.exists():
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def process_pdf_with_dedoc(
    pdf_path: Path,
    annotation_path: Path,
    dedoc_output_dir: Optional[Path] = None,
    use_saved: bool = False
) -> 'DocumentMetrics':
    """
    Обрабатывает один PDF файл через dedoc и вычисляет метрики.
    
    Сначала пытается использовать Docker API, затем локальную установку.
    
    Args:
        pdf_path: Путь к PDF файлу
        annotation_path: Путь к ground truth аннотации
    
    Returns:
        DocumentMetrics с результатами
    """
    start_time = time.time()
    document_id = pdf_path.stem
    
    try:
        # Если есть сохраненные результаты, используем их
        if use_saved and dedoc_output_dir:
            saved_result = load_saved_dedoc_result(dedoc_output_dir, document_id)
            if saved_result:
                print(f"  [INFO] Используются сохраненные результаты dedoc")
                result = saved_result
            else:
                raise FileNotFoundError(f"Сохраненный результат не найден для {document_id}")
        else:
            # Сначала пытаемся использовать Docker API
            use_docker = check_docker_dedoc_available()
            
            if use_docker:
                print(f"  [INFO] Используется Docker API dedoc")
                result = parse_with_docker_dedoc(pdf_path)
            else:
                print(f"  [INFO] Используется локальная установка dedoc")
                result = parse_with_local_dedoc(pdf_path)
        
        # Преобразуем результат в элементы
        predicted = parse_dedoc_structure(result, document_id)
        
    except ImportError as e:
        print(f"  [ERROR] dedoc не установлен. Установите через: pip install dedoc")
        print(f"  [ERROR] Или запустите Docker контейнер: docker run -p 1231:1231 dedocproject/dedoc")
        print(f"  [ERROR] Детали: {e}")
        raise
    except Exception as e:
        print(f"  [ERROR] Ошибка при парсинге через dedoc: {e}")
        import traceback
        traceback.print_exc()
        raise
    
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

@dataclass
class DocumentMetrics:
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

def find_matching_annotation(pdf_path: Path, annotations_dir: Path) -> Optional[Path]:
    """Находит соответствующую аннотацию для PDF файла."""
    pdf_name = pdf_path.stem
    
    # Пытаемся найти аннотацию с разными суффиксами
    possible_names = [
        f"{pdf_name}.pdf_annotation.json",
        f"{pdf_name}_pdf_annotation.json",
        f"{pdf_name}_annotation.json",
    ]
    
    for name in possible_names:
        annotation_path = annotations_dir / name
        if annotation_path.exists():
            return annotation_path
    
    return None

def main():
    """Основная функция для обработки всех PDF файлов."""
    script_dir = Path(__file__).parent
    
    # Пути к файлам
    test_files_dir = script_dir / "test_files_for_metrics"
    annotations_dir = script_dir / "annotations"
    output_file = script_dir / "dedoc_metrics.json"
    dedoc_output_dir = script_dir / "dedoc_output"
    
    # Проверяем, есть ли сохраненные результаты
    use_saved_results = dedoc_output_dir.exists() and any(dedoc_output_dir.glob("*_dedoc.json"))
    
    if use_saved_results:
        print("[INFO] Найдены сохраненные результаты dedoc")
        print("[INFO] Используются результаты из папки dedoc_output")
        print("[INFO] Для переобработки запустите: python run_dedoc_pipeline.py")
    else:
        # Проверяем наличие venv_dedoc
        venv_dedoc = script_dir / "venv_dedoc"
        if venv_dedoc.exists():
            print(f"[INFO] Найдено виртуальное окружение: {venv_dedoc}")
            print(f"[INFO] Для использования активируйте его:")
            print(f"      Windows: venv_dedoc\\Scripts\\activate")
            print(f"      Linux/Mac: source venv_dedoc/bin/activate")
            print(f"      Или запустите скрипт через: venv_dedoc\\Scripts\\python.exe evaluate_dedoc.py")
    
    # Находим все PDF файлы
    pdf_files = list(test_files_dir.glob("*.pdf"))
    
    if not pdf_files:
        print(f"[ERROR] PDF файлы не найдены в {test_files_dir}")
        return
    
    print(f"Найдено {len(pdf_files)} PDF файлов")
    
    results = {}
    all_metrics = []
    
    # Обрабатываем каждый файл
    for i, pdf_file in enumerate(pdf_files, 1):
        print(f"\n[{i}/{len(pdf_files)}] Обработка: {pdf_file.name}")
        
        # Находим соответствующую аннотацию
        annotation_path = find_matching_annotation(pdf_file, annotations_dir)
        
        if not annotation_path:
            print(f"  [ERROR] Аннотация не найдена для {pdf_file.name}")
            continue
        
        print(f"  Используется аннотация: {annotation_path.name}")
        
        try:
            metrics = process_pdf_with_dedoc(
                pdf_file, 
                annotation_path,
                dedoc_output_dir=dedoc_output_dir if use_saved_results else None,
                use_saved=use_saved_results
            )
            all_metrics.append(metrics)
            
            results[pdf_file.name] = {
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
        summary = {
            'total_files': len(all_metrics),
            'avg_cer': sum(m.cer for m in all_metrics) / len(all_metrics),
            'avg_wer': sum(m.wer for m in all_metrics) / len(all_metrics),
            'avg_ordering_accuracy': sum(m.ordering_accuracy for m in all_metrics) / len(all_metrics),
            'avg_hierarchy_accuracy': sum(m.hierarchy_accuracy for m in all_metrics) / len(all_metrics),
            'avg_document_teds': sum(m.document_teds for m in all_metrics) / len(all_metrics),
            'avg_hierarchy_teds': sum(m.hierarchy_teds for m in all_metrics) / len(all_metrics),
        }
        
        results['_summary'] = summary
        
        print("\n" + "="*60)
        print("ИТОГОВЫЕ МЕТРИКИ:")
        print("="*60)
        print(f"Средний CER: {summary['avg_cer']:.4f} ({summary['avg_cer']*100:.2f}%)")
        print(f"Средний WER: {summary['avg_wer']:.4f} ({summary['avg_wer']*100:.2f}%)")
        print(f"Средняя Ordering accuracy: {summary['avg_ordering_accuracy']:.4f} ({summary['avg_ordering_accuracy']*100:.2f}%)")
        print(f"Средняя Hierarchy accuracy: {summary['avg_hierarchy_accuracy']:.4f} ({summary['avg_hierarchy_accuracy']*100:.2f}%)")
        print(f"Средний Document TEDS: {summary['avg_document_teds']:.4f}")
        print(f"Средний Hierarchy TEDS: {summary['avg_hierarchy_teds']:.4f}")
    
    # Сохраняем результаты
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\nРезультаты сохранены в: {output_file}")

if __name__ == "__main__":
    main()

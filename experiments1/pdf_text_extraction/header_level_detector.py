"""
Автоматическое определение уровней заголовков на основе:
1. Паттернов нумерации (1, 1.1, 1.1.1, A, A.1, I, I.1 и т.д.)
2. Размера шрифта и форматирования
3. Иерархической структуры документа
4. Валидации логики иерархии
"""

import re
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


class NumberingPattern:
    """Класс для анализа паттернов нумерации заголовков."""
    
    # Паттерны для разных типов нумерации
    PATTERNS = {
        'arabic_dot': r'^(\d+)\.?\s+(.+)$',  # "1. " или "1 "
        'arabic_nested': r'^(\d+(?:\.\d+)+)\s+(.+)$',  # "1.1", "1.1.1"
        'roman_dot': r'^([IVX]+)\.?\s+(.+)$',  # "I. " или "I "
        'roman_nested': r'^([IVX]+(?:\.\d+)+)\s+(.+)$',  # "I.1", "I.1.1"
        'letter_dot': r'^([A-Z])\.?\s+(.+)$',  # "A. " или "A "
        'letter_nested': r'^([A-Z](?:\.\d+)+)\s+(.+)$',  # "A.1", "A.1.1"
        # ВАЖНО: без точки этот паттерн слишком широкий и ловит любые строки, начинающиеся с "a "
        # (например: "a maximum allowed ..."). Поэтому требуем явный разделитель.
        'letter_lower_dot': r'^([a-z])[\.\)]\s+(.+)$',  # "a. " или "a) "
        'parentheses': r'^\((\d+)\)\s+(.+)$',  # "(1) "
        'bracket': r'^(\d+)\)\s+(.+)$',  # "1) "
    }
    
    @staticmethod
    def extract_numbering(text: str) -> Optional[Tuple[str, str, int]]:
        """
        Извлекает нумерацию из текста заголовка.
        
        Args:
            text: Текст заголовка
            
        Returns:
            Tuple (номер, текст_без_номера, глубина_вложенности) или None
            Например: ("1.1", "Section name", 2)
        """
        text = text.strip()
        
        # Проверяем паттерны по порядку приоритета
        for pattern_name, pattern in NumberingPattern.PATTERNS.items():
            match = re.match(pattern, text)
            if match:
                numbering = match.group(1)
                content = match.group(2) if len(match.groups()) > 1 else text
                
                # Определяем глубину вложенности
                depth = NumberingPattern._calculate_depth(numbering, pattern_name)
                
                return (numbering, content.strip(), depth)
        
        return None
    
    @staticmethod
    def _calculate_depth(numbering: str, pattern_type: str) -> int:
        """Вычисляет глубину вложенности нумерации."""
        if 'nested' in pattern_type:
            # Для вложенной нумерации считаем количество точек + 1
            return numbering.count('.') + 1
        elif pattern_type in ['arabic_dot', 'roman_dot', 'letter_dot', 'letter_lower_dot']:
            return 1
        elif pattern_type in ['parentheses', 'bracket']:
            return 1
        else:
            return 1
    
    @staticmethod
    def get_numbering_type(numbering: str) -> str:
        """
        Определяет тип нумерации.
        
        Returns:
            'arabic', 'roman', 'letter', 'letter_lower', 'unknown'
        """
        if re.match(r'^\d+', numbering):
            return 'arabic'
        elif re.match(r'^[IVX]+', numbering):
            return 'roman'
        elif re.match(r'^[A-Z]', numbering):
            return 'letter'
        elif re.match(r'^[a-z]', numbering):
            return 'letter_lower'
        else:
            return 'unknown'


class HeaderLevelDetector:
    """Детектор уровней заголовков на основе анализа структуры."""
    
    def __init__(self):
        """Инициализация детектора."""
        self.headers: List[Dict] = []
        self.numbering_types: Dict[int, str] = {}  # {level: numbering_type}
    
    def detect_levels(self, headers: List[Dict]) -> List[Dict]:
        """
        Определяет уровни заголовков на основе анализа структуры.
        
        Args:
            headers: Список заголовков с базовыми метаданными
                   (должны содержать: 'text', 'font_size', 'page_num')
        
        Returns:
            Список заголовков с определенными уровнями
        """
        if not headers:
            return []
        
        self.headers = headers.copy()
        
        # Шаг 1: Анализируем нумерацию для каждого заголовка
        for header in self.headers:
            numbering_info = NumberingPattern.extract_numbering(header['text'])
            if numbering_info:
                numbering, content, depth = numbering_info
                header['numbering'] = numbering
                header['numbering_content'] = content
                header['numbering_depth'] = depth
                header['numbering_type'] = NumberingPattern.get_numbering_type(numbering)
            else:
                header['numbering'] = None
                header['numbering_depth'] = 0
                header['numbering_type'] = None
        
        # Шаг 2: Определяем уровни на основе нумерации
        self._assign_levels_by_numbering()
        
        # Шаг 3: Корректируем уровни на основе размера шрифта
        self._adjust_levels_by_font_size()
        
        # Шаг 4: Валидируем и исправляем иерархию
        self._validate_and_fix_hierarchy()
        
        return self.headers
    
    def _assign_levels_by_numbering(self):
        """Присваивает уровни на основе нумерации."""
        # Группируем заголовки по типам нумерации
        numbered_headers = [h for h in self.headers if h.get('numbering')]
        unnumbered_headers = [h for h in self.headers if not h.get('numbering')]
        
        # Для пронумерованных заголовков используем глубину нумерации
        for header in numbered_headers:
            depth = header.get('numbering_depth', 0)
            if depth > 0:
                # Уровень = глубина нумерации (1.1.1 -> level 3)
                header['level'] = depth
                # Сохраняем тип нумерации для уровня
                if depth not in self.numbering_types:
                    self.numbering_types[depth] = header.get('numbering_type', 'unknown')
        
        # Для непронумерованных заголовков используем размер шрифта
        if unnumbered_headers:
            # Вычисляем средний размер шрифта для пронумерованных заголовков каждого уровня
            level_font_sizes = defaultdict(list)
            for header in numbered_headers:
                level = header.get('level')
                if level and 'font_size' in header:
                    level_font_sizes[level].append(header['font_size'])
            
            # Вычисляем средние размеры шрифтов для каждого уровня
            avg_font_sizes = {}
            for level, sizes in level_font_sizes.items():
                if sizes:
                    avg_font_sizes[level] = sum(sizes) / len(sizes)
            
            # Присваиваем уровни непронумерованным заголовкам
            for header in unnumbered_headers:
                font_size = header.get('font_size', 0)
                if not avg_font_sizes:
                    # Если нет пронумерованных заголовков, используем простую эвристику
                    header['level'] = self._estimate_level_by_font_size_only(header)
                else:
                    # Находим ближайший уровень по размеру шрифта
                    closest_level = min(
                        avg_font_sizes.keys(),
                        key=lambda l: abs(avg_font_sizes[l] - font_size)
                    )
                    header['level'] = closest_level
    
    def _estimate_level_by_font_size_only(self, header: Dict) -> int:
        """Оценивает уровень только по размеру шрифта (если нет нумерации)."""
        font_size = header.get('font_size', 0)
        
        # Вычисляем средний размер шрифта всех заголовков
        all_sizes = [h.get('font_size', 0) for h in self.headers if h.get('font_size', 0) > 0]
        if not all_sizes:
            return 1
        
        avg_size = sum(all_sizes) / len(all_sizes)
        size_ratio = font_size / avg_size if avg_size > 0 else 1.0
        
        if size_ratio >= 1.5:
            return 1
        elif size_ratio >= 1.3:
            return 2
        elif size_ratio >= 1.1:
            return 3
        else:
            return 4
    
    def _adjust_levels_by_font_size(self):
        """Корректирует уровни на основе размера шрифта."""
        # Группируем заголовки по текущим уровням
        level_groups = defaultdict(list)
        for header in self.headers:
            level = header.get('level', 1)
            level_groups[level].append(header)
        
        # Вычисляем средние размеры шрифтов для каждого уровня
        level_avg_sizes = {}
        for level, headers in level_groups.items():
            sizes = [h.get('font_size', 0) for h in headers if h.get('font_size', 0) > 0]
            if sizes:
                level_avg_sizes[level] = sum(sizes) / len(sizes)
        
        # Если есть явные аномалии (заголовок уровня 3 больше уровня 1), корректируем
        if len(level_avg_sizes) > 1:
            sorted_levels = sorted(level_avg_sizes.keys())
            for i in range(len(sorted_levels) - 1):
                level1 = sorted_levels[i]
                level2 = sorted_levels[i + 1]
                
                # Если уровень 2 больше уровня 1, это аномалия
                if level_avg_sizes[level2] > level_avg_sizes[level1] * 1.1:
                    # Корректируем только если нет нумерации (нумерация имеет приоритет)
                    for header in level_groups[level2]:
                        if not header.get('numbering'):
                            # Возможно, это должен быть более высокий уровень
                            header['level'] = level1
    
    def _validate_and_fix_hierarchy(self):
        """Валидирует и исправляет иерархию заголовков."""
        # Сортируем заголовки по странице и позиции
        sorted_headers = sorted(
            self.headers,
            key=lambda h: (h.get('page_num', 0), h.get('bbox', [0])[1] if h.get('bbox') else 0)
        )
        
        # Проверяем последовательность уровней
        previous_level = None
        for i, header in enumerate(sorted_headers):
            current_level = header.get('level', 1)
            
            if previous_level is not None:
                # Правило: уровень не может "прыгать" более чем на 1
                # (не может быть HEADER_1 -> HEADER_3, должно быть HEADER_1 -> HEADER_2 -> HEADER_3)
                if current_level > previous_level + 1:
                    # Исправляем: устанавливаем промежуточный уровень
                    header['level'] = previous_level + 1
                    current_level = header['level']
            
            previous_level = current_level
        
        # Обновляем уровни в исходном списке
        for i, header in enumerate(self.headers):
            # Находим соответствующий заголовок в отсортированном списке
            for sorted_header in sorted_headers:
                if (sorted_header.get('text') == header.get('text') and
                    sorted_header.get('page_num') == header.get('page_num')):
                    header['level'] = sorted_header.get('level', 1)
                    break
    
    def get_header_hierarchy(self) -> Dict:
        """
        Строит иерархическое дерево заголовков.
        
        Returns:
            Дерево заголовков в виде словаря
        """
        # Сортируем заголовки по позиции
        sorted_headers = sorted(
            self.headers,
            key=lambda h: (h.get('page_num', 0), h.get('bbox', [0])[1] if h.get('bbox') else 0)
        )
        
        # Строим дерево
        root = {'level': 0, 'children': []}
        stack = [root]
        
        for header in sorted_headers:
            level = header.get('level', 1)
            
            # Находим родительский узел (последний узел с уровнем меньше текущего)
            while len(stack) > 1 and stack[-1]['level'] >= level:
                stack.pop()
            
            # Создаем новый узел
            node = {
                'header': header,
                'level': level,
                'children': []
            }
            
            # Добавляем к родителю
            stack[-1]['children'].append(node)
            stack.append(node)
        
        return root


def detect_header_levels(headers: List[Dict]) -> List[Dict]:
    """
    Удобная функция для определения уровней заголовков.
    
    Args:
        headers: Список заголовков с базовыми метаданными
        
    Returns:
        Список заголовков с определенными уровнями
    """
    detector = HeaderLevelDetector()
    return detector.detect_levels(headers)

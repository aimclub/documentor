"""
Пайплайн извлечения заголовков из DOCX файлов.

Основные компоненты:
- HeadingDetector: детектор заголовков с правилами
- Paragraph: класс для представления параграфа
- HeadingNode: узел иерархии заголовков
- process_docx_file: основная функция обработки
"""

from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
import re
from docx import Document as DocxDocument
from docx.shared import Pt


@dataclass
class Paragraph:
    """Представление параграфа с метаданными."""
    text: str
    index: int
    style_name: str
    font_size: float
    is_bold: bool
    alignment: str
    space_before: float
    space_after: float
    numbering_text: Optional[str] = None
    
    # Результаты анализа
    is_heading: bool = False
    detected_level: int = 1
    heading_score: float = 0.0
    detection_reason: List[str] = None
    
    def __post_init__(self):
        if self.detection_reason is None:
            self.detection_reason = []
    
    @property
    def word_count(self) -> int:
        """Количество слов в тексте."""
        return len(self.text.split())
    
    @property
    def has_numbering(self) -> bool:
        """Есть ли нумерация."""
        return self.numbering_text is not None


class HeadingNode:
    """Узел иерархии заголовков."""
    def __init__(self, paragraph: Paragraph):
        self.text = paragraph.text
        self.level = paragraph.detected_level
        self.index = paragraph.index
        self.numbering = paragraph.numbering_text
        self.children: List['HeadingNode'] = []
    
    def add_child(self, child: 'HeadingNode'):
        """Добавить дочерний узел."""
        self.children.append(child)
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в словарь для JSON."""
        return {
            'text': self.text,
            'level': self.level,
            'index': self.index,
            'numbering': self.numbering,
            'children': [child.to_dict() for child in self.children]
        }


class HeadingDetector:
    """Детектор заголовков на основе правил."""
    
    def __init__(self):
        self.avg_font_size = 0.0
        self.max_font_size = 0.0
        self.avg_space_before = 0.0
        self.avg_space_after = 0.0
        self.content_start_index = 0
        
        # Паттерны нумерации (только начинающиеся с 1)
        self.numbering_patterns = [
            r'^1\.',            # 1.
            r'^1\.\d+',         # 1.1, 1.2
            r'^1\.\d+\.\d+',    # 1.1.1, 1.2.3
            r'^2\.',            # 2.
            r'^2\.\d+',         # 2.1, 2.2
            r'^2\.\d+\.\d+',    # 2.1.1, 2.2.3
            r'^3\.',            # 3.
            r'^3\.\d+',         # 3.1, 3.2
            r'^3\.\d+\.\d+',    # 3.1.1, 3.2.3
            r'^[IVX]+\.',       # I.
            r'^[ivx]+\.',       # i.
            r'^[А-Я]\.',        # А.
            r'^[а-я]\.',        # а.
        ]
    
    def extract_paragraphs(self, docx_path: Path) -> List[Paragraph]:
        """Извлечь параграфы из DOCX файла."""
        doc = DocxDocument(docx_path)
        paragraphs = []
        
        for i, para in enumerate(doc.paragraphs):
            if not para.text.strip():
                continue
            
            # Извлечение форматирования
            runs = para.runs
            if runs:
                first_run = runs[0]
                font_size = first_run.font.size
                is_bold = first_run.bold
            else:
                font_size = Pt(12)
                is_bold = False
            
            # Размер шрифта в пунктах
            font_size_pt = font_size.pt if font_size else 12.0
            
            # Выравнивание
            alignment_map = {
                'CENTER': 'center',
                'LEFT': 'left', 
                'RIGHT': 'right',
                'JUSTIFY': 'justify'
            }
            alignment = alignment_map.get(str(para.alignment), 'left')
            
            # Отступы
            space_before = para.paragraph_format.space_before.pt if para.paragraph_format.space_before else 0
            space_after = para.paragraph_format.space_after.pt if para.paragraph_format.space_after else 0
            
            # Проверка нумерации
            numbering_text = self._extract_numbering(para.text)
            
            paragraph = Paragraph(
                text=para.text.strip(),
                index=i,
                style_name=para.style.name if para.style else "Normal",
                font_size=font_size_pt,
                is_bold=is_bold,
                alignment=alignment,
                space_before=space_before,
                space_after=space_after,
                numbering_text=numbering_text
            )
            
            paragraphs.append(paragraph)
        
        # Вычисление статистики
        self._calculate_statistics(paragraphs)
        
        return paragraphs
    
    def _extract_numbering(self, text: str) -> Optional[str]:
        """Извлечь нумерацию из текста."""
        for pattern in self.numbering_patterns:
            match = re.match(pattern, text.strip())
            if match:
                return match.group(0)
        return None
    
    def _calculate_statistics(self, paragraphs: List[Paragraph]):
        """Вычислить статистику по параграфам."""
        if not paragraphs:
            return
        
        font_sizes = [p.font_size for p in paragraphs]
        space_before_values = [p.space_before for p in paragraphs]
        space_after_values = [p.space_after for p in paragraphs]
        
        self.avg_font_size = sum(font_sizes) / len(font_sizes)
        self.max_font_size = max(font_sizes)
        self.avg_space_before = sum(space_before_values) / len(space_before_values)
        self.avg_space_after = sum(space_after_values) / len(space_after_values)
        
        # Определение начала основного текста
        self.content_start_index = self._find_content_start(paragraphs)
    
    def _find_content_start(self, paragraphs: List[Paragraph]) -> int:
        """Найти начало основного текста (после титульной страницы)."""
        # Ищем первый параграф с обычным размером шрифта и достаточной длиной
        for i, para in enumerate(paragraphs):
            if (para.font_size <= self.avg_font_size * 1.2 and 
                para.word_count >= 10 and
                not para.alignment == 'center'):
                return i
        return 0
    
    def detect_headings(self, paragraphs: List[Paragraph]):
        """Определить заголовки в параграфах."""
        for para in paragraphs:
            score, reasons = self._calculate_heading_score(para)
            
            if score >= 2.0:  # Порог для заголовка
                para.is_heading = True
                para.heading_score = score
                para.detection_reason = reasons
                para.detected_level = self._determine_level(para)
            else:
                para.is_heading = False
                para.heading_score = score
                para.detection_reason = reasons
    
    def _calculate_heading_score(self, para: Paragraph) -> Tuple[float, List[str]]:
        """Вычислить оценку заголовка."""
        score = 0.0
        reasons = []
        
        # Проверка нумерации
        if para.has_numbering:
            score += 2.0
            reasons.append(f"Нумерация: {para.numbering_text}")
        
        # Проверка стиля Heading
        if 'Heading' in para.style_name:
            score += 3.0
            reasons.append(f"Стиль Heading: {para.style_name}")
        
        # Проверка размера шрифта
        font_ratio = para.font_size / self.avg_font_size
        if font_ratio > 1.2:
            score += 1.5
            reasons.append(f"Увеличенный шрифт (ratio={font_ratio:.2f})")
        elif font_ratio > 1.0:
            score += 0.5
            reasons.append(f"Уровень {int(font_ratio)} по размеру шрифта (ratio={font_ratio:.2f})")
        
        # Проверка жирности
        if para.is_bold:
            score += 1.0
            reasons.append("Жирный текст")
        
        # Проверка выравнивания
        if para.alignment == 'center':
            score += 1.0
            reasons.append("Выравнивание по центру")
        
        # Проверка длины текста
        word_count = para.word_count
        if word_count <= 5:
            score += 1.0
            reasons.append(f"Короткий текст: {word_count} слов")
        elif word_count <= 10:
            score += 0.5
            reasons.append(f"Средний текст: {word_count} слов")
        
        # Проверка на заглавные буквы
        if para.text.isupper():
            score += 1.0
            reasons.append("Все заглавные буквы")
        
        # Проверка на отсутствие точки в конце
        if not para.text.endswith('.'):
            score += 0.5
            reasons.append("Без точки в конце")
        
        # Проверка отступов
        if para.space_before > self.avg_space_before * 1.5:
            score += 0.5
            reasons.append("Увеличенный отступ сверху")
        
        if para.space_after > self.avg_space_after * 1.5:
            score += 0.5
            reasons.append("Увеличенный отступ снизу")
        
        return score, reasons
    
    def _determine_level(self, para: Paragraph) -> int:
        """Определить уровень заголовка."""
        # По нумерации
        if para.has_numbering:
            numbering = para.numbering_text
            if re.match(r'^\d+\.$', numbering):
                return 1
            elif re.match(r'^\d+\.\d+\.$', numbering):
                return 2
            elif re.match(r'^\d+\.\d+\.\d+\.$', numbering):
                return 3
            elif re.match(r'^[IVX]+\.$', numbering):
                return 1
            elif re.match(r'^[ivx]+\.$', numbering):
                return 2
        
        # По размеру шрифта
        font_ratio = para.font_size / self.avg_font_size
        if font_ratio > 1.5:
            return 1
        elif font_ratio > 1.2:
            return 2
        else:
            return 3
    
    def build_hierarchy(self, paragraphs: List[Paragraph]) -> List[HeadingNode]:
        """Построить иерархию заголовков."""
        headings = [p for p in paragraphs if p.is_heading and p.index >= self.content_start_index]
        
        if not headings:
            return []
        
        # Создание узлов
        nodes = [HeadingNode(h) for h in headings]
        
        # Построение дерева
        root_nodes = []
        stack = []
        
        for node in nodes:
            # Удаляем узлы из стека с уровнем >= текущего
            while stack and stack[-1].level >= node.level:
                stack.pop()
            
            if stack:
                # Добавляем как дочерний к последнему узлу в стеке
                stack[-1].add_child(node)
            else:
                # Корневой узел
                root_nodes.append(node)
            
            stack.append(node)
        
        return root_nodes
    
    def export_to_dict(self, hierarchy: List[HeadingNode]) -> List[Dict[str, Any]]:
        """Экспортировать иерархию в словарь."""
        return [node.to_dict() for node in hierarchy]


def process_docx_file(docx_path: Path) -> Tuple[List[Paragraph], List[HeadingNode], HeadingDetector]:
    """
    Обработать DOCX файл и извлечь заголовки.
    
    Args:
        docx_path: Путь к DOCX файлу
        
    Returns:
        Tuple[paragraphs, hierarchy, detector]: Параграфы, иерархия заголовков, детектор
    """
    detector = HeadingDetector()
    
    # Извлечение параграфов
    paragraphs = detector.extract_paragraphs(docx_path)
    
    # Определение заголовков
    detector.detect_headings(paragraphs)
    
    # Построение иерархии
    hierarchy = detector.build_hierarchy(paragraphs)
    
    return paragraphs, hierarchy, detector


if __name__ == "__main__":
    # Тестирование
    test_file = Path("test_folder/Диплом.docx")
    if test_file.exists():
        paragraphs, hierarchy, detector = process_docx_file(test_file)
        
        headings = [p for p in paragraphs if p.is_heading]
        content_headings = [p for p in headings if p.index >= detector.content_start_index]
        
        print(f"Обработано параграфов: {len(paragraphs)}")
        print(f"Найдено заголовков: {len(headings)}")
        print(f"Заголовков в основном тексте: {len(content_headings)}")
        print(f"Корневых узлов в иерархии: {len(hierarchy)}")
        
        print("\nПервые 5 заголовков:")
        for i, h in enumerate(content_headings[:5], 1):
            print(f"{i}. [{h.detected_level}] {h.text}")
    else:
        print(f"Тестовый файл не найден: {test_file}")

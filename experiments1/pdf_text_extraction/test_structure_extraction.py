"""
Извлечение структуры из PDF (абзацы, списки, заголовки).

Эксперименты:
- Определение абзацев по координатам
- Поиск списков по маркерам и отступам
- Определение заголовков по шрифтам
- Построение иерархии элементов
"""

import pdfplumber
from pathlib import Path
from typing import List, Dict, Any


def extract_paragraphs(page) -> List[Dict[str, Any]]:
    """
    Извлекает абзацы из страницы на основе координат и переносов строк.
    
    Args:
        page: Страница pdfplumber.
        
    Returns:
        Список абзацев с метаданными.
    """
    text = page.extract_text()
    if not text:
        return []
    
    # Разбиение на абзацы по двойным переносам строк
    paragraphs = []
    for para_text in text.split("\n\n"):
        para_text = para_text.strip()
        if para_text:
            paragraphs.append({
                "text": para_text,
                "type": "paragraph",
            })
    
    return paragraphs


def detect_lists(page) -> List[Dict[str, Any]]:
    """
    Определяет списки на странице по маркерам и отступам.
    
    Args:
        page: Страница pdfplumber.
        
    Returns:
        Список найденных списков.
    """
    words = page.extract_words()
    lists = []
    current_list = []
    
    # Маркеры списков
    bullet_markers = ["•", "◦", "▪", "-", "—", "–"]
    number_patterns = [f"{i}." for i in range(1, 100)]  # "1.", "2.", ...
    
    for word in words:
        text = word.get("text", "").strip()
        
        # Проверка на маркер списка
        is_bullet = text in bullet_markers
        is_numbered = any(text.startswith(pattern) for pattern in number_patterns)
        
        if is_bullet or is_numbered:
            # Начало нового элемента списка
            if current_list:
                lists.append({
                    "type": "list",
                    "items": current_list,
                })
            current_list = [{"marker": text, "text": ""}]
        elif current_list:
            # Продолжение текущего элемента списка
            current_list[-1]["text"] += " " + text if current_list[-1]["text"] else text
    
    if current_list:
        lists.append({
            "type": "list",
            "items": current_list,
        })
    
    return lists


def detect_headers(page) -> List[Dict[str, Any]]:
    """
    Определяет заголовки по размеру шрифта и жирности.
    
    Args:
        page: Страница pdfplumber.
        
    Returns:
        Список найденных заголовков.
    """
    chars = page.chars
    if not chars:
        return []
    
    # Группировка символов по строкам
    lines = {}
    for char in chars:
        y = round(char["top"], 1)  # Округление для группировки
        if y not in lines:
            lines[y] = []
        lines[y].append(char)
    
    headers = []
    
    # Анализ каждой строки
    for y, line_chars in sorted(lines.items()):
        if not line_chars:
            continue
        
        # Получение текста строки
        line_text = "".join(char["text"] for char in sorted(line_chars, key=lambda c: c["x0"]))
        line_text = line_text.strip()
        
        if not line_text:
            continue
        
        # Анализ шрифтов
        font_sizes = [char.get("size", 0) for char in line_chars]
        is_bold = any(char.get("bold", False) for char in line_chars)
        avg_size = sum(font_sizes) / len(font_sizes) if font_sizes else 0
        
        # Эвристики для определения заголовков
        is_header = False
        level = 0
        
        # Большой шрифт (>14) - вероятно заголовок
        if avg_size > 14:
            is_header = True
            if avg_size > 18:
                level = 1
            elif avg_size > 16:
                level = 2
            else:
                level = 3
        
        # Жирный текст + короткая строка - вероятно заголовок
        elif is_bold and len(line_text.split()) < 10:
            is_header = True
            level = 3
        
        if is_header:
            headers.append({
                "text": line_text,
                "level": level,
                "font_size": avg_size,
                "is_bold": is_bold,
                "y_position": y,
            })
    
    return headers


def test_structure_extraction(pdf_path: str | Path):
    """Тестирует извлечение структуры из PDF."""
    print(f"\n{'='*80}")
    print(f"Извлечение структуры из: {pdf_path}")
    print(f"{'='*80}\n")
    
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):  # Все страницы
            print(f"--- Страница {i} ---\n")
            
            # Абзацы
            paragraphs = extract_paragraphs(page)
            print(f"Найдено абзацев: {len(paragraphs)}")
            if paragraphs:
                print("Все абзацы:")
                for para in paragraphs:
                    print(f"  - {para['text']}")
            print()
            
            # Списки
            lists = detect_lists(page)
            print(f"Найдено списков: {len(lists)}")
            if lists:
                print("Все списки:")
                for list_idx, list_obj in enumerate(lists, 1):
                    print(f"  Список {list_idx}:")
                    for item in list_obj["items"]:
                        print(f"    {item.get('marker', '•')} {item.get('text', '')}")
            print()
            
            # Заголовки
            headers = detect_headers(page)
            print(f"Найдено заголовков: {len(headers)}")
            if headers:
                print("Заголовки:")
                for header in headers:
                    level_marker = "#" * header["level"]
                    print(f"  {level_marker} {header['text']} "
                          f"(размер: {header['font_size']:.1f}, "
                          f"жирный: {header['is_bold']})")
            print()
            print("-" * 80)
            print()


if __name__ == "__main__":
    import sys
    
    # Поиск первого PDF файла в test_files
    test_files_dir = Path("test_files")
    pdf_files = list(test_files_dir.glob("*.pdf")) if test_files_dir.exists() else []
    
    if not pdf_files:
        print("⚠️  PDF файлы не найдены в test_files/")
        print("Поместите PDF файлы в папку test_files/")
        sys.exit(1)
    
    # Используем первый найденный PDF или файл из аргументов
    if len(sys.argv) > 1:
        test_pdf = Path(sys.argv[1])
    else:
        test_pdf = pdf_files[0]
        print(f"Используется файл: {test_pdf.name}\n")
    
    if not test_pdf.exists():
        print(f"⚠️  Файл {test_pdf} не найден!")
        sys.exit(1)
    
    try:
        test_structure_extraction(test_pdf)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

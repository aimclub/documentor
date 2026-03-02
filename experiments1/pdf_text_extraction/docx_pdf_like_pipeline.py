"""
Пример реализации пайплайна DOCX, аналогичного PDF пайплайну.

Использует данные из docx_extraction_results для построения структуры,
аналогичной PDF пайплайну.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    from docx import Document as PythonDocxDocument
    HAS_PYTHON_DOCX = True
except ImportError:
    HAS_PYTHON_DOCX = False
    print("Предупреждение: python-docx не установлен")


def docx_to_layout_element(para_data: Dict) -> Dict:
    """
    Преобразует данные параграфа DOCX в формат layout element (аналог Dots.OCR output).
    
    Args:
        para_data: Словарь с данными параграфа из full_data.json
        
    Returns:
        Словарь в формате layout element
    """
    # Определение категории по стилю
    category_map = {
        "Heading 1": "Section-header",
        "Heading 2": "Section-header",
        "Heading 3": "Section-header",
        "Heading 4": "Section-header",
        "Heading 5": "Section-header",
        "Heading 6": "Section-header",
        "Normal": "Text",
        "List Paragraph": "List-item",
        "Title": "Title",
    }
    
    style = para_data.get("style", "Normal")
    category = category_map.get(style, "Text")
    
    # Преобразование отступов в координаты (аналог bbox)
    coordinates = para_data.get("coordinates", {})
    left_indent = int(coordinates.get("left_indent", 0) or 0) / 20  # twips -> pt
    right_indent = int(coordinates.get("right_indent", 0) or 0) / 20
    
    # Создаем виртуальный bbox на основе отступов
    # Для DOCX используем относительные координаты
    # Y-координата будет вычисляться по порядку параграфов
    bbox = [
        left_indent,  # x1
        0,  # y1 (будет вычисляться по порядку)
        left_indent + 500,  # x2 (примерная ширина текста)
        20  # y2 (примерная высота параграфа)
    ]
    
    return {
        "bbox": bbox,
        "category": category,
        "page_num": 0,  # В DOCX нет страниц
        "paragraph_index": para_data["index"],
        "text": para_data["text"],
        "style": style,
        "metadata": para_data.get("formatting", {}),
        "is_heading": para_data.get("is_heading", False)
    }


def determine_header_level_docx(para_data: Dict, previous_headers: List[Dict]) -> int:
    """
    Определяет уровень заголовка для DOCX (аналог _determine_header_level из PDF).
    
    Args:
        para_data: Данные параграфа
        previous_headers: Список предыдущих заголовков для контекста
        
    Returns:
        Уровень заголовка (1-6)
    """
    style = para_data.get("style", "")
    text = para_data.get("text", "")
    
    # Приоритет 1: Встроенные стили DOCX
    if style.startswith("Heading"):
        level = int(style.split()[-1])  # "Heading 1" -> 1
        return min(level, 6)  # Ограничиваем максимум 6
    
    # Приоритет 2: Анализ нумерации в тексте (как в PDF)
    if re.match(r'^\d+\s+[A-Z]', text):
        return 1
    if re.match(r'^\d+\.\d+\s+', text):
        return 2
    if re.match(r'^\d+\.\d+\.\d+\s+', text):
        return 3
    if re.match(r'^\d+\.\d+\.\d+\.\d+\s+', text):
        return 4
    
    # Приоритет 3: Сравнение размера шрифта с предыдущими (как в PDF)
    font_size_str = para_data.get("formatting", {}).get("font_size")
    if font_size_str and previous_headers:
        try:
            current_size = float(font_size_str.replace("pt", ""))
            
            # Находим последний заголовок с известным размером шрифта
            for header in reversed(previous_headers):
                last_font_size_str = header.get("formatting", {}).get("font_size")
                if last_font_size_str:
                    last_size = float(last_font_size_str.replace("pt", ""))
                    last_level = header.get("level", 1)
                    
                    # Сравниваем размеры (как в PDF: >= 2pt разница)
                    if current_size >= last_size + 2:
                        return max(1, last_level - 1)
                    elif current_size <= last_size - 2:
                        return min(6, last_level + 1)
                    else:
                        return last_level
        except (ValueError, AttributeError):
            pass
    
    # По умолчанию
    return 1


def analyze_header_levels_docx(layout_elements: List[Dict]) -> List[Dict]:
    """
    Анализирует уровни заголовков (аналог _analyze_header_levels_from_elements из PDF).
    
    Args:
        layout_elements: Список layout elements
        
    Returns:
        Список элементов с определенными уровнями заголовков
    """
    analyzed_elements = []
    previous_headers = []
    last_numbered_level = None
    
    for element in layout_elements:
        if element["category"] == "Section-header":
            # Определяем уровень заголовка
            para_data = {
                "style": element.get("style", ""),
                "text": element.get("text", ""),
                "formatting": element.get("metadata", {})
            }
            
            level = determine_header_level_docx(para_data, previous_headers)
            
            # Проверяем наличие нумерации
            text = element.get("text", "")
            if re.match(r'^\d+', text):
                last_numbered_level = level
            
            # Сохраняем заголовок для контекста
            previous_headers.append({
                "level": level,
                "text": text,
                "formatting": para_data["formatting"]
            })
            
            # Добавляем уровень в элемент
            element["header_level"] = level
            element["last_numbered_level"] = last_numbered_level
        
        analyzed_elements.append(element)
    
    return analyzed_elements


def build_hierarchy_from_docx(analyzed_elements: List[Dict]) -> List[Dict]:
    """
    Строит иерархию из элементов DOCX (аналог _build_hierarchy_from_section_headers из PDF).
    
    Args:
        analyzed_elements: Список элементов с определенными уровнями заголовков
        
    Returns:
        Список секций с заголовками и дочерними элементами
    """
    sections = []
    current_section = None
    
    for element in analyzed_elements:
        if element["category"] == "Section-header":
            # Начинаем новую секцию
            if current_section:
                sections.append(current_section)
            
            current_section = {
                "header": {
                    "text": element["text"],
                    "level": element.get("header_level", 1),
                    "style": element.get("style", ""),
                    "index": element.get("paragraph_index", 0),
                    "bbox": element.get("bbox", []),
                    "category": "Section-header"
                },
                "children": []
            }
        else:
            # Добавляем в текущую секцию
            if current_section:
                current_section["children"].append(element)
            else:
                # Если нет заголовка, создаем секцию "Начало документа"
                if not sections or sections[-1].get("header", {}).get("text") != "Начало документа":
                    current_section = {
                        "header": {
                            "text": "Начало документа",
                            "level": 0,
                            "category": "Title",
                            "style": "Title"
                        },
                        "children": []
                    }
                    sections.append(current_section)
                else:
                    current_section = sections[-1]
                
                current_section["children"].append(element)
    
    if current_section:
        sections.append(current_section)
    
    return sections


def merge_text_blocks_docx(children: List[Dict], max_chunk_size: int = 3000) -> List[Dict]:
    """
    Склеивает близкие текстовые блоки (аналог _merge_nearby_text_blocks из PDF).
    
    Args:
        children: Список дочерних элементов
        max_chunk_size: Максимальный размер чанка
        
    Returns:
        Список объединенных элементов
    """
    merged = []
    current_chunk = []
    current_size = 0
    
    for child in children:
        if child["category"] == "Text" or child["category"] == "List-item":
            text = child.get("text", "")
            text_size = len(text)
            
            if current_size + text_size > max_chunk_size and current_chunk:
                # Сохраняем текущий чанк
                merged_text = "\n".join([c.get("text", "") for c in current_chunk])
                merged.append({
                    "category": "Text",
                    "text": merged_text,
                    "metadata": current_chunk[0].get("metadata", {})
                })
                current_chunk = []
                current_size = 0
            
            current_chunk.append(child)
            current_size += text_size
        else:
            # Если это не текст, сохраняем как есть
            if current_chunk:
                merged_text = "\n".join([c.get("text", "") for c in current_chunk])
                merged.append({
                    "category": "Text",
                    "text": merged_text,
                    "metadata": current_chunk[0].get("metadata", {})
                })
                current_chunk = []
                current_size = 0
            
            merged.append(child)
    
    # Сохраняем последний чанк
    if current_chunk:
        merged_text = "\n".join([c.get("text", "") for c in current_chunk])
        merged.append({
            "category": "Text",
            "text": merged_text,
            "metadata": current_chunk[0].get("metadata", {})
        })
    
    return merged


def process_tables_from_docx(tables_info: List[Dict]) -> List[Dict]:
    """
    Обрабатывает таблицы из DOCX (аналог _parse_tables_with_qwen из PDF).
    
    Args:
        tables_info: Список информации о таблицах из full_data.json
        
    Returns:
        Список элементов таблиц
    """
    table_elements = []
    
    for table in tables_info:
        # Преобразуем таблицу в markdown формат
        if not table.get("data"):
            continue
        
        # Заголовок таблицы
        header_row = table["data"][0]
        markdown_table = "| " + " | ".join(header_row) + " |\n"
        markdown_table += "| " + " | ".join(["---"] * len(header_row)) + " |\n"
        
        # Данные таблицы
        for row in table["data"][1:]:
            markdown_table += "| " + " | ".join(row) + " |\n"
        
        table_elements.append({
            "category": "Table",
            "text": markdown_table,
            "metadata": {
                "table_index": table["index"],
                "rows": table["rows"],
                "columns": table["columns"]
            }
        })
    
    return table_elements


def parse_docx_like_pdf(docx_path: Path) -> Dict[str, Any]:
    """
    Парсит DOCX используя подход, аналогичный PDF пайплайну.
    
    Args:
        docx_path: Путь к DOCX файлу
        
    Returns:
        Словарь с результатами парсинга (аналог ParsedDocument)
    """
    # Шаг 1: Загрузка данных (уже извлеченных)
    results_dir = docx_path.parent / "docx_extraction_results"
    json_file = results_dir / f"{docx_path.stem}_full_data.json"
    
    if not json_file.exists():
        raise FileNotFoundError(f"Файл с данными не найден: {json_file}")
    
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    paragraphs_metadata = data["paragraphs_with_metadata"]
    tables_info = data.get("tables", [])
    
    # Шаг 2: Преобразование в layout elements (аналог Dots.OCR output)
    print("Шаг 1: Преобразование параграфов в layout elements...")
    layout_elements = [docx_to_layout_element(para) for para in paragraphs_metadata]
    print(f"  Создано {len(layout_elements)} layout elements")
    
    # Шаг 3: Анализ уровней заголовков
    print("Шаг 2: Анализ уровней заголовков...")
    analyzed_elements = analyze_header_levels_docx(layout_elements)
    headers_count = len([e for e in analyzed_elements if e["category"] == "Section-header"])
    print(f"  Найдено {headers_count} заголовков")
    
    # Шаг 4: Построение иерархии
    print("Шаг 3: Построение иерархии...")
    hierarchy = build_hierarchy_from_docx(analyzed_elements)
    print(f"  Создано {len(hierarchy)} секций")
    
    # Шаг 5: Склеивание текстовых блоков
    print("Шаг 4: Склеивание текстовых блоков...")
    for section in hierarchy:
        section["children"] = merge_text_blocks_docx(section["children"], max_chunk_size=3000)
    
    # Шаг 6: Обработка таблиц
    print("Шаг 5: Обработка таблиц...")
    table_elements = process_tables_from_docx(tables_info)
    print(f"  Обработано {len(table_elements)} таблиц")
    
    # Шаг 7: Создание элементов (упрощенная версия)
    elements = []
    
    for section in hierarchy:
        # Заголовок
        header_level = section["header"].get("level", 1)
        elements.append({
            "type": f"HEADER_{header_level}",
            "content": section["header"]["text"],
            "metadata": {
                "style": section["header"].get("style", ""),
                "index": section["header"].get("index", 0)
            }
        })
        
        # Дочерние элементы
        for child in section["children"]:
            if child["category"] == "Text":
                elements.append({
                    "type": "TEXT",
                    "content": child["text"],
                    "metadata": child.get("metadata", {})
                })
            elif child["category"] == "List-item":
                elements.append({
                    "type": "LIST_ITEM",
                    "content": child["text"],
                    "metadata": child.get("metadata", {})
                })
    
    # Добавляем таблицы
    for table in table_elements:
        elements.append({
            "type": "TABLE",
            "content": table["text"],
            "metadata": table["metadata"]
        })
    
    # Шаг 8: Создание результата (аналог ParsedDocument)
    result = {
        "source": str(docx_path),
        "format": "DOCX",
        "elements": elements,
        "metadata": {
            "parser": "docx_pdf_like",
            "status": "completed",
            "processing_method": "style_based_hierarchy",
            "sections_count": len(hierarchy),
            "tables_count": len(tables_info),
            "elements_count": len(elements),
            "headers_count": headers_count
        },
        "hierarchy": hierarchy  # Дополнительная информация для анализа
    }
    
    return result


def main():
    """Основная функция для тестирования."""
    # Путь к документу
    docx_path = Path(r"E:\easy\documentor\documentor_langchain\experiments\pdf_text_extraction\test_folder\Диплом.docx")
    
    if not docx_path.exists():
        print(f"Ошибка: Файл не найден: {docx_path}")
        return
    
    print("=" * 80)
    print("ПАЙПЛАЙН DOCX (АНАЛОГ PDF)")
    print("=" * 80)
    print()
    
    # Парсинг
    result = parse_docx_like_pdf(docx_path)
    
    # Сохранение результата
    output_dir = docx_path.parent / "docx_extraction_results"
    output_file = output_dir / f"{docx_path.stem}_pdf_like_pipeline.json"
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print()
    print("=" * 80)
    print("РЕЗУЛЬТАТЫ")
    print("=" * 80)
    print(f"Источник: {result['source']}")
    print(f"Формат: {result['format']}")
    print(f"Секций: {result['metadata']['sections_count']}")
    print(f"Заголовков: {result['metadata']['headers_count']}")
    print(f"Таблиц: {result['metadata']['tables_count']}")
    print(f"Всего элементов: {result['metadata']['elements_count']}")
    print()
    print(f"Результат сохранен в: {output_file}")


if __name__ == "__main__":
    main()

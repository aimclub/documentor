"""
Тест для парсера Markdown документов.

Проверяет парсинг различных элементов Markdown:
- Заголовки (уровни 1-6)
- Маркированные и нумерованные списки
- Вложенные списки
- Таблицы
- Цитаты
- Код-блоки
- Ссылки
- Изображения
- Inline код
- Горизонтальные линии
- Текст
"""

import sys
from pathlib import Path

from langchain_core.documents import Document

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Импортируем напрямую, чтобы избежать проблем с зависимостями других парсеров
from documentor.processing.parsers.md.md_parser import MarkdownParser
from documentor.domain.models import ElementType


def test_md_parser(md_file_path: str | Path):
    """
    Тестирует парсинг Markdown файла.
    
    Args:
        md_file_path: Путь к Markdown файлу
    """
    md_path = Path(md_file_path)
    
    if not md_path.exists():
        print(f"Файл не найден: {md_path}")
        sys.exit(1)
    
    print(f"\n{'='*80}")
    print(f"Тест парсера Markdown: {md_path.name}")
    print(f"{'='*80}\n")
    
    # Загружаем содержимое файла
    with open(md_path, "r", encoding="utf-8") as f:
        markdown_content = f.read()
    
    # Создаем Document
    doc = Document(
        page_content=markdown_content,
        metadata={"source": str(md_path)}
    )
    
    # Создаем парсер и парсим
    parser = MarkdownParser()
    parsed_doc = parser.parse(doc)
    
    # Выводим общую информацию
    print(f"Источник: {parsed_doc.source}")
    print(f"Формат: {parsed_doc.format}")
    print(f"Всего элементов: {len(parsed_doc.elements)}")
    print(f"\nМетаданные парсера:")
    for key, value in parsed_doc.metadata.items():
        print(f"  {key}: {value}")
    print()
    
    # Группируем элементы по типам
    elements_by_type = {}
    for element in parsed_doc.elements:
        element_type = element.type.value
        if element_type not in elements_by_type:
            elements_by_type[element_type] = []
        elements_by_type[element_type].append(element)
    
    print(f"{'='*80}")
    print("Элементы по типам:")
    print(f"{'='*80}\n")
    
    # Выводим элементы по типам
    for element_type in sorted(elements_by_type.keys()):
        elements = elements_by_type[element_type]
        print(f"{element_type.upper()}: {len(elements)} элементов")
        print("-" * 80)
        
        for i, element in enumerate(elements, 1):
            print(f"\n[{i}] ID: {element.id}")
            if element.parent_id:
                print(f"    Parent ID: {element.parent_id}")
            
            # Выводим содержимое (обрезаем длинные тексты)
            content = element.content
            if len(content) > 200:
                content = content[:200] + "..."
            print(f"    Содержимое: {content}")
            
            # Выводим метаданные
            if element.metadata:
                print(f"    Метаданные:")
                for key, value in element.metadata.items():
                    if isinstance(value, str) and len(value) > 100:
                        value = value[:100] + "..."
                    print(f"      {key}: {value}")
        
        print()
    
    # Проверяем конкретные элементы из тестового файла
    print(f"{'='*80}")
    print("Проверка конкретных элементов:")
    print(f"{'='*80}\n")
    
    # Заголовки
    headers = [e for e in parsed_doc.elements if e.type.name.startswith("HEADER_")]
    print(f"Заголовки ({len(headers)}):")
    for header in headers:
        level = header.type.name.split("_")[-1]
        print(f"  H{level}: {header.content}")
    print()
    
    # Списки
    list_items = [e for e in parsed_doc.elements if e.type == ElementType.LIST_ITEM]
    print(f"Элементы списков ({len(list_items)}):")
    for item in list_items[:10]:  # Показываем первые 10
        list_type = item.metadata.get("list_type", "unknown")
        level = item.metadata.get("list_level", 0)
        indent = "  " * level
        print(f"  {indent}[{list_type}] {item.content}")
    if len(list_items) > 10:
        print(f"  ... и еще {len(list_items) - 10} элементов")
    print()
    
    # Таблицы
    tables = [e for e in parsed_doc.elements if e.type == ElementType.TABLE]
    print(f"Таблицы ({len(tables)}):")
    for i, table in enumerate(tables, 1):
        print(f"  Таблица {i}:")
        # Таблица хранится в HTML формате
        html_content = table.content
        if len(html_content) > 300:
            html_content = html_content[:300] + "..."
        print(f"    HTML: {html_content}")
    print()
    
    # Изображения
    images = [e for e in parsed_doc.elements if e.type == ElementType.IMAGE]
    print(f"Изображения ({len(images)}):")
    for image in images:
        alt = image.metadata.get("alt", "")
        src = image.metadata.get("src", "")
        print(f"  Alt: '{alt}', Src: '{src}'")
    print()
    
    # Ссылки
    links = [e for e in parsed_doc.elements if e.type == ElementType.LINK]
    print(f"Ссылки ({len(links)}):")
    for link in links:
        href = link.metadata.get("href", "")
        print(f"  Текст: '{link.content}', URL: '{href}'")
    print()
    
    # Код-блоки
    code_blocks = [e for e in parsed_doc.elements if e.type == ElementType.CODE_BLOCK]
    print(f"Код-блоки ({len(code_blocks)}):")
    for code in code_blocks:
        language = code.metadata.get("language", "")
        content_preview = code.content[:100] + "..." if len(code.content) > 100 else code.content
        print(f"  Язык: '{language}', Содержимое: {content_preview}")
    print()
    
    # Цитаты
    quotes = [e for e in parsed_doc.elements if e.type == ElementType.TEXT and e.metadata.get("quote")]
    print(f"Цитаты ({len(quotes)}):")
    for quote in quotes:
        content_preview = quote.content[:150] + "..." if len(quote.content) > 150 else quote.content
        print(f"  {content_preview}")
    print()
    
    # Горизонтальные линии
    separators = [e for e in parsed_doc.elements if e.type == ElementType.TEXT and e.metadata.get("separator")]
    print(f"Горизонтальные линии ({len(separators)}):")
    for sep in separators:
        print(f"  {sep.content}")
    print()
    
    # Иерархия
    print(f"{'='*80}")
    print("Иерархия элементов:")
    print(f"{'='*80}\n")
    
    def print_element_tree(element, indent=0, elements_dict=None):
        """Рекурсивно выводит дерево элементов."""
        if elements_dict is None:
            elements_dict = {e.id: e for e in parsed_doc.elements}
        
        prefix = "  " * indent
        element_type_short = element.type.value.upper()[:8]
        content_preview = element.content[:50] + "..." if len(element.content) > 50 else element.content
        print(f"{prefix}[{element_type_short}] {content_preview}")
        
        # Находим дочерние элементы
        children = [e for e in parsed_doc.elements if e.parent_id == element.id]
        for child in children:
            print_element_tree(child, indent + 1, elements_dict)
    
    # Находим корневые элементы (без parent_id)
    root_elements = [e for e in parsed_doc.elements if e.parent_id is None]
    print(f"Корневых элементов: {len(root_elements)}\n")
    
    for root in root_elements[:5]:  # Показываем первые 5 корневых элементов
        print_element_tree(root)
        print()
    
    if len(root_elements) > 5:
        print(f"... и еще {len(root_elements) - 5} корневых элементов")
    
    print(f"\n{'='*80}")
    print("Тест завершен успешно!")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    # Путь к тестовому файлу
    test_file = Path(__file__).parent.parent.parent / "tests" / "files_for_tests" / "full_markdown.md"
    
    # Можно передать путь к файлу как аргумент
    if len(sys.argv) > 1:
        test_file = Path(sys.argv[1])
    
    if not test_file.exists():
        print(f"Файл не найден: {test_file}")
        print(f"Использование: python {Path(__file__).name} [путь_к_md_файлу]")
        sys.exit(1)
    
    try:
        test_md_parser(test_file)
    except Exception as e:
        print(f"\nОшибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

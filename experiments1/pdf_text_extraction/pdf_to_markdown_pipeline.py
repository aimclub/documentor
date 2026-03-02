"""
Пайплайн для конвертации PDF в Markdown с использованием Dots OCR.

Обрабатывает сканированный PDF файл через Dots OCR и конвертирует результат в Markdown формат.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from langchain_core.documents import Document

# Добавляем путь к корню проекта
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from documentor import Pipeline
from documentor.domain.models import ParsedDocument, ElementType


def convert_element_to_markdown(element, indent_level: int = 0) -> str:
    """
    Конвертирует элемент в Markdown формат.
    
    Args:
        element: Element из ParsedDocument
        indent_level: Уровень отступа для вложенных элементов
    
    Returns:
        Markdown строка
    """
    indent = "  " * indent_level
    element_type = element.type
    
    # Заголовки
    if element_type in [ElementType.HEADER_1, ElementType.HEADER_2, ElementType.HEADER_3,
                        ElementType.HEADER_4, ElementType.HEADER_5, ElementType.HEADER_6]:
        level = int(element_type.name.split("_")[1])
        # Убираем существующие символы # из начала контента
        content = element.content.strip()
        # Удаляем все # в начале строки
        while content.startswith('#'):
            content = content.lstrip('#').strip()
        return f"{indent}{'#' * level} {content}\n"
    
    # Заголовок документа
    if element_type == ElementType.TITLE:
        # Убираем существующие символы # из начала контента
        content = element.content.strip()
        while content.startswith('#'):
            content = content.lstrip('#').strip()
        return f"# {content}\n\n"
    
    # Текст
    if element_type == ElementType.TEXT:
        # Проверяем, является ли это формулой
        if element.metadata.get("is_formula") or element.metadata.get("formula_latex"):
            latex = element.metadata.get("formula_latex", element.content)
            return f"{indent}$${latex}$$\n\n"
        
        # Проверяем, является ли это элементом списка
        if element.metadata.get("is_list_item"):
            # Определяем тип маркера списка (нумерованный или маркированный)
            content = element.content.strip()
            if content and content[0].isdigit() and (content[1:2] in [".", ")"]):
                # Нумерованный список
                return f"{indent}{content}\n"
            else:
                # Маркированный список
                return f"{indent}- {content}\n"
        
        # Обычный текст
        if element.content.strip():
            return f"{indent}{element.content}\n\n"
        return ""
    
    # Таблицы
    if element_type == ElementType.TABLE:
        if element.content:
            return f"{element.content}\n\n"
        return ""
    
    # Изображения
    if element_type == ElementType.IMAGE:
        # Изображения сохраняются в base64 в metadata
        image_data = element.metadata.get("image_data", "")
        if image_data:
            # Сохраняем изображение и создаем ссылку
            # Для простоты просто указываем, что здесь изображение
            caption = element.metadata.get("caption", "Image")
            return f"{indent}![{caption}](image_{element.id}.png)\n\n"
        return ""
    
    # Подписи (Caption)
    if element_type == ElementType.CAPTION:
        # Caption обычно идет после изображения
        image_data = element.metadata.get("image_data", "")
        if image_data:
            # Если есть изображение, оно уже обработано выше
            return f"{indent}*{element.content}*\n\n"
        return f"{indent}*{element.content}*\n\n"
    
    # Ссылки
    if element_type == ElementType.LINK:
        href = element.metadata.get("href", "")
        return f"{indent}[{element.content}]({href})\n\n"
    
    # Код
    if element_type == ElementType.CODE_BLOCK:
        language = element.metadata.get("language", "")
        return f"{indent}```{language}\n{element.content}\n{indent}```\n\n"
    
    # По умолчанию - просто текст
    if element.content:
        return f"{indent}{element.content}\n\n"
    
    return ""


def convert_parsed_document_to_markdown(parsed_doc: ParsedDocument) -> str:
    """
    Конвертирует ParsedDocument в Markdown формат.
    
    Args:
        parsed_doc: ParsedDocument с распарсенными элементами
    
    Returns:
        Markdown строка
    """
    markdown_lines = []
    
    # Сортируем элементы по порядку (order или по page_num и позиции)
    sorted_elements = sorted(
        parsed_doc.elements,
        key=lambda e: (
            e.metadata.get("page_num", 0),
            e.metadata.get("bbox", [0, 0])[1] if len(e.metadata.get("bbox", [])) >= 2 else 0,
        )
    )
    
    # Создаем словарь элементов по ID для быстрого поиска родителей
    elements_by_id = {elem.id: elem for elem in sorted_elements}
    
    # Обрабатываем элементы с учетом иерархии
    processed_ids = set()
    
    def process_element(elem, indent: int = 0):
        """Рекурсивно обрабатывает элемент и его дочерние элементы."""
        if elem.id in processed_ids:
            return
        
        processed_ids.add(elem.id)
        
        # Конвертируем элемент в Markdown
        markdown = convert_element_to_markdown(elem, indent)
        if markdown:
            markdown_lines.append(markdown)
        
        # Обрабатываем дочерние элементы
        children = [e for e in sorted_elements if e.parent_id == elem.id]
        for child in sorted(children, key=lambda e: (
            e.metadata.get("page_num", 0),
            e.metadata.get("bbox", [0, 0])[1] if len(e.metadata.get("bbox", [])) >= 2 else 0,
        )):
            # Увеличиваем отступ для дочерних элементов
            process_element(child, indent + 1)
    
    # Обрабатываем элементы без родителей (корневые элементы)
    root_elements = [e for e in sorted_elements if e.parent_id is None]
    for root_elem in root_elements:
        process_element(root_elem, 0)
    
    # Обрабатываем оставшиеся элементы (на случай, если они не были обработаны)
    for elem in sorted_elements:
        if elem.id not in processed_ids:
            markdown = convert_element_to_markdown(elem, 0)
            if markdown:
                markdown_lines.append(markdown)
    
    return "".join(markdown_lines)


def pdf_to_markdown(pdf_path: Path, output_path: Optional[Path] = None) -> str:
    """
    Конвертирует PDF файл в Markdown с использованием Dots OCR.
    
    Args:
        pdf_path: Путь к PDF файлу
        output_path: Путь для сохранения Markdown файла (опционально)
    
    Returns:
        Markdown строка
    """
    print(f"Обработка PDF файла: {pdf_path.name}")
    
    # Создаем Pipeline
    pipeline = Pipeline()
    
    # Создаем LangChain Document
    document = Document(
        page_content="",
        metadata={"source": str(pdf_path.absolute())}
    )
    
    # Парсим PDF
    print("Парсинг PDF через Dots OCR...")
    parsed_doc: ParsedDocument = pipeline.parse(document)
    print(f"✓ Распарсено элементов: {len(parsed_doc.elements)}")
    
    # Конвертируем в Markdown
    print("Конвертация в Markdown...")
    markdown_content = convert_parsed_document_to_markdown(parsed_doc)
    print(f"✓ Сгенерировано Markdown: {len(markdown_content)} символов")
    
    # Сохраняем в файл, если указан путь
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        print(f"✓ Markdown сохранен в: {output_path}")
    
    return markdown_content


def main():
    """Основная функция."""
    # Путь к PDF файлу
    pdf_file_path = Path(r"E:\easy\documentor\documentor_langchain\experiments\pdf_text_extraction\test_files\scanned_2506.10204v1.pdf")
    
    if not pdf_file_path.exists():
        print(f"Файл не найден: {pdf_file_path}")
        return
    
    # Путь для сохранения Markdown
    output_file_path = pdf_file_path.parent.parent / "results" / "markdown" / f"{pdf_file_path.stem}.md"
    
    # Конвертируем PDF в Markdown
    markdown = pdf_to_markdown(pdf_file_path, output_file_path)
    
    print(f"\n{'='*80}")
    print("КОНВЕРТАЦИЯ ЗАВЕРШЕНА")
    print(f"{'='*80}")
    print(f"Исходный файл: {pdf_file_path.name}")
    print(f"Результат: {output_file_path}")
    print(f"Размер Markdown: {len(markdown)} символов")


if __name__ == "__main__":
    main()

"""
Инструмент для разметки документов (создание ground truth).

Позволяет интерактивно размечать документы для последующей оценки метрик.
"""

import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from documentor import Pipeline
from documentor.domain.models import ParsedDocument, Element, ElementType

try:
    import pandas as pd
except ImportError:
    pd = None


def create_annotation_template(
    document_id: str,
    source_file: Path,
    document_format: str,
    annotator: str = "unknown"
) -> Dict[str, Any]:
    """Создает шаблон разметки."""
    return {
        "document_id": document_id,
        "source_file": str(source_file),
        "document_format": document_format,
        "annotation_version": "1.0",
        "annotator": annotator,
        "annotation_date": datetime.now().isoformat(),
        "elements": [],
        "statistics": {
            "total_elements": 0,
            "total_pages": 0,
            "elements_by_type": {},
            "table_count": 0,
            "image_count": 0
        }
    }


def parse_document_for_annotation(source_file: Path) -> ParsedDocument:
    """Парсит документ для помощи в разметке."""
    from langchain_core.documents import Document
    
    # Преобразуем в абсолютный путь
    source_file = source_file.resolve()
    
    if not source_file.exists():
        raise FileNotFoundError(f"Файл не найден: {source_file}")
    
    pipeline = Pipeline()
    langchain_doc = Document(page_content="", metadata={"source": str(source_file)})
    parsed = pipeline.parse(langchain_doc)
    
    return parsed


def convert_parsed_to_annotation_elements(
    parsed: ParsedDocument,
    start_order: int = 0
) -> List[Dict[str, Any]]:
    """Конвертирует ParsedDocument в элементы для разметки."""
    elements = []
    
    for i, elem in enumerate(parsed.elements):
        element_data = {
            "id": elem.id,
            "type": elem.type.value.lower(),
            "content": elem.content,
            "parent_id": elem.parent_id,
            "order": start_order + i,
            "page_number": elem.metadata.get("page_num"),
            "bbox": elem.metadata.get("bbox"),
            "metadata": {}
        }
        
        # Добавляем метаданные для таблиц
        if elem.type == ElementType.TABLE:
            if pd is not None and elem.metadata.get("dataframe") is not None:
                df = elem.metadata["dataframe"]
                if isinstance(df, pd.DataFrame):
                    # Создаем структуру таблицы для TEDS
                    cells = []
                    for row_idx in range(df.shape[0]):
                        for col_idx in range(df.shape[1]):
                            cells.append({
                                "row": row_idx,
                                "col": col_idx,
                                "content": str(df.iloc[row_idx, col_idx]),
                                "rowspan": 1,
                                "colspan": 1
                            })
                    
                    element_data["metadata"]["table_structure"] = {
                        "html": df.to_html(),
                        "cells": cells
                    }
        
        # Добавляем ссылки
        if elem.metadata.get("links"):
            element_data["metadata"]["links"] = elem.metadata["links"]
        
        elements.append(element_data)
    
    return elements


def calculate_statistics(elements: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Вычисляет статистику по элементам."""
    stats = {
        "total_elements": len(elements),
        "total_pages": 0,
        "elements_by_type": {},
        "table_count": 0,
        "image_count": 0
    }
    
    pages = set()
    for elem in elements:
        # Подсчет по типам
        elem_type = elem["type"]
        stats["elements_by_type"][elem_type] = stats["elements_by_type"].get(elem_type, 0) + 1
        
        # Подсчет страниц
        if elem.get("page_number"):
            pages.add(elem["page_number"])
        
        # Подсчет таблиц и изображений
        if elem_type == "table":
            stats["table_count"] += 1
        elif elem_type == "image":
            stats["image_count"] += 1
    
    stats["total_pages"] = len(pages) if pages else 0
    
    return stats


def annotate_document(
    source_file: Path,
    output_path: Path,
    annotator: str = "unknown",
    use_auto_annotation: bool = True
) -> None:
    """
    Размечает документ.
    
    Args:
        source_file: Путь к исходному документу
        output_path: Путь для сохранения разметки
        annotator: Имя аннотатора
        use_auto_annotation: Использовать автоматическую разметку на основе парсинга
    """
    # Преобразуем пути в абсолютные
    source_file = Path(source_file).resolve()
    output_path = Path(output_path).resolve()
    
    if not source_file.exists():
        raise FileNotFoundError(f"Исходный файл не найден: {source_file}")
    
    print(f"Разметка документа: {source_file}")
    
    # Определяем формат
    if source_file.suffix.lower() == ".pdf":
        # Нужно определить, scanned или нет (упрощенно)
        doc_format = "pdf"  # или "pdf_scanned"
    elif source_file.suffix.lower() in [".docx", ".doc"]:
        doc_format = "docx"
    else:
        doc_format = "unknown"
    
    document_id = source_file.stem
    
    # Создаем шаблон
    annotation = create_annotation_template(
        document_id=document_id,
        source_file=source_file,
        document_format=doc_format,
        annotator=annotator
    )
    
    # Автоматическая разметка на основе парсинга
    if use_auto_annotation:
        print("Выполняется автоматический парсинг для помощи в разметке...")
        try:
            parsed = parse_document_for_annotation(source_file)
            elements = convert_parsed_to_annotation_elements(parsed)
            annotation["elements"] = elements
            print(f"Найдено {len(elements)} элементов")
        except Exception as e:
            print(f"Ошибка при автоматическом парсинге: {e}")
            print("Продолжаем с пустой разметкой...")
    
    # Вычисляем статистику
    annotation["statistics"] = calculate_statistics(annotation["elements"])
    
    # Сохраняем разметку
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(annotation, f, ensure_ascii=False, indent=2)
    
    print(f"Разметка сохранена: {output_path}")
    print(f"Всего элементов: {annotation['statistics']['total_elements']}")
    print(f"Таблиц: {annotation['statistics']['table_count']}")
    print(f"Изображений: {annotation['statistics']['image_count']}")
    print("\nВНИМАНИЕ: Пожалуйста, проверьте и отредактируйте разметку вручную!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Разметка документов для оценки")
    parser.add_argument("--input", "-i", type=Path, required=True, help="Входной файл документа")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Выходной файл разметки")
    parser.add_argument("--annotator", "-a", type=str, default="unknown", help="Имя аннотатора")
    parser.add_argument("--no-auto", action="store_true", help="Не использовать автоматическую разметку")
    
    args = parser.parse_args()
    
    try:
        import pandas as pd
    except ImportError:
        pd = None
    
    annotate_document(
        source_file=args.input,
        output_path=args.output,
        annotator=args.annotator,
        use_auto_annotation=not args.no_auto
    )

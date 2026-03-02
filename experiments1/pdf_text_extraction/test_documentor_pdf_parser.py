"""
Тестовый скрипт для запуска PDF parser из documentor на тестовых файлах.

Обрабатывает все PDF файлы из test_files/ и сохраняет результаты.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from langchain_core.documents import Document

# Добавляем путь к documentor в sys.path
# Путь: experiments/pdf_text_extraction -> experiments -> documentor_langchain (корень проекта)
_project_root = Path(__file__).resolve().parents[2]  # На уровень выше experiments
if _project_root.exists():
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

try:
    # Импортируем напрямую, минуя __init__.py который может импортировать pandas
    import importlib.util
    import types
    
    # Создаем заглушки для промежуточных пакетов
    for module_name in [
        "documentor",
        "documentor.domain",
        "documentor.processing",
        "documentor.processing.parsers",
        "documentor.processing.parsers.pdf",
    ]:
        if module_name not in sys.modules:
            sys.modules[module_name] = types.ModuleType(module_name)
    
    # Импортируем domain напрямую
    domain_models_path = _project_root / "documentor" / "domain" / "models.py"
    spec_domain = importlib.util.spec_from_file_location("documentor.domain.models", domain_models_path)
    domain_models = importlib.util.module_from_spec(spec_domain)
    # Регистрируем модуль в sys.modules перед выполнением (нужно для dataclass)
    sys.modules["documentor.domain.models"] = domain_models
    spec_domain.loader.exec_module(domain_models)
    ParsedDocument = domain_models.ParsedDocument
    ElementType = domain_models.ElementType
    
    # Импортируем pdf_parser напрямую
    pdf_parser_path = _project_root / "documentor" / "processing" / "parsers" / "pdf" / "pdf_parser.py"
    spec_parser = importlib.util.spec_from_file_location("documentor.processing.parsers.pdf.pdf_parser", pdf_parser_path)
    pdf_parser_module = importlib.util.module_from_spec(spec_parser)
    # Регистрируем модуль в sys.modules перед выполнением
    sys.modules["documentor.processing.parsers.pdf.pdf_parser"] = pdf_parser_module
    spec_parser.loader.exec_module(pdf_parser_module)
    PdfParser = pdf_parser_module.PdfParser
    
except Exception as e:
    import traceback
    print(f"Ошибка импорта: {e}")
    print(f"Убедитесь, что PYTHONPATH установлен на корень проекта:")
    print(f"  set PYTHONPATH=E:\\easy\\documentor\\documentor_langchain")
    print(f"Или запустите из корня проекта:")
    print(f"  cd E:\\easy\\documentor\\documentor_langchain")
    print(f"  python experiments\\pdf_text_extraction\\test_documentor_pdf_parser.py")
    traceback.print_exc()
    raise SystemExit(f"Не удалось импортировать documentor: {e}") from e


def process_pdf_file(pdf_path: Path, parser: PdfParser, output_dir: Path) -> Dict[str, Any]:
    """
    Обрабатывает один PDF файл.
    
    Args:
        pdf_path: Путь к PDF файлу
        parser: Экземпляр PdfParser
        output_dir: Директория для сохранения результатов
    
    Returns:
        Словарь с результатами обработки
    """
    print(f"\n{'='*80}")
    print(f"Обработка: {pdf_path.name}")
    print(f"{'='*80}")
    
    start_time = time.time()
    
    try:
        # Создаем LangChain Document
        document = Document(
            page_content="",  # Пустое содержимое, так как парсим из файла
            metadata={"source": str(pdf_path.absolute())}
        )
        
        # Парсим PDF
        parsed_doc: ParsedDocument = parser.parse(document)
        
        processing_time = time.time() - start_time
        
        # Создаем директорию для результатов
        pdf_output_dir = output_dir / pdf_path.stem
        pdf_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Сохраняем метаданные
        metadata_file = pdf_output_dir / "metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(parsed_doc.metadata, f, indent=2, ensure_ascii=False, default=str)
        
        # Сохраняем структуру документа
        structure_file = pdf_output_dir / "structure.json"
        structure = {
            "source": parsed_doc.source,
            "format": parsed_doc.format.value if hasattr(parsed_doc.format, "value") else str(parsed_doc.format),
            "total_elements": len(parsed_doc.elements),
            "elements": []
        }
        
        for element in parsed_doc.elements:
            element_type_name = element.type.name if hasattr(element.type, "name") else str(element.type)
            elem_data = {
                "id": element.id,
                "type": element_type_name,
                "content_preview": element.content[:200] + "..." if len(element.content) > 200 else element.content,
                "content_length": len(element.content),
                "parent_id": element.parent_id,
                "metadata_keys": list(element.metadata.keys()),
            }
            
            # Добавляем информацию о DataFrame для таблиц
            if element_type_name == "TABLE":
                has_dataframe = "dataframe" in element.metadata
                has_image = "image_data" in element.metadata
                elem_data["has_dataframe"] = has_dataframe
                elem_data["has_image"] = has_image
                if has_dataframe:
                    df = element.metadata["dataframe"]
                    if df is not None:
                        elem_data["dataframe_shape"] = f"{df.shape[0]}x{df.shape[1]}"
                        elem_data["dataframe_columns"] = list(df.columns) if hasattr(df, "columns") else []
            
            structure["elements"].append(elem_data)
        
        with open(structure_file, "w", encoding="utf-8") as f:
            json.dump(structure, f, indent=2, ensure_ascii=False, default=str)
        
        # Сохраняем полный текст документа
        full_text_file = pdf_output_dir / "full_text.txt"
        with open(full_text_file, "w", encoding="utf-8") as f:
            for element in parsed_doc.elements:
                if element.content:
                    f.write(f"\n{'='*80}\n")
                    f.write(f"ID: {element.id}\n")
                    f.write(f"Type: {element.type.name if hasattr(element.type, 'name') else element.type}\n")
                    f.write(f"Parent: {element.parent_id}\n")
                    f.write(f"{'='*80}\n")
                    f.write(element.content)
                    f.write("\n")
        
        # Сохраняем таблицы отдельно
        tables = parsed_doc.get_tables()
        if tables:
            tables_dir = pdf_output_dir / "tables"
            tables_dir.mkdir(exist_ok=True)
            
            for i, table in enumerate(tables):
                table_file = tables_dir / f"table_{i+1}.md"
                with open(table_file, "w", encoding="utf-8") as f:
                    f.write(f"# Table {i+1}\n\n")
                    f.write(f"ID: {table.id}\n")
                    f.write(f"Page: {table.metadata.get('page_num', 'N/A')}\n")
                    f.write(f"BBox: {table.metadata.get('bbox', [])}\n\n")
                    f.write("## Markdown Table\n\n")
                    f.write(table.content)
                    f.write("\n\n")
                    
                    # Информация о DataFrame
                    if "dataframe" in table.metadata:
                        df = table.metadata["dataframe"]
                        if df is not None:
                            f.write("## DataFrame Info\n\n")
                            f.write(f"Shape: {df.shape}\n")
                            f.write(f"Columns: {list(df.columns)}\n\n")
                            f.write("### DataFrame Preview\n\n")
                            f.write(df.head(10).to_markdown())
                            f.write("\n")
        
        # Статистика
        stats = {
            "processing_time_seconds": processing_time,
            "total_elements": len(parsed_doc.elements),
            "headers": len([e for e in parsed_doc.elements if e.type.name.startswith("HEADER")]),
            "text_blocks": len([e for e in parsed_doc.elements if e.type.name == "TEXT"]),
            "tables": len(tables),
            "images": len([e for e in parsed_doc.elements if e.type.name == "IMAGE"]),
            "captions": len([e for e in parsed_doc.elements if e.type.name == "CAPTION"]),
        }
        
        stats_file = pdf_output_dir / "stats.json"
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Успешно обработан за {processing_time:.2f} сек")
        print(f"  Элементов: {stats['total_elements']}")
        print(f"  Заголовков: {stats['headers']}")
        print(f"  Текстовых блоков: {stats['text_blocks']}")
        print(f"  Таблиц: {stats['tables']}")
        print(f"  Изображений: {stats['images']}")
        print(f"  Результаты сохранены в: {pdf_output_dir}")
        
        return {
            "success": True,
            "processing_time": processing_time,
            "stats": stats,
            "output_dir": str(pdf_output_dir),
        }
    
    except Exception as e:
        processing_time = time.time() - start_time
        error_msg = f"Ошибка при обработке {pdf_path.name}: {e}"
        print(f"✗ {error_msg}")
        
        return {
            "success": False,
            "processing_time": processing_time,
            "error": str(e),
        }


def main():
    """Основная функция."""
    # Пути
    script_dir = Path(__file__).parent
    test_files_dir = script_dir / "test_files"
    output_dir = script_dir / "results" / "documentor_pdf_parser"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Находим все PDF файлы
    pdf_files = list(test_files_dir.glob("*.pdf"))
    
    if not pdf_files:
        print(f"Не найдено PDF файлов в {test_files_dir}")
        return
    
    print(f"Найдено PDF файлов: {len(pdf_files)}")
    print(f"Выходная директория: {output_dir}")
    
    # Создаем парсер
    print("\nИнициализация PdfParser...")
    parser = PdfParser()
    print("✓ PdfParser инициализирован")
    
    # Обрабатываем каждый файл
    results: List[Dict[str, Any]] = []
    total_start_time = time.time()
    
    for pdf_file in pdf_files:
        result = process_pdf_file(pdf_file, parser, output_dir)
        results.append({
            "file": pdf_file.name,
            **result
        })
    
    total_time = time.time() - total_start_time
    
    # Сохраняем общую статистику
    summary = {
        "total_files": len(pdf_files),
        "successful": len([r for r in results if r.get("success", False)]),
        "failed": len([r for r in results if not r.get("success", False)]),
        "total_processing_time_seconds": total_time,
        "average_processing_time_seconds": total_time / len(pdf_files) if pdf_files else 0,
        "results": results,
    }
    
    summary_file = output_dir / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    
    # Выводим итоги
    print(f"\n{'='*80}")
    print("ИТОГИ")
    print(f"{'='*80}")
    print(f"Всего файлов: {summary['total_files']}")
    print(f"Успешно: {summary['successful']}")
    print(f"Ошибок: {summary['failed']}")
    print(f"Общее время: {total_time:.2f} сек")
    print(f"Среднее время на файл: {summary['average_processing_time_seconds']:.2f} сек")
    print(f"\nДетальная статистика сохранена в: {summary_file}")
    
    if summary['failed'] > 0:
        print("\nФайлы с ошибками:")
        for result in results:
            if not result.get("success", False):
                print(f"  - {result['file']}: {result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    main()

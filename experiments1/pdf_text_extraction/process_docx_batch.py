"""
Скрипт для пакетной обработки DOCX/DOC файлов с использованием Documentor библиотеки.

Обрабатывает все DOCX/DOC файлы в указанной папке и сохраняет результаты в JSON формате.
"""

import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from langchain_core.documents import Document

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from documentor import Pipeline
from documentor.exceptions import ParsingError, UnsupportedFormatError, ValidationError

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('docx_processing.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def process_docx_file(
    docx_path: Path,
    pipeline: Pipeline,
    output_dir: Path
) -> Dict[str, any]:
    """
    Обрабатывает один DOCX/DOC файл.
    
    Args:
        docx_path: Путь к DOCX/DOC файлу
        pipeline: Экземпляр Pipeline
        output_dir: Директория для сохранения результатов
    
    Returns:
        Словарь с результатами обработки
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"Обработка: {docx_path.name}")
    logger.info(f"{'='*80}")
    
    start_time = time.time()
    
    result = {
        "file_name": docx_path.name,
        "file_path": str(docx_path.absolute()),
        "status": "unknown",
        "error": None,
        "processing_time": None,
        "elements_count": 0,
        "output_file": None
    }
    
    try:
        # Создаем LangChain Document
        document = Document(
            page_content="",  # Пустое содержимое, так как парсим из файла
            metadata={"source": str(docx_path.absolute())}
        )
        
        # Парсим документ
        parsed_doc = pipeline.parse(document)
        
        processing_time = time.time() - start_time
        
        # Создаем директорию для результатов
        docx_output_dir = output_dir / docx_path.stem
        docx_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Сохраняем полный результат в JSON
        output_file = docx_output_dir / f"{docx_path.stem}_parsed.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json_str = parsed_doc.to_json()
            f.write(json_str)
        
        # Сохраняем краткую статистику
        stats_file = docx_output_dir / "stats.json"
        stats = {
            "file_name": docx_path.name,
            "file_path": str(docx_path.absolute()),
            "source": parsed_doc.source,
            "format": parsed_doc.format.value,
            "elements_count": len(parsed_doc.elements),
            "processing_time_seconds": round(processing_time, 2),
            "metadata": parsed_doc.metadata,
            "elements_by_type": {}
        }
        
        # Подсчитываем элементы по типам
        from documentor.domain import ElementType
        for elem in parsed_doc.elements:
            elem_type = elem.type.value
            stats["elements_by_type"][elem_type] = stats["elements_by_type"].get(elem_type, 0) + 1
        
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        
        result.update({
            "status": "success",
            "processing_time": round(processing_time, 2),
            "elements_count": len(parsed_doc.elements),
            "output_file": str(output_file),
            "format": parsed_doc.format.value
        })
        
        logger.info(f"✓ Успешно обработан: {docx_path.name}")
        logger.info(f"  Элементов: {len(parsed_doc.elements)}")
        logger.info(f"  Время обработки: {processing_time:.2f} сек")
        logger.info(f"  Результат сохранен: {output_file}")
        
    except UnsupportedFormatError as e:
        result.update({
            "status": "unsupported_format",
            "error": str(e),
            "processing_time": time.time() - start_time
        })
        logger.warning(f"✗ Неподдерживаемый формат: {docx_path.name} - {e}")
        
    except ValidationError as e:
        result.update({
            "status": "validation_error",
            "error": str(e),
            "processing_time": time.time() - start_time
        })
        logger.error(f"✗ Ошибка валидации: {docx_path.name} - {e}")
        
    except ParsingError as e:
        result.update({
            "status": "parsing_error",
            "error": str(e),
            "processing_time": time.time() - start_time
        })
        logger.error(f"✗ Ошибка парсинга: {docx_path.name} - {e}")
        
    except Exception as e:
        result.update({
            "status": "error",
            "error": f"{type(e).__name__}: {str(e)}",
            "processing_time": time.time() - start_time
        })
        logger.error(f"✗ Неожиданная ошибка: {docx_path.name} - {e}", exc_info=True)
    
    return result


def process_all_documents(
    input_dir: Path,
    output_dir: Path,
    max_files: Optional[int] = None
) -> List[Dict[str, any]]:
    """
    Обрабатывает DOCX/DOC файлы в указанной директории.
    
    Args:
        input_dir: Директория с исходными файлами
        output_dir: Директория для сохранения результатов
        max_files: Максимальное количество файлов для обработки (None = все)
    
    Returns:
        Список результатов обработки
    """
    # Создаем выходную директорию
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Инициализируем пайплайн
    logger.info("Инициализация пайплайна...")
    pipeline = Pipeline()
    logger.info("Пайплайн инициализирован")
    
    # Находим все DOCX и DOC файлы
    all_files = list(input_dir.glob("*.docx")) + list(input_dir.glob("*.doc"))
    
    # Сортируем по размеру (от меньшего к большему)
    files_with_size = [(f.stat().st_size, f) for f in all_files]
    files_with_size.sort(key=lambda x: x[0])
    
    logger.info(f"\nНайдено файлов в директории: {len(all_files)}")
    
    # Выбираем самые маленькие файлы
    if max_files is not None:
        selected_files = [f for _, f in files_with_size[:max_files]]
        logger.info(f"\nВыбрано {max_files} самых маленьких файлов:")
        for size, f in files_with_size[:max_files]:
            logger.info(f"  - {f.name} ({size:,} bytes / {size/1024:.1f} KB)")
        docx_files = selected_files
    else:
        docx_files = [f for _, f in files_with_size]
        logger.info(f"\nОбработка всех файлов (отсортированы по размеру)")
    
    logger.info(f"Файлов для обработки: {len(docx_files)}")
    
    if not docx_files:
        logger.warning(f"Не найдено DOCX/DOC файлов в директории: {input_dir}")
        return []
    
    # Обрабатываем каждый файл
    results = []
    total_start_time = time.time()
    
    for i, docx_file in enumerate(docx_files, 1):
        logger.info(f"\n[{i}/{len(docx_files)}] Обработка файла: {docx_file.name}")
        
        try:
            result = process_docx_file(docx_file, pipeline, output_dir)
            results.append(result)
        except Exception as e:
            logger.error(f"Критическая ошибка при обработке {docx_file.name}: {e}", exc_info=True)
            results.append({
                "file_name": docx_file.name,
                "file_path": str(docx_file.absolute()),
                "status": "critical_error",
                "error": f"{type(e).__name__}: {str(e)}",
                "processing_time": None,
                "elements_count": 0,
                "output_file": None
            })
    
    total_time = time.time() - total_start_time
    
    # Сохраняем общую статистику
    summary = {
        "total_files": len(docx_files),
        "processed_files": len([r for r in results if r["status"] == "success"]),
        "failed_files": len([r for r in results if r["status"] != "success"]),
        "total_processing_time_seconds": round(total_time, 2),
        "average_processing_time_seconds": round(total_time / len(docx_files), 2) if docx_files else 0,
        "results": results
    }
    
    summary_file = output_dir / "processing_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    logger.info(f"\n{'='*80}")
    logger.info("ОБРАБОТКА ЗАВЕРШЕНА")
    logger.info(f"{'='*80}")
    logger.info(f"Всего файлов: {len(docx_files)}")
    logger.info(f"Успешно обработано: {summary['processed_files']}")
    logger.info(f"Ошибок: {summary['failed_files']}")
    logger.info(f"Общее время: {total_time:.2f} сек")
    logger.info(f"Среднее время на файл: {summary['average_processing_time_seconds']:.2f} сек")
    logger.info(f"Сводка сохранена: {summary_file}")
    
    return results


if __name__ == "__main__":
    # Путь к директории с документами
    input_directory = Path(__file__).parent / "OneDrive_1_12.02.2026"
    
    # Путь к директории для результатов
    output_directory = Path(__file__).parent / "docx_processing_results"
    
    if not input_directory.exists():
        logger.error(f"Директория с документами не найдена: {input_directory}")
        sys.exit(1)
    
    logger.info(f"Входная директория: {input_directory}")
    logger.info(f"Выходная директория: {output_directory}")
    
    # Обрабатываем только 2 документа
    max_files_to_process = 2
    
    # Запускаем обработку
    process_all_documents(input_directory, output_directory, max_files=max_files_to_process)

"""
Пакетная оценка всех документов для всех парсеров.
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Dict
import time


def find_annotation_files(annotations_dir: Path) -> Dict[str, Path]:
    """Находит все файлы разметки."""
    annotations = {}
    
    for ann_file in annotations_dir.glob("*_annotation.json"):
        # Извлекаем document_id из имени файла
        doc_id = ann_file.stem.replace("_annotation", "")
        annotations[doc_id] = ann_file
    
    return annotations


def find_source_files(source_dir: Path, document_ids: List[str]) -> Dict[str, Path]:
    """Находит исходные файлы документов."""
    source_files = {}
    
    # Ищем файлы с соответствующими именами
    for doc_id in document_ids:
        # Пробуем разные расширения
        for ext in [".pdf", ".docx", ".doc"]:
            file_path = source_dir / f"{doc_id}{ext}"
            if file_path.exists():
                source_files[doc_id] = file_path
                break
    
    return source_files


def run_batch_evaluation(
    annotations_dir: Path,
    source_dir: Path,
    results_dir: Path,
    parsers: List[str] = None
) -> None:
    """
    Запускает пакетную оценку.
    
    Args:
        annotations_dir: Директория с разметками
        source_dir: Директория с исходными документами
        results_dir: Директория для сохранения результатов
        parsers: Список парсеров для оценки (None = все)
    """
    if parsers is None:
        parsers = ["documentor", "marker", "dedoc"]
    
    # Находим разметки
    annotations = find_annotation_files(annotations_dir)
    print(f"Найдено разметок: {len(annotations)}")
    
    # Находим исходные файлы
    source_files = find_source_files(source_dir, list(annotations.keys()))
    print(f"Найдено исходных файлов: {len(source_files)}")
    
    if not annotations:
        print("Не найдено файлов разметки!")
        return
    
    if not source_files:
        print("Не найдено исходных файлов!")
        return
    
    # Оцениваем каждый документ для каждого парсера
    total_tasks = len(parsers) * len(annotations)
    current_task = 0
    
    for parser_name in parsers:
        print(f"\n{'='*60}")
        print(f"Оценка парсера: {parser_name}")
        print(f"{'='*60}")
        
        parser_results_dir = results_dir / parser_name
        parser_results_dir.mkdir(parents=True, exist_ok=True)
        
        for doc_id, ann_file in annotations.items():
            if doc_id not in source_files:
                print(f"Пропуск {doc_id}: исходный файл не найден")
                continue
            
            source_file = source_files[doc_id]
            current_task += 1
            
            print(f"\n[{current_task}/{total_tasks}] {doc_id} ({parser_name})")
            
            try:
                # Запускаем оценку
                cmd = [
                    sys.executable,
                    "run_evaluation.py",
                    "--parser", parser_name,
                    "--input", str(source_file),
                    "--annotation", str(ann_file),
                    "--output", str(parser_results_dir)
                ]
                
                start_time = time.time()
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).parent)
                elapsed = time.time() - start_time
                
                if result.returncode == 0:
                    print(f"  ✓ Успешно ({elapsed:.1f}с)")
                else:
                    print(f"  ✗ Ошибка: {result.stderr}")
                    
            except Exception as e:
                print(f"  ✗ Исключение: {e}")
    
    print(f"\n{'='*60}")
    print("Пакетная оценка завершена!")
    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Пакетная оценка документов")
    parser.add_argument("--annotations", "-a", type=Path, required=True,
                       help="Директория с разметками")
    parser.add_argument("--source", "-s", type=Path, required=True,
                       help="Директория с исходными документами")
    parser.add_argument("--results", "-r", type=Path, required=True,
                       help="Директория для сохранения результатов")
    parser.add_argument("--parsers", "-p", nargs="+",
                       choices=["documentor", "marker", "dedoc"],
                       default=None,
                       help="Парсеры для оценки (по умолчанию все)")
    
    args = parser.parse_args()
    
    run_batch_evaluation(
        annotations_dir=args.annotations,
        source_dir=args.source,
        results_dir=args.results,
        parsers=args.parsers
    )

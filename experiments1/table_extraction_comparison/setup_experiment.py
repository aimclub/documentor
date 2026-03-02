#!/usr/bin/env python3
"""
Скрипт для инициализации эксперимента по сравнению методов извлечения таблиц.
"""

import shutil
from pathlib import Path

def setup_experiment_directories(base_dir: Path):
    """Создает необходимую структуру директорий для эксперимента."""
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "test_files").mkdir(exist_ok=True)
    (base_dir / "results").mkdir(exist_ok=True)
    print(f"Создана структура директорий в {base_dir}")

def copy_pdf_files(source_dir: Path, destination_dir: Path):
    """Копирует все PDF файлы из исходной директории в целевую."""
    copied_files = []
    for pdf_file in source_dir.glob("*.pdf"):
        destination_path = destination_dir / pdf_file.name
        shutil.copy(pdf_file, destination_path)
        copied_files.append(pdf_file.name)
        print(f"Скопирован: {pdf_file.name}")
    return copied_files

if __name__ == "__main__":
    experiment_dir = Path(__file__).parent
    setup_experiment_directories(experiment_dir)

    source_pdfs_dir = Path(__file__).parent.parent / "metrics" / "test_files_for_metrics"
    destination_pdfs_dir = experiment_dir / "test_files"
    
    print(f"Исходная директория PDF: {source_pdfs_dir}")
    print(f"Целевая директория PDF: {destination_pdfs_dir}")
    
    found_pdfs = [f.name for f in source_pdfs_dir.glob("*.pdf")]
    print(f"Найдено PDF в исходной директории: {found_pdfs}")

    copied = copy_pdf_files(source_pdfs_dir, destination_pdfs_dir)
    print(f"Скопировано: {copied}")

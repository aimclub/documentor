#!/usr/bin/env python3
"""
Скрипт для создания структуры эксперимента.
"""

import shutil
from pathlib import Path

# Пути
project_root = Path(__file__).parent.parent.parent
experiment_dir = Path(__file__).parent
test_files_source = project_root / "experiments" / "metrics" / "test_files_for_metrics"
test_files_dest = experiment_dir / "test_files"

# Создаем директории
(experiment_dir / "test_files").mkdir(exist_ok=True)
(experiment_dir / "results").mkdir(exist_ok=True)
(experiment_dir / "ground_truth").mkdir(exist_ok=True)

# Копируем PDF файлы
pdf_files = list(test_files_source.glob("*.pdf"))
print(f"Найдено {len(pdf_files)} PDF файлов")

for pdf_file in pdf_files:
    dest = test_files_dest / pdf_file.name
    shutil.copy2(pdf_file, dest)
    print(f"Скопирован: {pdf_file.name}")

print(f"\n✓ Структура эксперимента создана в: {experiment_dir}")

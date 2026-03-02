#!/usr/bin/env python3
"""
Скрипт для пакетной обработки всех PDF файлов в test_files.
"""

import subprocess
import sys
import time
from pathlib import Path

def run_pipeline_for_all_pdfs():
    """
    Находит все PDF файлы в директории test_files
    и запускает pipeline.py для каждого.
    """
    script_dir = Path(__file__).parent
    test_files_dir = script_dir / "test_files"
    
    if not test_files_dir.is_dir():
        print(f"Ошибка: Директория {test_files_dir} не найдена.")
        print("Пожалуйста, убедитесь, что вы запустили setup_experiment.py.")
        sys.exit(1)
    
    pdf_files = list(test_files_dir.glob("*.pdf"))
    
    if not pdf_files:
        print(f"В директории {test_files_dir} не найдено PDF файлов.")
        sys.exit(0)
    
    print(f"Найдено {len(pdf_files)} PDF файлов для обработки.")
    
    start_time_total = time.time()
    
    for pdf_file in pdf_files:
        print(f"\n{'='*80}")
        print(f"Обработка: {pdf_file.name}")
        print(f"{'='*80}")
        try:
            result = subprocess.run(
                [sys.executable, str(script_dir / "pipeline.py"), str(pdf_file)],
                capture_output=True,
                text=True,
                check=True
            )
            print(result.stdout)
            if result.stderr:
                print(f"Предупреждения для {pdf_file.name}:\n{result.stderr}")
        except subprocess.CalledProcessError as e:
            print(f"Ошибка при обработке {pdf_file.name}:")
            print(e.stdout)
            print(e.stderr)
        except Exception as e:
            print(f"Непредвиденная ошибка при обработке {pdf_file.name}: {e}")
    
    time_total = time.time() - start_time_total
    
    print(f"\n{'='*80}")
    print("ПАКЕТНАЯ ОБРАБОТКА ЗАВЕРШЕНА")
    print(f"{'='*80}")
    print(f"Общее время: {time_total:.2f} сек ({time_total/60:.2f} мин)")
    print(f"Результаты сохранены в: {script_dir / 'results'}")

if __name__ == "__main__":
    run_pipeline_for_all_pdfs()

#!/usr/bin/env python3
"""
Скрипт для пакетной обработки всех PDF файлов в test_files.
"""

import sys
import time
from pathlib import Path

# Добавляем путь к корню проекта
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from pipeline import process_pdf

def main():
    """Обрабатывает все PDF файлы."""
    experiment_dir = Path(__file__).parent
    test_files_dir = experiment_dir / "test_files"
    results_dir = experiment_dir / "results"
    
    results_dir.mkdir(parents=True, exist_ok=True)
    
    pdf_files = list(test_files_dir.glob("*.pdf"))
    
    if not pdf_files:
        print(f"Не найдено PDF файлов в {test_files_dir}")
        return
    
    print(f"Найдено {len(pdf_files)} PDF файлов")
    
    all_results = {}
    start_time_total = time.time()
    
    for pdf_file in pdf_files:
        try:
            print(f"\n{'='*80}")
            print(f"Обработка: {pdf_file.name}")
            print(f"{'='*80}")
            
            results = process_pdf(pdf_file, results_dir)
            all_results[pdf_file.name] = results
            
        except Exception as e:
            print(f"\n✗ Ошибка при обработке {pdf_file.name}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    time_total = time.time() - start_time_total
    
    # Сводный отчет
    print(f"\n{'='*80}")
    print("СВОДНЫЙ ОТЧЕТ ПО ВСЕМ ФАЙЛАМ")
    print(f"{'='*80}")
    
    total_time_method1 = 0
    total_time_method2 = 0
    total_blocks_method1 = 0
    total_blocks_method2 = 0
    
    for pdf_name, results in all_results.items():
        print(f"\n{pdf_name}:")
        method1_agg = results["method1"]["aggregated"]
        method2_agg = results["method2"]["aggregated"]
        timing = results.get("timing", {})
        
        time1 = timing.get("method1_seconds", 0)
        time2 = timing.get("method2_seconds", 0)
        
        total_time_method1 += time1
        total_time_method2 += time2
        total_blocks_method1 += method1_agg.get('total_blocks', 0)
        total_blocks_method2 += method2_agg.get('total_blocks', 0)
        
        print(f"  Метод 1 - CER: {method1_agg.get('avg_cer', 0):.4f}, WER: {method1_agg.get('avg_wer', 'N/A')}, "
              f"Время: {time1:.2f} сек ({time1/60:.2f} мин), Блоков: {method1_agg.get('total_blocks', 0)}")
        print(f"  Метод 2 - CER: {method2_agg.get('avg_cer', 0):.4f}, WER: {method2_agg.get('avg_wer', 'N/A')}, "
              f"Время: {time2:.2f} сек ({time2/60:.2f} мин), Блоков: {method2_agg.get('total_blocks', 0)}")
    
    print(f"\n{'='*80}")
    print("ОБЩАЯ СТАТИСТИКА")
    print(f"{'='*80}")
    print(f"Всего файлов обработано: {len(all_results)}")
    print(f"Общее время: {time_total:.2f} сек ({time_total/60:.2f} мин)")
    print(f"\nМетод 1 (layout_all_en):")
    print(f"  Общее время: {total_time_method1:.2f} сек ({total_time_method1/60:.2f} мин)")
    print(f"  Всего блоков: {total_blocks_method1}")
    if total_blocks_method1 > 0:
        print(f"  Среднее время на блок: {total_time_method1/total_blocks_method1:.2f} сек")
    print(f"\nМетод 2 (layout_only_en + Qwen):")
    print(f"  Общее время: {total_time_method2:.2f} сек ({total_time_method2/60:.2f} мин)")
    print(f"  Всего блоков: {total_blocks_method2}")
    if total_blocks_method2 > 0:
        print(f"  Среднее время на блок: {total_time_method2/total_blocks_method2:.2f} сек")
    
    print(f"\n✓ Обработка всех файлов завершена")
    print(f"Результаты сохранены в: {results_dir}")


if __name__ == "__main__":
    main()

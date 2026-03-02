"""
Скрипт для запуска пайплайна сохранения структуры заголовков на всех DOCX файлах.
"""

import sys
from pathlib import Path

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from experiments.pdf_text_extraction.docx_header_structure_pipeline import process_header_structure_pipeline

# Список DOCX файлов для обработки
test_folder = Path(__file__).parent / "test_folder"

docx_files = [
    "Диплом.docx",
    "02_Отчет_Этап_2_полный_замечания_эксперта.docx",
    "Diplom2024.docx",
    # "Отчёт ГОСТ.docx",  # Убрали, там нет изображений
]

# Выходная директория для результатов
output_base_dir = Path(__file__).parent / "results" / "header_structure"


def main():
    print("=" * 80)
    print("ПАЙПЛАЙН СОХРАНЕНИЯ СТРУКТУРЫ ЗАГОЛОВКОВ ИЗ DOTS OCR")
    print("=" * 80)
    print(f"Всего файлов для обработки: {len(docx_files)}\n")
    
    results = []
    
    for docx_file in docx_files:
        docx_path = test_folder / docx_file
        
        if not docx_path.exists():
            print(f"⚠ Файл не найден: {docx_path}")
            continue
        
        print(f"\n{'='*80}")
        print(f"Обработка: {docx_file}")
        print(f"{'='*80}\n")
        
        output_dir = output_base_dir / docx_path.stem
        
        try:
            result = process_header_structure_pipeline(
                docx_path=docx_path,
                output_dir=output_dir,
                limit=None  # Обрабатываем все страницы
            )
            
            if "error" in result:
                print(f"✗ Ошибка при обработке {docx_file}: {result['error']}")
                results.append({
                    "file": docx_file,
                    "status": "error",
                    "error": result["error"]
                })
            else:
                print(f"✓ Успешно обработан: {docx_file}")
                results.append({
                    "file": docx_file,
                    "status": "success",
                    "docx_headers_count": result.get("docx_headers_count", 0),
                    "ocr_headers_count": result.get("ocr_headers_count", 0),
                    "match_methods": result.get("match_methods", {}),
                    "level_distribution": result.get("level_distribution", {}),
                })
        
        except Exception as e:
            print(f"✗ Исключение при обработке {docx_file}: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "file": docx_file,
                "status": "exception",
                "error": str(e)
            })
    
    # Итоговая статистика
    print(f"\n{'='*80}")
    print("ИТОГОВАЯ СТАТИСТИКА")
    print(f"{'='*80}\n")
    
    successful = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] != "success"]
    
    print(f"Успешно обработано: {len(successful)}/{len(results)}")
    print(f"Ошибок: {len(failed)}/{len(results)}\n")
    
    if successful:
        print("Детализация по файлам:")
        print("-" * 80)
        for result in successful:
            print(f"\n{result['file']}:")
            print(f"  Заголовков в DOCX: {result.get('docx_headers_count', 0)}")
            print(f"  Заголовков в OCR: {result.get('ocr_headers_count', 0)}")
            
            match_methods = result.get("match_methods", {})
            if match_methods:
                print(f"  Методы сопоставления:")
                for method, count in match_methods.items():
                    print(f"    {method}: {count}")
            
            level_distribution = result.get("level_distribution", {})
            if level_distribution:
                print(f"  Распределение по уровням:")
                for level in sorted(level_distribution.keys()):
                    count = level_distribution[level]
                    print(f"    HEADER_{level}: {count}")
    
    if failed:
        print(f"\nОшибки:")
        print("-" * 80)
        for result in failed:
            print(f"  {result['file']}: {result.get('error', 'Unknown error')}")
    
    print(f"\n{'='*80}")
    print("ОБРАБОТКА ЗАВЕРШЕНА")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()

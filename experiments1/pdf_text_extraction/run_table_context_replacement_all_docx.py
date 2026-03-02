"""
Скрипт для запуска пайплайна замены OCR-таблиц на структуру из DOCX
через текстовый контекст на всех DOCX файлах.
"""

import sys
from pathlib import Path

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from experiments.pdf_text_extraction.docx_table_context_replacement import process_table_context_replacement

# Путь к папке с DOCX файлами
TEST_FOLDER = Path(r"E:\easy\documentor\documentor_langchain\experiments\pdf_text_extraction\test_folder")

# Список DOCX файлов для обработки
DOCX_FILES = [
    "Отчёт НИР Хаухия АВ.docx",
    "02_Отчет_Этап_2_полный_замечания_эксперта.docx",
    "Диплом.docx",
    "Diplom2024.docx",
]


def main():
    """Запускает пайплайн на всех DOCX файлах."""
    print(f"\n{'='*80}")
    print(f"Запуск пайплайна замены OCR-таблиц на структуру из DOCX через контекст")
    print(f"Папка с файлами: {TEST_FOLDER}")
    print(f"{'='*80}\n")
    
    if not TEST_FOLDER.exists():
        print(f"Ошибка: папка {TEST_FOLDER} не существует")
        sys.exit(1)
    
    results_summary = []
    
    for docx_filename in DOCX_FILES:
        docx_path = TEST_FOLDER / docx_filename
        
        if not docx_path.exists():
            print(f"Предупреждение: файл {docx_path} не найден, пропускаем")
            continue
        
        print(f"\n{'='*80}")
        print(f"Обработка: {docx_filename}")
        print(f"{'='*80}\n")
        
        # Определяем выходную директорию
        base_output = Path(__file__).parent / "results" / "table_context_replacement"
        output_dir = base_output / docx_path.stem
        
        try:
            result = process_table_context_replacement(
                docx_path,
                output_dir,
                limit=None  # Обрабатываем все таблицы
            )
            
            if "error" in result:
                print(f"  ✗ Ошибка при обработке {docx_filename}: {result['error']}")
                results_summary.append({
                    "file": docx_filename,
                    "status": "error",
                    "error": result["error"]
                })
            else:
                results_summary.append({
                    "file": docx_filename,
                    "status": "success",
                    "total_docx_tables": result.get("total_docx_tables", 0),
                    "total_ocr_tables": result.get("total_ocr_tables", 0),
                    "matched_tables": result.get("matched_tables", 0),
                    "not_found_tables": result.get("not_found_tables", 0),
                })
                print(f"  ✓ Успешно обработан {docx_filename}")
        
        except Exception as e:
            print(f"  ✗ Исключение при обработке {docx_filename}: {e}")
            import traceback
            traceback.print_exc()
            results_summary.append({
                "file": docx_filename,
                "status": "exception",
                "error": str(e)
            })
    
    # Выводим итоговую статистику
    print(f"\n{'='*80}")
    print(f"ИТОГОВАЯ СТАТИСТИКА")
    print(f"{'='*80}\n")
    
    total_docx = sum(r.get("total_docx_tables", 0) for r in results_summary if r.get("status") == "success")
    total_ocr = sum(r.get("total_ocr_tables", 0) for r in results_summary if r.get("status") == "success")
    total_matched = sum(r.get("matched_tables", 0) for r in results_summary if r.get("status") == "success")
    total_not_found = sum(r.get("not_found_tables", 0) for r in results_summary if r.get("status") == "success")
    
    print(f"Всего файлов обработано: {len([r for r in results_summary if r.get('status') == 'success'])}")
    print(f"Всего таблиц найдено в DOCX: {total_docx}")
    print(f"Всего таблиц найдено через OCR: {total_ocr}")
    print(f"Совпадений найдено: {total_matched}")
    print(f"Не найдено совпадений: {total_not_found}")
    
    if total_ocr > 0:
        match_rate = (total_matched / total_ocr) * 100
        print(f"Процент совпадений: {match_rate:.1f}%")
    
    print(f"\nДетали по файлам:")
    for r in results_summary:
        if r.get("status") == "success":
            print(f"  {r['file']}:")
            print(f"    DOCX таблиц: {r.get('total_docx_tables', 0)}")
            print(f"    OCR таблиц: {r.get('total_ocr_tables', 0)}")
            print(f"    Совпадений: {r.get('matched_tables', 0)}")
            print(f"    Не найдено: {r.get('not_found_tables', 0)}")
        else:
            print(f"  {r['file']}: {r.get('status', 'unknown')} - {r.get('error', '')}")


if __name__ == "__main__":
    main()

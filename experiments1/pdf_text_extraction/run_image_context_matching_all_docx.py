"""
Скрипт для запуска пайплайна сопоставления изображений через текстовый контекст
на всех DOCX файлах.
"""

import sys
from pathlib import Path

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from experiments.pdf_text_extraction.docx_image_context_matching import process_image_context_matching

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
    print(f"Запуск пайплайна сопоставления изображений через текстовый контекст")
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
        base_output = Path(__file__).parent / "results" / "image_context_matching"
        output_dir = base_output / docx_path.stem
        
        try:
            result = process_image_context_matching(
                docx_path,
                output_dir,
                limit=None  # Обрабатываем все изображения
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
                    "total_docx_images": result.get("total_docx_images", 0),
                    "total_ocr_images": result.get("total_ocr_images", 0),
                    "matched_images": result.get("matched_images", 0),
                    "not_found_images": result.get("not_found_images", 0),
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
    
    total_docx = sum(r.get("total_docx_images", 0) for r in results_summary if r.get("status") == "success")
    total_ocr = sum(r.get("total_ocr_images", 0) for r in results_summary if r.get("status") == "success")
    total_matched = sum(r.get("matched_images", 0) for r in results_summary if r.get("status") == "success")
    total_not_found = sum(r.get("not_found_images", 0) for r in results_summary if r.get("status") == "success")
    
    print(f"Всего файлов обработано: {len([r for r in results_summary if r.get('status') == 'success'])}")
    print(f"Всего изображений найдено в DOCX: {total_docx}")
    print(f"Всего изображений найдено через OCR: {total_ocr}")
    print(f"Совпадений найдено: {total_matched}")
    print(f"Не найдено совпадений: {total_not_found}")
    
    if total_docx > 0:
        match_rate = (total_matched / total_docx) * 100
        print(f"Процент совпадений: {match_rate:.1f}%")
    
    print(f"\nДетали по файлам:")
    for r in results_summary:
        if r.get("status") == "success":
            print(f"  {r['file']}:")
            print(f"    DOCX изображений: {r.get('total_docx_images', 0)}")
            print(f"    OCR изображений: {r.get('total_ocr_images', 0)}")
            print(f"    Совпадений: {r.get('matched_images', 0)}")
            print(f"    Не найдено: {r.get('not_found_images', 0)}")
        else:
            print(f"  {r['file']}: {r.get('status', 'unknown')} - {r.get('error', '')}")


if __name__ == "__main__":
    main()

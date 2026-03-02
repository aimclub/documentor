"""
Скрипт для запуска эксперимента по сопоставлению изображений на всех DOCX файлах.
"""

import sys
from pathlib import Path

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from experiments.pdf_text_extraction.docx_image_matching_experiment import process_image_experiment

# Путь к папке с DOCX файлами (как в docx_hybrid_pipeline.py)
TEST_FOLDER = Path(r"E:\easy\documentor\documentor_langchain\experiments\pdf_text_extraction\test_folder")

# Список DOCX файлов для обработки (те же файлы, что использовались в docx_hybrid_pipeline.py)
# Исключены файлы без изображений
DOCX_FILES = [
    "Отчёт НИР Хаухия АВ.docx",
    "02_Отчет_Этап_2_полный_замечания_эксперта.docx",
    "Диплом.docx",
    "Diplom2024.docx",
]


def main():
    """Запускает эксперимент на всех DOCX файлах."""
    print(f"\n{'='*80}")
    print(f"Запуск эксперимента по сопоставлению изображений на всех DOCX файлах")
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
        base_output = Path(__file__).parent / "results" / "image_matching"
        output_dir = base_output / docx_path.stem
        
        try:
            result = process_image_experiment(
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
                    "total_ocr_images": result.get("total_ocr_images", 0),
                    "total_docx_images": result.get("total_docx_images", 0),
                    "matched_images": result.get("matched_images", 0),
                    "not_found_images": result.get("not_found_images", 0),
                    "method_statistics": result.get("method_statistics", {}),
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
    
    # Выводим итоговую сводку
    print(f"\n{'='*80}")
    print(f"ИТОГОВАЯ СВОДКА")
    print(f"{'='*80}\n")
    
    successful = [r for r in results_summary if r["status"] == "success"]
    failed = [r for r in results_summary if r["status"] != "success"]
    
    print(f"Успешно обработано: {len(successful)}")
    print(f"Ошибок: {len(failed)}\n")
    
    if successful:
        print("Статистика по успешно обработанным файлам:")
        print("-" * 80)
        
        total_ocr = sum(r["total_ocr_images"] for r in successful)
        total_docx = sum(r["total_docx_images"] for r in successful)
        total_matched = sum(r["matched_images"] for r in successful)
        total_not_found = sum(r["not_found_images"] for r in successful)
        
        # Статистика по методам
        method1_total = sum(r["method_statistics"].get("method1_normalized_ssim", {}).get("found_count", 0) for r in successful)
        method2_total = sum(r["method_statistics"].get("method2_orb_feature_matching", {}).get("found_count", 0) for r in successful)
        method3_total = sum(r["method_statistics"].get("method3_perceptual_hash", {}).get("found_count", 0) for r in successful)
        
        print(f"Всего изображений в OCR: {total_ocr}")
        print(f"Всего изображений в DOCX: {total_docx}")
        print(f"Всего совпадений найдено: {total_matched}")
        print(f"Всего не найдено: {total_not_found}")
        print(f"\nСтатистика по методам:")
        print(f"  Метод 1 (Normalized SSIM): найдено {method1_total}")
        print(f"  Метод 2 (ORB Feature Matching): найдено {method2_total}")
        print(f"  Метод 3 (Perceptual Hash): найдено {method3_total}")
        
        print(f"\nДетали по файлам:")
        for r in successful:
            print(f"  {r['file']}:")
            print(f"    OCR: {r['total_ocr_images']}, DOCX: {r['total_docx_images']}, Совпадений: {r['matched_images']}")
            m1 = r["method_statistics"].get("method1_normalized_ssim", {})
            m2 = r["method_statistics"].get("method2_orb_ransac", {})
            m3 = r["method_statistics"].get("method3_perceptual_hash", {})
            print(f"    Метод 1: {m1.get('found_count', 0)} (score: {m1.get('average_score', 0):.2%})")
            m2 = r["method_statistics"].get("method2_orb_feature_matching", {})
            print(f"    Метод 2: {m2.get('found_count', 0)} (score: {m2.get('average_score', 0):.2%})")
            print(f"    Метод 3: {m3.get('found_count', 0)} (score: {m3.get('average_score', 0):.2%})")
    
    if failed:
        print(f"\nОшибки:")
        for r in failed:
            print(f"  {r['file']}: {r.get('error', 'Unknown error')}")
    
    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    main()

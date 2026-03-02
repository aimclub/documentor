"""
Скрипт для запуска всех тестов извлечения из PDF и сохранения результатов в файлы.
"""

import sys
from pathlib import Path
from datetime import datetime
import io
from contextlib import redirect_stdout

# Добавляем путь к скриптам
sys.path.insert(0, str(Path(__file__).parent))

from test_basic_extraction import (
    test_basic_text_extraction,
    test_text_with_metadata,
    test_characters_extraction,
)
from test_table_extraction import (
    test_find_tables,
    test_extract_table_data,
    test_table_settings,
    test_table_bbox,
)
from test_structure_extraction import test_structure_extraction


def run_test_and_capture(func, *args, **kwargs):
    """Запускает тест и захватывает вывод."""
    f = io.StringIO()
    with redirect_stdout(f):
        try:
            func(*args, **kwargs)
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
    return f.getvalue()


def test_single_pdf(pdf_path: Path, output_dir: Path):
    """Запускает все тесты для одного PDF и сохраняет результаты."""
    pdf_name = pdf_path.stem
    print(f"\n{'='*80}")
    print(f"Processing: {pdf_path.name}")
    print(f"{'='*80}\n")
    
    results = []
    results.append(f"{'='*80}\n")
    results.append(f"PDF File: {pdf_path.name}\n")
    results.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    results.append(f"{'='*80}\n\n")
    
    # 1. Базовое извлечение текста
    print("[1/7] Basic text extraction...")
    results.append("=" * 80 + "\n")
    results.append("1. BASIC TEXT EXTRACTION\n")
    results.append("=" * 80 + "\n\n")
    output = run_test_and_capture(test_basic_text_extraction, pdf_path)
    results.append(output)
    results.append("\n\n")
    
    # 2. Текст с метаданными
    print("[2/7] Text with metadata...")
    results.append("=" * 80 + "\n")
    results.append("2. TEXT WITH METADATA\n")
    results.append("=" * 80 + "\n\n")
    output = run_test_and_capture(test_text_with_metadata, pdf_path)
    results.append(output)
    results.append("\n\n")
    
    # 3. Извлечение символов
    print("[3/7] Character extraction...")
    results.append("=" * 80 + "\n")
    results.append("3. CHARACTER EXTRACTION\n")
    results.append("=" * 80 + "\n\n")
    output = run_test_and_capture(test_characters_extraction, pdf_path)
    results.append(output)
    results.append("\n\n")
    
    # 4. Поиск таблиц
    print("[4/7] Finding tables...")
    results.append("=" * 80 + "\n")
    results.append("4. FINDING TABLES\n")
    results.append("=" * 80 + "\n\n")
    output = run_test_and_capture(test_find_tables, pdf_path)
    results.append(output)
    results.append("\n\n")
    
    # 5. Извлечение данных таблиц
    print("[5/7] Extracting table data...")
    results.append("=" * 80 + "\n")
    results.append("5. EXTRACTING TABLE DATA\n")
    results.append("=" * 80 + "\n\n")
    output = run_test_and_capture(test_extract_table_data, pdf_path)
    results.append(output)
    results.append("\n\n")
    
    # 6. Настройки извлечения таблиц
    print("[6/7] Table extraction settings...")
    results.append("=" * 80 + "\n")
    results.append("6. TABLE EXTRACTION SETTINGS\n")
    results.append("=" * 80 + "\n\n")
    output = run_test_and_capture(test_table_settings, pdf_path)
    results.append(output)
    results.append("\n\n")
    
    # 7. Извлечение структуры
    print("[7/7] Structure extraction...")
    results.append("=" * 80 + "\n")
    results.append("7. STRUCTURE EXTRACTION\n")
    results.append("=" * 80 + "\n\n")
    output = run_test_and_capture(test_structure_extraction, pdf_path)
    results.append(output)
    results.append("\n\n")
    
    # Сохранение результатов
    output_file = output_dir / f"{pdf_name}_results.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("".join(results))
    
    print(f"Results saved to: {output_file}")
    return output_file


def main():
    """Запускает тесты для всех PDF файлов."""
    # Создаем папку для результатов
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    
    # Ищем все PDF файлы
    test_files_dir = Path("test_files")
    if not test_files_dir.exists():
        print(f"ERROR: Directory {test_files_dir} not found!")
        sys.exit(1)
    
    pdf_files = list(test_files_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"ERROR: No PDF files found in {test_files_dir}")
        sys.exit(1)
    
    print(f"Found {len(pdf_files)} PDF file(s)")
    print(f"Results will be saved to: {results_dir.absolute()}\n")
    
    # Создаем сводный отчет
    summary = []
    summary.append("=" * 80 + "\n")
    summary.append("PDF EXTRACTION TEST RESULTS SUMMARY\n")
    summary.append("=" * 80 + "\n")
    summary.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    summary.append(f"Total PDF files: {len(pdf_files)}\n")
    summary.append("=" * 80 + "\n\n")
    
    # Обрабатываем каждый PDF
    for i, pdf_file in enumerate(pdf_files, 1):
        print(f"\n[{i}/{len(pdf_files)}] Processing: {pdf_file.name}")
        try:
            result_file = test_single_pdf(pdf_file, results_dir)
            summary.append(f"✓ {pdf_file.name}\n")
            summary.append(f"  Results: {result_file.name}\n\n")
        except Exception as e:
            print(f"ERROR processing {pdf_file.name}: {e}")
            summary.append(f"✗ {pdf_file.name}\n")
            summary.append(f"  Error: {e}\n\n")
    
    # Сохраняем сводный отчет
    summary_file = results_dir / "SUMMARY.txt"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write("".join(summary))
    
    print("\n" + "=" * 80)
    print("All tests completed!")
    print(f"Summary saved to: {summary_file}")
    print(f"Individual results saved to: {results_dir}")
    print("=" * 80)


if __name__ == "__main__":
    main()

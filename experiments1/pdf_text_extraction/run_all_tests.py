"""
Скрипт для запуска всех тестов извлечения из PDF.
"""

import sys
from pathlib import Path

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
)
from test_structure_extraction import test_structure_extraction


def main():
    """Запускает все тесты для указанного PDF файла."""
    if len(sys.argv) < 2:
        # Ищем первый PDF в test_files
        test_files_dir = Path("test_files")
        pdf_files = list(test_files_dir.glob("*.pdf")) if test_files_dir.exists() else []
        
        if not pdf_files:
            print("ERROR: No PDF files found in test_files/")
            print("Usage: python run_all_tests.py <path_to_pdf>")
            sys.exit(1)
        
        test_pdf = pdf_files[0]
        print(f"Using first PDF found: {test_pdf.name}\n")
    else:
        test_pdf = Path(sys.argv[1])
    
    if not test_pdf.exists():
        print(f"ERROR: File {test_pdf} not found!")
        sys.exit(1)
    
    print("=" * 80)
    print(f"Running all extraction tests on: {test_pdf.name}")
    print("=" * 80)
    print()
    
    try:
        # 1. Базовое извлечение текста
        print("\n[1/6] Basic text extraction...")
        test_basic_text_extraction(test_pdf)
        
        print("\n[2/6] Text with metadata...")
        test_text_with_metadata(test_pdf)
        
        print("\n[3/6] Character extraction...")
        test_characters_extraction(test_pdf)
        
        # 2. Извлечение таблиц
        print("\n[4/6] Finding tables...")
        test_find_tables(test_pdf)
        
        print("\n[5/6] Extracting table data...")
        test_extract_table_data(test_pdf)
        
        # 3. Извлечение структуры
        print("\n[6/6] Structure extraction...")
        test_structure_extraction(test_pdf)
        
        print("\n" + "=" * 80)
        print("All tests completed!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

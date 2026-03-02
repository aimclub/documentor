"""
Базовое извлечение текста из PDF с помощью pdfplumber.

Эксперименты:
- Извлечение всего текста
- Извлечение текста по страницам
- Получение метаданных (шрифты, координаты)
"""

import pdfplumber
from pathlib import Path


def test_basic_text_extraction(pdf_path: str | Path):
    """Извлекает весь текст из PDF."""
    print(f"\n{'='*80}")
    print(f"Извлечение текста из: {pdf_path}")
    print(f"{'='*80}\n")
    
    with pdfplumber.open(pdf_path) as pdf:
        print(f"Количество страниц: {len(pdf.pages)}\n")
        
        # Извлечение всего текста
        full_text = ""
        for i, page in enumerate(pdf.pages, 1):
            page_text = page.extract_text()
            if page_text:
                full_text += f"\n--- Страница {i} ---\n"
                full_text += page_text
        
        print("Полный текст:")
        print("-" * 80)
        print(full_text)  # Весь текст без обрезки
        print("-" * 80)
        print(f"\nВсего символов: {len(full_text)}")
        
        return full_text


def test_text_with_metadata(pdf_path: str | Path):
    """Извлекает текст с метаданными (шрифты, координаты)."""
    print(f"\n{'='*80}")
    print(f"Извлечение текста с метаданными из: {pdf_path}")
    print(f"{'='*80}\n")
    
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):  # Все страницы
            print(f"\n--- Страница {i} ---\n")
            
            # Извлечение слов с метаданными
            words = page.extract_words()
            
            print(f"Количество слов: {len(words)}\n")
            print("Все слова с метаданными:")
            print("-" * 80)
            
            for word in words:
                print(f"Текст: '{word['text']}'")
                # pdfplumber использует x0, top, x1, bottom вместо y0, y1
                print(f"  Координаты: x0={word.get('x0', 0):.1f}, top={word.get('top', 0):.1f}, "
                      f"x1={word.get('x1', 0):.1f}, bottom={word.get('bottom', 0):.1f}")
                if 'fontname' in word:
                    print(f"  Шрифт: {word.get('fontname', 'N/A')}, "
                          f"Размер: {word.get('size', 'N/A')}")
                print()
            
            print("-" * 80)


def test_characters_extraction(pdf_path: str | Path):
    """Извлекает отдельные символы с полными метаданными."""
    print(f"\n{'='*80}")
    print(f"Извлечение символов с метаданными из: {pdf_path}")
    print(f"{'='*80}\n")
    
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]  # Первая страница
        
        # Извлечение символов
        chars = page.chars
        
        print(f"Количество символов на первой странице: {len(chars)}\n")
        print("Все символы с метаданными:")
        print("-" * 80)
        
        for char in chars:
            print(f"'{char['text']}' - "
                  f"Шрифт: {char.get('fontname', 'N/A')}, "
                  f"Размер: {char.get('size', 'N/A')}, "
                  f"Жирный: {char.get('bold', False)}, "
                  f"Курсив: {char.get('italic', False)}")
        
        print("-" * 80)


if __name__ == "__main__":
    import sys
    
    # Поиск первого PDF файла в test_files
    test_files_dir = Path("test_files")
    pdf_files = list(test_files_dir.glob("*.pdf")) if test_files_dir.exists() else []
    
    if not pdf_files:
        print("⚠️  PDF файлы не найдены в test_files/")
        print("Поместите PDF файлы в папку test_files/")
        sys.exit(1)
    
    # Используем первый найденный PDF или файл из аргументов
    if len(sys.argv) > 1:
        test_pdf = Path(sys.argv[1])
    else:
        test_pdf = pdf_files[0]
        print(f"Используется файл: {test_pdf.name}\n")
    
    if not test_pdf.exists():
        print(f"⚠️  Файл {test_pdf} не найден!")
        sys.exit(1)
    
    try:
        # Базовое извлечение текста
        test_basic_text_extraction(test_pdf)
        
        # Извлечение с метаданными
        test_text_with_metadata(test_pdf)
        
        # Извлечение символов
        test_characters_extraction(test_pdf)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

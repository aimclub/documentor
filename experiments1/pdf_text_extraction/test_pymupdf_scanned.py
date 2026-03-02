"""
Проверка работы PyMuPDF со сканированными PDF без выделяемого текста.
"""

import fitz  # PyMuPDF
from pathlib import Path

def check_pdf_text(pdf_path: Path):
    """Проверяет наличие текста в PDF и выводит информацию."""
    print(f"Проверка файла: {pdf_path}")
    print("=" * 80)
    
    doc = fitz.open(str(pdf_path))
    
    print(f"Количество страниц: {len(doc)}")
    print(f"Метаданные: {doc.metadata}")
    print()
    
    total_text_length = 0
    pages_with_text = 0
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # Получаем текст со страницы
        text = page.get_text()
        text_length = len(text.strip())
        
        if text_length > 0:
            pages_with_text += 1
            total_text_length += text_length
            print(f"Страница {page_num + 1}: {text_length} символов")
            print(f"Первые 200 символов: {text[:200]}")
            print()
        else:
            print(f"Страница {page_num + 1}: НЕТ ТЕКСТА")
            print()
    
    print("=" * 80)
    print(f"Итого:")
    print(f"  Страниц с текстом: {pages_with_text} из {len(doc)}")
    print(f"  Общая длина текста: {total_text_length} символов")
    
    # Проверяем наличие изображений
    print()
    print("Проверка изображений:")
    total_images = 0
    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images()
        if image_list:
            total_images += len(image_list)
            print(f"  Страница {page_num + 1}: {len(image_list)} изображений")
    
    print(f"  Всего изображений: {total_images}")
    
    # Проверяем наличие OCR слоя (XObject с типом Image)
    print()
    print("Проверка OCR слоя:")
    for page_num in range(min(3, len(doc))):  # Проверяем первые 3 страницы
        page = doc[page_num]
        xrefs = page.get_contents()
        if xrefs:
            print(f"  Страница {page_num + 1}: есть содержимое (xrefs: {xrefs})")
            # Попробуем получить текст через разные методы
            text_dict = page.get_text("dict")
            blocks = text_dict.get("blocks", [])
            text_blocks = [b for b in blocks if b.get("type") == 0]  # type 0 = text
            image_blocks = [b for b in blocks if b.get("type") == 1]  # type 1 = image
            print(f"    Текстовых блоков: {len(text_blocks)}")
            print(f"    Изображений: {len(image_blocks)}")
    
    # Проверяем, есть ли встроенный OCR в PyMuPDF
    print()
    print("Проверка встроенного OCR в PyMuPDF:")
    try:
        import fitz.tools as fitz_tools
        print("  fitz.tools доступен")
    except ImportError:
        print("  fitz.tools недоступен (OCR может быть недоступен)")
    
    # Пробуем получить текст через OCR, если доступен
    print()
    print("Попытка извлечения текста через OCR (если доступен):")
    print("  PyMuPDF не имеет встроенного OCR")
    print("  Для OCR нужно использовать внешние инструменты (tesseract, DOTS OCR и т.д.)")
    print("  В данном случае файл содержит только изображения страниц без текстового слоя")
    
    doc.close()

if __name__ == "__main__":
    pdf_path = Path("experiments/pdf_text_extraction/test_files/scanned_2506.10204v1.pdf")
    
    if not pdf_path.exists():
        print(f"Файл не найден: {pdf_path}")
    else:
        check_pdf_text(pdf_path)

#!/usr/bin/env python3
"""
Скрипт для получения сырого (raw) вывода от Dots OCR с промптом prompt_layout_all_en.
Выводит ответ без какой-либо обработки.
"""

import sys
import io
from pathlib import Path

# Добавляем путь к корню проекта
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import fitz  # PyMuPDF
from PIL import Image
from documentor.ocr.dots_ocr import load_prompts_from_config
from documentor.processing.parsers.pdf.ocr.dots_ocr_client import run_inference


def render_pdf_page(pdf_path: Path, page_num: int, render_scale: float = 2.0) -> Image.Image:
    """
    Рендерит страницу PDF в изображение.
    
    Args:
        pdf_path: Путь к PDF файлу
        page_num: Номер страницы (0-based)
        render_scale: Масштаб рендеринга
    
    Returns:
        PIL Image
    """
    pdf_doc = fitz.open(str(pdf_path))
    try:
        page = pdf_doc[page_num]
        mat = fitz.Matrix(render_scale, render_scale)
        pix = page.get_pixmap(matrix=mat)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return img
    finally:
        pdf_doc.close()


def main():
    """Основная функция."""
    # Путь к PDF файлу
    pdf_file_path = Path(r"E:\easy\documentor\documentor_langchain\experiments\pdf_text_extraction\test_files\scanned_2506.10204v1.pdf")
    
    if not pdf_file_path.exists():
        print(f"Файл не найден: {pdf_file_path}")
        return
    
    # Загружаем промпт из конфига
    config_path = project_root / "documentor" / "config" / "ocr_config.yaml"
    prompts = load_prompts_from_config(config_path)
    prompt = prompts.get("prompt_layout_all_en")
    
    if not prompt:
        print("Ошибка: промпт prompt_layout_all_en не найден в конфиге")
        return
    
    print("=" * 80)
    print("ПРОМПТ:")
    print("=" * 80)
    print(prompt)
    print("\n" + "=" * 80)
    
    # Открываем PDF и обрабатываем первую страницу
    pdf_doc = fitz.open(str(pdf_file_path))
    total_pages = len(pdf_doc)
    pdf_doc.close()
    
    print(f"Всего страниц в PDF: {total_pages}")
    print(f"Обрабатываю первую страницу (страница 0)...\n")
    
    # Рендерим первую страницу
    page_image = render_pdf_page(pdf_file_path, 0, render_scale=2.0)
    print(f"Размер изображения: {page_image.width}x{page_image.height} пикселей\n")
    
    # Отправляем в Dots OCR и получаем сырой ответ
    print("=" * 80)
    print("ОТПРАВКА ЗАПРОСА В DOTS OCR...")
    print("=" * 80)
    
    try:
        raw_response = run_inference(
            input_image=page_image,
            prompt=prompt,
            timeout=300,  # 5 минут таймаут
        )
        
        if raw_response:
            print("\n" + "=" * 80)
            print("СЫРОЙ ОТВЕТ ОТ DOTS OCR:")
            print("=" * 80)
            print(raw_response)
            print("\n" + "=" * 80)
            print(f"Длина ответа: {len(raw_response)} символов")
            
            # Сохраняем в файл
            output_file = pdf_file_path.parent.parent / "results" / "raw_dots_ocr_output.txt"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                f.write("=" * 80 + "\n")
                f.write("ПРОМПТ:\n")
                f.write("=" * 80 + "\n")
                f.write(prompt + "\n\n")
                f.write("=" * 80 + "\n")
                f.write("СЫРОЙ ОТВЕТ ОТ DOTS OCR:\n")
                f.write("=" * 80 + "\n")
                f.write(raw_response)
                f.write("\n" + "=" * 80 + "\n")
            
            print(f"\nОтвет сохранен в: {output_file}")
        else:
            print("\nОШИБКА: Dots OCR вернул пустой ответ")
            
    except Exception as e:
        print(f"\nОШИБКА при запросе к Dots OCR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

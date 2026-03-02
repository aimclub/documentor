# Эксперименты с извлечением текста из PDF

Папка для экспериментов с использованием pdfplumber для извлечения текста, таблиц и других элементов из PDF.

## Структура

- `test_basic_extraction.py` - базовое извлечение текста
- `test_table_extraction.py` - извлечение таблиц
- `test_structure_extraction.py` - извлечение структуры (абзацы, списки)
- `test_dots_ocr_local.py` - локальный Dots OCR для layout detection
- `test_files/` - тестовые PDF файлы

## Зависимости

```bash
pip install pdfplumber pandas
```

## Локальный Dots OCR

Для использования локального Dots OCR с transformers:

1. Установите зависимости:
```bash
pip install transformers torch pillow PyMuPDF pdfplumber
```

2. Запустите скрипт:
```bash
# Обработать один файл
python test_dots_ocr_local.py test_files/2304.05128v2.pdf

# Обработать конкретные страницы (например, 9-11)
python test_dots_ocr_local.py test_files/2304.05128v2.pdf --pages "9,10,11"

# Использовать другую модель (требует больше памяти)
python test_dots_ocr_local.py test_files/2304.05128v2.pdf --model "Qwen/Qwen2-VL-7B-Instruct"
```

Результаты сохраняются в `results/{pdf_name}_dots_ocr_local/`:
- `images_with_layout/` - изображения с визуализацией layout (bbox элементов)
- `page_XXXX_result.json` - JSON результаты для каждой страницы
- `summary.json` - сводка по всем страницам

**Примечание:** Модель `Qwen/Qwen2-VL-2B-Instruct` требует ~4GB памяти. Для более точных результатов используйте `Qwen/Qwen2-VL-7B-Instruct` (~14GB).

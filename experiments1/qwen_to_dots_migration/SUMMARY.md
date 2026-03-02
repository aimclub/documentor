# Резюме: Замена Qwen на Dots OCR

## Текущая ситуация

### Где используется Qwen:

1. **OCR для текста** (`ocr_text_with_qwen`)
   - Файл: `pdf_parser.py` → `_extract_text_by_bboxes()`
   - Когда: Для отсканированных PDF (`use_ocr=True`)
   - Что делает: Извлекает текст из изображений для категорий Text, Section-header, Title, Caption

2. **Парсинг таблиц** (`parse_table_with_qwen`)
   - Файл: `pdf_parser.py` → `_process_tables()`
   - Когда: Для всех таблиц (всегда)
   - Что делает: Конвертирует изображение таблицы в markdown/dataframe

### Проблема

**Dots OCR уже может делать все это!**

- `prompt_layout_all_en` извлекает **layout + текст одновременно**
- Для таблиц Dots OCR возвращает **HTML формат**
- Но мы используем `prompt_layout_only_en` (без текста) и потом Qwen для текста

**Это избыточно!** Один запрос вместо двух.

## Решение

### Заменить Qwen на Dots OCR:

1. **Для текста:**
   - Использовать `prompt_layout_all_en` вместо `prompt_layout_only_en`
   - Брать текст напрямую из результатов Dots OCR
   - Убрать вызовы `ocr_text_with_qwen`

2. **Для таблиц:**
   - Парсить HTML из Dots OCR вместо Qwen
   - Создать `html_table_parser.py` для конвертации HTML → markdown/dataframe
   - Убрать вызовы `parse_table_with_qwen`

## Преимущества

✅ **Быстрее:** Один запрос вместо двух  
✅ **Дешевле:** Меньше API запросов  
✅ **Проще:** Одна модель вместо двух  
✅ **Меньше зависимостей:** Не нужен Qwen  

## План действий

1. Изменить промпт на `prompt_layout_all_en` в `layout_detector.py` и `dots_ocr_client.py`
2. Использовать текст из Dots OCR в `pdf_parser.py`
3. Создать парсер HTML таблиц
4. Удалить весь код Qwen
5. Протестировать на реальных документах

## Файлы для изменения

### Изменить:
- `documentor/processing/parsers/pdf/ocr/layout_detector.py` (строка 98)
- `documentor/processing/parsers/pdf/ocr/dots_ocr_client.py` (строки 277, 311)
- `documentor/processing/parsers/pdf/pdf_parser.py` (строки 730-850, 1300-1400)

### Создать:
- `documentor/processing/parsers/pdf/ocr/html_table_parser.py`

### Удалить:
- `documentor/processing/parsers/pdf/ocr/qwen_ocr.py`
- `documentor/processing/parsers/pdf/ocr/qwen_table_parser.py`
- Секция `qwen_ocr` из `ocr_config.yaml`

## Детали

См. файлы:
- `ANALYSIS.md` - Детальный анализ использования Qwen
- `MIGRATION_PLAN.md` - Пошаговый план миграции с кодом

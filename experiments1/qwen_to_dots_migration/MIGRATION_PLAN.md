# План миграции с Qwen на Dots OCR

## Цель
Полностью заменить Qwen OCR на Dots OCR для всех задач:
- Извлечение текста из изображений
- Парсинг таблиц

## Текущая ситуация

### Использование Qwen:
1. **OCR для текста** (`ocr_text_with_qwen`):
   - Файл: `documentor/processing/parsers/pdf/pdf_parser.py`
   - Метод: `_extract_text_by_bboxes()` (строка 820)
   - Условие: `use_ocr=True` (когда `is_text_extractable=False`)

2. **Парсинг таблиц** (`parse_table_with_qwen`):
   - Файл: `documentor/processing/parsers/pdf/pdf_parser.py`
   - Метод: `_process_tables()` (строка 1365)
   - Условие: Всегда используется для всех таблиц

### Использование Dots OCR:
- Файл: `documentor/processing/parsers/pdf/ocr/layout_detector.py`
- Промпт: `prompt_layout_only_en` (строка 98) - **БЕЗ текста**
- Результат: Только layout (bbox, category), без текста

## Проблема
Dots OCR с `prompt_layout_all_en` **уже извлекает текст**, но мы используем `prompt_layout_only_en` и потом Qwen для текста. Это избыточно!

## План миграции

### Этап 1: Изменить промпт на `prompt_layout_all_en`

#### Файл 1: `documentor/processing/parsers/pdf/ocr/layout_detector.py`
**Изменение:** Строка 98
```python
# БЫЛО:
prompt_mode="prompt_layout_only_en"

# СТАНЕТ:
prompt_mode="prompt_layout_all_en"
```

#### Файл 2: `documentor/processing/parsers/pdf/ocr/dots_ocr_client.py`
**Изменение:** Строка 277 - заменить хардкодный промпт на загрузку из конфига
```python
# БЫЛО:
if prompt is None:
    prompt = "Please output the layout information from this PDF image, including each layout's bbox and its category. The bbox should be in the format [x1, y1, x2, y2]. The layout categories for the PDF document include ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title']. Do not output the corresponding text. The layout result should be in JSON format."

# СТАНЕТ:
if prompt is None:
    # Загружаем промпт из конфига
    config = _load_ocr_config()
    prompt = config.get("dots_ocr", {}).get("prompts", {}).get("prompt_layout_all_en")
    if not prompt:
        # Fallback на старый промпт, если конфиг не найден
        prompt = "Please output the layout information from the PDF image, including each layout element's bbox, its category, and the corresponding text content within the bbox..."
```

**Изменение:** Строка 311 - изменить `post_process_output`
```python
# БЫЛО:
parsed_cells, filtered = post_process_output(
    raw_response,
    "prompt_layout_only_en",  # <-- изменить
    origin_image,
    image,
    min_pixels=min_pixels,
    max_pixels=max_pixels,
)

# СТАНЕТ:
parsed_cells, filtered = post_process_output(
    raw_response,
    "prompt_layout_all_en",  # <-- изменить
    origin_image,
    image,
    min_pixels=min_pixels,
    max_pixels=max_pixels,
)
```

### Этап 2: Использовать текст из Dots OCR вместо Qwen

#### Файл: `documentor/processing/parsers/pdf/pdf_parser.py`

**Изменение 1:** Метод `_extract_text_by_bboxes()` (строка 730-850)
- Убрать логику `use_ocr` для текста
- Использовать текст напрямую из `layout_elements` (поле `text`)

```python
# БЫЛО:
if use_ocr:
    # Use OCR via Qwen2.5
    text = ocr_text_with_qwen(cropped_image)
    element["text"] = text.strip() if text else ""
else:
    # Use PyMuPDF for extractable text
    page = pdf_document.load_page(page_num)
    text = page.get_text("text", clip=rect)
    element["text"] = text.strip() if text else ""

# СТАНЕТ:
# Используем текст из Dots OCR, если есть
if "text" in element and element["text"]:
    # Текст уже извлечен Dots OCR
    element["text"] = element["text"].strip()
elif not use_ocr:
    # Fallback на PyMuPDF для выделяемого текста (если Dots OCR не вернул текст)
    page = pdf_document.load_page(page_num)
    text = page.get_text("text", clip=rect)
    element["text"] = text.strip() if text else ""
else:
    # Если use_ocr=True, но Dots OCR не вернул текст - оставляем пустым
    element["text"] = element.get("text", "").strip()
```

**Изменение 2:** Убрать рендеринг страниц для OCR (строки 753-780)
- Если используем `prompt_layout_all_en`, не нужно рендерить страницы отдельно для OCR
- Убрать `page_images` и весь блок `if use_ocr:` для рендеринга

**Изменение 3:** Убрать импорт Qwen (строка 45)
```python
# БЫЛО:
from .ocr.qwen_ocr import ocr_text_with_qwen

# СТАНЕТ:
# Удалить импорт
```

### Этап 3: Парсить HTML таблицы из Dots OCR

#### Файл: `documentor/processing/parsers/pdf/pdf_parser.py`

**Изменение:** Метод `_process_tables()` (строка 1300-1400)
- Вместо рендеринга таблицы в изображение и вызова Qwen
- Использовать HTML из поля `text` элемента таблицы

```python
# БЫЛО:
# Render table area
mat = fitz.Matrix(2.0, 2.0)
pix = page.get_pixmap(matrix=mat, clip=rect)
img_data = pix.tobytes("png")
table_image = Image.open(BytesIO(img_data)).convert("RGB")

# Parse table via Qwen
markdown_content, dataframe, success = parse_table_with_qwen(
    table_image,
    method=method,
)

# СТАНЕТ:
# Используем HTML из Dots OCR
table_html = element.get("text", "")  # HTML из Dots OCR
if table_html:
    # Парсим HTML в markdown/dataframe
    markdown_content, dataframe, success = parse_table_from_html(
        table_html,
        method=method,
    )
else:
    # Fallback: если HTML нет, рендерим и используем Qwen (временно)
    # TODO: Удалить после тестирования
    markdown_content, dataframe, success = parse_table_with_qwen(...)
```

**Создать новый файл:** `documentor/processing/parsers/pdf/ocr/html_table_parser.py`
```python
"""
Парсинг HTML таблиц из Dots OCR в markdown/dataframe.
"""

from typing import Tuple, Optional, Any
import pandas as pd
from bs4 import BeautifulSoup

def parse_table_from_html(
    html_content: str,
    method: str = "markdown",
) -> Tuple[Optional[str], Optional[Any], bool]:
    """
    Парсит HTML таблицу в markdown или dataframe.
    
    Args:
        html_content: HTML строка с таблицей
        method: "markdown" или "dataframe"
    
    Returns:
        tuple: (markdown_content, dataframe, success)
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        table = soup.find('table')
        
        if not table:
            return None, None, False
        
        # Парсим таблицу в DataFrame
        rows = []
        for tr in table.find_all('tr'):
            cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            if cells:
                rows.append(cells)
        
        if not rows:
            return None, None, False
        
        # Создаем DataFrame
        df = pd.DataFrame(rows[1:], columns=rows[0] if rows else None)
        
        if method == "dataframe":
            return None, df, True
        
        # Конвертируем в markdown
        markdown = df.to_markdown(index=False)
        return markdown, df, True
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error parsing HTML table: {e}")
        return None, None, False
```

### Этап 4: Удалить код Qwen

#### Файлы для удаления:
1. `documentor/processing/parsers/pdf/ocr/qwen_ocr.py`
2. `documentor/processing/parsers/pdf/ocr/qwen_table_parser.py`

#### Файлы для изменения:
1. `documentor/processing/parsers/pdf/ocr/__init__.py` - убрать экспорты Qwen
2. `documentor/config/ocr_config.yaml` - удалить секцию `qwen_ocr`
3. `documentor/processing/parsers/pdf/pdf_parser.py` - убрать импорты Qwen

### Этап 5: Тестирование

#### Тесты для проверки:
1. **Точность текста:**
   - Сравнить текст из Dots OCR vs Qwen на тестовых документах
   - Вычислить CER/WER метрики

2. **Точность таблиц:**
   - Сравнить таблицы из Dots OCR (HTML) vs Qwen (markdown)
   - Проверить корректность парсинга HTML

3. **Производительность:**
   - Измерить время обработки документов
   - Сравнить количество API запросов (должно быть меньше)

4. **Ресурсы:**
   - Проверить использование памяти
   - Проверить использование API квот

## Порядок выполнения

1. ✅ Создать анализ (ANALYSIS.md) - **ГОТОВО**
2. ✅ Создать план миграции (MIGRATION_PLAN.md) - **ГОТОВО**
3. ⏳ Этап 1: Изменить промпт на `prompt_layout_all_en`
4. ⏳ Этап 2: Использовать текст из Dots OCR
5. ⏳ Этап 3: Парсить HTML таблицы
6. ⏳ Этап 4: Удалить код Qwen
7. ⏳ Этап 5: Тестирование

## Риски

1. **Качество текста:** Dots OCR может давать менее точный текст
   - **Митигация:** Протестировать на реальных документах

2. **HTML таблицы:** Могут быть сложные таблицы с merged cells
   - **Митигация:** Использовать BeautifulSoup для корректного парсинга

3. **Обратная совместимость:** Если кто-то использует Qwen напрямую
   - **Митигация:** Добавить deprecation warnings перед удалением

## Преимущества после миграции

1. ✅ Один запрос вместо двух (layout + OCR)
2. ✅ Быстрее обработка документов
3. ✅ Меньше зависимостей (не нужен Qwen)
4. ✅ Проще поддержка (одна модель вместо двух)
5. ✅ Меньше API запросов = дешевле

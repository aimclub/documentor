# Как парсятся таблицы в Marker

## Общий процесс

Marker использует многоступенчатый процесс для парсинга таблиц из PDF:

### 1. Обнаружение таблиц (Table Detection)
- Таблицы обнаруживаются на этапе layout detection (используется модель из `surya`)
- Блоки таблиц создаются как `BlockTypes.Table`, `BlockTypes.TableOfContents` или `BlockTypes.Form`

### 2. Распознавание структуры таблицы (Table Recognition)
**Файл:** `marker/processors/table.py` - класс `TableProcessor`

Основные шаги:

#### a) Распознавание ячеек
- Используется модель `TableRecPredictor` из библиотеки `surya.table_rec`
- Модель определяет:
  - Границы ячеек (polygon/bbox)
  - `row_id`, `col_id` - позиция ячейки
  - `rowspan`, `colspan` - объединенные ячейки
  - `is_header` - является ли ячейка заголовком

#### b) Извлечение текста из ячеек
Marker использует два подхода в зависимости от качества PDF:

**1. Извлечение из PDF (pdftext):**
- Если PDF содержит извлекаемый текст (`text_extraction_method != "surya"` и нет OCR ошибок)
- Используется библиотека `pdftext.extraction.table_output`
- Текст извлекается на уровне строк (`table_text_lines`)
- Текст привязывается к ячейкам через матрицу пересечений (intersection matrix)

**2. OCR (если нужно):**
- Если PDF не содержит извлекаемого текста или есть ошибки OCR
- Используется `DetectionPredictor` для обнаружения текстовых линий
- Затем `RecognitionPredictor` для распознавания текста в каждой ячейке
- OCR выполняется только для ячеек, где `text_lines is None`

#### c) Обработка и очистка текста ячеек
Метод `finalize_cell_text()`:
- Удаляет повторяющиеся символы (`. . .`, `---`, `___`)
- Обрабатывает LaTeX команды:
  - `\mathbf{...}` → `<b>...</b>` для чисел
  - Удаляет пустые теги (`\overline{}`, `\phantom{...}`)
  - Разворачивает `\mathsf{...}`, `\text{...}`
- Нормализует пробелы (заменяет специальные пробелы на обычные)
- Использует `ftfy` для исправления текста

#### d) Постобработка структуры таблицы

**Объединение столбцов с долларами (`combine_dollar_column`):**
- Находит столбцы, состоящие только из символов `$`
- Объединяет их со следующим столбцом (для форматирования валют)

**Разделение объединенных строк (`split_combined_rows`):**
- Обнаруживает строки, где каждая ячейка содержит несколько строк текста
- Разделяет такие строки на несколько физических строк
- Работает только если >50% строк в таблице требуют разделения (настраивается через `row_split_threshold`)

### 3. LLM обработка (опционально)
**Файл:** `marker/processors/llm/llm_table.py` - класс `LLMTableProcessor`

Если включен флаг `--use_llm`:

#### a) Исправление через LLM
- Таблица конвертируется в HTML
- LLM получает изображение таблицы и HTML представление
- LLM исправляет ошибки в HTML, сверяя с изображением
- Особое внимание к соответствию заголовков столбцов значениям

#### b) Обработка больших таблиц
- Таблицы с >60 строк обрабатываются по частям (`max_rows_per_batch`)
- Таблицы с >175 строк пропускаются (`max_table_rows`)

#### c) Обработка повернутых таблиц
- Автоматически определяет поворот таблицы
- Поворачивает изображение перед отправкой в LLM

### 4. Объединение таблиц через страницы (опционально)
**Файл:** `marker/processors/llm/llm_table_merge.py` - класс `LLMTableMergeProcessor`

- Обнаруживает таблицы, разбитые на несколько страниц
- Объединяет их в одну таблицу через LLM

### 5. Рендеринг в Markdown
**Файл:** `marker/renderers/markdown.py` - метод `convert_table()`

#### Вариант 1: HTML таблицы в Markdown
Если `html_tables_in_markdown=True`:
- Таблица вставляется как HTML (`<table>...</table>`)

#### Вариант 2: Markdown таблицы
Если `html_tables_in_markdown=False`:
- Таблица конвертируется в Markdown формат с разделителями `|`
- Обрабатывает `rowspan` и `colspan`:
  - Создает сетку (grid) размером `max_rows × max_cols`
  - Заполняет пустые ячейки от `rowspan/colspan` пустыми строками
- Экранирует символы `|` в тексте ячеек
- Форматирует математику: `<math>...</math>` → `$...$`

## Ключевые модели и библиотеки

1. **Surya Table Recognition** (`surya.table_rec.TableRecPredictor`)
   - Распознает структуру таблицы (ячейки, строки, столбцы)

2. **Surya Text Detection** (`surya.detection.DetectionPredictor`)
   - Обнаруживает текстовые линии в таблице (для OCR)

3. **Surya Text Recognition** (`surya.recognition.RecognitionPredictor`)
   - Распознает текст в ячейках (OCR)

4. **pdftext** (`pdftext.extraction.table_output`)
   - Извлекает текст из таблиц в PDF с хорошим текстовым слоем

## Структура данных

### TableResult (из surya)
```python
{
    cells: List[SuryaTableCell]  # Список ячеек таблицы
}
```

### SuryaTableCell
```python
{
    polygon: List[List[float]]  # Координаты ячейки
    bbox: List[float]  # [x0, y0, x1, y1]
    row_id: int
    col_id: int
    rowspan: int
    colspan: int
    is_header: bool
    text_lines: List[dict] | None  # Текст ячейки
    cell_id: int
}
```

### TableCell (внутренняя структура Marker)
```python
{
    row_id: int
    col_id: int
    rowspan: int
    colspan: int
    is_header: bool
    text_lines: List[str]  # Очищенный текст
    polygon: PolygonBox
}
```

## Настройки и параметры

### TableProcessor
- `table_rec_batch_size`: размер батча для распознавания таблиц (по умолчанию: 14 для CUDA, 6 для MPS/CPU)
- `recognition_batch_size`: размер батча для OCR (по умолчанию: 48 для CUDA, 32 для MPS/CPU)
- `detection_batch_size`: размер батча для обнаружения текста (по умолчанию: 10 для CUDA, 4 для CPU)
- `row_split_threshold`: порог для разделения строк (по умолчанию: 0.5)
- `disable_ocr`: отключить OCR полностью
- `disable_ocr_math`: отключить распознавание математики в OCR

### LLMTableProcessor
- `max_rows_per_batch`: максимальное количество строк в батче для LLM (по умолчанию: 60)
- `max_table_rows`: максимальное количество строк для обработки LLM (по умолчанию: 175)
- `max_table_iterations`: максимальное количество итераций исправления (по умолчанию: 2)

## Особенности обработки

1. **Привязка текста к ячейкам:**
   - Используется матрица пересечений (intersection matrix)
   - Текстовая линия привязывается к ячейке с максимальным пересечением

2. **Выравнивание ячеек:**
   - Если ячейка содержит несколько текстовых линий, она расширяется по Y-оси
   - Удаляются текстовые линии, не принадлежащие ячейке

3. **Обработка пустых ячеек:**
   - Ячейки без текста получают пустой `TextLine` при OCR
   - Маленькие ячейки (<6px высотой) или пустые изображения пропускаются

4. **Очистка структуры:**
   - Текстовые блоки внутри таблиц удаляются (если >95% пересекаются с таблицей)

## Пример использования

```python
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict

converter = PdfConverter(
    artifact_dict=create_model_dict(),
)

# Конвертация PDF
rendered = converter("file.pdf")

# Таблицы будут автоматически распознаны и обработаны
# Результат в rendered.markdown или rendered.html
```

## Отдельный конвертер для таблиц

```python
from marker.converters.table import TableConverter
from marker.models import create_model_dict

converter = TableConverter(
    artifact_dict=create_model_dict(),
)

# Извлекает только таблицы из PDF
rendered = converter("file.pdf")
```

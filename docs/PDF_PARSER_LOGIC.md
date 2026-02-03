# Логика PDF парсера (Layout-based подход)

## Обзор

PDF парсер использует **layout detection как основу** для построения структуры документа. Вместо извлечения текста через PdfPlumber, мы сначала определяем layout через Dots.OCR, затем извлекаем текст по координатам через PyMuPDF.

## Полный путь обработки

### Шаг 1: Получение PDF

**Вход:** `Document` (LangChain) с путем к PDF файлу

**Действие:**
- Валидация входных данных
- Получение пути к файлу из `document.metadata["source"]`

### Шаг 2: Проверка выделяемого текста

**Метод:** `PdfParser._is_text_extractable(source: str) -> bool`

**Логика:**
- Открывает PDF через PyMuPDF (`fitz.open()`)
- Проверяет наличие текстового слоя на первой странице
- Оценивает качество текста (количество символов, наличие осмысленного текста)
- Если текст выделяется → продолжаем с layout detection
- Если текст не выделяется → используем OCR путь (рендеринг + Dots.OCR + Qwen OCR)

**Результат:**
- `True` - текст выделяется, используем layout-based подход
- `False` - текст не выделяется, используем полный OCR путь

### Шаг 3: Layout Detection через Dots.OCR

**Метод:** `PdfParser._detect_layout_for_all_pages(source: str) -> List[Dict]`

**Логика:**
1. **Рендеринг страниц:**
   - Используем `PdfPageRenderer` для рендеринга всех страниц
   - Увеличение 2x на стадии рендеринга (`fitz.Matrix(2.0, 2.0)`)
   - Применяем `smart_resize` через `fetch_image` для оптимизации

2. **Layout Detection для каждой страницы:**
   - Используем `PdfLayoutDetector` с `use_direct_api=True`
   - Вызываем Dots.OCR для каждой страницы
   - Получаем список элементов с категориями и bbox

**Результат:**
```python
all_layout_elements: List[Dict] = [
    {
        "bbox": [x1, y1, x2, y2],
        "category": "Section-header",  # или "Text", "Table", "Picture", "Caption" и т.д.
        "page_num": 0
    },
    ...
]
```

**Категории от Dots.OCR:**
- `Title` - заголовок документа
- `Section-header` - заголовок раздела
- `Text` - текстовый блок
- `Table` - таблица
- `Picture` - изображение
- `Caption` - подпись к изображению/таблице
- `Page-header` - колонтитул верхний
- `Page-footer` - колонтитул нижний
- `Formula` - формула
- `List-item` - элемент списка
- `Footnote` - сноска

### Шаг 4: Построение иерархии от Section-header

**Метод:** `PdfParser._build_hierarchy_from_section_headers(layout_elements: List[Dict]) -> Dict`

**Логика:**
1. **Группировка элементов по разделам:**
   - Находим все `Section-header` элементы
   - Для каждого `Section-header` находим все элементы, которые находятся "под ним" (по координатам Y)
   - Группируем элементы до следующего `Section-header` или конца страницы

2. **Определение уровней заголовков:**
   - Анализируем стиль `Section-header` (размер шрифта, позиция, форматирование)
   - Определяем уровень заголовка (HEADER_1, HEADER_2, HEADER_3 и т.д.)
   - Используем эвристики:
     - Размер шрифта (больше = выше уровень)
     - Позиция слева (левее = выше уровень)
     - Форматирование (жирный, заглавные буквы)

3. **Построение дерева иерархии:**
   - Создаем структуру: `Section-header` → дочерние элементы
   - Определяем `parent_id` для каждого элемента

**Результат:**
```python
hierarchy: Dict = {
    "sections": [
        {
            "header": {
                "bbox": [x1, y1, x2, y2],
                "category": "Section-header",
                "level": 1,  # HEADER_1
                "page_num": 0
            },
            "children": [
                {
                    "bbox": [x1, y1, x2, y2],
                    "category": "Text",
                    "page_num": 0
                },
                {
                    "bbox": [x1, y1, x2, y2],
                    "category": "Table",
                    "page_num": 0
                },
                ...
            ]
        },
        ...
    ]
}
```

### Шаг 5: Фильтрация лишних элементов

**Метод:** `PdfParser._filter_layout_elements(layout_elements: List[Dict]) -> List[Dict]`

**Логика:**
1. **Удаление колонтитулов:**
   - Удаляем все элементы с категорией `Page-header`
   - Удаляем все элементы с категорией `Page-footer`

2. **Удаление бокового текста (например, arXiv идентификатор):**
   - Определяем "основную область" документа (обычно от x=290 до x=1400)
   - Удаляем элементы, которые находятся слишком далеко слева (например, x < 100)
   - Проверяем соотношение ширины к высоте (узкие вертикальные блоки слева - обычно лишние)

3. **Удаление дубликатов:**
   - Если два элемента имеют очень похожие bbox (пересечение > 80%) → оставляем один

**Пример фильтрации:**
```python
# До фильтрации:
[
    {"bbox": [293, 60, 581, 111], "category": "Page-header"},  # удаляем
    {"bbox": [39, 604, 103, 1549], "category": "Text"},  # удаляем (боковой текст)
    {"bbox": [293, 216, 1414, 323], "category": "Title"},  # оставляем
    ...
]

# После фильтрации:
[
    {"bbox": [293, 216, 1414, 323], "category": "Title"},
    ...
]
```

**Конфигурация фильтрации:**
```yaml
# config/pdf_config.yaml
filtering:
  remove_page_headers: true
  remove_page_footers: true
  main_area:
    min_x: 290  # минимальная X координата основной области
    max_x: 1400  # максимальная X координата основной области
  side_text:
    max_x: 100  # элементы левее этой координаты удаляются
    min_width_ratio: 0.1  # минимальное соотношение ширины к высоте
```

### Шаг 6: Анализ заголовков по уровням

**Метод:** `PdfParser._analyze_header_levels(sections: List[Dict]) -> List[Dict]`

**Логика:**
1. **Анализ стилей заголовков:**
   - Для каждого `Section-header` извлекаем текст через PyMuPDF по bbox
   - Анализируем стиль (размер шрифта, жирность, позицию)
   - Сравниваем с другими заголовками для определения относительных уровней

2. **Определение уровней:**
   - Используем эвристики:
     - Заголовки с большим шрифтом → HEADER_1
     - Заголовки с меньшим шрифтом → HEADER_2, HEADER_3 и т.д.
     - Заголовки, начинающиеся с цифр (1, 2, 3) → обычно HEADER_1
     - Заголовки, начинающиеся с цифр (1.1, 1.2) → обычно HEADER_2
     - Заголовки, начинающиеся с цифр (1.1.1, 1.1.2) → обычно HEADER_3

3. **Валидация иерархии:**
   - Проверяем логику уровней (HEADER_2 не может быть дочерним HEADER_3)
   - Исправляем ошибки при необходимости

**Результат:**
```python
analyzed_sections: List[Dict] = [
    {
        "header": {
            "bbox": [x1, y1, x2, y2],
            "category": "Section-header",
            "level": 1,  # HEADER_1
            "element_type": ElementType.HEADER_1,
            "text": "1 INTRODUCTION",
            "page_num": 0
        },
        "children": [...]
    },
    {
        "header": {
            "bbox": [x1, y1, x2, y2],
            "category": "Section-header",
            "level": 2,  # HEADER_2
            "element_type": ElementType.HEADER_2,
            "text": "1.1 Background",
            "page_num": 0
        },
        "children": [...]
    },
    ...
]
```

### Шаг 7: Извлечение текста через PyMuPDF по координатам

**Метод:** `PdfParser._extract_text_by_bbox(pdf_path: str, bbox: List[int], page_num: int) -> str`

**Логика:**
1. **Для каждого текстового элемента:**
   - Открываем PDF через PyMuPDF
   - Получаем страницу по `page_num`
   - Извлекаем текст в области bbox через `page.get_text("text", clip=bbox)`
   - Очищаем текст (удаляем лишние пробелы, переносы строк)

2. **Обработка координат:**
   - Координаты от Dots.OCR могут быть в масштабе увеличенного изображения (2x)
   - Приводим координаты к масштабу оригинального PDF
   - Учитываем возможные неточности в координатах (добавляем небольшой отступ)

**Результат:**
```python
text_elements: List[Dict] = [
    {
        "bbox": [x1, y1, x2, y2],
        "category": "Text",
        "text": "Извлеченный текст из этого блока...",
        "page_num": 0
    },
    ...
]
```

### Шаг 8: Склеивание близких текстовых блоков

**Метод:** `PdfParser._merge_nearby_text_blocks(text_elements: List[Dict], max_chunk_size: int = 3000) -> List[Dict]`

**Логика:**
1. **Определение близких блоков:**
   - Для каждого текстового блока проверяем расстояние до следующего блока
   - Если блоки находятся на одной странице и близко по Y координате (разница < threshold) → склеиваем
   - Если блоки находятся на соседних страницах и близко по позиции → склеиваем

2. **Склеивание блоков:**
   - Объединяем текст близких блоков
   - Объединяем bbox (берем минимальный x1, y1 и максимальный x2, y2)
   - Проверяем, что общий размер текста не превышает `max_chunk_size`

3. **Разбиение больших блоков:**
   - Если после склеивания размер текста > `max_chunk_size` → разбиваем на части
   - Разбиваем по предложениям или параграфам
   - Сохраняем информацию о том, что блок был разбит

**Конфигурация:**
```yaml
# config/pdf_config.yaml
text_merging:
  max_chunk_size: 3000  # максимальный размер текстового блока
  merge_threshold_y: 50  # максимальное расстояние по Y для склеивания (в пикселях)
  merge_threshold_x: 100  # максимальное расстояние по X для склеивания
  split_by_sentences: true  # разбивать большие блоки по предложениям
```

**Результат:**
```python
merged_text_elements: List[Dict] = [
    {
        "bbox": [x1, y1, x2, y2],  # объединенный bbox
        "category": "Text",
        "text": "Текст блока 1. Текст блока 2. Текст блока 3...",  # объединенный текст
        "page_num": 0,
        "merged_from": [0, 1, 2]  # индексы исходных блоков
    },
    ...
]
```

### Шаг 9: Создание элементов и построение финальной иерархии

**Метод:** `PdfParser._create_elements_from_hierarchy(hierarchy: Dict, text_elements: List[Dict]) -> List[Element]`

**Логика:**
1. **Создание элементов заголовков:**
   - Для каждого `Section-header` создаем `Element` с типом `HEADER_1`, `HEADER_2` и т.д.
   - Определяем `parent_id` на основе иерархии уровней
   - Сохраняем метаданные (bbox, page_num, исходная категория)

2. **Создание текстовых элементов:**
   - Для каждого текстового блока создаем `Element` с типом `TEXT`
   - Определяем `parent_id` (заголовок, под которым находится блок)
   - Сохраняем текст и метаданные

3. **Создание элементов таблиц:**
   - Для каждой таблицы создаем `Element` с типом `TABLE`
   - Пока сохраняем только bbox и метаданные (содержимое будет извлечено на шаге 11)
   - Определяем `parent_id`

4. **Создание элементов изображений:**
   - Для каждого `Picture` создаем `Element` с типом `IMAGE`
   - Сохраняем bbox и метаданные
   - Ищем связанный `Caption` (ближайший по координатам)
   - Сохраняем изображение в метаданных (шаг 10)

5. **Построение стека иерархии:**
   - Используем стек заголовков для отслеживания текущего контекста
   - При встрече заголовка обновляем стек
   - Все последующие элементы получают `parent_id` от последнего заголовка в стеке

**Результат:**
```python
elements: List[Element] = [
    Element(
        id="00000001",
        type=ElementType.HEADER_1,
        content="1 INTRODUCTION",
        parent_id=None,
        metadata={"bbox": [...], "page_num": 0, "category": "Section-header"}
    ),
    Element(
        id="00000002",
        type=ElementType.TEXT,
        content="Текст параграфа...",
        parent_id="00000001",
        metadata={"bbox": [...], "page_num": 0, "category": "Text"}
    ),
    ...
]
```

### Шаг 10: Хранение изображений в метаданных

**Метод:** `PdfParser._store_images_in_metadata(elements: List[Element], pdf_path: str) -> List[Element]`

**Логика:**
1. **Для каждого элемента типа IMAGE:**
   - Извлекаем изображение из PDF по bbox через PyMuPDF
   - Конвертируем в base64 или сохраняем во временный файл
   - Сохраняем путь/данные в `metadata["image_data"]` или `metadata["image_path"]`

2. **Для связанных Caption:**
   - Ищем ближайший `Caption` элемент к `Picture`
   - Сохраняем текст подписи в `metadata["caption"]`
   - Если `Caption` находится перед `Picture` → создаем отдельный элемент `CAPTION` с `parent_id` на изображение

**Результат:**
```python
image_element = Element(
    id="00000010",
    type=ElementType.IMAGE,
    content="",  # пустой контент
    parent_id="00000005",
    metadata={
        "bbox": [x1, y1, x2, y2],
        "page_num": 1,
        "category": "Picture",
        "image_data": "base64_encoded_image_data",  # или
        "image_path": "/tmp/image_00000010.png",
        "caption": "Figure 1: Описание изображения"
    }
)
```

### Шаг 11: Парсинг таблиц через Qwen2.5

**Метод:** `PdfParser._parse_tables_with_qwen(table_elements: List[Element], pdf_path: str) -> List[Element]`

**Логика:**
1. **Для каждой таблицы:**
   - Рендерим область таблицы из PDF (по bbox)
   - Отправляем изображение таблицы в Qwen2.5 с промптом для парсинга

2. **Варианты парсинга:**
   
   **Вариант A: Markdown таблица**
   - Промпт: "Extract this table and return it as a Markdown table"
   - Получаем Markdown таблицу
   - Парсим Markdown в pandas DataFrame
   - Сохраняем DataFrame в `metadata["dataframe"]`
   - Сохраняем Markdown в `content`

   **Вариант B: Прямой DataFrame**
   - Промпт: "Extract this table and return it as JSON array of arrays"
   - Получаем JSON с данными таблицы
   - Создаем pandas DataFrame напрямую
   - Сохраняем DataFrame в `metadata["dataframe"]`
   - Сохраняем JSON в `content`

3. **Обработка склеенных таблиц:**
   - **Проблема:** Несколько таблиц могут быть склеены в один блок
   - **Решение:**
     - Анализируем структуру таблицы (количество столбцов, заголовки)
     - Ищем "разрывы" в структуре (изменение количества столбцов, повторение заголовков)
     - Если находим разрывы → разделяем на несколько таблиц
     - Для каждой части создаем отдельный `Element` с типом `TABLE`

4. **Валидация таблиц:**
   - Проверяем, что таблица имеет структуру (заголовки, строки)
   - Если таблица невалидна → сохраняем как TEXT с метаданными о попытке парсинга

**Конфигурация:**
```yaml
# config/pdf_config.yaml
table_parsing:
  method: "markdown"  # или "dataframe"
  qwen_model: "qwen2.5-coder"
  detect_merged_tables: true
  merge_threshold: 0.1  # порог для определения склеенных таблиц
```

**Промпт для Qwen2.5:**
```python
TABLE_PARSING_PROMPT = """
Extract the table from this image and return it as a Markdown table.

Requirements:
1. Preserve all headers and data
2. Use proper Markdown table format
3. If multiple tables are merged, separate them clearly
4. Handle merged cells appropriately

Output only the Markdown table, no additional text.
"""
```

**Результат:**
```python
table_element = Element(
    id="00000015",
    type=ElementType.TABLE,
    content="| Header1 | Header2 |\n|---------|---------|\n| Data1   | Data2   |",  # Markdown
    parent_id="00000005",
    metadata={
        "bbox": [x1, y1, x2, y2],
        "page_num": 2,
        "category": "Table",
        "dataframe": <pandas.DataFrame>,  # DataFrame для удобства работы
        "parsing_method": "markdown"
    }
)
```

**Обработка склеенных таблиц:**
```python
# Если обнаружены склеенные таблицы:
merged_table_element = Element(
    id="00000015",
    type=ElementType.TABLE,
    content="| Table 1 Header | ... |\n| ... | ... |\n\n| Table 2 Header | ... |\n| ... | ... |",
    metadata={
        "merged_tables": True,
        "table_count": 2,
        "dataframes": [<DataFrame1>, <DataFrame2>]
    }
)

# Или разделяем на отдельные элементы:
table1_element = Element(id="00000015", type=ElementType.TABLE, ...)
table2_element = Element(id="00000016", type=ElementType.TABLE, ...)
```

### Шаг 12: Финальная сборка ParsedDocument

**Метод:** `PdfParser._create_parsed_document(source: str, elements: List[Element]) -> ParsedDocument`

**Логика:**
- Создаем `ParsedDocument` со всеми элементами
- Добавляем метаданные:
  ```python
  metadata = {
      "parser": "pdf",
      "status": "completed",
      "processing_method": "layout_based",
      "total_pages": 78,
      "elements_count": len(elements),
      "headers_count": len([e for e in elements if e.type.name.startswith("HEADER")]),
      "tables_count": len([e for e in elements if e.type == ElementType.TABLE]),
      "images_count": len([e for e in elements if e.type == ElementType.IMAGE]),
  }
  ```
- Валидируем документ (проверка иерархии, уникальности ID и т.д.)

## Последовательность вызовов методов

```python
def parse(self, document: Document) -> ParsedDocument:
    # Шаг 1: Валидация
    self._validate_input(document)
    source = self.get_source(document)
    
    # Шаг 2: Проверка выделяемого текста
    is_text_extractable = self._is_text_extractable(source)
    
    if is_text_extractable:
        # Шаг 3: Layout Detection
        layout_elements = self._detect_layout_for_all_pages(source)
        
        # Шаг 4: Построение иерархии от Section-header
        hierarchy = self._build_hierarchy_from_section_headers(layout_elements)
        
        # Шаг 5: Фильтрация лишних элементов
        filtered_elements = self._filter_layout_elements(layout_elements)
        
        # Шаг 6: Анализ заголовков по уровням
        analyzed_hierarchy = self._analyze_header_levels(hierarchy)
        
        # Шаг 7: Извлечение текста через PyMuPDF
        text_elements = self._extract_text_by_bboxes(source, filtered_elements)
        
        # Шаг 8: Склеивание близких текстовых блоков
        merged_text_elements = self._merge_nearby_text_blocks(
            text_elements, 
            max_chunk_size=self.config.get("text_merging.max_chunk_size", 3000)
        )
        
        # Шаг 9: Создание элементов
        elements = self._create_elements_from_hierarchy(analyzed_hierarchy, merged_text_elements)
        
        # Шаг 10: Хранение изображений в метаданных
        elements = self._store_images_in_metadata(elements, source)
        
        # Шаг 11: Парсинг таблиц через Qwen2.5
        elements = self._parse_tables_with_qwen(elements, source)
        
        # Шаг 12: Создание ParsedDocument
        parsed_document = self._create_parsed_document(source, elements)
        
        return parsed_document
    else:
        # OCR путь (рендеринг + Dots.OCR + Qwen OCR)
        return self._parse_with_ocr(document)
```

## Конфигурация

```yaml
# config/pdf_config.yaml
pdf_parser:
  # Проверка выделяемого текста
  text_extraction:
    min_text_length: 100  # минимальная длина текста для определения "выделяемого"
    quality_threshold: 0.5  # порог качества текста
  
  # Layout Detection
  layout_detection:
    render_scale: 2.0  # увеличение при рендеринге
    optimize_for_ocr: true
    use_direct_api: true  # использовать прямой вызов API
  
  # Фильтрация
  filtering:
    remove_page_headers: true
    remove_page_footers: true
    main_area:
      min_x: 290
      max_x: 1400
    side_text:
      max_x: 100
      min_width_ratio: 0.1
  
  # Склеивание текста
  text_merging:
    max_chunk_size: 3000  # настраивается!
    merge_threshold_y: 50
    merge_threshold_x: 100
    split_by_sentences: true
  
  # Парсинг таблиц
  table_parsing:
    method: "markdown"  # или "dataframe"
    qwen_model: "qwen2.5-coder"
    detect_merged_tables: true
    merge_threshold: 0.1
```

## Зависимости и компоненты

### Основные компоненты:
1. **PdfPageRenderer** (`ocr/page_renderer.py`)
   - Рендеринг страниц PDF в изображения

2. **PdfLayoutDetector** (`ocr/layout_detector.py`)
   - Layout detection через Dots.OCR

3. **PyMuPDF (fitz)**
   - Извлечение текста по координатам
   - Извлечение изображений

4. **Qwen2.5**
   - Парсинг таблиц из изображений

5. **Utils:**
   - `_filter_layout_elements()` - фильтрация элементов
   - `_merge_nearby_text_blocks()` - склеивание текста
   - `_build_hierarchy_from_section_headers()` - построение иерархии
   - `_analyze_header_levels()` - анализ уровней заголовков

## Текущий статус реализации

**Реализовано:**
- ✅ Базовая структура `PdfParser`
- ✅ `PdfPageRenderer` - рендеринг страниц
- ✅ `PdfLayoutDetector` - layout detection через Dots.OCR
- ✅ Интеграция с `DotsOCRManager`
- ✅ Структура `Element` и `ParsedDocument`

**Требует реализации:**
- ❌ `_is_text_extractable()` - проверка выделяемого текста
- ❌ `_detect_layout_for_all_pages()` - layout detection для всех страниц
- ❌ `_build_hierarchy_from_section_headers()` - построение иерархии
- ❌ `_filter_layout_elements()` - фильтрация элементов
- ❌ `_analyze_header_levels()` - анализ уровней заголовков
- ❌ `_extract_text_by_bboxes()` - извлечение текста через PyMuPDF
- ❌ `_merge_nearby_text_blocks()` - склеивание текста
- ❌ `_create_elements_from_hierarchy()` - создание элементов
- ❌ `_store_images_in_metadata()` - хранение изображений
- ❌ `_parse_tables_with_qwen()` - парсинг таблиц через Qwen2.5
- ❌ Обработка склеенных таблиц

## Примечания

1. **Layout-based подход:**
   - Используем layout detection как основу, а не как дополнительный инструмент
   - Это позволяет работать с любыми PDF, даже если текст не идеально выделяется

2. **Производительность:**
   - Layout detection выполняется для всех страниц (может быть медленно)
   - Склеивание текста уменьшает количество элементов
   - Парсинг таблиц через Qwen2.5 может быть медленным для больших таблиц

3. **Качество:**
   - Фильтрация лишних элементов улучшает качество структуры
   - Анализ уровней заголовков требует эвристик или ML модели
   - Обработка склеенных таблиц - сложная задача

4. **Гибкость:**
   - Все параметры настраиваются через конфигурацию
   - Поддержка разных методов парсинга таблиц
   - Возможность расширения для других категорий элементов

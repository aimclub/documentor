# Логика PDF парсера для выделяемого текста (Selectable Text Path)

## Обзор

PDF парсер поддерживает два пути обработки:
1. **Текстовый путь** (selectable text) - для PDF с выделяемым текстом
2. **OCR путь** (scan) - для отсканированных PDF

Данный документ описывает **полный путь обработки для выделяемого текста**.

## Архитектура пути обработки

```
PDF Document (LangChain Document)
    ↓
PdfParser.parse()
    ↓
_is_text_extractable() - определение типа PDF
    ↓ [текст выделяется]
_parse_with_text_extraction()
```

## Детальный путь обработки

### Шаг 1: Определение типа PDF

**Метод:** `PdfParser._is_text_extractable(source: str) -> bool`

**Логика:**
- Использует `PdfTextExtractor.is_text_extractable()`
- Открывает PDF через PdfPlumber
- Проверяет наличие текстового слоя
- Оценивает качество текста (количество символов, наличие осмысленного текста)
- Возвращает `True`, если текст можно извлечь, `False` иначе

**Реализация:**
```python
def _is_text_extractable(self, source: str) -> bool:
    return self.text_extractor.is_text_extractable(source)
```

### Шаг 2: Извлечение текста и структуры

**Метод:** `PdfTextExtractor.extract_text()` и `extract_structure()`

**Логика:**
1. **Извлечение текста:**
   - Открывает PDF через PdfPlumber
   - Извлекает текст по страницам
   - Объединяет текст со всех страниц
   - Возвращает полный текст документа

2. **Извлечение структуры:**
   - Извлекает абзацы с координатами (bbox)
   - Извлекает таблицы с их содержимым
   - Сохраняет метаданные (шрифты, размеры, позиции)
   - Возвращает структурированные данные

**Результат:**
- `text: str` - полный текст документа
- `structure: Dict` - словарь со структурой:
  ```python
  {
      "paragraphs": [
          {
              "text": "...",
              "bbox": [x1, y1, x2, y2],
              "page_num": 0,
              "font": "...",
              "font_size": 12
          },
          ...
      ],
      "tables": [
          {
              "data": [[...], [...]],
              "bbox": [x1, y1, x2, y2],
              "page_num": 0
          },
          ...
      ],
      "metadata": {...}
  }
  ```

### Шаг 3: Разбиение текста на чанки с перекрытием

**Метод:** `split_with_overlap(text, chunk_size=3000, overlap_size=500)`

**Логика:**
- Разбивает текст на чанки размером ~3000 символов
- Добавляет перекрытие ~500 символов между чанками (для сохранения контекста)
- Сохраняет порядок чанков

**Зачем:**
- LLM имеет ограничения на длину входного текста
- Перекрытие необходимо для корректного детектирования заголовков на границах чанков
- Позволяет обрабатывать большие документы

**Результат:**
```python
chunks: List[str] = [
    "Чанк 1 (символы 0-3000)",
    "Чанк 2 (символы 2500-5500)",  # перекрытие 500 символов
    "Чанк 3 (символы 5000-8000)",
    ...
]
```

### Шаг 4: Детектирование заголовков через LLM

**Метод:** `HeaderDetector.detect_headers(chunk, previous_headers)`

**Логика:**
1. **Для каждого чанка:**
   - Подготавливает промпт с текстом чанка
   - Передает предыдущие заголовки для контекста (важно для иерархии)
   - Вызывает LLM (Qwen или другая модель) для определения заголовков
   - Парсит JSON ответ от LLM

2. **Валидация иерархии:**
   - Проверяет логику уровней (HEADER_2 не может быть внутри HEADER_1)
   - Исправляет ошибки иерархии при необходимости

3. **Объединение заголовков:**
   - Объединяет заголовки из всех чанков
   - Устраняет дубликаты на границах чанков (благодаря перекрытию)
   - Строит единую структуру заголовков

**Результат:**
```python
all_headers: List[HeaderInfo] = [
    HeaderInfo(
        text="Введение",
        level=1,
        position=0,
        element_type=ElementType.HEADER_1
    ),
    HeaderInfo(
        text="Методы",
        level=1,
        position=500,
        element_type=ElementType.HEADER_1
    ),
    HeaderInfo(
        text="Экспериментальная установка",
        level=2,
        position=1200,
        element_type=ElementType.HEADER_2
    ),
    ...
]
```

### Шаг 5: Парсинг ключевых слов для структурных элементов

**Логика:**
- Ищет в тексте ключевые слова для структурных элементов:
  - **Таблицы:** "Table 1", "Table 2", "Таблица 1", "Табл. 1" и т.д.
  - **Рисунки:** "Figure 1", "Figure 2", "Рис. 1", "Рисунок 1", "Fig. 1" и т.д.
  - **Изображения:** "Image 1", "Image 2", "Изображение 1" и т.д.
  - **Формулы:** "Equation 1", "Формула 1", "(1)", "(2)" и т.д.

- **Определение контекста:**
  - Проверяет, находятся ли ключевые слова внутри таблицы (используя bbox из структуры)
  - Если ключевые слова в таблице → требуется дополнительная обработка через DotsOCR

**Результат:**
```python
structural_elements: List[Dict] = [
    {
        "type": "table",
        "reference": "Table 1",
        "position": 1500,
        "in_table": False,  # находится ли ссылка в таблице
        "bbox": [x1, y1, x2, y2]  # координаты элемента (если найдены)
    },
    {
        "type": "figure",
        "reference": "Figure 1",
        "position": 2000,
        "in_table": True,  # ссылка находится в таблице
        "bbox": None
    },
    ...
]
```

### Шаг 6: Вызов DotsOCR для структурных элементов (при необходимости)

**Условие:** Если найдены ключевые слова в таблице или требуется извлечение структурных элементов

**Логика:**
1. **Для каждого структурного элемента:**
   - Если элемент находится в таблице → рендерим соответствующую страницу
   - Вызываем DotsOCR для layout detection этой области
   - Извлекаем точные координаты и содержимое элемента

2. **Извлечение всех структурных элементов:**
   - Рендерим страницы, где найдены структурные элементы
   - Вызываем DotsOCR для каждой страницы
   - Извлекаем:
     - Таблицы с их содержимым (HTML формат)
     - Изображения с подписями (Caption)
     - Формулы (LaTeX формат)

**Результат:**
```python
extracted_elements: List[Dict] = [
    {
        "type": "table",
        "reference": "Table 1",
        "content": "<table>...</table>",  # HTML
        "bbox": [x1, y1, x2, y2],
        "page_num": 0
    },
    {
        "type": "image",
        "reference": "Figure 1",
        "content": "base64_image_data",
        "caption": "Подпись к рисунку",
        "bbox": [x1, y1, x2, y2],
        "page_num": 1
    },
    ...
]
```

### Шаг 7: Построение иерархии элементов

**Метод:** `PdfParser._build_elements_from_text(text, headers, structural_elements)`

**Логика:**
1. **Создание элементов заголовков:**
   - Для каждого заголовка создается `Element` с типом `HEADER_1`, `HEADER_2` и т.д.
   - Определяется `parent_id` на основе иерархии заголовков (используется стек заголовков)
   - Сохраняются метаданные (позиция, уровень)

2. **Создание текстовых элементов:**
   - Текст между заголовками разбивается на параграфы
   - Для каждого параграфа создается `Element` с типом `TEXT`
   - Определяется `parent_id` (последний заголовок в стеке)

3. **Создание структурных элементов:**
   - Для каждой таблицы создается `Element` с типом `TABLE`
   - Для каждого изображения создается `Element` с типом `IMAGE`
   - Для каждой формулы создается `Element` с типом `FORMULA`
   - Определяется `parent_id` (заголовок, под которым находится элемент)

4. **Построение стека иерархии:**
   - Используется стек заголовков для отслеживания текущего контекста
   - При встрече заголовка обновляется стек (удаляются заголовки с уровнем >= текущего)
   - Все последующие элементы получают `parent_id` от последнего заголовка в стеке

**Алгоритм построения стека:**
```python
header_stack: List[tuple[int, str]] = []  # (уровень, element_id)

for header in headers:
    level = header.level
    # Удаляем заголовки с уровнем >= текущего
    while header_stack and header_stack[-1][0] >= level:
        header_stack.pop()
    
    # Создаем элемент заголовка
    parent_id = header_stack[-1][1] if header_stack else None
    element = create_element(
        type=header.element_type,
        content=header.text,
        parent_id=parent_id
    )
    
    # Добавляем в стек
    header_stack.append((level, element.id))

# Для текстовых элементов
for paragraph in paragraphs:
    parent_id = header_stack[-1][1] if header_stack else None
    element = create_element(
        type=ElementType.TEXT,
        content=paragraph,
        parent_id=parent_id
    )
```

**Результат:**
```python
elements: List[Element] = [
    Element(
        id="00000001",
        type=ElementType.HEADER_1,
        content="Введение",
        parent_id=None
    ),
    Element(
        id="00000002",
        type=ElementType.TEXT,
        content="Текст параграфа...",
        parent_id="00000001"  # дочерний элемент заголовка "Введение"
    ),
    Element(
        id="00000003",
        type=ElementType.HEADER_1,
        content="Методы",
        parent_id=None
    ),
    Element(
        id="00000004",
        type=ElementType.HEADER_2,
        content="Экспериментальная установка",
        parent_id="00000003"  # дочерний элемент заголовка "Методы"
    ),
    Element(
        id="00000005",
        type=ElementType.TABLE,
        content="<table>...</table>",
        parent_id="00000004"  # дочерний элемент заголовка "Экспериментальная установка"
    ),
    ...
]
```

### Шаг 8: Создание ParsedDocument

**Метод:** `PdfParser._create_parsed_document(source, elements, metadata)`

**Логика:**
- Создает `ParsedDocument` с:
  - `source`: путь к исходному PDF файлу
  - `format`: `DocumentFormat.PDF`
  - `elements`: список всех созданных элементов
  - `metadata`: дополнительные метаданные:
    ```python
    {
        "parser": "pdf",
        "status": "completed",
        "text_length": 50000,
        "paragraphs_count": 120,
        "headers_count": 15,
        "tables_count": 5,
        "images_count": 3,
        "processing_method": "text_extraction"
    }
    ```

- **Валидация:**
  - Проверяет уникальность `id` элементов
  - Проверяет корректность `parent_id` (все ссылаются на существующие элементы)
  - Проверяет отсутствие циклов в иерархии
  - Проверяет базовые поля каждого элемента

**Результат:**
```python
parsed_document = ParsedDocument(
    source="/path/to/document.pdf",
    format=DocumentFormat.PDF,
    elements=[...],  # список всех элементов
    metadata={...}
)
```

## Последовательность вызовов методов

```python
def parse(self, document: Document) -> ParsedDocument:
    # 1. Валидация входных данных
    self._validate_input(document)
    
    source = self.get_source(document)
    
    # 2. Определение типа PDF
    is_text_extractable = self._is_text_extractable(source)
    
    if is_text_extractable:
        # 3. Текстовый путь
        return self._parse_with_text_extraction(document)
    else:
        # 4. OCR путь
        return self._parse_with_ocr(document)

def _parse_with_text_extraction(self, document: Document) -> ParsedDocument:
    source = self.get_source(document)
    
    # Шаг 1: Извлечение текста и структуры
    text = self.text_extractor.extract_text(source)
    structure = self.text_extractor.extract_structure(source)
    
    # Шаг 2: Разбиение на чанки
    chunks = split_with_overlap(text, chunk_size=3000, overlap_size=500)
    
    # Шаг 3: Детектирование заголовков
    if self.header_detector is None:
        self.header_detector = HeaderDetector()
    
    all_headers = []
    previous_headers = None
    for chunk in chunks:
        headers = self.header_detector.detect_headers(chunk, previous_headers)
        all_headers.extend(headers)
        previous_headers = headers
    
    # Объединение заголовков
    merged_headers = self.header_detector.merge_headers([all_headers])
    
    # Шаг 4: Парсинг ключевых слов
    structural_elements = self._parse_structural_keywords(text, structure)
    
    # Шаг 5: Вызов DotsOCR (если необходимо)
    if self._needs_ocr_processing(structural_elements):
        extracted_elements = self._extract_with_dots_ocr(source, structural_elements)
        structural_elements = self._merge_structural_elements(
            structural_elements, extracted_elements
        )
    
    # Шаг 6: Построение иерархии элементов
    elements = self._build_elements_from_text(text, merged_headers, structural_elements)
    
    # Шаг 7: Создание ParsedDocument
    parsed_document = ParsedDocument(
        source=source,
        format=self.format,
        elements=elements,
        metadata={
            "parser": "pdf",
            "status": "completed",
            "processing_method": "text_extraction",
            ...
        }
    )
    
    return parsed_document
```

## Зависимости и компоненты

### Основные компоненты:
1. **PdfTextExtractor** (`text_extractor.py`)
   - Извлечение текста через PdfPlumber
   - Извлечение структуры (абзацы, таблицы)

2. **HeaderDetector** (`llm/header_detector.py`)
   - Детектирование заголовков через LLM
   - Валидация иерархии
   - Объединение заголовков из разных чанков

3. **DotsOCRManager** (`ocr/manager.py`)
   - Управление очередями задач на OCR
   - Вызов DotsOCR для layout detection
   - Извлечение структурных элементов

4. **PdfLayoutDetector** (`ocr/layout_detector.py`)
   - Layout detection через DotsOCR
   - Определение структуры страницы

5. **Utils:**
   - `split_with_overlap()` - разбиение текста на чанки
   - `_build_elements_from_text()` - построение иерархии элементов

## Текущий статус реализации

**Реализовано:**
- ✅ Базовая структура `PdfParser`
- ✅ Класс `PdfTextExtractor` (заглушка)
- ✅ Класс `HeaderDetector` (заглушка)
- ✅ Интеграция с `DotsOCRManager`
- ✅ Структура `Element` и `ParsedDocument`

**Требует реализации:**
- ❌ `PdfTextExtractor.is_text_extractable()` - определение типа PDF
- ❌ `PdfTextExtractor.extract_text()` - извлечение текста
- ❌ `PdfTextExtractor.extract_structure()` - извлечение структуры
- ❌ `HeaderDetector.detect_headers()` - детектирование заголовков через LLM
- ❌ `PdfParser._parse_structural_keywords()` - парсинг ключевых слов
- ❌ `PdfParser._extract_with_dots_ocr()` - извлечение через DotsOCR
- ❌ `PdfParser._build_elements_from_text()` - построение иерархии элементов
- ❌ `PdfParser._parse_with_text_extraction()` - полная реализация текстового пути

## Примечания

1. **Производительность:**
   - Разбиение на чанки позволяет обрабатывать большие документы
   - Перекрытие между чанками важно для корректного детектирования заголовков
   - DotsOCR вызывается только при необходимости (структурные элементы в таблицах)

2. **Качество:**
   - Оценка качества текста помогает определить, нужен ли OCR путь
   - Валидация иерархии заголовков предотвращает ошибки структурирования
   - Объединение заголовков из разных чанков устраняет дубликаты

3. **Гибкость:**
   - Поддержка различных форматов ключевых слов (английский, русский)
   - Возможность использования разных LLM для детектирования заголовков
   - Интеграция с DotsOCR только при необходимости

# Адаптация пайплайна PDF для DOCX

## Обзор

Данный документ описывает подход к обработке DOCX файлов, аналогичный пайплайну PDF, с использованием Dots.OCR для layout detection.

## ⚠️ Важные замечания

### Проблемы предыдущих подходов:

1. **Стили DOCX ненадежны**: Пользователи не всегда правильно используют стили (Heading 1-6), поэтому мы можем потерять уровни заголовков. Например, заголовок может иметь стиль "Heading 1", но на самом деле быть заголовком 3-го или 4-го уровня.

2. **Сравнение размера шрифта не работает**: Эксперименты показали, что сравнение размера шрифта из встроенных стилей DOCX дает плохие результаты.

3. **Конвертация DOCX → PDF отклонена**: Идея перевода DOCX в PDF для обработки была отклонена.

### Решение: Dots.OCR + текст из DOCX

**Новый подход:**
1. **Первый этап - всегда Dots.OCR**: Dots.OCR сканирует страницу и определяет классы элементов (Section-header, Text, Table и т.д.)
2. **Извлечение текста из DOCX**: Параллельно извлекаем текст из DOCX через python-docx
3. **Сопоставление**: Сопоставляем текст из Dots.OCR bbox с текстом из DOCX
4. **Построение иерархии**: Строим иерархию на основе Dots.OCR (как в PDF)
5. **Определение уровней**: Определяем уровни заголовков на основе анализа текста и контекста (как в PDF)

## Сравнение подходов

### PDF Пайплайн

1. **Layout Detection** через Dots.OCR
   - Рендеринг страниц в изображения
   - Определение типов элементов (Section-header, Text, Table, Picture и т.д.)
   - Получение координат (bbox) для каждого элемента

2. **Построение иерархии**
   - Группировка элементов по Section-header
   - Определение уровней заголовков (HEADER_1, HEADER_2, ...)
   - Создание структуры секций

3. **Извлечение текста**
   - Извлечение текста по координатам через PyMuPDF
   - Склеивание близких текстовых блоков

4. **Обработка специальных элементов**
   - Парсинг таблиц через Qwen2.5
   - Хранение изображений в метаданных

### DOCX Пайплайн (новый подход с Dots.OCR)

1. **Layout Detection** через Dots.OCR (как в PDF)
   - Рендеринг страниц DOCX в изображения (через временный PDF)
   - Определение типов элементов через Dots.OCR (Section-header, Text, Table и т.д.)
   - Получение координат (bbox) для каждого элемента

2. **Извлечение текста из DOCX**
   - Параллельное извлечение текста через python-docx
   - Сохранение метаданных (стили, форматирование, отступы)

3. **Сопоставление текста**
   - Сопоставление текста из Dots.OCR bbox с текстом из DOCX
   - Использование точного текста из DOCX вместо OCR текста

4. **Построение иерархии**
   - Группировка элементов по Section-header (как в PDF)
   - Определение уровней заголовков на основе анализа текста и контекста (как в PDF)
   - Создание структуры секций

5. **Обработка специальных элементов**
   - Парсинг таблиц через Qwen2.5 (если нужно)
   - Хранение изображений в метаданных

## Маппинг данных DOCX → PDF структура

### 1. Layout Elements (аналог Dots.OCR output)

**PDF формат:**
```python
{
    "bbox": [x1, y1, x2, y2],
    "category": "Section-header",  # или "Text", "Table", "Picture"
    "page_num": 0
}
```

**DOCX формат (из `paragraphs_with_metadata`):**
```python
{
    "index": 0,
    "text": "Заголовок",
    "style": "Heading 1",  # или "Normal", "List Paragraph"
    "formatting": {
        "alignment": "left",
        "font_size": "14.0pt",
        "bold": True
    },
    "coordinates": {
        "left_indent": "720",  # в twips (1/20 pt)
        "right_indent": "0",
        "first_line_indent": "0"
    }
}
```

**Маппинг:**
```python
def docx_to_layout_element(para_data: Dict) -> Dict:
    """Преобразует данные параграфа DOCX в формат layout element."""
    
    # Определение категории по стилю
    category_map = {
        "Heading 1": "Section-header",
        "Heading 2": "Section-header",
        "Heading 3": "Section-header",
        "Heading 4": "Section-header",
        "Heading 5": "Section-header",
        "Heading 6": "Section-header",
        "Normal": "Text",
        "List Paragraph": "List-item",
        "Title": "Title",
    }
    
    category = category_map.get(para_data["style"], "Text")
    
    # Преобразование отступов в координаты (аналог bbox)
    # В DOCX нет точных координат, но можно использовать отступы
    left_indent = int(para_data.get("coordinates", {}).get("left_indent", 0) or 0) / 20  # twips -> pt
    right_indent = int(para_data.get("coordinates", {}).get("right_indent", 0) or 0) / 20
    
    # Создаем виртуальный bbox на основе отступов
    # Для DOCX используем относительные координаты
    bbox = [
        left_indent,  # x1
        0,  # y1 (будет вычисляться по порядку параграфов)
        left_indent + 500,  # x2 (примерная ширина)
        20  # y2 (высота параграфа)
    ]
    
    return {
        "bbox": bbox,
        "category": category,
        "page_num": 0,  # В DOCX нет страниц, используем 0
        "paragraph_index": para_data["index"],
        "text": para_data["text"],
        "style": para_data["style"],
        "metadata": para_data["formatting"]
    }
```

### 2. Определение уровней заголовков

**PDF подход:**
- Анализ текста заголовка (нумерация: "1.1", "1.2.3")
- Сравнение размера шрифта с предыдущими заголовками
- Использование контекста (last_numbered_level)

**DOCX подход:**
- Использование встроенных стилей (Heading 1 → HEADER_1, Heading 2 → HEADER_2)
- Дополнительная проверка через анализ текста (нумерация)
- Сравнение размера шрифта из метаданных

```python
def determine_header_level_docx(para_data: Dict, previous_headers: List[Dict]) -> int:
    """Определяет уровень заголовка для DOCX."""
    
    style = para_data.get("style", "")
    text = para_data.get("text", "")
    
    # Приоритет 1: Встроенные стили DOCX
    if style.startswith("Heading"):
        level = int(style.split()[-1])  # "Heading 1" -> 1
        return min(level, 6)  # Ограничиваем максимум 6
    
    # Приоритет 2: Анализ нумерации в тексте
    if re.match(r'^\d+\s+[A-Z]', text):
        return 1
    if re.match(r'^\d+\.\d+\s+', text):
        return 2
    if re.match(r'^\d+\.\d+\.\d+\s+', text):
        return 3
    
    # Приоритет 3: Сравнение размера шрифта с предыдущими
    font_size = para_data.get("formatting", {}).get("font_size")
    if font_size and previous_headers:
        # Извлекаем размер шрифта (например, "14.0pt" -> 14.0)
        try:
            current_size = float(font_size.replace("pt", ""))
            last_header = previous_headers[-1]
            last_size = float(last_header.get("formatting", {}).get("font_size", "12pt").replace("pt", ""))
            last_level = last_header.get("level", 1)
            
            if current_size >= last_size + 2:
                return max(1, last_level - 1)
            elif current_size <= last_size - 2:
                return min(6, last_level + 1)
            else:
                return last_level
        except:
            pass
    
    # По умолчанию
    return 1
```

### 3. Построение иерархии

**PDF подход:**
```python
def _build_hierarchy_from_section_headers(layout_elements):
    sections = []
    current_section = None
    
    for element in layout_elements:
        if element["category"] == "Section-header":
            if current_section:
                sections.append(current_section)
            current_section = {
                "header": element,
                "children": []
            }
        else:
            if current_section:
                current_section["children"].append(element)
    
    if current_section:
        sections.append(current_section)
    
    return sections
```

**DOCX подход (адаптированный):**
```python
def build_hierarchy_from_docx(paragraphs_data: List[Dict]) -> List[Dict]:
    """Строит иерархию из параграфов DOCX, аналогично PDF."""
    
    sections = []
    current_section = None
    previous_headers = []
    
    for para in paragraphs_data:
        # Определяем уровень заголовка
        if para.get("is_heading") or para.get("style", "").startswith("Heading"):
            level = determine_header_level_docx(para, previous_headers)
            
            # Сохраняем предыдущий заголовок
            previous_headers.append({
                "level": level,
                "text": para["text"],
                "formatting": para["formatting"]
            })
            
            # Начинаем новую секцию
            if current_section:
                sections.append(current_section)
            
            current_section = {
                "header": {
                    "text": para["text"],
                    "level": level,
                    "style": para["style"],
                    "index": para["index"],
                    "bbox": para.get("coordinates", {}),
                    "category": "Section-header"
                },
                "children": []
            }
        else:
            # Добавляем в текущую секцию
            if current_section:
                layout_element = docx_to_layout_element(para)
                current_section["children"].append(layout_element)
            else:
                # Если нет заголовка, создаем секцию "Начало документа"
                if not sections or sections[-1].get("header", {}).get("text") != "Начало документа":
                    current_section = {
                        "header": {
                            "text": "Начало документа",
                            "level": 0,
                            "category": "Title"
                        },
                        "children": []
                    }
                else:
                    current_section = sections[-1]
                
                layout_element = docx_to_layout_element(para)
                current_section["children"].append(layout_element)
    
    if current_section:
        sections.append(current_section)
    
    return sections
```

### 4. Извлечение текста

**PDF подход:**
- Извлечение текста по bbox через PyMuPDF
- Склеивание близких текстовых блоков

**DOCX подход:**
- Текст уже извлечен из параграфов
- Группировка параграфов по секциям
- Склеивание параграфов в пределах секции

```python
def extract_text_from_docx_section(section: Dict) -> str:
    """Извлекает текст из секции DOCX."""
    
    text_parts = []
    
    for child in section["children"]:
        if child["category"] == "Text":
            text_parts.append(child["text"])
        elif child["category"] == "List-item":
            text_parts.append(f"• {child['text']}")
    
    return "\n".join(text_parts)
```

### 5. Обработка таблиц

**PDF подход:**
- Обнаружение таблиц через Dots.OCR (category: "Table")
- Парсинг содержимого через Qwen2.5

**DOCX подход:**
- Извлечение таблиц из `tables_info` (уже есть в данных)
- Преобразование в формат Element

```python
def process_tables_from_docx(tables_info: List[Dict]) -> List[Element]:
    """Обрабатывает таблицы из DOCX."""
    
    elements = []
    
    for table in tables_info:
        # Преобразуем таблицу в markdown формат
        markdown_table = "| " + " | ".join(table["data"][0]) + " |\n"
        markdown_table += "| " + " | ".join(["---"] * len(table["data"][0])) + " |\n"
        
        for row in table["data"][1:]:
            markdown_table += "| " + " | ".join(row) + " |\n"
        
        element = Element(
            type=ElementType.TABLE,
            content=markdown_table,
            metadata={
                "table_index": table["index"],
                "rows": table["rows"],
                "columns": table["columns"]
            }
        )
        elements.append(element)
    
    return elements
```

## Полный пайплайн для DOCX

```python
def parse_docx_like_pdf(docx_path: Path) -> ParsedDocument:
    """
    Парсит DOCX используя подход, аналогичный PDF пайплайну.
    """
    
    # Шаг 1: Загрузка данных (уже извлеченных)
    with open(docx_path.parent / "docx_extraction_results" / f"{docx_path.stem}_full_data.json") as f:
        data = json.load(f)
    
    paragraphs_metadata = data["paragraphs_with_metadata"]
    tables_info = data["tables"]
    
    # Шаг 2: Преобразование в layout elements (аналог Dots.OCR output)
    layout_elements = [docx_to_layout_element(para) for para in paragraphs_metadata]
    
    # Шаг 3: Анализ уровней заголовков
    analyzed_elements = analyze_header_levels_docx(layout_elements)
    
    # Шаг 4: Построение иерархии
    hierarchy = build_hierarchy_from_docx(analyzed_elements)
    
    # Шаг 5: Создание элементов
    elements = []
    
    for section in hierarchy:
        # Заголовок
        header_element = Element(
            type=ElementType[f"HEADER_{section['header']['level']}"],
            content=section["header"]["text"],
            metadata={
                "style": section["header"]["style"],
                "index": section["header"]["index"]
            }
        )
        elements.append(header_element)
        
        # Дочерние элементы (текст, списки)
        for child in section["children"]:
            if child["category"] == "Text":
                text_element = Element(
                    type=ElementType.TEXT,
                    content=child["text"],
                    metadata=child.get("metadata", {})
                )
                elements.append(text_element)
            elif child["category"] == "List-item":
                list_element = Element(
                    type=ElementType.LIST_ITEM,
                    content=child["text"],
                    metadata=child.get("metadata", {})
                )
                elements.append(list_element)
    
    # Шаг 6: Обработка таблиц
    table_elements = process_tables_from_docx(tables_info)
    elements.extend(table_elements)
    
    # Шаг 7: Создание ParsedDocument
    parsed_document = ParsedDocument(
        source=str(docx_path),
        format=DocumentFormat.DOCX,
        elements=elements,
        metadata={
            "parser": "docx_pdf_like",
            "status": "completed",
            "processing_method": "style_based_hierarchy",
            "sections_count": len(hierarchy),
            "tables_count": len(tables_info)
        }
    )
    
    return parsed_document
```

## Ключевые отличия и решения

### 1. Координаты (bbox)

**Проблема:** В DOCX нет точных координат как в PDF.

**Решение:**
- Использовать отступы (left_indent, right_indent) как относительные координаты
- Использовать порядок параграфов для определения Y-координат
- Создавать виртуальные bbox на основе отступов и порядка

### 2. Страницы

**Проблема:** В DOCX нет понятия страниц.

**Решение:**
- Использовать `page_num: 0` для всех элементов
- Или вычислять виртуальные страницы на основе количества параграфов

### 3. Layout Detection

**Проблема:** Нет Dots.OCR для DOCX.

**Решение:**
- Использовать встроенные стили DOCX как категории
- Маппинг: Heading 1-6 → Section-header, Normal → Text, List Paragraph → List-item

### 4. Извлечение текста

**Проблема:** Не нужно извлекать текст по координатам.

**Решение:**
- Использовать уже извлеченный текст из параграфов
- Группировать параграфы по секциям

## Преимущества подхода

1. **Единообразие:** Одинаковая структура данных для PDF и DOCX
2. **Переиспользование кода:** Можно использовать общие функции для построения иерархии
3. **Консистентность:** Одинаковый формат выходных данных (ParsedDocument)

## Недостатки и ограничения

1. **Неточные координаты:** В DOCX нет точных координат, только отступы
2. **Нет layout detection:** Нельзя определить сложные layout структуры
3. **Зависимость от стилей:** Качество зависит от правильного использования стилей в документе

## Новый подход: Dots.OCR + текст из DOCX

### Проблемы предыдущих подходов

1. **Стили DOCX ненадежны**: Пользователи не всегда правильно используют стили (Heading 1-6), поэтому мы можем потерять уровни заголовков. Например, заголовок может иметь стиль "Heading 1", но на самом деле быть заголовком 3-го или 4-го уровня.

2. **Сравнение размера шрифта не работает**: Эксперименты показали, что сравнение размера шрифта из встроенных стилей DOCX дает плохие результаты.

3. **Конвертация DOCX → PDF отклонена**: Идея перевода DOCX в PDF для обработки была отклонена.

### Решение: Dots.OCR + текст из DOCX

**Новый подход:**
1. **Первый этап - всегда Dots.OCR**: Dots.OCR сканирует страницу и определяет классы элементов (Section-header, Text, Table и т.д.)
2. **Извлечение текста из DOCX**: Параллельно извлекаем текст из DOCX через python-docx
3. **Сопоставление**: Сопоставляем текст из Dots.OCR bbox с текстом из DOCX
4. **Построение иерархии**: Строим иерархию на основе Dots.OCR (как в PDF)
5. **Определение уровней**: Определяем уровни заголовков на основе анализа текста и контекста (как в PDF)

### Преимущества нового подхода:

1. **Надежность**: Dots.OCR определяет layout независимо от стилей DOCX
2. **Точность текста**: Используем точный текст из DOCX вместо OCR текста
3. **Единообразие**: Одинаковый подход для PDF и DOCX
4. **Гибкость**: Не зависим от правильного использования стилей пользователем

### Реализация:

См. `docx_dots_ocr_pipeline.py` - полная реализация нового подхода.

**Основные шаги:**

1. **Рендеринг DOCX в изображения**:
   - Конвертация DOCX → PDF (временный файл)
   - Рендеринг PDF страниц в изображения через PyMuPDF
   - Оптимизация изображений для OCR

2. **Layout Detection через Dots.OCR**:
   - Использование `process_layout_detection` для каждой страницы
   - Получение элементов с bbox и категориями

3. **Извлечение текста из DOCX**:
   - Использование python-docx для извлечения параграфов
   - Сохранение метаданных (стили, форматирование)

4. **Сопоставление текста**:
   - Поиск соответствий между OCR элементами и DOCX параграфами
   - Использование точного текста из DOCX

5. **Построение иерархии**:
   - Группировка по Section-header (как в PDF)
   - Определение уровней заголовков (анализ нумерации + контекст)

## Рекомендации по реализации

1. Создать класс `DocxParser` с методами, аналогичными `PdfParser`
2. Использовать общий базовый класс для построения иерархии
3. **Использовать Dots.OCR для layout detection (как в PDF)** - это ключевое отличие от предыдущего подхода
4. **Сопоставлять текст из OCR с текстом из DOCX** - использовать точный текст из DOCX
5. Сохранить единый формат выходных данных (ParsedDocument)

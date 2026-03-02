# Краткое резюме: Задача сбора метрик и разметки данных

## Цель

Создать систему объективной оценки качества парсинга документов для сравнения различных парсеров (Documentor, Marker, Dedoc).

## Что оцениваем?

1. **Обнаружение элементов** (Precision, Recall, F1)
2. **Точность порядка** (Ordering Accuracy)
3. **Точность иерархии** (Hierarchy Accuracy)
4. **Структурное сходство документа** (Document TEDS)
5. **Структурное сходство таблиц** (Table TEDS)
6. **Качество извлечения текста** (BLEU, ROUGE)
7. **Качество извлечения таблиц** (HTML структура, содержимое ячеек)
8. **Время на страницу**
9. **Время на документ**
## Формат размеченных данных

### Основная структура

```json
{
  "document_id": "unique_id",
  "source_file": "path/to/document.pdf",
  "document_format": "pdf",
  "annotation_version": "2.0",
  "annotator": "Имя",
  "annotation_date": "2024-01-15T10:30:00Z",
  "elements": [
    // Массив элементов в порядке появления
  ],
  "statistics": {
    "total_elements": 150,
    "total_pages": 10,
    "elements_by_type": {...},
    "table_count": 8,
    "image_count": 15
  }
}
```

### Элемент (базовый формат)

```json
{
  "id": "elem_001",
  "type": "header_1",  // title, header_1-6, text, table, image, formula, list_item, caption, etc.
  "content": "Содержимое элемента",
  "order": 0,  // Порядковый номер (0-based)
  "parent_id": null,  // ID родителя (null для корневых)
  "page_number": 1,  // Номер страницы (1-based)
  "bbox": [100, 50, 500, 80],  // [x0, y0, x1, y1]
  "metadata": {
    // Дополнительные метаданные в зависимости от типа
  }
}
```

### Таблица (ВАЖНО: только HTML)

```json
{
  "id": "elem_015",
  "type": "table",
  "content": "<table><thead><tr><th>Колонка 1</th></tr></thead><tbody><tr><td>Значение</td></tr></tbody></table>",
  "order": 14,
  "parent_id": "elem_010",
  "metadata": {
    "table_structure": {
      "html": "<table>...</table>",  // HTML таблицы
      "cells": [
        {
          "row": 0,
          "col": 0,
          "content": "Колонка 1",
          "rowspan": 1,
          "colspan": 1
        }
      ]
    }
  }
}
```

**Ключевые моменты**:
- ✅ Таблицы хранятся **только в HTML** (в поле `content` и `metadata.table_structure.html`)
- ✅ Массив `cells` содержит все ячейки с координатами (row, col)
- ❌ Нет DataFrame - только HTML

### Изображение (ВАЖНО: только base64)

```json
{
  "id": "elem_025",
  "type": "image",
  "content": "",  // Пустая строка для изображений
  "order": 24,
  "metadata": {
    "image_data": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
    "image_format": "png",
    "image_width": 250,
    "image_height": 150
  }
}
```

**Ключевые моменты**:
- ✅ Изображения хранятся **только в base64** (в `metadata.image_data`)
- ✅ Формат: `data:image/{format};base64,{base64_string}`
- ❌ Нет локальных файлов - только base64

## Процесс разметки

1. **Выбор документов**: 5-10 документов разных типов
2. **Разметка элементов**: Все элементы с типами, содержимым, порядком, иерархией
3. **Разметка таблиц**: HTML структура + массив ячеек с координатами
4. **Разметка изображений**: Base64 кодирование изображений
5. **Проверка**: Валидация порядка, иерархии, полноты
6. **Сохранение**: JSON файл согласно схеме

## Инструменты

- **GUI (Streamlit)**: `streamlit run gui_annotation_tool.py` - рекомендуется
- **Консольный**: `python manual_annotation_tool.py`
- **Валидация**: `python verify_annotation.py annotations/doc1_annotation.json`

## Использование

```bash
# Оценка парсера
python run_evaluation.py \
    --parser documentor \
    --input test_files/doc1.pdf \
    --annotation annotations/doc1_annotation.json \
    --output results/documentor/doc1_results.json

# Сравнение парсеров
python compare_parsers.py \
    --annotations annotations/ \
    --results results/ \
    --output reports/comparison_report.md
```

## Документация

- **Полное описание**: `METRICS_TASK_DESCRIPTION.md`
- **Схема разметки**: `annotation_schema.json`
- **Руководство**: `ANNOTATION_GUIDE.md`

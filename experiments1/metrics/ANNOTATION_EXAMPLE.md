# Пример разметки документа

## Визуальное представление документа

```
Страница 1:
┌─────────────────────────────────────────┐
│  [Заголовок документа]                  │
│  Новое исследование в области ML        │
│                                         │
│  [Авторы]                               │
│  Иван Петров, Мария Сидорова           │
│                                         │
│  [Заголовок 1]                          │
│  Введение                              │
│                                         │
│  [Текст]                                │
│  В данной работе мы представляем...     │
│                                         │
│  [Заголовок 2]                          │
│  Методология                            │
│                                         │
│  [Таблица]                              │
│  ┌─────────┬──────────┬────────┐      │
│  │ Метод   │ Точность │ Время  │      │
│  ├─────────┼──────────┼────────┤      │
│  │ Метод A │ 95%      │ 10 сек │      │
│  │ Метод B │ 92%      │ 8 сек  │      │
│  └─────────┴──────────┴────────┘      │
│                                         │
│  [Подпись таблицы]                      │
│  Таблица 1: Сравнение методов          │
└─────────────────────────────────────────┘

Страница 2:
┌─────────────────────────────────────────┐
│  [Изображение]                           │
│  ┌─────────────────────┐                │
│  │                     │                │
│  │   [Схема системы]   │                │
│  │                     │                │
│  └─────────────────────┘                │
│                                         │
│  [Подпись изображения]                  │
│  Рисунок 1: Архитектура системы         │
│                                         │
│  [Текст]                                │
│  На рисунке 1 показана архитектура...  │
└─────────────────────────────────────────┘
```

## Соответствующая разметка

```json
{
  "document_id": "research_paper_example",
  "source_file": "test_files/research_paper.pdf",
  "document_format": "pdf",
  "annotation_version": "2.0",
  "annotator": "Иван Иванов",
  "annotation_date": "2024-01-15T10:30:00Z",
  "elements": [
    {
      "id": "elem_001",
      "type": "title",
      "content": "Новое исследование в области машинного обучения",
      "order": 0,
      "parent_id": null,
      "page_number": 1,
      "bbox": [100, 50, 500, 100]
    },
    {
      "id": "elem_002",
      "type": "text",
      "content": "Иван Петров, Мария Сидорова",
      "order": 1,
      "parent_id": null,
      "page_number": 1,
      "bbox": [100, 110, 500, 130]
    },
    {
      "id": "elem_003",
      "type": "header_1",
      "content": "Введение",
      "order": 2,
      "parent_id": null,
      "page_number": 1,
      "bbox": [100, 150, 500, 180]
    },
    {
      "id": "elem_004",
      "type": "text",
      "content": "В данной работе мы представляем новый подход к обработке документов, который позволяет эффективно извлекать структурированную информацию из различных форматов.",
      "order": 3,
      "parent_id": "elem_003",
      "page_number": 1,
      "bbox": [100, 190, 500, 250]
    },
    {
      "id": "elem_005",
      "type": "header_2",
      "content": "Методология",
      "order": 4,
      "parent_id": "elem_003",
      "page_number": 1,
      "bbox": [100, 260, 500, 290]
    },
    {
      "id": "elem_006",
      "type": "table",
      "content": "<table><thead><tr><th>Метод</th><th>Точность</th><th>Время</th></tr></thead><tbody><tr><td>Метод A</td><td>95%</td><td>10 сек</td></tr><tr><td>Метод B</td><td>92%</td><td>8 сек</td></tr></tbody></table>",
      "order": 5,
      "parent_id": "elem_005",
      "page_number": 1,
      "bbox": [100, 300, 500, 450],
      "metadata": {
        "table_structure": {
          "html": "<table><thead><tr><th>Метод</th><th>Точность</th><th>Время</th></tr></thead><tbody><tr><td>Метод A</td><td>95%</td><td>10 сек</td></tr><tr><td>Метод B</td><td>92%</td><td>8 сек</td></tr></tbody></table>",
          "cells": [
            {"row": 0, "col": 0, "content": "Метод", "rowspan": 1, "colspan": 1},
            {"row": 0, "col": 1, "content": "Точность", "rowspan": 1, "colspan": 1},
            {"row": 0, "col": 2, "content": "Время", "rowspan": 1, "colspan": 1},
            {"row": 1, "col": 0, "content": "Метод A", "rowspan": 1, "colspan": 1},
            {"row": 1, "col": 1, "content": "95%", "rowspan": 1, "colspan": 1},
            {"row": 1, "col": 2, "content": "10 сек", "rowspan": 1, "colspan": 1},
            {"row": 2, "col": 0, "content": "Метод B", "rowspan": 1, "colspan": 1},
            {"row": 2, "col": 1, "content": "92%", "rowspan": 1, "colspan": 1},
            {"row": 2, "col": 2, "content": "8 сек", "rowspan": 1, "colspan": 1}
          ]
        },
        "rows_count": 3,
        "cols_count": 3
      }
    },
    {
      "id": "elem_007",
      "type": "caption",
      "content": "Таблица 1: Сравнение методов",
      "order": 6,
      "parent_id": "elem_006",
      "page_number": 1,
      "bbox": [100, 455, 500, 475]
    },
    {
      "id": "elem_008",
      "type": "image",
      "content": "",
      "order": 7,
      "parent_id": "elem_005",
      "page_number": 2,
      "bbox": [150, 200, 450, 400],
      "metadata": {
        "image_data": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        "image_format": "png",
        "image_width": 300,
        "image_height": 200
      }
    },
    {
      "id": "elem_009",
      "type": "caption",
      "content": "Рисунок 1: Архитектура системы",
      "order": 8,
      "parent_id": "elem_008",
      "page_number": 2,
      "bbox": [150, 405, 450, 425]
    },
    {
      "id": "elem_010",
      "type": "text",
      "content": "На рисунке 1 показана архитектура предложенной системы, которая состоит из трех основных компонентов.",
      "order": 9,
      "parent_id": "elem_005",
      "page_number": 2,
      "bbox": [100, 430, 500, 480]
    }
  ],
  "statistics": {
    "total_elements": 10,
    "total_pages": 2,
    "elements_by_type": {
      "title": 1,
      "text": 3,
      "header_1": 1,
      "header_2": 1,
      "table": 1,
      "image": 1,
      "caption": 2
    },
    "table_count": 1,
    "image_count": 1
  }
}
```

## Иерархия элементов

```
elem_001 (title) [root]
├── elem_002 (text) [root]
└── elem_003 (header_1) [root]
    ├── elem_004 (text)
    └── elem_005 (header_2)
        ├── elem_006 (table)
        │   └── elem_007 (caption)
        ├── elem_008 (image)
        │   └── elem_009 (caption)
        └── elem_010 (text)
```

## Порядок элементов (order)

```
order: 0  → elem_001 (title)
order: 1  → elem_002 (text)
order: 2  → elem_003 (header_1)
order: 3  → elem_004 (text)
order: 4  → elem_005 (header_2)
order: 5  → elem_006 (table)
order: 6  → elem_007 (caption)
order: 7  → elem_008 (image)
order: 8  → elem_009 (caption)
order: 9  → elem_010 (text)
```

## Ключевые моменты

### Таблицы
- ✅ `content` содержит HTML строку
- ✅ `metadata.table_structure.html` содержит тот же HTML
- ✅ `metadata.table_structure.cells` содержит массив ячеек с координатами
- ❌ Нет DataFrame

### Изображения
- ✅ `content` всегда пустая строка
- ✅ `metadata.image_data` содержит base64 с префиксом `data:image/{format};base64,`
- ❌ Нет локальных файлов

### Иерархия
- ✅ Корневые элементы имеют `parent_id: null`
- ✅ Вложенные элементы ссылаются на родителя через `parent_id`
- ✅ Заголовки создают иерархию (header_1 > header_2 > header_3)

### Порядок
- ✅ `order` последовательный (0, 1, 2, 3, ...)
- ✅ Соответствует порядку чтения документа

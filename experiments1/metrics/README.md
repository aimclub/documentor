# Метрики оценки качества парсинга документов

Этот модуль содержит инструменты для оценки качества парсинга документов и сравнения различных парсеров.

## Структура проекта

```
experiments/metrics/
├── README.md                    # Этот файл
├── annotation_schema.json       # Схема разметки документов
├── evaluation_metrics.py        # Реализация метрик оценки
├── annotate_document.py         # Инструмент для разметки документов
├── run_evaluation.py            # Скрипт для запуска оценки
├── compare_parsers.py           # Сравнение разных парсеров
├── generate_report.py           # Генерация отчета
├── annotations/                 # Размеченные документы (ground truth)
│   ├── doc1_annotation.json
│   ├── doc2_annotation.json
│   └── ...
├── results/                     # Результаты оценки
│   ├── documentor/
│   ├── marker/
│   └── dedoc/
└── reports/                     # Финальные отчеты
    └── comparison_report.md
```

## Метрики

### 1. Element Detection (Precision, Recall, F1)
Оценивает, насколько точно парсер находит все элементы документа.

- **Precision**: Доля найденных элементов, которые действительно есть в документе
- **Recall**: Доля реальных элементов, которые были найдены парсером
- **F1 Score**: Гармоническое среднее precision и recall

### 2. Ordering Accuracy
Оценивает правильность порядка элементов в документе.

**Что размечаем**: Поле `order` для каждого элемента (0, 1, 2, ...) в порядке появления в документе.

### 3. Hierarchy Accuracy
Оценивает правильность иерархической структуры (parent_id).

**Что размечаем**: Поле `parent_id` для каждого элемента, указывающее на родительский заголовок или раздел.

### 4. TEDS (Tree-Edit-Distance-based Similarity)
- **Document TEDS**: Оценивает структурное сходство всего документа
- **Table TEDS**: Оценивает структурное сходство таблиц

**Что размечаем**: 
- Для документа: полная структура элементов с иерархией
- Для таблиц: структура ячеек (`metadata.table_structure.cells`) с координатами (row, col)

## Формат разметки

Разметка сохраняется в JSON формате согласно схеме `annotation_schema.json`.

Пример:
```json
{
  "document_id": "doc1",
  "source_file": "test_files/doc1.pdf",
  "document_format": "pdf",
  "elements": [
    {
      "id": "elem_1",
      "type": "header_1",
      "content": "Introduction",
      "parent_id": null,
      "order": 0,
      "page_number": 1
    },
    {
      "id": "elem_2",
      "type": "text",
      "content": "This is the introduction text...",
      "parent_id": "elem_1",
      "order": 1,
      "page_number": 1
    }
  ]
}
```

## Использование

### 1. Разметка документов

**ВАЖНО: Используйте РУЧНУЮ разметку для объективной оценки!**

Автоматическая разметка на основе нашего пайплайна создаст нечестное преимущество. См. `ANNOTATION_GUIDE.md` для подробностей.

#### Графический инструмент (рекомендуется):

```bash
pip install -r requirements_gui.txt
streamlit run gui_annotation_tool.py
```

Веб-интерфейс с возможностями:
- Визуальный просмотр PDF документов
- Удобные формы для добавления элементов
- Фильтрация и поиск элементов
- Статистика в реальном времени
- Сохранение и загрузка разметки

**См. `GUI_ANNOTATION_README.md` для подробностей.**

#### Консольный инструмент:

```bash
python manual_annotation_tool.py --input test_files_for_metrics/doc1.pdf --output annotations/doc1_annotation.json
```

Интерактивный консольный инструмент для разметки.

**См. `QUICK_START.md` для быстрого старта.**

#### Автоматическая разметка (только для справки):

```bash
python annotate_document.py --input test_files_for_metrics/doc1.pdf --output annotations/doc1_annotation.json
```

**Не используйте автоматическую разметку для финальной оценки!**

### 2. Оценка парсера

```bash
python run_evaluation.py \
    --parser documentor \
    --input test_files/doc1.pdf \
    --annotation annotations/doc1_annotation.json \
    --output results/documentor/doc1_results.json
```

### 3. Сравнение парсеров

```bash
python compare_parsers.py \
    --annotations annotations/ \
    --output reports/comparison_report.md
```

## Парсеры для сравнения

1. **Documentor** - наш парсер
2. **Marker** - https://github.com/datalab-to/marker
3. **Dedoc** - https://github.com/ispras/dedoc

## Требования

- Python 3.9+
- pandas (для работы с таблицами)
- documentor (наш парсер)
- marker (для сравнения)
- dedoc (для сравнения)

# Пайплайн оценки качества парсинга документов

## Описание

Пайплайн для оценки качества парсинга документов на основе размеченных данных (ground truth).

## Метрики

Пайплайн вычисляет следующие метрики:

1. **CER (Character Error Rate)** - процент ошибок на уровне символов
2. **WER (Word Error Rate)** - процент ошибок на уровне слов
3. **Время на страницу** - среднее время обработки одной страницы
4. **Время на документ** - общее время обработки документа
5. **TEDS для документа** - Tree-Edit-Distance-based Similarity для структуры документа
6. **TEDS для иерархии** - Tree-Edit-Distance-based Similarity для иерархии элементов (parent-child отношения)
7. **Точность детекции классов** - Precision, Recall, F1 для каждого типа элемента (title, header_1-6, text, table, image, и т.д.)

## Особенности

- **Игнорирование ошибок родителей для HEADER_1**: При вычислении метрик иерархии ошибки в parent_id для элементов типа `header_1` не учитываются (так как логика определения родителя для заголовков первого уровня может варьироваться).

## Использование

### Базовое использование

```bash
cd experiments/metrics
python evaluation_pipeline.py
```

### С указанием директории и выходного файла

```bash
python evaluation_pipeline.py \
    --annotations-dir experiments/metrics/annotations \
    --output experiments/metrics/evaluation_results.json
```

### Параметры

- `--annotations-dir`: Директория с файлами аннотаций (по умолчанию: `experiments/metrics/annotations`)
- `--output`: Путь к файлу для сохранения результатов в JSON (по умолчанию: `experiments/metrics/evaluation_results.json`)

## Формат результатов

Результаты сохраняются в JSON файл со следующей структурой:

```json
{
  "summary": {
    "total_documents": 12,
    "avg_cer": 0.0234,
    "avg_wer": 0.0456,
    "avg_time_per_page": 2.34,
    "avg_time_per_document": 15.67,
    "avg_document_teds": 0.89,
    "avg_hierarchy_teds": 0.87
  },
  "per_document": [
    {
      "document_id": "2508.19267v1",
      "source_file": "...",
      "format": "pdf",
      "cer": 0.02,
      "wer": 0.04,
      "time_per_page": 2.1,
      "time_per_document": 12.5,
      "total_pages": 6,
      "document_teds": 0.91,
      "hierarchy_teds": 0.88,
      "total_elements_gt": 150,
      "total_elements_pred": 148,
      "matched_elements": 145
    },
    ...
  ],
  "class_metrics": {
    "title": {
      "precision": 1.0,
      "recall": 1.0,
      "f1": 1.0,
      "count_gt": 12,
      "count_pred": 12,
      "count_matched": 12
    },
    "header_1": {
      "precision": 0.95,
      "recall": 0.93,
      "f1": 0.94,
      "count_gt": 45,
      "count_pred": 47,
      "count_matched": 42
    },
    ...
  }
}
```

## Требования

- Python 3.8+
- `documentor` - библиотека парсинга документов
- Все зависимости из `requirements.txt`

## Примечания

- Пайплайн обрабатывает все файлы с суффиксом `_annotation.json` в указанной директории
- Для каждого документа выполняется полный парсинг через `Pipeline`
- Метрики вычисляются на основе сопоставления предсказанных элементов с ground truth
- CER и WER вычисляются только для текстовых элементов (text, title, headers, caption, list_item)

# Сравнение распознавания таблиц: Qwen vs Dots OCR

Эксперимент для сравнения качества распознавания таблиц между Qwen и Dots OCR на датасете SciTSR_no_latex.

## Метрики

- **TEDS** (Tree-Edit-Distance-based Similarity) - структурное сходство таблиц
- **CER** (Character Error Rate) - ошибка на уровне символов
- **WER** (Word Error Rate) - ошибка на уровне слов
- **Время** - время обработки одного изображения

## Датасет

Используется датасет `SciTSR_no_latex` из папки `dots.ocr/table_parsing/SciTSR_no_latex`:
- Изображения таблиц: `img/*.png`
- Ground truth: `structure/*.json`

## Запуск

```bash
python experiments/table_recognition_comparison/compare_table_recognition.py
```

Для тестирования на ограниченном количестве изображений можно раскомментировать строку:
```python
process_dataset(dataset_path, output_path, limit=10)
```

## Результаты

Результаты сохраняются в `experiments/table_recognition_comparison/results/`:
- `results.json` - детальные результаты по каждому изображению
- `summary.json` - сводная статистика по всем метрикам

## Структура результатов

### results.json
Для каждого изображения:
```json
{
  "image": "0001020v1.12",
  "qwen": {
    "time_seconds": 2.5,
    "metrics": {
      "cer": 0.05,
      "wer": 0.10,
      "teds": 0.95
    },
    "success": true
  },
  "dots_ocr": {
    "time_seconds": 1.2,
    "metrics": {
      "cer": 0.03,
      "wer": 0.08,
      "teds": 0.97
    },
    "success": true
  }
}
```

### summary.json
Средние значения по всем изображениям:
```json
{
  "total_images": 770,
  "qwen": {
    "avg_time": 2.5,
    "avg_cer": 0.05,
    "avg_wer": 0.10,
    "avg_teds": 0.95,
    "success_rate": 0.98
  },
  "dots_ocr": {
    "avg_time": 1.2,
    "avg_cer": 0.03,
    "avg_wer": 0.08,
    "avg_teds": 0.97,
    "success_rate": 0.99
  }
}
```

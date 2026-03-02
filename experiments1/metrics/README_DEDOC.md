# Оценка метрик для Dedoc

Этот скрипт оценивает качество парсинга документов через библиотеку [dedoc](https://github.com/ispras/dedoc) по ground truth аннотациям.

**Быстрый старт:** См. [QUICKSTART_DEDOC.md](QUICKSTART_DEDOC.md)

## Установка

### 1. Создание виртуального окружения (уже создано)

Виртуальное окружение `venv_dedoc` уже создано в директории `experiments/metrics/`.

### 2. Активация виртуального окружения

**Windows:**
```bash
cd experiments/metrics
venv_dedoc\Scripts\activate
```

**Linux/Mac:**
```bash
cd experiments/metrics
source venv_dedoc/bin/activate
```

### 3. Установка зависимостей

**Если используете Docker (рекомендуется):**
```bash
# Только requests для работы с Docker API
pip install requests
```

**Если используете локальную установку:**
```bash
pip install dedoc
```

**Примечание:** Установка dedoc может занять много времени из-за компиляции зависимостей (scikit-image и др.). 

**Важно:** На Windows установка может завершиться ошибкой из-за проблем с компиляцией scikit-image. В этом случае рекомендуется использовать Docker.

### Альтернатива: через Docker (рекомендуется для Windows)

```bash
# Скачать образ
docker pull dedocproject/dedoc

# Запустить контейнер
docker run -d -p 1231:1231 --name dedoc dedocproject/dedoc

# Проверить, что контейнер работает
docker ps | grep dedoc
```

Скрипт автоматически определит, доступен ли Docker API, и будет использовать его вместо локальной установки.

## Использование

### Запуск оценки

**Вариант 1: С активированным venv**
```bash
# Активируйте venv (см. выше)
python evaluate_dedoc.py
```

**Вариант 2: Прямой запуск через venv**
```bash
# Windows
venv_dedoc\Scripts\python.exe evaluate_dedoc.py

# Linux/Mac
venv_dedoc/bin/python evaluate_dedoc.py
```

**Вариант 3: С Docker (не требует venv)**
```bash
# Убедитесь, что Docker контейнер запущен
docker run -d -p 1231:1231 --name dedoc dedocproject/dedoc

# Запустите скрипт (используется системный Python)
python evaluate_dedoc.py
```

**Примечание:** Скрипт автоматически определит, использовать Docker API или локальную установку.

Скрипт автоматически:
1. Найдет все PDF файлы в `test_files_for_metrics/`
2. Найдет соответствующие аннотации в `annotations/`
3. Обработает каждый файл через dedoc
4. Вычислит метрики (CER, WER, TEDS, Ordering accuracy, Hierarchy accuracy)
5. Сохранит результаты в `dedoc_metrics.json`

## Структура результатов

Результаты сохраняются в JSON формате:

```json
{
  "document_name.pdf": {
    "document_id": "document_name",
    "cer": 0.0234,
    "wer": 0.0456,
    "ordering_accuracy": 0.9876,
    "hierarchy_accuracy": 0.8765,
    "document_teds": 0.5432,
    "hierarchy_teds": 0.1234,
    "total_elements_gt": 100,
    "total_elements_pred": 95,
    "matched_elements": 90,
    "processing_time": 12.34
  },
  "_summary": {
    "total_files": 8,
    "avg_cer": 0.0234,
    "avg_wer": 0.0456,
    ...
  }
}
```

## Метрики

- **CER (Character Error Rate)**: Процент ошибок на уровне символов
- **WER (Word Error Rate)**: Процент ошибок на уровне слов
- **Ordering Accuracy**: Точность порядка элементов
- **Hierarchy Accuracy**: Точность иерархии элементов (parent-child relationships)
- **Document TEDS**: Общая метрика структуры документа
- **Hierarchy TEDS**: Метрика иерархической структуры

## Примечания

- Dedoc может работать как библиотека или через REST API
- Для работы со сканированными документами требуется Tesseract OCR
- Скрипт автоматически определяет формат вывода dedoc и преобразует его в стандартный формат элементов

## Troubleshooting

### Ошибка импорта dedoc

Если возникает ошибка `ImportError: No module named 'dedoc'`:

1. **Вариант 1 (рекомендуется):** Используйте Docker:
   ```bash
   docker run -d -p 1231:1231 --name dedoc dedocproject/dedoc
   ```
   Скрипт автоматически обнаружит Docker API и будет использовать его.

2. **Вариант 2:** Установите локально: `pip install dedoc`
   - На Windows может потребоваться Visual Studio Build Tools для компиляции зависимостей
   - Проверьте, что вы используете правильное виртуальное окружение

### Ошибка парсинга документа

Если dedoc не может распарсить документ:

1. Проверьте формат файла (dedoc поддерживает PDF, DOCX, HTML, TXT)
2. Для сканированных PDF убедитесь, что установлен Tesseract OCR
3. Проверьте логи dedoc для деталей ошибки

### Несоответствие структуры вывода

Если структура вывода dedoc изменилась, обновите функцию `parse_dedoc_structure()` в скрипте.

# Workflow для оценки метрик

## Шаг 1: Разметка документов

Разметить 5 PDF файлов с выделяемым текстом.

```bash
# Для каждого PDF файла
python annotate_document.py \
    --input test_files_for_metrics/doc1.pdf \
    --output annotations/doc1_annotation.json \
    --annotator "Your Name"
```

**Важно**: После автоматической разметки нужно **вручную проверить и исправить** разметку:
- Проверить правильность типов элементов
- Проверить порядок элементов (order)
- Проверить иерархию (parent_id)
- Для таблиц проверить структуру (cells)

## Шаг 2: Конвертация документов

Для каждого размеченного PDF создать:
1. DOCX версию
2. PDF scanned версию

**DOCX**: Можно использовать LibreOffice или docx2pdf в обратную сторону.

**PDF scanned**: Можно использовать:
- ImageMagick для конвертации PDF в изображения и обратно
- Или специальные инструменты для создания scanned PDF

## Шаг 3: Оценка нашего парсера

```bash
# Оценка одного документа
python run_evaluation.py \
    --parser documentor \
    --input test_files_for_metrics/doc1.pdf \
    --annotation annotations/doc1_annotation.json \
    --output results/documentor/

# Пакетная оценка всех документов
python batch_evaluate.py \
    --annotations annotations/ \
    --source test_files_for_metrics/ \
    --results results/ \
    --parsers documentor
```

## Шаг 4: Интеграция Marker и Dedoc

### Marker

1. Установить Marker:
```bash
pip install marker-pdf
```

2. Интегрировать в `run_evaluation.py`:
```python
def parse_with_marker(source_file: Path) -> ParsedDocument:
    from marker import Marker
    
    marker = Marker()
    result = marker.extract(str(source_file))
    
    # Конвертировать результат Marker в ParsedDocument
    # ...
```

### Dedoc

1. Установить Dedoc:
```bash
pip install dedoc
```

2. Или использовать через Docker:
```bash
docker pull dedocproject/dedoc
docker run -p 1231:1231 dedocproject/dedoc
```

3. Интегрировать в `run_evaluation.py`:
```python
def parse_with_dedoc(source_file: Path) -> ParsedDocument:
    import requests
    
    # Отправка запроса к Dedoc API
    with open(source_file, 'rb') as f:
        files = {'file': f}
        response = requests.post('http://localhost:1231/api/v1/parse', files=files)
    
    # Конвертировать результат Dedoc в ParsedDocument
    # ...
```

## Шаг 5: Оценка всех парсеров

```bash
# Оценка всех парсеров для всех документов
python batch_evaluate.py \
    --annotations annotations/ \
    --source test_files_for_metrics/ \
    --results results/ \
    --parsers documentor marker dedoc
```

## Шаг 6: Сравнение и отчет

```bash
# Генерация отчета сравнения
python compare_parsers.py \
    --results results/ \
    --output reports/comparison_report.md
```

## Шаг 7: Финальный отчет

Создать детальный отчет с:
- Сравнением метрик
- Затраченными ресурсами (время, память)
- Анализом ошибок
- Выводами и рекомендациями

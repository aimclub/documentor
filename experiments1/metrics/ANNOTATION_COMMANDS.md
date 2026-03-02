# Команды для разметки файлов

## Все файлы (последовательно)

### Windows (Batch):
```bash
annotate_all_files.bat
```

### Linux/Mac (Bash):
```bash
bash annotate_all_files.sh
```

## Отдельные файлы

### 1. 2412.19495v2.pdf
```bash
python manual_annotation_tool.py --input test_files_for_metrics/2412.19495v2.pdf --output annotations/2412.19495v2_annotation.json
```

### 2. 2506.10204v1.pdf
```bash
python manual_annotation_tool.py --input test_files_for_metrics/2506.10204v1.pdf --output annotations/2506.10204v1_annotation.json
```

### 3. 2508.19267v1.pdf
```bash
python manual_annotation_tool.py --input test_files_for_metrics/2508.19267v1.pdf --output annotations/2508.19267v1_annotation.json
```

### 4. journal-10-67-5-676-697.pdf
```bash
python manual_annotation_tool.py --input test_files_for_metrics/journal-10-67-5-676-697.pdf --output annotations/journal-10-67-5-676-697_annotation.json
```

### 5. journal-10-67-5-721-729.pdf
```bash
python manual_annotation_tool.py --input test_files_for_metrics/journal-10-67-5-721-729.pdf --output annotations/journal-10-67-5-721-729_annotation.json
```

## Использование

1. Откройте терминал в директории `experiments/metrics`
2. Запустите команду для нужного файла
3. В интерактивном режиме используйте:
   - `add` - добавить элемент
   - `list` - показать все элементы
   - `save` - сохранить разметку
   - `quit` - выйти с сохранением

## Примечания

- Каждый файл размечается отдельно
- Разметка сохраняется в `annotations/`
- После разметки проверьте JSON файлы вручную
- Для таблиц может потребоваться дополнительная ручная правка структуры ячеек

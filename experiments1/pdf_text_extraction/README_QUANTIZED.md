# DOTS OCR с 4-bit Quantization

Эксперимент с использованием DOTS OCR модели с 4-bit quantization для уменьшения использования памяти GPU.

## Установка зависимостей

```bash
# Основные зависимости
pip install transformers torch torchvision

# Для 4-bit quantization
pip install bitsandbytes

# Для работы с PDF
pip install pymupdf pillow
```

## Использование

### Базовый пример

```bash
python test_dots_ocr_quantized.py \
    --pdf test_files/2304.05128v2.pdf \
    --page 1
```

### С увеличенным изображением

```bash
python test_dots_ocr_quantized.py \
    --pdf test_files/2304.05128v2.pdf \
    --page 1 \
    --enlarge-image 2048
```

### С ограничением размера изображения

```bash
python test_dots_ocr_quantized.py \
    --pdf test_files/2304.05128v2.pdf \
    --page 1 \
    --max-image-size 1024
```

### Без quantization (для сравнения)

```bash
python test_dots_ocr_quantized.py \
    --pdf test_files/2304.05128v2.pdf \
    --page 1 \
    --no-quantization
```

## Параметры

- `--pdf`: Путь к PDF файлу (обязательно)
- `--page`: Номер страницы (по умолчанию: 1)
- `--output`: Директория для сохранения результатов (по умолчанию: `results/dots_ocr_quantized`)
- `--model`: Имя модели на Hugging Face (по умолчанию: `rednote-hilab/dots.ocr.base`)
- `--device`: Устройство (`cuda` или `cpu`, по умолчанию: автоматический выбор)
- `--no-quantization`: Отключить 4-bit quantization
- `--max-image-size`: Максимальный размер изображения по большей стороне (None = без ограничений)
- `--enlarge-image`: Увеличить изображение до указанного размера по большей стороне
- `--max-tokens`: Максимальное количество токенов для генерации (по умолчанию: 2048)
- `--dpi`: DPI для рендеринга PDF (по умолчанию: 200)

## Особенности

### 4-bit Quantization

- Использует `BitsAndBytesConfig` из transformers
- Тип quantization: NF4 (Normalized Float 4)
- Double quantization включен для лучшего сжатия
- Compute dtype: float16

### Обработка изображений

- Поддержка нормального размера изображений
- Поддержка увеличенных изображений (через `--enlarge-image`)
- Автоматическое уменьшение больших изображений (через `--max-image-size`)
- Использование LANCZOS resampling для качественного масштабирования

### Управление памятью

- Автоматическая очистка памяти после обработки
- `torch.cuda.empty_cache()` для освобождения GPU памяти
- Использование `torch.inference_mode()` для экономии памяти

## Результаты

Скрипт сохраняет:
- JSON файл с результатами layout detection
- Визуализацию с bounding boxes (если найдены элементы)
- Информацию о размерах изображений
- Статус quantization

## Примеры использования памяти

### С quantization (4-bit)
- Модель: ~3-4 GB GPU памяти
- Обработка: ~1-2 GB дополнительно

### Без quantization (full precision)
- Модель: ~12-16 GB GPU памяти
- Обработка: ~2-4 GB дополнительно

## Устранение проблем

### Ошибка: "bitsandbytes not found"
```bash
pip install bitsandbytes
```

### Ошибка: "CUDA out of memory"
- Используйте `--max-image-size 1024` для уменьшения размера изображений
- Используйте `--max-tokens 1024` для уменьшения генерации
- Убедитесь, что quantization включена (по умолчанию)

### Ошибка: "Model not found"
- Проверьте подключение к интернету
- Модель будет загружена автоматически при первом запуске
- Проверьте имя модели: `rednote-hilab/dots.ocr.base`

## Сравнение с обычной версией

| Параметр | С quantization | Без quantization |
|----------|----------------|------------------|
| Память GPU | ~3-4 GB | ~12-16 GB |
| Скорость | Немного медленнее | Быстрее |
| Точность | Практически та же | Максимальная |
| Совместимость | Требует bitsandbytes | Работает везде |

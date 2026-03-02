# Команды для запуска DOTS OCR с Quantization

## Для Windows (cmd.exe)

### Вариант 1: Использование существующего venv_dots_ocr

```cmd
cd E:\easy\documentor\documentor_langchain\experiments\pdf_text_extraction
venv_dots_ocr\Scripts\activate
python test_dots_ocr_quantized.py --pdf test_files\2304.05128v2.pdf --page 1
```

### Вариант 2: Создание нового venv (если venv_dots_ocr не подходит)

```cmd
cd E:\easy\documentor\documentor_langchain\experiments\pdf_text_extraction
python -m venv venv_quantized
venv_quantized\Scripts\activate
pip install transformers bitsandbytes torch torchvision pymupdf pillow
python test_dots_ocr_quantized.py --pdf test_files\2304.05128v2.pdf --page 1
```

## Полная последовательность команд (Windows)

### Шаг 1: Переход в директорию
```cmd
cd E:\easy\documentor\documentor_langchain\experiments\pdf_text_extraction
```

### Шаг 2: Активация виртуального окружения
```cmd
venv_dots_ocr\Scripts\activate
```

### Шаг 3: Установка зависимостей (если нужно)
```cmd
pip install transformers bitsandbytes torch torchvision pymupdf pillow
```

### Шаг 4: Запуск скрипта

#### Базовый запуск:
```cmd
python test_dots_ocr_quantized.py --pdf test_files\2304.05128v2.pdf --page 1
```

#### С увеличенным изображением:
```cmd
python test_dots_ocr_quantized.py --pdf test_files\2304.05128v2.pdf --page 1 --enlarge-image 2048
```

#### С ограничением размера:
```cmd
python test_dots_ocr_quantized.py --pdf test_files\2304.05128v2.pdf --page 1 --max-image-size 1024
```

#### Без quantization (для сравнения):
```cmd
python test_dots_ocr_quantized.py --pdf test_files\2304.05128v2.pdf --page 1 --no-quantization
```

#### С указанием выходной директории:
```cmd
python test_dots_ocr_quantized.py --pdf test_files\2304.05128v2.pdf --page 1 --output results\my_experiment
```

## Для PowerShell

```powershell
cd E:\easy\documentor\documentor_langchain\experiments\pdf_text_extraction
.\venv_dots_ocr\Scripts\Activate.ps1
python test_dots_ocr_quantized.py --pdf test_files\2304.05128v2.pdf --page 1
```

## Для Linux/Mac

```bash
cd /path/to/documentor_langchain/experiments/pdf_text_extraction
source venv_dots_ocr/bin/activate
python test_dots_ocr_quantized.py --pdf test_files/2304.05128v2.pdf --page 1
```

## Все команды одной строкой (Windows cmd)

```cmd
cd E:\easy\documentor\documentor_langchain\experiments\pdf_text_extraction && venv_dots_ocr\Scripts\activate && python test_dots_ocr_quantized.py --pdf test_files\2304.05128v2.pdf --page 1
```

## Все команды одной строкой (PowerShell)

```powershell
cd E:\easy\documentor\documentor_langchain\experiments\pdf_text_extraction; .\venv_dots_ocr\Scripts\Activate.ps1; python test_dots_ocr_quantized.py --pdf test_files\2304.05128v2.pdf --page 1
```

## Проверка установки

Перед запуском можно проверить установленные библиотеки:

```cmd
python -c "import transformers; import bitsandbytes; import torch; print('Все библиотеки установлены!')"
```

## Доступные PDF файлы для тестирования

```cmd
dir test_files\*.pdf
```

## Результаты

Результаты будут сохранены в:
- `results\dots_ocr_quantized\` (по умолчанию)
- Или в указанной директории через `--output`

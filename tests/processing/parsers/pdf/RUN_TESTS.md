# Команды для запуска тестов PDF парсера

## Запуск всех тестов PDF парсера

```bash
python -m pytest tests/processing/parsers/pdf/ -v
```

## Запуск отдельных файлов тестов

### Тесты основного PDF парсера
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py -v
```

### Тесты layout detector
```bash
python -m pytest tests/processing/parsers/pdf/ocr/test_layout_detector.py -v
```

### Тесты page renderer
```bash
python -m pytest tests/processing/parsers/pdf/ocr/test_page_renderer.py -v
```

## Запуск отдельных тестовых классов

### PDF Parser - Инициализация
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestPdfParserInitialization -v
```

### PDF Parser - can_parse
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestCanParse -v
```

### PDF Parser - is_text_extractable
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestIsTextExtractable -v
```

### PDF Parser - get_page_count
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestGetPageCount -v
```

### PDF Parser - filter_layout_elements
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestFilterLayoutElements -v
```

### PDF Parser - analyze_header_levels
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestAnalyzeHeaderLevels -v
```

### PDF Parser - build_hierarchy
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestBuildHierarchy -v
```

### PDF Parser - extract_text_by_bboxes
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestExtractTextByBboxes -v
```

### PDF Parser - merge_nearby_text_blocks
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestMergeNearbyTextBlocks -v
```

### PDF Parser - determine_header_level
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestDetermineHeaderLevel -v
```

### PDF Parser - detect_layout_for_all_pages
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestDetectLayoutForAllPages -v
```

### PDF Parser - store_images_in_metadata
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestStoreImagesInMetadata -v
```

### PDF Parser - parse_tables_with_qwen
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestParseTablesWithQwen -v
```

### PDF Parser - parse_full_cycle
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestParseFullCycle -v
```

### PDF Parser - get_config
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestGetConfig -v
```

### PDF Parser - create_elements_from_hierarchy
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestCreateElementsFromHierarchy -v
```

### Layout Detector - Инициализация
```bash
python -m pytest tests/processing/parsers/pdf/ocr/test_layout_detector.py::TestPdfLayoutDetectorInitialization -v
```

### Layout Detector - Direct API
```bash
python -m pytest tests/processing/parsers/pdf/ocr/test_layout_detector.py::TestDetectLayoutDirectAPI -v
```

### Layout Detector - With Manager
```bash
python -m pytest tests/processing/parsers/pdf/ocr/test_layout_detector.py::TestDetectLayoutWithManager -v
```

### Layout Detector - Context Manager
```bash
python -m pytest tests/processing/parsers/pdf/ocr/test_layout_detector.py::TestContextManager -v
```

### Page Renderer - Инициализация
```bash
python -m pytest tests/processing/parsers/pdf/ocr/test_page_renderer.py::TestPdfPageRendererInitialization -v
```

### Page Renderer - render_page
```bash
python -m pytest tests/processing/parsers/pdf/ocr/test_page_renderer.py::TestRenderPage -v
```

### Page Renderer - render_pages
```bash
python -m pytest tests/processing/parsers/pdf/ocr/test_page_renderer.py::TestRenderPages -v
```

### Page Renderer - get_page_count
```bash
python -m pytest tests/processing/parsers/pdf/ocr/test_page_renderer.py::TestGetPageCount -v
```

## Запуск отдельных тестовых методов

### Пример: тест инициализации парсера
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestPdfParserInitialization::test_default_initialization -v
```

### Пример: тест can_parse для PDF
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestCanParse::test_can_parse_pdf -v
```

### Пример: тест фильтрации элементов
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestFilterLayoutElements::test_filter_page_headers -v
```

## Дополнительные опции

### Запуск с выводом print statements
```bash
python -m pytest tests/processing/parsers/pdf/ -v -s
```

### Запуск с остановкой на первой ошибке
```bash
python -m pytest tests/processing/parsers/pdf/ -v -x
```

### Запуск с подробным выводом ошибок
```bash
python -m pytest tests/processing/parsers/pdf/ -v --tb=long
```

### Запуск с покрытием кода
```bash
python -m pytest tests/processing/parsers/pdf/ -v --cov=documentor.processing.parsers.pdf --cov-report=html
```

### Запуск только быстрых тестов (без реальных API вызовов)
```bash
python -m pytest tests/processing/parsers/pdf/ -v -m "not slow"
```

### Запуск с маркером (если добавлены маркеры)
```bash
python -m pytest tests/processing/parsers/pdf/ -v -m "unit"
```

## Пропуск тестов, требующих внешние зависимости

Если тесты требуют PyMuPDF (fitz), но он не установлен, они автоматически пропускаются через `pytest.skip()`.

## Отладка тестов

### Запуск с отладчиком (pdb)
```bash
python -m pytest tests/processing/parsers/pdf/ -v --pdb
```

### Запуск конкретного теста с отладчиком
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestPdfParserInitialization::test_default_initialization -v --pdb
```

# Commands for running PDF parser tests

## Run all PDF parser tests

```bash
python -m pytest tests/processing/parsers/pdf/ -v
```

## Run individual test files

### Main PDF parser tests
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py -v
```

### Layout detector tests
```bash
python -m pytest tests/processing/parsers/pdf/ocr/test_layout_detector.py -v
```

### Page renderer tests
```bash
python -m pytest tests/processing/parsers/pdf/ocr/test_page_renderer.py -v
```

## Run individual test classes

### PDF Parser - Initialization
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

### PDF Parser - parse_tables
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestParseTables -v
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

### Layout Detector - Initialization
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

### Page Renderer - Initialization
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

## Run individual test methods

### Example: parser initialization test
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestPdfParserInitialization::test_default_initialization -v
```

### Example: can_parse test for PDF
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestCanParse::test_can_parse_pdf -v
```

### Example: element filtering test
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestFilterLayoutElements::test_filter_page_headers -v
```

## Additional options

### Run with print statements
```bash
python -m pytest tests/processing/parsers/pdf/ -v -s
```

### Stop on first failure
```bash
python -m pytest tests/processing/parsers/pdf/ -v -x
```

### Run with verbose error output
```bash
python -m pytest tests/processing/parsers/pdf/ -v --tb=long
```

### Run with code coverage
```bash
python -m pytest tests/processing/parsers/pdf/ -v --cov=documentor.processing.parsers.pdf --cov-report=html
```

### Run only fast tests (no real API calls)
```bash
python -m pytest tests/processing/parsers/pdf/ -v -m "not slow"
```

### Run with marker (if markers are added)
```bash
python -m pytest tests/processing/parsers/pdf/ -v -m "unit"
```

## Skipping tests that require external dependencies

If tests require PyMuPDF (fitz) but it is not installed, they are automatically skipped via `pytest.skip()`.

## Debugging tests

### Run with debugger (pdb)
```bash
python -m pytest tests/processing/parsers/pdf/ -v --pdb
```

### Run specific test with debugger
```bash
python -m pytest tests/processing/parsers/pdf/test_pdf_parser.py::TestPdfParserInitialization::test_default_initialization -v --pdb
```

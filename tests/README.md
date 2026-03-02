# Tests

This directory contains tests for the `documentor` package.

## Running Tests

### Run all tests
```bash
pytest tests/
```

### Run tests with verbose output
```bash
pytest tests/ -v
```

### Run specific test file
```bash
# Core module tests
pytest tests/core/test_load_env.py -v

# Exceptions tests
pytest tests/test_exceptions.py -v

# Pipeline tests
pytest tests/test_pipeline.py -v

# Utils tests
pytest tests/utils/test_ocr_image_utils.py -v
pytest tests/utils/test_ocr_layout_utils.py -v
pytest tests/utils/test_ocr_output_cleaner.py -v
pytest tests/utils/test_ocr_consts.py -v
```

### Run tests with coverage
```bash
pytest tests/ --cov=documentor --cov-report=html
```

### Run tests and show print statements
```bash
pytest tests/ -v -s
```

### Run tests matching a pattern
```bash
pytest tests/ -k "test_load_env" -v
```

## Test Structure

- `core/` - Tests for core utilities (load_env)
- `config/` - Tests for configuration loading
- `domain/` - Tests for domain models
- `processing/` - Tests for processing modules (parsers, loader, hierarchy)
- `utils/` - Tests for utility functions (used by ocr/processing)
- `ocr/` - Tests for OCR modules
- `llm/` - Tests for LLM modules
- `integration/` - Integration tests (pipeline, docx, markdown)
- Root: `test_exceptions.py`, `test_pipeline.py` - exceptions and pipeline tests
- `files_for_tests/` - Test data files
- `fixtures/` - Fixture files (e.g. sample markdown)

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
- `domain/` - Tests for domain models
- `exceptions/` - Tests for exceptions (in root tests/)
- `processing/` - Tests for processing modules
- `utils/` - Tests for utility functions
- `ocr/` - Tests for OCR modules
- `llm/` - Tests for LLM modules
- `integration/` - Integration tests

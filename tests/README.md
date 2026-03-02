# Tests

Tests for the `documentor` package. Pytest is used; configuration is in `pyproject.toml` (`[tool.pytest.ini_options]`).

## Running tests

**All tests:**
```bash
pytest tests/
pytest tests/ -v
```

**With coverage:**
```bash
pytest tests/ --cov=documentor --cov-report=html
```

**By directory (examples):**
```bash
pytest tests/config/ -v
pytest tests/domain/ -v
pytest tests/processing/ -v
pytest tests/ocr/ -v
pytest tests/integration/ -v
```

**Root-level test modules:**
```bash
pytest tests/core/test_load_env.py -v
pytest tests/test_exceptions.py -v
pytest tests/test_pipeline.py -v
```

**Integration metadata tests (images, tables as HTML, links):**  
On Windows the shell does not expand globs; pass files explicitly:
```bash
pytest tests/integration/test_integration_images_base64.py tests/integration/test_integration_tables_html.py tests/integration/test_integration_links_metadata.py tests/integration/test_integration_metadata_combined.py -v
```

**By keyword:**
```bash
pytest tests/ -k "test_load_env" -v
```

**Show print output:**
```bash
pytest tests/ -v -s
```

## Structure

| Directory | Contents |
|-----------|----------|
| `config/` | ConfigLoader, OCR config, LLM config |
| `core/` | Core utilities (e.g. load_env) |
| `domain/` | Domain models (DocumentFormat, ElementType, Element, ParsedDocument, ElementIdGenerator) |
| `processing/` | Loader, text_utils, file_utils; `parsers/` (base, md, docx, pdf incl. ocr); `hierarchy/` |
| `ocr/` | OCR base, Dots OCR, reading order; OCR utils (ocr_image_utils, ocr_consts, ocr_output_cleaner, ocr_layout_utils, image_utils) |
| `integration/` | Pipeline, Markdown, DOCX; metadata tests (images base64, tables HTML, links) |
| `data/` | Test assets (PDF, DOCX, MD, images) |

Root-level test files: `test_exceptions.py`, `test_pipeline.py`.

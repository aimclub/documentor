# Configuration Examples

This directory contains example configuration files for Documentor.

## Files

- **config.yaml**: Main configuration file for PDF and DOCX parsers
- **ocr_config.yaml**: OCR service configuration (Dots.OCR)
- **llm_config.yaml**: LLM service configuration (for future use)

**See also**: `../env.example` for environment variables configuration (API keys, secrets).

## Usage

### Option 1: Using External Config File

Copy the example config files to your project and customize them:

```python
from documentor.processing.parsers.pdf import PdfParser

# Use custom config file
parser = PdfParser(config_path="/path/to/your/config.yaml")
```

### Option 2: Using Config Dictionary

Pass configuration directly as a dictionary:

```python
from documentor.processing.parsers.pdf import PdfParser

# Use custom config dictionary
parser = PdfParser(config_dict={
    "pdf_parser": {
        "layout_detection": {
            "render_scale": 3.0
        },
        "processing": {
            "skip_title_page": True
        }
    }
})
```

### Option 3: Using Default Config

If you don't specify `config_path` or `config_dict`, parsers will use the default internal configuration:

```python
from documentor.processing.parsers.pdf import PdfParser

# Uses default internal config
parser = PdfParser()
```

## Priority

When both `config_path` and `config_dict` are provided, `config_dict` takes priority.

## Configuration Sections

### PDF Parser (`pdf_parser`)

- `layout_detection`: OCR rendering and layout detection settings
- `processing`: Document processing options
- `filtering`: Element filtering (headers, footers)
- `table_parsing`: Table detection and parsing
- `header_analysis`: Header level determination

### DOCX Parser (`docx_parser`)

- `layout_detection`: OCR rendering settings
- `processing`: Document processing options
- `scanned_detection`: Scanned document detection thresholds
- `hierarchy`: Text block merging settings

## Environment Variables

For sensitive configuration (API keys, secrets), use environment variables in a `.env` file.

1. Copy the example: `cp examples/env.example .env`
2. Edit `.env` and fill in your actual values
3. Never commit `.env` to version control

See `../env.example` for all available environment variables.

## Configuration Priority

1. **Environment variables** (`.env` file) - for secrets and sensitive data
2. **Config files** (`config.yaml`, `ocr_config.yaml`) - for non-secret settings
3. **Default values** - fallback

## Notes

- Configuration files are YAML format
- All settings are optional - missing values will use defaults
- You can override only specific sections - other sections will use defaults
- Internal config files are kept for backward compatibility but should not be modified
- Use `.env` file for API keys and secrets, config files for other settings

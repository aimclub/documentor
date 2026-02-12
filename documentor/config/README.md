# Configuration Files

Configuration files for Documentor parsers and services.

## Files

- **config.yaml**: General configuration
- **pdf_config.yaml**: PDF parser settings
  - Layout detection parameters
  - Filtering options
  - Table parsing configuration
  - Header analysis settings
- **docx_config.yaml**: DOCX parser settings
  - Layout detection scale
  - Scanned document detection thresholds
  - Hierarchy building parameters
- **llm_config.yaml**: LLM service configuration
  - Qwen API settings
  - Model selection
  - Request parameters
- **ocr_config.yaml**: OCR service configuration
  - Dots.OCR API settings
  - Image processing parameters
- **prompts.yaml**: Prompt templates for LLM interactions

## Configuration Format

All configuration files use YAML format. Settings can be overridden via environment variables.

## Example

```yaml
pdf_parser:
  layout_detection:
    render_scale: 2.0
    optimize_for_ocr: true
  filtering:
    remove_page_headers: true
```

# Configuration Files

Configuration files for Documentor parsers and services.

All configuration files use YAML format. Settings can be overridden via environment variables.

## Files

### **config.yaml**
Main configuration file containing general settings and parser configurations.

**Structure:**
- `general`: General settings
  - `output_len`: Default output length for text chunks (characters)
- `pdf_parser`: PDF parser settings
  - `layout_detection`: Layout detection parameters
    - `render_scale`: Scale increase for rendering
    - `optimize_for_ocr`: Optimize images for OCR
    - `use_direct_api`: Use direct API call instead of queue
  - `processing`: Document processing options
    - `skip_title_page`: Skip first page if title page exists (default: false)
  - `filtering`: Element filtering options
    - `remove_page_headers`: Remove page headers from content
    - `remove_page_footers`: Remove page footers from content
  - `table_parsing`: Table parsing configuration
    - `method`: Method ("markdown" or "dataframe")
    - `detect_merged_tables`: Detect merged tables across pages
  - `header_analysis`: Header analysis settings
    - `use_font_size`: Use font size to determine header level
    - `use_position`: Use position to determine header level
    - `min_font_size_diff`: Minimum font size difference for different levels
- `docx_parser`: DOCX parser settings
  - `layout_detection`: Layout detection parameters
    - `render_scale`: Scale increase for OCR rendering
  - `processing`: Document processing options
    - `skip_title_page`: Skip first page if title page exists (default: false)
  - `scanned_detection`: Scanned document detection thresholds
    - `min_text_length`: Minimum text length to determine text presence
    - `min_text_for_non_scanned`: Minimum text length for non-scanned document
    - `images_to_text_ratio`: Ratio for determining if document is scanned
  - `hierarchy`: Hierarchy building parameters
    - `max_text_block_size`: Maximum text block size in characters
    - `max_paragraphs_per_block`: Maximum number of paragraphs in one block

### **ocr_config.yaml**
OCR (Optical Character Recognition) service configuration.

**Structure:**
- `dots_ocr`: Dots.OCR settings
  - `endpoint`: URL or path to Dots.OCR service (if null - uses local service)
  - `model`: Model name (default: "/model")
  - `recognition`: Recognition parameters
    - `temperature`: Generation temperature (0.0 - 1.0, default: 0.1)
    - `max_tokens`: Maximum number of tokens (default: 32768)
    - `timeout`: Request timeout in seconds (default: 30)
  - `prompts`: Prompts for Dots.OCR
  - `prompt_mode`: Prompt mode to use
  - `layout`: Layout detection parameters
    - `confidence_threshold`: Detection confidence threshold (0.0 - 1.0, default: 0.5)
  - `reading_order`: Reading order building settings
- `qwen_ocr`: Qwen OCR settings
  - `model`: Model for OCR (default: "qwen2-vl-7b-instruct")
  - `base_url`: API URL (if null - uses local model)
  - `recognition`: Recognition parameters
    - `languages`: Recognition languages (ISO 639-1 codes)
    - `resolution`: Image resolution for OCR (DPI)
    - `temperature`: Generation temperature (0.0 - 1.0, default: 0.1)
    - `max_tokens`: Maximum number of tokens (default: 4096)
    - `timeout`: Timeout per image in seconds (default: 30)
  - `batch`: Batch processing settings
- `image_processing`: Image processing settings
  - `format`: Image format for OCR
  - `quality`: Image quality for JPEG
  - `dpi`: DPI for page rendering
  - `preprocessing`: Image preprocessing options
- `coordinates`: Coordinate (bbox) settings
  - `precision`: Coordinate precision (decimal places)
  - `normalize`: Coordinate normalization
  - `units`: Units of measurement
- `type_mapping`: Layout Type → ElementType mapping
  - `layout_to_element`: Mapping dictionary
  - `header_level`: Rules for determining header level
- `performance`: Performance settings
  - `parallel_processing`: Enable parallel page processing
  - `num_workers`: Number of threads for parallel processing
  - `cache_layout`: Cache layout detection results
  - `cache_ocr`: Cache OCR results

### **llm_config.yaml**
LLM (Large Language Models) service configuration.

**Structure:**
- `providers`: LLM provider settings
  - `qwen`: Qwen provider settings
    - `text`: Text analysis model settings
    - `visual`: Visual analysis (OCR) model settings
  - `openai`: OpenAI provider settings (optional)
- `chunking`: Text chunking settings
  - `chunk_size`: Chunk size for LLM analysis (characters)
  - `overlap`: Overlap between chunks (paragraphs)
  - `min_chunk_size`: Minimum chunk size
- `prompts`: Prompts for various tasks
  - `header_detection`: Prompt for header detection
  - `structure_classification`: Prompt for element classification
  - `visual_structure_analysis`: Prompt for visual structure analysis
- `headers`: Header processing settings
  - `max_level`: Maximum header level (1-6)
  - `min_level`: Minimum header level (1-6)
  - `validate_hierarchy`: Enable hierarchy validation
- `response_processing`: LLM response processing settings
  - `parse_json`: Parse JSON response
  - `handle_parse_errors`: Handle parse errors gracefully
  - `retry_on_error`: Retry on errors
  - `max_retries`: Maximum number of retries

## Usage

Configuration files are automatically loaded by parsers:

```python
from documentor import Pipeline
from langchain_core.documents import Document

# Configuration is automatically loaded from config files
pipeline = Pipeline()
doc = Document(page_content="", metadata={"source": "document.pdf"})
parsed = pipeline.parse(doc)
```

## Configuration Priority

For non-secret parameters (timeouts, temperatures, model names, etc.), the priority is:
1. **Configuration file** (`ocr_config.yaml`, `config.yaml`, `llm_config.yaml`)
2. **Environment variables** (if config value is not found)
3. **Default values** (hardcoded in code)

For secret parameters (API keys, base URLs), only environment variables are used.

Example for Qwen OCR timeout:
- If `qwen_ocr.recognition.timeout` is set in `ocr_config.yaml` → uses that value
- If not set in config but `QWEN_TIMEOUT` env var exists → uses env var
- Otherwise → uses default value (180 seconds)

## Configuration Format

All configuration files use YAML format. Example:

```yaml
pdf_parser:
  layout_detection:
    render_scale: 2.0
    optimize_for_ocr: true
  filtering:
    remove_page_headers: true
```

## Overriding Configuration

Settings can be overridden via environment variables. Check individual parser documentation for specific environment variable names.

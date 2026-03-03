# Configuration Files

**Note**: These are internal default configuration files. They are kept for backward compatibility and should not be modified.

**For production use**: Copy example config files from `examples/config/` to your project and pass the path when initializing parsers:

```python
from documentor.processing.parsers.pdf import PdfParser

# Use external config file
parser = PdfParser(config_path="/path/to/your/config.yaml")
```

See `examples/config/README.md` for detailed instructions on using external configuration files.

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
OCR (Optical Character Recognition) service configuration. This file contains settings for the default Dots.OCR implementation. If you use custom OCR components, you may not need all of these settings.

**Structure:**
- `dots_ocr`: Dots.OCR settings (default OCR implementation)
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

**Note**: If you use custom OCR components (see [CUSTOM_COMPONENTS_GUIDE.md](../CUSTOM_COMPONENTS_GUIDE.md)), you can configure them separately and pass them to the parser constructor.
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
  - `openai`: OpenAI provider settings (optional)
    - `text`: Text analysis model settings
    - `visual`: Visual analysis (OCR) model settings
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

## Docker Deployment

If you're using Dots OCR, you can deploy it using Docker Compose. See the [project README](../../README.md#docker-deployment-dots-ocr) for a complete example configuration.

**Key Configuration Points:**
- Set `ocr_config.yaml` → `dots_ocr` → `endpoint` to your Docker service URL (e.g., `http://localhost:8000`)
- Use environment variables for API keys and sensitive configuration
- Adjust GPU and memory settings based on your hardware

## Configuration Priority

For non-secret parameters (timeouts, temperatures, model names, etc.), the priority is:
1. **Configuration file** (`ocr_config.yaml`, `config.yaml`, `llm_config.yaml`)
2. **Environment variables** (if config value is not found)
3. **Default values** (hardcoded in code)

For secret parameters (API keys, base URLs), only environment variables are used.


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

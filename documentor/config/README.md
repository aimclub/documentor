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
    - `qwen_model`: Model for table parsing
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
  - `endpoint`: URL or path to Dots.OCR service
  - `timeout`: Request timeout in seconds
  - `prompts`: Prompts for Dots.OCR
  - `prompt_mode`: Prompt mode to use
  - `layout`: Layout detection parameters
  - `reading_order`: Reading order building settings
- `qwen_ocr`: Qwen OCR settings
  - `model`: Model for OCR
  - `base_url`: API URL
  - `recognition`: Recognition parameters
  - `batch`: Batch processing settings
- `image_processing`: Image processing settings
  - `format`: Image format for OCR
  - `quality`: Image quality for JPEG
  - `dpi`: DPI for page rendering
  - `max_size`: Maximum image size in pixels
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

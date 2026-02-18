# Documentor

A powerful document parsing library that extracts structured content from PDF, DOCX, and Markdown files. Documentor uses a layout-based approach with OCR capabilities to parse documents into a unified hierarchical structure.

## Features

- **Multi-format Support**: Parse PDF, DOCX, and Markdown documents
- **Layout-based Parsing**: Uses OCR for intelligent layout detection (default: Dots.OCR)
- **Custom OCR Components**: Replace any OCR component with your own implementation
- **Smart OCR Integration**: 
  - Different prompts for different PDF types (scanned vs text-extractable)
  - Text extraction from OCR for scanned PDFs (default: Dots OCR)
  - PyMuPDF extraction for text-extractable PDFs
- **Structured Output**: Unified hierarchical structure across all formats
- **Table Extraction**: 
  - PDF: Parsing from OCR HTML (default: Dots OCR)
  - DOCX: Conversion from XML to Pandas DataFrames
  - Markdown: Automatic conversion to DataFrames
- **Formula Extraction**: Extracts formulas in LaTeX format (default: Dots OCR)
- **Image Handling**: Extracts and links images with captions
- **Advanced Header Detection**:
  - DOCX: OCR + XML + TOC validation + rules-based missing header detection
  - PDF: Layout-based with level analysis
  - Markdown: Regex-based parsing
- **Caption Finding**: Automatic caption detection for tables and images (DOCX)
- **Table Structure Matching**: Validates tables by comparing OCR and XML structures (DOCX)
- **LangChain Integration**: Compatible with LangChain Document format
- **Modular Architecture**: Easy to extend and customize

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

### Basic Usage
```python
from langchain_core.documents import Document
from documentor import Pipeline

# Initialize pipeline
pipeline = Pipeline()

# Create a document
doc = Document(
    page_content="",
    metadata={"source": "path/to/document.pdf"}
)

# Parse the document
parsed_doc = pipeline.parse(doc)

# Access elements
for element in parsed_doc.elements:
    print(f"{element.type}: {element.content[:100]}")
```

### Custom OCR Components
```python
from documentor.processing.parsers.pdf import PdfParser
from documentor.ocr.base import BaseLayoutDetector
from langchain_core.documents import Document

# Define custom layout detector
class MyLayoutDetector(BaseLayoutDetector):
    def detect_layout(self, image, origin_image=None):
        # Your custom OCR implementation
        return [...]

# Use custom component
parser = PdfParser(layout_detector=MyLayoutDetector())
doc = Document(page_content="", metadata={"source": "document.pdf"})
parsed = parser.parse(doc)
```

See [CUSTOM_COMPONENTS_GUIDE.md](documentor/CUSTOM_COMPONENTS_GUIDE.md) for detailed instructions.

## Architecture

### Core Components

- **Pipeline**: Main entry point for document processing
- **Parsers**: Format-specific parsers (PDF, DOCX, Markdown)
- **OCR**: OCR services integration (Dots.OCR)
- **Domain Models**: Unified data structures (Element, ParsedDocument)

### Parser Types

1. **PDF Parser**: 
   - Layout-based parsing with specialized processors
   - Different prompts for scanned vs text-extractable PDFs
   - Table parsing from OCR HTML (default: Dots OCR)
   - Formula extraction in LaTeX format (default: Dots OCR)
   - Specialized processors: layout, text, tables, images, hierarchy
   - **Custom Components**: Replace any OCR component with your own implementation

2. **DOCX Parser**: 
   - Combined approach (OCR + XML + TOC parsing)
   - Rules-based missing header detection
   - Caption finding for tables and images
   - Table structure matching (OCR vs XML)

3. **Markdown Parser**: 
   - Regex-based parsing (no LLM or OCR)
   - Table extraction to DataFrames
   - Nested list support with proper hierarchy

## Project Structure

```
documentor/
├── config/          # Configuration files (YAML)
├── core/            # Core utilities (environment loading)
├── domain/          # Domain models (Element, ParsedDocument)
├── exceptions.py    # Custom exceptions
├── llm/             # LLM integration (header detection, structure validation)
├── ocr/             # OCR services (base classes + Dots.OCR implementation)
│   ├── base.py      # Base classes for OCR components
│   ├── dots_ocr/    # Dots.OCR implementation (default)
│   └── manager.py   # DotsOCRManager
├── pipeline.py      # Main pipeline class
├── processing/      # Document processing modules
│   ├── loader/      # Document loading utilities
│   └── parsers/    # Format-specific parsers
│       ├── docx/   # DOCX parser modules
│       │   ├── docx_parser.py
│       │   ├── layout_detector.py
│       │   ├── header_processor.py
│       │   ├── header_finder.py
│       │   ├── caption_finder.py
│       │   ├── hierarchy_builder.py
│       │   ├── xml_parser.py
│       │   ├── toc_parser.py
│       │   └── converter_wrapper.py
│       ├── md/     # Markdown parser modules
│       │   ├── md_parser.py
│       │   ├── tokenizer.py
│       │   └── hierarchy.py
│       └── pdf/    # PDF parser modules
│           ├── pdf_parser.py
│           ├── layout_processor.py
│           ├── text_extractor.py
│           ├── table_parser.py
│           ├── image_processor.py
│           ├── hierarchy_builder.py
│           └── ocr/  # OCR components
└── utils/          # Utility functions
```

## Configuration

Configuration files are located in `documentor/config/`:

- `config.yaml`: Main configuration file (contains `pdf_parser` and `docx_parser` sections)
- `llm_config.yaml`: LLM service configuration
- `ocr_config.yaml`: OCR service configuration

### Docker Deployment (Dots OCR)

If you're using Dots OCR as the default OCR service, you can deploy it using Docker Compose. Here's an example configuration:

```yaml
version: '3.8'

services:
  dots-ocr:
    image: vllm/vllm-openai:v0.11.0
    container_name: dots-ocr-service
    ports:
      - '8000:8000'  # Adjust port as needed
    ipc: "host"
    environment:
      - NVIDIA_VISIBLE_DEVICES=0,1  # Adjust GPU devices as needed
      - CUDA_DEVICE_ORDER=PCI_BUS_ID
      - CUDA_VISIBLE_DEVICES=0,1
      - PYTORCH_ALLOC_CONF=expandable_segments:False
      - VLLM_LOGGING_LEVEL=INFO  # Use INFO for production
      - VLLM_WORKER_MULTIPROC_METHOD=spawn
    volumes:
      - /path/to/your/model:/model  # Mount your model directory
    restart: unless-stopped
    mem_limit: 36G  # Adjust based on your GPU memory
    runtime: nvidia
    command:
      - --model
      - /model
      - --tensor-parallel-size
      - "2"  # Adjust based on number of GPUs
      - --gpu-memory-utilization
      - "0.184"  # Adjust based on your needs
      - --max-model-len
      - "65536"
      - --api-key
      - ${DOTS_OCR_API_KEY}  # Use environment variable for security
      - --trust-remote-code
```

**Important Security Notes:**
- Store API keys in environment variables (`.env` file) or use Docker secrets
- Never commit API keys or sensitive paths to version control
- Adjust GPU settings (`NVIDIA_VISIBLE_DEVICES`, `CUDA_VISIBLE_DEVICES`) based on your hardware
- Modify memory limits and GPU utilization based on your system resources

**Environment Variables:**
Create a `.env` file in the same directory as `docker-compose.yml`:
```bash
DOTS_OCR_API_KEY=your-secure-api-key-here
```

**Usage:**
```bash
# Start the service
docker-compose up -d

# Check logs
docker-compose logs -f dots-ocr

# Stop the service
docker-compose down
```

## Output Format

All parsers return a unified `ParsedDocument` structure:

```python
ParsedDocument(
    source: str,
    format: DocumentFormat,
    elements: List[Element],
    metadata: Dict[str, Any]
)
```

Each `Element` contains:
- `id`: Unique identifier
- `type`: Element type (HEADER_1-6, TEXT, TABLE, IMAGE, etc.)
- `content`: Element content
- `parent_id`: Parent element ID (for hierarchy)
- `metadata`: Additional metadata (bbox, page_num, dataframe, etc.)

## Documentation

See the [documentation](docs/) folder for detailed information about each module.

## License

[Add your license here]

## Contributing

[Add contributing guidelines here]

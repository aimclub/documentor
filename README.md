<div style="float: right; width: 200px; height: 200px;">
  <img src="images/logo.png" width="200" alt="DocuMentor logo">
</div>

# DocuMentor

[![Acknowledgement ITMO](https://raw.githubusercontent.com/aimclub/open-source-ops/master/badges/ITMO_badge.svg)](https://itmo.ru/)
[![Acknowledgement SAI](https://raw.githubusercontent.com/aimclub/open-source-ops/master/badges/SAI_badge.svg)](https://sai.itmo.ru/)
[![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause)
[![Visitors](https://api.visitorbadge.io/api/combined?path=https%3A%2F%2Fgithub.com%2FIndustrial-AI-Research-Lab%2Fdocumentor&countColor=%23263759&style=plastic&labelStyle=lower)](https://visitorbadge.io/status?path=https%3A%2F%2Fgithub.com%2FIndustrial-AI-Research-Lab%2Fdocumentor)
[![PythonVersion](https://img.shields.io/badge/python_3.10-passing-success)](https://img.shields.io/badge/python_3.10-passing-success)

A powerful document parsing library that extracts structured content from PDF, DOCX, and Markdown files. DocuMentor uses a layout-based approach with OCR capabilities to parse documents into a unified hierarchical structure.

## The purpose of the project

The DocuMentor library is designed to simplify and automate the parsing and semantic analysis of various types of documents, including PDF, DOCX, and Markdown files.

The library performs the following tasks:
1. **Data extraction** - Extract structured content from documents
2. **Document structure analysis** - Hierarchical analysis of document structure
3. **Entity recognition** - Identify and classify document elements (headers, tables, images, formulas)
4. **Format conversion** - Unified output format across all supported document types

## Core features

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

For installation from the source code, you need to have the poetry package manager installed ([poetry](https://github.com/python-poetry/install.python-poetry.org)).
```shell
poetry install
```

Alternatively, you can use pip:
```bash
pip install -r requirements.txt
```

## Prerequisites

Before running DocuMentor, you need to:

### 1. Configure Environment Variables

Create a `.env` file in the project root (use `docs/env.example` or `examples/env.example` as a template) with the following required variables:

**Required OCR variables:**
- `DOTS_OCR_BASE_URL` - Base URL for Dots OCR service
- `DOTS_OCR_API_KEY` - API key for authentication
- `DOTS_OCR_MODEL_NAME` - Model name to use

**Optional variables:**
- `DOTS_OCR_TEMPERATURE`, `DOTS_OCR_MAX_TOKENS`, `DOTS_OCR_TIMEOUT`
- `OCR_MAX_IMAGE_SIZE`, `OCR_MIN_CONFIDENCE`

**Important**: Never commit `.env` to version control. Store API keys securely.

### 2. Deploy Dots OCR via vLLM Server

DocuMentor requires Dots OCR to be deployed as a vLLM server before use. You can deploy it using Docker Compose (see [Docker Deployment](#docker-deployment-dots-ocr) section below) or manually using vLLM.

**Using Docker Compose (Recommended):**
```bash
# Use the provided compose.yml from examples/
cd examples
docker-compose -f compose.yml up -d

# Check logs
docker-compose -f compose.yml logs -f dots-ocr
```

See [examples/compose.yml](examples/compose.yml) for the complete Docker Compose configuration.

**Manual vLLM deployment:**
```bash
# Example vLLM command
python -m vllm.entrypoints.openai.api_server \
    --model /path/to/your/model \
    --tensor-parallel-size 2 \
    --gpu-memory-utilization 0.184 \
    --max-model-len 65536 \
    --api-key ${DOTS_OCR_API_KEY} \
    --trust-remote-code
```

For detailed vLLM integration instructions, see [examples/README_vllm.md](examples/README_vllm.md).

Make sure the `DOTS_OCR_BASE_URL` in your `.env` file points to the running vLLM server.

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

### Configuration

Documentor supports flexible configuration options. You can use:
1. **Default internal config** (used automatically if not specified)
2. **External config file** (recommended for production)
3. **Config dictionary** (useful for programmatic configuration)

#### Using External Config File

Copy example config files from `examples/config/` to your project:

```python
from documentor.processing.parsers.pdf import PdfParser
from langchain_core.documents import Document

# Use custom config file
parser = PdfParser(config_path="/path/to/your/config.yaml")
doc = Document(page_content="", metadata={"source": "document.pdf"})
parsed = parser.parse(doc)
```

#### Using Config Dictionary

```python
from documentor.processing.parsers.pdf import PdfParser
from langchain_core.documents import Document

# Use custom config dictionary
parser = PdfParser(config_dict={
    "pdf_parser": {
        "layout_detection": {
            "render_scale": 3.0  # Higher quality OCR
        },
        "processing": {
            "skip_title_page": True
        }
    }
})
doc = Document(page_content="", metadata={"source": "document.pdf"})
parsed = parser.parse(doc)
```

#### Configuration Priority

When both `config_path` and `config_dict` are provided, `config_dict` takes priority.

See [examples/config/README.md](examples/config/README.md) for detailed configuration options.

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

# Use custom component with custom config
parser = PdfParser(
    layout_detector=MyLayoutDetector(),
    config_path="/path/to/your/config.yaml"
)
doc = Document(page_content="", metadata={"source": "document.pdf"})
parsed = parser.parse(doc)
```

See [CUSTOM_COMPONENTS_GUIDE.md](documentor/CUSTOM_COMPONENTS_GUIDE.md) for detailed instructions.

For a complete example of custom OCR implementation, see [examples/custom_ocr_example.py](examples/custom_ocr_example.py).

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

### Supported formats
- **Input**: `pdf`, `docx`, `md` (Markdown)
- **Output**: Structured `ParsedDocument` with hierarchical elements

**Note**: For DOC files, please convert them to DOCX format first using Microsoft Word, LibreOffice, or online converters before processing.

## Configuration

### Configuration Files

Configuration files are provided as examples in `examples/config/`:
- `config.yaml`: Main configuration file (contains `pdf_parser` and `docx_parser` sections)
- `llm_config.yaml`: LLM service configuration
- `ocr_config.yaml`: OCR service configuration

**Note**: Internal config files in `documentor/config/` are kept for backward compatibility but should not be modified. Copy example configs from `examples/config/` to your project and pass the path when initializing parsers.

### Environment Variables

`.env` is auto-loaded by `documentor/core/load_env.py`. Use `docs/env.example` or `examples/env.example` as a template.

**Required OCR variables:**
- `DOTS_OCR_BASE_URL`, `DOTS_OCR_API_KEY`, `DOTS_OCR_MODEL_NAME`

**Optional:**
- `DOTS_OCR_TEMPERATURE`, `DOTS_OCR_MAX_TOKENS`, `DOTS_OCR_TIMEOUT`
- `OCR_MAX_IMAGE_SIZE`, `OCR_MIN_CONFIDENCE`

**Important**: Never commit `.env` to version control. Store API keys securely.

## Project structure

```
documentor/
├── documentor/                   # Main library package
│   ├── config/                   # Internal default config files (do not modify)
│   ├── core/                     # Core utilities (environment loading)
│   ├── domain/                   # Domain models (Element, ParsedDocument)
│   ├── exceptions.py            # Custom exceptions
│   ├── ocr/                      # OCR services integration
│   │   ├── base.py               # Base classes for OCR components
│   │   ├── dots_ocr/             # Dots.OCR implementation (default)
│   │   └── manager.py            # DotsOCRManager
│   ├── pipeline.py              # Main pipeline class
│   └── processing/               # Document processing modules
│       ├── loader/               # Document loading utilities
│       └── parsers/             # Format-specific parsers
│           ├── docx/            # DOCX parser modules
│           │   ├── docx_parser.py
│           │   ├── layout_detector.py
│           │   ├── header_processor.py
│           │   ├── header_finder.py
│           │   ├── caption_finder.py
│           │   ├── hierarchy_builder.py
│           │   ├── xml_parser.py
│           │   ├── toc_parser.py
│           │   └── converter_wrapper.py
│           ├── md/              # Markdown parser modules
│           │   ├── md_parser.py
│           │   ├── tokenizer.py
│           │   └── hierarchy.py
│           └── pdf/              # PDF parser modules
│               ├── pdf_parser.py
│               ├── layout_processor.py
│               ├── text_extractor.py
│               ├── table_parser.py
│               ├── image_processor.py
│               ├── hierarchy_builder.py
│               └── ocr/          # OCR components
├── docs/                         # Documentation
├── examples/                     # Example configurations and code
├── images/                       # Diagrams and images
└── experiments/                  # Experimental code and metrics
```


### Docker Deployment (Dots OCR)

If you're using Dots OCR as the default OCR service, you can deploy it using Docker Compose. We provide ready-to-use configuration files in the `examples/` directory.

**Quick Start:**
```bash
# Navigate to examples directory
cd examples

# Start the service
docker-compose -f compose.yml up -d

# Check logs
docker-compose -f compose.yml logs -f dots-ocr

# Stop the service
docker-compose -f compose.yml down
```

**Configuration Files:**
- **Docker Compose**: [examples/compose.yml](examples/compose.yml) - Complete Docker Compose configuration for Dots OCR
- **Dockerfile**: [examples/Dockerfile.dotsocr](examples/Dockerfile.dotsocr) - Custom Dockerfile for building Dots OCR image
- **Entrypoint Script**: [examples/entrypoint.sh](examples/entrypoint.sh) - Entrypoint script for Docker container

**Important Security Notes:**
- Store API keys in environment variables (`.env` file) or use Docker secrets
- Never commit API keys or sensitive paths to version control
- Adjust GPU settings (`CUDA_VISIBLE_DEVICES`) based on your hardware
- Modify memory limits and GPU utilization based on your system resources

**Environment Variables:**
Create a `.env` file in the project root using [examples/env.example](examples/env.example) as a template:
```bash
DOTS_OCR_BASE_URL=http://localhost:8069/v1
DOTS_OCR_API_KEY=your-secure-api-key-here
DOTS_OCR_MODEL_NAME=/model
```

For detailed vLLM integration and deployment instructions, see [examples/README_vllm.md](examples/README_vllm.md).

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

- [vLLM integration](examples/README_vllm.md) - Detailed guide for vLLM server setup and integration
- [Environment template](examples/env.example) - Example `.env` file with all required variables
- [Custom Components Guide](documentor/CUSTOM_COMPONENTS_GUIDE.md) - How to create custom OCR components
- [Configuration Guide](examples/config/README.md) - Detailed configuration options
- [Custom OCR Example](examples/custom_ocr_example.py) - Complete example of custom OCR implementation
- [Docker Compose](examples/compose.yml) - Docker Compose configuration for Dots OCR
- [Dockerfile](examples/Dockerfile.dotsocr) - Dockerfile for building Dots OCR container

## License

[BSD 3-Clause License](LICENSE.md)

## Acknowledgements

By ITMO University, Saint Petersburg, Russia

## Contacts

Questions and suggestions can be asked to the maintainers:
- [GitHub Issues](https://github.com/Industrial-AI-Research-Lab/documentor/issues)

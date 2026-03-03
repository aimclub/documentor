# Markdown Parser

Regex-based Markdown parser with table extraction.

## Architecture

The Markdown parser uses regex-based parsing:

1. **Tokenization**: Tokenize Markdown content
2. **Element Extraction**: Extract headers, text, tables, lists, etc.
3. **Hierarchy Building**: Build document hierarchy
4. **Table Conversion**: Convert Markdown tables to HTML format

## Modules

### `md_parser.py`
Main Markdown parser class. Handles complete Markdown parsing: block parsing in `_parse_markdown()`, hierarchy and parent_id in `_build_elements()`.

### `tokenizer.py`
Documents where block parsing lives (md_parser._parse_markdown). No separate tokenizer class; logic is in the parser.

### `hierarchy.py`
Documents hierarchy approach (header_stack, list_stack, parent_id). Implementation is in md_parser._build_elements().

## Features

- **Header Parsing**: Supports headers levels 1-6
- **Table Extraction**: Converts Markdown tables to HTML format (stored in element.content)
- **List Support**: Ordered and unordered lists
- **Link Support**: Extracts links with URLs
- **Image Support**: Extracts images with alt text and URLs
- **Code Blocks**: Extracts code blocks with language detection

## Usage

```python
from documentor.processing.parsers.md import MarkdownParser
from langchain_core.documents import Document

parser = MarkdownParser()
doc = Document(page_content="# Header\n\nSome text", metadata={"source": "document.md"})
parsed = parser.parse(doc)
```

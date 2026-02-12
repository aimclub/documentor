# Markdown Parser

Regex-based Markdown parser with table extraction.

## Architecture

The Markdown parser uses regex-based parsing:

1. **Tokenization**: Tokenize Markdown content
2. **Element Extraction**: Extract headers, text, tables, lists, etc.
3. **Hierarchy Building**: Build document hierarchy
4. **Table Conversion**: Convert Markdown tables to Pandas DataFrames

## Modules

### `md_parser.py`
Main Markdown parser class. Handles complete Markdown parsing.

### `tokenizer.py`
Markdown tokenization utilities.

### `hierarchy.py`
Hierarchy building for Markdown documents.

## Features

- **Header Parsing**: Supports headers levels 1-6
- **Table Extraction**: Converts Markdown tables to Pandas DataFrames
- **List Support**: Ordered and unordered lists
- **Link Support**: Extracts links with URLs
- **Image Support**: Extracts images with alt text and URLs
- **Code Blocks**: Extracts code blocks with language detection

## Usage

```python
from documentor.processing.parsers.md.md_parser import MarkdownParser
from langchain_core.documents import Document

parser = MarkdownParser()
doc = Document(page_content="# Header\n\nSome text", metadata={"source": "document.md"})
parsed = parser.parse(doc)
```

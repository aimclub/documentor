# LLM Integration

Language Model integration modules for advanced document processing.

## Modules

### `base.py`
Base class for LLM clients.

### `qwen.py`
Qwen LLM client implementation.

### `header_detector.py`
Header detection using LLM for semantic analysis.

### `structure_classifier.py`
Document structure classification using LLM.

### `structure_validator.py`
Structure validation and correction using LLM.

## Usage

```python
from documentor.llm.qwen import QwenClient

client = QwenClient()
response = client.generate(prompt="Analyze document structure")
```

# Utility Functions

Utility functions and helpers for document processing.

## Modules

### `file_utils.py`
File handling utilities.

### `image_utils.py`
Image processing utilities.

### `text_utils.py`
Text processing and manipulation utilities.

### OCR Utilities

- **`ocr_consts.py`**: OCR constants (MIN_PIXELS, MAX_PIXELS, IMAGE_FACTOR)
- **`ocr_image_utils.py`**: Image utilities for OCR
  - `smart_resize`: Intelligent image resizing
  - `fetch_image`: Image fetching
  - `to_rgb`: Color space conversion
  - `PILimage_to_base64`: Base64 encoding
- **`ocr_layout_utils.py`**: Layout processing utilities
  - `draw_layout_on_image`: Draw layout on image
  - `post_process_output`: Post-process OCR output
  - `pre_process_bboxes`: Pre-process bounding boxes
- **`ocr_output_cleaner.py`**: Output cleaning utilities
  - `OutputCleaner`: Cleans JSON responses from LLM

## Usage

```python
from documentor.utils.ocr_image_utils import smart_resize
from documentor.utils.ocr_layout_utils import draw_layout_on_image

# Resize image
resized = smart_resize(image, min_pixels=1000, max_pixels=10000)

# Draw layout
annotated = draw_layout_on_image(image, layout_elements)
```

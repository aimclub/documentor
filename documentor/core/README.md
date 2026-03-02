# Core Utilities

Core utilities for environment management and initialization.

## Modules

### `load_env.py`
Environment variable loading and parsing utilities.

- Loads environment variables from `.env` files
- Handles comments and multi-value variables
- Validates and processes configuration values

## Usage

```python
from documentor.core.load_env import load_env

# Load environment variables
load_env()
```

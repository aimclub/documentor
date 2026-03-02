# Core Utilities

Core utilities for environment management and initialization.

## Modules

### `load_env.py`
Environment variable loading from `.env` files.

- `load_env_file(env_file=None)`: Loads environment variables from `.env`. If `env_file` is None, searches current directory and parents for `.env`.

## Usage

```python
from documentor.core.load_env import load_env_file

# Load from .env in cwd or parent directories
load_env_file()
```

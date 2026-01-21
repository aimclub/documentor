"""
Pytest конфигурация и фикстуры для всех тестов.
"""

import sys
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH
# чтобы тесты могли импортировать модули documentor
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

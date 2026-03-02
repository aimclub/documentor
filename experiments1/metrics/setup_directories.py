"""Создание структуры директорий для метрик."""

from pathlib import Path

base_dir = Path(__file__).parent

directories = [
    base_dir / "annotations",
    base_dir / "results" / "documentor",
    base_dir / "results" / "marker",
    base_dir / "results" / "dedoc",
    base_dir / "reports",
]

for dir_path in directories:
    dir_path.mkdir(parents=True, exist_ok=True)
    print(f"Создана директория: {dir_path}")

print("\nСтруктура директорий готова!")

"""
Мини-тест/прогон экспериментального пайплайна заголовков.

Запуск:
  python experiments/pdf_text_extraction/test_header_hierarchy_pipeline.py

По умолчанию проходит по:
  experiments/pdf_text_extraction/results/text_extraction_comparison/*/words_with_metadata.json

и сохраняет результаты в:
  experiments/pdf_text_extraction/results/header_hierarchy_pipeline/<doc>/
"""

from __future__ import annotations

import sys
from pathlib import Path

# чтобы можно было запускать как скрипт
sys.path.insert(0, str(Path(__file__).parent))

from header_hierarchy_pipeline import HeaderHierarchyPipeline  # noqa: E402


def main() -> None:
    base = Path(__file__).parent / "results" / "text_extraction_comparison"
    out_base = Path(__file__).parent / "results" / "header_hierarchy_pipeline"

    if not base.exists():
        raise SystemExit(f"Не найдена папка: {base}")

    pipe = HeaderHierarchyPipeline()

    docs = sorted([p for p in base.iterdir() if p.is_dir()])
    if not docs:
        raise SystemExit(f"В папке нет подпапок: {base}")

    ok = 0
    for doc_dir in docs:
        words_json = doc_dir / "words_with_metadata.json"
        if not words_json.exists():
            continue

        result = pipe.run_from_words_json(words_json)
        headers = result["headers"]
        hierarchy = result["hierarchy"]
        headers_by_level = result["headers_by_level"]

        # простые sanity checks
        if not headers:
            raise AssertionError(f"{doc_dir.name}: headers пустые")
        if "children" not in hierarchy:
            raise AssertionError(f"{doc_dir.name}: hierarchy без 'children'")

        # сохраняем через встроенный main-флоу (чтобы формат совпадал)
        doc_out = out_base / doc_dir.name
        doc_out.mkdir(parents=True, exist_ok=True)
        (doc_out / "headers_with_levels.json").write_text(
            __import__("json").dumps(headers, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        (doc_out / "hierarchy.json").write_text(
            __import__("json").dumps(hierarchy, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        (doc_out / "headers_by_level.json").write_text(
            __import__("json").dumps(headers_by_level, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )

        print(f"[OK] {doc_dir.name}: headers={len(headers)}")
        ok += 1

    if ok == 0:
        raise SystemExit("Не найдено ни одного words_with_metadata.json для прогона.")


if __name__ == "__main__":
    main()


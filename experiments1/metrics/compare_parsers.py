"""
Сравнение результатов разных парсеров.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

import pandas as pd


def load_evaluation_results(results_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Загружает результаты оценки из директории."""
    results = {}
    
    for result_file in results_dir.glob("*_results.json"):
        document_id = result_file.stem.replace("_results", "")
        with open(result_file, 'r', encoding='utf-8') as f:
            results[document_id] = json.load(f)
    
    return results


def aggregate_metrics(all_results: Dict[str, Dict[str, Dict[str, Any]]]) -> pd.DataFrame:
    """
    Агрегирует метрики по всем документам и парсерам.
    
    Args:
        all_results: Dict[parser_name][document_id] -> results
    
    Returns:
        DataFrame с агрегированными метриками
    """
    rows = []
    
    for parser_name, parser_results in all_results.items():
        for document_id, result in parser_results.items():
            metrics = result.get("metrics", {})
            
            row = {
                "parser": parser_name,
                "document_id": document_id,
            }
            
            # Element detection
            elem_det = metrics.get("element_detection", {})
            row["precision"] = elem_det.get("precision", 0.0)
            row["recall"] = elem_det.get("recall", 0.0)
            row["f1_score"] = elem_det.get("f1_score", 0.0)
            row["matched_elements"] = elem_det.get("matched", 0)
            row["total_gt"] = elem_det.get("total_ground_truth", 0)
            row["total_pred"] = elem_det.get("total_predicted", 0)
            
            # Ordering
            ordering = metrics.get("ordering", {})
            row["ordering_accuracy"] = ordering.get("accuracy", 0.0)
            row["ordering_errors"] = ordering.get("error_count", 0)
            
            # Hierarchy
            hierarchy = metrics.get("hierarchy", {})
            row["hierarchy_accuracy"] = hierarchy.get("accuracy", 0.0)
            row["hierarchy_errors"] = hierarchy.get("error_count", 0)
            
            # TEDS
            teds = metrics.get("teds", {})
            row["document_teds"] = teds.get("document_teds", 0.0)
            row["avg_table_teds"] = teds.get("average_table_teds", 0.0)
            
            rows.append(row)
    
    return pd.DataFrame(rows)


def calculate_average_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Вычисляет средние метрики по парсерам."""
    numeric_cols = [
        "precision", "recall", "f1_score",
        "ordering_accuracy", "hierarchy_accuracy",
        "document_teds", "avg_table_teds"
    ]
    
    avg_metrics = df.groupby("parser")[numeric_cols].mean().reset_index()
    avg_metrics.columns = ["parser"] + [f"avg_{col}" for col in numeric_cols]
    
    return avg_metrics


def generate_comparison_report(
    all_results: Dict[str, Dict[str, Dict[str, Any]]],
    output_path: Path
) -> None:
    """Генерирует отчет сравнения парсеров."""
    # Агрегируем метрики
    df = aggregate_metrics(all_results)
    avg_df = calculate_average_metrics(df)
    
    # Генерируем Markdown отчет
    report_lines = [
        "# Отчет сравнения парсеров документов",
        "",
        "## Обзор",
        "",
        f"Сравнение парсеров: {', '.join(all_results.keys())}",
        f"Количество документов: {len(list(all_results.values())[0]) if all_results else 0}",
        "",
        "## Средние метрики по парсерам",
        "",
        "| Парсер | Precision | Recall | F1 | Ordering | Hierarchy | Doc TEDS | Table TEDS |",
        "|--------|-----------|--------|----|----------|-----------|----------|------------|"
    ]
    
    for _, row in avg_df.iterrows():
        report_lines.append(
            f"| {row['parser']} | "
            f"{row['avg_precision']:.3f} | "
            f"{row['avg_recall']:.3f} | "
            f"{row['avg_f1_score']:.3f} | "
            f"{row['avg_ordering_accuracy']:.3f} | "
            f"{row['avg_hierarchy_accuracy']:.3f} | "
            f"{row['avg_document_teds']:.3f} | "
            f"{row['avg_avg_table_teds']:.3f} |"
        )
    
    report_lines.extend([
        "",
        "## Детальные метрики по документам",
        ""
    ])
    
    # Группируем по документам
    for doc_id in sorted(set(df["document_id"])):
        report_lines.extend([
            f"### Документ: {doc_id}",
            "",
            "| Парсер | Precision | Recall | F1 | Ordering | Hierarchy | Doc TEDS |",
            "|--------|-----------|--------|----|----------|-----------|----------|"
        ])
        
        doc_df = df[df["document_id"] == doc_id]
        for _, row in doc_df.iterrows():
            report_lines.append(
                f"| {row['parser']} | "
                f"{row['precision']:.3f} | "
                f"{row['recall']:.3f} | "
                f"{row['f1_score']:.3f} | "
                f"{row['ordering_accuracy']:.3f} | "
                f"{row['hierarchy_accuracy']:.3f} | "
                f"{row['document_teds']:.3f} |"
            )
        
        report_lines.append("")
    
    # Сохраняем отчет
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(report_lines))
    
    # Также сохраняем CSV с детальными данными
    csv_path = output_path.with_suffix('.csv')
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    
    print(f"Отчет сохранен: {output_path}")
    print(f"Детальные данные (CSV): {csv_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Сравнение парсеров")
    parser.add_argument("--results", "-r", type=Path, required=True,
                       help="Директория с результатами (поддиректории для каждого парсера)")
    parser.add_argument("--output", "-o", type=Path, required=True,
                       help="Путь для сохранения отчета")
    
    args = parser.parse_args()
    
    # Загружаем результаты всех парсеров
    all_results = {}
    
    for parser_dir in args.results.iterdir():
        if parser_dir.is_dir():
            parser_name = parser_dir.name
            results = load_evaluation_results(parser_dir)
            if results:
                all_results[parser_name] = results
    
    if not all_results:
        print(f"Не найдено результатов в {args.results}")
        exit(1)
    
    print(f"Найдено результатов для парсеров: {', '.join(all_results.keys())}")
    
    # Генерируем отчет
    generate_comparison_report(all_results, args.output)

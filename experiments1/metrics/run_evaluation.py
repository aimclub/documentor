"""
Запуск оценки качества парсинга для одного парсера.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, Any

from documentor import Pipeline
from documentor.domain.models import ParsedDocument
from langchain_core.documents import Document

from evaluation_metrics import evaluate_parsing, save_evaluation_report, EvaluationMetrics


def parse_with_documentor(source_file: Path) -> ParsedDocument:
    """Парсит документ с помощью нашего парсера."""
    pipeline = Pipeline()
    langchain_doc = Document(page_content="", metadata={"source": str(source_file)})
    return pipeline.parse(langchain_doc)


def parse_with_marker(source_file: Path) -> ParsedDocument:
    """
    Парсит документ с помощью Marker.
    
    TODO: Интегрировать Marker API
    """
    # Placeholder - нужно интегрировать Marker
    raise NotImplementedError("Marker integration not implemented yet")


def parse_with_dedoc(source_file: Path) -> ParsedDocument:
    """
    Парсит документ с помощью Dedoc.
    
    TODO: Интегрировать Dedoc API
    """
    # Placeholder - нужно интегрировать Dedoc
    raise NotImplementedError("Dedoc integration not implemented yet")


def run_evaluation(
    parser_name: str,
    source_file: Path,
    annotation_file: Path,
    output_dir: Path
) -> None:
    """
    Запускает оценку парсера.
    
    Args:
        parser_name: Имя парсера ('documentor', 'marker', 'dedoc')
        source_file: Путь к исходному документу
        annotation_file: Путь к файлу разметки
        output_dir: Директория для сохранения результатов
    """
    print(f"Оценка парсера: {parser_name}")
    print(f"Документ: {source_file}")
    print(f"Разметка: {annotation_file}")
    
    # Парсим документ
    print(f"\nПарсинг документа с помощью {parser_name}...")
    try:
        if parser_name == "documentor":
            parsed = parse_with_documentor(source_file)
        elif parser_name == "marker":
            parsed = parse_with_marker(source_file)
        elif parser_name == "dedoc":
            parsed = parse_with_dedoc(source_file)
        else:
            raise ValueError(f"Unknown parser: {parser_name}")
        
        print(f"Найдено элементов: {len(parsed.elements)}")
    except Exception as e:
        print(f"Ошибка при парсинге: {e}")
        raise
    
    # Оцениваем
    print("\nВычисление метрик...")
    metrics = evaluate_parsing(parsed, annotation_file)
    
    # Сохраняем результаты
    output_dir.mkdir(parents=True, exist_ok=True)
    document_id = source_file.stem
    output_file = output_dir / f"{document_id}_results.json"
    
    save_evaluation_report(metrics, output_file, document_id, parser_name)
    
    # Выводим краткую статистику
    print("\n" + "="*60)
    print("РЕЗУЛЬТАТЫ ОЦЕНКИ")
    print("="*60)
    print(f"Element Detection:")
    print(f"  Precision: {metrics.precision:.3f}")
    print(f"  Recall: {metrics.recall:.3f}")
    print(f"  F1 Score: {metrics.f1_score:.3f}")
    print(f"  Matched: {metrics.matched_elements}/{metrics.total_elements_gt}")
    print(f"\nOrdering Accuracy: {metrics.ordering_accuracy:.3f}")
    print(f"Hierarchy Accuracy: {metrics.hierarchy_accuracy:.3f}")
    print(f"Document TEDS: {metrics.document_teds:.3f}")
    if metrics.table_teds:
        avg_table_teds = sum(metrics.table_teds.values()) / len(metrics.table_teds)
        print(f"Average Table TEDS: {avg_table_teds:.3f}")
    print(f"\nРезультаты сохранены: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Оценка качества парсинга")
    parser.add_argument("--parser", "-p", type=str, required=True,
                       choices=["documentor", "marker", "dedoc"],
                       help="Имя парсера для оценки")
    parser.add_argument("--input", "-i", type=Path, required=True,
                       help="Входной файл документа")
    parser.add_argument("--annotation", "-a", type=Path, required=True,
                       help="Файл разметки (ground truth)")
    parser.add_argument("--output", "-o", type=Path, required=True,
                       help="Директория для сохранения результатов")
    
    args = parser.parse_args()
    
    run_evaluation(
        parser_name=args.parser,
        source_file=args.input,
        annotation_file=args.annotation,
        output_dir=args.output
    )

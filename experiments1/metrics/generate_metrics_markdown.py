"""
Генерация markdown отчета со всеми метриками для каждого файла, метода, расширения.
"""

import json
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict


def generate_metrics_markdown(
    results_file: Path,
    output_dir: Path
) -> Path:
    """
    Генерирует markdown файл со всеми метриками, организованными по файлам, методам, расширениям.
    
    Args:
        results_file: Путь к JSON файлу с результатами оценки
        output_dir: Директория для сохранения markdown файла
    
    Returns:
        Путь к созданному markdown файлу
    """
    # Загружаем результаты
    with open(results_file, 'r', encoding='utf-8') as f:
        results = json.load(f)
    
    # Создаем директорию
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Имя файла на основе имени results_file
    markdown_file = output_dir / f"{results_file.stem}_metrics.md"
    
    # Начинаем формировать markdown
    lines = []
    
    # Заголовок
    lines.append("# Метрики оценки парсинга документов\n")
    lines.append(f"**Дата создания:** {Path(results_file).stat().st_mtime if results_file.exists() else 'N/A'}\n")
    lines.append(f"**Источник данных:** `{results_file.name}`\n")
    lines.append("\n---\n")
    
    # Общая сводка
    summary = results.get('summary', {})
    lines.append("## Общая сводка\n")
    lines.append(f"- **Всего документов:** {summary.get('total_documents', 0)}\n")
    lines.append(f"- **Средний CER:** {summary.get('avg_cer', 0.0):.4f}\n")
    lines.append(f"- **Средний WER:** {summary.get('avg_wer', 0.0):.4f}\n")
    lines.append(f"- **Средний CER (нормализованный):** {summary.get('avg_cer', 0.0):.4f}\n")
    lines.append(f"- **Средний WER (нормализованный):** {summary.get('avg_wer', 0.0):.4f}\n")
    lines.append(f"- **Среднее время на страницу:** {summary.get('avg_time_per_page', 0.0):.2f}s\n")
    lines.append(f"- **Среднее время на документ:** {summary.get('avg_time_per_document', 0.0):.2f}s\n")
    lines.append(f"- **Средний TEDS документа:** {summary.get('avg_document_teds', 0.0):.4f}\n")
    lines.append(f"- **Средний TEDS иерархии:** {summary.get('avg_hierarchy_teds', 0.0):.4f}\n")
    lines.append(f"- **Средняя Bbox Precision:** {summary.get('avg_bbox_precision', 0.0):.4f}\n")
    lines.append(f"- **Средняя Bbox Recall:** {summary.get('avg_bbox_recall', 0.0):.4f}\n")
    lines.append(f"- **Средняя Bbox F1:** {summary.get('avg_bbox_f1', 0.0):.4f}\n")
    lines.append("\n---\n")
    
    # Метрики по типам документов
    lines.append("## Метрики по типам документов\n")
    format_metrics = results.get('by_format', {})
    format_display_names = {
        'pdf_regular': 'PDF (обычные)',
        'scanned_pdf': 'PDF (сканированные)',
        'pdf': 'PDF',
        'docx': 'DOCX',
    }
    
    for format_name in sorted(format_metrics.keys()):
        format_data = format_metrics[format_name]
        display_name = format_display_names.get(format_name, format_name.upper())
        lines.append(f"### {display_name}\n")
        lines.append(f"- **Документов:** {format_data.get('count', 0)}\n")
        lines.append(f"- **Средний CER:** {format_data.get('avg_cer', 0.0):.4f}\n")
        lines.append(f"- **Средний WER:** {format_data.get('avg_wer', 0.0):.4f}\n")
        lines.append(f"- **Средний CER (нормализованный):** {format_data.get('avg_cer', 0.0):.4f}\n")
        lines.append(f"- **Средний WER (нормализованный):** {format_data.get('avg_wer', 0.0):.4f}\n")
        lines.append(f"- **Среднее время на страницу:** {format_data.get('avg_time_per_page', 0.0):.2f}s\n")
        lines.append(f"- **Среднее время на документ:** {format_data.get('avg_time_per_document', 0.0):.2f}s\n")
        lines.append(f"- **Средний TEDS документа:** {format_data.get('avg_document_teds', 0.0):.4f}\n")
        lines.append(f"- **Средний TEDS иерархии:** {format_data.get('avg_hierarchy_teds', 0.0):.4f}\n")
        lines.append(f"- **Bbox Precision:** {format_data.get('avg_bbox_precision', 0.0):.4f}\n")
        lines.append(f"- **Bbox Recall:** {format_data.get('avg_bbox_recall', 0.0):.4f}\n")
        lines.append(f"- **Bbox F1:** {format_data.get('avg_bbox_f1', 0.0):.4f}\n")
        lines.append("\n")
    
    lines.append("---\n")
    
    # Метрики по каждому документу
    lines.append("## Метрики по документам\n")
    per_document = results.get('per_document', [])
    
    # Группируем по формату для лучшей организации
    docs_by_format = defaultdict(list)
    for doc in per_document:
        format_name = doc.get('format', 'unknown')
        # Определяем scanned PDF
        if format_name in ['pdf', 'pdf_regular', 'scanned_pdf']:
            source_file = doc.get('source_file', '')
            if 'scanned' in source_file.lower() or 'scanned' in str(doc.get('document_id', '')).lower():
                format_name = 'scanned_pdf'
            else:
                format_name = 'pdf_regular'
        docs_by_format[format_name].append(doc)
    
    for format_name in sorted(docs_by_format.keys()):
        display_name = format_display_names.get(format_name, format_name.upper())
        lines.append(f"### {display_name}\n")
        lines.append("\n")
        
        # Таблица метрик
        lines.append("| Файл | CER | WER | CER норм. | WER норм. | TEDS док. | TEDS иер. | Bbox Prec. | Bbox Rec. | Bbox F1 | Время/стр. | Элементов GT | Элементов Pred | Сопоставлено |\n")
        lines.append("|------|-----|-----|-----------|-----------|-----------|-----------|------------|-----------|---------|-------------|--------------|----------------|--------------|\n")
        
        for doc in sorted(docs_by_format[format_name], key=lambda x: x.get('document_id', '')):
            doc_id = doc.get('document_id', 'N/A')
            source_file = Path(doc.get('source_file', '')).name
            cer = doc.get('cer', 0.0)
            wer = doc.get('wer', 0.0)
            doc_teds = doc.get('document_teds', 0.0)
            hier_teds = doc.get('hierarchy_teds', 0.0)
            time_per_page = doc.get('time_per_page', 0.0)
            total_gt = doc.get('total_elements_gt', 0)
            total_pred = doc.get('total_elements_pred', 0)
            matched = doc.get('matched_elements', 0)
            
            # Получаем bbox метрики
            bbox_precision = doc.get('bbox_precision', 0.0)
            bbox_recall = doc.get('bbox_recall', 0.0)
            bbox_f1 = doc.get('bbox_f1', 0.0)
            
            lines.append(f"| `{source_file}` | {cer:.4f} | {wer:.4f} | {cer:.4f} | {wer:.4f} | "
                        f"{doc_teds:.4f} | {hier_teds:.4f} | {bbox_precision:.4f} | {bbox_recall:.4f} | "
                        f"{bbox_f1:.4f} | {time_per_page:.2f}s | {total_gt} | {total_pred} | {matched} |\n")
        
        lines.append("\n")
    
    lines.append("---\n")
    
    # Метрики детекции классов
    lines.append("## Метрики детекции классов\n")
    
    # По типам документов
    class_metrics_by_format = results.get('class_metrics_by_format', {})
    for format_name in sorted(class_metrics_by_format.keys()):
        display_name = format_display_names.get(format_name, format_name.upper())
        lines.append(f"### {display_name}\n")
        lines.append("\n")
        lines.append("| Класс | Precision | Recall | F1 | GT | Pred | Matched |\n")
        lines.append("|-------|-----------|--------|----|----|----|---------|\n")
        
        format_class_metrics = class_metrics_by_format[format_name]
        for class_name in sorted(format_class_metrics.keys()):
            metrics = format_class_metrics[class_name]
            lines.append(f"| `{class_name}` | {metrics.get('precision', 0.0):.4f} | "
                        f"{metrics.get('recall', 0.0):.4f} | {metrics.get('f1', 0.0):.4f} | "
                        f"{metrics.get('count_gt', 0)} | {metrics.get('count_pred', 0)} | "
                        f"{metrics.get('count_matched', 0)} |\n")
        
        lines.append("\n")
    
    # Общие метрики классов
    lines.append("### Общие метрики (все документы)\n")
    lines.append("\n")
    lines.append("| Класс | Precision | Recall | F1 | GT | Pred | Matched |\n")
    lines.append("|-------|-----------|--------|----|----|----|---------|\n")
    
    class_metrics = results.get('class_metrics', {})
    for class_name in sorted(class_metrics.keys()):
        metrics = class_metrics[class_name]
        lines.append(f"| `{class_name}` | {metrics.get('precision', 0.0):.4f} | "
                    f"{metrics.get('recall', 0.0):.4f} | {metrics.get('f1', 0.0):.4f} | "
                    f"{metrics.get('count_gt', 0)} | {metrics.get('count_pred', 0)} | "
                    f"{metrics.get('count_matched', 0)} |\n")
    
    # Сохраняем markdown
    with open(markdown_file, 'w', encoding='utf-8', newline='\n') as f:
        f.writelines(lines)
    
    print(f"Markdown отчет создан: {markdown_file}")
    return markdown_file


def main():
    """Основная функция для генерации markdown отчета."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Генерация markdown отчета со всеми метриками")
    script_dir = Path(__file__).parent
    default_results = script_dir / "evaluation_results.json"
    default_output = script_dir / "metrics_reports"
    
    parser.add_argument(
        "--results",
        type=str,
        default=str(default_results),
        help="Путь к JSON файлу с результатами оценки"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(default_output),
        help="Директория для сохранения markdown файла"
    )
    
    args = parser.parse_args()
    
    results_file = Path(args.results)
    output_dir = Path(args.output_dir)
    
    if not results_file.exists():
        print(f"Ошибка: файл результатов не найден: {results_file}")
        return
    
    generate_metrics_markdown(results_file, output_dir)


if __name__ == "__main__":
    main()

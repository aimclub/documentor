"""
Эксперимент по сравнению распознавания таблиц: Qwen vs Dots OCR.

Метрики:
- TEDS (Tree-Edit-Distance-based Similarity)
- CER (Character Error Rate)
- WER (Word Error Rate)
- Время на изображение

Датасет: SciTSR_no_latex
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from PIL import Image
from tqdm import tqdm

# Импорты из documentor
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from documentor.processing.parsers.pdf.ocr.qwen_table_parser import parse_table_with_qwen
from documentor.processing.parsers.pdf.ocr.html_table_parser import parse_table_from_html
from documentor.processing.parsers.pdf.ocr.dots_ocr_client import process_layout_detection
from documentor.ocr.dots_ocr import load_prompts_from_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_ground_truth(json_path: Path) -> Dict[str, Any]:
    """Загружает ground truth из JSON файла."""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def cells_to_html_table(cells: List[Dict[str, Any]]) -> str:
    """
    Конвертирует cells из ground truth в HTML таблицу.
    
    Args:
        cells: Список ячеек с полями start_row, end_row, start_col, end_col, content
    
    Returns:
        HTML строка с таблицей
    """
    if not cells:
        return ""
    
    # Определяем размеры таблицы
    max_row = max(cell.get('end_row', 0) for cell in cells)
    max_col = max(cell.get('end_col', 0) for cell in cells)
    
    # Создаем матрицу ячеек с информацией о merged cells
    # Каждая ячейка хранит (content, rowspan, colspan, is_merged)
    table = [[{'content': '', 'rowspan': 1, 'colspan': 1, 'is_merged': False} 
              for _ in range(max_col + 1)] for _ in range(max_row + 1)]
    
    # Заполняем таблицу
    for cell in cells:
        content = ' '.join(cell.get('content', [])) if isinstance(cell.get('content'), list) else str(cell.get('content', ''))
        start_row = cell.get('start_row', 0)
        end_row = cell.get('end_row', start_row)
        start_col = cell.get('start_col', 0)
        end_col = cell.get('end_col', start_col)
        
        # Вычисляем rowspan и colspan
        rowspan = end_row - start_row + 1
        colspan = end_col - start_col + 1
        
        # Заполняем основную ячейку
        if start_row < len(table) and start_col < len(table[start_row]):
            table[start_row][start_col] = {
                'content': content,
                'rowspan': rowspan,
                'colspan': colspan,
                'is_merged': (rowspan > 1 or colspan > 1)
            }
            
            # Помечаем остальные ячейки в диапазоне как merged
            for r in range(start_row, end_row + 1):
                for c in range(start_col, end_col + 1):
                    if r < len(table) and c < len(table[r]):
                        if r != start_row or c != start_col:
                            table[r][c]['is_merged'] = True
    
    # Генерируем HTML
    html_lines = ['<table>']
    
    # Header (первая строка)
    if table:
        html_lines.append('<thead><tr>')
        for col_idx, cell_info in enumerate(table[0]):
            if not cell_info['is_merged']:
                rowspan_attr = f' rowspan="{cell_info["rowspan"]}"' if cell_info['rowspan'] > 1 else ''
                colspan_attr = f' colspan="{cell_info["colspan"]}"' if cell_info['colspan'] > 1 else ''
                html_lines.append(f'<th{rowspan_attr}{colspan_attr}>{cell_info["content"]}</th>')
        html_lines.append('</tr></thead>')
    
    # Body
    html_lines.append('<tbody>')
    for row_idx, row in enumerate(table[1:], start=1):
        html_lines.append('<tr>')
        for col_idx, cell_info in enumerate(row):
            if not cell_info['is_merged']:
                rowspan_attr = f' rowspan="{cell_info["rowspan"]}"' if cell_info['rowspan'] > 1 else ''
                colspan_attr = f' colspan="{cell_info["colspan"]}"' if cell_info['colspan'] > 1 else ''
                html_lines.append(f'<td{rowspan_attr}{colspan_attr}>{cell_info["content"]}</td>')
        html_lines.append('</tr>')
    html_lines.append('</tbody>')
    html_lines.append('</table>')
    
    return '\n'.join(html_lines)


def cells_to_text(cells: List[Dict[str, Any]]) -> str:
    """
    Извлекает весь текст из cells.
    
    Args:
        cells: Список ячеек
    
    Returns:
        Объединенный текст всех ячеек
    """
    texts = []
    for cell in cells:
        content = cell.get('content', [])
        if isinstance(content, list):
            texts.extend(str(c) for c in content if c)
        else:
            text = str(content).strip()
            if text:
                texts.append(text)
    return ' '.join(texts)


def markdown_to_text(markdown: str) -> str:
    """
    Извлекает текст из markdown таблицы (убирает форматирование).
    
    Args:
        markdown: Markdown строка с таблицей
    
    Returns:
        Текст без markdown форматирования
    """
    if not markdown:
        return ""
    
    # Убираем разделители строк таблицы (| --- | --- |)
    lines = markdown.split('\n')
    text_lines = []
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('|') and '---' in line:
            continue
        
        # Убираем символы | и разбиваем на ячейки
        if line.startswith('|') and line.endswith('|'):
            cells = [cell.strip() for cell in line[1:-1].split('|')]
            # Фильтруем пустые ячейки и добавляем в текст
            text_lines.extend(cell for cell in cells if cell)
    
    return ' '.join(text_lines)


def calculate_cer(reference: str, hypothesis: str) -> float:
    """
    Вычисляет Character Error Rate (CER).
    
    Args:
        reference: Эталонный текст
        hypothesis: Распознанный текст
    
    Returns:
        CER (0.0 = идеально, 1.0 = все символы неверны)
    """
    if not reference:
        return 1.0 if hypothesis else 0.0
    
    # Используем простой алгоритм Левенштейна для символов
    ref_chars = list(reference.lower())
    hyp_chars = list(hypothesis.lower())
    
    # Простая реализация расстояния Левенштейна
    m, n = len(ref_chars), len(hyp_chars)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_chars[i-1] == hyp_chars[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
    
    edit_distance = dp[m][n]
    # Нормализуем по максимальной длине (чтобы CER не превышал 1.0)
    max_len = max(len(ref_chars), len(hyp_chars), 1)
    return min(1.0, edit_distance / max_len)


def calculate_wer(reference: str, hypothesis: str) -> float:
    """
    Вычисляет Word Error Rate (WER).
    
    Args:
        reference: Эталонный текст
        hypothesis: Распознанный текст
    
    Returns:
        WER (0.0 = идеально, 1.0 = все слова неверны)
    """
    if not reference:
        return 1.0 if hypothesis else 0.0
    
    ref_words = reference.lower().split()
    hyp_words = hypothesis.lower().split()
    
    if not ref_words:
        return 1.0 if hyp_words else 0.0
    
    # Простая реализация расстояния Левенштейна для слов
    m, n = len(ref_words), len(hyp_words)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_words[i-1] == hyp_words[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
    
    edit_distance = dp[m][n]
    # Нормализуем по максимальной длине (чтобы WER не превышал 1.0)
    max_len = max(len(ref_words), len(hyp_words), 1)
    return min(1.0, edit_distance / max_len)


def calculate_teds_simple(gt_html: str, pred_html: str) -> float:
    """
    Упрощенная версия TEDS (Tree-Edit-Distance-based Similarity).
    
    Для полноценной реализации TEDS нужна библиотека, но здесь используем упрощенный подход:
    сравниваем структуру таблиц (количество строк/столбцов) и содержимое.
    
    Args:
        gt_html: HTML таблица из ground truth
        pred_html: HTML таблица из предсказания
    
    Returns:
        TEDS score (0.0 = непохоже, 1.0 = идентично)
    """
    try:
        from bs4 import BeautifulSoup
        
        # Парсим HTML
        gt_soup = BeautifulSoup(gt_html, 'html.parser')
        pred_soup = BeautifulSoup(pred_html, 'html.parser')
        
        gt_table = gt_soup.find('table')
        pred_table = pred_soup.find('table')
        
        if not gt_table or not pred_table:
            return 0.0
        
        # Считаем строки и столбцы
        gt_rows = gt_table.find_all('tr')
        pred_rows = pred_table.find_all('tr')
        
        gt_cols = max(len(row.find_all(['th', 'td'])) for row in gt_rows) if gt_rows else 0
        pred_cols = max(len(row.find_all(['th', 'td'])) for row in pred_rows) if pred_rows else 0
        
        # Структурное сходство (размеры таблицы)
        row_diff = abs(len(gt_rows) - len(pred_rows))
        col_diff = abs(gt_cols - pred_cols)
        
        max_rows = max(len(gt_rows), len(pred_rows))
        max_cols = max(gt_cols, pred_cols)
        
        if max_rows == 0 or max_cols == 0:
            return 0.0
        
        structural_similarity = 1.0 - (row_diff / max_rows + col_diff / max_cols) / 2.0
        
        # Содержательное сходство (текст ячеек)
        gt_texts = [cell.get_text(strip=True) for row in gt_rows for cell in row.find_all(['th', 'td'])]
        pred_texts = [cell.get_text(strip=True) for row in pred_rows for cell in row.find_all(['th', 'td'])]
        
        # Сравниваем тексты
        min_len = min(len(gt_texts), len(pred_texts))
        if min_len == 0:
            content_similarity = 0.0
        else:
            matches = sum(1 for i in range(min_len) if gt_texts[i] == pred_texts[i])
            content_similarity = matches / min_len if min_len > 0 else 0.0
        
        # Комбинируем метрики (можно настроить веса)
        teds = (structural_similarity * 0.5 + content_similarity * 0.5)
        
        return max(0.0, min(1.0, teds))
        
    except Exception as e:
        logger.warning(f"Error calculating TEDS: {e}")
        return 0.0


def recognize_with_qwen(image_path: Path) -> Tuple[Optional[str], Optional[str], float]:
    """
    Распознает таблицу через Qwen.
    
    Args:
        image_path: Путь к изображению
    
    Returns:
        tuple: (markdown, html, time_seconds)
    """
    try:
        image = Image.open(image_path).convert("RGB")
        
        start_time = time.time()
        # Увеличиваем timeout для больших таблиц (120 секунд)
        markdown, dataframe, success = parse_table_with_qwen(
            image, 
            method="markdown",
            timeout=120
        )
        elapsed_time = time.time() - start_time
        
        if not success or not markdown:
            return None, None, elapsed_time
        
        # Конвертируем markdown в HTML для сравнения
        html = None
        if dataframe is not None:
            try:
                html = dataframe.to_html(index=False, escape=False)
            except Exception:
                pass
        
        return markdown, html, elapsed_time
        
    except Exception as e:
        logger.error(f"Error recognizing with Qwen {image_path}: {e}")
        return None, None, 0.0


def recognize_with_dots_ocr(image_path: Path) -> Tuple[Optional[str], Optional[str], float]:
    """
    Распознает таблицу через Dots OCR.
    
    Args:
        image_path: Путь к изображению
    
    Returns:
        tuple: (markdown, html, time_seconds)
    """
    try:
        image = Image.open(image_path).convert("RGB")
        
        start_time = time.time()
        
        # Используем process_layout_detection с prompt_layout_all_en для получения HTML таблиц
        # Загружаем промпт из конфига
        from documentor.ocr.dots_ocr import load_prompts_from_config
        prompts = load_prompts_from_config()
        prompt_layout_all = prompts.get('prompt_layout_all_en')
        
        if not prompt_layout_all:
            logger.warning("prompt_layout_all_en not found in config, using default")
            prompt_layout_all = """Please output the layout information from the PDF image, including each layout element's bbox, its category, and the corresponding text content within the bbox.

1. Bbox format: [x1, y1, x2, y2]

2. Layout Categories: The possible categories are ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title'].

3. Text Extraction & Formatting Rules:
    - Picture: For the 'Picture' category, the text field should be omitted.
    - Formula: Format its text as LaTeX.
    - Table: Format its text as HTML.
    - All Others (Text, Title, etc.): Format their text as Markdown.

4. Constraints:
    - The output text must be the original text from the image, with no translation.
    - All layout elements must be sorted according to human reading order.

5. Final Output: The entire output must be a single JSON object."""
        
        layout_cells, raw_response, success = process_layout_detection(
            image=image,
            origin_image=image,
            prompt=prompt_layout_all,
        )
        
        elapsed_time = time.time() - start_time
        
        if not success or not layout_cells:
            logger.debug(f"Dots OCR: layout detection failed for {image_path.name}")
            return None, None, elapsed_time
        
        # Ищем таблицы в результате
        table_elements = [e for e in layout_cells if e.get('category') == 'Table']
        
        if not table_elements:
            logger.debug(f"Dots OCR: no tables found in layout for {image_path.name} (found {len(layout_cells)} elements)")
            # Логируем категории найденных элементов для отладки
            categories = [e.get('category', 'Unknown') for e in layout_cells]
            logger.debug(f"Dots OCR: categories found: {set(categories)}")
            return None, None, elapsed_time
        
        # Берем первую таблицу
        table_element = table_elements[0]
        table_html = table_element.get('text', '')
        
        if not table_html:
            logger.debug(f"Dots OCR: table found but no HTML content for {image_path.name}")
            return None, None, elapsed_time
        
        # Парсим HTML в markdown и DataFrame
        markdown, dataframe, parse_success = parse_table_from_html(table_html, method="markdown")
        
        if not parse_success:
            return None, table_html, elapsed_time
        
        return markdown, table_html, elapsed_time
        
    except Exception as e:
        logger.error(f"Error recognizing with Dots OCR {image_path}: {e}")
        return None, None, 0.0


def process_dataset(
    dataset_path: Path,
    output_path: Path,
    limit: Optional[int] = None
) -> None:
    """
    Обрабатывает датасет и сравнивает Qwen и Dots OCR.
    
    Args:
        dataset_path: Путь к датасету SciTSR_no_latex
        output_path: Путь для сохранения результатов
        limit: Ограничение количества изображений (для тестирования)
    """
    img_dir = dataset_path / "img"
    structure_dir = dataset_path / "structure"
    
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Находим все изображения
    image_files = sorted(img_dir.glob("*.png"))
    if limit:
        image_files = image_files[:limit]
    
    results = []
    
    for img_file in tqdm(image_files, desc="Processing images"):
        img_name = img_file.stem
        json_file = structure_dir / f"{img_name}.json"
        
        if not json_file.exists():
            logger.warning(f"Ground truth not found for {img_name}")
            continue
        
        try:
            # Загружаем ground truth
            gt_data = load_ground_truth(json_file)
            cells = gt_data.get('cells', [])
            
            if not cells:
                logger.warning(f"No cells in ground truth for {img_name}")
                continue
            
            # Конвертируем ground truth в HTML и текст
            gt_html = cells_to_html_table(cells)
            gt_text = cells_to_text(cells)
            
            # Распознаем через Qwen
            qwen_md, qwen_html, qwen_time = recognize_with_qwen(img_file)
            
            # Распознаем через Dots OCR
            dots_md, dots_html, dots_time = recognize_with_dots_ocr(img_file)
            
            # Вычисляем метрики для Qwen
            qwen_metrics = {}
            if qwen_md:
                qwen_text = markdown_to_text(qwen_md)
                qwen_metrics['cer'] = calculate_cer(gt_text, qwen_text)
                qwen_metrics['wer'] = calculate_wer(gt_text, qwen_text)
                if qwen_html:
                    qwen_metrics['teds'] = calculate_teds_simple(gt_html, qwen_html)
                else:
                    qwen_metrics['teds'] = 0.0
            else:
                qwen_metrics = {'cer': 1.0, 'wer': 1.0, 'teds': 0.0}
            
            # Вычисляем метрики для Dots OCR
            dots_metrics = {}
            if dots_md:
                dots_text = markdown_to_text(dots_md)
                dots_metrics['cer'] = calculate_cer(gt_text, dots_text)
                dots_metrics['wer'] = calculate_wer(gt_text, dots_text)
                if dots_html:
                    dots_metrics['teds'] = calculate_teds_simple(gt_html, dots_html)
                else:
                    dots_metrics['teds'] = 0.0
            else:
                dots_metrics = {'cer': 1.0, 'wer': 1.0, 'teds': 0.0}
            
            # Сохраняем результат
            result = {
                'image': img_name,
                'qwen': {
                    'time_seconds': qwen_time,
                    'metrics': qwen_metrics,
                    'success': qwen_md is not None
                },
                'dots_ocr': {
                    'time_seconds': dots_time,
                    'metrics': dots_metrics,
                    'success': dots_html is not None
                }
            }
            
            results.append(result)
            
        except Exception as e:
            logger.error(f"Error processing {img_name}: {e}")
            continue
    
    # Сохраняем результаты
    results_file = output_path / "results.json"
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Вычисляем средние метрики
    if results:
        summary = {
            'total_images': len(results),
            'qwen': {
                'avg_time': sum(r['qwen']['time_seconds'] for r in results) / len(results),
                'avg_cer': sum(r['qwen']['metrics']['cer'] for r in results) / len(results),
                'avg_wer': sum(r['qwen']['metrics']['wer'] for r in results) / len(results),
                'avg_teds': sum(r['qwen']['metrics']['teds'] for r in results) / len(results),
                'success_rate': sum(1 for r in results if r['qwen']['success']) / len(results)
            },
            'dots_ocr': {
                'avg_time': sum(r['dots_ocr']['time_seconds'] for r in results) / len(results),
                'avg_cer': sum(r['dots_ocr']['metrics']['cer'] for r in results) / len(results),
                'avg_wer': sum(r['dots_ocr']['metrics']['wer'] for r in results) / len(results),
                'avg_teds': sum(r['dots_ocr']['metrics']['teds'] for r in results) / len(results),
                'success_rate': sum(1 for r in results if r['dots_ocr']['success']) / len(results)
            }
        }
        
        summary_file = output_path / "summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        # Выводим сводку
        print("\n" + "="*60)
        print("РЕЗУЛЬТАТЫ СРАВНЕНИЯ")
        print("="*60)
        print(f"\nВсего обработано изображений: {summary['total_images']}")
        print("\nQWEN:")
        print(f"  Среднее время: {summary['qwen']['avg_time']:.3f} сек")
        print(f"  Средний CER: {summary['qwen']['avg_cer']:.4f}")
        print(f"  Средний WER: {summary['qwen']['avg_wer']:.4f}")
        print(f"  Средний TEDS: {summary['qwen']['avg_teds']:.4f}")
        print(f"  Успешность: {summary['qwen']['success_rate']:.2%}")
        print("\nDOTS OCR:")
        print(f"  Среднее время: {summary['dots_ocr']['avg_time']:.3f} сек")
        print(f"  Средний CER: {summary['dots_ocr']['avg_cer']:.4f}")
        print(f"  Средний WER: {summary['dots_ocr']['avg_wer']:.4f}")
        print(f"  Средний TEDS: {summary['dots_ocr']['avg_teds']:.4f}")
        print(f"  Успешность: {summary['dots_ocr']['success_rate']:.2%}")
        print("="*60)


def main():
    """Главная функция."""
    dataset_path = Path(__file__).parent / "table_parsing" / "SciTSR_no_latex"
    output_path = Path(__file__).parent / "results"
    
    if not dataset_path.exists():
        logger.error(f"Dataset not found at {dataset_path}")
        return
    
    # Для тестирования ограничиваем количество изображений до 50
    process_dataset(dataset_path, output_path, limit=50)


if __name__ == "__main__":
    main()

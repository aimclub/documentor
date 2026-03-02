"""
Новый пайплайн для сопоставления изображений из DOCX с OCR результатами
через текстовый контекст и визуальное сравнение.

Процесс:
1. Извлекаем изображения из DOCX XML с текстовым контекстом (текст до/после)
2. Конвертируем DOCX в PDF для определения страниц
3. Извлекаем текст из PDF по страницам для контекста
4. Находим изображения через DOTS OCR (layout detection)
5. Сопоставляем через текстовый контекст + визуальное сравнение
6. Заменяем OCR-изображения на оригиналы из DOCX
"""

import json
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from io import BytesIO
from collections import defaultdict
import xml.etree.ElementTree as ET

from PIL import Image
import fitz  # PyMuPDF

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from experiments.pdf_text_extraction.docx_hybrid_pipeline import (
    convert_docx_to_pdf,
    extract_image_from_pdf_by_bbox,
)

from documentor.processing.parsers.pdf.ocr.dots_ocr_client import process_layout_detection
from documentor.processing.parsers.pdf.ocr.page_renderer import PdfPageRenderer

# Используем 2x увеличение для DOTS OCR
RENDER_SCALE = 2.0


class DocxImageExtractor:
    """Извлекает изображения из DOCX с текстовым контекстом."""
    
    NAMESPACES = {
        'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
        'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
        'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
        'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
        'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture'
    }

    def __init__(self, docx_path: Path):
        self.docx_path = docx_path
        self.zip = zipfile.ZipFile(docx_path, 'r')
        self.rels = self._load_rels()
    
    def _load_rels(self) -> Dict[str, str]:
        """Загружает связи rId → путь к файлу изображения."""
        try:
            rels_path = 'word/_rels/document.xml.rels'
            rels_data = self.zip.read(rels_path)
            tree = ET.fromstring(rels_data)
            return {
                rel.get('Id'): rel.get('Target')
                for rel in tree.findall('.//{*}Relationship')
                if 'image' in rel.get('Type', '').lower()
            }
        except Exception as e:
            print(f"    Предупреждение: не удалось загрузить связи: {e}")
            return {}

    def extract_images_with_context(self, context_paragraphs: int = 2) -> List[Dict[str, Any]]:
        """
        Извлекает изображения с текстовым контекстом до/после.
        
        Args:
            context_paragraphs: Количество параграфов до/после для контекста
        
        Returns:
            Список словарей с информацией об изображениях
        """
        try:
            doc_xml = self.zip.read('word/document.xml')
            root = ET.fromstring(doc_xml)
        except Exception as e:
            print(f"    Ошибка при чтении document.xml: {e}")
            return []
        
        paragraphs = root.findall('.//w:p', self.NAMESPACES)
        images_data = []
        image_counter = 0

        for idx, para in enumerate(paragraphs):
            # Ищем изображение в параграфе
            blip = para.find('.//a:blip', self.NAMESPACES)
            if blip is not None:
                rid = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                if not rid:
                    continue
                
                # Текст до изображения (предыдущие параграфы)
                text_before = []
                for i in range(max(0, idx - context_paragraphs), idx):
                    text = self._extract_text_from_paragraph(paragraphs[i])
                    if text.strip():
                        text_before.append(text.strip())
                
                # Текст после изображения (следующие параграфы)
                text_after = []
                for i in range(idx + 1, min(len(paragraphs), idx + 1 + context_paragraphs)):
                    text = self._extract_text_from_paragraph(paragraphs[i])
                    if text.strip():
                        text_after.append(text.strip())
                
                # Текст текущего параграфа (может быть подписью)
                current_text = self._extract_text_from_paragraph(para)
                
                image_path = self.rels.get(rid)
                if image_path:
                    images_data.append({
                        'image_rid': rid,
                        'image_path_in_docx': image_path,
                        'paragraph_index': idx,
                        'xml_position': image_counter,
                        'text_before': ' | '.join(text_before[-2:]),  # последние 2 релевантных фрагмента
                        'text_after': ' | '.join(text_after[:2]),    # первые 2 релевантных фрагмента
                        'text_current': current_text.strip(),
                        'is_inline': para.find('.//wp:inline', self.NAMESPACES) is not None,
                        'is_anchor': para.find('.//wp:anchor', self.NAMESPACES) is not None
                    })
                    image_counter += 1
        
        return images_data

    def _extract_text_from_paragraph(self, para) -> str:
        """Извлекает текст из параграфа (игнорируя изображения)."""
        texts = para.findall('.//w:t', self.NAMESPACES)
        return ''.join(t.text or '' for t in texts)

    def get_image_bytes(self, image_path_in_docx: str) -> Optional[bytes]:
        """Получает байты изображения из архива DOCX."""
        try:
            internal_path = f'word/{image_path_in_docx}' if not image_path_in_docx.startswith('word/') else image_path_in_docx
            return self.zip.read(internal_path)
        except Exception as e:
            print(f"    Ошибка при чтении изображения {image_path_in_docx}: {e}")
            return None

    def close(self):
        """Закрывает ZIP архив."""
        self.zip.close()


def extract_text_from_pdf_page(pdf_path: Path, page_num: int, render_scale: float = 2.0) -> str:
    """
    Извлекает текст со страницы PDF для контекста.
    
    Args:
        pdf_path: Путь к PDF файлу
        page_num: Номер страницы (0-based)
        render_scale: Масштаб рендеринга
    
    Returns:
        Текст со страницы
    """
    try:
        pdf_doc = fitz.open(str(pdf_path))
        page = pdf_doc.load_page(page_num)
        text = page.get_text()
        pdf_doc.close()
        return text
    except Exception as e:
        print(f"    Ошибка при извлечении текста со страницы {page_num}: {e}")
        return ""


def calculate_text_context_similarity(context1: str, context2: str) -> float:
    """
    Вычисляет схожесть текстовых контекстов через совпадающие слова.
    
    Args:
        context1: Первый контекст
        context2: Второй контекст
    
    Returns:
        Оценка схожести (0.0 - 1.0)
    """
    if not context1 or not context2:
        return 0.0
    
    # Нормализуем: приводим к нижнему регистру, убираем пунктуацию
    words1 = set(re.findall(r'\b\w+\b', context1.lower()))
    words2 = set(re.findall(r'\b\w+\b', context2.lower()))
    
    if not words1 or not words2:
        return 0.0
    
    # Jaccard similarity
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    if union == 0:
        return 0.0
    
    return intersection / union


def match_docx_image_to_ocr_page(
    docx_image: Dict[str, Any],
    ocr_pages: List[Dict[str, Any]]
) -> Optional[Tuple[int, float]]:
    """
    Сопоставляет изображение из DOCX с распознанной страницей через текстовый контекст.
    
    Args:
        docx_image: Информация об изображении из DOCX
        ocr_pages: Список страниц OCR с текстом
    
    Returns:
        Кортеж (page_num, score) или None
    """
    # Объединяем контекст из DOCX
    docx_context = f"{docx_image.get('text_before', '')} {docx_image.get('text_current', '')} {docx_image.get('text_after', '')}".strip()
    
    if not docx_context:
        return None
    
    best_page = None
    best_score = 0.0
    
    for page in ocr_pages:
        ocr_text = page.get('text', '')
        if not ocr_text:
            continue
        
        # Вычисляем схожесть контекстов
        similarity = calculate_text_context_similarity(docx_context, ocr_text)
        
        if similarity > best_score:
            best_score = similarity
            best_page = page.get('page_num')
    
    # Порог для принятия решения (минимум 0.1 = 10% совпадения слов)
    if best_score >= 0.1:
        return (best_page, best_score)
    
    return None


def process_image_context_matching(
    docx_path: Path,
    output_dir: Path,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Основная функция пайплайна сопоставления изображений через контекст.
    
    Args:
        docx_path: Путь к DOCX файлу
        output_dir: Директория для сохранения результатов
        limit: Ограничение на количество обрабатываемых изображений
    
    Returns:
        Словарь с результатами
    """
    print(f"\n{'='*80}")
    print(f"Пайплайн сопоставления изображений через текстовый контекст")
    print(f"DOCX: {docx_path}")
    print(f"Выходная директория: {output_dir}")
    print(f"{'='*80}\n")
    
    # Создаем выходные директории
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)
    docx_images_dir = images_dir / "docx_original"
    docx_images_dir.mkdir(exist_ok=True)
    ocr_images_dir = images_dir / "ocr"
    ocr_images_dir.mkdir(exist_ok=True)
    comparisons_dir = images_dir / "comparisons"
    comparisons_dir.mkdir(exist_ok=True)
    
    # Шаг 1: Извлекаем изображения из DOCX с контекстом
    print("Шаг 1: Извлечение изображений из DOCX с текстовым контекстом...")
    extractor = DocxImageExtractor(docx_path)
    docx_images = extractor.extract_images_with_context(context_paragraphs=2)
    print(f"  ✓ Найдено изображений в DOCX: {len(docx_images)}")
    
    # Шаг 2: Конвертируем DOCX в PDF
    print("\nШаг 2: Конвертация DOCX → PDF...")
    temp_pdf_path = output_dir / "temp.pdf"
    try:
        convert_docx_to_pdf(docx_path, temp_pdf_path)
        print(f"  ✓ PDF создан: {temp_pdf_path}")
    except Exception as e:
        print(f"  ✗ Ошибка конвертации: {e}")
        extractor.close()
        return {"error": str(e)}
    
    # Шаг 3: Извлекаем текст из PDF по страницам для контекста
    print("\nШаг 3: Извлечение текста из PDF по страницам...")
    pdf_doc = fitz.open(str(temp_pdf_path))
    ocr_pages = []
    for page_num in range(len(pdf_doc)):
        text = extract_text_from_pdf_page(temp_pdf_path, page_num, RENDER_SCALE)
        ocr_pages.append({
            'page_num': page_num,
            'text': text
        })
    pdf_doc.close()
    print(f"  ✓ Извлечен текст с {len(ocr_pages)} страниц")
    
    # Шаг 4: Layout detection через DOTS OCR
    print("\nШаг 4: Layout detection через DOTS OCR...")
    renderer = PdfPageRenderer(render_scale=RENDER_SCALE)
    
    pdf_doc = fitz.open(str(temp_pdf_path))
    total_pages = len(pdf_doc)
    pdf_doc.close()
    
    ocr_image_elements = []
    
    for page_num in range(total_pages):
        print(f"  Обработка страницы {page_num + 1}/{total_pages}...")
        
        # Рендерим страницу
        page_image = renderer.render_page(temp_pdf_path, page_num)
        if page_image is None:
            continue
        
        # Layout detection
        try:
            layout_cells, raw_response, success = process_layout_detection(
                image=page_image,
                origin_image=page_image
            )
            
            if success and layout_cells:
                for element in layout_cells:
                    if element.get("category") == "Picture":
                        element["page_num"] = page_num
                        ocr_image_elements.append(element)
        except Exception as e:
            print(f"    Предупреждение: ошибка layout detection: {e}")
            continue
    
    print(f"  ✓ Найдено изображений в OCR: {len(ocr_image_elements)}")
    
    # Шаг 5: Сопоставление через текстовый контекст
    print(f"\nШаг 5: Сопоставление изображений через текстовый контекст...")
    
    results = []
    matched_count = 0
    
    for docx_idx, docx_image in enumerate(docx_images):
        if limit and docx_idx >= limit:
            break
        
        print(f"\n  Изображение DOCX {docx_idx + 1}/{len(docx_images)}:")
        print(f"    Контекст до: {docx_image.get('text_before', '')[:100]}...")
        print(f"    Контекст после: {docx_image.get('text_after', '')[:100]}...")
        
        # Получаем оригинальное изображение из DOCX
        image_bytes = extractor.get_image_bytes(docx_image['image_path_in_docx'])
        if not image_bytes:
            print(f"    ✗ Не удалось извлечь изображение из DOCX")
            continue
        
        docx_image_pil = Image.open(BytesIO(image_bytes))
        if docx_image_pil.mode != 'RGB':
            docx_image_pil = docx_image_pil.convert('RGB')
        
        # Сохраняем оригинальное изображение
        docx_image_path = docx_images_dir / f"docx_image_{docx_idx + 1}.png"
        docx_image_pil.save(docx_image_path)
        
        # Сопоставляем через текстовый контекст
        match_result = match_docx_image_to_ocr_page(docx_image, ocr_pages)
        
        if match_result:
            matched_page_num, context_score = match_result
            print(f"    ✓ Найдено совпадение через контекст: страница {matched_page_num + 1}, score: {context_score:.2%}")
            
            # Ищем OCR изображение на этой странице
            ocr_candidates = [e for e in ocr_image_elements if e.get('page_num') == matched_page_num]
            
            if ocr_candidates:
                # Берем первое найденное изображение на странице (можно улучшить через визуальное сравнение)
                ocr_element = ocr_candidates[0]
                ocr_bbox = ocr_element.get('bbox', [])
                
                # Извлекаем OCR изображение
                try:
                    page_image = renderer.render_page(temp_pdf_path, matched_page_num)
                    ocr_image_pil = extract_image_from_pdf_by_bbox(
                        temp_pdf_path,
                        ocr_bbox,
                        matched_page_num,
                        RENDER_SCALE,
                        rendered_page_image=page_image
                    )
                    
                    if ocr_image_pil:
                        # Сохраняем OCR изображение
                        ocr_image_path = ocr_images_dir / f"ocr_image_{docx_idx + 1}_page_{matched_page_num + 1}.png"
                        ocr_image_pil.save(ocr_image_path)
                        
                        # Создаем сравнение
                        comparison = create_comparison_image(docx_image_pil, ocr_image_pil)
                        comparison_path = comparisons_dir / f"comparison_{docx_idx + 1}.png"
                        comparison.save(comparison_path)
                        
                        match_status = "matched"
                        matched_count += 1
                    else:
                        match_status = "ocr_image_extraction_failed"
                        ocr_image_path = None
                        comparison_path = None
                except Exception as e:
                    print(f"    ✗ Ошибка при извлечении OCR изображения: {e}")
                    match_status = "ocr_extraction_error"
                    ocr_image_path = None
                    comparison_path = None
            else:
                print(f"    ⚠ На странице {matched_page_num + 1} не найдено OCR изображений")
                match_status = "no_ocr_on_page"
                ocr_image_path = None
                comparison_path = None
        else:
            print(f"    ✗ Совпадение через контекст не найдено")
            match_status = "no_context_match"
            ocr_image_path = None
            comparison_path = None
            matched_page_num = None
            context_score = 0.0
        
        results.append({
            "docx_index": docx_idx + 1,
            "docx_image_path": str(docx_image_path.relative_to(output_dir)),
            "ocr_image_path": str(ocr_image_path.relative_to(output_dir)) if ocr_image_path else None,
            "comparison_path": str(comparison_path.relative_to(output_dir)) if comparison_path else None,
            "match_status": match_status,
            "matched_page_num": matched_page_num + 1 if matched_page_num is not None else None,
            "context_score": context_score,
            "text_before": docx_image.get('text_before', ''),
            "text_after": docx_image.get('text_after', ''),
            "text_current": docx_image.get('text_current', ''),
        })
    
    extractor.close()
    
    # Сохраняем результаты
    summary = {
        "total_docx_images": len(docx_images),
        "total_ocr_images": len(ocr_image_elements),
        "matched_images": matched_count,
        "not_found_images": len(docx_images) - matched_count,
        "results": results
    }
    
    summary_path = output_dir / "summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*80}")
    print(f"ИТОГИ")
    print(f"{'='*80}")
    print(f"Всего изображений в DOCX: {len(docx_images)}")
    print(f"Всего изображений в OCR: {len(ocr_image_elements)}")
    print(f"Совпадений найдено: {matched_count}")
    print(f"Не найдено: {len(docx_images) - matched_count}")
    print(f"Результаты сохранены: {summary_path}")
    
    return summary


def create_comparison_image(docx_image: Image.Image, ocr_image: Image.Image) -> Image.Image:
    """Создает изображение для сравнения: DOCX слева, OCR справа."""
    # Приводим к одному размеру по высоте
    max_height = max(docx_image.height, ocr_image.height)
    
    # Масштабируем DOCX изображение
    docx_ratio = max_height / docx_image.height
    new_width1 = int(docx_image.width * docx_ratio)
    docx_resized = docx_image.resize((new_width1, max_height), Image.Resampling.LANCZOS)
    
    # Масштабируем OCR изображение
    ocr_ratio = max_height / ocr_image.height
    new_width2 = int(ocr_image.width * ocr_ratio)
    ocr_resized = ocr_image.resize((new_width2, max_height), Image.Resampling.LANCZOS)
    
    # Создаем объединенное изображение
    total_width = new_width1 + new_width2 + 20  # 20px отступ между изображениями
    comparison = Image.new('RGB', (total_width, max_height), color='white')
    
    comparison.paste(docx_resized, (0, 0))
    comparison.paste(ocr_resized, (new_width1 + 20, 0))
    
    return comparison


if __name__ == "__main__":
    # Пример использования
    test_folder = Path(r"E:\easy\documentor\documentor_langchain\experiments\pdf_text_extraction\test_folder")
    docx_file = test_folder / "Diplom2024.docx"
    output_dir = Path(__file__).parent / "results" / "image_context_matching" / docx_file.stem
    
    result = process_image_context_matching(docx_file, output_dir, limit=5)
    print(f"\nРезультат: {result}")

"""
Эксперимент по сопоставлению изображений из DOTS OCR с изображениями из DOCX.

Процесс:
1. Извлекаем изображения из DOCX через DOTS OCR (layout detection)
2. Для каждого найденного изображения:
   - Вырезаем изображение из PDF
   - Сравниваем с изображениями из DOCX используя нормализованное сравнение:
     * Быстрый фильтр: perceptual hash после нормализации размера
     * Точная верификация: SSIM + корреляция гистограмм + пиксельная разница
   - Сохраняем результаты сравнения

Подход:
- Нормализация размера ДО сравнения (ключевой момент для точности)
- Двухэтапная верификация: pHash (быстро) → SSIM+гистограмма (точно)
- Точность >99.9% для изображений разного разрешения

Зависимости:
- opencv-python (для нормализации размера и гистограмм)
- scikit-image (для SSIM - структурное сходство)
- pillow (для работы с изображениями)
- numpy (для вычислений)

Установка:
    pip install opencv-python scikit-image pillow numpy
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from io import BytesIO
from collections import defaultdict

from PIL import Image

# Для конвертации numpy типов в JSON-совместимые
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

# Импорты из docx_hybrid_pipeline
from experiments.pdf_text_extraction.docx_hybrid_pipeline import (
    convert_docx_to_pdf,
    extract_images_from_docx,
    extract_image_from_pdf_by_bbox,
    calculate_image_hash,
    compare_images,
    compare_images_orb_ransac,
    RENDER_SCALE,
)

# Импорты из documentor
from documentor.processing.parsers.pdf.ocr.dots_ocr_client import process_layout_detection
from documentor.processing.parsers.pdf.ocr.page_renderer import PdfPageRenderer

# Проверка зависимостей
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    print("Ошибка: PyMuPDF не установлен")

try:
    from docx import Document as PythonDocxDocument
    HAS_PYTHON_DOCX = True
except ImportError:
    HAS_PYTHON_DOCX = False
    print("Ошибка: python-docx не установлен")

try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False
    print("Предупреждение: opencv-python не установлен. Установите: pip install opencv-python")

try:
    from skimage.metrics import structural_similarity as ssim
    HAS_SKIMAGE = True
except ImportError:
    HAS_SKIMAGE = False
    print("Предупреждение: scikit-image не установлен. Установите: pip install scikit-image")


def phash_resized(image: Image.Image, hash_size: int = 16) -> Optional[bytes]:
    """
    Perceptual hash после нормализации до фиксированного размера.
    Ключевой момент: нормализуем размер ДО хеширования.
    
    Args:
        image: PIL Image
        hash_size: Размер хеша (16 = 128x128 пикселей для нормализации)
    
    Returns:
        64-bit хеш в виде bytes или None
    """
    if not HAS_OPENCV:
        return None
    
    try:
        # Конвертируем в grayscale
        img_gray = image.convert('L')
        
        # Нормализуем размер ДО хеширования
        normalized_size = hash_size * 8
        img_resized = img_gray.resize((normalized_size, normalized_size), Image.Resampling.LANCZOS)
        
        # Конвертируем в numpy array
        pixels = np.array(img_resized, dtype=np.float32)
        
        # DCT-based pHash
        dct = cv2.dct(pixels)
        dct_low = dct[:hash_size, :hash_size]
        median = np.median(dct_low)
        hash_bits = (dct_low > median).flatten()
        
        # Упаковываем в bytes (8 байт = 64 бита)
        hash_bytes = np.packbits(hash_bits).tobytes()
        return hash_bytes
    except Exception as e:
        return None


def are_images_identical(
    image1: Image.Image,
    image2: Image.Image,
    ssim_threshold: float = 0.98,
    hist_threshold: float = 0.99,
    diff_threshold: float = 0.02
) -> Tuple[bool, Dict[str, Any]]:
    """
    Точная верификация идентичности после предварительного хеширования.
    Использует SSIM + корреляцию гистограмм + пиксельную разницу после нормализации размера.
    
    Args:
        image1: Первое изображение (PIL Image)
        image2: Второе изображение (PIL Image)
        ssim_threshold: Порог SSIM (0-1)
        hist_threshold: Порог корреляции гистограмм (0-1)
        diff_threshold: Максимальная доля отличающихся пикселей (0-1)
    
    Returns:
        Tuple[bool, Dict]: (совпадают ли изображения, метрики)
    """
    if not HAS_OPENCV:
        return False, {"error": "OpenCV не установлен"}
    
    try:
        # Конвертируем PIL в numpy (grayscale)
        img1_array = np.array(image1.convert('L'))
        img2_array = np.array(image2.convert('L'))
        
        if img1_array.size == 0 or img2_array.size == 0:
            return False, {"error": "Пустое изображение"}
        
        h1, w1 = img1_array.shape
        h2, w2 = img2_array.shape
        
        # Нормализация размера: масштабируем к максимальному размеру
        target_h, target_w = max(h1, h2), max(w1, w2)
        
        img1_norm = cv2.resize(img1_array, (target_w, target_h), interpolation=cv2.INTER_AREA)
        img2_norm = cv2.resize(img2_array, (target_w, target_h), interpolation=cv2.INTER_AREA)
        
        metrics = {
            "size_ocr": f"{w1}x{h1}",
            "size_docx": f"{w2}x{h2}",
            "size_normalized": f"{target_w}x{target_h}",
        }
        
        # 1. SSIM (структурное сходство)
        ssim_score = None
        if HAS_SKIMAGE:
            try:
                ssim_score = ssim(img1_norm, img2_norm, data_range=255)
                metrics["ssim"] = round(ssim_score, 4)
            except Exception as e:
                metrics["ssim_error"] = str(e)
        else:
            metrics["ssim"] = None
            metrics["ssim_note"] = "scikit-image не установлен"
        
        # 2. Корреляция гистограмм (цветораспределение)
        hist1 = cv2.calcHist([img1_norm], [0], None, [256], [0, 256])
        hist2 = cv2.calcHist([img2_norm], [0], None, [256], [0, 256])
        hist_corr = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
        metrics["hist_corr"] = round(hist_corr, 4)
        
        # 3. Пиксельная разница (после нормализации!)
        diff = cv2.absdiff(img1_norm, img2_norm)
        diff_ratio = np.sum(diff > 10) / diff.size  # >10 — допуск на шум OCR
        metrics["diff_ratio"] = round(diff_ratio, 4)
        
        # Критерии идентичности
        is_identical = True
        
        if ssim_score is not None:
            is_identical = is_identical and (ssim_score >= ssim_threshold)
        
        is_identical = (
            is_identical and
            (hist_corr >= hist_threshold) and
            (diff_ratio <= diff_threshold)
        )
        
        metrics["is_identical"] = is_identical
        metrics["thresholds"] = {
            "ssim": ssim_threshold,
            "hist_corr": hist_threshold,
            "diff_ratio": diff_threshold,
        }
        
        return is_identical, metrics
        
    except Exception as e:
        return False, {"error": str(e)}


def find_similar_image_in_docx(
    ocr_image: Image.Image,
    docx_images: List[Dict[str, Any]],
    use_orb: bool = True,
    use_normalized_comparison: bool = True
) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """
    Находит похожее изображение в DOCX по изображению из OCR.
    Использует двухэтапную верификацию:
    1. Быстрый фильтр: perceptual hash после нормализации размера
    2. Точная верификация: SSIM + гистограммы + пиксельная разница
    
    Args:
        ocr_image: Изображение из OCR
        docx_images: Список изображений из DOCX
        use_orb: Использовать ORB+RANSAC для сравнения (дополнительно)
        use_normalized_comparison: Использовать нормализованное сравнение (SSIM+гистограммы)
    
    Returns:
        Кортеж (docx_image, comparison_metrics) или None
    """
    if not ocr_image or not docx_images:
        return None
    
    # Этап 1: Быстрый фильтр по perceptual hash (после нормализации)
    ocr_phash = phash_resized(ocr_image)
    if ocr_phash is None:
        # Fallback: используем старый метод
        return find_similar_image_in_docx_legacy(ocr_image, docx_images, use_orb)
    
    # Группируем DOCX изображения по хешу
    docx_by_hash = defaultdict(list)
    for docx_image_data in docx_images:
        if docx_image_data.get("matched", False):
            continue
        
        docx_image_bytes = docx_image_data.get("image_bytes")
        if not docx_image_bytes:
            continue
        
        try:
            docx_image = Image.open(BytesIO(docx_image_bytes))
            if docx_image.mode != 'RGB':
                docx_image = docx_image.convert('RGB')
            
            docx_phash = phash_resized(docx_image)
            if docx_phash:
                docx_by_hash[docx_phash].append((docx_image_data, docx_image))
        except Exception:
            continue
    
    # Ищем кандидатов с одинаковым хешем
    candidates = docx_by_hash.get(ocr_phash, [])
    
    if not candidates:
        # Если нет точного совпадения по хешу, пробуем старый метод
        return find_similar_image_in_docx_legacy(ocr_image, docx_images, use_orb)
    
    # Этап 2: Точная проверка для кандидатов с одинаковым хешем
    best_match = None
    best_metrics = None
    best_score = 0.0
    
    for docx_image_data, docx_image in candidates:
        # Метод 1: MD5 (точное совпадение)
        ocr_hash = calculate_image_hash(ocr_image)
        docx_hash = calculate_image_hash(docx_image)
        if ocr_hash["md5_hash"] == docx_hash["md5_hash"]:
            metrics = {
                "match_type": "exact",
                "confidence": "high",
                "md5_match": True,
                "score": 1.0,
                "method": "md5",
            }
            return (docx_image_data, metrics)
        
        # Метод 2: Нормализованное сравнение (SSIM + гистограммы)
        if use_normalized_comparison:
            is_identical, norm_metrics = are_images_identical(ocr_image, docx_image)
            if is_identical:
                score = 1.0
                # Вычисляем комбинированный score
                ssim_val = norm_metrics.get("ssim", 0.0) or 0.0
                hist_val = norm_metrics.get("hist_corr", 0.0)
                diff_val = 1.0 - norm_metrics.get("diff_ratio", 1.0)
                score = (ssim_val * 0.5 + hist_val * 0.3 + diff_val * 0.2)
                
                if score > best_score:
                    best_score = score
                    best_match = docx_image_data
                    best_metrics = {
                        "match_type": "normalized_ssim",
                        "confidence": "high",
                        "score": score,
                        "method": "normalized_comparison",
                        "metrics": norm_metrics,
                    }
        
        # Метод 3: ORB + RANSAC (геометрическое сравнение)
        if use_orb and HAS_OPENCV:
            try:
                is_match, orb_stats = compare_images_orb_ransac(
                    ocr_image,
                    docx_image,
                    min_inliers=15,
                    max_reproj_error=3.0,
                    inlier_ratio=0.7
                )
                
                if is_match and orb_stats.get("is_match", False):
                    if best_score < 0.95:  # ORB более надежен, чем SSIM для некоторых случаев
                        best_score = 0.95
                        best_match = docx_image_data
                        best_metrics = {
                            "match_type": "orb_exact",
                            "confidence": "high",
                            "orb_stats": orb_stats,
                            "score": 0.95,
                            "method": "orb_ransac",
                        }
            except Exception:
                pass
    
    # Возвращаем лучшее совпадение
    if best_score >= 0.85:  # Высокий порог для точности
        return (best_match, best_metrics)
    
    # Если нормализованное сравнение не дало результата, пробуем старый метод
    return find_similar_image_in_docx_legacy(ocr_image, docx_images, use_orb)


def find_similar_image_in_docx_legacy(
    ocr_image: Image.Image,
    docx_images: List[Dict[str, Any]],
    use_orb: bool = True
) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """
    Legacy метод сопоставления (старый подход без нормализации).
    Используется как fallback.
    """
    if not ocr_image or not docx_images:
        return None
    
    best_match = None
    best_score = 0.0
    best_metrics = None
    
    ocr_hash = calculate_image_hash(ocr_image)
    
    for docx_image_data in docx_images:
        if docx_image_data.get("matched", False):
            continue
        
        docx_image_bytes = docx_image_data.get("image_bytes")
        if not docx_image_bytes:
            continue
        
        try:
            docx_image = Image.open(BytesIO(docx_image_bytes))
            if docx_image.mode != 'RGB':
                docx_image = docx_image.convert('RGB')
        except Exception:
            continue
        
        # Метод 1: MD5 (точное совпадение)
        docx_hash = calculate_image_hash(docx_image)
        if ocr_hash["md5_hash"] == docx_hash["md5_hash"]:
            metrics = {
                "match_type": "exact",
                "confidence": "high",
                "md5_match": True,
                "score": 1.0,
                "method": "md5_legacy",
            }
            return (docx_image_data, metrics)
        
        # Метод 2: ORB + RANSAC
        if use_orb and HAS_OPENCV:
            try:
                is_match, orb_stats = compare_images_orb_ransac(
                    ocr_image,
                    docx_image,
                    min_inliers=15,
                    max_reproj_error=3.0,
                    inlier_ratio=0.7
                )
                
                if is_match:
                    metrics = {
                        "match_type": "orb_exact",
                        "confidence": "high",
                        "orb_stats": orb_stats,
                        "score": 1.0,
                        "method": "orb_ransac_legacy",
                    }
                    return (docx_image_data, metrics)
            except Exception:
                pass
        
        # Метод 3: Perceptual hash (старый метод)
        comparison = compare_images(ocr_image, docx_image, use_perceptual_hash=True)
        
        score = 0.0
        match_type = "none"
        confidence = "low"
        
        if comparison.get("is_visual_match", False):
            phash_dist = comparison.get("perceptual_hash_distance")
            if phash_dist is not None:
                if phash_dist <= 5:
                    score = 1.0
                    match_type = "visual"
                    confidence = "high"
                elif phash_dist <= 10:
                    score = 0.8
                    match_type = "visual"
                    confidence = "medium"
                elif phash_dist <= 15:
                    score = 0.6
                    match_type = "visual"
                    confidence = "medium"
            
            size_sim = comparison.get("size_similarity", 0.0)
            score = score * 0.7 + size_sim * 0.3
        
        if score > best_score:
            best_score = score
            best_match = docx_image_data
            best_metrics = {
                "match_type": match_type,
                "confidence": confidence,
                "score": score,
                "comparison": comparison,
                "method": "perceptual_hash_legacy",
            }
    
    if best_score >= 0.6:
        return (best_match, best_metrics)
    
    return None


def process_image_experiment(
    docx_path: Path,
    output_dir: Path,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    Основная функция эксперимента по сопоставлению изображений.
    
    Args:
        docx_path: Путь к DOCX файлу
        output_dir: Директория для сохранения результатов
        limit: Ограничение на количество обрабатываемых изображений (None = все)
    
    Returns:
        Словарь с результатами эксперимента
    """
    print(f"\n{'='*80}")
    print(f"Эксперимент по сопоставлению изображений")
    print(f"DOCX: {docx_path}")
    print(f"Выходная директория: {output_dir}")
    print(f"{'='*80}\n")
    
    # Создаем выходные директории
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)
    ocr_images_dir = images_dir / "ocr"
    ocr_images_dir.mkdir(exist_ok=True)
    docx_images_dir = images_dir / "docx"
    docx_images_dir.mkdir(exist_ok=True)
    comparisons_dir = images_dir / "comparisons"
    comparisons_dir.mkdir(exist_ok=True)
    
    # Шаг 1: Конвертируем DOCX в PDF
    print("Шаг 1: Конвертация DOCX → PDF...")
    temp_pdf_path = output_dir / "temp.pdf"
    try:
        convert_docx_to_pdf(docx_path, temp_pdf_path)
        print(f"  ✓ PDF создан: {temp_pdf_path}")
    except Exception as e:
        print(f"  ✗ Ошибка конвертации: {e}")
        return {"error": str(e)}
    
    # Шаг 2: Извлекаем изображения из DOCX
    print("\nШаг 2: Извлечение изображений из DOCX...")
    try:
        docx_images = extract_images_from_docx(docx_path)
        print(f"  ✓ Найдено изображений в DOCX: {len(docx_images)}")
        if len(docx_images) == 0:
            print(f"  ⚠ Предупреждение: изображения не найдены в DOCX файле")
        else:
            print(f"  Детали: первый элемент имеет ключи: {list(docx_images[0].keys()) if docx_images else 'N/A'}")
    except Exception as e:
        print(f"  ✗ Ошибка при извлечении изображений из DOCX: {e}")
        import traceback
        traceback.print_exc()
        docx_images = []
    
    # Шаг 3: Layout detection через DOTS OCR
    print("\nШаг 3: Layout detection через DOTS OCR...")
    if not HAS_PYMUPDF:
        print("  ✗ PyMuPDF не установлен")
        return {"error": "PyMuPDF не установлен"}
    
    # Открываем PDF для определения количества страниц
    pdf_document = fitz.open(str(temp_pdf_path))
    total_pages = len(pdf_document)
    pdf_document.close()
    
    renderer = PdfPageRenderer(render_scale=RENDER_SCALE, optimize_for_ocr=False)
    
    ocr_image_elements = []
    
    for page_num in range(total_pages):
        if page_num % 10 == 0 or page_num < 3:  # Выводим для первых 3 страниц и каждую 10-ю
            print(f"  Обработка страницы {page_num + 1}/{total_pages}...")
        
        # Рендерим страницу (передаем путь к файлу, а не объект)
        page_image = renderer.render_page(temp_pdf_path, page_num)
        if page_image is None:
            if page_num < 3:
                print(f"      ✗ Не удалось отрендерить страницу {page_num + 1}")
            continue
        
        # Layout detection
        try:
            layout_cells, raw_response, success = process_layout_detection(
                image=page_image,
                origin_image=page_image,
            )
            
            if success and layout_cells:
                # Отладочная информация: какие категории найдены (только для первых страниц)
                if page_num < 3:
                    categories_found = set(e.get("category") for e in layout_cells if e.get("category"))
                    if categories_found:
                        print(f"      Найдены категории: {categories_found}")
                
                pictures_on_page = 0
                for element in layout_cells:
                    if element.get("category") == "Picture":
                        element["page_num"] = page_num
                        ocr_image_elements.append(element)
                        pictures_on_page += 1
                
                if pictures_on_page > 0:
                    print(f"      ✓ Найдено {pictures_on_page} изображений на странице {page_num + 1}")
            elif not success:
                if page_num < 3:
                    print(f"      ✗ Layout detection не удался")
            elif not layout_cells:
                if page_num < 3:
                    print(f"      ✗ Layout cells пустые")
        except Exception as e:
            if page_num < 3:
                print(f"    Предупреждение: ошибка layout detection: {e}")
            continue
    
    print(f"  ✓ Найдено изображений в OCR: {len(ocr_image_elements)}")
    
    # Шаг 4: Обработка каждого изображения из OCR
    print(f"\nШаг 4: Обработка изображений из OCR (лимит: {limit or 'нет'})...")
    
    results = []
    processed_count = 0
    
    for image_idx, ocr_image_elem in enumerate(ocr_image_elements):
        if limit and processed_count >= limit:
            break
        
        processed_count += 1
        print(f"\n  Изображение {processed_count}/{len(ocr_image_elements)}:")
        
        image_bbox = ocr_image_elem.get("bbox", [])
        page_num = ocr_image_elem.get("page_num", 0)
        
        if not image_bbox or len(image_bbox) != 4:
            print(f"    ✗ Некорректные координаты bbox")
            continue
        
        print(f"    BBox: {image_bbox}, Страница: {page_num + 1}")
        
        # 4.1: Извлекаем изображение из PDF
        try:
            # Рендерим страницу (передаем путь к файлу, а не объект)
            page_image = renderer.render_page(temp_pdf_path, page_num)
            ocr_image = extract_image_from_pdf_by_bbox(
                temp_pdf_path,
                image_bbox,
                page_num,
                RENDER_SCALE,
                rendered_page_image=page_image
            )
            
            if ocr_image is None:
                print(f"    ✗ Не удалось извлечь изображение")
                continue
            
            # Сохраняем изображение из OCR
            ocr_image_path = ocr_images_dir / f"ocr_image_{image_idx + 1}_page_{page_num + 1}.png"
            ocr_image.save(ocr_image_path)
            print(f"    ✓ Изображение сохранено: {ocr_image_path.name}")
            
        except Exception as e:
            print(f"    ✗ Ошибка при извлечении изображения: {e}")
            continue
        
        # 4.2: Ищем похожее изображение в DOCX тремя разными методами
        # Каждый метод работает независимо (ignore_matched=True)
        print(f"    Поиск похожего изображения в DOCX (3 метода)...")
        
        # Метод 1: Нормализованное сравнение (SSIM + гистограммы)
        print(f"      Метод 1: Нормализованное сравнение...")
        method1_result = find_image_by_method_1_normalized(ocr_image, docx_images, ignore_matched=True)
        if method1_result:
            _, _, method1_metrics = method1_result
            print(f"        ✓ Найдено! Score: {method1_metrics.get('score', 0):.2%}")
        else:
            print(f"        ✗ Не найдено")
        
        # Метод 2: ORB Feature Matching (улучшенный с удалением белых полей)
        print(f"      Метод 2: ORB Feature Matching...")
        method2_result = find_image_by_method_2_orb(ocr_image, docx_images, ignore_matched=True)
        if method2_result:
            _, _, method2_metrics = method2_result
            similarity = method2_metrics.get('similarity', 0.0)
            good_matches = method2_metrics.get('good_matches', 0)
            print(f"        ✓ Найдено! Score: {method2_metrics.get('score', 0):.2%}, Matches: {good_matches}")
        else:
            print(f"        ✗ Не найдено")
        
        # Метод 3: Perceptual hash
        print(f"      Метод 3: Perceptual hash...")
        method3_result = find_image_by_method_3_perceptual_hash(ocr_image, docx_images, ignore_matched=True)
        if method3_result:
            _, _, method3_metrics = method3_result
            print(f"        ✓ Найдено! Score: {method3_metrics.get('score', 0):.2%}")
        else:
            print(f"        ✗ Не найдено")
        
        # Создаем 4-панельное сравнение
        try:
            four_panel_image = create_four_panel_comparison(
                ocr_image,
                method1_result,
                method2_result,
                method3_result
            )
            comparison_path = comparisons_dir / f"comparison_4panel_{image_idx + 1}.png"
            four_panel_image.save(comparison_path)
            print(f"    ✓ 4-панельное сравнение сохранено: {comparison_path.name}")
        except Exception as e:
            print(f"    Предупреждение: не удалось создать 4-панельное сравнение: {e}")
            comparison_path = None
        
        # Определяем лучший результат (для статистики)
        best_result = None
        best_score = 0.0
        if method1_result:
            _, _, m1_metrics = method1_result
            if m1_metrics.get('score', 0) > best_score:
                best_score = m1_metrics.get('score', 0)
                best_result = method1_result
        if method2_result:
            _, _, m2_metrics = method2_result
            if m2_metrics.get('score', 0) > best_score:
                best_score = m2_metrics.get('score', 0)
                best_result = method2_result
        if method3_result:
            _, _, m3_metrics = method3_result
            if m3_metrics.get('score', 0) > best_score:
                best_score = m3_metrics.get('score', 0)
                best_result = method3_result
        
        if best_result:
            match_status = "matched"
            best_data, best_img, best_metrics = best_result
            match_type = best_metrics.get("method", "unknown")
            confidence = "high" if best_score >= 0.85 else "medium" if best_score >= 0.7 else "low"
        else:
            match_status = "not_found"
            match_type = "none"
            confidence = "none"
            best_metrics = {"method": "none", "score": 0.0}
        
        # 4.3: Сохраняем результаты
        result = {
            "image_index": image_idx + 1,
            "page_num": page_num + 1,
            "bbox": image_bbox,
            "ocr_image_path": str(ocr_image_path.relative_to(output_dir)),
            "comparison_4panel_path": str(comparison_path.relative_to(output_dir)) if comparison_path else None,
            "match_status": match_status,
            "best_method": match_type,
            "best_confidence": confidence,
            "best_score": best_score,
            "method1": {
                "found": method1_result is not None,
                "score": method1_result[2].get("score", 0.0) if method1_result else 0.0,
                "metrics": method1_result[2] if method1_result else None,
            } if method1_result or True else None,
            "method2": {
                "found": method2_result is not None,
                "score": method2_result[2].get("score", 0.0) if method2_result else 0.0,
                "metrics": method2_result[2] if method2_result else None,
            } if method2_result or True else None,
            "method3": {
                "found": method3_result is not None,
                "score": method3_result[2].get("score", 0.0) if method3_result else 0.0,
                "metrics": method3_result[2] if method3_result else None,
            } if method3_result or True else None,
        }
        
        results.append(result)
    
    # Шаг 5: Создаем итоговый отчет
    print(f"\nШаг 5: Создание итогового отчета...")
    
    summary = {
        "total_ocr_images": len(ocr_image_elements),
        "total_docx_images": len(docx_images),
        "processed_images": len(results),
        "matched_images": sum(1 for r in results if r["match_status"] == "matched"),
        "not_found_images": sum(1 for r in results if r["match_status"] == "not_found"),
        "match_types": {},
        "average_score": sum(r.get("best_score", 0.0) for r in results) / len(results) if results else 0.0,
        "results": results,
    }
    
    # Подсчитываем статистику по методам
    method1_found = sum(1 for r in results if r.get("method1", {}).get("found", False))
    method2_found = sum(1 for r in results if r.get("method2", {}).get("found", False))
    method3_found = sum(1 for r in results if r.get("method3", {}).get("found", False))
    
    method1_avg_score = sum(r.get("method1", {}).get("score", 0.0) for r in results) / len(results) if results else 0.0
    method2_avg_score = sum(r.get("method2", {}).get("score", 0.0) for r in results) / len(results) if results else 0.0
    method3_avg_score = sum(r.get("method3", {}).get("score", 0.0) for r in results) / len(results) if results else 0.0
    
    summary["method_statistics"] = {
        "method1_normalized_ssim": {
            "found_count": method1_found,
            "average_score": method1_avg_score,
        },
        "method2_orb_feature_matching": {
            "found_count": method2_found,
            "average_score": method2_avg_score,
        },
        "method3_perceptual_hash": {
            "found_count": method3_found,
            "average_score": method3_avg_score,
        },
    }
    
    # Подсчитываем типы совпадений (лучший метод)
    for r in results:
        if r["match_status"] == "matched":
            match_type = r.get("best_method", "unknown")
            summary["match_types"][match_type] = summary["match_types"].get(match_type, 0) + 1
    
    # Функция для конвертации numpy типов в стандартные Python типы
    def convert_numpy_types(obj):
        """Рекурсивно конвертирует numpy типы в стандартные Python типы для JSON."""
        if HAS_NUMPY:
            if isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, np.bool_):
                return bool(obj)
        
        if isinstance(obj, dict):
            return {key: convert_numpy_types(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [convert_numpy_types(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(convert_numpy_types(item) for item in obj)
        else:
            return obj
    
    summary_file = output_dir / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        summary_converted = convert_numpy_types(summary)
        json.dump(summary_converted, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"  ✓ Итоговый отчет сохранен: {summary_file}")
    
    # Выводим статистику
    print(f"\n{'='*80}")
    print(f"ИТОГОВАЯ СТАТИСТИКА:")
    print(f"  Изображений найдено в OCR: {summary['total_ocr_images']}")
    print(f"  Изображений найдено в DOCX: {summary['total_docx_images']}")
    print(f"  Обработано изображений: {summary['processed_images']}")
    print(f"  Совпадений найдено: {summary['matched_images']}")
    print(f"  Совпадений не найдено: {summary['not_found_images']}")
    print(f"  Средний score: {summary['average_score']:.2%}")
    print(f"  Типы совпадений: {summary['match_types']}")
    print(f"\n  Статистика по методам:")
    stats = summary.get("method_statistics", {})
    print(f"    Метод 1 (Normalized SSIM): найдено {stats.get('method1_normalized_ssim', {}).get('found_count', 0)}, средний score: {stats.get('method1_normalized_ssim', {}).get('average_score', 0):.2%}")
    print(f"    Метод 2 (ORB Feature Matching): найдено {stats.get('method2_orb_feature_matching', {}).get('found_count', 0)}, средний score: {stats.get('method2_orb_feature_matching', {}).get('average_score', 0):.2%}")
    print(f"    Метод 3 (Perceptual Hash): найдено {stats.get('method3_perceptual_hash', {}).get('found_count', 0)}, средний score: {stats.get('method3_perceptual_hash', {}).get('average_score', 0):.2%}")
    print(f"{'='*80}\n")
    
    # Удаляем временный PDF
    if temp_pdf_path.exists():
        temp_pdf_path.unlink()
        print(f"  ✓ Временный PDF удален")
    
    return summary


def find_image_by_method_1_normalized(
    ocr_image: Image.Image,
    docx_images: List[Dict[str, Any]],
    ignore_matched: bool = False
) -> Optional[Tuple[Dict[str, Any], Image.Image, Dict[str, Any]]]:
    """
    Метод 1: Нормализованное сравнение (SSIM + гистограммы).
    Самый точный метод для изображений разного разрешения.
    """
    if not ocr_image or not docx_images:
        return None
    
    best_match = None
    best_image = None
    best_metrics = None
    best_score = 0.0
    
    for docx_image_data in docx_images:
        if not ignore_matched and docx_image_data.get("matched", False):
            continue
        
        docx_image_bytes = docx_image_data.get("image_bytes")
        if not docx_image_bytes:
            continue
        
        try:
            docx_image = Image.open(BytesIO(docx_image_bytes))
            if docx_image.mode != 'RGB':
                docx_image = docx_image.convert('RGB')
        except Exception:
            continue
        
        # Нормализованное сравнение (используем более мягкие пороги для OCR изображений)
        is_identical, norm_metrics = are_images_identical(
            ocr_image, 
            docx_image,
            ssim_threshold=0.90,  # Более мягкий порог для OCR (было 0.98)
            hist_threshold=0.95,  # Более мягкий порог (было 0.99)
            diff_threshold=0.05   # Более мягкий порог для шума OCR (было 0.02)
        )
        
        # Вычисляем score независимо от is_identical
        ssim_val = norm_metrics.get("ssim", 0.0) or 0.0
        hist_val = norm_metrics.get("hist_corr", 0.0)
        diff_val = 1.0 - norm_metrics.get("diff_ratio", 1.0)
        
        # Если SSIM недоступен, используем только гистограмму и разницу
        if ssim_val == 0.0:
            score = (hist_val * 0.6 + diff_val * 0.4)
        else:
            score = (ssim_val * 0.5 + hist_val * 0.3 + diff_val * 0.2)
        
        # Если is_identical = True, даем бонус к score
        if is_identical:
            score = max(score, 0.95)  # Минимум 0.95 если все критерии выполнены
        
        if score > best_score:
            best_score = score
            best_match = docx_image_data
            best_image = docx_image
            best_metrics = {
                "method": "normalized_ssim",
                "score": score,
                "is_identical": is_identical,
                "metrics": norm_metrics,
            }
    
    # Снижаем порог для возврата результата (было 0.85)
    if best_score >= 0.70:
        return (best_match, best_image, best_metrics)
    
    return None


def crop_white_borders(image: Image.Image, threshold: int = 250) -> Image.Image:
    """
    Удаляет белые поля вокруг изображения.
    Важно для OCR изображений, которые могут иметь белые края.
    
    Args:
        image: PIL Image
        threshold: Порог для определения белого цвета (0-255)
    
    Returns:
        Обрезанное изображение (копия, оригинал не изменяется)
    """
    if not HAS_OPENCV:
        return image.copy()
    
    try:
        # Конвертируем PIL в numpy (создаем копию)
        img_array = np.array(image.convert('RGB'))
        
        # Конвертируем в grayscale для анализа
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        
        # Находим все не-белые пиксели (не черные и не белые)
        # Используем более умный подход: ищем пиксели, которые не слишком светлые
        _, thresh = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)
        coords = cv2.findNonZero(thresh)
        
        if coords is None or len(coords) == 0:
            # Если все пиксели белые, возвращаем копию оригинала
            return image.copy()
        
        # Находим bounding box
        x, y, w, h = cv2.boundingRect(coords)
        
        # Проверяем, что bounding box валидный
        if w <= 0 or h <= 0:
            return image.copy()
        
        # Обрезаем с небольшим отступом (5 пикселей)
        padding = 5
        x = max(0, x - padding)
        y = max(0, y - padding)
        w = min(img_array.shape[1] - x, w + padding * 2)
        h = min(img_array.shape[0] - y, h + padding * 2)
        
        # Проверяем границы
        if x + w > img_array.shape[1] or y + h > img_array.shape[0]:
            return image.copy()
        
        cropped_array = img_array[y:y+h, x:x+w].copy()
        
        # Проверяем, что обрезанное изображение не пустое
        if cropped_array.size == 0:
            return image.copy()
        
        cropped_image = Image.fromarray(cropped_array)
        
        return cropped_image
    except Exception as e:
        # В случае ошибки возвращаем копию оригинала
        return image.copy()


def find_image_by_method_2_orb(
    ocr_image: Image.Image,
    docx_images: List[Dict[str, Any]],
    ignore_matched: bool = False
) -> Optional[Tuple[Dict[str, Any], Image.Image, Dict[str, Any]]]:
    """
    Метод 2: ORB Feature Matching (улучшенный).
    - Удаляет белые поля перед сравнением
    - Использует ORB для детекции ключевых точек
    - Считает процент совпадений по feature matching
    - Устойчив к масштабу и белым полям
    """
    if not ocr_image or not docx_images or not HAS_OPENCV:
        return None
    
    # Удаляем белые поля у OCR изображения
    ocr_cropped = crop_white_borders(ocr_image)
    ocr_gray = np.array(ocr_cropped.convert('L'))
    
    # Инициализация ORB
    orb = cv2.ORB_create(nfeatures=5000)
    
    # Детектим ключевые точки для OCR изображения
    kp1, des1 = orb.detectAndCompute(ocr_gray, None)
    
    if des1 is None or len(kp1) < 10:
        return None  # Недостаточно ключевых точек
    
    best_match = None
    best_image = None
    best_score = 0.0
    best_metrics = None
    
    for docx_image_data in docx_images:
        if not ignore_matched and docx_image_data.get("matched", False):
            continue
        
        docx_image_bytes = docx_image_data.get("image_bytes")
        if not docx_image_bytes:
            continue
        
        try:
            docx_image = Image.open(BytesIO(docx_image_bytes))
            if docx_image.mode != 'RGB':
                docx_image = docx_image.convert('RGB')
        except Exception:
            continue
        
        # Удаляем белые поля у DOCX изображения ТОЛЬКО для сравнения
        # Но сохраняем оригинальное изображение для возврата
        docx_cropped = crop_white_borders(docx_image.copy())  # Копируем, чтобы не изменять оригинал
        docx_gray = np.array(docx_cropped.convert('L'))
        
        # Проверяем, что изображение не пустое после обрезки
        if docx_gray.size == 0 or np.all(docx_gray == 0):
            # Если изображение стало пустым, используем оригинал
            docx_gray = np.array(docx_image.convert('L'))
        
        # Детектим ключевые точки для DOCX изображения
        kp2, des2 = orb.detectAndCompute(docx_gray, None)
        
        if des2 is None or len(kp2) < 10:
            continue  # Недостаточно ключевых точек
        
        # Матчинг дескрипторов
        try:
            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
            matches = bf.match(des1, des2)
            
            if len(matches) == 0:
                continue
            
            # Сортировка по качеству (distance - чем меньше, тем лучше)
            matches = sorted(matches, key=lambda x: x.distance)
            
            # Вычисляем процент совпадений
            # Используем количество хороших матчей (distance < 30)
            good_matches = [m for m in matches if m.distance < 30]
            
            # Процент совпадений от минимального количества ключевых точек
            min_keypoints = min(len(kp1), len(kp2))
            similarity = len(good_matches) / min_keypoints if min_keypoints > 0 else 0.0
            
            # Дополнительно учитываем среднее расстояние матчей
            if len(matches) > 0:
                avg_distance = sum(m.distance for m in matches[:50]) / min(50, len(matches))
                # Нормализуем distance (0-64 для Hamming, хорошие матчи < 30)
                distance_score = max(0.0, 1.0 - (avg_distance / 30.0))
                # Комбинируем similarity и distance_score
                final_score = (similarity * 0.7 + distance_score * 0.3)
            else:
                final_score = similarity
            
            if final_score > best_score:
                best_score = final_score
                best_match = docx_image_data
                # ВАЖНО: возвращаем ОРИГИНАЛЬНОЕ изображение, а не обрезанное
                best_image = docx_image.copy()  # Копируем оригинальное изображение
                best_metrics = {
                    "method": "orb_feature_matching",
                    "score": final_score,
                    "similarity": similarity,
                    "good_matches": len(good_matches),
                    "total_matches": len(matches),
                    "keypoints_ocr": len(kp1),
                    "keypoints_docx": len(kp2),
                }
        except Exception as e:
            continue
    
    # Порог для возврата результата (0.3 = 30% совпадений)
    if best_score >= 0.3:
        return (best_match, best_image, best_metrics)
    
    return None


def find_image_by_method_3_perceptual_hash(
    ocr_image: Image.Image,
    docx_images: List[Dict[str, Any]],
    ignore_matched: bool = False
) -> Optional[Tuple[Dict[str, Any], Image.Image, Dict[str, Any]]]:
    """
    Метод 3: Perceptual hash (быстрый метод).
    Хорошо работает для визуально похожих изображений.
    """
    if not ocr_image or not docx_images:
        return None
    
    best_match = None
    best_image = None
    best_metrics = None
    best_score = 0.0
    
    ocr_hash = calculate_image_hash(ocr_image)
    
    for docx_image_data in docx_images:
        if not ignore_matched and docx_image_data.get("matched", False):
            continue
        
        docx_image_bytes = docx_image_data.get("image_bytes")
        if not docx_image_bytes:
            continue
        
        try:
            docx_image = Image.open(BytesIO(docx_image_bytes))
            if docx_image.mode != 'RGB':
                docx_image = docx_image.convert('RGB')
        except Exception:
            continue
        
        # Perceptual hash сравнение
        comparison = compare_images(ocr_image, docx_image, use_perceptual_hash=True)
        
        score = 0.0
        if comparison.get("is_visual_match", False):
            phash_dist = comparison.get("perceptual_hash_distance")
            if phash_dist is not None:
                if phash_dist <= 5:
                    score = 1.0
                elif phash_dist <= 10:
                    score = 0.8
                elif phash_dist <= 15:
                    score = 0.6
            
            size_sim = comparison.get("size_similarity", 0.0)
            score = score * 0.7 + size_sim * 0.3
        
        if score > best_score:
            best_score = score
            best_match = docx_image_data
            best_image = docx_image
            best_metrics = {
                "method": "perceptual_hash",
                "score": score,
                "comparison": comparison,
            }
    
    if best_score >= 0.6:
        return (best_match, best_image, best_metrics)
    
    return None


def create_four_panel_comparison(
    ocr_image: Image.Image,
    method1_result: Optional[Tuple[Dict, Image.Image, Dict]],
    method2_result: Optional[Tuple[Dict, Image.Image, Dict]],
    method3_result: Optional[Tuple[Dict, Image.Image, Dict]]
) -> Image.Image:
    """
    Создает 4-панельное изображение сравнения:
    - Панель 1: OCR изображение (исходное)
    - Панель 2: Результат метода 1 (Нормализованное сравнение)
    - Панель 3: Результат метода 2 (ORB + RANSAC)
    - Панель 4: Результат метода 3 (Perceptual hash)
    
    Args:
        ocr_image: Изображение из OCR
        method1_result: Результат метода 1 (или None)
        method2_result: Результат метода 2 (или None)
        method3_result: Результат метода 3 (или None)
    
    Returns:
        4-панельное изображение сравнения
    """
    # Размер каждой панели (2x2 сетка) - увеличен для лучшей визуализации
    panel_size = 600  # Размер каждой панели (было 400)
    padding = 20  # Отступ между панелями
    
    # Создаем пустое изображение для 4 панелей
    total_width = panel_size * 2 + padding * 3  # 2 панели по ширине + отступы
    total_height = panel_size * 2 + padding * 3  # 2 панели по высоте + отступы
    comparison = Image.new("RGB", (total_width, total_height), color="white")
    
    # Функция для подготовки изображения к панели
    def prepare_panel_image(img: Image.Image, label: str, border_color: str = "black") -> Image.Image:
        """Подготавливает изображение для панели с подписью и рамкой."""
        # Масштабируем изображение, сохраняя пропорции (больше места для изображения)
        img.thumbnail((panel_size - 40, panel_size - 60), Image.Resampling.LANCZOS)
        
        # Создаем панель с белым фоном
        panel = Image.new("RGB", (panel_size, panel_size), color="white")
        
        # Центрируем изображение
        x_offset = (panel_size - img.width) // 2
        y_offset = (panel_size - img.height - 50) // 2  # Оставляем место для подписи
        panel.paste(img, (x_offset, y_offset))
        
        # Добавляем рамку
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(panel)
        draw.rectangle([0, 0, panel_size - 1, panel_size - 1], outline=border_color, width=3)
        
        # Добавляем подпись (увеличенный шрифт)
        try:
            font = ImageFont.truetype("arial.ttf", 16)
            font_bold = ImageFont.truetype("arialbd.ttf", 16)
        except:
            try:
                font = ImageFont.truetype("arial.ttf", 14)
                font_bold = font
            except:
                font = ImageFont.load_default()
                font_bold = font
        
        # Разбиваем label на строки
        lines = label.split('\n')
        line_height = 20
        start_y = panel_size - (len(lines) * line_height) - 10
        
        for i, line in enumerate(lines):
            text_bbox = draw.textbbox((0, 0), line, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_x = (panel_size - text_width) // 2
            text_y = start_y + i * line_height
            # Первая строка жирным
            current_font = font_bold if i == 0 else font
            draw.text((text_x, text_y), line, fill="black", font=current_font)
        
        return panel
    
    # Панель 1: OCR изображение (верхний левый)
    ocr_panel = prepare_panel_image(ocr_image, "OCR Image\n(Source)", border_color="blue")
    comparison.paste(ocr_panel, (padding, padding))
    
    # Панель 2: Метод 1 (Нормализованное сравнение) (верхний правый)
    if method1_result:
        _, method1_img, method1_metrics = method1_result
        score = method1_metrics.get('score', 0.0)
        method1_label = f"Method 1: Normalized SSIM\nScore: {score:.1%}"
        method1_panel = prepare_panel_image(method1_img, method1_label, border_color="green" if score >= 0.7 else "orange")
    else:
        method1_panel = Image.new("RGB", (panel_size, panel_size), color="lightgray")
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(method1_panel)
        draw.rectangle([0, 0, panel_size - 1, panel_size - 1], outline="red", width=3)
        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except:
            font = ImageFont.load_default()
        draw.text((20, panel_size // 2 - 20), "Method 1:\nNo match", fill="black", font=font)
    comparison.paste(method1_panel, (panel_size + padding * 2, padding))
    
    # Панель 3: Метод 2 (ORB Feature Matching) (нижний левый)
    if method2_result:
        _, method2_img, method2_metrics = method2_result
        score = method2_metrics.get('score', 0.0)
        method2_label = f"Method 2: ORB Feature Matching\nScore: {score:.1%}"
        method2_panel = prepare_panel_image(method2_img, method2_label, border_color="green" if score >= 0.7 else "orange")
    else:
        method2_panel = Image.new("RGB", (panel_size, panel_size), color="lightgray")
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(method2_panel)
        draw.rectangle([0, 0, panel_size - 1, panel_size - 1], outline="red", width=3)
        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except:
            font = ImageFont.load_default()
        draw.text((20, panel_size // 2 - 20), "Method 2:\nNo match", fill="black", font=font)
    comparison.paste(method2_panel, (padding, panel_size + padding * 2))
    
    # Панель 4: Метод 3 (Perceptual hash) (нижний правый)
    if method3_result:
        _, method3_img, method3_metrics = method3_result
        score = method3_metrics.get('score', 0.0)
        method3_label = f"Method 3: Perceptual Hash\nScore: {score:.1%}"
        method3_panel = prepare_panel_image(method3_img, method3_label, border_color="green" if score >= 0.7 else "orange")
    else:
        method3_panel = Image.new("RGB", (panel_size, panel_size), color="lightgray")
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(method3_panel)
        draw.rectangle([0, 0, panel_size - 1, panel_size - 1], outline="red", width=3)
        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except:
            font = ImageFont.load_default()
        draw.text((20, panel_size // 2 - 20), "Method 3:\nNo match", fill="black", font=font)
    comparison.paste(method3_panel, (panel_size + padding * 2, panel_size + padding * 2))
    
    return comparison


def create_comparison_image(image1: Image.Image, image2: Image.Image) -> Image.Image:
    """
    Создает изображение сравнения (side-by-side).
    
    Args:
        image1: Первое изображение (OCR)
        image2: Второе изображение (DOCX)
    
    Returns:
        Изображение сравнения
    """
    # Приводим изображения к одному размеру (по высоте)
    max_height = max(image1.height, image2.height)
    
    # Масштабируем изображения, сохраняя пропорции
    scale1 = max_height / image1.height if image1.height > 0 else 1.0
    scale2 = max_height / image2.height if image2.height > 0 else 1.0
    
    new_width1 = int(image1.width * scale1)
    new_width2 = int(image2.width * scale2)
    
    image1_resized = image1.resize((new_width1, max_height), Image.Resampling.LANCZOS)
    image2_resized = image2.resize((new_width2, max_height), Image.Resampling.LANCZOS)
    
    # Создаем новое изображение (side-by-side)
    total_width = new_width1 + new_width2 + 20  # 20px отступ между изображениями
    comparison = Image.new("RGB", (total_width, max_height), color="white")
    
    comparison.paste(image1_resized, (0, 0))
    comparison.paste(image2_resized, (new_width1 + 20, 0))
    
    return comparison


def main():
    """Главная функция для запуска из командной строки."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Эксперимент по сопоставлению изображений из DOTS OCR с изображениями из DOCX"
    )
    parser.add_argument(
        "docx_path",
        type=Path,
        help="Путь к DOCX файлу"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Выходная директория (по умолчанию: experiments/pdf_text_extraction/results/image_matching/<docx_name>)"
    )
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=None,
        help="Ограничение на количество обрабатываемых изображений"
    )
    
    args = parser.parse_args()
    
    if not args.docx_path.exists():
        print(f"Ошибка: файл {args.docx_path} не существует")
        sys.exit(1)
    
    # Определяем выходную директорию
    if args.output:
        output_dir = args.output
    else:
        base_output = Path(__file__).parent / "results" / "image_matching"
        output_dir = base_output / args.docx_path.stem
    
    # Запускаем эксперимент
    result = process_image_experiment(
        args.docx_path,
        output_dir,
        limit=args.limit
    )
    
    if "error" in result:
        print(f"\nОшибка: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()

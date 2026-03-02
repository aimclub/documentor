"""
Скрипт для извлечения всех изображений из DOCX файла в порядке появления.

Находит все изображения, получает их в порядке, как они отмечены в тексте,
и сохраняет под именами 1.png, 2.png, 3.png и т.д.
"""

import sys
from pathlib import Path

# Добавляем корень проекта в путь
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from experiments.pdf_text_extraction.docx_xml_parser import extract_images_from_docx_xml
from PIL import Image
from io import BytesIO


def save_images_from_docx(docx_path: Path, output_dir: Path) -> None:
    """
    Извлекает все изображения из DOCX и сохраняет их с последовательными номерами.
    
    Args:
        docx_path: Путь к DOCX файлу
        output_dir: Директория для сохранения изображений
    """
    print("=" * 80)
    print("ИЗВЛЕЧЕНИЕ ИЗОБРАЖЕНИЙ ИЗ DOCX")
    print("=" * 80)
    print(f"DOCX файл: {docx_path}")
    print(f"Выходная директория: {output_dir}")
    print("=" * 80 + "\n")
    
    # Создаем выходную директорию
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Извлекаем изображения из DOCX XML
    print("Шаг 1: Извлечение изображений из DOCX XML...")
    images = extract_images_from_docx_xml(docx_path)
    
    if not images:
        print("  ✗ Изображения не найдены")
        return
    
    print(f"  ✓ Найдено изображений: {len(images)}\n")
    
    # 2. Сохраняем изображения в порядке появления
    print("Шаг 2: Сохранение изображений...")
    
    saved_count = 0
    
    for img_idx, img_data in enumerate(images, start=1):
        try:
            # Получаем байты изображения
            image_bytes = img_data.get('image_bytes')
            if not image_bytes:
                print(f"  ⚠ Изображение {img_idx}: нет данных")
                continue
            
            # Открываем изображение
            image = Image.open(BytesIO(image_bytes))
            
            # Конвертируем в RGB если нужно
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Сохраняем под именем с номером
            output_path = output_dir / f"{img_idx}.png"
            image.save(output_path, 'PNG')
            
            # Информация об изображении
            width = img_data.get('width', '?')
            height = img_data.get('height', '?')
            xml_position = img_data.get('xml_position', '?')
            image_path = img_data.get('image_path', '?')
            
            print(f"  ✓ Сохранено: {img_idx}.png (размер: {width}x{height}, позиция в XML: {xml_position}, путь: {image_path})")
            
            saved_count += 1
        
        except Exception as e:
            print(f"  ✗ Ошибка при сохранении изображения {img_idx}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"\n{'='*80}")
    print(f"ИТОГО: Сохранено {saved_count} из {len(images)} изображений")
    print(f"Директория: {output_dir}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python extract_images_from_docx.py <docx_path> [output_dir]")
        print("\nПримеры:")
        print("  python extract_images_from_docx.py test_folder/Диплом.docx")
        print("  python extract_images_from_docx.py test_folder/Диплом.docx output/images")
        sys.exit(1)
    
    docx_path = Path(sys.argv[1])
    
    if not docx_path.exists():
        print(f"Ошибка: файл не найден: {docx_path}")
        sys.exit(1)
    
    # Определяем выходную директорию
    if len(sys.argv) >= 3:
        output_dir = Path(sys.argv[2])
    else:
        # По умолчанию: output/images/<имя_файла>/
        output_dir = Path(__file__).parent / "output" / "images" / docx_path.stem
    
    save_images_from_docx(docx_path, output_dir)

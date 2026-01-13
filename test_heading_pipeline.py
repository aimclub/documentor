"""
Тестовый скрипт для проверки пайплайна извлечения заголовков.
"""

from pathlib import Path
from heading_extraction_pipeline import process_docx_file, HeadingDetector
import json


def test_single_file(docx_path: Path):
    """Протестировать пайплайн на одном файле."""
    print(f"\n{'='*80}")
    print(f"Тестирование: {docx_path.name}")
    print(f"{'='*80}\n")
    
    try:
        # Обработка файла
        paragraphs, hierarchy, detector = process_docx_file(docx_path)
        
        # Статистика
        headings = [p for p in paragraphs if p.is_heading]
        content_headings = [p for p in headings if p.index >= detector.content_start_index]
        
        print(f"✅ Успешно обработано!")
        print(f"\n📊 Статистика:")
        print(f"  Всего параграфов: {len(paragraphs)}")
        print(f"  Начало основного текста: индекс {detector.content_start_index}")
        print(f"  Обнаружено заголовков всего: {len(headings)}")
        print(f"  Заголовков в основном тексте: {len(content_headings)}")
        
        # Вывод первых 5 заголовков
        print(f"\n📝 Первые 5 заголовков основного текста:\n")
        shown = 0
        for para in headings:
            if para.index >= detector.content_start_index and shown < 5:
                print(f"[Уровень {para.detected_level}] {para.text}")
                print(f"  Индекс: {para.index}, Оценка: {para.heading_score:.1f}")
                if para.numbering_text:
                    print(f"  Нумерация: {para.numbering_text}")
                print(f"  Причины: {', '.join(para.detection_reason[:3])}")
                print()
                shown += 1
        
        # Вывод иерархии (только первый уровень)
        print(f"\n🌲 Корневые заголовки иерархии:\n")
        for i, root in enumerate(hierarchy[:5], 1):
            children_count = len(root.children)
            print(f"{i}. [Уровень {root.level}] {root.text}")
            if children_count > 0:
                print(f"   └─ Подзаголовков: {children_count}")
        
        if len(hierarchy) > 5:
            print(f"\n   ... и еще {len(hierarchy) - 5} корневых заголовков")
        
        # Сохранение результата
        output_file = docx_path.with_suffix('.headings.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            result = {
                'file': str(docx_path),
                'total_paragraphs': len(paragraphs),
                'content_start_index': detector.content_start_index,
                'total_headings': len(headings),
                'content_headings': len(content_headings),
                'headings': [
                    {
                        'level': p.detected_level,
                        'text': p.text,
                        'index': p.index,
                        'score': p.heading_score,
                        'reasons': p.detection_reason,
                        'style': p.style_name,
                        'font_size': p.font_size,
                        'is_bold': p.is_bold,
                        'alignment': p.alignment,
                        'numbering': p.numbering_text,
                        'in_content': p.index >= detector.content_start_index
                    }
                    for p in headings
                ],
                'hierarchy': detector.export_to_dict(hierarchy)
            }
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 Результаты сохранены в: {output_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при обработке: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Основная функция для тестирования."""
    print("\n🚀 Тестирование пайплайна извлечения заголовков\n")
    
    # Ищем DOCX файлы в test_folder
    test_folder = Path("test_folder")
    
    if not test_folder.exists():
        print(f"❌ Папка {test_folder} не найдена")
        return
    
    docx_files = list(test_folder.glob("*.docx"))
    
    if not docx_files:
        print(f"❌ DOCX файлы не найдены в {test_folder}")
        return
    
    print(f"Найдено {len(docx_files)} DOCX файлов:\n")
    for i, f in enumerate(docx_files, 1):
        print(f"{i}. {f.name}")
    
    # Обрабатываем каждый файл
    success_count = 0
    for docx_file in docx_files:
        if test_single_file(docx_file):
            success_count += 1
    
    # Итоговая статистика
    print(f"\n{'='*80}")
    print(f"📈 Итоговая статистика:")
    print(f"  Обработано успешно: {success_count}/{len(docx_files)}")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()








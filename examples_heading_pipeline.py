"""
Примеры использования пайплайна извлечения заголовков.
"""

from pathlib import Path
from heading_extraction_pipeline import HeadingDetector, process_docx_file
import json


def example_1_basic_usage():
    """Пример 1: Базовое использование - обработка одного файла."""
    print("=" * 80)
    print("Пример 1: Базовое использование")
    print("=" * 80)
    
    # Путь к DOCX файлу
    docx_path = Path("test_folder/Диплом.docx")
    
    if not docx_path.exists():
        print(f"❌ Файл не найден: {docx_path}")
        return
    
    # Обработка файла
    paragraphs, hierarchy, detector = process_docx_file(docx_path)
    
    # Получение заголовков
    headings = [p for p in paragraphs if p.is_heading]
    
    print(f"\n✅ Обработано:")
    print(f"  - Параграфов: {len(paragraphs)}")
    print(f"  - Заголовков: {len(headings)}")
    print(f"  - Корневых узлов: {len(hierarchy)}")
    
    # Вывод первых 3 заголовков
    print(f"\nПервые 3 заголовка:")
    for para in headings[:3]:
        print(f"  [{para.detected_level}] {para.text}")


def example_2_hierarchy_navigation():
    """Пример 2: Навигация по иерархии заголовков."""
    print("\n" + "=" * 80)
    print("Пример 2: Навигация по иерархии")
    print("=" * 80)
    
    docx_path = Path("test_folder/Диплом.docx")
    
    if not docx_path.exists():
        print(f"❌ Файл не найден: {docx_path}")
        return
    
    _, hierarchy, _ = process_docx_file(docx_path)
    
    # Обход дерева заголовков
    def print_tree(nodes, level=0):
        for node in nodes:
            indent = "  " * level
            print(f"{indent}├─ {node.text}")
            if node.children:
                print_tree(node.children, level + 1)
    
    print("\nДерево заголовков:")
    print_tree(hierarchy)


def example_3_filtering_by_level():
    """Пример 3: Фильтрация заголовков по уровню."""
    print("\n" + "=" * 80)
    print("Пример 3: Фильтрация по уровню")
    print("=" * 80)
    
    docx_path = Path("test_folder/Отчёт ГОСТ.docx")
    
    if not docx_path.exists():
        print(f"❌ Файл не найден: {docx_path}")
        return
    
    paragraphs, _, detector = process_docx_file(docx_path)
    
    # Фильтрация по уровням
    level_1 = [p for p in paragraphs if p.is_heading and p.detected_level == 1]
    level_2 = [p for p in paragraphs if p.is_heading and p.detected_level == 2]
    level_3 = [p for p in paragraphs if p.is_heading and p.detected_level == 3]
    
    print(f"\nЗаголовки по уровням:")
    print(f"  Уровень 1: {len(level_1)}")
    print(f"  Уровень 2: {len(level_2)}")
    print(f"  Уровень 3: {len(level_3)}")
    
    print(f"\nЗаголовки уровня 1:")
    for para in level_1:
        print(f"  • {para.text}")


def example_4_extract_toc():
    """Пример 4: Извлечение оглавления (Table of Contents)."""
    print("\n" + "=" * 80)
    print("Пример 4: Генерация оглавления")
    print("=" * 80)
    
    docx_path = Path("test_folder/Диплом.docx")
    
    if not docx_path.exists():
        print(f"❌ Файл не найден: {docx_path}")
        return
    
    paragraphs, hierarchy, detector = process_docx_file(docx_path)
    
    # Генерация оглавления в текстовом виде
    def generate_toc(nodes, level=0):
        lines = []
        for node in nodes:
            indent = "  " * level
            # Извлекаем текст без номера
            text = node.text
            if node.numbering and text.startswith(node.numbering):
                text = text[len(node.numbering):].lstrip('. ')
            
            line = f"{indent}{node.numbering or ''} {text}"
            lines.append(line.strip())
            
            if node.children:
                lines.extend(generate_toc(node.children, level + 1))
        
        return lines
    
    toc = generate_toc(hierarchy)
    
    print("\nСгенерированное оглавление:")
    print("-" * 40)
    for line in toc:
        print(line)


def example_5_export_to_json():
    """Пример 5: Экспорт структуры в JSON."""
    print("\n" + "=" * 80)
    print("Пример 5: Экспорт в JSON")
    print("=" * 80)
    
    docx_path = Path("test_folder/Отчёт НИР Хаухия АВ.docx")
    
    if not docx_path.exists():
        print(f"❌ Файл не найден: {docx_path}")
        return
    
    paragraphs, hierarchy, detector = process_docx_file(docx_path)
    
    # Подготовка данных для экспорта
    headings = [p for p in paragraphs if p.is_heading and p.index >= detector.content_start_index]
    
    export_data = {
        'document': str(docx_path.name),
        'stats': {
            'total_paragraphs': len(paragraphs),
            'total_headings': len([p for p in paragraphs if p.is_heading]),
            'content_headings': len(headings),
            'content_start': detector.content_start_index
        },
        'headings': [
            {
                'level': h.detected_level,
                'text': h.text,
                'numbering': h.numbering_text,
                'index': h.index,
                'score': round(h.heading_score, 2)
            }
            for h in headings
        ],
        'hierarchy': detector.export_to_dict(hierarchy)
    }
    
    # Вывод в консоль (первые 50 строк)
    json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
    lines = json_str.split('\n')
    
    print("\nJSON экспорт (первые 30 строк):")
    print("-" * 40)
    for line in lines[:30]:
        print(line)
    if len(lines) > 30:
        print(f"... и еще {len(lines) - 30} строк")


def example_6_statistics():
    """Пример 6: Статистика по документу."""
    print("\n" + "=" * 80)
    print("Пример 6: Детальная статистика")
    print("=" * 80)
    
    docx_path = Path("test_folder/Диплом.docx")
    
    if not docx_path.exists():
        print(f"❌ Файл не найден: {docx_path}")
        return
    
    paragraphs, hierarchy, detector = process_docx_file(docx_path)
    
    headings = [p for p in paragraphs if p.is_heading]
    content_headings = [p for p in headings if p.index >= detector.content_start_index]
    
    # Статистика по уровням
    level_counts = {}
    for h in content_headings:
        level_counts[h.detected_level] = level_counts.get(h.detected_level, 0) + 1
    
    # Статистика по способу определения
    with_numbering = len([h for h in content_headings if h.has_numbering])
    with_style = len([h for h in content_headings if 'Heading' in h.style_name])
    
    # Средняя длина заголовков
    avg_length = sum(len(h.text) for h in content_headings) / len(content_headings) if content_headings else 0
    avg_words = sum(h.word_count for h in content_headings) / len(content_headings) if content_headings else 0
    
    print(f"\n📊 Статистика документа '{docx_path.name}':")
    print(f"\nОбщее:")
    print(f"  Всего параграфов: {len(paragraphs)}")
    print(f"  Заголовков в документе: {len(headings)}")
    print(f"  Заголовков в основном тексте: {len(content_headings)}")
    print(f"  Начало основного текста: индекс {detector.content_start_index}")
    
    print(f"\nРаспределение по уровням:")
    for level in sorted(level_counts.keys()):
        print(f"  Уровень {level}: {level_counts[level]} заголовков")
    
    print(f"\nСпособы определения:")
    print(f"  С нумерацией: {with_numbering} ({with_numbering/len(content_headings)*100:.1f}%)")
    print(f"  Со стилем Heading: {with_style} ({with_style/len(content_headings)*100:.1f}%)")
    
    print(f"\nХарактеристики заголовков:")
    print(f"  Средняя длина: {avg_length:.1f} символов")
    print(f"  Среднее количество слов: {avg_words:.1f}")
    
    print(f"\nКорневых узлов в иерархии: {len(hierarchy)}")
    
    # Глубина дерева
    def max_depth(nodes, current_depth=1):
        if not nodes:
            return current_depth - 1
        return max(max_depth(node.children, current_depth + 1) for node in nodes)
    
    depth = max_depth(hierarchy)
    print(f"Максимальная глубина вложенности: {depth}")


def example_7_custom_detector():
    """Пример 7: Использование HeadingDetector с настройкой."""
    print("\n" + "=" * 80)
    print("Пример 7: Настройка детектора")
    print("=" * 80)
    
    docx_path = Path("test_folder/Диплом.docx")
    
    if not docx_path.exists():
        print(f"❌ Файл не найден: {docx_path}")
        return
    
    # Создание детектора
    detector = HeadingDetector()
    
    # Извлечение параграфов
    paragraphs = detector.extract_paragraphs(docx_path)
    
    # Определение заголовков
    detector.detect_headings(paragraphs)
    
    # Построение иерархии
    hierarchy = detector.build_hierarchy(paragraphs)
    
    # Доступ к внутренней статистике
    print(f"\n📈 Внутренняя статистика детектора:")
    print(f"  Средний размер шрифта: {detector.avg_font_size:.1f}pt")
    print(f"  Максимальный размер шрифта: {detector.max_font_size:.1f}pt")
    print(f"  Средний отступ сверху: {detector.avg_space_before:.1f}pt")
    print(f"  Средний отступ снизу: {detector.avg_space_after:.1f}pt")
    print(f"  Начало основного текста: индекс {detector.content_start_index}")
    
    # Вывод заголовков с детальной информацией
    headings = [p for p in paragraphs if p.is_heading][:5]
    
    print(f"\nДетальная информация о первых 5 заголовках:")
    for i, h in enumerate(headings, 1):
        print(f"\n{i}. {h.text}")
        print(f"   Уровень: {h.detected_level}")
        print(f"   Оценка: {h.heading_score:.1f}")
        print(f"   Шрифт: {h.font_size}pt, жирный: {h.is_bold}, выравнивание: {h.alignment}")
        print(f"   Нумерация: {h.numbering_text or 'нет'}")
        print(f"   Стиль: {h.style_name}")


def main():
    """Запуск всех примеров."""
    examples = [
        example_1_basic_usage,
        example_2_hierarchy_navigation,
        example_3_filtering_by_level,
        example_4_extract_toc,
        example_5_export_to_json,
        example_6_statistics,
        example_7_custom_detector
    ]
    
    print("\n🚀 Примеры использования пайплайна извлечения заголовков\n")
    
    for example in examples:
        try:
            example()
        except Exception as e:
            print(f"\n❌ Ошибка в примере: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("✅ Все примеры выполнены")
    print("=" * 80)


if __name__ == "__main__":
    main()








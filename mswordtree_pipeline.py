"""
Пайплайн для анализа Word документов с помощью mswordtree.
Простой и понятный вывод структуры документа.
"""

from mswordtree import GetWordDocTree, ToString
from pathlib import Path
import json
from docx import Document


def analyze_with_python_docx(docx_path: Path):
    """Анализ документа через python-docx как fallback."""
    print(f"  Fallback: python-docx для {docx_path.name}")
    
    try:
        doc = Document(str(docx_path))
        headings = []
        
        for paragraph in doc.paragraphs:
            text = paragraph.text.strip()
            style_name = paragraph.style.name
            
            if style_name.startswith('Heading') and text:
                level = style_name.replace('Heading ', '')
                headings.append({
                    'content': text,
                    'level': f'Heading {level}',
                    'style': style_name
                })
        
        if headings:
            print(f"  python-docx: найдено {len(headings)} заголовков")
            return headings
        else:
            print(f"  python-docx: заголовки не найдены")
            return None
            
    except Exception as e:
        print(f"  python-docx: ошибка - {e}")
        return None


def analyze_document_with_mswordtree(docx_path: Path):
    """Анализ документа с помощью mswordtree."""
    print(f"Анализ документа: {docx_path.name}")
    print("-" * 50)
    
    try:
        # Получаем дерево документа
        print(f"Загружаем документ: {docx_path}")
        try:
            root = GetWordDocTree(str(docx_path))
            print(f"Документ загружен, тип root: {type(root)}")
        except Exception as e:
            print(f"Ошибка при загрузке документа: {e}")
            print("Пробуем через python-docx...")
            return analyze_with_python_docx(docx_path)
    
        # Проверяем, что root не None и имеет Items
        if not root:
            print("Документ не содержит элементов или поврежден (root is None)")
            return None
            
        if not hasattr(root, 'Items'):
            print("Документ не содержит элементов или поврежден (нет атрибута Items)")
            return None
            
        print(f"Найдено элементов: {len(root.Items) if root.Items else 0}")
        
        # Собираем статистику
        total_items = 0
        headings = []
        paragraphs = []
        tables = []
        other_items = []
        
        # Проходим по всем элементам
        for item in root.Items:
            total_items += 1
            
            try:
                item_type = getattr(item, 'Type', None)
                content = getattr(item, 'Content', None)
                
                # Безопасно обрабатываем content
                if content is None:
                    content = ""
                else:
                    content = str(content).strip()
                
                # Проверяем, что content не является DataFrame
                if hasattr(content, 'empty'):  # Это DataFrame
                    content = str(content)
                
                # Безопасно обрабатываем item_type
                if item_type is None:
                    item_type = "Unknown"
                else:
                    item_type = str(item_type)
                
                # mswordtree использует стили Word, а не типы
                if "Heading" in item_type or item_type in ["Heading 1", "Heading 2", "Heading 3"]:
                    headings.append({
                        'content': content,
                        'level': item_type,
                        'style': item_type
                    })
                elif item_type == "Table":
                    tables.append(content)
                elif item_type in ["Normal", "Body Text"] and content:
                    paragraphs.append(content)
                else:
                    other_items.append({
                        'type': item_type,
                        'content': content[:100] + "..." if len(content) > 100 else content
                    })
                    
            except Exception as e:
                # Если элемент вызывает ошибку, добавляем его в другие
                print(f"Ошибка при обработке элемента: {e}")
                try:
                    item_type = str(item.Type) if hasattr(item, 'Type') and item.Type is not None else "Unknown"
                    content = str(item.Content) if hasattr(item, 'Content') and item.Content is not None else ""
                except Exception as e2:
                    print(f"Дополнительная ошибка: {e2}")
                    item_type = "Error"
                    content = f"Ошибка обработки элемента: {e}"
                
                other_items.append({
                    'type': item_type,
                    'content': content[:100] + "..." if len(content) > 100 else content
                })
        
        # Выводим статистику
        print(f"Всего элементов: {total_items}")
        print(f"Заголовков: {len(headings)}")
        print(f"Параграфов: {len(paragraphs)}")
        print(f"Таблиц: {len(tables)}")
        print(f"Других элементов: {len(other_items)}")
        print()
        
        # Показываем заголовки
        if headings:
            print("ЗАГОЛОВКИ:")
            print("-" * 50)
            for i, h in enumerate(headings, 1):
                level = h['level']
                content = h['content']
                # Определяем уровень по стилю
                if "Heading 1" in level:
                    prefix = "1."
                elif "Heading 2" in level:
                    prefix = "2."
                elif "Heading 3" in level:
                    prefix = "3."
                else:
                    prefix = "•"
                print(f"{i:2d}. {prefix} {content}")
        
        # Показываем первые несколько параграфов
        if paragraphs:
            print(f"\nПАРАГРАФЫ (первые 5 из {len(paragraphs)}):")
            print("-" * 30)
            for i, p in enumerate(paragraphs[:5], 1):
                preview = p[:80] + "..." if len(p) > 80 else p
                print(f"{i}. {preview}")
        
        # Показываем таблицы
        if tables:
            print(f"\nТАБЛИЦЫ ({len(tables)} шт.):")
            print("-" * 30)
            for i, t in enumerate(tables, 1):
                preview = t[:60] + "..." if len(t) > 60 else t
                print(f"{i}. {preview}")
        
        # Показываем другие элементы
        if other_items:
            print(f"\nДРУГИЕ ЭЛЕМЕНТЫ ({len(other_items)} шт.):")
            print("-" * 30)
            for i, item in enumerate(other_items[:10], 1):  # Показываем первые 10
                print(f"{i}. [{item['type']}] {item['content']}")
        
        # Получаем JSON представление
        try:
            json_data = ToString([root])
            # Сохраняем в файл
            output_file = docx_path.with_suffix('.mswordtree.json')
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(str(json_data))
            print(f"\nПолная структура сохранена в: {output_file}")
        except Exception as e:
            print(f"Ошибка при сохранении JSON: {e}")
        
        return {
            'total_items': total_items,
            'headings': headings,
            'paragraphs': paragraphs,
            'tables': tables,
            'other_items': other_items
        }
        
    except Exception as e:
        print(f"ОШИБКА: {e}")
        return None


def process_all_documents():
    """Обработать все документы в папке test_folder."""
    test_folder = Path("test_folder")
    
    if not test_folder.exists():
        print("Папка test_folder не найдена")
        return
    
    # Находим все docx файлы
    docx_files = list(test_folder.glob("*.docx"))
    
    if not docx_files:
        print("DOCX файлы не найдены в папке test_folder")
        return
    
    print(f"Найдено файлов для обработки: {len(docx_files)}")
    print("=" * 60)
    
    results = {}
    
    for i, docx_file in enumerate(docx_files, 1):
        print(f"\n[{i}/{len(docx_files)}] Обработка файла: {docx_file.name}")
        print("=" * 60)
        
        try:
            # Анализируем документ
            result = analyze_document_with_mswordtree(docx_file)
            
            if result:
                results[docx_file.name] = result
            
        except Exception as e:
            print(f"ОШИБКА при обработке {docx_file.name}: {e}")
            continue
        
        print("\n" + "=" * 60)
    
        # Итоговая статистика
        print(f"\nИТОГОВАЯ СТАТИСТИКА:")
        print("=" * 60)
        print(f"Обработано файлов: {len(results)}")
        
        total_items = sum(r.get('total_items', 0) for r in results.values() if isinstance(r, dict))
        total_headings = sum(len(r.get('headings', [])) for r in results.values() if isinstance(r, dict))
        total_paragraphs = sum(len(r.get('paragraphs', [])) for r in results.values() if isinstance(r, dict))
        total_tables = sum(len(r.get('tables', [])) for r in results.values() if isinstance(r, dict))
    
    print(f"Всего элементов: {total_items}")
    print(f"Всего заголовков: {total_headings}")
    print(f"Всего параграфов: {total_paragraphs}")
    print(f"Всего таблиц: {total_tables}")
    
    # Сохраняем сводный отчет
    summary_file = test_folder / "mswordtree_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\nСводный отчет сохранен в: {summary_file}")


if __name__ == "__main__":
    # Обрабатываем все файлы
    process_all_documents()

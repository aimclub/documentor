#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Принудительный парсинг проблемных файлов с mswordtree
"""

from mswordtree import GetWordDocTree, ToString
from pathlib import Path
import json
import traceback


def force_parse_document(docx_path: Path):
    """Принудительный парсинг документа любыми способами."""
    print(f"ПРИНУДИТЕЛЬНЫЙ ПАРСИНГ: {docx_path.name}")
    print("=" * 80)
    
    # Способ 1: Обычный парсинг
    print("СПОСОБ 1: Обычный GetWordDocTree")
    try:
        root = GetWordDocTree(str(docx_path))
        print(f"✅ Успех! Тип root: {type(root)}")
        
        if root and hasattr(root, 'Items'):
            print(f"✅ Items найдены: {len(root.Items) if root.Items else 0}")
            return analyze_items(root.Items, "Обычный")
        else:
            print("❌ Root пустой или нет Items")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        print(f"Детали: {traceback.format_exc()}")
    
    # Способ 2: Попробуем с разными путями
    print("\nСПОСОБ 2: Разные пути к файлу")
    paths_to_try = [
        str(docx_path),
        str(docx_path.absolute()),
        str(docx_path.resolve()),
        docx_path.as_posix(),
        docx_path.as_uri()
    ]
    
    for i, path in enumerate(paths_to_try, 1):
        print(f"  Попытка {i}: {path}")
        try:
            root = GetWordDocTree(path)
            if root and hasattr(root, 'Items'):
                print(f"✅ Успех с путем {i}!")
                return analyze_items(root.Items, f"Путь {i}")
        except Exception as e:
            print(f"❌ Путь {i}: {e}")
    
    # Способ 3: Попробуем скопировать файл
    print("\nСПОСОБ 3: Копирование файла")
    try:
        import shutil
        temp_path = Path("temp_file.docx")
        shutil.copy2(docx_path, temp_path)
        print(f"Файл скопирован в: {temp_path}")
        
        root = GetWordDocTree(str(temp_path))
        if root and hasattr(root, 'Items'):
            print("✅ Успех с копией!")
            result = analyze_items(root.Items, "Копия")
            temp_path.unlink()  # Удаляем временный файл
            return result
        else:
            temp_path.unlink()
            print("❌ Копия не помогла")
            
    except Exception as e:
        print(f"❌ Ошибка копирования: {e}")
    
    # Способ 4: Попробуем разные кодировки
    print("\nСПОСОБ 4: Разные кодировки")
    encodings = ['utf-8', 'cp1251', 'latin1', 'ascii']
    
    for encoding in encodings:
        try:
            print(f"  Кодировка: {encoding}")
            # Попробуем прочитать файл и пересохранить
            with open(docx_path, 'rb') as f:
                content = f.read()
            
            temp_path = Path(f"temp_{encoding}.docx")
            with open(temp_path, 'wb') as f:
                f.write(content)
            
            root = GetWordDocTree(str(temp_path))
            if root and hasattr(root, 'Items'):
                print(f"✅ Успех с кодировкой {encoding}!")
                result = analyze_items(root.Items, f"Кодировка {encoding}")
                temp_path.unlink()
                return result
            else:
                temp_path.unlink()
                
        except Exception as e:
            print(f"❌ Кодировка {encoding}: {e}")
            if temp_path.exists():
                temp_path.unlink()
    
    # Способ 5: Попробуем через python-docx
    print("\nСПОСОБ 5: Через python-docx")
    try:
        from docx import Document
        doc = Document(str(docx_path))
        
        headings = []
        for paragraph in doc.paragraphs:
            if paragraph.style.name.startswith('Heading'):
                headings.append({
                    'content': paragraph.text.strip(),
                    'level': paragraph.style.name,
                    'style': paragraph.style.name
                })
        
        if headings:
            print(f"✅ python-docx нашел {len(headings)} заголовков!")
            return headings
        else:
            print("❌ python-docx не нашел заголовков")
            
    except Exception as e:
        print(f"❌ python-docx ошибка: {e}")
    
    print("\n❌ ВСЕ СПОСОБЫ НЕУДАЧНЫ")
    return None


def analyze_items(items, method):
    """Анализ элементов документа."""
    print(f"\nАНАЛИЗ ЭЛЕМЕНТОВ ({method}):")
    print("-" * 50)
    
    headings = []
    total_items = 0
    
    for i, item in enumerate(items):
        total_items += 1
        
        try:
            # Получаем атрибуты безопасно
            item_type = getattr(item, 'Type', None)
            content = getattr(item, 'Content', None)
            
            # Обрабатываем content
            if content is None:
                content = ""
            elif hasattr(content, 'empty'):  # DataFrame
                content = str(content)
            else:
                content = str(content).strip()
            
            # Обрабатываем item_type
            if item_type is None:
                item_type = "Unknown"
            else:
                item_type = str(item_type)
            
            # Проверяем на заголовок
            if "Heading" in item_type and content:
                headings.append({
                    'content': content,
                    'level': item_type,
                    'style': item_type,
                    'method': method
                })
            
            # Выводим первые несколько элементов для отладки
            if i < 10:
                print(f"  {i+1:2d}. [{item_type}] {content[:50]}...")
                
        except Exception as e:
            print(f"  {i+1:2d}. ОШИБКА: {e}")
    
    print(f"\nИТОГО: {total_items} элементов, {len(headings)} заголовков")
    
    if headings:
        print(f"\nЗАГОЛОВКИ ({len(headings)} шт.):")
        print("-" * 50)
        for i, h in enumerate(headings, 1):
            level = h['level']
            content = h['content']
            
            if "Heading 1" in level:
                prefix = "1."
            elif "Heading 2" in level:
                prefix = "2."
            elif "Heading 3" in level:
                prefix = "3."
            else:
                prefix = "•"
                
            print(f"{i:2d}. {prefix} {content}")
    
    return headings


def process_problem_files():
    """Обработать проблемные файлы."""
    problem_files = [
        "02_Отчет_Этап_2_полный_замечания_эксперта.docx",
        "Diplom2024.docx"
    ]
    
    test_folder = Path("test_folder")
    results = {}
    
    for filename in problem_files:
        file_path = test_folder / filename
        
        if not file_path.exists():
            print(f"❌ Файл не найден: {filename}")
            continue
        
        print(f"\n{'='*80}")
        headings = force_parse_document(file_path)
        
        if headings:
            results[filename] = {
                'success': True,
                'headings_count': len(headings),
                'headings': headings
            }
            
            # Сохраняем результат
            output_file = file_path.with_suffix('.forced_headings.json')
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(headings, f, ensure_ascii=False, indent=2)
            print(f"\n💾 Результат сохранен в: {output_file}")
        else:
            results[filename] = {
                'success': False,
                'headings_count': 0,
                'headings': []
            }
    
    # Итоговая статистика
    print(f"\n{'='*80}")
    print("ИТОГОВАЯ СТАТИСТИКА:")
    print("=" * 80)
    
    successful = sum(1 for r in results.values() if r['success'])
    total_headings = sum(r['headings_count'] for r in results.values())
    
    print(f"Успешно обработано: {successful}/{len(problem_files)}")
    print(f"Всего заголовков: {total_headings}")
    
    for filename, result in results.items():
        status = "✅" if result['success'] else "❌"
        print(f"{status} {filename}: {result['headings_count']} заголовков")


if __name__ == "__main__":
    process_problem_files()





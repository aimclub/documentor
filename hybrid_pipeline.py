#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Гибридный пайплайн для извлечения заголовков из DOCX файлов.
Использует mswordtree для совместимых файлов и правиловый пайплайн для остальных.
"""

from mswordtree import GetWordDocTree, ToString
from heading_extraction_pipeline import HeadingDetector, process_docx_file
from pathlib import Path
import json


def analyze_with_mswordtree(docx_path: Path):
    """Анализ документа с помощью mswordtree."""
    print(f"  Пробуем mswordtree...")
    
    try:
        root = GetWordDocTree(str(docx_path))
        if not root or not hasattr(root, 'Items'):
            return None
            
        headings = []
        
        for item in root.Items:
            try:
                item_type = getattr(item, 'Type', None)
                content = getattr(item, 'Content', None)
                
                if content is None:
                    content = ""
                else:
                    content = str(content).strip()
                
                if hasattr(content, 'empty'):  # DataFrame
                    content = str(content)
                
                if item_type is None:
                    item_type = "Unknown"
                else:
                    item_type = str(item_type)
                
                if "Heading" in item_type and content:
                    headings.append({
                        'content': content,
                        'level': item_type,
                        'style': item_type
                    })
                    
            except Exception:
                continue
        
        if headings:
            print(f"  mswordtree: найдено {len(headings)} заголовков")
            return headings
        else:
            print(f"  mswordtree: заголовки не найдены")
            return None
            
    except Exception as e:
        print(f"  mswordtree: ошибка - {e}")
        return None


def analyze_with_rules(docx_path: Path):
    """Анализ документа с помощью правилового пайплайна."""
    print(f"  Пробуем правиловый пайплайн...")
    
    try:
        detector = HeadingDetector()
        headings = detector.extract_headings(str(docx_path))
        
        if headings:
            print(f"  Правила: найдено {len(headings)} заголовков")
            return headings
        else:
            print(f"  Правила: заголовки не найдены")
            return None
            
    except Exception as e:
        print(f"  Правила: ошибка - {e}")
        return None


def analyze_document_hybrid(docx_path: Path):
    """Гибридный анализ документа."""
    print(f"Анализ документа: {docx_path.name}")
    print("-" * 60)
    
    # Сначала пробуем mswordtree
    headings = analyze_with_mswordtree(docx_path)
    
    # Если mswordtree не сработал, пробуем правила
    if not headings:
        headings = analyze_with_rules(docx_path)
    
    if headings:
        print(f"\nЗАГОЛОВКИ ({len(headings)} шт.):")
        print("-" * 60)
        
        for i, h in enumerate(headings, 1):
            if isinstance(h, dict):
                # mswordtree результат
                level = h.get('level', 'Unknown')
                content = h.get('content', '')
                
                # Определяем префикс по стилю
                if "Heading 1" in level:
                    prefix = "1."
                elif "Heading 2" in level:
                    prefix = "2."
                elif "Heading 3" in level:
                    prefix = "3."
                else:
                    prefix = "•"
                    
                print(f"{i:2d}. {prefix} {content}")
            else:
                # Правиловый результат
                level = h.get('level', 1)
                content = h.get('text', '')
                prefix = f"{level}."
                print(f"{i:2d}. {prefix} {content}")
        
        # Сохраняем результат
        output_file = docx_path.with_suffix('.hybrid_headings.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(headings, f, ensure_ascii=False, indent=2)
        print(f"\nРезультат сохранен в: {output_file}")
        
        return headings
    else:
        print(f"\nНе удалось извлечь заголовки из документа")
        return None


def process_all_documents_hybrid():
    """Обработать все документы гибридным методом."""
    test_folder = Path("test_folder")
    
    if not test_folder.exists():
        print("Папка test_folder не найдена")
        return
    
    docx_files = list(test_folder.glob("*.docx"))
    
    if not docx_files:
        print("DOCX файлы не найдены в папке test_folder")
        return
    
    print(f"ГИБРИДНЫЙ ПАЙПЛАЙН")
    print(f"Найдено файлов: {len(docx_files)}")
    print("=" * 80)
    
    results = {}
    successful = 0
    
    for i, docx_file in enumerate(docx_files, 1):
        print(f"\n[{i}/{len(docx_files)}] {docx_file.name}")
        print("=" * 80)
        
        try:
            headings = analyze_document_hybrid(docx_file)
            
            if headings:
                results[docx_file.name] = {
                    'headings_count': len(headings),
                    'headings': headings,
                    'method': 'mswordtree' if isinstance(headings[0], dict) and 'level' in headings[0] else 'rules'
                }
                successful += 1
            else:
                results[docx_file.name] = {
                    'headings_count': 0,
                    'headings': [],
                    'method': 'failed'
                }
                
        except Exception as e:
            print(f"Критическая ошибка: {e}")
            results[docx_file.name] = {
                'headings_count': 0,
                'headings': [],
                'method': 'error',
                'error': str(e)
            }
    
    # Итоговая статистика
    print(f"\nИТОГОВАЯ СТАТИСТИКА:")
    print("=" * 80)
    print(f"Успешно обработано: {successful}/{len(docx_files)}")
    
    total_headings = sum(r['headings_count'] for r in results.values())
    print(f"Всего заголовков: {total_headings}")
    
    # Статистика по методам
    mswordtree_count = sum(1 for r in results.values() if r['method'] == 'mswordtree')
    rules_count = sum(1 for r in results.values() if r['method'] == 'rules')
    failed_count = sum(1 for r in results.values() if r['method'] in ['failed', 'error'])
    
    print(f"mswordtree: {mswordtree_count} файлов")
    print(f"Правила: {rules_count} файлов")
    print(f"Ошибки: {failed_count} файлов")
    
    # Сохраняем сводный отчет
    summary_file = test_folder / "hybrid_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\nСводный отчет: {summary_file}")


if __name__ == "__main__":
    process_all_documents_hybrid()

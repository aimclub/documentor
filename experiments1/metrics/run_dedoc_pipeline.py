"""
Скрипт для обработки документов через dedoc и сохранения результатов.

Сначала обрабатывает все PDF файлы через dedoc (через Docker API),
сохраняет результаты в JSON и Markdown форматах,
затем можно будет вычислить метрики на основе этих результатов.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, Optional

# Попытка импортировать requests для Docker API
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("[ERROR] requests не установлен. Установите: pip install requests")


def check_docker_dedoc_available() -> bool:
    """Проверяет, доступен ли dedoc через Docker API."""
    if not REQUESTS_AVAILABLE:
        return False
    
    # Пробуем несколько вариантов проверки
    endpoints_to_try = [
        'http://localhost:1231/',
        'http://localhost:1231/health',
    ]
    
    for endpoint in endpoints_to_try:
        try:
            response = requests.get(endpoint, timeout=2)
            if response.status_code != 404:
                return True
        except requests.exceptions.ConnectionError:
            continue
        except Exception:
            continue
    
    # Проверяем через upload endpoint
    try:
        response = requests.get('http://localhost:1231/upload', timeout=1)
        # Любой ответ означает, что сервер работает
        return True
    except requests.exceptions.ConnectionError:
        return False
    except Exception:
        return True


def parse_with_docker_dedoc(pdf_path: Path) -> Dict[str, Any]:
    """Парсит документ через Docker API dedoc."""
    if not REQUESTS_AVAILABLE:
        raise ImportError("requests не установлен. Установите: pip install requests")
    
    api_url = 'http://localhost:1231/upload'
    
    with open(pdf_path, 'rb') as f:
        files = {'file': (pdf_path.name, f, 'application/pdf')}
        response = requests.post(api_url, files=files, timeout=300)
        response.raise_for_status()
        
        return response.json()


def save_dedoc_result(
    result: Dict[str, Any],
    output_dir: Path,
    document_id: str
) -> None:
    """Сохраняет результат dedoc в JSON и Markdown форматах."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Сохраняем полный JSON результат
    json_path = output_dir / f"{document_id}_dedoc.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  [OK] JSON сохранен: {json_path.name}")
    
    # Извлекаем текст и сохраняем в Markdown
    text_content = extract_text_from_dedoc_result(result)
    if text_content:
        md_path = output_dir / f"{document_id}_dedoc.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(text_content)
        print(f"  [OK] Markdown сохранен: {md_path.name}")


def extract_text_from_dedoc_result(result: Dict[str, Any]) -> str:
    """Извлекает текст из результата dedoc для сохранения в Markdown."""
    lines = []
    
    # Извлекаем структуру из content.structure
    content = result.get('content', {})
    if not isinstance(content, dict):
        return ''
    
    structure = content.get('structure')
    if not structure or not isinstance(structure, dict):
        return ''
    
    def extract_from_node(node: Dict[str, Any], level: int = 0) -> None:
        """Рекурсивно извлекает текст из узлов структуры."""
        if not isinstance(node, dict):
            return
        
        # Извлекаем данные узла
        text = node.get('text', '')
        metadata = node.get('metadata', {})
        paragraph_type = metadata.get('paragraph_type', 'raw_text')
        
        # Пропускаем корневой узел без текста
        if paragraph_type == 'root' and not text.strip():
            # Обрабатываем только дочерние элементы
            subparagraphs = node.get('subparagraphs', [])
            for subpara in subparagraphs:
                extract_from_node(subpara, level)
            return
        
        # Форматируем в зависимости от типа
        if text and text.strip():
            paragraph_type_lower = paragraph_type.lower()
            
            if 'header' in paragraph_type_lower or 'title' in paragraph_type_lower:
                # Заголовки - определяем уровень по типу
                if '1' in paragraph_type_lower or 'title' in paragraph_type_lower:
                    header_marker = '#'
                elif '2' in paragraph_type_lower:
                    header_marker = '##'
                elif '3' in paragraph_type_lower:
                    header_marker = '###'
                elif '4' in paragraph_type_lower:
                    header_marker = '####'
                elif '5' in paragraph_type_lower:
                    header_marker = '#####'
                elif '6' in paragraph_type_lower:
                    header_marker = '######'
                else:
                    header_marker = '#'
                lines.append(f"\n{header_marker} {text.strip()}\n")
            elif 'list' in paragraph_type_lower:
                # Списки
                lines.append(f"- {text.strip()}\n")
            else:
                # Обычный текст
                lines.append(f"{text.strip()}\n\n")
        
        # Обрабатываем дочерние элементы (subparagraphs)
        subparagraphs = node.get('subparagraphs', [])
        for subpara in subparagraphs:
            extract_from_node(subpara, level + 1)
    
    # Обрабатываем корневой узел структуры
    extract_from_node(structure)
    
    return '\n'.join(lines)


def main():
    """Основная функция для обработки всех PDF файлов."""
    script_dir = Path(__file__).parent
    
    # Пути к файлам
    test_files_dir = script_dir / "test_files_for_metrics"
    output_dir = script_dir / "dedoc_output"
    
    # Проверяем доступность Docker API
    if not check_docker_dedoc_available():
        print("[ERROR] Docker API dedoc недоступен!")
        print("[INFO] Убедитесь, что контейнер запущен:")
        print("      docker run -d -p 1231:1231 --name dedoc dedocproject/dedoc")
        return
    
    print("[INFO] Docker API dedoc доступен")
    
    # Находим все PDF файлы
    pdf_files = sorted(test_files_dir.glob("*.pdf"))
    
    if not pdf_files:
        print(f"[ERROR] PDF файлы не найдены в {test_files_dir}")
        return
    
    print(f"\nНайдено PDF файлов: {len(pdf_files)}")
    print(f"Результаты будут сохранены в: {output_dir}\n")
    
    # Обрабатываем каждый файл
    for i, pdf_file in enumerate(pdf_files, 1):
        print(f"\n[{i}/{len(pdf_files)}] Обработка: {pdf_file.name}")
        
        document_id = pdf_file.stem
        
        try:
            start_time = time.time()
            
            # Парсим через dedoc
            result = parse_with_docker_dedoc(pdf_file)
            
            processing_time = time.time() - start_time
            print(f"  [OK] Обработка завершена за {processing_time:.2f} сек")
            
            # Сохраняем результаты
            save_dedoc_result(result, output_dir, document_id)
            
        except Exception as e:
            print(f"  [ERROR] Ошибка при обработке: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("ОБРАБОТКА ЗАВЕРШЕНА")
    print("=" * 80)
    print(f"\nОбработано файлов: {len(pdf_files)}")
    print(f"Результаты сохранены в: {output_dir}")
    print("\nТеперь можно запустить вычисление метрик:")
    print("  python evaluate_dedoc.py")


if __name__ == "__main__":
    main()

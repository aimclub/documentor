"""
Скрипт для тестирования извлечения структуры из PDF с помощью pdfplumber и Qwen LLM.

Процесс:
1. Извлекает текст из PDF с помощью pdfplumber
2. Разбивает текст на чанки с перекрытием
3. Отправляет чанки в Qwen для определения структуры (заголовки, списки, таблицы)
4. Сохраняет результаты
"""

import sys
import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

import openai
import pdfplumber
from documentor.core.load_env import load_env_file


def clean_url(url: str) -> str:
    """Очищает URL от комментариев и лишних пробелов."""
    if not url:
        return ""
    if '#' in url:
        url = url.split('#')[0]
    return url.strip()


def load_qwen_config() -> Dict[str, Any]:
    """Загружает конфигурацию Qwen из .env файла."""
    load_env_file()
    
    qwen_base_url = clean_url(os.getenv("QWEN_BASE_URL", ""))
    
    return {
        "base_url": qwen_base_url,
        "api_key": os.getenv("QWEN_API_KEY", "dummy"),
        "model_name": os.getenv("QWEN_MODEL_NAME", "/model"),
        "temperature": float(os.getenv("QWEN_TEMPERATURE", "0.1")),
        "max_tokens": int(os.getenv("QWEN_MAX_TOKENS", "4096")),
        "timeout": int(os.getenv("QWEN_TIMEOUT", "180"))
    }


def split_text_into_chunks(text: str, chunk_size: int = 3000, overlap: int = 300) -> List[Dict[str, Any]]:
    """
    Разбивает текст на чанки с перекрытием.
    
    Args:
        text: Текст для разбиения
        chunk_size: Размер чанка в символах
        overlap: Размер перекрытия в символах
        
    Returns:
        Список чанков с метаданными
    """
    chunks = []
    start = 0
    chunk_num = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk_text = text[start:end]
        
        chunks.append({
            "chunk_number": chunk_num,
            "start_position": start,
            "end_position": end,
            "text": chunk_text,
            "length": len(chunk_text)
        })
        
        start = end - overlap
        chunk_num += 1
        
        # Предотвращаем бесконечный цикл
        if start >= len(text):
            break
    
    return chunks


def get_structure_detection_prompt(text_chunk: str, previous_headers: List[Dict] = None) -> str:
    """
    Создает промпт для определения структуры документа.
    
    Args:
        text_chunk: Текст чанка для анализа
        previous_headers: Предыдущие заголовки для контекста
        
    Returns:
        Промпт для LLM
    """
    previous_context = ""
    if previous_headers:
        prev_text = "\n".join([f"  {'  ' * (h['level'] - 1)}- {h['text']}" for h in previous_headers[-5:]])
        previous_context = f"\n\nПредыдущие заголовки для контекста:\n{prev_text}"
    
    prompt = f"""Проанализируй следующий текст из PDF документа и определи его структуру.

Определи следующие элементы:
1. Заголовки (с уровнями 1-6, где 1 - самый верхний уровень)
2. Обычный текст (параграфы)
3. Списки (маркированные и нумерованные)
4. Таблицы (если есть упоминания)
5. Подписи к изображениям/таблицам

Правила:
- Заголовки должны быть выделены из обычного текста по смыслу
- Определи уровень заголовка на основе иерархии и важности
- Учти существующую иерархию из предыдущих заголовков
- Проверь логику: внутри заголовка уровня N не может быть заголовка уровня < N
- Обычный текст группируй в параграфы
- Списки определяй по наличию маркеров или нумерации

Текст для анализа:
{text_chunk}{previous_context}

Верни результат в формате JSON:
{{
  "headers": [
    {{"level": 1, "text": "Заголовок", "position": 0, "context": "контекст вокруг заголовка"}},
    {{"level": 2, "text": "Подзаголовок", "position": 150, "context": "контекст"}}
  ],
  "paragraphs": [
    {{"text": "Текст параграфа", "position": 200}}
  ],
  "lists": [
    {{"type": "bullet", "items": ["Элемент 1", "Элемент 2"], "position": 300}},
    {{"type": "numbered", "items": ["Первый пункт", "Второй пункт"], "position": 400}}
  ],
  "tables": [
    {{"description": "Описание таблицы", "position": 500}}
  ],
  "captions": [
    {{"text": "Подпись к изображению", "position": 600}}
  ]
}}

Важно: position - это позиция в исходном тексте (символ от начала чанка)."""
    
    return prompt


def detect_structure_with_qwen(
    text_chunk: str,
    config: Dict[str, Any],
    previous_headers: List[Dict] = None
) -> Dict[str, Any]:
    """
    Отправляет текст в Qwen для определения структуры.
    
    Args:
        text_chunk: Текст для анализа
        config: Конфигурация Qwen
        previous_headers: Предыдущие заголовки для контекста
        
    Returns:
        Dict с результатами анализа структуры
    """
    try:
        client = openai.OpenAI(
            base_url=config["base_url"],
            api_key=config["api_key"],
            timeout=config["timeout"]
        )
        
        prompt = get_structure_detection_prompt(text_chunk, previous_headers)
        
        print(f"    Отправка запроса в Qwen (размер текста: {len(text_chunk)} символов)...")
        
        response = client.chat.completions.create(
            model=config["model_name"],
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=config["temperature"],
            max_tokens=config["max_tokens"]
        )
        
        content = response.choices[0].message.content
        
        # Пытаемся распарсить JSON
        try:
            # Убираем markdown code blocks если есть
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            structure_data = json.loads(content)
            return {
                "success": True,
                "data": structure_data,
                "raw_response": content
            }
        except json.JSONDecodeError as e:
            print(f"    Предупреждение: Не удалось распарсить JSON: {e}")
            print(f"    Первые 500 символов ответа: {content[:500]}")
            return {
                "success": False,
                "error": f"Failed to parse JSON response: {str(e)}",
                "raw_response": content
            }
            
    except openai.APIError as e:
        error_msg = f"API Error: {e.status_code} - {e.message}"
        if hasattr(e, 'response') and e.response:
            error_msg += f" | Response: {e.response}"
        print(f"    {error_msg}")
        return {
            "success": False,
            "error": error_msg,
            "error_type": "APIError",
            "status_code": getattr(e, 'status_code', None)
        }
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"    {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": error_msg,
            "error_type": type(e).__name__
        }


def extract_text_from_pdf(pdf_path: Path) -> Dict[str, Any]:
    """
    Извлекает текст из PDF с помощью pdfplumber.
    
    Args:
        pdf_path: Путь к PDF файлу
        
    Returns:
        Dict с извлеченным текстом и метаданными
    """
    text_by_pages = []
    full_text = ""
    tables_by_pages = []
    
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        
        for page_num, page in enumerate(pdf.pages, 1):
            # Извлекаем текст
            page_text = page.extract_text() or ""
            text_by_pages.append({
                "page_number": page_num,
                "text": page_text,
                "length": len(page_text)
            })
            full_text += page_text + "\n\n"
            
            # Извлекаем таблицы
            page_tables = page.extract_tables()
            if page_tables:
                tables_by_pages.append({
                    "page_number": page_num,
                    "tables_count": len(page_tables),
                    "tables": page_tables
                })
    
    return {
        "full_text": full_text,
        "text_by_pages": text_by_pages,
        "tables_by_pages": tables_by_pages,
        "total_pages": len(text_by_pages),
        "total_length": len(full_text)
    }


def process_pdf_with_pdfplumber_qwen(
    pdf_path: Path,
    output_dir: Path,
    config: Dict[str, Any]
):
    """
    Обрабатывает PDF файл через pdfplumber и Qwen.
    
    Args:
        pdf_path: Путь к PDF файлу
        output_dir: Директория для сохранения результатов
        config: Конфигурация Qwen
    """
    pdf_name = pdf_path.stem
    pdf_output_dir = output_dir / f"{pdf_name}_pdfplumber_qwen"
    pdf_output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*80}")
    print(f"Обработка PDF: {pdf_path.name}")
    print(f"{'='*80}\n")
    
    # Шаг 1: Извлечение текста
    print("Шаг 1: Извлечение текста из PDF...")
    extracted_data = extract_text_from_pdf(pdf_path)
    
    print(f"  ✓ Извлечено {extracted_data['total_pages']} страниц")
    print(f"  ✓ Всего символов: {extracted_data['total_length']}")
    print(f"  ✓ Найдено таблиц: {sum(len(p['tables']) for p in extracted_data['tables_by_pages'])}")
    
    # Сохраняем извлеченный текст
    text_output_path = pdf_output_dir / "extracted_text.txt"
    with open(text_output_path, "w", encoding="utf-8") as f:
        f.write(extracted_data["full_text"])
    print(f"  ✓ Текст сохранен в: {text_output_path}")
    
    # Сохраняем таблицы
    if extracted_data["tables_by_pages"]:
        tables_output_path = pdf_output_dir / "extracted_tables.json"
        with open(tables_output_path, "w", encoding="utf-8") as f:
            json.dump(extracted_data["tables_by_pages"], f, ensure_ascii=False, indent=2)
        print(f"  ✓ Таблицы сохранены в: {tables_output_path}")
    
    # Шаг 2: Разбиение на чанки
    print(f"\nШаг 2: Разбиение текста на чанки...")
    chunks = split_text_into_chunks(extracted_data["full_text"], chunk_size=3000, overlap=200)
    print(f"  ✓ Создано {len(chunks)} чанков")
    
    # Шаг 3: Обработка чанков через Qwen
    print(f"\nШаг 3: Обработка чанков через Qwen LLM...")
    all_headers = []
    all_paragraphs = []
    all_lists = []
    all_tables = []
    all_captions = []
    chunk_results = []
    
    for chunk_idx, chunk in enumerate(chunks, 1):
        print(f"  Обработка чанка {chunk_idx}/{len(chunks)} (позиция {chunk['start_position']}-{chunk['end_position']})...")
        
        result = detect_structure_with_qwen(
            chunk["text"],
            config,
            previous_headers=all_headers
        )
        
        chunk_result = {
            "chunk_number": chunk["chunk_number"],
            "start_position": chunk["start_position"],
            "end_position": chunk["end_position"],
            "detection_result": result
        }
        chunk_results.append(chunk_result)
        
        if result["success"]:
            data = result["data"]
            
            # Корректируем позиции заголовков относительно полного текста
            if "headers" in data:
                for header in data["headers"]:
                    header["absolute_position"] = chunk["start_position"] + header.get("position", 0)
                    all_headers.append(header)
            
            if "paragraphs" in data:
                for para in data["paragraphs"]:
                    para["absolute_position"] = chunk["start_position"] + para.get("position", 0)
                    all_paragraphs.append(para)
            
            if "lists" in data:
                for lst in data["lists"]:
                    lst["absolute_position"] = chunk["start_position"] + lst.get("position", 0)
                    all_lists.append(lst)
            
            if "tables" in data:
                for table in data["tables"]:
                    table["absolute_position"] = chunk["start_position"] + table.get("position", 0)
                    all_tables.append(table)
            
            if "captions" in data:
                for caption in data["captions"]:
                    caption["absolute_position"] = chunk["start_position"] + caption.get("position", 0)
                    all_captions.append(caption)
            
            print(f"    ✓ Найдено: {len(data.get('headers', []))} заголовков, "
                  f"{len(data.get('paragraphs', []))} параграфов, "
                  f"{len(data.get('lists', []))} списков")
        else:
            print(f"    ✗ Ошибка: {result.get('error', 'Unknown error')}")
    
    # Шаг 4: Сохранение результатов
    print(f"\nШаг 4: Сохранение результатов...")
    
    # Сортируем элементы по позиции
    all_headers.sort(key=lambda x: x.get("absolute_position", 0))
    all_paragraphs.sort(key=lambda x: x.get("absolute_position", 0))
    all_lists.sort(key=lambda x: x.get("absolute_position", 0))
    all_tables.sort(key=lambda x: x.get("absolute_position", 0))
    all_captions.sort(key=lambda x: x.get("absolute_position", 0))
    
    final_structure = {
        "source": str(pdf_path),
        "total_pages": extracted_data["total_pages"],
        "total_length": extracted_data["total_length"],
        "chunks_processed": len(chunks),
        "structure": {
            "headers": all_headers,
            "paragraphs": all_paragraphs,
            "lists": all_lists,
            "tables": all_tables,
            "captions": all_captions
        },
        "statistics": {
            "headers_count": len(all_headers),
            "paragraphs_count": len(all_paragraphs),
            "lists_count": len(all_lists),
            "tables_count": len(all_tables),
            "captions_count": len(all_captions)
        }
    }
    
    # Сохраняем финальную структуру
    structure_output_path = pdf_output_dir / "structure.json"
    with open(structure_output_path, "w", encoding="utf-8") as f:
        json.dump(final_structure, f, ensure_ascii=False, indent=2)
    print(f"  ✓ Структура сохранена в: {structure_output_path}")
    
    # Сохраняем результаты по чанкам
    chunks_output_path = pdf_output_dir / "chunks_results.json"
    with open(chunks_output_path, "w", encoding="utf-8") as f:
        json.dump(chunk_results, f, ensure_ascii=False, indent=2)
    print(f"  ✓ Результаты по чанкам сохранены в: {chunks_output_path}")
    
    # Выводим статистику
    print(f"\n{'='*80}")
    print(f"Обработка завершена: {pdf_path.name}")
    print(f"{'='*80}")
    print(f"Статистика:")
    print(f"  - Заголовков: {len(all_headers)}")
    print(f"  - Параграфов: {len(all_paragraphs)}")
    print(f"  - Списков: {len(all_lists)}")
    print(f"  - Таблиц: {len(all_tables)}")
    print(f"  - Подписей: {len(all_captions)}")
    print(f"Результаты сохранены в: {pdf_output_dir}")
    print(f"{'='*80}\n")


def main():
    """Основная функция."""
    # Загружаем конфигурацию
    config = load_qwen_config()
    
    if not config.get("base_url"):
        print("Ошибка: Отсутствует QWEN_BASE_URL")
        print("Укажите в .env файле или через переменную окружения")
        return
    
    print(f"Используется Qwen URL: {config['base_url']}")
    
    # Определяем входные файлы
    if len(sys.argv) > 1:
        pdf_files = [Path(sys.argv[1])]
    else:
        # Обрабатываем все PDF в test_files
        test_files_dir = Path("test_files")
        pdf_files = list(test_files_dir.glob("*.pdf")) if test_files_dir.exists() else []
    
    if not pdf_files:
        print("Ошибка: PDF файлы не найдены")
        print("Укажите путь к PDF файлу или поместите файлы в test_files/")
        return
    
    # Директория для результатов
    output_dir = Path("results")
    output_dir.mkdir(exist_ok=True)
    
    # Обрабатываем каждый PDF
    for pdf_path in pdf_files:
        if not pdf_path.exists():
            print(f"⚠️  Файл не найден: {pdf_path}")
            continue
        
        try:
            process_pdf_with_pdfplumber_qwen(pdf_path, output_dir, config)
        except Exception as e:
            print(f"✗ Критическая ошибка при обработке {pdf_path.name}: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()

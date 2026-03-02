"""
Интерактивный инструмент для ручной разметки документов.

Использование:
    python manual_annotation_tool.py --input test_files_for_metrics/doc1.pdf --output annotations/doc1_annotation.json
"""

import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import sys

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    print("ВНИМАНИЕ: PyMuPDF не установлен. Координаты будут недоступны.")


class AnnotationTool:
    """Интерактивный инструмент для разметки документов."""
    
    ELEMENT_TYPES = [
        "title", "header_1", "header_2", "header_3", "header_4", "header_5", "header_6",
        "text", "image", "table", "formula", "list_item", "caption", "footnote",
        "page_header", "page_footer", "link", "code_block"
    ]
    
    def __init__(self, pdf_path: Path, output_path: Path):
        self.pdf_path = pdf_path.resolve()
        self.output_path = output_path.resolve()
        self.elements: List[Dict[str, Any]] = []
        self.current_order = 0
        
        if HAS_PYMUPDF:
            try:
                self.pdf_doc = fitz.open(str(self.pdf_path))
                self.total_pages = len(self.pdf_doc)
            except Exception as e:
                print(f"Ошибка открытия PDF: {e}")
                self.pdf_doc = None
                self.total_pages = 0
        else:
            self.pdf_doc = None
            self.total_pages = 0
    
    def show_page_info(self, page_num: int) -> None:
        """Показывает информацию о странице."""
        if self.pdf_doc and 0 <= page_num < self.total_pages:
            page = self.pdf_doc[page_num]
            print(f"\nСтраница {page_num + 1}/{self.total_pages}")
            print(f"Размер: {page.rect.width:.0f} x {page.rect.height:.0f}")
        else:
            print(f"\nСтраница {page_num + 1} (информация недоступна)")
    
    def get_element_type(self) -> str:
        """Интерактивный выбор типа элемента."""
        print("\nВыберите тип элемента:")
        for i, elem_type in enumerate(self.ELEMENT_TYPES, 1):
            print(f"  {i:2d}. {elem_type}")
        
        while True:
            try:
                choice = input("\nВведите номер (или название типа): ").strip()
                
                # Попытка по номеру
                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(self.ELEMENT_TYPES):
                        return self.ELEMENT_TYPES[idx]
                
                # Попытка по названию
                if choice in self.ELEMENT_TYPES:
                    return choice
                
                print("Неверный выбор. Попробуйте снова.")
            except (KeyboardInterrupt, EOFError):
                return None
    
    def get_text_content(self) -> str:
        """Получение текстового содержимого."""
        print("\nВведите текстовое содержимое элемента:")
        print("(Для многострочного текста используйте Enter, завершите пустой строкой или 'END')")
        
        lines = []
        while True:
            try:
                line = input()
                if line.strip() == "" or line.strip().upper() == "END":
                    break
                lines.append(line)
            except (KeyboardInterrupt, EOFError):
                break
        
        return "\n".join(lines)
    
    def get_bbox(self, page_num: int) -> Optional[List[float]]:
        """Получение координат bounding box."""
        if not self.pdf_doc or page_num < 0 or page_num >= self.total_pages:
            print("\nКоординаты недоступны (PDF не загружен или неверный номер страницы)")
            return None
        
        page = self.pdf_doc[page_num]
        print(f"\nВведите координаты bbox [x0, y0, x1, y1] для страницы {page_num + 1}")
        print(f"Размер страницы: {page.rect.width:.0f} x {page.rect.height:.0f}")
        print("Или нажмите Enter для пропуска координат")
        
        try:
            bbox_input = input("bbox: ").strip()
            if not bbox_input:
                return None
            
            # Парсинг координат
            coords = [float(x.strip()) for x in bbox_input.split(",")]
            if len(coords) == 4:
                return coords
            else:
                print("Неверный формат. Ожидается: x0, y0, x1, y1")
                return None
        except (ValueError, KeyboardInterrupt, EOFError):
            return None
    
    def get_parent_id(self) -> Optional[str]:
        """Выбор родительского элемента."""
        if not self.elements:
            return None
        
        print("\nДоступные элементы для родителя:")
        print("  0. Нет родителя (root)")
        for i, elem in enumerate(self.elements, 1):
            elem_type = elem.get("type", "unknown")
            content_preview = elem.get("content", "")[:50]
            if len(content_preview) > 50:
                content_preview += "..."
            print(f"  {i:2d}. [{elem_type}] {content_preview}")
        
        try:
            choice = input("\nВыберите родителя (номер или Enter для None): ").strip()
            if not choice or choice == "0":
                return None
            
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(self.elements):
                    return self.elements[idx]["id"]
            
            print("Неверный выбор. Родитель не установлен.")
            return None
        except (KeyboardInterrupt, EOFError):
            return None
    
    def add_element(self) -> bool:
        """Добавление нового элемента."""
        print("\n" + "="*60)
        print("Добавление нового элемента")
        print("="*60)
        
        # Тип элемента
        elem_type = self.get_element_type()
        if not elem_type:
            return False
        
        # Текстовое содержимое
        content = self.get_text_content()
        if not content.strip() and elem_type not in ["image", "table"]:
            print("Предупреждение: пустое содержимое для элемента типа 'text'")
            confirm = input("Продолжить? (y/n): ").strip().lower()
            if confirm != 'y':
                return True
        
        # Номер страницы
        try:
            page_input = input(f"\nНомер страницы (1-{self.total_pages}, Enter для 1): ").strip()
            page_num = int(page_input) - 1 if page_input else 0
            if page_num < 0:
                page_num = 0
            if self.total_pages > 0 and page_num >= self.total_pages:
                page_num = self.total_pages - 1
        except (ValueError, KeyboardInterrupt, EOFError):
            page_num = 0
        
        self.show_page_info(page_num)
        
        # Координаты
        bbox = self.get_bbox(page_num)
        
        # Родитель
        parent_id = self.get_parent_id()
        
        # Создание элемента
        element = {
            "id": f"elem_{len(self.elements) + 1:04d}",
            "type": elem_type,
            "content": content,
            "parent_id": parent_id,
            "order": self.current_order,
            "page_number": page_num + 1,
            "bbox": bbox,
            "metadata": {}
        }
        
        # Дополнительные данные для таблиц
        if elem_type == "table":
            print("\nДля таблицы нужно указать структуру ячеек.")
            print("Это можно сделать позже в JSON файле.")
            # TODO: Добавить интерактивный ввод структуры таблицы
        
        self.elements.append(element)
        self.current_order += 1
        
        print(f"\n✓ Элемент добавлен: {element['id']} ({elem_type})")
        return True
    
    def edit_element(self, idx: int) -> None:
        """Редактирование элемента."""
        if idx < 0 or idx >= len(self.elements):
            print("Неверный индекс элемента")
            return
        
        elem = self.elements[idx]
        print(f"\nРедактирование элемента: {elem['id']}")
        print(f"Текущий тип: {elem['type']}")
        print(f"Текущее содержимое: {elem['content'][:100]}...")
        
        # Простое редактирование - можно расширить
        new_content = input("Новое содержимое (Enter для пропуска): ").strip()
        if new_content:
            elem["content"] = new_content
        
        print("✓ Элемент обновлен")
    
    def list_elements(self) -> None:
        """Вывод списка всех элементов."""
        if not self.elements:
            print("\nЭлементы не добавлены")
            return
        
        print("\n" + "="*60)
        print(f"Всего элементов: {len(self.elements)}")
        print("="*60)
        
        for i, elem in enumerate(self.elements, 1):
            elem_type = elem.get("type", "unknown")
            content_preview = elem.get("content", "")[:40]
            if len(content_preview) > 40:
                content_preview += "..."
            order = elem.get("order", -1)
            page = elem.get("page_number", "?")
            parent = elem.get("parent_id", "None")
            
            print(f"{i:3d}. [{elem_type:12s}] order={order:3d} page={page:2s} parent={parent:15s}")
            print(f"     {content_preview}")
    
    def save_annotation(self) -> None:
        """Сохранение разметки."""
        # Вычисляем статистику
        stats = {
            "total_elements": len(self.elements),
            "total_pages": self.total_pages,
            "elements_by_type": {},
            "table_count": 0,
            "image_count": 0
        }
        
        pages = set()
        for elem in self.elements:
            elem_type = elem["type"]
            stats["elements_by_type"][elem_type] = stats["elements_by_type"].get(elem_type, 0) + 1
            
            if elem.get("page_number"):
                pages.add(elem["page_number"])
            
            if elem_type == "table":
                stats["table_count"] += 1
            elif elem_type == "image":
                stats["image_count"] += 1
        
        stats["total_pages"] = len(pages) if pages else self.total_pages
        
        # Создаем структуру разметки
        annotation = {
            "document_id": self.pdf_path.stem,
            "source_file": str(self.pdf_path),
            "document_format": "pdf",
            "annotation_version": "1.0",
            "annotator": "manual",
            "annotation_date": datetime.now().isoformat(),
            "elements": self.elements,
            "statistics": stats
        }
        
        # Сохраняем
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(annotation, f, ensure_ascii=False, indent=2)
        
        print(f"\n✓ Разметка сохранена: {self.output_path}")
        print(f"  Элементов: {stats['total_elements']}")
        print(f"  Таблиц: {stats['table_count']}")
        print(f"  Изображений: {stats['image_count']}")
    
    def run(self) -> None:
        """Запуск интерактивного режима."""
        print("="*60)
        print("ИНСТРУМЕНТ РУЧНОЙ РАЗМЕТКИ ДОКУМЕНТОВ")
        print("="*60)
        print(f"Документ: {self.pdf_path.name}")
        print(f"Выходной файл: {self.output_path.name}")
        
        if self.total_pages > 0:
            print(f"Страниц: {self.total_pages}")
        else:
            print("ВНИМАНИЕ: PDF не загружен, некоторые функции недоступны")
        
        print("\nКоманды:")
        print("  add    - добавить элемент")
        print("  list   - показать все элементы")
        print("  edit N - редактировать элемент N")
        print("  save   - сохранить разметку")
        print("  quit   - выйти (с сохранением)")
        print("  exit   - выйти без сохранения")
        
        while True:
            try:
                command = input("\n> ").strip().lower()
                
                if command == "add" or command == "a":
                    self.add_element()
                elif command == "list" or command == "l":
                    self.list_elements()
                elif command.startswith("edit "):
                    try:
                        idx = int(command.split()[1]) - 1
                        self.edit_element(idx)
                    except (ValueError, IndexError):
                        print("Неверный формат. Используйте: edit N")
                elif command == "save" or command == "s":
                    self.save_annotation()
                elif command == "quit" or command == "q":
                    self.save_annotation()
                    print("\nДо свидания!")
                    break
                elif command == "exit":
                    print("\nВыход без сохранения.")
                    break
                elif command == "help" or command == "h":
                    print("\nКоманды:")
                    print("  add    - добавить элемент")
                    print("  list   - показать все элементы")
                    print("  edit N - редактировать элемент N")
                    print("  save   - сохранить разметку")
                    print("  quit   - выйти (с сохранением)")
                    print("  exit   - выйти без сохранения")
                elif command == "":
                    continue
                else:
                    print(f"Неизвестная команда: {command}. Введите 'help' для справки.")
            
            except (KeyboardInterrupt, EOFError):
                print("\n\nПрервано пользователем.")
                save = input("Сохранить перед выходом? (y/n): ").strip().lower()
                if save == 'y':
                    self.save_annotation()
                break


def main():
    parser = argparse.ArgumentParser(description="Интерактивный инструмент для ручной разметки документов")
    parser.add_argument("--input", "-i", type=Path, required=True, help="Входной PDF файл")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Выходной JSON файл разметки")
    
    args = parser.parse_args()
    
    if not args.input.exists():
        print(f"Ошибка: файл не найден: {args.input}")
        sys.exit(1)
    
    tool = AnnotationTool(args.input, args.output)
    tool.run()


if __name__ == "__main__":
    main()

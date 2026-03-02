#!/usr/bin/env python3
"""
Тестовый скрипт для проверки обнаружения формул и элементов списка в PDF.

Рисует боксы только для формул и элементов списка, чтобы проверить,
правильно ли они определяются парсером.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any
import json

# Добавляем путь к корню проекта для импорта
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QFont, QImage

import fitz  # PyMuPDF

# Импорт нашего парсера
from documentor import Pipeline
from langchain_core.documents import Document


class FormulaListTestViewer(QWidget):
    """Виджет для отображения только формул и элементов списка."""
    
    def __init__(self, pdf_path: Path, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.pdf_doc = None
        self.current_page = 0
        self.formulas = []
        self.list_items = []
        self.scale = 1.5
        self.render_scale = 2.0
        
        self.setMinimumSize(1200, 800)
        self.setWindowTitle(f"Тест формул и списков: {pdf_path.name}")
        
        # Загружаем PDF
        self.load_pdf()
        
        # Парсим документ
        self.parse_document()
    
    def load_pdf(self):
        """Загрузка PDF документа."""
        try:
            self.pdf_doc = fitz.open(str(self.pdf_path))
            print(f"Загружен PDF: {len(self.pdf_doc)} страниц")
        except Exception as e:
            print(f"Ошибка загрузки PDF: {e}")
            return False
        return True
    
    def parse_document(self):
        """Парсинг документа для поиска формул и элементов списка."""
        try:
            pipeline = Pipeline()
            langchain_doc = Document(page_content="", metadata={"source": str(self.pdf_path)})
            parsed = pipeline.parse(langchain_doc)
            
            print(f"\n=== Результаты парсинга ===")
            print(f"Всего элементов: {len(parsed.elements)}")
            
            # Ищем формулы и элементы списка
            for i, elem in enumerate(parsed.elements):
                elem_type = elem.type.value.lower()
                page_num = elem.metadata.get("page_num", 0)
                bbox = elem.metadata.get("bbox")
                
                print(f"Элемент {i}: type={elem_type}, page={page_num}, bbox={bbox}")
                
                if elem_type == "formula":
                    self.formulas.append({
                        "id": elem.id,
                        "type": elem_type,
                        "content": elem.content[:50] + "..." if len(elem.content) > 50 else elem.content,
                        "page_number": page_num,
                        "bbox": bbox,
                        "order": i
                    })
                    print(f"  → НАЙДЕНА ФОРМУЛА: {elem.content[:50]}")
                
                elif elem_type == "list_item":
                    self.list_items.append({
                        "id": elem.id,
                        "type": elem_type,
                        "content": elem.content[:50] + "..." if len(elem.content) > 50 else elem.content,
                        "page_number": page_num,
                        "bbox": bbox,
                        "order": i
                    })
                    print(f"  → НАЙДЕН ЭЛЕМЕНТ СПИСКА: {elem.content[:50]}")
            
            print(f"\n=== Итого ===")
            print(f"Формул найдено: {len(self.formulas)}")
            print(f"Элементов списка найдено: {len(self.list_items)}")
            
            # Выводим детальную информацию
            if self.formulas:
                print("\n=== Формулы ===")
                for f in self.formulas:
                    print(f"  Page {f['page_number']}: {f['content']}")
                    print(f"    BBox: {f['bbox']}")
            
            if self.list_items:
                print("\n=== Элементы списка ===")
                for li in self.list_items:
                    print(f"  Page {li['page_number']}: {li['content']}")
                    print(f"    BBox: {li['bbox']}")
            
            self.update()
            
        except Exception as e:
            print(f"Ошибка парсинга: {e}")
            import traceback
            traceback.print_exc()
    
    def paintEvent(self, event):
        """Отрисовка страницы с боксами для формул и элементов списка."""
        if not self.pdf_doc:
            return
        
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Рендерим страницу PDF
            page = self.pdf_doc[self.current_page]
            mat = fitz.Matrix(self.render_scale, self.render_scale)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            
            # Конвертируем в QImage
            qimage = QImage.fromData(img_data, "png")
            pixmap = QPixmap.fromImage(qimage)
            
            # Масштабируем для отображения
            display_pixmap = pixmap.scaled(
                int(pixmap.width() * self.scale / self.render_scale),
                int(pixmap.height() * self.scale / self.render_scale),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            # Рисуем изображение
            painter.drawPixmap(0, 0, display_pixmap)
            
            # Коэффициенты масштабирования
            scale_factor = self.scale / self.render_scale
            
            # Рисуем боксы для формул (синий)
            formula_color = QColor(0, 153, 255)  # Синий
            for formula in self.formulas:
                if formula.get("page_number") == self.current_page:
                    bbox = formula.get("bbox")
                    if bbox and len(bbox) >= 4:
                        x0 = bbox[0] * scale_factor
                        y0 = bbox[1] * scale_factor
                        x1 = bbox[2] * scale_factor
                        y1 = bbox[3] * scale_factor
                        
                        if x1 > x0 and y1 > y0:
                            # Рисуем прямоугольник
                            pen = QPen(formula_color, 3)
                            painter.setPen(pen)
                            painter.drawRect(int(x0), int(y0), int(x1 - x0), int(y1 - y0))
                            
                            # Подпись
                            label = f"FORMULA ({formula.get('id', '?')})"
                            font = QFont("Arial", 12, QFont.Bold)
                            painter.setFont(font)
                            
                            # Фон для текста
                            text_rect = painter.fontMetrics().boundingRect(label)
                            text_rect.moveTopLeft((int(x0), int(y0) - text_rect.height() - 2))
                            painter.fillRect(text_rect, formula_color)
                            painter.setPen(QPen(QColor(255, 255, 255)))
                            painter.drawText(text_rect, Qt.AlignLeft, label)
            
            # Рисуем боксы для элементов списка (зелено-голубой)
            list_color = QColor(0, 255, 153)  # Зелено-голубой
            for list_item in self.list_items:
                if list_item.get("page_number") == self.current_page:
                    bbox = list_item.get("bbox")
                    if bbox and len(bbox) >= 4:
                        x0 = bbox[0] * scale_factor
                        y0 = bbox[1] * scale_factor
                        x1 = bbox[2] * scale_factor
                        y1 = bbox[3] * scale_factor
                        
                        if x1 > x0 and y1 > y0:
                            # Рисуем прямоугольник
                            pen = QPen(list_color, 3)
                            painter.setPen(pen)
                            painter.drawRect(int(x0), int(y0), int(x1 - x0), int(y1 - y0))
                            
                            # Подпись
                            label = f"LIST_ITEM ({list_item.get('id', '?')})"
                            font = QFont("Arial", 12, QFont.Bold)
                            painter.setFont(font)
                            
                            # Фон для текста
                            text_rect = painter.fontMetrics().boundingRect(label)
                            text_rect.moveTopLeft((int(x0), int(y0) - text_rect.height() - 2))
                            painter.fillRect(text_rect, list_color)
                            painter.setPen(QPen(QColor(255, 255, 255)))
                            painter.drawText(text_rect, Qt.AlignLeft, label)
            
            # Информация о странице
            info_text = f"Страница {self.current_page + 1}/{len(self.pdf_doc)} | "
            info_text += f"Формул на странице: {sum(1 for f in self.formulas if f.get('page_number') == self.current_page)} | "
            info_text += f"Элементов списка: {sum(1 for li in self.list_items if li.get('page_number') == self.current_page)}"
            
            painter.setPen(QPen(QColor(0, 0, 0)))
            painter.setFont(QFont("Arial", 10))
            painter.drawText(10, 20, info_text)
            
        except Exception as e:
            painter.drawText(10, 20, f"Ошибка отрисовки: {e}")
            import traceback
            traceback.print_exc()
    
    def keyPressEvent(self, event):
        """Обработка нажатий клавиш для навигации."""
        if event.key() == Qt.Key_Right or event.key() == Qt.Key_Space:
            if self.current_page < len(self.pdf_doc) - 1:
                self.current_page += 1
                self.update()
        elif event.key() == Qt.Key_Left:
            if self.current_page > 0:
                self.current_page -= 1
                self.update()
        elif event.key() == Qt.Key_Escape:
            self.close()


def main():
    """Главная функция."""
    if len(sys.argv) < 2:
        print("Использование: python test_formulas_lists.py <path_to_pdf>")
        sys.exit(1)
    
    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"Файл не найден: {pdf_path}")
        sys.exit(1)
    
    app = QApplication(sys.argv)
    
    viewer = FormulaListTestViewer(pdf_path)
    viewer.show()
    
    print("\n=== Управление ===")
    print("Стрелка вправо / Пробел: следующая страница")
    print("Стрелка влево: предыдущая страница")
    print("Escape: выход")
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

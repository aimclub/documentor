#!/usr/bin/env python3
"""
Скрипт для проверки правильности разметки документов.

Загружает разметку из JSON и визуализирует её на PDF,
позволяя проверить правильность координат и типов элементов.
"""

import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QSpinBox, QComboBox, QMessageBox, QSplitter, QScrollArea
)
from PyQt5.QtCore import Qt, QRect, QPoint
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QFont, QImage

import fitz  # PyMuPDF

# Цвета для типов элементов (как в qt_annotation_tool.py)
ELEMENT_COLORS = {
    "title": QColor(255, 0, 0),  # Красный
    "header_1": QColor(255, 102, 0),  # Оранжевый
    "header_2": QColor(255, 153, 0),  # Темно-оранжевый
    "header_3": QColor(255, 204, 0),  # Желтый
    "header_4": QColor(255, 255, 0),  # Ярко-желтый
    "header_5": QColor(204, 255, 0),  # Желто-зеленый
    "header_6": QColor(153, 255, 0),  # Зеленый
    "text": QColor(0, 204, 255),  # Голубой
    "table": QColor(153, 0, 255),  # Фиолетовый
    "image": QColor(255, 0, 255),  # Розовый
    "list_item": QColor(0, 255, 153),  # Зелено-голубой
    "caption": QColor(255, 0, 153),  # Розово-красный
    "formula": QColor(0, 153, 255),  # Синий
    "link": QColor(0, 255, 0),  # Ярко-зеленый
    "code_block": QColor(102, 102, 102),  # Серый
}


class PDFAnnotationViewer(QWidget):
    """Виджет для отображения PDF с разметкой."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pdf_doc = None
        self.elements = []
        self.current_page = 0
        self.scale = 1.5
        self.render_scale = 2.0
        self.selected_element_id = None
        self.show_all = True  # Показывать все элементы или только выбранный тип
        
        self.setMinimumSize(1000, 800)
        self.setFocusPolicy(Qt.StrongFocus)
    
    def load_pdf(self, pdf_path: Path):
        """Загрузка PDF документа."""
        try:
            self.pdf_doc = fitz.open(str(pdf_path))
            self.current_page = 0
            self.update()
            return True
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить PDF: {e}")
            return False
    
    def set_elements(self, elements: List[Dict[str, Any]]):
        """Установка элементов разметки."""
        self.elements = elements
        self.update()
    
    def set_page(self, page_num: int):
        """Установка текущей страницы."""
        if self.pdf_doc and 0 <= page_num < len(self.pdf_doc):
            self.current_page = page_num
            self.update()
    
    def get_total_pages(self) -> int:
        """Получить общее количество страниц."""
        return len(self.pdf_doc) if self.pdf_doc else 0
    
    def set_selected_element(self, element_id: Optional[str]):
        """Установить выбранный элемент."""
        self.selected_element_id = element_id
        self.update()
    
    def set_filter_type(self, elem_type: Optional[str]):
        """Установить фильтр по типу элемента."""
        self.filter_type = elem_type
        self.update()
    
    def paintEvent(self, event):
        """Отрисовка страницы с разметкой."""
        if not self.pdf_doc:
            painter = QPainter(self)
            painter.drawText(QRect(0, 0, self.width(), self.height()),
                           Qt.AlignCenter, "Загрузите PDF")
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
            
            # Устанавливаем размер виджета
            self.setMinimumSize(display_pixmap.width(), display_pixmap.height())
            self.resize(display_pixmap.width(), display_pixmap.height())
            
            # Рисуем изображение
            painter.drawPixmap(0, 0, display_pixmap)
            
            # Коэффициенты масштабирования
            scale_factor = self.scale / self.render_scale
            
            # Фильтруем элементы для текущей страницы
            page_elements = [
                e for e in self.elements
                if e.get("page_number") == self.current_page
            ]
            
            # Рисуем боксы для элементов
            for elem in page_elements:
                bbox = elem.get("bbox")
                if not bbox or len(bbox) < 4:
                    continue
                
                x0_bbox, y0_bbox, x1_bbox, y1_bbox = bbox
                
                # Конвертируем координаты
                x0 = x0_bbox * scale_factor
                y0 = y0_bbox * scale_factor
                x1 = x1_bbox * scale_factor
                y1 = y1_bbox * scale_factor
                
                if x1 <= x0 or y1 <= y0:
                    continue
                
                # Получаем цвет для типа элемента
                elem_type = elem.get("type", "text")
                color = ELEMENT_COLORS.get(elem_type, QColor(0, 0, 0))
                
                # Если элемент выбран, делаем рамку толще
                is_selected = elem.get("id") == self.selected_element_id
                pen_width = 4 if is_selected else 2
                
                # Для формул и элементов списка делаем толще
                if elem_type in ["formula", "list_item"]:
                    pen_width = max(pen_width, 3)
                
                # Рисуем прямоугольник
                pen = QPen(color, pen_width)
                painter.setPen(pen)
                painter.drawRect(int(x0), int(y0), int(x1 - x0), int(y1 - y0))
                
                # Добавляем подпись
                label = f"{elem_type} ({elem.get('id', '?')})"
                font = QFont("Arial", 10)
                painter.setFont(font)
                
                # Фон для текста
                text_rect = painter.fontMetrics().boundingRect(label)
                text_rect.moveTopLeft(QPoint(int(x0), int(y0) - text_rect.height() - 2))
                painter.fillRect(text_rect, color)
                painter.setPen(QPen(QColor(255, 255, 255)))
                painter.drawText(text_rect, Qt.AlignLeft, label)
            
            # Информация о странице
            info_text = f"Страница {self.current_page + 1}/{len(self.pdf_doc)} | "
            info_text += f"Элементов на странице: {len(page_elements)}"
            
            # Фон для текста
            font = QFont("Arial", 10)
            painter.setFont(font)
            text_rect = painter.fontMetrics().boundingRect(info_text)
            text_rect.adjust(-5, -2, 5, 2)
            text_rect.moveTopLeft(QPoint(10, 10))
            painter.fillRect(text_rect, QColor(255, 255, 255, 200))
            painter.setPen(QPen(QColor(0, 0, 0)))
            painter.drawText(text_rect, Qt.AlignLeft, info_text)
            
        except Exception as e:
            painter.setPen(QPen(QColor(255, 0, 0)))
            painter.setFont(QFont("Arial", 12))
            painter.drawText(10, 20, f"Ошибка отрисовки: {e}")
    
    def keyPressEvent(self, event):
        """Обработка нажатий клавиш."""
        parent = self.parent()
        while parent and not isinstance(parent, QMainWindow):
            parent = parent.parent()
        
        if event.key() == Qt.Key_Left:
            if self.current_page > 0:
                self.set_page(self.current_page - 1)
                if parent:
                    parent.update_page_info()
        elif event.key() == Qt.Key_Right:
            total = self.get_total_pages()
            if self.current_page < total - 1:
                self.set_page(self.current_page + 1)
                if parent:
                    parent.update_page_info()
        elif event.key() == Qt.Key_Space:
            total = self.get_total_pages()
            if self.current_page < total - 1:
                self.set_page(self.current_page + 1)
                if parent:
                    parent.update_page_info()
        super().keyPressEvent(event)


class AnnotationVerifier(QMainWindow):
    """Главное окно для проверки разметки."""
    
    def __init__(self, annotation_path=None, pdf_path=None):
        super().__init__()
        self.annotation_path = annotation_path
        self.pdf_path = pdf_path
        self.elements = []
        self.current_page = 0
        
        self.setWindowTitle("Проверка разметки")
        self.setMinimumSize(1400, 900)
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # Разделитель
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Левая панель - список элементов
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Информация о документе
        self.doc_info = QLabel("Загрузите разметку и PDF")
        left_layout.addWidget(self.doc_info)
        
        # Фильтр по типу
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Фильтр:"))
        self.type_filter = QComboBox()
        self.type_filter.addItem("Все типы", None)
        for elem_type in sorted(ELEMENT_COLORS.keys()):
            self.type_filter.addItem(elem_type, elem_type)
        self.type_filter.currentIndexChanged.connect(self.on_filter_changed)
        filter_layout.addWidget(self.type_filter)
        left_layout.addLayout(filter_layout)
        
        # Список элементов
        self.elements_list = QListWidget()
        self.elements_list.itemClicked.connect(self.on_element_selected)
        left_layout.addWidget(self.elements_list)
        
        # Статистика
        self.stats_label = QLabel("")
        left_layout.addWidget(self.stats_label)
        
        # Информация о выбранном элементе
        self.element_info = QLabel("")
        self.element_info.setWordWrap(True)
        self.element_info.setMaximumHeight(150)
        left_layout.addWidget(self.element_info)
        
        splitter.addWidget(left_panel)
        
        # Правая панель - PDF с разметкой
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Панель навигации
        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("◀ Предыдущая")
        self.prev_btn.clicked.connect(self.prev_page)
        nav_layout.addWidget(self.prev_btn)
        
        self.page_label = QLabel("Страница: 1")
        nav_layout.addWidget(self.page_label)
        
        self.next_btn = QPushButton("Следующая ▶")
        self.next_btn.clicked.connect(self.next_page)
        nav_layout.addWidget(self.next_btn)
        
        nav_layout.addStretch()
        
        self.load_btn = QPushButton("📁 Загрузить разметку и PDF")
        self.load_btn.clicked.connect(self.load_files)
        nav_layout.addWidget(self.load_btn)
        
        right_layout.addLayout(nav_layout)
        
        # PDF viewer
        self.pdf_viewer = PDFAnnotationViewer()
        
        # PDF viewer с прокруткой
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.pdf_viewer)
        scroll_area.setWidgetResizable(True)
        scroll_area.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(scroll_area)
        
        splitter.addWidget(right_panel)
        
        # Устанавливаем пропорции
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        
        # Автозагрузка, если файлы указаны
        if self.annotation_path and self.pdf_path:
            self.load_annotation_and_pdf(self.annotation_path, self.pdf_path)
    
    def load_files(self):
        """Загрузка файлов разметки и PDF через диалог."""
        from PyQt5.QtWidgets import QFileDialog
        
        # Загружаем JSON разметку
        json_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите файл разметки JSON",
            str(Path("experiments/metrics/annotations")),
            "JSON Files (*.json)"
        )
        if not json_path:
            return
        
        # Загружаем PDF
        pdf_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите PDF файл",
            str(Path("experiments/metrics/test_files_for_metrics")),
            "PDF Files (*.pdf)"
        )
        if not pdf_path:
            return
        
        self.load_annotation_and_pdf(Path(json_path), Path(pdf_path))
    
    def load_annotation_and_pdf(self, json_path: Path, pdf_path: Path):
        """Загрузка разметки и PDF из указанных путей."""
        try:
            # Загружаем разметку
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.elements = data.get("elements", [])
            self.annotation_path = json_path
            self.pdf_path = pdf_path
            
            # Загружаем PDF
            if not self.pdf_viewer.load_pdf(self.pdf_path):
                return
            
            # Устанавливаем элементы в viewer
            self.pdf_viewer.set_elements(self.elements)
            
            # Обновляем интерфейс
            self.update_elements_list()
            self.update_stats()
            self.update_page_info()
            
            # Устанавливаем информацию о документе
            doc_id = data.get("document_id", "unknown")
            self.doc_info.setText(f"Документ: {doc_id}\nPDF: {self.pdf_path.name}")
            
            QMessageBox.information(
                self, "Успех",
                f"Загружено {len(self.elements)} элементов из {len(self.pdf_viewer.pdf_doc)} страниц"
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить файлы: {e}")
    
    def update_elements_list(self):
        """Обновление списка элементов."""
        self.elements_list.clear()
        
        # Получаем выбранный тип для фильтрации
        filter_type = self.type_filter.currentData()
        
        for elem in self.elements:
            elem_type = elem.get("type", "text")
            page_num = elem.get("page_number", 0)
            elem_id = elem.get("id", "?")
            parent_id = elem.get("parent_id")
            
            # Фильтруем по типу, если выбран фильтр
            if filter_type and elem_type != filter_type:
                continue
            
            # Формируем текст для отображения
            display_text = f"P{page_num + 1} | {elem_id} | {elem_type}"
            if parent_id:
                display_text += f" | parent: {parent_id}"
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, elem_id)
            self.elements_list.addItem(item)
    
    def update_stats(self):
        """Обновление статистики."""
        if not self.elements:
            self.stats_label.setText("")
            return
        
        # Подсчитываем элементы по типам
        type_counts = {}
        for elem in self.elements:
            elem_type = elem.get("type", "text")
            type_counts[elem_type] = type_counts.get(elem_type, 0) + 1
        
        stats_text = "Статистика:\n"
        for elem_type, count in sorted(type_counts.items()):
            stats_text += f"  {elem_type}: {count}\n"
        stats_text += f"\nВсего: {len(self.elements)}"
        
        self.stats_label.setText(stats_text)
    
    def on_element_selected(self, item):
        """Обработка выбора элемента."""
        element_id = item.data(Qt.UserRole)
        
        # Находим элемент
        element = next((e for e in self.elements if e.get("id") == element_id), None)
        if not element:
            return
        
        # Переходим на страницу элемента
        page_num = element.get("page_number", 0)
        self.current_page = page_num
        self.pdf_viewer.set_page(page_num)
        self.pdf_viewer.set_selected_element(element_id)
        self.update_page_info()
        
        # Показываем информацию об элементе
        info_text = f"<b>ID:</b> {element.get('id', '?')}<br>"
        info_text += f"<b>Тип:</b> {element.get('type', '?')}<br>"
        info_text += f"<b>Страница:</b> {page_num + 1}<br>"
        info_text += f"<b>Порядок:</b> {element.get('order', '?')}<br>"
        parent_id = element.get('parent_id')
        if parent_id:
            info_text += f"<b>Родитель:</b> {parent_id}<br>"
        content = element.get('content', '')
        if content:
            # Обрезаем длинный текст
            content_preview = content[:200] + "..." if len(content) > 200 else content
            info_text += f"<b>Содержимое:</b><br>{content_preview}"
        self.element_info.setText(info_text)
    
    def on_filter_changed(self):
        """Обработка изменения фильтра."""
        self.update_elements_list()
    
    def prev_page(self):
        """Предыдущая страница."""
        if self.current_page > 0:
            self.current_page -= 1
            self.pdf_viewer.set_page(self.current_page)
            self.update_page_info()
    
    def next_page(self):
        """Следующая страница."""
        total_pages = self.pdf_viewer.get_total_pages()
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.pdf_viewer.set_page(self.current_page)
            self.update_page_info()
    
    def update_page_info(self):
        """Обновление информации о странице."""
        total_pages = self.pdf_viewer.get_total_pages()
        self.page_label.setText(f"Страница: {self.current_page + 1}/{total_pages}")


def main():
    """Главная функция."""
    app = QApplication(sys.argv)
    
    # Парсим аргументы командной строки
    annotation_path = None
    pdf_path = None
    
    if len(sys.argv) >= 3:
        annotation_path = Path(sys.argv[1])
        pdf_path = Path(sys.argv[2])
    elif len(sys.argv) == 2:
        # Если указан только один файл, пытаемся определить тип
        file_path = Path(sys.argv[1])
        if file_path.suffix.lower() == '.json':
            annotation_path = file_path
            # Пытаемся найти соответствующий PDF
            pdf_name = file_path.stem.replace('_annotation', '') + '.pdf'
            pdf_path = file_path.parent.parent / 'test_files_for_metrics' / pdf_name
            if not pdf_path.exists():
                pdf_path = None
        elif file_path.suffix.lower() == '.pdf':
            pdf_path = file_path
            # Пытаемся найти соответствующую разметку
            json_name = file_path.stem + '_annotation.json'
            annotation_path = file_path.parent.parent / 'annotations' / json_name
            if not annotation_path.exists():
                annotation_path = None
    
    verifier = AnnotationVerifier(annotation_path, pdf_path)
    verifier.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

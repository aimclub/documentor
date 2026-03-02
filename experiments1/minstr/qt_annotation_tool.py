"""
Графический инструмент для разметки документов на PyQt5.

Автоматически создает предварительную разметку используя наш парсер,
визуализирует её на изображении PDF с цветными прямоугольниками,
и позволяет редактировать прямо в интерфейсе.
"""

import sys
import json
import io
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QFileDialog,
    QMessageBox, QGroupBox, QFormLayout, QSplitter,
    QTabWidget, QScrollArea, QDialog, QProgressDialog
)
from PyQt5.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QFont, QImage

import fitz  # PyMuPDF
import tempfile
from PIL import Image, ImageDraw, ImageFont

# Импорт нашего парсера
from documentor import Pipeline
from documentor.domain.models import ParsedDocument, ElementType
from documentor.processing.parsers.docx.converter import convert_docx_to_pdf
from langchain_core.documents import Document

# Типы элементов и их цвета
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

ELEMENT_TYPES = list(ELEMENT_COLORS.keys())


class PDFImageViewer(QWidget):
    """Виджет для отображения PDF страницы с разметкой."""
    
    element_selected = pyqtSignal(dict)  # Сигнал при выборе элемента
    element_selected_multi = pyqtSignal(dict, bool)  # Сигнал при выборе элемента (элемент, add_to_selection)
    element_double_clicked = pyqtSignal(dict)  # Сигнал при двойном клике на элемент
    bbox_drawn = pyqtSignal(list)  # Сигнал при рисовании bbox [x0, y0, x1, y1] в координатах render_scale
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pdf_doc = None
        self.current_page = 0
        self.elements = []
        self.selected_element_id = None
        self.scale = 1.5
        self.render_scale = 2.0
        
        # Режим рисования bbox
        self.drawing_mode = False
        self.drawing_start = None
        self.drawing_current = None
        self.current_pixmap = None
        
        self.setMinimumSize(800, 600)
        self.setMouseTracking(True)
        
    def load_pdf(self, pdf_path: Path, is_docx: bool = False, temp_pdf_path: Optional[Path] = None):
        """Загрузка PDF документа или DOCX (конвертированного в PDF)."""
        try:
            if is_docx and temp_pdf_path:
                # Загружаем временный PDF, созданный из DOCX
                self.pdf_doc = fitz.open(str(temp_pdf_path))
            else:
                self.pdf_doc = fitz.open(str(pdf_path))
            self.current_page = 0
            self.update()
            return True
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить документ: {e}")
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
    
    def set_drawing_mode(self, enabled: bool):
        """Включить/выключить режим рисования bbox."""
        self.drawing_mode = enabled
        self.drawing_start = None
        self.drawing_current = None
        if enabled:
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        self.update()
    
    def paintEvent(self, event):
        """Отрисовка страницы PDF с разметкой."""
        if not self.pdf_doc:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        try:
            # Рендерим страницу PDF
            page = self.pdf_doc[self.current_page]
            mat = fitz.Matrix(self.scale, self.scale)
            pix = page.get_pixmap(matrix=mat)
            
            # Конвертируем в QImage
            img_data = pix.tobytes("ppm")
            qimage = QImage.fromData(img_data)
            pixmap = QPixmap.fromImage(qimage)
            self.current_pixmap = pixmap  # Сохраняем для использования в mouse events
            
            # Устанавливаем размер виджета равным размеру изображения для правильной прокрутки
            self.setMinimumSize(pixmap.width(), pixmap.height())
            self.resize(pixmap.width(), pixmap.height())
            
            # Рисуем изображение
            rect = pixmap.rect()
            rect.moveTopLeft(QPoint(0, 0))
            painter.drawPixmap(rect, pixmap)
            
            # Получаем размеры PDF страницы
            pdf_width_pts = page.rect.width
            pdf_height_pts = page.rect.height
            
            # Коэффициенты масштабирования
            scale_x = self.scale / self.render_scale
            scale_y = self.scale / self.render_scale
            
            # Фильтруем элементы для текущей страницы
            # page_number в разметке - 1-based (1, 2, 3, ...)
            # self.current_page - 0-based (0, 1, 2, ...)
            page_elements = [
                e for e in self.elements 
                if e.get("page_number") == self.current_page + 1
            ]
            
            # Рисуем прямоугольники для каждого элемента
            for elem in page_elements:
                bbox = elem.get("bbox")
                if not bbox or len(bbox) != 4:
                    continue
                
                x0_bbox, y0_bbox, x1_bbox, y1_bbox = bbox
                
                # Конвертируем координаты
                x0 = x0_bbox * scale_x
                y0 = y0_bbox * scale_y
                x1 = x1_bbox * scale_x
                y1 = y1_bbox * scale_y
                
                # Ограничиваем координаты
                x0 = max(0, min(x0, pixmap.width()))
                y0 = max(0, min(y0, pixmap.height()))
                x1 = max(0, min(x1, pixmap.width()))
                y1 = max(0, min(y1, pixmap.height()))
                
                if x1 <= x0 or y1 <= y0:
                    continue
                
                # Получаем цвет для типа элемента
                elem_type = elem.get("type", "text")
                color = ELEMENT_COLORS.get(elem_type, QColor(0, 0, 0))
                
                # Определяем толщину линии
                # Если элемент выбран, делаем рамку толще
                is_selected = elem.get("id") == self.selected_element_id
                pen_width = 4 if is_selected else 2
                
                # Отладка: проверяем формулы и элементы списка
                if elem_type == "formula" or elem_type == "list_item":
                    # Увеличиваем толщину линии для лучшей видимости
                    if pen_width == 2:
                        pen_width = 3
                
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
            
            # Рисуем текущий прямоугольник, если идет процесс рисования
            if self.drawing_mode and self.drawing_start and self.drawing_current:
                start_x = min(self.drawing_start.x(), self.drawing_current.x())
                start_y = min(self.drawing_start.y(), self.drawing_current.y())
                end_x = max(self.drawing_start.x(), self.drawing_current.x())
                end_y = max(self.drawing_start.y(), self.drawing_current.y())
                
                # Рисуем полупрозрачный прямоугольник
                pen = QPen(QColor(255, 0, 0), 2, Qt.DashLine)
                painter.setPen(pen)
                painter.setBrush(QColor(255, 0, 0, 50))  # Полупрозрачный красный
                painter.drawRect(QRect(start_x, start_y, end_x - start_x, end_y - start_y))
            
        except Exception as e:
            painter.drawText(QRect(0, 0, self.width(), self.height()), 
                           Qt.AlignCenter, f"Ошибка отрисовки: {e}")
    
    def mousePressEvent(self, event):
        """Обработка клика мыши для выбора элемента или начала рисования."""
        if not self.pdf_doc:
            return
        
        if self.drawing_mode:
            # Начинаем рисование bbox
            if event.button() == Qt.LeftButton:
                self.drawing_start = event.pos()
                self.drawing_current = event.pos()
                self.update()
        else:
            # Выбор элемента
            if not self.elements:
                return
            
            click_x = event.x()
            click_y = event.y()
            
            # Получаем размеры PDF страницы
            page = self.pdf_doc[self.current_page]
            pdf_width_pts = page.rect.width
            pdf_height_pts = page.rect.height
            
            # Коэффициенты масштабирования
            scale_x = self.scale / self.render_scale
            scale_y = self.scale / self.render_scale
            
            # Ищем элемент, на который кликнули
            # page_number в разметке - 1-based (1, 2, 3, ...)
            # self.current_page - 0-based (0, 1, 2, ...)
            page_elements = [
                e for e in self.elements 
                if e.get("page_number") == self.current_page + 1
            ]
            
            # Проверяем клики с конца списка (верхние элементы имеют приоритет)
            for elem in reversed(page_elements):
                bbox = elem.get("bbox")
                if not bbox or len(bbox) != 4:
                    continue
                
                x0_bbox, y0_bbox, x1_bbox, y1_bbox = bbox
                
                # Конвертируем координаты
                x0 = x0_bbox * scale_x
                y0 = y0_bbox * scale_y
                x1 = x1_bbox * scale_x
                y1 = y1_bbox * scale_y
                
                # Проверяем, попадает ли клик в прямоугольник
                if x0 <= click_x <= x1 and y0 <= click_y <= y1:
                    # Проверяем, нажат ли Shift для множественного выделения
                    is_shift_pressed = event.modifiers() & Qt.ShiftModifier
                    
                    self.selected_element_id = elem.get("id")
                    # Используем только multi-сигнал, он обрабатывает оба случая
                    self.element_selected_multi.emit(elem, is_shift_pressed)
                    # Для обратной совместимости также отправляем обычный сигнал
                    self.element_selected.emit(elem)
                    self.update()
                    break
    
    def mouseDoubleClickEvent(self, event):
        """Обработка двойного клика мыши для открытия редактора элемента."""
        if not self.pdf_doc or self.drawing_mode:
            return
        
        if not self.elements:
            return
        
        click_x = event.x()
        click_y = event.y()
        
        # Получаем размеры PDF страницы
        page = self.pdf_doc[self.current_page]
        pdf_width_pts = page.rect.width
        pdf_height_pts = page.rect.height
        
        # Коэффициенты масштабирования
        scale_x = self.scale / self.render_scale
        scale_y = self.scale / self.render_scale
        
        # Ищем элемент, на который кликнули
        # page_number в разметке - 1-based (1, 2, 3, ...)
        # self.current_page - 0-based (0, 1, 2, ...)
        page_elements = [
            e for e in self.elements 
            if e.get("page_number") == self.current_page + 1
        ]
        
        # Проверяем клики с конца списка (верхние элементы имеют приоритет)
        for elem in reversed(page_elements):
            bbox = elem.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            
            x0_bbox, y0_bbox, x1_bbox, y1_bbox = bbox
            
            # Конвертируем координаты
            x0 = x0_bbox * scale_x
            y0 = y0_bbox * scale_y
            x1 = x1_bbox * scale_x
            y1 = y1_bbox * scale_y
            
            # Проверяем, попадает ли клик в прямоугольник
            if x0 <= click_x <= x1 and y0 <= click_y <= y1:
                self.selected_element_id = elem.get("id")
                self.element_selected.emit(elem)
                self.element_double_clicked.emit(elem)
                self.update()
                break
    
    def mouseMoveEvent(self, event):
        """Обработка движения мыши при рисовании."""
        if self.drawing_mode and self.drawing_start:
            self.drawing_current = event.pos()
            self.update()
    
    def mouseReleaseEvent(self, event):
        """Обработка отпускания кнопки мыши - завершение рисования."""
        if self.drawing_mode and self.drawing_start and event.button() == Qt.LeftButton:
            if not self.current_pixmap or not self.pdf_doc:
                self.drawing_start = None
                self.drawing_current = None
                return
            
            # Получаем координаты прямоугольника в координатах изображения (scale)
            start_x = min(self.drawing_start.x(), self.drawing_current.x())
            start_y = min(self.drawing_start.y(), self.drawing_current.y())
            end_x = max(self.drawing_start.x(), self.drawing_current.x())
            end_y = max(self.drawing_start.y(), self.drawing_current.y())
            
            # Проверяем, что прямоугольник не слишком маленький
            if abs(end_x - start_x) < 10 or abs(end_y - start_y) < 10:
                self.drawing_start = None
                self.drawing_current = None
                self.update()
                return
            
            # Конвертируем координаты из scale в render_scale
            # Координаты в изображении при scale, нужно перевести в render_scale
            scale_factor = self.render_scale / self.scale
            
            x0_bbox = start_x * scale_factor
            y0_bbox = start_y * scale_factor
            x1_bbox = end_x * scale_factor
            y1_bbox = end_y * scale_factor
            
            # Ограничиваем координаты размерами изображения при render_scale
            page = self.pdf_doc[self.current_page]
            pdf_width_pts = page.rect.width
            pdf_height_pts = page.rect.height
            max_width = pdf_width_pts * self.render_scale
            max_height = pdf_height_pts * self.render_scale
            
            x0_bbox = max(0, min(x0_bbox, max_width))
            y0_bbox = max(0, min(y0_bbox, max_height))
            x1_bbox = max(0, min(x1_bbox, max_width))
            y1_bbox = max(0, min(y1_bbox, max_height))
            
            # Отправляем сигнал с координатами в системе render_scale
            self.bbox_drawn.emit([x0_bbox, y0_bbox, x1_bbox, y1_bbox])
            
            # Сбрасываем состояние рисования
            self.drawing_start = None
            self.drawing_current = None
            self.update()
    
    def set_selected_element(self, element_id: Optional[str]):
        """Установить выбранный элемент."""
        self.selected_element_id = element_id
        self.update()


class AnnotationTool(QMainWindow):
    """Главное окно инструмента разметки."""
    
    def __init__(self):
        super().__init__()
        self.pdf_path = None
        self.source_file_path = None  # Исходный файл (PDF или DOCX)
        self.temp_pdf_path = None  # Временный PDF для DOCX
        self.elements = []
        self.current_order = 0
        
        # Определяем директорию скрипта для правильных путей
        self.script_dir = Path(__file__).parent
        self.annotations_dir = self.script_dir / "annotations"
        self.documents_dir = self.script_dir / "documents"
        
        self.init_ui()
        
    def init_ui(self):
        """Инициализация интерфейса."""
        self.setWindowTitle("Инструмент разметки документов (PyQt5)")
        self.setGeometry(100, 100, 1400, 900)
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Главный layout
        main_layout = QHBoxLayout(central_widget)
        
        # Создаем splitter для разделения на панели
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Левая панель - просмотр PDF
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Панель управления страницами
        page_control = QHBoxLayout()
        self.prev_btn = QPushButton("◀ Предыдущая")
        self.prev_btn.clicked.connect(self.prev_page)
        self.page_label = QLabel("Страница 1 из 1")
        self.next_btn = QPushButton("Следующая ▶")
        self.next_btn.clicked.connect(self.next_page)
        
        page_control.addWidget(self.prev_btn)
        page_control.addWidget(self.page_label)
        page_control.addWidget(self.next_btn)
        left_layout.addLayout(page_control)
        
        # Виджет просмотра PDF с прокруткой
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)  # Виджет будет изменять размер вместе с областью прокрутки
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        self.pdf_viewer = PDFImageViewer()
        self.pdf_viewer.element_selected.connect(self.on_element_selected)
        self.pdf_viewer.element_selected_multi.connect(self.on_element_selected_multi)
        self.pdf_viewer.element_double_clicked.connect(self.on_element_double_clicked)
        self.pdf_viewer.bbox_drawn.connect(self.on_bbox_drawn)
        
        scroll_area.setWidget(self.pdf_viewer)
        left_layout.addWidget(scroll_area)
        
        # Кнопка режима рисования
        draw_btn_layout = QHBoxLayout()
        self.draw_bbox_btn = QPushButton("✏️ Рисовать BBox")
        self.draw_bbox_btn.setCheckable(True)
        self.draw_bbox_btn.toggled.connect(self.toggle_drawing_mode)
        draw_btn_layout.addWidget(self.draw_bbox_btn)
        draw_btn_layout.addStretch()
        left_layout.addLayout(draw_btn_layout)
        
        splitter.addWidget(left_panel)
        
        # Правая панель - редактирование
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Вкладки
        self.tabs = QTabWidget()
        
        # Вкладка: Список элементов
        elements_tab = QWidget()
        elements_layout = QVBoxLayout(elements_tab)
        
        # Список элементов (с поддержкой множественного выбора)
        self.elements_list = QListWidget()
        self.elements_list.setSelectionMode(QListWidget.ExtendedSelection)  # Множественный выбор (Ctrl+Click, Shift+Click)
        self.elements_list.itemSelectionChanged.connect(self.on_list_selection_changed)
        self.elements_list.itemDoubleClicked.connect(self.on_list_item_double_clicked)
        elements_layout.addWidget(QLabel("Элементы разметки (Ctrl+Click или Shift+Click для множественного выбора):"))
        elements_layout.addWidget(self.elements_list)
        
        # Кнопки управления элементами
        elem_buttons = QHBoxLayout()
        self.edit_btn = QPushButton("Редактировать")
        self.edit_btn.clicked.connect(self.edit_selected_element)
        self.delete_btn = QPushButton("Удалить")
        self.delete_btn.clicked.connect(self.delete_selected_element)
        self.unite_btn = QPushButton("🔗 Объединить")
        self.unite_btn.clicked.connect(self.unite_selected_elements)
        self.set_parent_btn = QPushButton("👨‍👩‍👧 Назначить родителя")
        self.set_parent_btn.clicked.connect(self.set_parent_for_selected)
        elem_buttons.addWidget(self.edit_btn)
        elem_buttons.addWidget(self.delete_btn)
        elem_buttons.addWidget(self.unite_btn)
        elem_buttons.addWidget(self.set_parent_btn)
        elements_layout.addLayout(elem_buttons)
        
        self.tabs.addTab(elements_tab, "Элементы")
        
        # Вкладка: Добавить элемент
        add_tab = QWidget()
        add_layout = QVBoxLayout(add_tab)
        
        form = QFormLayout()
        
        self.elem_type_combo = QComboBox()
        self.elem_type_combo.addItems(ELEMENT_TYPES)
        form.addRow("Тип:", self.elem_type_combo)
        
        self.elem_page_spin = QSpinBox()
        self.elem_page_spin.setMinimum(1)
        self.elem_page_spin.setMaximum(1000)
        form.addRow("Страница:", self.elem_page_spin)
        
        self.elem_content_text = QTextEdit()
        self.elem_content_text.setMaximumHeight(100)
        form.addRow("Содержимое:", self.elem_content_text)
        
        self.elem_parent_combo = QComboBox()
        form.addRow("Родитель:", self.elem_parent_combo)
        
        bbox_group = QGroupBox("Координаты (bbox)")
        bbox_layout = QFormLayout()
        
        self.bbox_x0 = QDoubleSpinBox()
        self.bbox_x0.setMaximum(100000)
        self.bbox_y0 = QDoubleSpinBox()
        self.bbox_y0.setMaximum(100000)
        self.bbox_x1 = QDoubleSpinBox()
        self.bbox_x1.setMaximum(100000)
        self.bbox_y1 = QDoubleSpinBox()
        self.bbox_y1.setMaximum(100000)
        
        bbox_layout.addRow("x0:", self.bbox_x0)
        bbox_layout.addRow("y0:", self.bbox_y0)
        bbox_layout.addRow("x1:", self.bbox_x1)
        bbox_layout.addRow("y1:", self.bbox_y1)
        bbox_group.setLayout(bbox_layout)
        
        add_layout.addLayout(form)
        add_layout.addWidget(bbox_group)
        
        self.add_btn = QPushButton("➕ Добавить элемент")
        self.add_btn.clicked.connect(self.add_element)
        add_layout.addWidget(self.add_btn)
        
        add_layout.addStretch()
        
        self.tabs.addTab(add_tab, "Добавить")
        
        right_layout.addWidget(self.tabs)
        
        # Быстрый выбор существующих разметок
        quick_load_group = QGroupBox("Быстрая загрузка разметки")
        quick_load_layout = QHBoxLayout()
        self.quick_load_combo = QComboBox()
        self.quick_load_combo.addItem("-- Выберите разметку --", None)
        self.refresh_quick_load_list()
        quick_load_btn = QPushButton("📥 Загрузить")
        quick_load_btn.clicked.connect(self.quick_load_annotation)
        refresh_btn = QPushButton("🔄 Обновить список")
        refresh_btn.clicked.connect(self.refresh_quick_load_list)
        quick_load_layout.addWidget(self.quick_load_combo)
        quick_load_layout.addWidget(quick_load_btn)
        quick_load_layout.addWidget(refresh_btn)
        quick_load_group.setLayout(quick_load_layout)
        right_layout.addWidget(quick_load_group)
        
        # Кнопки управления файлами
        file_buttons = QHBoxLayout()
        load_btn = QPushButton("📂 Загрузить PDF/DOCX")
        load_btn.clicked.connect(self.load_pdf)
        load_ann_btn = QPushButton("📥 Загрузить разметку...")
        load_ann_btn.clicked.connect(self.load_annotation)
        auto_btn = QPushButton("✨ Авторазметка")
        auto_btn.clicked.connect(self.create_auto_annotation)
        extract_gt_btn = QPushButton("📝 Извлечь GT текст")
        extract_gt_btn.clicked.connect(self.extract_ground_truth_text)
        save_btn = QPushButton("💾 Сохранить")
        save_btn.clicked.connect(self.save_annotation)
        
        file_buttons.addWidget(load_btn)
        file_buttons.addWidget(load_ann_btn)
        file_buttons.addWidget(auto_btn)
        file_buttons.addWidget(extract_gt_btn)
        file_buttons.addWidget(save_btn)
        right_layout.addLayout(file_buttons)
        
        splitter.addWidget(right_panel)
        
        # Устанавливаем пропорции
        splitter.setSizes([1000, 400])
        
    def load_pdf(self):
        """Загрузка PDF или DOCX файла."""
        # Устанавливаем начальную директорию - папка documents, если существует
        initial_dir = str(self.documents_dir) if self.documents_dir.exists() else ""
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Выберите файл (PDF или DOCX)", 
            initial_dir,
            "Все документы (*.pdf *.docx);;PDF Files (*.pdf);;DOCX Files (*.docx);;All Files (*.*)"
        )
        
        if file_path:
            file_path_obj = Path(file_path)
            self.source_file_path = file_path_obj
            
            # Если это DOCX, конвертируем в PDF
            if file_path_obj.suffix.lower() == '.docx':
                try:
                    # Создаем временный PDF файл
                    temp_dir = tempfile.gettempdir()
                    temp_pdf = Path(temp_dir) / f"{file_path_obj.stem}_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                    
                    # Показываем прогресс
                    QMessageBox.information(self, "Конвертация", 
                                           f"Конвертация DOCX в PDF...\nЭто может занять некоторое время.")
                    
                    # Конвертируем DOCX в PDF
                    convert_docx_to_pdf(file_path_obj, temp_pdf)
                    
                    if not temp_pdf.exists():
                        QMessageBox.critical(self, "Ошибка", "Не удалось конвертировать DOCX в PDF")
                        return
                    
                    self.temp_pdf_path = temp_pdf
                    self.pdf_path = temp_pdf
                    
                    if self.pdf_viewer.load_pdf(self.pdf_path, is_docx=True, temp_pdf_path=temp_pdf):
                        total_pages = self.pdf_viewer.get_total_pages()
                        self.page_label.setText(f"Страница 1 из {total_pages} (DOCX)")
                        self.elem_page_spin.setMaximum(total_pages)
                        self.elem_page_spin.setValue(1)
                        self.update_navigation()
                        QMessageBox.information(self, "Успех", 
                                               f"DOCX файл успешно загружен и конвертирован в PDF.\n"
                                               f"Временный PDF: {temp_pdf}")
                except Exception as e:
                    QMessageBox.critical(self, "Ошибка", f"Ошибка при конвертации DOCX: {e}")
                    return
            else:
                # Это PDF файл
                self.pdf_path = file_path_obj
                self.temp_pdf_path = None
                if self.pdf_viewer.load_pdf(self.pdf_path):
                    total_pages = self.pdf_viewer.get_total_pages()
                    self.page_label.setText(f"Страница 1 из {total_pages}")
                    self.elem_page_spin.setMaximum(total_pages)
                    self.elem_page_spin.setValue(1)
                    self.update_navigation()
    
    def refresh_quick_load_list(self):
        """Обновляет список доступных разметок в выпадающем списке."""
        self.quick_load_combo.clear()
        self.quick_load_combo.addItem("-- Выберите разметку --", None)
        
        if self.annotations_dir.exists():
            json_files = sorted(self.annotations_dir.glob("*_annotation.json"))
            for json_file in json_files:
                display_name = json_file.stem.replace("_annotation", "")
                self.quick_load_combo.addItem(display_name, str(json_file))
    
    def quick_load_annotation(self):
        """Быстрая загрузка разметки из выпадающего списка."""
        json_path = self.quick_load_combo.currentData()
        if not json_path:
            QMessageBox.warning(self, "Предупреждение", "Выберите разметку из списка")
            return
        
        self.load_annotation_from_file(Path(json_path))
    
    def load_annotation_from_file(self, json_path: Path):
        """Загружает разметку из указанного файла."""
        try:
            # Загружаем JSON
            with open(json_path, 'r', encoding='utf-8') as f:
                annotation_data = json.load(f)
            
            # Извлекаем элементы
            elements = annotation_data.get("elements", [])
            if not elements:
                QMessageBox.warning(self, "Предупреждение", "Файл разметки не содержит элементов")
                return
            
            # Загружаем элементы
            self.elements = elements
            self.current_order = max((e.get("order", 0) for e in elements), default=-1) + 1
            
            # Пересчитываем parent_id для таблиц и изображений, чтобы они подвязывались к заголовкам
            # (а не к caption или другим элементам)
            self._fix_table_image_parents()
            
            # Обновляем viewer
            self.pdf_viewer.set_elements(elements)
            self.update_elements_list()
            self.update_parent_combo()
            
            # Пытаемся найти и загрузить соответствующий файл (PDF или DOCX)
            source_file = annotation_data.get("source_file", "")
            file_loaded = False
            if source_file:
                # Пробуем сначала как относительный путь (от директории скрипта)
                source_file_path = self.script_dir / source_file
                if not source_file_path.exists():
                    # Если не найден, пробуем как абсолютный путь
                    source_file_path = Path(source_file)
                
                if source_file_path.exists():
                    self.source_file_path = source_file_path
                    
                    # Если это DOCX, конвертируем в PDF
                    if source_file_path.suffix.lower() == '.docx':
                        try:
                            temp_dir = tempfile.gettempdir()
                            temp_pdf = Path(temp_dir) / f"{source_file_path.stem}_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                            convert_docx_to_pdf(source_file_path, temp_pdf)
                            if temp_pdf.exists():
                                self.temp_pdf_path = temp_pdf
                                self.pdf_path = temp_pdf
                                if self.pdf_viewer.load_pdf(self.pdf_path, is_docx=True, temp_pdf_path=temp_pdf):
                                    total_pages = self.pdf_viewer.get_total_pages()
                                    self.page_label.setText(f"Страница 1 из {total_pages} (DOCX)")
                                    self.elem_page_spin.setMaximum(total_pages)
                                    self.elem_page_spin.setValue(1)
                                    self.update_navigation()
                                    file_loaded = True
                            else:
                                QMessageBox.critical(self, "Ошибка", "Не удалось конвертировать DOCX в PDF")
                        except Exception as e:
                            QMessageBox.critical(self, "Ошибка", f"Ошибка при конвертации DOCX: {e}")
                    else:
                        # Это PDF файл
                        self.pdf_path = source_file_path
                        self.temp_pdf_path = None
                        if self.pdf_viewer.load_pdf(self.pdf_path):
                            total_pages = self.pdf_viewer.get_total_pages()
                            self.page_label.setText(f"Страница 1 из {total_pages}")
                            self.elem_page_spin.setMaximum(total_pages)
                            self.elem_page_spin.setValue(1)
                            self.update_navigation()
                            file_loaded = True
            
            if not file_loaded:
                # Пытаемся найти файл по имени файла разметки
                # Пробуем DOCX и PDF
                base_name = json_path.stem.replace("_annotation", "").replace(".docx", "").replace(".pdf", "")
                
                # Ищем в разных местах
                possible_paths = [
                    self.documents_dir / f"{base_name}.docx",
                    self.documents_dir / f"{base_name}.pdf",
                    json_path.parent.parent / "test_files_for_metrics" / f"{base_name}.pdf",
                    json_path.parent / f"{base_name}.pdf",
                    Path("test_files_for_metrics") / f"{base_name}.pdf",
                    Path("experiments/metrics/test_files_for_metrics") / f"{base_name}.pdf",
                    Path(f"{base_name}.pdf"),
                ]
                
                file_found = False
                for file_path in possible_paths:
                    if file_path.exists():
                        self.source_file_path = file_path
                        
                        # Если это DOCX, конвертируем в PDF
                        if file_path.suffix.lower() == '.docx':
                            try:
                                temp_dir = tempfile.gettempdir()
                                temp_pdf = Path(temp_dir) / f"{file_path.stem}_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                                convert_docx_to_pdf(file_path, temp_pdf)
                                if temp_pdf.exists():
                                    self.temp_pdf_path = temp_pdf
                                    self.pdf_path = temp_pdf
                                    if self.pdf_viewer.load_pdf(self.pdf_path, is_docx=True, temp_pdf_path=temp_pdf):
                                        total_pages = self.pdf_viewer.get_total_pages()
                                        self.page_label.setText(f"Страница 1 из {total_pages} (DOCX)")
                                        self.elem_page_spin.setMaximum(total_pages)
                                        self.elem_page_spin.setValue(1)
                                        self.update_navigation()
                                        file_found = True
                                        break
                            except Exception as e:
                                print(f"Ошибка при конвертации DOCX: {e}")
                                continue
                        else:
                            # Это PDF файл
                            self.pdf_path = file_path
                            self.temp_pdf_path = None
                            if self.pdf_viewer.load_pdf(self.pdf_path):
                                total_pages = self.pdf_viewer.get_total_pages()
                                self.page_label.setText(f"Страница 1 из {total_pages}")
                                self.elem_page_spin.setMaximum(total_pages)
                                self.elem_page_spin.setValue(1)
                                self.update_navigation()
                                file_found = True
                                break
                
                if not file_found:
                    QMessageBox.information(
                        self, "Информация",
                        f"Разметка загружена ({len(elements)} элементов).\n"
                        f"Файл (PDF или DOCX) не найден автоматически.\n"
                        f"Загрузите файл вручную через кнопку 'Загрузить PDF'."
                    )
            
            # Статистика
            doc_id = annotation_data.get("document_id", "unknown")
            annotator = annotation_data.get("annotator", "unknown")
            version = annotation_data.get("annotation_version", "unknown")
            
            stats = annotation_data.get("statistics", {})
            total_elements = stats.get("total_elements", len(elements))
            total_pages_ann = stats.get("total_pages", "?")
            
            QMessageBox.information(
                self, "Разметка загружена",
                f"Документ: {doc_id}\n"
                f"Разметчик: {annotator}\n"
                f"Версия схемы: {version}\n"
                f"Элементов: {total_elements}\n"
                f"Страниц: {total_pages_ann}"
            )
            
        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Ошибка", f"Неверный формат JSON: {e}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить разметку: {e}")
    
    def load_annotation(self):
        """Загрузка существующей разметки из JSON файла через диалог.
        
        Примечание: эта функция загружает JSON файлы аннотаций, а не DOCX/PDF файлы.
        Для загрузки DOCX/PDF используйте кнопку 'Загрузить PDF/DOCX'.
        """
        default_path = str(self.annotations_dir) if self.annotations_dir.exists() else ""
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите файл разметки (JSON)", default_path, "JSON Files (*.json);;All Files (*.*)"
        )
        
        if not file_path:
            return
        
        self.load_annotation_from_file(Path(file_path))
    
    def create_auto_annotation(self):
        """Создание автоматической разметки с улучшенной обработкой."""
        if not self.pdf_path:
            QMessageBox.warning(self, "Предупреждение", "Сначала загрузите PDF файл")
            return
        
        try:
            pipeline = Pipeline()
            langchain_doc = Document(page_content="", metadata={"source": str(self.pdf_path)})
            parsed = pipeline.parse(langchain_doc)
            
            # Создаём элементы с сохранением уровней заголовков
            raw_elements = []
            type_counts = {}  # Для отладки
            
            for elem in parsed.elements:
                elem_type = elem.type.value.lower()
                
                # Отладка: считаем типы элементов
                type_counts[elem_type] = type_counts.get(elem_type, 0) + 1
                
                # Сохраняем уровни заголовков (не конвертируем все в header_1)
                # Но если заголовок неопределённого уровня, используем header_1
                if elem_type.startswith('header_'):
                    # Проверяем, что уровень валидный (header_1 - header_6)
                    header_level = elem_type.replace('header_', '')
                    if not header_level.isdigit() or int(header_level) < 1 or int(header_level) > 6:
                        elem_type = 'header_1'
                
                # Конвертируем page_num из 0-based (0,1,2...) в 1-based (1,2,3...)
                page_num_0based = elem.metadata.get("page_num")
                page_number = None
                if page_num_0based is not None:
                    page_number = page_num_0based + 1  # Конвертируем в 1-based
                
                element_data = {
                    "type": elem_type,
                    "content": elem.content,
                    "parent_id": elem.parent_id,
                    "page_number": page_number,
                    "bbox": elem.metadata.get("bbox"),
                    "metadata": {}
                }
                
                # Таблицы: сохраняем HTML в metadata.table_structure
                if elem_type == "table" and elem.content:
                    # Парсим HTML таблицу для извлечения ячеек
                    cells = self._html_table_to_cells(elem.content)
                    element_data["metadata"]["table_structure"] = {
                        "html": elem.content,
                        "cells": cells
                    }
                
                # Изображения: сохраняем base64 из metadata
                if elem_type == "image":
                    img_b64 = elem.metadata.get("image_data", "")
                    if img_b64:
                        element_data["metadata"]["image_data"] = img_b64
                        element_data["metadata"]["image_format"] = elem.metadata.get("image_format", "png")
                        element_data["metadata"]["image_width"] = elem.metadata.get("image_width")
                        element_data["metadata"]["image_height"] = elem.metadata.get("image_height")
                raw_elements.append(element_data)
            
            # Выводим статистику типов для отладки
            print("\n=== Статистика типов элементов от парсера ===")
            for elem_type, count in sorted(type_counts.items()):
                print(f"  {elem_type}: {count}")
            print(f"  Всего: {len(raw_elements)}")
            
            # Проверяем наличие формул и элементов списка
            formulas_found = type_counts.get('formula', 0)
            list_items_found = type_counts.get('list_item', 0)
            if formulas_found == 0:
                print("  ⚠️  ВНИМАНИЕ: Формулы не найдены парсером!")
            if list_items_found == 0:
                print("  ⚠️  ВНИМАНИЕ: Элементы списка не найдены парсером!")
            
            # Улучшенная сортировка: сначала по странице, затем по координатам Y
            def get_sort_key(elem):
                page = elem.get("page_number", 0)
                bbox = elem.get("bbox")
                if bbox and len(bbox) >= 4:
                    y_center = (bbox[1] + bbox[3]) / 2
                    return (page, y_center)
                # Если нет координат, используем порядок в исходном списке
                return (page, float('inf'))
            
            raw_elements.sort(key=get_sort_key)
            
            # Создаём финальные элементы с правильными order и id
            elements = []
            for i, elem in enumerate(raw_elements):
                element_data = {
                    "id": f"elem_{i:04d}",
                    "type": elem["type"],
                    "content": elem["content"],
                    "parent_id": elem["parent_id"],
                    "order": i,
                    "page_number": elem["page_number"],
                    "bbox": elem["bbox"],
                    "metadata": elem["metadata"]
                }
                elements.append(element_data)
            
            # Улучшаем parent_id для элементов, у которых он не определён или некорректен
            self._improve_parent_ids(elements)
            
            self.elements = elements
            self.current_order = len(elements)
            
            # Дополнительно исправляем parent_id для таблиц и изображений
            # (чтобы они точно подвязывались к заголовкам, а не к caption)
            self._fix_table_image_parents()
            
            self.pdf_viewer.set_elements(elements)
            self.update_elements_list()
            
            # Статистика
            header_count = sum(1 for e in elements if e["type"].startswith("header_"))
            text_count = sum(1 for e in elements if e["type"] == "text")
            table_count = sum(1 for e in elements if e["type"] == "table")
            formula_count = sum(1 for e in elements if e["type"] == "formula")
            
            QMessageBox.information(
                self, "Успех", 
                f"Создано {len(elements)} элементов:\n"
                f"• Заголовки: {header_count}\n"
                f"• Текст: {text_count}\n"
                f"• Таблицы: {table_count}\n"
                f"• Формулы: {formula_count}\n"
                f"ID: elem_0000 - elem_{len(elements)-1:04d}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать разметку: {e}")
    
    def _html_table_to_cells(self, html: str) -> List[Dict[str, Any]]:
        """Парсит HTML-таблицу и возвращает массив ячеек [{row, col, content, rowspan, colspan}]."""
        import re
        cells = []
        try:
            row_idx = 0
            for tr_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE):
                tr_content = tr_match.group(1)
                col_idx = 0
                for cell_match in re.finditer(
                    r"<(td|th)[^>]*?(?:rowspan=[\"']?(\d+)[\"']?)?[^>]*?(?:colspan=[\"']?(\d+)[\"']?)?[^>]*>(.*?)</\1>",
                    tr_content,
                    re.DOTALL | re.IGNORECASE,
                ):
                    tag = cell_match.group(1)
                    rowspan = int(cell_match.group(2)) if cell_match.group(2) else 1
                    colspan = int(cell_match.group(3)) if cell_match.group(3) else 1
                    text = re.sub(r"<[^>]+>", "", cell_match.group(4)).strip()
                    cells.append({
                        "row": row_idx,
                        "col": col_idx,
                        "content": text,
                        "rowspan": rowspan,
                        "colspan": colspan,
                    })
                    col_idx += 1
                row_idx += 1
        except Exception:
            pass
        return cells
    
    def _improve_parent_ids(self, elements: List[Dict[str, Any]]):
        """Улучшает parent_id для элементов, используя иерархию заголовков."""
        # Создаём словарь для быстрого доступа
        id_to_elem = {elem["id"]: elem for elem in elements}
        
        # Стек заголовков для отслеживания иерархии
        header_stack = []  # [(id, level, page, order), ...]
        
        for elem in elements:
            elem_type = elem["type"]
            elem_id = elem["id"]
            page_num = elem.get("page_number", 1)  # 1-based по умолчанию
            order = elem.get("order", 0)
            
            # Если это заголовок
            if elem_type.startswith("header_") or elem_type == "title":
                # Определяем уровень заголовка
                if elem_type == "title":
                    level = 0
                    # Title не имеет родителя
                    parent_id = None
                elif elem_type.startswith("header_"):
                    level = int(elem_type.replace("header_", ""))
                    # Удаляем из стека все заголовки с уровнем >= текущего (они не могут быть родителями)
                    header_stack = [h for h in header_stack if h[1] < level]
                    
                    # Находим родителя по правилам:
                    # - Header1 -> title (level 0)
                    # - Header2 -> Header1 (level 1)
                    # - Header3 -> Header2 (level 2)
                    # и т.д.
                    parent_id = None
                    if header_stack:
                        # Ищем последний заголовок с уровнем на 1 меньше текущего
                        target_level = level - 1
                        for h in reversed(header_stack):
                            if h[1] == target_level:
                                parent_id = h[0]
                                break
                        # Если не нашли нужного уровня, берем последний заголовок с меньшим уровнем
                        if not parent_id and header_stack:
                            parent_id = header_stack[-1][0]
                else:
                    level = 1
                    parent_id = None
                
                # Обновляем parent_id элемента
                elem["parent_id"] = parent_id
                
                # Добавляем текущий заголовок в стек
                header_stack.append((elem_id, level, page_num, order))
            
            # Для обычных элементов (text, table, image, caption, etc.)
            else:
                is_table_or_image = elem_type in ("table", "image")
                is_caption = elem_type == "caption"
                
                # Для таблиц и изображений - сначала ищем Caption, потом заголовок
                if is_table_or_image:
                    # Сначала ищем Caption перед этим элементом на той же странице
                    same_page_elements_before = [
                        e for e in elements
                        if e.get("page_number") == page_num and e.get("order", 0) < order
                    ]
                    same_page_elements_before.sort(key=lambda x: x.get("order", 0))
                    
                    # Ищем последний Caption перед элементом
                    captions_before = [
                        e for e in same_page_elements_before
                        if e.get("type") == "caption"
                    ]
                    
                    # Проверяем, есть ли между последним Caption и элементом другие Table/Image
                    has_table_image_between = False
                    if captions_before:
                        last_caption_order = captions_before[-1].get("order", 0)
                        # Проверяем элементы между последним Caption и текущим элементом
                        elements_between = [
                            e for e in same_page_elements_before
                            if e.get("order", 0) > last_caption_order and e.get("type") in ("table", "image")
                        ]
                        has_table_image_between = len(elements_between) > 0
                    
                    # Если есть Caption перед элементом и между ними нет других Table/Image - подвязываемся к нему
                    if captions_before and not has_table_image_between:
                        elem["parent_id"] = captions_before[-1]["id"]
                    else:
                        # Если нет Caption перед элементом или между ними есть Table/Image, ищем Caption после элемента
                        same_page_elements_after = [
                            e for e in elements
                            if e.get("page_number") == page_num and e.get("order", 0) > order
                        ]
                        captions_after = [
                            e for e in same_page_elements_after
                            if e.get("type") == "caption"
                        ]
                        if captions_after:
                            # Нашли Caption после элемента - подвязываем к нему
                            captions_after.sort(key=lambda x: x.get("order", 0))
                            elem["parent_id"] = captions_after[0]["id"]
                        else:
                            # Если нет Caption вообще, ищем заголовок
                            same_page_headers = [
                                h for h in header_stack
                                if h[2] == page_num and h[3] < order
                            ]
                            if same_page_headers:
                                elem["parent_id"] = same_page_headers[-1][0]
                            elif header_stack:
                                elem["parent_id"] = header_stack[-1][0]
                            else:
                                elem["parent_id"] = None
                
                # Для caption - проверяем, не подвязан ли он к таблице/изображению
                # Если подвязан к не-заголовку, ищем ближайший заголовок
                elif is_caption:
                    current_parent = elem.get("parent_id")
                    if current_parent and current_parent in id_to_elem:
                        parent_elem = id_to_elem[current_parent]
                        parent_type = parent_elem.get("type", "")
                        # Если родитель - заголовок, оставляем как есть
                        if parent_type.startswith("header_") or parent_type == "title":
                            continue
                        # Если родитель - таблица/изображение, ищем заголовок
                    
                    # Ищем ближайший заголовок
                    same_page_headers = [
                        h for h in header_stack
                        if h[2] == page_num and h[3] < order
                    ]
                    if same_page_headers:
                        elem["parent_id"] = same_page_headers[-1][0]
                    elif header_stack:
                        elem["parent_id"] = header_stack[-1][0]
                    else:
                        elem["parent_id"] = None
                
                # Для остальных элементов (text, formula, list_item, etc.)
                else:
                    # Проверяем, валиден ли текущий parent_id
                    current_parent = elem.get("parent_id")
                    if current_parent and current_parent in id_to_elem:
                        # Проверяем, что родитель действительно заголовок
                        parent_elem = id_to_elem[current_parent]
                        parent_type = parent_elem.get("type", "")
                        if parent_type.startswith("header_") or parent_type == "title":
                            # parent_id валиден, оставляем как есть
                            continue
                    
                    # Если parent_id не установлен или некорректен, находим правильного родителя
                    same_page_headers = [
                        h for h in header_stack
                        if h[2] == page_num and h[3] < order
                    ]
                    if same_page_headers:
                        elem["parent_id"] = same_page_headers[-1][0]
                    elif header_stack:
                        elem["parent_id"] = header_stack[-1][0]
                    else:
                        elem["parent_id"] = None
    
    def _fix_table_image_parents(self):
        """Исправляет parent_id для таблиц и изображений: сначала ищем Caption, потом заголовок."""
        header_types = {'title', 'header_1', 'header_2', 'header_3', 'header_4', 'header_5', 'header_6'}
        id_to_elem = {elem["id"]: elem for elem in self.elements}
        
        for elem in self.elements:
            elem_type = elem.get("type", "")
            if elem_type not in ("table", "image"):
                continue
            
            # Проверяем текущий parent_id
            current_parent = elem.get("parent_id")
            if current_parent and current_parent in id_to_elem:
                parent_elem = id_to_elem[current_parent]
                parent_type = parent_elem.get("type", "")
                # Если родитель - Caption или заголовок, оставляем как есть (будет пересчитан ниже)
                if parent_type == "caption" or parent_type in header_types:
                    pass  # Продолжаем проверку
            
            # Находим правильного родителя: сначала Caption, потом заголовок
            page_number = elem.get("page_number", 1)
            order = elem.get("order", 0)
            new_parent_id = self.find_auto_parent_id(elem_type, page_number, order)
            elem["parent_id"] = new_parent_id
    
    def find_auto_parent_id(self, element_type: str, page_number: int, order: int) -> Optional[str]:
        """Автоматически определяет parent_id для нового элемента с учётом иерархии заголовков."""
        header_types = {'title', 'header_1', 'header_2', 'header_3', 'header_4', 'header_5', 'header_6'}
        
        # Сначала ищем заголовки на той же странице, которые идут перед текущим элементом
        same_page_elements = [
            e for e in self.elements 
            if e.get('page_number') == page_number and e.get('order', 0) < order
        ]
        
        # Сортируем по order
        same_page_elements.sort(key=lambda x: x.get('order', 0))
        
        # Ищем заголовки на текущей странице
        same_page_headers = [e for e in same_page_elements if e.get('type', '') in header_types]
        
        # Если это заголовок - ищем родителя по иерархии
        if element_type in header_types:
            # Определяем уровень текущего заголовка
            if element_type == 'title':
                current_level = 0
                # Title не имеет родителя
                return None
            else:
                current_level = int(element_type.replace('header_', ''))
            
            # Правила иерархии:
            # Header1 -> title (level 0)
            # Header2 -> Header1 (level 1)
            # Header3 -> Header2 (level 2)
            # и т.д.
            target_level = current_level - 1
            
            # Сначала ищем на той же странице
            if same_page_headers:
                for elem in reversed(same_page_headers):
                    elem_type = elem.get('type', '')
                    if elem_type == 'title':
                        elem_level = 0
                    else:
                        elem_level = int(elem_type.replace('header_', ''))
                    
                    # Ищем заголовок с уровнем на 1 меньше текущего
                    if elem_level == target_level:
                        return elem.get('id')
            
            # Если на текущей странице нет подходящего родителя, ищем на предыдущих страницах
            prev_page_elements = [
                e for e in self.elements 
                if e.get('page_number', 0) < page_number and e.get('type', '') in header_types
            ]
            if prev_page_elements:
                prev_page_elements.sort(key=lambda x: (x.get('page_number', 0), x.get('order', 0)))
                # Ищем последний заголовок с нужным уровнем
                for elem in reversed(prev_page_elements):
                    elem_type = elem.get('type', '')
                    if elem_type == 'title':
                        elem_level = 0
                    else:
                        elem_level = int(elem_type.replace('header_', ''))
                    
                    if elem_level == target_level:
                        return elem.get('id')
            
            return None
        
        # Для таблиц и изображений - сначала ищем Caption, потом заголовок
        if element_type in ("table", "image"):
            # Сначала ищем Caption перед элементом на той же странице
            same_page_captions_before = [
                e for e in same_page_elements
                if e.get('type', '') == 'caption'
            ]
            
            # Проверяем, есть ли между последним Caption и элементом другие Table/Image
            has_table_image_between = False
            if same_page_captions_before:
                last_caption_order = same_page_captions_before[-1].get('order', 0)
                # Проверяем элементы между последним Caption и текущим элементом
                elements_between = [
                    e for e in same_page_elements
                    if e.get('order', 0) > last_caption_order and e.get('type', '') in ('table', 'image')
                ]
                has_table_image_between = len(elements_between) > 0
            
            # Если есть Caption перед элементом и между ними нет других Table/Image - подвязываемся к нему
            if same_page_captions_before and not has_table_image_between:
                return same_page_captions_before[-1].get('id')
            
            # Если нет Caption перед элементом или между ними есть Table/Image, ищем Caption после элемента
            same_page_elements_after = [
                e for e in self.elements
                if e.get('page_number') == page_number and e.get('order', 0) > order
            ]
            same_page_captions_after = [
                e for e in same_page_elements_after
                if e.get('type', '') == 'caption'
            ]
            if same_page_captions_after:
                # Нашли Caption после элемента - подвязываем к нему
                same_page_captions_after.sort(key=lambda x: x.get('order', 0))
                return same_page_captions_after[0].get('id')
            
            # Если нет Caption вообще, ищем заголовок
            if same_page_headers:
                return same_page_headers[-1].get('id')
            
            # Если на текущей странице нет заголовков, ищем последний заголовок на предыдущих страницах
            prev_page_headers = [
                e for e in self.elements 
                if e.get('page_number', 0) < page_number and e.get('type', '') in header_types
            ]
            if prev_page_headers:
                prev_page_headers.sort(key=lambda x: (x.get('page_number', 0), x.get('order', 0)))
                return prev_page_headers[-1].get('id')
            
            return None
        
        # Для остальных элементов (text, caption, formula, etc.) - ищем последний заголовок
        # Сначала на текущей странице
        if same_page_headers:
            return same_page_headers[-1].get('id')
        
        # Если на текущей странице нет заголовков, ищем последний заголовок на предыдущих страницах
        prev_page_headers = [
            e for e in self.elements 
            if e.get('page_number', 0) < page_number and e.get('type', '') in header_types
        ]
        if prev_page_headers:
            prev_page_headers.sort(key=lambda x: (x.get('page_number', 0), x.get('order', 0)))
            return prev_page_headers[-1].get('id')
        
        return None
    
    def update_children_parent_ids(self, changed_element_id: str, old_type: str, new_type: str):
        """Обновляет parent_id всех дочерних элементов при изменении элемента."""
        header_types = {'title', 'header_1', 'header_2', 'header_3', 'header_4', 'header_5', 'header_6'}
        
        changed_element = next((e for e in self.elements if e['id'] == changed_element_id), None)
        if not changed_element:
            return
        
        page_number = changed_element.get('page_number', 1)  # 1-based
        order = changed_element.get('order', 0)
        
        # Если элемент был заголовком и стал не заголовком
        was_header = old_type in header_types
        is_header = new_type in header_types
        
        if was_header and not is_header:
            # Заголовок стал обычным элементом - нужно найти новый parent для его детей
            for elem in self.elements:
                if elem.get('parent_id') == changed_element_id:
                    elem_page = elem.get('page_number', 1)
                    elem_order = elem.get('order', 0)
                    new_parent_id = self.find_auto_parent_id(elem.get('type', ''), elem_page, elem_order)
                    elem['parent_id'] = new_parent_id
        
        # Если элемент был или стал заголовком - пересчитываем parent_id для всех зависимых элементов
        if was_header or is_header:
            # Пересчитываем parent_id для:
            # 1. Всех дочерних элементов измененного заголовка
            # 2. Всех элементов на той же странице после измененного
            # 3. Всех заголовков, которые должны подвязываться к измененному
            for elem in self.elements:
                if elem.get('id') == changed_element_id:
                    continue
                
                elem_page = elem.get('page_number', 1)
                elem_order = elem.get('order', 0)
                elem_type = elem.get('type', '')
                
                # Если это дочерний элемент измененного заголовка
                if elem.get('parent_id') == changed_element_id:
                    # Пересчитываем parent_id
                    new_parent_id = self.find_auto_parent_id(elem_type, elem_page, elem_order)
                    elem['parent_id'] = new_parent_id
                
                # Если это заголовок на той же или последующих страницах
                elif elem_type in header_types:
                    # Пересчитываем parent_id заголовка (может измениться иерархия)
                    new_parent_id = self.find_auto_parent_id(elem_type, elem_page, elem_order)
                    elem['parent_id'] = new_parent_id
                
                # Если это элемент на той же странице после измененного
                elif elem_page == page_number and elem_order > order:
                    # Для таблиц и изображений - всегда пересчитываем
                    if elem_type in ("table", "image"):
                        new_parent_id = self.find_auto_parent_id(elem_type, elem_page, elem_order)
                        elem['parent_id'] = new_parent_id
                    # Для остальных - пересчитываем только если parent_id был измененный элемент
                    elif elem.get('parent_id') == changed_element_id:
                        new_parent_id = self.find_auto_parent_id(elem_type, elem_page, elem_order)
                        elem['parent_id'] = new_parent_id
        
        # Если изменился тип элемента (не заголовок), пересчитываем parent_id для таблиц/изображений
        # которые могли подвязаться к нему неправильно
        if not was_header and not is_header:
            # Если элемент стал или был таблицей/изображением, пересчитываем его parent_id
            if new_type in ("table", "image") or old_type in ("table", "image"):
                new_parent_id = self.find_auto_parent_id(new_type, page_number, order)
                changed_element['parent_id'] = new_parent_id
    
    def find_insertion_position(self, page_number: int, bbox: list) -> int:
        """Находит правильную позицию для вставки элемента на основе страницы и координат."""
        if not bbox or len(bbox) < 4:
            # Если нет координат, вставляем в конец элементов на той же странице
            same_page_elements = [e for e in self.elements if e.get('page_number') == page_number]
            if same_page_elements:
                max_order = max(e.get('order', 0) for e in same_page_elements)
                return max_order + 1
            return len(self.elements)
        
        y_center = (bbox[1] + bbox[3]) / 2  # Центр по Y
        
        # Находим все элементы на той же странице
        same_page_elements = [
            (i, e) for i, e in enumerate(self.elements)
            if e.get('page_number') == page_number
        ]
        
        if not same_page_elements:
            return len(self.elements)
        
        # Сортируем по order
        same_page_elements.sort(key=lambda x: x[1].get('order', 0))
        
        # Ищем позицию на основе Y координаты
        for idx, (orig_idx, elem) in enumerate(same_page_elements):
            elem_bbox = elem.get('bbox')
            if elem_bbox and len(elem_bbox) >= 4:
                elem_y_center = (elem_bbox[1] + elem_bbox[3]) / 2
                if y_center < elem_y_center:
                    # Вставляем перед этим элементом
                    return elem.get('order', 0)
        
        # Если не нашли, вставляем после последнего элемента на странице
        last_elem = same_page_elements[-1][1]
        return last_elem.get('order', 0) + 1
    
    def add_element(self):
        """Добавление нового элемента с автоматической вставкой в правильную позицию."""
        element_type = self.elem_type_combo.currentText()
        page_number = self.elem_page_spin.value()  # 1-based (как в spinbox)
        
        bbox = [
            self.bbox_x0.value(),
            self.bbox_y0.value(),
            self.bbox_x1.value(),
            self.bbox_y1.value()
        ] if (self.bbox_x0.value(), self.bbox_y0.value(), self.bbox_x1.value(), self.bbox_y1.value()) != (0, 0, 0, 0) else None
        
        # Находим правильную позицию для вставки (используем 0-based для поиска)
        insertion_order = self.find_insertion_position(page_number, bbox)
        
        # Автоматически определяем parent_id, если не выбран вручную
        manual_parent_id = self.elem_parent_combo.currentData() if self.elem_parent_combo.currentData() else None
        auto_parent_id = self.find_auto_parent_id(element_type, page_number, insertion_order)
        
        # Используем ручной выбор, если есть, иначе автоматический
        parent_id = manual_parent_id if manual_parent_id else auto_parent_id
        
        # Подготовка metadata в зависимости от типа элемента
        metadata = {}
        if element_type == "table":
            # Для таблиц: парсим HTML и создаём структуру
            html_content = self.elem_content_text.toPlainText()
            if html_content and "<table" in html_content.lower():
                cells = self._html_table_to_cells(html_content)
                metadata["table_structure"] = {
                    "html": html_content,
                    "cells": cells
                }
        elif element_type == "image":
            # Для изображений: content пустой, данные в metadata
            pass  # Изображения добавляются отдельно через загрузку файла
        
        # Создаём временный ID (будет перенумерован)
        element = {
            "id": f"elem_temp_{len(self.elements)}",
            "type": element_type,
            "content": "" if element_type == "image" else self.elem_content_text.toPlainText(),
            "parent_id": parent_id,
            "order": insertion_order,
            "page_number": page_number,  # 1-based
            "bbox": bbox,
            "metadata": metadata
        }
        
        # Вставляем элемент в правильную позицию на основе insertion_order
        # Находим индекс для вставки
        insert_idx = len(self.elements)
        for i, existing_elem in enumerate(self.elements):
            existing_order = existing_elem.get('order', 0)
            existing_page = existing_elem.get('page_number', 0)
            # Вставляем перед первым элементом с order >= insertion_order на той же странице
            if existing_page == page_number and existing_order >= insertion_order:
                insert_idx = i
                break
            # Если перешли на другую страницу, вставляем в конец элементов текущей страницы
            elif existing_page > page_number:
                insert_idx = i
                break
        
        # Вставляем элемент
        self.elements.insert(insert_idx, element)
        
        # Перенумеровываем все элементы
        self.renumber_element_ids()
        
        # Обновляем current_order
        self.current_order = len(self.elements)
        
        # Пересчитываем parent_id после перенумерации
        self.recalculate_all_parent_ids()
        
        # Находим новый ID элемента
        new_id = element['id']
        
        self.pdf_viewer.set_elements(self.elements)
        self.update_elements_list()
        self.update_parent_combo()
        
        parent_info = f" (parent: {parent_id})" if parent_id else " (без родителя)"
        QMessageBox.information(self, "Успех", f"Элемент {new_id} добавлен на позицию {insertion_order}{parent_info}")
    
    def update_elements_list(self):
        """Обновление списка элементов."""
        self.elements_list.clear()
        for elem in self.elements:
            # page_number хранится как 0-based, для отображения конвертируем в 1-based
            page_num = elem.get('page_number')
            if page_num is not None:
                page_display = page_num  # Уже 1-based
            else:
                page_display = '?'
            
            # Получаем parent_id для отображения
            parent_id = elem.get('parent_id')
            parent_display = parent_id if parent_id else "нет"
            
            # Формат: стр. X | ID | тип | parent: ID
            item_text = f"стр. {page_display} | {elem['id']} | [{elem['type']}] | parent: {parent_display}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, elem['id'])
            self.elements_list.addItem(item)
    
    def update_parent_combo(self):
        """Обновление списка родительских элементов."""
        self.elem_parent_combo.clear()
        self.elem_parent_combo.addItem("Нет родителя", None)
        for elem in self.elements:
            self.elem_parent_combo.addItem(f"{elem['id']} - {elem['type']}", elem['id'])
    
    def on_list_selection_changed(self):
        """Обработка выбора элемента в списке."""
        items = self.elements_list.selectedItems()
        if items:
            element_id = items[0].data(Qt.UserRole)
            self.pdf_viewer.set_selected_element(element_id)
    
    def on_list_item_double_clicked(self, item: QListWidgetItem):
        """Обработка двойного клика по элементу в списке."""
        element_id = item.data(Qt.UserRole)
        element = next((e for e in self.elements if e['id'] == element_id), None)
        if element:
            self.open_element_editor(element)
    
    def on_element_double_clicked(self, element: Dict[str, Any]):
        """Обработка двойного клика по элементу на изображении."""
        self.open_element_editor(element)
    
    def open_element_editor(self, element: Dict[str, Any]):
        """Открывает редактор для указанного элемента."""
        element_id = element.get('id')
        if not element_id:
            return
        
        # Заполняем форму данными элемента
        idx = self.elem_type_combo.findText(element['type'])
        if idx >= 0:
            self.elem_type_combo.setCurrentIndex(idx)
        
        # page_number хранится как 1-based
        page_num = element.get('page_number')
        if page_num is not None:
            self.elem_page_spin.setValue(page_num)
        else:
            self.elem_page_spin.setValue(1)
        self.elem_content_text.setPlainText(element.get('content', ''))
        
        # Устанавливаем родителя
        parent_id = element.get('parent_id')
        if parent_id:
            idx = self.elem_parent_combo.findData(parent_id)
            if idx >= 0:
                self.elem_parent_combo.setCurrentIndex(idx)
        else:
            self.elem_parent_combo.setCurrentIndex(0)  # "Нет родителя"
        
        bbox = element.get('bbox')
        if bbox and len(bbox) == 4:
            self.bbox_x0.setValue(bbox[0])
            self.bbox_y0.setValue(bbox[1])
            self.bbox_x1.setValue(bbox[2])
            self.bbox_y1.setValue(bbox[3])
        
        # Сохраняем ID редактируемого элемента
        self.editing_element_id = element_id
        
        # Переключаемся на вкладку "Добавить" и меняем текст кнопки
        self.tabs.setCurrentIndex(1)
        self.add_btn.setText("💾 Сохранить изменения")
        self.add_btn.clicked.disconnect()
        self.add_btn.clicked.connect(self.save_edited_element)
    
    def on_element_selected(self, element: Dict[str, Any]):
        """Обработка выбора элемента на изображении (одиночный выбор).
        
        Примечание: основная логика выделения теперь в on_element_selected_multi.
        Этот метод оставлен для обратной совместимости, но не должен конфликтовать
        с множественным выделением, так как on_element_selected_multi вызывается первым.
        """
        # Логика выделения перенесена в on_element_selected_multi
        # Этот метод оставлен для обратной совместимости, но не выполняет действий
        pass
    
    def on_element_selected_multi(self, element: Dict[str, Any], add_to_selection: bool):
        """Обработка выбора элемента на изображении с поддержкой множественного выделения."""
        element_id = element.get("id")
        if not element_id:
            return
        
        # Находим элемент в списке
        target_item = None
        for i in range(self.elements_list.count()):
            item = self.elements_list.item(i)
            if item.data(Qt.UserRole) == element_id:
                target_item = item
                break
        
        if not target_item:
            return
        
        if add_to_selection:
            # Добавляем к выделению (Shift+Click)
            # Проверяем, не выделен ли уже этот элемент
            if not target_item.isSelected():
                target_item.setSelected(True)
            # Прокручиваем список к выделенному элементу
            self.elements_list.scrollToItem(target_item)
        else:
            # Обычный клик - выделяем только этот элемент
            # Сначала снимаем выделение со всех элементов
            self.elements_list.clearSelection()
            # Затем выделяем нужный элемент
            target_item.setSelected(True)
            self.elements_list.setCurrentItem(target_item)
    
    def toggle_drawing_mode(self, enabled: bool):
        """Включить/выключить режим рисования bbox."""
        self.pdf_viewer.set_drawing_mode(enabled)
        if enabled:
            self.draw_bbox_btn.setText("✏️ Рисовать BBox (ВКЛ)")
            QMessageBox.information(
                self, "Режим рисования", 
                "Кликните и перетащите мышью, чтобы нарисовать bounding box.\n"
                "Координаты автоматически заполнятся в форме."
            )
        else:
            self.draw_bbox_btn.setText("✏️ Рисовать BBox")
    
    def on_bbox_drawn(self, bbox: List[float]):
        """Обработка завершения рисования bbox."""
        # Заполняем форму координатами
        self.bbox_x0.setValue(bbox[0])
        self.bbox_y0.setValue(bbox[1])
        self.bbox_x1.setValue(bbox[2])
        self.bbox_y1.setValue(bbox[3])
        
        # Устанавливаем текущую страницу (конвертируем из 0-based в 1-based)
        self.elem_page_spin.setValue(self.pdf_viewer.current_page + 1)
        
        # Переключаемся на вкладку "Добавить"
        self.tabs.setCurrentIndex(1)  # Вкладка "Добавить" - индекс 1
        
        QMessageBox.information(
            self, "BBox нарисован",
            f"Координаты заполнены:\n"
            f"x0={bbox[0]:.1f}, y0={bbox[1]:.1f}\n"
            f"x1={bbox[2]:.1f}, y1={bbox[3]:.1f}\n\n"
            f"Заполните остальные поля и нажмите 'Добавить элемент'."
        )
    
    def edit_selected_element(self):
        """Редактирование выбранного элемента."""
        items = self.elements_list.selectedItems()
        if not items:
            QMessageBox.warning(self, "Предупреждение", "Выберите элемент для редактирования")
            return
        
        element_id = items[0].data(Qt.UserRole)
        element = next((e for e in self.elements if e['id'] == element_id), None)
        
        if element:
            self.open_element_editor(element)
    
    def save_edited_element(self):
        """Сохранение отредактированного элемента."""
        if not hasattr(self, 'editing_element_id'):
            # Если не редактируем, просто добавляем новый элемент
            self.add_element()
            return
        
        element_id = self.editing_element_id
        
        # Находим элемент и обновляем его
        element = next((e for e in self.elements if e['id'] == element_id), None)
        if not element:
            QMessageBox.warning(self, "Ошибка", "Элемент не найден")
            return
        
        # Сохраняем старый тип для проверки изменений
        old_type = element.get('type', '')
        
        # Обновляем данные элемента
        new_type = self.elem_type_combo.currentText()
        element['type'] = new_type
        element['content'] = self.elem_content_text.toPlainText()
        
        # Определяем parent_id
        page_number = self.elem_page_spin.value()  # 1-based
        order = element.get('order', 0)
        
        # Если изменился тип, автоматически пересчитываем parent_id
        if old_type != new_type:
            # Автоматически определяем parent_id для нового типа
            element['parent_id'] = self.find_auto_parent_id(new_type, page_number, order)
            # Обновляем parent_id для всех зависимых элементов
            self.update_children_parent_ids(element_id, old_type, new_type)
        else:
            # Если тип не изменился, используем выбранный вручную parent_id или автоматический
            manual_parent_id = self.elem_parent_combo.currentData() if self.elem_parent_combo.currentData() else None
            if manual_parent_id:
                element['parent_id'] = manual_parent_id
            else:
                # Автоматически определяем parent_id
                element['parent_id'] = self.find_auto_parent_id(new_type, page_number, order)
        
        element['page_number'] = page_number
        bbox = [
            self.bbox_x0.value(),
            self.bbox_y0.value(),
            self.bbox_x1.value(),
            self.bbox_y1.value()
        ] if (self.bbox_x0.value(), self.bbox_y0.value(), self.bbox_x1.value(), self.bbox_y1.value()) != (0, 0, 0, 0) else None
        element['bbox'] = bbox
        
        # Обновляем отображение
        self.pdf_viewer.set_elements(self.elements)
        self.update_elements_list()
        self.update_parent_combo()
        
        # Сбрасываем режим редактирования
        delattr(self, 'editing_element_id')
        
        # Возвращаем кнопку в исходное состояние
        self.add_btn.setText("➕ Добавить элемент")
        self.add_btn.clicked.disconnect()
        self.add_btn.clicked.connect(self.add_element)
        
        # Очищаем форму
        self.elem_content_text.clear()
        self.bbox_x0.setValue(0)
        self.bbox_y0.setValue(0)
        self.bbox_x1.setValue(0)
        self.bbox_y1.setValue(0)
        
        QMessageBox.information(self, "Успех", f"Элемент {element_id} обновлен")
    
    def delete_selected_element(self):
        """Удаление выбранного элемента."""
        items = self.elements_list.selectedItems()
        if not items:
            QMessageBox.warning(self, "Предупреждение", "Выберите элемент для удаления")
            return
        
        element_ids = [item.data(Qt.UserRole) for item in items]
        
        if len(element_ids) == 1:
            reply = QMessageBox.question(
                self, "Подтверждение", 
                f"Удалить элемент {element_ids[0]}?",
                QMessageBox.Yes | QMessageBox.No
            )
        else:
            reply = QMessageBox.question(
                self, "Подтверждение", 
                f"Удалить {len(element_ids)} элементов?",
                QMessageBox.Yes | QMessageBox.No
            )
        
        if reply == QMessageBox.Yes:
            # Перед удалением обновляем parent_id для элементов, которые ссылались на удаляемые
            for deleted_id in element_ids:
                deleted_elem = next((e for e in self.elements if e['id'] == deleted_id), None)
                if not deleted_elem:
                    continue
                
                # Находим новый parent для детей удаляемого элемента
                page_number = deleted_elem.get('page_number', 1)  # 1-based по умолчанию
                order = deleted_elem.get('order', 0)
                new_parent_id = self.find_auto_parent_id('header_1', page_number, order)
                
                # Обновляем parent_id всех детей
                for elem in self.elements:
                    if elem.get('parent_id') == deleted_id:
                        elem['parent_id'] = new_parent_id
            
            # Удаляем элементы
            self.elements = [e for e in self.elements if e['id'] not in element_ids]
            
            # Перенумеровываем ID
            self.renumber_element_ids()
            
            # Пересчитываем parent_id для всех элементов (на случай изменений в порядке)
            self.recalculate_all_parent_ids()
            
            # Обновляем отображение
            self.pdf_viewer.set_elements(self.elements)
            self.update_elements_list()
            self.update_parent_combo()
    
    def renumber_element_ids(self):
        """Перенумеровывает ID элементов, чтобы они были последовательными (elem_0000, elem_0001, ...)."""
        # Сортируем элементы по order
        self.elements.sort(key=lambda x: x.get('order', 0))
        
        # Перенумеровываем ID и order
        for i, elem in enumerate(self.elements):
            old_id = elem['id']
            new_id = f"elem_{i:04d}"
            elem['id'] = new_id
            elem['order'] = i
            
            # Обновляем parent_id, если он ссылался на старый ID
            for other_elem in self.elements:
                if other_elem.get('parent_id') == old_id:
                    other_elem['parent_id'] = new_id
        
        # Обновляем current_order
        self.current_order = len(self.elements)
    
    def recalculate_all_parent_ids(self):
        """Пересчитывает parent_id для всех элементов на основе их порядка и типа."""
        # Сортируем элементы по странице и order
        self.elements.sort(key=lambda x: (x.get('page_number', 0), x.get('order', 0)))
        
        # Пересчитываем parent_id для каждого элемента
        for elem in self.elements:
            page_number = elem.get('page_number', 1)  # 1-based по умолчанию
            order = elem.get('order', 0)
            elem_type = elem.get('type', '')
            
            # Автоматически определяем parent_id
            auto_parent_id = self.find_auto_parent_id(elem_type, page_number, order)
            
            # Обновляем parent_id только если он не был установлен вручную
            # (для автоматической разметки обновляем все)
            elem['parent_id'] = auto_parent_id
    
    def unite_selected_elements(self):
        """Объединение выбранных элементов в один."""
        items = self.elements_list.selectedItems()
        if len(items) < 2:
            QMessageBox.warning(self, "Предупреждение", "Выберите минимум 2 элемента для объединения")
            return
        
        element_ids = [item.data(Qt.UserRole) for item in items]
        selected_elements = [e for e in self.elements if e['id'] in element_ids]
        
        if not selected_elements:
            QMessageBox.warning(self, "Ошибка", "Элементы не найдены")
            return
        
        # Проверяем, что все элементы на одной странице
        pages = set(e.get('page_number') for e in selected_elements if e.get('page_number') is not None)
        if len(pages) > 1:
            reply = QMessageBox.question(
                self, "Предупреждение",
                "Элементы находятся на разных страницах. Продолжить объединение?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        
        # Определяем тип объединенного элемента (берем первый тип)
        united_type = selected_elements[0]['type']
        
        # Объединяем содержимое
        contents = [e.get('content', '') for e in selected_elements if e.get('content')]
        united_content = '\n\n'.join(contents) if contents else ''
        
        # Вычисляем объединенный bbox (минимальный прямоугольник, содержащий все элементы)
        bboxes = [e.get('bbox') for e in selected_elements if e.get('bbox') and len(e.get('bbox')) == 4]
        if bboxes:
            x0 = min(bbox[0] for bbox in bboxes)
            y0 = min(bbox[1] for bbox in bboxes)
            x1 = max(bbox[2] for bbox in bboxes)
            y1 = max(bbox[3] for bbox in bboxes)
            united_bbox = [x0, y0, x1, y1]
        else:
            united_bbox = None
        
        # Определяем страницу (берем первую найденную)
        united_page = selected_elements[0].get('page_number')
        
        # Определяем родителя (берем первого родителя, если есть)
        united_parent = None
        for elem in selected_elements:
            if elem.get('parent_id'):
                united_parent = elem.get('parent_id')
                break
        
        # Находим минимальный order среди объединяемых элементов
        # Это будет позиция, на которую встанет объединенный элемент
        min_order = min(elem.get('order', 0) for elem in selected_elements)
        
        # Удаляем старые элементы
        self.elements = [e for e in self.elements if e['id'] not in element_ids]
        
        # Создаем объединенный элемент с минимальным order
        # Временный ID, будет перенумерован после
        united_element = {
            "id": "temp_united",  # Временный ID
            "type": united_type,
            "content": united_content,
            "parent_id": united_parent,
            "order": min_order,  # Используем минимальный order из объединяемых элементов
            "page_number": united_page,
            "bbox": united_bbox,
            "metadata": {}
        }
        
        # Добавляем объединенный элемент
        self.elements.append(united_element)
        
        # Перенумеровываем ID - это правильно установит ID и order для всех элементов
        self.renumber_element_ids()
        
        # Пересчитываем parent_id для всех элементов
        self.recalculate_all_parent_ids()
        
        # Обновляем отображение
        self.pdf_viewer.set_elements(self.elements)
        self.update_elements_list()
        self.update_parent_combo()
        
        QMessageBox.information(
            self, "Успех",
            f"Объединено {len(selected_elements)} элементов в {united_element['id']}"
        )
    
    def set_parent_for_selected(self):
        """Массовое назначение parent_id для выбранных элементов."""
        items = self.elements_list.selectedItems()
        if not items:
            QMessageBox.warning(self, "Предупреждение", "Выберите элементы для назначения родителя")
            return
        
        element_ids = [item.data(Qt.UserRole) for item in items]
        selected_elements = [e for e in self.elements if e['id'] in element_ids]
        
        if not selected_elements:
            QMessageBox.warning(self, "Ошибка", "Элементы не найдены")
            return
        
        # Диалог выбора родителя
        parent_dialog = QDialog(self)
        parent_dialog.setWindowTitle("Назначить родителя")
        parent_dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(parent_dialog)
        
        layout.addWidget(QLabel(f"Выбрано элементов: {len(selected_elements)}"))
        layout.addWidget(QLabel("Выберите родительский элемент:"))
        
        parent_combo = QComboBox()
        parent_combo.addItem("Нет родителя", None)
        
        # Добавляем все элементы, кроме выбранных
        for elem in self.elements:
            if elem['id'] not in element_ids:
                page_num = elem.get('page_number')
                page_display = page_num if page_num is not None else '?'
                display_text = f"{elem['id']} - [{elem['type']}] - стр. {page_display}"
                parent_combo.addItem(display_text, elem['id'])
        
        layout.addWidget(parent_combo)
        
        # Кнопки
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("ОК")
        cancel_btn = QPushButton("Отмена")
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        ok_btn.clicked.connect(parent_dialog.accept)
        cancel_btn.clicked.connect(parent_dialog.reject)
        
        if parent_dialog.exec_() == QDialog.Accepted:
            selected_parent_id = parent_combo.currentData()
            
            # Обновляем parent_id для всех выбранных элементов
            updated_count = 0
            for elem in selected_elements:
                elem['parent_id'] = selected_parent_id
                updated_count += 1
            
            # Обновляем отображение
            self.pdf_viewer.set_elements(self.elements)
            self.update_elements_list()
            self.update_parent_combo()
            
            parent_info = selected_parent_id if selected_parent_id else "нет"
            QMessageBox.information(
                self, "Успех",
                f"Родитель '{parent_info}' назначен для {updated_count} элементов"
            )
    
    def prev_page(self):
        """Переход на предыдущую страницу."""
        if self.pdf_viewer.current_page > 0:
            self.pdf_viewer.set_page(self.pdf_viewer.current_page - 1)
            self.update_navigation()
    
    def next_page(self):
        """Переход на следующую страницу."""
        total_pages = self.pdf_viewer.get_total_pages()
        if self.pdf_viewer.current_page < total_pages - 1:
            self.pdf_viewer.set_page(self.pdf_viewer.current_page + 1)
            self.update_navigation()
    
    def update_navigation(self):
        """Обновление навигации по страницам."""
        total_pages = self.pdf_viewer.get_total_pages()
        current = self.pdf_viewer.current_page + 1
        self.page_label.setText(f"Страница {current} из {total_pages}")
        self.prev_btn.setEnabled(self.pdf_viewer.current_page > 0)
        self.next_btn.setEnabled(self.pdf_viewer.current_page < total_pages - 1)
        self.elem_page_spin.setValue(current)
    
    def save_annotation(self):
        """Сохранение разметки."""
        if not self.pdf_path:
            QMessageBox.warning(self, "Предупреждение", "Сначала загрузите файл (PDF или DOCX)")
            return
        
        output_dir = self.annotations_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Определяем исходный файл для имени аннотации
        # Для DOCX файлов всегда используем source_file_path, а не временный PDF
        if self.source_file_path:
            source_file = self.source_file_path
            # Для DOCX файлов используем полное имя с расширением
            if source_file.suffix.lower() == '.docx':
                # Формат: 2412.19495v2.docx -> 2412.19495v2.docx_annotation.json
                output_path = output_dir / f"{source_file.name}_annotation.json"
            else:
                # Для PDF используем только имя без расширения
                output_path = output_dir / f"{source_file.stem}_annotation.json"
        else:
            # Если source_file_path не установлен, используем pdf_path
            # Но для временных PDF из DOCX нужно извлечь оригинальное имя
            if self.temp_pdf_path and self.temp_pdf_path == self.pdf_path:
                # Это временный PDF из DOCX - извлекаем оригинальное имя
                # Формат: document_temp_20240101_120000.pdf -> document
                temp_name = self.pdf_path.stem
                if temp_name.endswith('_temp'):
                    # Если имя заканчивается на _temp, убираем его
                    original_name = temp_name[:-5]  # Убираем '_temp'
                elif '_temp_' in temp_name:
                    # Если есть _temp_ с датой, берем часть до _temp_
                    original_name = temp_name.split('_temp_')[0]
                else:
                    original_name = temp_name
                # Для DOCX предполагаем расширение .docx
                output_path = output_dir / f"{original_name}.docx_annotation.json"
            else:
                # Обычный PDF файл
                source_file = self.pdf_path
                output_path = output_dir / f"{source_file.stem}_annotation.json"
        
        try:
            stats = {
                "total_elements": len(self.elements),
                "total_pages": self.pdf_viewer.get_total_pages(),
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
            
            stats["total_pages"] = len(pages) if pages else self.pdf_viewer.get_total_pages()
            
            # Определяем формат документа и исходный файл для сохранения в JSON
            # Для сохранения в JSON используем реальный source_file_path, если он есть
            if self.source_file_path:
                json_source_file = self.source_file_path
                document_format = "docx" if json_source_file.suffix.lower() == '.docx' else "pdf"
                # Для document_id используем имя без расширения
                document_id = json_source_file.stem
                
                # Если файл находится в папке documents, используем относительный путь
                try:
                    json_source_file_relative = json_source_file.relative_to(self.script_dir)
                    json_source_file_str = str(json_source_file_relative)
                except ValueError:
                    # Если файл не в папке скрипта, используем абсолютный путь
                    json_source_file_str = str(json_source_file)
            else:
                json_source_file = self.pdf_path
                document_format = "pdf"
                # Для document_id используем имя без расширения
                document_id = json_source_file.stem
                
                # Если файл находится в папке documents, используем относительный путь
                try:
                    json_source_file_relative = json_source_file.relative_to(self.script_dir)
                    json_source_file_str = str(json_source_file_relative)
                except ValueError:
                    # Если файл не в папке скрипта, используем абсолютный путь
                    json_source_file_str = str(json_source_file)
            
            annotation = {
                "document_id": document_id,
                "source_file": json_source_file_str,
                "document_format": document_format,
                "annotation_version": "2.0",
                "annotator": "qt_visual",
                "annotation_date": datetime.now().isoformat(),
                "elements": self.elements,
                "statistics": stats
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(annotation, f, ensure_ascii=False, indent=2)
            
            # Для DOCX файлов создаем комбинированные изображения (оригинал + разметка)
            if document_format == "docx" and self.pdf_path:
                try:
                    # Убеждаемся, что пути - это Path объекты
                    output_path_obj = Path(output_path) if not isinstance(output_path, Path) else output_path
                    pdf_path_obj = Path(self.pdf_path) if not isinstance(self.pdf_path, Path) else self.pdf_path
                    
                    print(f"[DEBUG] Создание изображений для DOCX: output_path={output_path_obj}, pdf_path={pdf_path_obj}")
                    images_saved = self._save_comparison_images_for_docx(
                        output_path_obj, 
                        pdf_path_obj,
                        self.elements
                    )
                    print(f"[DEBUG] Создано изображений: {images_saved}")
                    if images_saved > 0:
                        images_dir = output_path_obj.parent / f"{output_path_obj.stem}_comparison_images"
                        QMessageBox.information(
                            self, "Успех", 
                            f"Разметка сохранена в:\n{output_path_obj}\n\n"
                            f"Создано {images_saved} комбинированных изображений для сравнения.\n"
                            f"Папка: {images_dir}"
                        )
                    else:
                        QMessageBox.warning(
                            self, "Предупреждение",
                            f"Разметка сохранена в:\n{output_path_obj}\n\n"
                            f"Не удалось создать изображения (создано: {images_saved}).\n"
                            f"Проверьте наличие PDF файла: {pdf_path_obj}\n"
                            f"Проверьте консоль для деталей."
                        )
                except Exception as e:
                    # Если не удалось создать изображения, все равно показываем успех сохранения
                    import traceback
                    error_msg = traceback.format_exc()
                    print(f"[ERROR] Ошибка при создании изображений: {error_msg}")
                    output_path_display = output_path_obj if 'output_path_obj' in locals() else output_path
                    QMessageBox.warning(
                        self, "Предупреждение",
                        f"Разметка сохранена в:\n{output_path_display}\n\n"
                        f"Не удалось создать изображения для сравнения:\n{str(e)}\n\n"
                        f"Подробности в консоли."
                    )
            else:
                QMessageBox.information(self, "Успех", f"Разметка сохранена в:\n{output_path}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить разметку: {e}")
    
    def extract_ground_truth_text(self):
        """Извлекает ground truth текст из PDF с выделяемым текстом по bbox элементов."""
        if not self.elements:
            QMessageBox.warning(self, "Предупреждение", "Сначала создайте разметку (авторазметка или вручную)")
            return
        
        if not self.pdf_path:
            QMessageBox.warning(self, "Предупреждение", "Сначала загрузите файл")
            return
        
        # Автоматически определяем соответствующий PDF файл
        # Если загружен scanned.pdf, ищем обычный .pdf, и наоборот
        source_file = self.source_file_path if self.source_file_path else self.pdf_path
        source_name = source_file.stem
        source_dir = source_file.parent
        
        # Пробуем найти соответствующий PDF
        gt_pdf_path = None
        
        # Если это scanned.pdf, ищем обычный .pdf
        if "scanned" in source_name.lower():
            regular_name = source_name.replace("_scanned", "").replace("scanned", "")
            possible_paths = [
                source_dir / f"{regular_name}.pdf",
                source_dir / f"{source_name.replace('_scanned', '')}.pdf",
            ]
            for path in possible_paths:
                if path.exists() and path != source_file:
                    gt_pdf_path = path
                    break
        else:
            # Если это обычный PDF, ищем scanned.pdf
            scanned_paths = [
                source_dir / f"{source_name}_scanned.pdf",
                source_dir / f"{source_name} scanned.pdf",
            ]
            for path in scanned_paths:
                if path.exists():
                    gt_pdf_path = path
                    break
            
            # Если не нашли scanned, используем сам файл (если это PDF с текстом)
            if not gt_pdf_path and source_file.suffix.lower() == '.pdf':
                # Проверяем, есть ли в файле выделяемый текст
                try:
                    test_pdf = fitz.open(str(source_file))
                    if test_pdf[0].get_text().strip():
                        gt_pdf_path = source_file
                    test_pdf.close()
                except:
                    pass
        
        # Если не нашли автоматически, запрашиваем у пользователя
        if not gt_pdf_path:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Выберите PDF файл с выделяемым текстом (ground truth)", str(source_dir), "PDF Files (*.pdf)"
            )
            if not file_path:
                return
            gt_pdf_path = Path(file_path)
        else:
            # Подтверждаем использование найденного файла
            reply = QMessageBox.question(
                self, "Подтверждение",
                f"Найден соответствующий PDF файл:\n{gt_pdf_path.name}\n\nИспользовать его для извлечения текста?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                # Запрашиваем другой файл
                file_path, _ = QFileDialog.getOpenFileName(
                    self, "Выберите PDF файл с выделяемым текстом (ground truth)", str(source_dir), "PDF Files (*.pdf)"
                )
                if not file_path:
                    return
                gt_pdf_path = Path(file_path)
        
        try:
            # Открываем PDF
            gt_pdf = fitz.open(str(gt_pdf_path))
            
            # Подсчитываем элементы с bbox
            elements_with_bbox = [e for e in self.elements if len(e.get('bbox', [])) >= 4]
            
            if not elements_with_bbox:
                QMessageBox.warning(self, "Предупреждение", "Нет элементов с bbox для извлечения текста")
                gt_pdf.close()
                return
            
            # Показываем прогресс
            progress = QProgressDialog("Извлечение ground truth текста...", "Отмена", 0, len(elements_with_bbox), self)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()
            
            updated_count = 0
            render_scale = 2.0  # Масштаб, используемый при создании bbox
            
            for i, elem in enumerate(elements_with_bbox):
                if progress.wasCanceled():
                    break
                
                progress.setValue(i)
                QApplication.processEvents()
                
                bbox = elem.get('bbox', [])
                page_number = elem.get('page_number', 1)  # 1-based в аннотациях
                page_num = page_number - 1  # Конвертируем в 0-based для PyMuPDF
                
                if len(bbox) < 4 or page_num < 0 or page_num >= len(gt_pdf):
                    continue
                
                try:
                    page = gt_pdf[page_num]
                    
                    # Конвертируем координаты из render_scale в оригинальный масштаб PDF
                    x1, y1, x2, y2 = (
                        bbox[0] / render_scale,
                        bbox[1] / render_scale,
                        bbox[2] / render_scale,
                        bbox[3] / render_scale,
                    )
                    
                    rect = fitz.Rect(x1, y1, x2, y2)
                    
                    # Извлекаем текст из PDF
                    # Пробуем get_textbox - более точный метод
                    text = page.get_textbox(rect).strip()
                    
                    # Если не получилось, пробуем другой метод
                    if not text or len(text) < 2:
                        text_dict = page.get_text("dict", clip=rect)
                        text_parts = []
                        
                        for block in text_dict.get("blocks", []):
                            if "lines" not in block:
                                continue
                            for line in block["lines"]:
                                for span in line.get("spans", []):
                                    text_parts.append(span.get("text", ""))
                        
                        text = " ".join(text_parts).strip()
                    
                    # Если всё ещё нет текста, пробуем простой метод
                    if not text or len(text) < 2:
                        text = page.get_text("text", clip=rect).strip()
                    
                    # Заменяем content элемента на извлеченный текст
                    if text:
                        elem['content'] = text
                        updated_count += 1
                
                except Exception as e:
                    # Игнорируем ошибки для отдельных элементов
                    continue
            
            gt_pdf.close()
            progress.setValue(len(elements_with_bbox))
            
            # Обновляем отображение
            self.pdf_viewer.set_elements(self.elements)
            self.update_elements_list()
            
            QMessageBox.information(
                self, "Успех",
                f"Ground truth текст извлечен для {updated_count} из {len(elements_with_bbox)} элементов"
            )
        
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при извлечении ground truth текста: {e}")
    
    def _save_comparison_images_for_docx(
        self, 
        annotation_path: Path, 
        pdf_path: Path,
        elements: List[Dict[str, Any]]
    ) -> int:
        """
        Создает комбинированные изображения для DOCX файлов: оригинал + с разметкой.
        Сохраняет их в папку рядом с аннотацией.
        
        Returns:
            Количество сохраненных изображений
        """
        print(f"[DEBUG] _save_comparison_images_for_docx вызван")
        print(f"[DEBUG] annotation_path={annotation_path}, exists={annotation_path.exists()}")
        print(f"[DEBUG] pdf_path={pdf_path}, exists={pdf_path.exists() if pdf_path else False}")
        print(f"[DEBUG] elements count={len(elements)}")
        
        if not pdf_path:
            print("[ERROR] pdf_path is None")
            return 0
        
        if not pdf_path.exists():
            print(f"[ERROR] PDF файл не существует: {pdf_path}")
            return 0
        
        try:
            # Открываем PDF
            pdf_doc = fitz.open(str(pdf_path))
            total_pages = len(pdf_doc)
            print(f"[DEBUG] PDF открыт, страниц: {total_pages}")
            
            if total_pages == 0:
                pdf_doc.close()
                print("[ERROR] PDF не содержит страниц")
                return 0
            
            # Создаем папку для изображений рядом с аннотацией
            images_dir = annotation_path.parent / f"{annotation_path.stem}_comparison_images"
            images_dir.mkdir(parents=True, exist_ok=True)
            print(f"[DEBUG] Папка для изображений: {images_dir}")
            
            render_scale = 2.0  # Масштаб, используемый при парсинге
            scale = 2.0  # Масштаб для рендеринга изображений
            
            saved_count = 0
            
            for page_num in range(total_pages):
                try:
                    page = pdf_doc[page_num]
                    
                    # Рендерим оригинальную страницу
                    mat = fitz.Matrix(scale, scale)
                    pix = page.get_pixmap(matrix=mat)
                    
                    # Конвертируем в PIL Image
                    img_data = pix.tobytes("ppm")
                    original_img = Image.open(io.BytesIO(img_data))
                    
                    # Создаем копию для рисования разметки
                    annotated_img = original_img.copy()
                    draw = ImageDraw.Draw(annotated_img)
                    
                    # Получаем размеры PDF страницы
                    pdf_width_pts = page.rect.width
                    pdf_height_pts = page.rect.height
                    
                    # Коэффициенты масштабирования для bbox
                    scale_x = scale / render_scale
                    scale_y = scale / render_scale
                    
                    # Фильтруем элементы для текущей страницы (page_number 1-based)
                    page_elements = [
                        e for e in elements 
                        if e.get("page_number") == page_num + 1
                    ]
                    
                    # Рисуем bbox для каждого элемента
                    for elem in page_elements:
                        bbox = elem.get("bbox")
                        if not bbox or len(bbox) != 4:
                            continue
                        
                        x0_bbox, y0_bbox, x1_bbox, y1_bbox = bbox
                        
                        # Конвертируем координаты
                        x0 = x0_bbox * scale_x
                        y0 = y0_bbox * scale_y
                        x1 = x1_bbox * scale_x
                        y1 = y1_bbox * scale_y
                        
                        # Ограничиваем координаты
                        x0 = max(0, min(x0, annotated_img.width))
                        y0 = max(0, min(y0, annotated_img.height))
                        x1 = max(0, min(x1, annotated_img.width))
                        y1 = max(0, min(y1, annotated_img.height))
                        
                        if x1 <= x0 or y1 <= y0:
                            continue
                        
                        # Получаем цвет для типа элемента
                        elem_type = elem.get("type", "text")
                        color_obj = ELEMENT_COLORS.get(elem_type, QColor(0, 0, 0))
                        
                        # Конвертируем QColor в RGB кортеж
                        if isinstance(color_obj, QColor):
                            color = (color_obj.red(), color_obj.green(), color_obj.blue())
                        else:
                            # Если это не QColor, используем красный по умолчанию
                            color = (255, 0, 0)
                        
                        # Рисуем прямоугольник
                        draw.rectangle(
                            [int(x0), int(y0), int(x1), int(y1)],
                            outline=color,
                            width=3
                        )
                        
                        # Добавляем подпись
                        label = f"{elem_type} ({elem.get('id', '?')})"
                        try:
                            font = ImageFont.truetype("arial.ttf", 14)
                        except:
                            try:
                                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
                            except:
                                font = ImageFont.load_default()
                        
                        # Фон для текста
                        text_bbox = draw.textbbox((int(x0), int(y0) - 18), label, font=font)
                        draw.rectangle(text_bbox, fill=color, outline=color)
                        draw.text((int(x0), int(y0) - 18), label, fill=(255, 255, 255), font=font)
                    
                    # Создаем комбинированное изображение: оригинал слева, с разметкой справа
                    img_width = original_img.width
                    img_height = original_img.height
                    
                    # Создаем новое изображение для комбинации
                    combined_img = Image.new('RGB', (img_width * 2, img_height), (255, 255, 255))
                    combined_img.paste(original_img, (0, 0))
                    combined_img.paste(annotated_img, (img_width, 0))
                    
                    # Добавляем подписи
                    draw_combined = ImageDraw.Draw(combined_img)
                    try:
                        title_font = ImageFont.truetype("arial.ttf", 20)
                    except:
                        try:
                            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
                        except:
                            title_font = ImageFont.load_default()
                    
                    # Подпись для оригинального изображения
                    draw_combined.text((10, 10), "Оригинал", fill=(0, 0, 0), font=title_font)
                    # Подпись для изображения с разметкой
                    draw_combined.text((img_width + 10, 10), "Разметка модели", fill=(0, 0, 0), font=title_font)
                    
                    # Сохраняем комбинированное изображение
                    output_image_path = images_dir / f"page_{page_num + 1:03d}_comparison.png"
                    combined_img.save(output_image_path, "PNG")
                    saved_count += 1
                    print(f"[DEBUG] Сохранено изображение: {output_image_path}")
                    
                except Exception as e:
                    # Продолжаем обработку других страниц при ошибке
                    import traceback
                    print(f"[ERROR] Ошибка при обработке страницы {page_num + 1}: {e}")
                    print(traceback.format_exc())
                    continue
            
            pdf_doc.close()
            print(f"[DEBUG] Всего сохранено изображений: {saved_count}")
            return saved_count
            
        except Exception as e:
            import traceback
            print(f"[ERROR] Критическая ошибка в _save_comparison_images_for_docx: {e}")
            print(traceback.format_exc())
            return 0

    def closeEvent(self, event):
        """Очистка временных файлов при закрытии."""
        if self.temp_pdf_path and self.temp_pdf_path.exists():
            try:
                self.temp_pdf_path.unlink()
            except Exception:
                pass  # Игнорируем ошибки при удалении
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = AnnotationTool()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

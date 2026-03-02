"""
Графический инструмент для разметки с визуализацией и автоматической предразметкой.

Автоматически создает предварительную разметку используя наш парсер,
визуализирует её на изображении PDF с цветными прямоугольниками,
и позволяет редактировать прямо в интерфейсе.
"""

import streamlit as st
import json
import fitz  # PyMuPDF
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import io
from PIL import Image, ImageDraw, ImageFont
import numpy as np

# Импорт нашего парсера
from documentor import Pipeline
from documentor.domain.models import ParsedDocument, ElementType
from langchain_core.documents import Document

# Конфигурация страницы
st.set_page_config(
    page_title="Визуальная разметка документов",
    page_icon="🎨",
    layout="wide"
)

# Типы элементов и их цвета
ELEMENT_COLORS = {
    "title": "#FF0000",  # Красный
    "header_1": "#FF6600",  # Оранжевый
    "header_2": "#FF9900",  # Темно-оранжевый
    "header_3": "#FFCC00",  # Желтый
    "header_4": "#FFFF00",  # Ярко-желтый
    "header_5": "#CCFF00",  # Желто-зеленый
    "header_6": "#99FF00",  # Зеленый
    "text": "#00CCFF",  # Голубой
    "table": "#9900FF",  # Фиолетовый
    "image": "#FF00FF",  # Розовый
    "list_item": "#00FF99",  # Зелено-голубой
    "caption": "#FF0099",  # Розово-красный
    "formula": "#0099FF",  # Синий
    "link": "#00FF00",  # Ярко-зеленый
    "code_block": "#666666",  # Серый
}

ELEMENT_TYPES = list(ELEMENT_COLORS.keys())

# Инициализация состояния (только если не существует)
if 'elements' not in st.session_state:
    st.session_state.elements = []
if 'current_order' not in st.session_state:
    st.session_state.current_order = 0
if 'pdf_doc' not in st.session_state:
    st.session_state.pdf_doc = None
if 'total_pages' not in st.session_state:
    st.session_state.total_pages = 0
if 'current_page' not in st.session_state:
    st.session_state.current_page = 0
if 'pdf_path' not in st.session_state:
    st.session_state.pdf_path = None
if 'parsed_document' not in st.session_state:
    st.session_state.parsed_document = None

# Восстанавливаем current_order на основе существующих элементов при загрузке
# Это гарантирует, что ID будут последовательными
if st.session_state.elements:
    max_order = max((elem.get("order", -1) for elem in st.session_state.elements), default=-1)
    if st.session_state.current_order <= max_order:
        st.session_state.current_order = max_order + 1

# Восстанавливаем current_order на основе существующих элементов
if st.session_state.elements and st.session_state.current_order == 0:
    max_order = max((elem.get("order", -1) for elem in st.session_state.elements), default=-1)
    st.session_state.current_order = max_order + 1


def load_pdf(pdf_path: Path) -> bool:
    """Загрузка PDF документа."""
    try:
        # Не сбрасываем элементы при загрузке нового PDF
        # Пользователь может захотеть сохранить существующую разметку
        st.session_state.pdf_doc = fitz.open(str(pdf_path))
        st.session_state.total_pages = len(st.session_state.pdf_doc)
        st.session_state.current_page = 0
        st.session_state.pdf_path = pdf_path
        return True
    except Exception as e:
        st.error(f"Ошибка загрузки PDF: {e}")
        return False


def create_auto_annotation(pdf_path: Path) -> List[Dict[str, Any]]:
    """Создает автоматическую предварительную разметку используя наш парсер."""
    try:
        pipeline = Pipeline()
        langchain_doc = Document(page_content="", metadata={"source": str(pdf_path)})
        parsed = pipeline.parse(langchain_doc)
        
        st.session_state.parsed_document = parsed
        
        elements = []
        for i, elem in enumerate(parsed.elements):
            # ID начинается с 0: elem_0000, elem_0001, ...
            element_data = {
                "id": f"elem_{i:04d}",
                "type": elem.type.value.lower(),
                "content": elem.content,
                "parent_id": elem.parent_id,
                "order": i,  # order тоже начинается с 0
                "page_number": elem.metadata.get("page_num"),
                "bbox": elem.metadata.get("bbox"),
                "metadata": {}
            }
            elements.append(element_data)
        
        return elements
    except Exception as e:
        st.error(f"Ошибка автоматической разметки: {e}")
        return []


def render_pdf_page_with_annotations(
    page_num: int,
    elements: List[Dict[str, Any]],
    scale: float = 1.5,
    render_scale: float = 2.0  # Масштаб рендеринга, использованный при парсинге
) -> Image.Image:
    """Рендерит страницу PDF с визуализацией разметки."""
    if not st.session_state.pdf_doc or page_num < 0 or page_num >= st.session_state.total_pages:
        return None
    
    try:
        page = st.session_state.pdf_doc[page_num]
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Создаем копию для рисования
        draw_img = img.copy()
        draw = ImageDraw.Draw(draw_img)
        
        # Фильтруем элементы для текущей страницы
        page_elements = [e for e in elements if e.get("page_number") == page_num + 1]
        
        # Получаем размеры PDF страницы в пунктах (points)
        pdf_page = st.session_state.pdf_doc[page_num]
        pdf_width_pts = pdf_page.rect.width
        pdf_height_pts = pdf_page.rect.height
        
        # Координаты bbox хранятся в пикселях изображения, отрендеренного с render_scale
        # Но это изображение могло быть изменено через smart_resize для OCR
        # Поэтому используем реальные размеры изображения для вычисления масштаба
        
        # Размеры текущего изображения (реальные)
        current_img_width = img.width
        current_img_height = img.height
        
        # Теоретические размеры изображения при render_scale (без smart_resize)
        # Это размеры, в которых хранятся координаты bbox
        theoretical_width_at_render_scale = pdf_width_pts * render_scale
        theoretical_height_at_render_scale = pdf_height_pts * render_scale
        
        # Коэффициенты масштабирования для конвертации координат
        # Координаты bbox в координатах изображения при render_scale
        # Конвертируем в координаты текущего изображения при scale
        # Формула: scale_x = (current_width) / (width_at_render_scale) = scale / render_scale
        scale_x = scale / render_scale
        scale_y = scale / render_scale
        
        # Отладочная информация (можно убрать после проверки)
        # st.write(f"Debug: PDF size: {pdf_width_pts:.1f}x{pdf_height_pts:.1f} pts")
        # st.write(f"Debug: Image at render_scale: {theoretical_width_at_render_scale:.1f}x{theoretical_height_at_render_scale:.1f} px")
        # st.write(f"Debug: Current image: {current_img_width}x{current_img_height} px")
        # st.write(f"Debug: Scale factors: {scale_x:.4f}, {scale_y:.4f}")
        
        # Рисуем прямоугольники для каждого элемента
        for elem in page_elements:
            bbox = elem.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            
            x0_bbox, y0_bbox, x1_bbox, y1_bbox = bbox
            
            # Конвертируем координаты из масштаба render_scale в масштаб текущего изображения
            x0 = x0_bbox * scale_x
            y0 = y0_bbox * scale_y
            x1 = x1_bbox * scale_x
            y1 = y1_bbox * scale_y
            
            # Ограничиваем координаты границами изображения (на случай ошибок округления)
            x0 = max(0, min(x0, img.width))
            y0 = max(0, min(y0, img.height))
            x1 = max(0, min(x1, img.width))
            y1 = max(0, min(y1, img.height))
            
            # Проверяем, что координаты валидны (x1 > x0, y1 > y0)
            if x1 <= x0 or y1 <= y0:
                continue
            
            # Получаем цвет для типа элемента
            elem_type = elem.get("type", "text")
            color = ELEMENT_COLORS.get(elem_type, "#000000")
            
            # Рисуем прямоугольник
            draw.rectangle(
                [x0, y0, x1, y1],
                outline=color,
                width=3
            )
            
            # Добавляем подпись с типом и ID
            label = f"{elem_type} ({elem['id']})"
            try:
                # Пытаемся использовать системный шрифт
                font = ImageFont.truetype("arial.ttf", 12)
            except:
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
                except:
                    font = ImageFont.load_default()
            
            # Фон для текста
            text_bbox = draw.textbbox((x0, y0 - 15), label, font=font)
            draw.rectangle(text_bbox, fill=color, outline=color)
            draw.text((x0, y0 - 15), label, fill="white", font=font)
        
        return draw_img
    except Exception as e:
        st.error(f"Ошибка рендеринга: {e}")
        return None


def save_annotation(output_path: Path) -> bool:
    """Сохранение разметки в JSON."""
    try:
        stats = {
            "total_elements": len(st.session_state.elements),
            "total_pages": st.session_state.total_pages,
            "elements_by_type": {},
            "table_count": 0,
            "image_count": 0
        }
        
        pages = set()
        for elem in st.session_state.elements:
            elem_type = elem["type"]
            stats["elements_by_type"][elem_type] = stats["elements_by_type"].get(elem_type, 0) + 1
            
            if elem.get("page_number"):
                pages.add(elem["page_number"])
            
            if elem_type == "table":
                stats["table_count"] += 1
            elif elem_type == "image":
                stats["image_count"] += 1
        
        stats["total_pages"] = len(pages) if pages else st.session_state.total_pages
        
        annotation = {
            "document_id": st.session_state.pdf_path.stem if st.session_state.pdf_path else "unknown",
            "source_file": str(st.session_state.pdf_path) if st.session_state.pdf_path else "",
            "document_format": "pdf",
            "annotation_version": "1.0",
            "annotator": "auto_visual",
            "annotation_date": datetime.now().isoformat(),
            "elements": st.session_state.elements,
            "statistics": stats
        }
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(annotation, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        st.error(f"Ошибка сохранения: {e}")
        return False


def load_annotation(annotation_path: Path) -> bool:
    """Загрузка существующей разметки."""
    try:
        with open(annotation_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        st.session_state.elements = data.get("elements", [])
        if st.session_state.elements:
            # Находим максимальный порядковый номер
            max_order = max(elem.get("order", -1) for elem in st.session_state.elements)
            st.session_state.current_order = max_order + 1
        else:
            st.session_state.current_order = 0
        
        return True
    except Exception as e:
        st.error(f"Ошибка загрузки разметки: {e}")
        return False


def main():
    st.title("🎨 Визуальная разметка документов с автоматической предразметкой")
    
    # Боковая панель
    with st.sidebar:
        st.header("📂 Загрузка файлов")
        
        uploaded_pdf = st.file_uploader("Загрузите PDF файл", type=["pdf"])
        if uploaded_pdf:
            temp_pdf = Path("temp_uploaded.pdf")
            with open(temp_pdf, "wb") as f:
                f.write(uploaded_pdf.getbuffer())
            
            if load_pdf(temp_pdf):
                st.success(f"PDF загружен: {uploaded_pdf.name}")
                st.info(f"Страниц: {st.session_state.total_pages}")
        
        # Выбор из списка
        st.subheader("Или выберите из списка")
        test_files_dir = Path("test_files_for_metrics")
        if test_files_dir.exists():
            pdf_files = list(test_files_dir.glob("*.pdf"))
            if pdf_files:
                selected_file = st.selectbox(
                    "Выберите файл",
                    options=pdf_files,
                    format_func=lambda x: x.name
                )
                if st.button("Загрузить выбранный файл"):
                    if load_pdf(selected_file):
                        st.success(f"Загружен: {selected_file.name}")
                        st.rerun()
        
        st.divider()
        
        # Автоматическая предразметка
        st.subheader("🤖 Автоматическая предразметка")
        if st.session_state.pdf_path:
            if st.button("✨ Создать автоматическую разметку", type="primary"):
                with st.spinner("Создание предварительной разметки..."):
                    auto_elements = create_auto_annotation(st.session_state.pdf_path)
                    if auto_elements:
                        st.session_state.elements = auto_elements
                        # current_order должен быть следующим после последнего элемента
                        # Если элементы начинаются с 0, то следующий будет len(elements)
                        st.session_state.current_order = len(auto_elements)
                        st.success(f"✅ Создано {len(auto_elements)} элементов (ID: elem_0000 - elem_{len(auto_elements)-1:04d})")
                        st.rerun()
                    else:
                        st.warning("Не удалось создать автоматическую разметку")
        
        st.divider()
        
        # Загрузка существующей разметки
        st.subheader("📥 Загрузка разметки")
        uploaded_annotation = st.file_uploader("Загрузите JSON разметку", type=["json"])
        if uploaded_annotation:
            temp_json = Path("temp_annotation.json")
            with open(temp_json, "wb") as f:
                f.write(uploaded_annotation.getbuffer())
            
            if load_annotation(temp_json):
                st.success("Разметка загружена")
                st.rerun()
        
        st.divider()
        
        # Сохранение
        st.subheader("💾 Сохранение")
        if st.session_state.pdf_path:
            default_output = f"annotations/{st.session_state.pdf_path.stem}_annotation.json"
            output_path = st.text_input("Путь для сохранения", value=default_output)
            
            if st.button("💾 Сохранить разметку", type="primary"):
                if save_annotation(Path(output_path)):
                    st.success(f"Разметка сохранена: {output_path}")
                    st.balloons()
        
        st.divider()
        
        # Легенда цветов
        st.subheader("🎨 Легенда цветов")
        for elem_type, color in ELEMENT_COLORS.items():
            st.markdown(f'<span style="color: {color}; font-weight: bold;">■</span> {elem_type}', unsafe_allow_html=True)
        
        st.divider()
        
        # Статистика
        st.subheader("📊 Статистика")
        st.metric("Элементов", len(st.session_state.elements))
        st.metric("Страниц", st.session_state.total_pages)
        
        if st.session_state.elements:
            elem_types = {}
            for elem in st.session_state.elements:
                elem_type = elem.get("type", "unknown")
                elem_types[elem_type] = elem_types.get(elem_type, 0) + 1
            
            st.write("**По типам:**")
            for elem_type, count in sorted(elem_types.items()):
                color = ELEMENT_COLORS.get(elem_type, "#000000")
                st.markdown(f'<span style="color: {color};">■</span> {elem_type}: {count}', unsafe_allow_html=True)
    
    # Основная область
    if not st.session_state.pdf_doc:
        st.info("👈 Загрузите PDF файл в боковой панели")
        return
    
    # Навигация
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("◀ Предыдущая", disabled=st.session_state.current_page == 0):
            st.session_state.current_page -= 1
            st.rerun()
    
    with col2:
        page_num = st.slider(
            "Страница",
            min_value=1,
            max_value=st.session_state.total_pages,
            value=st.session_state.current_page + 1,
            key="page_slider"
        )
        if page_num - 1 != st.session_state.current_page:
            st.session_state.current_page = page_num - 1
            st.rerun()
    
    with col3:
        if st.button("Следующая ▶", disabled=st.session_state.current_page >= st.session_state.total_pages - 1):
            st.session_state.current_page += 1
            st.rerun()
    
    # Отображение страницы с разметкой
    st.subheader(f"Страница {st.session_state.current_page + 1} из {st.session_state.total_pages}")
    
    # Показываем информацию о разметке
    if st.session_state.elements:
        st.info(f"📋 Всего элементов в разметке: {len(st.session_state.elements)} (ID: elem_0000 - elem_{len(st.session_state.elements)-1:04d})")
    else:
        st.warning("⚠️ Разметка пуста. Создайте автоматическую разметку или добавьте элементы вручную.")
    
    # Используем render_scale=2.0 (по умолчанию в парсере)
    # Если нужно, можно добавить настройку в интерфейсе
    annotated_img = render_pdf_page_with_annotations(
        st.session_state.current_page,
        st.session_state.elements,
        scale=1.5,
        render_scale=2.0
    )
    
    if annotated_img:
        st.image(annotated_img, use_container_width=True)
        
        # Информация об элементах на странице
        page_elements = [
            e for e in st.session_state.elements 
            if e.get("page_number") == st.session_state.current_page + 1
        ]
        
        # Сортируем элементы по order для правильного отображения
        page_elements.sort(key=lambda x: x.get("order", 0))
        
        if page_elements:
            st.write(f"**Элементов на странице: {len(page_elements)}**")
            st.write(f"**Всего элементов в документе: {len(st.session_state.elements)}**")
            
            # Таблица элементов
            for elem in page_elements:
                elem_type = elem.get("type", "unknown")
                color = ELEMENT_COLORS.get(elem_type, "#000000")
                
                with st.expander(
                    f'<span style="color: {color};">■</span> {elem["id"]} - [{elem_type}]',
                    expanded=False
                ):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**ID:** {elem['id']}")
                        st.write(f"**Тип:** {elem_type}")
                        st.write(f"**Порядок:** {elem.get('order', -1)}")
                        st.write(f"**Родитель:** {elem.get('parent_id', 'None')}")
                    
                    with col2:
                        st.write(f"**Координаты:** {elem.get('bbox', 'Не указаны')}")
                        st.text_area(
                            "Содержимое",
                            value=elem.get('content', ''),
                            height=100,
                            key=f"edit_content_{elem['id']}"
                        )
                        
                        # Кнопки редактирования
                        if st.button(f"💾 Сохранить изменения", key=f"save_{elem['id']}"):
                            # Обновляем содержимое
                            new_content = st.session_state.get(f"edit_content_{elem['id']}", elem.get('content', ''))
                            elem['content'] = new_content
                            st.success("Изменения сохранены")
                            st.rerun()
                        
                        if st.button(f"🗑️ Удалить", key=f"delete_{elem['id']}"):
                            st.session_state.elements.remove(elem)
                            st.rerun()
        else:
            st.info("На этой странице нет размеченных элементов")
    
    # Форма добавления нового элемента
    with st.expander("➕ Добавить новый элемент", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            elem_type = st.selectbox("Тип элемента", options=ELEMENT_TYPES, key="new_elem_type")
            page_number = st.number_input(
                "Номер страницы",
                min_value=1,
                max_value=st.session_state.total_pages,
                value=st.session_state.current_page + 1,
                key="new_elem_page"
            )
        
        with col2:
            content = st.text_area("Текстовое содержимое", height=100, key="new_elem_content")
            parent_id = st.selectbox(
                "Родительский элемент",
                options=[None] + [elem["id"] for elem in st.session_state.elements],
                format_func=lambda x: "Нет родителя" if x is None else f"{x}",
                key="new_elem_parent"
            )
        
        # Координаты
        st.subheader("Координаты (bbox)")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            x0 = st.number_input("x0", value=0.0, key="new_bbox_x0", step=1.0)
        with col2:
            y0 = st.number_input("y0", value=0.0, key="new_bbox_y0", step=1.0)
        with col3:
            x1 = st.number_input("x1", value=0.0, key="new_bbox_x1", step=1.0)
        with col4:
            y1 = st.number_input("y1", value=0.0, key="new_bbox_y1", step=1.0)
        
        bbox = [x0, y0, x1, y1] if (x0, y0, x1, y1) != (0, 0, 0, 0) else None
        
        if st.button("➕ Добавить элемент", type="primary"):
            # ID начинается с 0, используем current_order для нового элемента
            new_id = f"elem_{st.session_state.current_order:04d}"
            element = {
                "id": new_id,
                "type": elem_type,
                "content": content,
                "parent_id": parent_id,
                "order": st.session_state.current_order,
                "page_number": page_number,
                "bbox": bbox,
                "metadata": {}
            }
            
            st.session_state.elements.append(element)
            st.session_state.current_order += 1
            st.success(f"✅ Элемент добавлен: {element['id']} (order: {element['order']})")
            st.rerun()


if __name__ == "__main__":
    main()

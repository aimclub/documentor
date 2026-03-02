"""
Графический инструмент для ручной разметки документов на основе Streamlit.

Использование:
    streamlit run gui_annotation_tool.py
"""

import streamlit as st
import json
import fitz  # PyMuPDF
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import io
from PIL import Image
import base64

try:
    from streamlit_drawable_canvas import st_canvas
    HAS_DRAWABLE_CANVAS = True
except ImportError:
    HAS_DRAWABLE_CANVAS = False
    st.warning("⚠️ streamlit-drawable-canvas не установлен. Установите: pip install streamlit-drawable-canvas")

# Конфигурация страницы
st.set_page_config(
    page_title="Инструмент разметки документов",
    page_icon="📝",
    layout="wide"
)

# Типы элементов
ELEMENT_TYPES = [
    "title", "header_1", "header_2", "header_3", "header_4", "header_5", "header_6",
    "text", "image", "table", "formula", "list_item", "caption", "footnote",
    "page_header", "page_footer", "link", "code_block"
]

# Инициализация состояния
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


def load_pdf(pdf_path: Path) -> bool:
    """Загрузка PDF документа."""
    try:
        st.session_state.pdf_doc = fitz.open(str(pdf_path))
        st.session_state.total_pages = len(st.session_state.pdf_doc)
        st.session_state.current_page = 0
        st.session_state.pdf_path = pdf_path
        return True
    except Exception as e:
        st.error(f"Ошибка загрузки PDF: {e}")
        return False


def render_pdf_page(page_num: int, scale: float = 1.5) -> Optional[Image.Image]:
    """Рендеринг страницы PDF в изображение."""
    if not st.session_state.pdf_doc or page_num < 0 or page_num >= st.session_state.total_pages:
        return None
    
    try:
        page = st.session_state.pdf_doc[page_num]
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return img
    except Exception as e:
        st.error(f"Ошибка рендеринга страницы: {e}")
        return None


def save_annotation(output_path: Path) -> bool:
    """Сохранение разметки в JSON."""
    try:
        # Вычисляем статистику
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
        
        # Создаем структуру разметки
        annotation = {
            "document_id": st.session_state.pdf_path.stem if st.session_state.pdf_path else "unknown",
            "source_file": str(st.session_state.pdf_path) if st.session_state.pdf_path else "",
            "document_format": "pdf",
            "annotation_version": "1.0",
            "annotator": "manual_gui",
            "annotation_date": datetime.now().isoformat(),
            "elements": st.session_state.elements,
            "statistics": stats
        }
        
        # Сохраняем
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
            max_order = max(elem.get("order", 0) for elem in st.session_state.elements)
            st.session_state.current_order = max_order + 1
        else:
            st.session_state.current_order = 0
        
        return True
    except Exception as e:
        st.error(f"Ошибка загрузки разметки: {e}")
        return False


def main():
    st.title("📝 Инструмент ручной разметки документов")
    
    # Боковая панель для загрузки файлов
    with st.sidebar:
        st.header("📂 Загрузка файлов")
        
        # Загрузка PDF
        uploaded_pdf = st.file_uploader("Загрузите PDF файл", type=["pdf"])
        if uploaded_pdf:
            # Сохраняем временный файл
            temp_pdf = Path("temp_uploaded.pdf")
            with open(temp_pdf, "wb") as f:
                f.write(uploaded_pdf.getbuffer())
            
            if load_pdf(temp_pdf):
                st.success(f"PDF загружен: {uploaded_pdf.name}")
                st.info(f"Страниц: {st.session_state.total_pages}")
        
        # Или выбор из списка
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
                st.write(f"- {elem_type}: {count}")
    
    # Основная область
    if not st.session_state.pdf_doc:
        st.info("👈 Загрузите PDF файл в боковой панели")
        return
    
    # Навигация по страницам
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
    
    # Отображение страницы с возможностью рисования
    st.subheader(f"Страница {st.session_state.current_page + 1} из {st.session_state.total_pages}")
    
    page_img = render_pdf_page(st.session_state.current_page, scale=1.5)
    if page_img:
        # Сохраняем изображение во временный буфер
        img_buffer = io.BytesIO()
        page_img.save(img_buffer, format='PNG')
        img_data = img_buffer.getvalue()
        
        # Canvas для рисования
        if HAS_DRAWABLE_CANVAS:
            # Режим рисования
            drawing_mode = st.radio(
                "Режим",
                ["Прямоугольник", "Просмотр"],
                horizontal=True,
                key="drawing_mode"
            )
            
            if drawing_mode == "Прямоугольник":
                # Canvas с возможностью рисования прямоугольников
                # Сохраняем изображение во временный файл для обхода проблемы с API
                import tempfile
                import os
                
                try:
                    # Создаем временный файл
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                        temp_img_path = tmp_file.name
                        page_img.save(temp_img_path, format='PNG')
                    
                    # Загружаем изображение из файла
                    bg_image = Image.open(temp_img_path)
                    
                    canvas_result = st_canvas(
                        fill_color="rgba(255, 165, 0, 0.3)",  # Полупрозрачный оранжевый
                        stroke_width=2,
                        stroke_color="#FF0000",  # Красная обводка
                        background_image=bg_image,  # PIL Image из файла
                        update_streamlit=True,
                        drawing_mode="rect",
                        point_display_radius=0,
                        key=f"canvas_{st.session_state.current_page}",
                        width=page_img.width,
                        height=page_img.height,
                    )
                    
                    # Удаляем временный файл после использования
                    try:
                        os.unlink(temp_img_path)
                    except:
                        pass
                        
                except Exception as e:
                    st.error(f"❌ Ошибка canvas: {e}")
                    st.warning("💡 Canvas недоступен из-за несовместимости версий.")
                    
                    # Предложение использовать упрощенную версию
                    st.info("""
                    **Рекомендация:** Используйте упрощенную версию без canvas:
                    ```bash
                    streamlit run gui_annotation_tool_simple.py
                    ```
                    """)
                    
                    # Fallback: показываем изображение без canvas
                    st.image(page_img, use_container_width=True)
                    canvas_result = None
                    
                    # Показываем инструкцию
                    with st.expander("📝 Как ввести координаты вручную", expanded=False):
                        st.write("""
                        **Способ 1: Использовать PDF-просмотрщик**
                        1. Откройте PDF в Adobe Reader или другом просмотрщике
                        2. Используйте инструменты измерения для определения координат
                        3. Введите координаты в форму ниже
                        
                        **Способ 2: Обновить библиотеку**
                        ```bash
                        pip install --upgrade streamlit streamlit-drawable-canvas
                        ```
                        Затем перезапустите приложение.
                        
                        **Способ 3: Использовать упрощенную версию**
                        Запустите `gui_annotation_tool_simple.py` - она работает без canvas.
                        
                        **Способ 4: Приблизительные координаты**
                        - Можно указать примерные координаты
                        - Главное - правильный порядок и иерархия элементов
                        """)
                
                # Обработка нарисованных прямоугольников
                if canvas_result and hasattr(canvas_result, 'json_data') and canvas_result.json_data is not None:
                    objects = canvas_result.json_data.get("objects", [])
                    if objects:
                        # Берем последний нарисованный прямоугольник
                        last_rect = objects[-1]
                        if last_rect.get("type") == "rect":
                            left = last_rect.get("left", 0)
                            top = last_rect.get("top", 0)
                            width = last_rect.get("width", 0)
                            height = last_rect.get("height", 0)
                            
                            # Конвертируем координаты canvas в координаты PDF
                            # Получаем размеры страницы PDF
                            if st.session_state.pdf_doc:
                                pdf_page = st.session_state.pdf_doc[st.session_state.current_page]
                                pdf_width = pdf_page.rect.width
                                pdf_height = pdf_page.rect.height
                                
                                canvas_width = page_img.width
                                canvas_height = page_img.height
                                
                                # Коэффициенты масштабирования
                                scale_x = pdf_width / canvas_width
                                scale_y = pdf_height / canvas_height
                                
                                # Конвертируем координаты
                                x0 = left * scale_x
                                y0 = top * scale_y
                                x1 = (left + width) * scale_x
                                y1 = (top + height) * scale_y
                            else:
                                # Fallback: используем координаты как есть
                                x0 = left
                                y0 = top
                                x1 = left + width
                                y1 = top + height
                            
                            # Обновляем координаты в форме
                            st.session_state.bbox_x0 = x0
                            st.session_state.bbox_y0 = y0
                            st.session_state.bbox_x1 = x1
                            st.session_state.bbox_y1 = y1
                            
                            st.success(f"✅ Координаты выделены: [{x0:.1f}, {y0:.1f}, {x1:.1f}, {y1:.1f}]")
                            
                            # Показываем информацию о выделении
                            with st.expander("📐 Информация о выделении", expanded=False):
                                st.write(f"**Координаты PDF:** [{x0:.1f}, {y0:.1f}, {x1:.1f}, {y1:.1f}]")
                                if st.session_state.pdf_doc:
                                    pdf_page = st.session_state.pdf_doc[st.session_state.current_page]
                                    st.write(f"**Размер:** {(x1-x0):.1f} x {(y1-y0):.1f} (в координатах PDF)")
                                
                                # Кнопка для применения координат
                                if st.button("🔄 Обновить форму с координатами", key="apply_coords"):
                                    st.rerun()
            else:
                # Просто просмотр без рисования
                st.image(page_img, use_container_width=True)
        else:
            # Fallback: просто показываем изображение
            st.image(page_img, use_container_width=True)
            st.info("💡 Установите streamlit-drawable-canvas для интерактивного выделения координат")
    
    # Форма добавления элемента
    with st.expander("➕ Добавить элемент", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            elem_type = st.selectbox("Тип элемента", options=ELEMENT_TYPES, key="elem_type")
            page_number = st.number_input(
                "Номер страницы",
                min_value=1,
                max_value=st.session_state.total_pages,
                value=st.session_state.current_page + 1,
                key="elem_page"
            )
        
        with col2:
            content = st.text_area("Текстовое содержимое", height=100, key="elem_content")
            parent_id = st.selectbox(
                "Родительский элемент",
                options=[None] + [elem["id"] for elem in st.session_state.elements],
                format_func=lambda x: "Нет родителя" if x is None else f"{x}",
                key="elem_parent"
            )
        
        # Координаты bbox
        st.subheader("Координаты (bbox)")
        st.info("💡 Выделите область на изображении выше, чтобы автоматически заполнить координаты")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            x0 = st.number_input("x0", value=st.session_state.get("bbox_x0", 0.0), key="bbox_x0")
        with col2:
            y0 = st.number_input("y0", value=st.session_state.get("bbox_y0", 0.0), key="bbox_y0")
        with col3:
            x1 = st.number_input("x1", value=st.session_state.get("bbox_x1", 0.0), key="bbox_x1")
        with col4:
            y1 = st.number_input("y1", value=st.session_state.get("bbox_y1", 0.0), key="bbox_y1")
        
        # Кнопка для очистки координат
        if st.button("🗑️ Очистить координаты"):
            st.session_state.bbox_x0 = 0.0
            st.session_state.bbox_y0 = 0.0
            st.session_state.bbox_x1 = 0.0
            st.session_state.bbox_y1 = 0.0
            st.rerun()
        
        bbox = [x0, y0, x1, y1] if (x0, y0, x1, y1) != (0, 0, 0, 0) else None
        
        if st.button("➕ Добавить элемент", type="primary"):
            element = {
                "id": f"elem_{len(st.session_state.elements) + 1:04d}",
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
            st.success(f"Элемент добавлен: {element['id']}")
            st.rerun()
    
    # Список элементов
    st.divider()
    st.subheader(f"📋 Все элементы ({len(st.session_state.elements)})")
    
    if st.session_state.elements:
        # Фильтры
        col1, col2 = st.columns(2)
        with col1:
            filter_type = st.selectbox(
                "Фильтр по типу",
                options=["Все"] + list(set(elem["type"] for elem in st.session_state.elements)),
                key="filter_type"
            )
        with col2:
            filter_page = st.selectbox(
                "Фильтр по странице",
                options=["Все"] + list(set(elem.get("page_number", 0) for elem in st.session_state.elements)),
                key="filter_page"
            )
        
        # Отфильтрованные элементы
        filtered_elements = st.session_state.elements
        if filter_type != "Все":
            filtered_elements = [e for e in filtered_elements if e["type"] == filter_type]
        if filter_page != "Все":
            filtered_elements = [e for e in filtered_elements if e.get("page_number") == filter_page]
        
        # Таблица элементов
        for i, elem in enumerate(filtered_elements):
            with st.expander(f"{elem['id']} - [{elem['type']}] {elem['content'][:50]}..."):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**ID:** {elem['id']}")
                    st.write(f"**Тип:** {elem['type']}")
                    st.write(f"**Порядок:** {elem.get('order', -1)}")
                    st.write(f"**Страница:** {elem.get('page_number', '?')}")
                    st.write(f"**Родитель:** {elem.get('parent_id', 'None')}")
                
                with col2:
                    st.write(f"**Координаты:** {elem.get('bbox', 'Не указаны')}")
                    st.text_area("Содержимое", value=elem['content'], height=100, key=f"content_{i}", disabled=True)
                
                # Кнопки редактирования/удаления
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"✏️ Редактировать", key=f"edit_{i}"):
                        st.session_state[f"editing_{i}"] = True
                
                with col2:
                    if st.button(f"🗑️ Удалить", key=f"delete_{i}"):
                        st.session_state.elements.remove(elem)
                        st.rerun()
    else:
        st.info("Элементы не добавлены. Используйте форму выше для добавления.")


if __name__ == "__main__":
    main()

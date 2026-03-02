"""
Упрощенный графический инструмент для разметки без canvas (альтернатива).

Использует простой подход с кликами по изображению для определения координат.
"""

import streamlit as st
import json
import fitz  # PyMuPDF
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import io
from PIL import Image

# Конфигурация страницы
st.set_page_config(
    page_title="Инструмент разметки документов (упрощенный)",
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
if 'click_coords' not in st.session_state:
    st.session_state.click_coords = []  # [(x, y), ...] для определения bbox


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
            "annotator": "manual_gui_simple",
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


def main():
    st.title("📝 Инструмент ручной разметки документов (упрощенный)")
    st.info("💡 Этот вариант работает без canvas. Используйте ручной ввод координат.")
    
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
    
    # Отображение страницы
    st.subheader(f"Страница {st.session_state.current_page + 1} из {st.session_state.total_pages}")
    
    page_img = render_pdf_page(st.session_state.current_page, scale=1.5)
    if page_img:
        st.image(page_img, use_container_width=True)
        
        # Информация о размерах для помощи в определении координат
        if st.session_state.pdf_doc:
            pdf_page = st.session_state.pdf_doc[st.session_state.current_page]
            with st.expander("📏 Информация о размерах страницы"):
                st.write(f"**Размер PDF страницы:** {pdf_page.rect.width:.1f} x {pdf_page.rect.height:.1f}")
                st.write(f"**Размер изображения:** {page_img.width} x {page_img.height}")
                st.write(f"**Масштаб:** {pdf_page.rect.width / page_img.width:.3f}")
                st.info("💡 Используйте эти размеры для определения координат элементов")
    
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
        st.info("💡 Определите координаты элемента на странице. Используйте PDF-просмотрщик для точных значений.")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            x0 = st.number_input("x0 (левая граница)", value=st.session_state.get("bbox_x0", 0.0), key="bbox_x0", step=1.0)
        with col2:
            y0 = st.number_input("y0 (верхняя граница)", value=st.session_state.get("bbox_y0", 0.0), key="bbox_y0", step=1.0)
        with col3:
            x1 = st.number_input("x1 (правая граница)", value=st.session_state.get("bbox_x1", 0.0), key="bbox_x1", step=1.0)
        with col4:
            y1 = st.number_input("y1 (нижняя граница)", value=st.session_state.get("bbox_y1", 0.0), key="bbox_y1", step=1.0)
        
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
        
        filtered_elements = st.session_state.elements
        if filter_type != "Все":
            filtered_elements = [e for e in filtered_elements if e["type"] == filter_type]
        if filter_page != "Все":
            filtered_elements = [e for e in filtered_elements if e.get("page_number") == filter_page]
        
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
                
                col1, col2 = st.columns(2)
                with col2:
                    if st.button(f"🗑️ Удалить", key=f"delete_{i}"):
                        st.session_state.elements.remove(elem)
                        st.rerun()
    else:
        st.info("Элементы не добавлены. Используйте форму выше для добавления.")


if __name__ == "__main__":
    main()

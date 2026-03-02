"""
Комплексный инструмент для разметки документов (Streamlit).

Возможности:
- Визуализация PDF страниц с цветными bbox элементов
- Добавление / редактирование / удаление элементов
- Разметка таблиц (HTML + массив ячеек)
- Разметка изображений (base64)
- Автоматическая предразметка через наш парсер (с предупреждением о bias)
- Импорт/экспорт JSON (annotation_schema v2.0)
- Валидация разметки
- Извлечение текста со страницы в один клик

Запуск:
    cd experiments/metrics
    streamlit run annotation_tool.py
"""

import streamlit as st
import json
import base64
import io
import re
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from collections import OrderedDict

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None

# ──────────────────────────────────────────────
# Конфигурация
# ──────────────────────────────────────────────
ANNOTATION_VERSION = "2.0"

ELEMENT_TYPES = [
    "title", "header_1", "header_2", "header_3", "header_4", "header_5", "header_6",
    "text", "image", "table", "formula", "list_item", "caption", "footnote",
    "page_header", "page_footer", "link", "code_block",
]

ELEMENT_COLORS = {
    "title":       "#FF0000",
    "header_1":    "#FF6600",
    "header_2":    "#FF9900",
    "header_3":    "#FFCC00",
    "header_4":    "#CCCC00",
    "header_5":    "#99CC00",
    "header_6":    "#66CC00",
    "text":        "#00CCFF",
    "table":       "#9900FF",
    "image":       "#FF00FF",
    "formula":     "#0099FF",
    "list_item":   "#00FF99",
    "caption":     "#FF0099",
    "footnote":    "#CC6600",
    "page_header": "#999999",
    "page_footer": "#666666",
    "link":        "#00FF00",
    "code_block":  "#555555",
}

TYPE_LABELS_RU = {
    "title":       "Заголовок документа",
    "header_1":    "Заголовок 1",
    "header_2":    "Заголовок 2",
    "header_3":    "Заголовок 3",
    "header_4":    "Заголовок 4",
    "header_5":    "Заголовок 5",
    "header_6":    "Заголовок 6",
    "text":        "Текст",
    "table":       "Таблица",
    "image":       "Изображение",
    "formula":     "Формула",
    "list_item":   "Элемент списка",
    "caption":     "Подпись",
    "footnote":    "Сноска",
    "page_header": "Колонтитул (верх)",
    "page_footer": "Колонтитул (низ)",
    "link":        "Ссылка",
    "code_block":  "Блок кода",
}

TEST_FILES_DIR = Path("test_files_for_metrics")
ANNOTATIONS_DIR = Path("annotations")


# ──────────────────────────────────────────────
# Настройка страницы Streamlit
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Annotation Tool v2",
    page_icon="🏷️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ──────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────
def _init_state():
    """Инициализация session_state при первом запуске."""
    defaults = {
        "elements": [],
        "next_order": 0,
        "pdf_bytes": None,
        "pdf_doc": None,
        "total_pages": 0,
        "current_page": 0,
        "pdf_filename": None,
        "annotator_name": "",
        "doc_format": "pdf",
        "editing_id": None,  # id элемента, который сейчас редактируется
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _next_id() -> str:
    """Генерирует следующий ID элемента вида elem_0000."""
    existing_ids = {e["id"] for e in st.session_state.elements}
    idx = len(st.session_state.elements)
    while True:
        candidate = f"elem_{idx:04d}"
        if candidate not in existing_ids:
            return candidate
        idx += 1


def _next_order() -> int:
    """Возвращает следующий порядковый номер."""
    if st.session_state.elements:
        return max(e.get("order", 0) for e in st.session_state.elements) + 1
    return 0


def _load_pdf_from_bytes(data: bytes, filename: str) -> bool:
    """Загружает PDF из bytes."""
    if fitz is None:
        st.error("PyMuPDF (fitz) не установлен. pip install PyMuPDF")
        return False
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        st.session_state.pdf_bytes = data
        st.session_state.pdf_doc = doc
        st.session_state.total_pages = len(doc)
        st.session_state.current_page = 0
        st.session_state.pdf_filename = filename
        return True
    except Exception as exc:
        st.error(f"Ошибка загрузки PDF: {exc}")
        return False


def render_page(page_idx: int, scale: float = 1.5) -> Optional["Image.Image"]:
    """Рендерит страницу PDF в PIL Image."""
    doc = st.session_state.pdf_doc
    if doc is None or page_idx < 0 or page_idx >= len(doc):
        return None
    page = doc[page_idx]
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def render_page_with_boxes(
    page_idx: int,
    elements: List[Dict[str, Any]],
    scale: float = 1.5,
    render_scale: float = 2.0,
    selected_id: Optional[str] = None,
) -> Optional["Image.Image"]:
    """Рендерит страницу PDF и рисует цветные рамки вокруг элементов."""
    img = render_page(page_idx, scale)
    if img is None:
        return None

    draw = ImageDraw.Draw(img)

    # Элементы текущей страницы (page_number: 1-based)
    page_elems = [e for e in elements if e.get("page_number") == page_idx + 1]

    scale_ratio = scale / render_scale

    try:
        font = ImageFont.truetype("arial.ttf", 13)
    except Exception:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
        except Exception:
            font = ImageFont.load_default()

    for elem in page_elems:
        bbox = elem.get("bbox")
        if not bbox or len(bbox) != 4:
            continue

        x0, y0, x1, y1 = [v * scale_ratio for v in bbox]
        x0 = max(0, min(x0, img.width))
        y0 = max(0, min(y0, img.height))
        x1 = max(0, min(x1, img.width))
        y1 = max(0, min(y1, img.height))
        if x1 <= x0 or y1 <= y0:
            continue

        etype = elem.get("type", "text")
        color = ELEMENT_COLORS.get(etype, "#000000")
        width = 4 if elem.get("id") == selected_id else 2
        draw.rectangle([x0, y0, x1, y1], outline=color, width=width)

        label = f"{etype} ({elem['id']})"
        tb = draw.textbbox((x0, y0 - 16), label, font=font)
        draw.rectangle(tb, fill=color)
        draw.text((x0, y0 - 16), label, fill="white", font=font)

    return img


def extract_page_text(page_idx: int) -> str:
    """Извлекает текст со страницы PDF через PyMuPDF."""
    doc = st.session_state.pdf_doc
    if doc is None:
        return ""
    page = doc[page_idx]
    return page.get_text("text")


def extract_page_images_b64(page_idx: int) -> List[Dict[str, str]]:
    """Извлекает изображения со страницы в base64."""
    doc = st.session_state.pdf_doc
    if doc is None:
        return []
    page = doc[page_idx]
    images = []
    for img_info in page.get_images(full=True):
        xref = img_info[0]
        try:
            base_image = doc.extract_image(xref)
            img_bytes = base_image["image"]
            ext = base_image.get("ext", "png")
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            images.append({
                "data": f"data:image/{ext};base64,{b64}",
                "format": ext,
                "width": base_image.get("width", 0),
                "height": base_image.get("height", 0),
            })
        except Exception:
            pass
    return images


def html_table_to_cells(html: str) -> List[Dict[str, Any]]:
    """Парсит HTML-таблицу и возвращает массив ячеек [{row, col, content, rowspan, colspan}]."""
    cells = []
    try:
        # Простой парсер на regex (без BeautifulSoup чтобы не добавлять зависимость)
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


# ──────────────────────────────────────────────
# Сохранение / загрузка
# ──────────────────────────────────────────────
def build_annotation_json() -> Dict[str, Any]:
    """Собирает финальный JSON разметки."""
    elements = st.session_state.elements
    stats: Dict[str, Any] = {
        "total_elements": len(elements),
        "total_pages": st.session_state.total_pages,
        "elements_by_type": {},
        "table_count": 0,
        "image_count": 0,
    }
    pages = set()
    for e in elements:
        t = e["type"]
        stats["elements_by_type"][t] = stats["elements_by_type"].get(t, 0) + 1
        if e.get("page_number"):
            pages.add(e["page_number"])
        if t == "table":
            stats["table_count"] += 1
        elif t == "image":
            stats["image_count"] += 1
    if pages:
        stats["total_pages"] = max(pages)

    return {
        "document_id": Path(st.session_state.pdf_filename or "unknown").stem,
        "source_file": st.session_state.pdf_filename or "",
        "document_format": st.session_state.doc_format,
        "annotation_version": ANNOTATION_VERSION,
        "annotator": st.session_state.annotator_name or "unknown",
        "annotation_date": datetime.now().isoformat(),
        "elements": elements,
        "statistics": stats,
    }


def save_annotation(path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = build_annotation_json()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as exc:
        st.error(f"Ошибка сохранения: {exc}")
        return False


def load_annotation_json(data: Dict[str, Any]):
    """Загружает элементы из JSON-разметки в session_state."""
    st.session_state.elements = data.get("elements", [])
    if st.session_state.elements:
        st.session_state.next_order = max(e.get("order", 0) for e in st.session_state.elements) + 1
    else:
        st.session_state.next_order = 0
    st.session_state.annotator_name = data.get("annotator", "")
    st.session_state.doc_format = data.get("document_format", "pdf")


# ──────────────────────────────────────────────
# Валидация
# ──────────────────────────────────────────────
def validate_annotation() -> List[str]:
    """Проверяет текущую разметку, возвращает список ошибок."""
    errors: List[str] = []
    elements = st.session_state.elements

    if not elements:
        errors.append("Нет ни одного элемента")
        return errors

    ids = set()
    for i, e in enumerate(elements):
        eid = e.get("id", "")
        # Уникальность ID
        if eid in ids:
            errors.append(f"Дублирующийся ID: {eid}")
        ids.add(eid)

        # Обязательные поля
        if not e.get("type"):
            errors.append(f"{eid}: отсутствует тип (type)")
        if e.get("type") not in ELEMENT_TYPES:
            errors.append(f"{eid}: неизвестный тип '{e.get('type')}'")
        if "order" not in e:
            errors.append(f"{eid}: отсутствует порядок (order)")
        if "content" not in e:
            errors.append(f"{eid}: отсутствует содержимое (content)")

        # parent_id ссылается на существующий элемент
        pid = e.get("parent_id")
        if pid and pid not in ids and pid not in {el["id"] for el in elements}:
            errors.append(f"{eid}: parent_id '{pid}' не найден среди элементов")

        # Таблицы: HTML + cells
        if e.get("type") == "table":
            content = e.get("content", "")
            if not content or "<table" not in content.lower():
                errors.append(f"{eid}: таблица без HTML в content")
            ts = e.get("metadata", {}).get("table_structure", {})
            if not ts.get("cells"):
                errors.append(f"{eid}: таблица без cells в metadata.table_structure")

        # Изображения: base64
        if e.get("type") == "image":
            img_data = e.get("metadata", {}).get("image_data", "")
            if not img_data or "base64" not in img_data:
                errors.append(f"{eid}: изображение без base64 в metadata.image_data")

    # Проверка порядка
    orders = [e.get("order", -1) for e in elements]
    if sorted(orders) != list(range(len(orders))):
        errors.append(f"Порядок (order) не последовательный: ожидается 0..{len(elements)-1}")

    return errors


# ──────────────────────────────────────────────
# Авто-разметка
# ──────────────────────────────────────────────
def auto_annotate() -> List[Dict[str, Any]]:
    """Автоматическая предразметка через наш парсер."""
    try:
        from documentor import Pipeline
        from langchain_core.documents import Document as LCDoc

        pdf_bytes = st.session_state.pdf_bytes
        if not pdf_bytes:
            return []

        # Сохраняем во временный файл
        tmp_path = Path("_tmp_auto_annotate.pdf")
        tmp_path.write_bytes(pdf_bytes)

        pipeline = Pipeline()
        lc_doc = LCDoc(page_content="", metadata={"source": str(tmp_path)})
        parsed = pipeline.parse(lc_doc)

        elements = []
        for i, elem in enumerate(parsed.elements):
            # Конвертируем page_num из 0-based (0,1,2...) в 1-based (1,2,3...)
            page_num_0based = elem.metadata.get("page_num")
            page_number = None
            if page_num_0based is not None:
                page_number = page_num_0based + 1  # Конвертируем в 1-based
            
            element_data: Dict[str, Any] = {
                "id": f"elem_{i:04d}",
                "type": elem.type.value.lower(),
                "content": elem.content or "",
                "parent_id": elem.parent_id,
                "order": i,
                "page_number": page_number,
                "bbox": elem.metadata.get("bbox"),
                "metadata": {},
            }
            # Таблицы: перекладываем HTML
            if elem.type.value.lower() == "table" and elem.content:
                cells = html_table_to_cells(elem.content)
                element_data["metadata"]["table_structure"] = {
                    "html": elem.content,
                    "cells": cells,
                }
            # Изображения: base64
            if elem.type.value.lower() == "image":
                img_b64 = elem.metadata.get("image_data", "")
                if img_b64:
                    element_data["metadata"]["image_data"] = img_b64
                    element_data["metadata"]["image_format"] = "png"
            elements.append(element_data)

        # Удаляем временный файл
        try:
            tmp_path.unlink()
        except Exception:
            pass

        return elements
    except Exception as exc:
        st.error(f"Ошибка авто-разметки: {exc}")
        return []


# ──────────────────────────────────────────────
# UI: Боковая панель
# ──────────────────────────────────────────────
def sidebar():
    with st.sidebar:
        st.header("📂 Документ")

        # Загрузка PDF
        uploaded = st.file_uploader("Загрузите PDF", type=["pdf"], key="pdf_uploader")
        if uploaded is not None:
            data = uploaded.getvalue()
            if data != st.session_state.pdf_bytes:
                if _load_pdf_from_bytes(data, uploaded.name):
                    st.success(f"Загружен: {uploaded.name} ({st.session_state.total_pages} стр.)")

        # Или выбор из папки
        if TEST_FILES_DIR.exists():
            pdf_files = sorted(TEST_FILES_DIR.glob("*.pdf"))
            if pdf_files:
                sel = st.selectbox(
                    "Или из папки test_files_for_metrics",
                    options=["-- выбрать --"] + [f.name for f in pdf_files],
                    key="local_pdf_select",
                )
                if sel != "-- выбрать --" and st.button("Загрузить", key="btn_load_local"):
                    p = TEST_FILES_DIR / sel
                    if _load_pdf_from_bytes(p.read_bytes(), str(p)):
                        st.success(f"Загружен: {sel}")
                        st.rerun()

        st.divider()

        # Настройки
        st.subheader("Настройки")
        st.session_state.annotator_name = st.text_input(
            "Имя разметчика", value=st.session_state.annotator_name, key="annotator_input"
        )
        st.session_state.doc_format = st.selectbox(
            "Формат документа",
            options=["pdf", "pdf_scanned", "docx"],
            index=["pdf", "pdf_scanned", "docx"].index(st.session_state.doc_format),
            key="doc_format_select",
        )

        st.divider()

        # Импорт разметки
        st.subheader("📥 Импорт разметки")
        uploaded_json = st.file_uploader("Загрузить JSON", type=["json"], key="json_uploader")
        if uploaded_json is not None:
            try:
                ann_data = json.loads(uploaded_json.getvalue().decode("utf-8"))
                load_annotation_json(ann_data)
                st.success(f"Загружено {len(st.session_state.elements)} элементов")
                st.rerun()
            except Exception as exc:
                st.error(f"Ошибка: {exc}")

        st.divider()

        # Авто-разметка
        st.subheader("🤖 Авто-разметка")
        st.warning("Авто-разметка использует наш парсер. Для объективной оценки **проверьте и исправьте** результат вручную!")
        if st.session_state.pdf_bytes and st.button("Создать авто-разметку", key="btn_auto"):
            with st.spinner("Парсинг документа..."):
                auto_elems = auto_annotate()
            if auto_elems:
                st.session_state.elements = auto_elems
                st.session_state.next_order = len(auto_elems)
                st.success(f"Создано {len(auto_elems)} элементов")
                st.rerun()

        st.divider()

        # Экспорт
        st.subheader("💾 Экспорт")
        if st.session_state.elements:
            fname = Path(st.session_state.pdf_filename or "doc").stem
            default_path = f"annotations/{fname}_annotation.json"
            out_path = st.text_input("Путь сохранения", value=default_path, key="save_path_input")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("💾 Сохранить", type="primary", key="btn_save"):
                    if save_annotation(Path(out_path)):
                        st.success(f"Сохранено: {out_path}")
                        st.balloons()
            with col2:
                # Скачать как файл
                ann_json = json.dumps(build_annotation_json(), ensure_ascii=False, indent=2)
                st.download_button(
                    "⬇ Скачать JSON",
                    data=ann_json.encode("utf-8"),
                    file_name=f"{fname}_annotation.json",
                    mime="application/json",
                    key="btn_download",
                )

        st.divider()

        # Валидация
        st.subheader("✅ Валидация")
        if st.button("Проверить разметку", key="btn_validate"):
            errs = validate_annotation()
            if errs:
                for e in errs:
                    st.error(e)
            else:
                st.success("Разметка валидна!")

        st.divider()

        # Статистика
        st.subheader("📊 Статистика")
        st.metric("Элементов", len(st.session_state.elements))
        st.metric("Страниц PDF", st.session_state.total_pages)
        if st.session_state.elements:
            by_type: Dict[str, int] = {}
            for e in st.session_state.elements:
                t = e.get("type", "?")
                by_type[t] = by_type.get(t, 0) + 1
            for t, c in sorted(by_type.items()):
                color = ELEMENT_COLORS.get(t, "#000")
                st.markdown(f'<span style="color:{color};font-weight:bold">■</span> {t}: {c}', unsafe_allow_html=True)

        # Легенда
        with st.expander("🎨 Легенда цветов"):
            for t in ELEMENT_TYPES:
                color = ELEMENT_COLORS[t]
                label = TYPE_LABELS_RU.get(t, t)
                st.markdown(f'<span style="color:{color};font-weight:bold">■</span> {label} (`{t}`)', unsafe_allow_html=True)


# ──────────────────────────────────────────────
# UI: Навигация по страницам
# ──────────────────────────────────────────────
def page_navigation():
    if st.session_state.total_pages == 0:
        return

    c1, c2, c3 = st.columns([1, 3, 1])
    with c1:
        if st.button("◀ Назад", disabled=st.session_state.current_page == 0, key="btn_prev"):
            st.session_state.current_page -= 1
            st.rerun()
    with c2:
        page = st.slider(
            "Страница",
            min_value=1,
            max_value=st.session_state.total_pages,
            value=st.session_state.current_page + 1,
            key="page_slider",
        )
        if page - 1 != st.session_state.current_page:
            st.session_state.current_page = page - 1
            st.rerun()
    with c3:
        if st.button("Вперёд ▶", disabled=st.session_state.current_page >= st.session_state.total_pages - 1, key="btn_next"):
            st.session_state.current_page += 1
            st.rerun()


# ──────────────────────────────────────────────
# UI: Просмотр страницы
# ──────────────────────────────────────────────
def page_viewer():
    if st.session_state.pdf_doc is None:
        st.info("👈 Загрузите PDF в боковой панели")
        return

    page_idx = st.session_state.current_page
    st.subheader(f"Страница {page_idx + 1} / {st.session_state.total_pages}")

    img = render_page_with_boxes(
        page_idx,
        st.session_state.elements,
        scale=1.5,
        render_scale=2.0,
        selected_id=st.session_state.editing_id,
    )
    if img:
        st.image(img, use_container_width=True)

    # Быстрые действия
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📋 Извлечь текст страницы", key="btn_extract_text"):
            text = extract_page_text(page_idx)
            st.text_area("Текст страницы", value=text, height=200, key="extracted_text_area")
    with c2:
        if st.button("🖼 Извлечь изображения страницы", key="btn_extract_images"):
            imgs = extract_page_images_b64(page_idx)
            if imgs:
                for i, img_data in enumerate(imgs):
                    st.write(f"Изображение {i+1}: {img_data['width']}x{img_data['height']} ({img_data['format']})")
                    st.image(img_data["data"], width=300)
                st.session_state["_extracted_images"] = imgs
            else:
                st.info("На этой странице нет встроенных изображений")


# ──────────────────────────────────────────────
# UI: Форма добавления / редактирования элемента
# ──────────────────────────────────────────────
def element_form():
    editing_id = st.session_state.editing_id
    editing_elem = None
    if editing_id:
        editing_elem = next((e for e in st.session_state.elements if e["id"] == editing_id), None)
        if editing_elem is None:
            st.session_state.editing_id = None
            editing_id = None

    title = f"✏️ Редактирование: {editing_id}" if editing_elem else "➕ Новый элемент"
    with st.expander(title, expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            default_type_idx = 0
            if editing_elem and editing_elem["type"] in ELEMENT_TYPES:
                default_type_idx = ELEMENT_TYPES.index(editing_elem["type"])
            elem_type = st.selectbox(
                "Тип",
                options=ELEMENT_TYPES,
                index=default_type_idx,
                format_func=lambda t: f"{t} — {TYPE_LABELS_RU.get(t, '')}",
                key="form_type",
            )

            default_page = (editing_elem.get("page_number") or (st.session_state.current_page + 1)) if editing_elem else st.session_state.current_page + 1
            page_number = st.number_input(
                "Страница",
                min_value=1,
                max_value=max(1, st.session_state.total_pages),
                value=min(default_page, max(1, st.session_state.total_pages)),
                key="form_page",
            )

            parent_options = [None] + [e["id"] for e in st.session_state.elements if e["id"] != editing_id]
            default_parent_idx = 0
            if editing_elem and editing_elem.get("parent_id") in parent_options:
                default_parent_idx = parent_options.index(editing_elem["parent_id"])
            parent_id = st.selectbox(
                "Родитель",
                options=parent_options,
                index=default_parent_idx,
                format_func=lambda x: "— нет —" if x is None else x,
                key="form_parent",
            )

        with c2:
            default_content = editing_elem.get("content", "") if editing_elem else ""
            content = st.text_area("Содержимое", value=default_content, height=150, key="form_content")

        # Координаты bbox
        st.markdown("**Координаты bbox** (в пикселях при render_scale=2.0)")
        bc1, bc2, bc3, bc4 = st.columns(4)
        default_bbox = editing_elem.get("bbox") if editing_elem else None
        with bc1:
            bx0 = st.number_input("x0", value=float(default_bbox[0]) if default_bbox else 0.0, step=1.0, key="form_bx0")
        with bc2:
            by0 = st.number_input("y0", value=float(default_bbox[1]) if default_bbox else 0.0, step=1.0, key="form_by0")
        with bc3:
            bx1 = st.number_input("x1", value=float(default_bbox[2]) if default_bbox else 0.0, step=1.0, key="form_bx1")
        with bc4:
            by1 = st.number_input("y1", value=float(default_bbox[3]) if default_bbox else 0.0, step=1.0, key="form_by1")

        bbox = [bx0, by0, bx1, by1] if any([bx0, by0, bx1, by1]) else None

        # --- Дополнительные поля для таблиц ---
        metadata: Dict[str, Any] = {}
        if elem_type == "table":
            st.markdown("---")
            st.markdown("**Таблица: HTML + ячейки**")
            st.info("Вставьте HTML таблицы. Ячейки будут извлечены автоматически.")
            default_html = ""
            if editing_elem:
                ts = editing_elem.get("metadata", {}).get("table_structure", {})
                default_html = ts.get("html", editing_elem.get("content", ""))
            table_html = st.text_area("HTML таблицы", value=default_html, height=200, key="form_table_html")
            if table_html:
                cells = html_table_to_cells(table_html)
                metadata["table_structure"] = {"html": table_html, "cells": cells}
                if cells:
                    rows_count = max(c["row"] for c in cells) + 1
                    cols_count = max(c["col"] for c in cells) + 1
                    metadata["rows_count"] = rows_count
                    metadata["cols_count"] = cols_count
                    st.success(f"Извлечено ячеек: {len(cells)} ({rows_count} строк x {cols_count} столбцов)")
                    with st.expander("Просмотр ячеек"):
                        st.json(cells)
                # content для таблицы = HTML
                content = table_html

        # --- Дополнительные поля для изображений ---
        if elem_type == "image":
            st.markdown("---")
            st.markdown("**Изображение: base64**")

            # Можно загрузить файл
            img_upload = st.file_uploader("Загрузить изображение", type=["png", "jpg", "jpeg"], key="form_img_upload")
            if img_upload:
                img_bytes = img_upload.getvalue()
                ext = img_upload.name.rsplit(".", 1)[-1].lower()
                b64 = base64.b64encode(img_bytes).decode("utf-8")
                data_url = f"data:image/{ext};base64,{b64}"
                metadata["image_data"] = data_url
                metadata["image_format"] = ext
                # Получаем размеры
                pil_img = Image.open(io.BytesIO(img_bytes))
                metadata["image_width"] = pil_img.width
                metadata["image_height"] = pil_img.height
                st.image(pil_img, width=300)
                st.success(f"Изображение: {pil_img.width}x{pil_img.height} ({ext})")
            elif editing_elem and editing_elem.get("metadata", {}).get("image_data"):
                metadata["image_data"] = editing_elem["metadata"]["image_data"]
                metadata["image_format"] = editing_elem["metadata"].get("image_format", "png")
                metadata["image_width"] = editing_elem["metadata"].get("image_width")
                metadata["image_height"] = editing_elem["metadata"].get("image_height")

            # Или выбрать из извлечённых
            extracted = st.session_state.get("_extracted_images", [])
            if extracted:
                sel_img_idx = st.selectbox(
                    "Или из извлечённых (кнопка выше)",
                    options=["-- выбрать --"] + [f"Изображение {i+1}" for i in range(len(extracted))],
                    key="form_img_extracted",
                )
                if sel_img_idx != "-- выбрать --":
                    idx = int(sel_img_idx.split()[-1]) - 1
                    img_info = extracted[idx]
                    metadata["image_data"] = img_info["data"]
                    metadata["image_format"] = img_info["format"]
                    metadata["image_width"] = img_info["width"]
                    metadata["image_height"] = img_info["height"]

            content = ""  # Для изображений content всегда пустой

        # --- Дополнительные поля для формул ---
        if elem_type == "formula":
            st.markdown("---")
            st.markdown("**Формула**")
            default_latex = ""
            if editing_elem:
                default_latex = editing_elem.get("metadata", {}).get("latex", "")
            latex = st.text_input("LaTeX (опционально)", value=default_latex, key="form_latex")
            if latex:
                metadata["latex"] = latex
            ftype = st.radio("Тип формулы", ["inline", "display"], key="form_formula_type",
                             index=0 if not editing_elem else (0 if editing_elem.get("metadata", {}).get("formula_type") == "inline" else 1))
            metadata["formula_type"] = ftype

        # --- Дополнительные поля для списков ---
        if elem_type == "list_item":
            st.markdown("---")
            st.markdown("**Элемент списка**")
            list_type = st.radio("Тип списка", ["unordered", "ordered"], key="form_list_type",
                                 index=0 if not editing_elem else (0 if editing_elem.get("metadata", {}).get("list_type") == "unordered" else 1))
            list_level = st.number_input("Уровень вложенности", min_value=0, max_value=5,
                                         value=editing_elem.get("metadata", {}).get("list_level", 0) if editing_elem else 0,
                                         key="form_list_level")
            metadata["list_type"] = list_type
            metadata["list_level"] = list_level

        # --- Дополнительные поля для подписей ---
        if elem_type == "caption":
            st.markdown("---")
            ct = st.radio("Тип подписи", ["image", "table"], key="form_caption_type",
                          index=0 if not editing_elem else (0 if editing_elem.get("metadata", {}).get("caption_type") == "image" else 1))
            metadata["caption_type"] = ct
            ref_id = st.text_input("ID связанного элемента",
                                   value=editing_elem.get("metadata", {}).get("referenced_element_id", "") if editing_elem else "",
                                   key="form_caption_ref")
            if ref_id:
                metadata["referenced_element_id"] = ref_id

        # Объединяем metadata
        if editing_elem:
            merged = {**editing_elem.get("metadata", {}), **metadata}
        else:
            merged = metadata

        # Кнопки
        st.markdown("---")
        bc1, bc2, bc3 = st.columns(3)
        with bc1:
            if editing_elem:
                if st.button("💾 Сохранить изменения", type="primary", key="btn_save_edit"):
                    editing_elem["type"] = elem_type
                    editing_elem["content"] = content
                    editing_elem["page_number"] = page_number
                    editing_elem["parent_id"] = parent_id
                    editing_elem["bbox"] = bbox
                    editing_elem["metadata"] = merged
                    st.session_state.editing_id = None
                    st.success(f"Обновлён: {editing_elem['id']}")
                    st.rerun()
            else:
                if st.button("➕ Добавить", type="primary", key="btn_add"):
                    new_order = _next_order()
                    new_elem = {
                        "id": _next_id(),
                        "type": elem_type,
                        "content": content,
                        "parent_id": parent_id,
                        "order": new_order,
                        "page_number": page_number,
                        "bbox": bbox,
                        "metadata": merged,
                    }
                    st.session_state.elements.append(new_elem)
                    st.success(f"Добавлен: {new_elem['id']} (order={new_order})")
                    st.rerun()

        with bc2:
            if editing_elem and st.button("❌ Отменить редактирование", key="btn_cancel_edit"):
                st.session_state.editing_id = None
                st.rerun()

        with bc3:
            if editing_elem and st.button("🗑 Удалить элемент", key="btn_delete_editing"):
                st.session_state.elements = [e for e in st.session_state.elements if e["id"] != editing_id]
                # Пересчитываем order
                for i, e in enumerate(st.session_state.elements):
                    e["order"] = i
                st.session_state.editing_id = None
                st.success(f"Удалён: {editing_id}")
                st.rerun()


# ──────────────────────────────────────────────
# UI: Список элементов
# ──────────────────────────────────────────────
def elements_list():
    elements = st.session_state.elements
    if not elements:
        st.info("Пока нет элементов. Добавьте вручную или используйте авто-разметку.")
        return

    st.subheader(f"📋 Элементы ({len(elements)})")

    # Фильтры
    fc1, fc2 = st.columns(2)
    with fc1:
        types_present = sorted(set(e["type"] for e in elements))
        filter_type = st.selectbox("Фильтр по типу", ["Все"] + types_present, key="filter_type_list")
    with fc2:
        pages_present = sorted(set(e.get("page_number", 0) for e in elements))
        filter_page = st.selectbox("Фильтр по странице", ["Все"] + pages_present, key="filter_page_list")

    filtered = elements
    if filter_type != "Все":
        filtered = [e for e in filtered if e["type"] == filter_type]
    if filter_page != "Все":
        filtered = [e for e in filtered if e.get("page_number") == filter_page]

    # Показываем только текущую страницу по умолчанию или все
    show_current_only = st.checkbox(
        f"Только текущая страница ({st.session_state.current_page + 1})",
        value=True,
        key="show_current_page_only",
    )
    if show_current_only and filter_page == "Все":
        filtered = [e for e in filtered if e.get("page_number") == st.session_state.current_page + 1]

    filtered.sort(key=lambda e: e.get("order", 0))

    for elem in filtered:
        eid = elem["id"]
        etype = elem["type"]
        color = ELEMENT_COLORS.get(etype, "#000")
        content_preview = (elem.get("content") or "")[:80]
        if len(elem.get("content", "")) > 80:
            content_preview += "..."

        is_selected = eid == st.session_state.editing_id
        prefix = "✏️ " if is_selected else ""
        header = f'{prefix}[{etype}] {eid} | order={elem.get("order", "?")} | стр.{elem.get("page_number", "?")}'

        with st.expander(header, expanded=is_selected):
            ec1, ec2 = st.columns([2, 1])
            with ec1:
                st.markdown(f'<span style="color:{color};font-weight:bold">■</span> **{etype}** — {TYPE_LABELS_RU.get(etype, "")}', unsafe_allow_html=True)
                st.text(content_preview)
                if elem.get("parent_id"):
                    st.caption(f"Родитель: {elem['parent_id']}")
                if elem.get("bbox"):
                    st.caption(f"bbox: {elem['bbox']}")
                # Для таблиц — показываем preview
                if etype == "table" and elem.get("content"):
                    with st.expander("Превью таблицы"):
                        st.markdown(elem["content"], unsafe_allow_html=True)
            with ec2:
                if st.button("✏️ Редактировать", key=f"edit_{eid}"):
                    st.session_state.editing_id = eid
                    # Переходим на страницу элемента
                    pg = elem.get("page_number")
                    if pg:
                        st.session_state.current_page = pg - 1
                    st.rerun()
                if st.button("🗑 Удалить", key=f"del_{eid}"):
                    st.session_state.elements = [e for e in st.session_state.elements if e["id"] != eid]
                    for i, e in enumerate(st.session_state.elements):
                        e["order"] = i
                    if st.session_state.editing_id == eid:
                        st.session_state.editing_id = None
                    st.rerun()
                # Стрелки для перемещения
                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("⬆", key=f"up_{eid}", help="Переместить вверх"):
                        idx = next((i for i, e in enumerate(st.session_state.elements) if e["id"] == eid), None)
                        if idx is not None and idx > 0:
                            st.session_state.elements[idx], st.session_state.elements[idx - 1] = (
                                st.session_state.elements[idx - 1],
                                st.session_state.elements[idx],
                            )
                            for i, e in enumerate(st.session_state.elements):
                                e["order"] = i
                            st.rerun()
                with bc2:
                    if st.button("⬇", key=f"down_{eid}", help="Переместить вниз"):
                        idx = next((i for i, e in enumerate(st.session_state.elements) if e["id"] == eid), None)
                        if idx is not None and idx < len(st.session_state.elements) - 1:
                            st.session_state.elements[idx], st.session_state.elements[idx + 1] = (
                                st.session_state.elements[idx + 1],
                                st.session_state.elements[idx],
                            )
                            for i, e in enumerate(st.session_state.elements):
                                e["order"] = i
                            st.rerun()

    # Массовые действия
    st.markdown("---")
    mc1, mc2 = st.columns(2)
    with mc1:
        if st.button("🔄 Пересчитать order", key="btn_reorder"):
            for i, e in enumerate(st.session_state.elements):
                e["order"] = i
            st.success("Порядок пересчитан")
            st.rerun()
    with mc2:
        if st.button("🗑 Удалить все элементы", key="btn_clear_all"):
            st.session_state.elements = []
            st.session_state.editing_id = None
            st.rerun()


# ──────────────────────────────────────────────
# Главная функция
# ──────────────────────────────────────────────
def main():
    _init_state()

    st.title("🏷️ Инструмент разметки документов v2.0")
    st.caption("Annotation Schema v2.0 · Таблицы: HTML · Изображения: base64")

    sidebar()
    page_navigation()

    # Основной контент: два столбца
    col_left, col_right = st.columns([3, 2])

    with col_left:
        page_viewer()

    with col_right:
        element_form()

    st.divider()
    elements_list()


if __name__ == "__main__":
    main()

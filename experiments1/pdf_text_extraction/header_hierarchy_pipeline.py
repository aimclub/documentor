"""
Экспериментальный пайплайн детекции заголовков и построения иерархии.

Фокус: работать в experiments/pdf_text_extraction независимо от основного пайплайна.

Источник данных:
- напрямую PDF (через PyMuPDF) -> слова + метаданные
- или уже сохранённый JSON `words_with_metadata.json` (из extract_text_with_metadata.py)

Идея:
1) Собрать строки (line) из слов (page, block_no, line_no)
2) Отфильтровать шум: колонтитулы/номера страниц/arXiv-строки/подписи к рисункам/TOC
3) Детектировать кандидатов заголовков по скорингу:
   - нумерация (1 / 1.2 / I. / A.1 ...)
   - ключевые слова (Abstract/References/ВВЕДЕНИЕ/...)
   - форматирование (font_size, bold_ratio, caps_ratio)
   - вертикальные интервалы (gap до/после строки)
4) Нормализовать/склеить некоторые паттерны (например: "1" + "INTRODUCTION")
5) Присвоить уровни через HeaderLevelDetector и построить дерево.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import fitz  # PyMuPDF

from header_level_detector import HeaderLevelDetector, NumberingPattern


_EN_KEYWORDS = {
    "abstract": 1,
    "acknowledgement": 1,
    "acknowledgement(s)": 1,
    "acknowledgments": 1,
    "references": 1,
    "appendix": 1,
}

_RU_KEYWORDS = {
    "реферат": 1,
    "аннотация": 1,
    "содержание": 1,
    "введение": 1,
    "заключение": 1,
    "список литературы": 1,
    "список использованных источников": 1,
    "список источников": 1,
    "приложения": 1,
    "приложение": 1,
}


def _norm_text(s: str) -> str:
    s = s.replace("\u00ad", "")  # soft hyphen
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _letters_upper_ratio(s: str) -> float:
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return 0.0
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters)


def _safe_float(x: Any) -> Optional[float]:
    if isinstance(x, (int, float)):
        return float(x)
    return None


def _is_page_number_line(text: str) -> bool:
    t = _norm_text(text)
    # "1" or "2" alone is ambiguous (can be section number). We'll treat as page number
    # only if it is not followed/preceded by other header patterns, and will be further filtered
    # by position/repeatability later.
    return bool(re.fullmatch(r"\d{1,4}", t))


def _looks_like_arxiv_footer(text: str) -> bool:
    t = _norm_text(text)
    return ("arxiv:" in t.lower()) or ("preprint" in t.lower())


def _looks_like_dialogue_or_prompt(text: str) -> bool:
    t = _norm_text(text)
    if not t:
        return False
    low = t.lower()
    # диалоги в приложениях (Q/A) почти никогда не заголовки
    if re.match(r"^(user|assistant|system|developer)\s*:\s+", low):
        return True
    # маркеры "Input/Output" в примерах, но не как "Output distance measures" (там обычно 3+ слова)
    if re.match(r"^(input|output)\s*:\s+", low):
        return True
    return False


def _looks_like_table_cell_label(text: str) -> bool:
    """
    Короткие табличные/рисуночные метки: "Output SQL", "Original SQL", "Unit Tests", "+ Expl."
    """
    t = _norm_text(text)
    low = t.lower()
    if not t:
        return False
    if t.strip() in {"+", "+ Expl.", "+ Expl", "+ UT", "+UT"}:
        return True
    # часто в таблицах/фигурах
    if low in {"output", "input", "prediction", "original", "prompt", "unit tests", "unit test", "code explanation", "output sql", "original sql"}:
        return True
    if low.startswith("self-debugging with "):
        return True
    if low.startswith("prediction after "):
        return True
    # "Output SQL" / "Original SQL" / "Unit Tests" / "Code explanation"
    if len(t.split()) <= 3 and any(low.startswith(x) for x in ("output ", "original ", "input ", "unit ")):
        return True
    return False


def _looks_like_bibliography_entry(text: str) -> bool:
    """
    Эвристика для строк библиографии: много запятых/and/год/сборник.
    """
    t = _norm_text(text)
    low = t.lower()
    if not t:
        return False
    if re.search(r"\b(19|20)\d{2}\b", t):
        return True
    if "pmlr" in low or "proceedings" in low:
        return True
    if "," in t and len(t.split()) >= 6:
        return True
    if " and " in f" {low} " and len(t.split()) >= 6:
        return True
    return False

def _is_caption_like(text: str) -> bool:
    t = _norm_text(text)
    # EN
    if re.match(r"^(figure|fig\.?|table|tab\.?)\s*\d+", t, flags=re.IGNORECASE):
        return True
    # RU
    if re.match(r"^(рис\.?|рисунок|табл\.?|таблица)\s*\d+", t, flags=re.IGNORECASE):
        return True
    return False


def _is_dotleader_toc_line(text: str) -> bool:
    t = _norm_text(text)
    # TOC лидеры + номер страницы в конце
    if re.search(r"\.{5,}\s*\d+\s*$", t):
        return True
    # вариант с табуляцией/многими пробелами и номером страницы
    if re.search(r"\s{6,}\d+\s*$", t):
        return True
    return False


def _is_probably_toc_page(lines: List["Line"]) -> bool:
    # эвристика: много dotleader-строк на одной странице
    cnt = sum(1 for ln in lines if _is_dotleader_toc_line(ln.text))
    return cnt >= 6


def _looks_like_author_line(text: str) -> bool:
    """
    Типичные строки авторов в arXiv-стиле: "Xinyun Chen1", "Maxwell Lin2", ...
    """
    t = _norm_text(text)
    if len(t) > 40:
        return False
    # Используем классы unicode: [^\W\d_] == "буква" (word char без цифр и подчёркивания)
    if re.match(r"^[A-Z][^\W\d_]+(?:[-'][A-Z][^\W\d_]+)?\s+[A-Z][^\W\d_]+(?:[-'][A-Z][^\W\d_]+)?\d{1,2}$", t, flags=re.UNICODE):
        return True
    return False


def _digit_heavy_short(text: str) -> bool:
    t = _norm_text(text)
    if not t:
        return False
    # Вложенная нумерация "5.2.1" может быть заголовком, но значения типа "80.6" чаще метрики.
    if re.fullmatch(r"\d+(?:\.\d+){1,3}", t):
        try:
            first = int(t.split(".")[0])
            return first > 20
        except Exception:
            return True
    # чистые числа/десятичные — чаще таблицы/метрики, но маленькие целые (1..30) нужны для склейки "1"+"INTRODUCTION"
    if re.fullmatch(r"\d+(\.\d+)?", t):
        if "." not in t:
            try:
                n = int(t)
                if 1 <= n <= 30:
                    return False
            except Exception:
                pass
        return True
    digits = sum(1 for c in t if c.isdigit())
    letters = sum(1 for c in t if c.isalpha())
    if digits >= 4 and letters <= 2 and len(t.split()) <= 8:
        return True
    # таблицы вида "63.0 (n = 25)"
    if re.match(r"^\d+(\.\d+)?\s*\(.*\)\s*$", t):
        return True
    return False


@dataclass(frozen=True)
class Line:
    page: int
    block_no: int
    line_no: int
    text: str
    bbox: Tuple[float, float, float, float]  # x0,y0,x1,y1
    avg_font_size: float
    bold_ratio: float
    italic_ratio: float
    upper_ratio: float
    word_count: int
    words: Tuple[Dict[str, Any], ...]


class HeaderHierarchyPipeline:
    def __init__(
        self,
        *,
        max_header_words: int = 18,
        min_header_chars: int = 3,
        min_score: float = 2.6,
        repeat_text_min_pages_ratio: float = 0.25,
        repeat_y_band: float = 0.12,
    ):
        self.max_header_words = max_header_words
        self.min_header_chars = min_header_chars
        self.min_score = min_score
        self.repeat_text_min_pages_ratio = repeat_text_min_pages_ratio
        self.repeat_y_band = repeat_y_band

    # ---------- loading ----------
    def load_words_from_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        all_words: List[Dict[str, Any]] = []
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            # words format: (x0, y0, x1, y1, text, block_no, line_no, word_no)
            words_list = page.get_text("words") or []
            # dict for font info
            text_dict = page.get_text("dict") or {}
            font_info_by_block_line: Dict[Tuple[int, int], Dict[str, Any]] = {}
            for block_idx, block in enumerate(text_dict.get("blocks", [])):
                if "lines" not in block:
                    continue
                for line_idx, line in enumerate(block.get("lines", [])):
                    for span in line.get("spans", []):
                        key = (block_idx, line_idx)
                        if key not in font_info_by_block_line:
                            font_info_by_block_line[key] = {
                                "font": span.get("font", "unknown"),
                                "font_size": span.get("size", 0),
                                "flags": span.get("flags", 0),
                            }

            for wd in words_list:
                if len(wd) < 8:
                    continue
                x0, y0, x1, y1, text, block_no, line_no, word_no = wd[:8]
                word: Dict[str, Any] = {
                    "text": text or "",
                    "x0": float(x0),
                    "y0": float(y0),
                    "x1": float(x1),
                    "y1": float(y1),
                    "bbox": [float(x0), float(y0), float(x1), float(y1)],
                    "block_no": int(block_no),
                    "line_no": int(line_no),
                    "word_no": int(word_no),
                    "page": page_idx + 1,
                }
                fi = font_info_by_block_line.get((int(block_no), int(line_no)))
                if fi:
                    flags = int(fi.get("flags") or 0)
                    word["font"] = fi.get("font", "unknown")
                    word["font_size"] = float(fi.get("font_size") or 0)
                    word["flags"] = flags
                    word["is_bold"] = bool(flags & 16)
                    word["is_italic"] = bool(flags & 1)
                else:
                    word["font"] = "unknown"
                    word["font_size"] = 0.0
                    word["flags"] = 0
                    word["is_bold"] = False
                    word["is_italic"] = False
                all_words.append(word)
        doc.close()
        return {
            "pdf_file": pdf_path.name,
            "total_pages": total_pages,
            "total_words": len(all_words),
            "words": all_words,
        }

    def load_words_from_json(self, words_json_path: Path) -> Dict[str, Any]:
        with open(words_json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ---------- core transforms ----------
    def build_lines(self, words: List[Dict[str, Any]]) -> List[Line]:
        grouped: Dict[Tuple[int, int, int], List[Dict[str, Any]]] = {}
        for w in words:
            page = int(w.get("page") or 0)
            block_no = int(w.get("block_no") if w.get("block_no") is not None else -1)
            line_no = int(w.get("line_no") if w.get("line_no") is not None else -1)
            grouped.setdefault((page, block_no, line_no), []).append(w)

        out: List[Line] = []
        for (page, block_no, line_no), ws in grouped.items():
            ws_sorted = sorted(ws, key=lambda x: (int(x.get("word_no") or 0), float(x.get("x0") or 0)))
            text = _norm_text(" ".join(str(w.get("text") or "") for w in ws_sorted))
            if not text:
                continue

            x0 = min(float(w.get("x0") or 0) for w in ws_sorted)
            y0 = min(float(w.get("y0") or 0) for w in ws_sorted)
            x1 = max(float(w.get("x1") or 0) for w in ws_sorted)
            y1 = max(float(w.get("y1") or 0) for w in ws_sorted)

            sizes = [_safe_float(w.get("font_size")) for w in ws_sorted]
            sizes = [s for s in sizes if s and s > 0]
            avg_size = sum(sizes) / len(sizes) if sizes else 0.0

            bold_ratio = sum(1 for w in ws_sorted if w.get("is_bold")) / len(ws_sorted)
            italic_ratio = sum(1 for w in ws_sorted if w.get("is_italic")) / len(ws_sorted)
            upper_ratio = _letters_upper_ratio(text)
            wc = len(text.split())

            out.append(
                Line(
                    page=page,
                    block_no=block_no,
                    line_no=line_no,
                    text=text,
                    bbox=(x0, y0, x1, y1),
                    avg_font_size=avg_size,
                    bold_ratio=bold_ratio,
                    italic_ratio=italic_ratio,
                    upper_ratio=upper_ratio,
                    word_count=wc,
                    words=tuple(ws_sorted),
                )
            )
        return out

    def _is_prefix_only_line(self, text: str) -> bool:
        """
        Префикс без названия (часто номер/литера отдельно от заголовка):
          "1", "I", "E.2", "F.10", "5.2.1"
        """
        t = _norm_text(text)
        if re.fullmatch(r"\d{1,3}", t):
            try:
                n = int(t)
                return 1 <= n <= 20
            except Exception:
                return False
        if re.fullmatch(r"[IVX]{1,6}", t):
            return True
        if re.fullmatch(r"[A-Z]\.\d{1,2}", t):
            return True
        if re.fullmatch(r"[A-Z](?:\.\d{1,2}){2,}", t):
            return True
        if re.fullmatch(r"\d+(?:\.\d+){1,3}", t):
            # Отсекаем "30.8" и подобные метрики из таблиц: для нумерации секций числа обычно небольшие.
            parts = [int(x) for x in t.split(".") if x.isdigit()]
            if parts and parts[0] <= 20 and all(p <= 50 for p in parts):
                return True
        return False

    def _merge_prefixes_by_geometry(self, headers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Склейка префиксов по геометрии (а не по соседству в списке):
          - prefix-only "1" / "E.2" / "5.2.1" часто стоит в отдельном блоке слева,
            а название заголовка — отдельной строкой справа на той же высоте.
        """
        # разложим по страницам
        by_page: Dict[int, List[Dict[str, Any]]] = {}
        for h in headers:
            by_page.setdefault(int(h.get("page_num") or 0), []).append(h)

        out: List[Dict[str, Any]] = []
        for p, hs in by_page.items():
            hs_sorted = sorted(hs, key=lambda x: ((x.get("bbox") or [0, 0, 0, 0])[1], (x.get("bbox") or [0, 0, 0, 0])[0]))
            used_title_idx: set[int] = set()
            # сначала добавим все не-префиксы, а префиксы попробуем привязать
            for i, h in enumerate(hs_sorted):
                t = _norm_text(h.get("text", ""))
                if not self._is_prefix_only_line(t):
                    continue
                bbox = h.get("bbox") or [0, 0, 0, 0]
                x0, y0, x1, y1 = bbox
                # найдём лучшего кандидата-название: рядом по Y и справа по X
                best_j = None
                best_key = None
                for j, cand in enumerate(hs_sorted):
                    if j == i or j in used_title_idx:
                        continue
                    t2 = _norm_text(cand.get("text", ""))
                    if not t2 or self._is_prefix_only_line(t2):
                        continue
                    b2 = cand.get("bbox") or [0, 0, 0, 0]
                    cx0, cy0, cx1, cy1 = b2
                    # близко по Y (строка на той же высоте)
                    if abs(cy0 - y0) > 6.0:
                        continue
                    # заголовок должен быть справа (или почти справа)
                    if cx0 < (x1 - 2.0):
                        continue
                    # название должно выглядеть как заголовок
                    # (keyword / caps / reasons уже посчитаны скорингом)
                    if not (self._is_keyword_header(t2) or _letters_upper_ratio(t2) >= 0.65 or float(cand.get("score") or 0) >= self.min_score):
                        continue
                    key = (abs(cy0 - y0), cx0 - x1)
                    if best_key is None or key < best_key:
                        best_key = key
                        best_j = j
                if best_j is not None:
                    title = hs_sorted[best_j]
                    used_title_idx.add(best_j)
                    merged_text = f"{t} {_norm_text(title.get('text',''))}"
                    b2 = title.get("bbox") or [0, 0, 0, 0]
                    merged_bbox = [min(x0, b2[0]), min(y0, b2[1]), max(x1, b2[2]), max(y1, b2[3])]
                    merged = {
                        **title,
                        "text": merged_text,
                        "bbox": merged_bbox,
                        "reasons": list(set((h.get("reasons") or []) + (title.get("reasons") or []) + ["merged_prefix_geom"])),
                        "score": float(h.get("score") or 0) + float(title.get("score") or 0),
                    }
                    out.append(merged)
                # если не нашли пару — просто игнорируем префикс

            # добавим оставшиеся НЕ использованные title-строки (не-префиксы)
            for j, h in enumerate(hs_sorted):
                t = _norm_text(h.get("text", ""))
                if self._is_prefix_only_line(t):
                    continue
                if j in used_title_idx:
                    continue
                out.append(h)

        out.sort(key=lambda h: (h.get("page_num", 0), (h.get("bbox") or [0, 0, 0, 0])[1], (h.get("bbox") or [0, 0, 0, 0])[0]))
        return out

    def _extract_run_in_candidates(
        self,
        lines: List[Line],
        *,
        body_font_median: float,
        gaps_by_key: Dict[Tuple[int, int, int], Tuple[float, float]],
    ) -> List[Dict[str, Any]]:
        """
        Run-in заголовки: короткий "заголовочный" префикс в начале строки абзаца:
          "Execution-based code selection. Prior works ..."
        Извлекаем префикс до первой точки, если у него признаки заголовка (bold/size/titlecase).
        """
        out: List[Dict[str, Any]] = []
        for ln in lines:
            # если это уже отдельный заголовок — не трогаем
            if NumberingPattern.extract_numbering(ln.text) or self._is_keyword_header(ln.text):
                continue
            if ln.word_count < 6 or ln.word_count > 28:
                continue
            if re.match(r"^[a-zа-яё]", ln.text):
                continue

            prefix_words: List[Dict[str, Any]] = []
            rest_exists = False
            for idx, w in enumerate(ln.words):
                wt = str(w.get("text") or "")
                prefix_words.append(w)
                if wt.endswith(".") and len(wt) >= 2:
                    rest_exists = (idx + 1) < len(ln.words)
                    break
            if not rest_exists:
                continue
            if len(prefix_words) < 2 or len(prefix_words) > 9:
                continue

            prefix_text = _norm_text(" ".join(str(w.get("text") or "") for w in prefix_words)).rstrip(".").strip()
            if len(prefix_text) < 3:
                continue
            # отсеиваем формулы/цифры/условия
            if re.search(r"[=<>∈∀]", prefix_text) or re.search(r"\d", prefix_text):
                continue

            p_sizes = [w.get("font_size") for w in prefix_words if isinstance(w.get("font_size"), (int, float)) and (w.get("font_size") or 0) > 0]
            p_avg = sum(p_sizes) / len(p_sizes) if p_sizes else 0.0
            p_bold = sum(1 for w in prefix_words if w.get("is_bold")) / len(prefix_words)
            p_ur = _letters_upper_ratio(prefix_text)
            is_titlecase_like = bool(re.match(r"^[A-ZА-ЯЁ].+", prefix_text)) and p_ur < 0.65

            # run-in делаем строго: должен быть реально выделен (жирность) и отделён сверху (gap_before)
            prev_gap, _next_gap = gaps_by_key.get((ln.page, ln.block_no, ln.line_no), (0.0, 0.0))
            gap_norm = max(1.0, body_font_median)
            if not (p_bold >= 0.70 or (body_font_median and p_avg >= body_font_median * 1.12)):
                continue
            if (prev_gap / gap_norm) < 0.9:
                continue

            x0 = min(float(w.get("x0") or 0) for w in prefix_words)
            y0 = min(float(w.get("y0") or 0) for w in prefix_words)
            x1 = max(float(w.get("x1") or 0) for w in prefix_words)
            y1 = max(float(w.get("y1") or 0) for w in prefix_words)
            out.append(
                {
                    "page_num": ln.page,
                    "text": prefix_text,
                    "font_size": p_avg,
                    "bbox": [x0, y0, x1, y1],
                    "score": max(self.min_score, 2.8),
                    "reasons": ["run_in"],
                    "level_hint": None,
                }
            )
        return out

    def _extract_numbered_run_in_from_lines(
        self,
        lines: List[Line],
        *,
        body_font_median: float,
        gaps_by_key: Dict[Tuple[int, int, int], Tuple[float, float]],
    ) -> List[Dict[str, Any]]:
        """
        Специальный (низкошумный) run-in режим:
        если на странице есть строка-префикс "2.1" / "3.4" / "A.2" (только номер),
        то берём следующий текстовый line и извлекаем заголовок из префикса до первой точки:
          2.1 + "Few-shot prompting. Few-shot prompting instructs ..." -> "2.1 Few-shot prompting"
        """
        out: List[Dict[str, Any]] = []
        by_page: Dict[int, List[Line]] = {}
        for ln in lines:
            by_page.setdefault(ln.page, []).append(ln)

        for p, page_lines in by_page.items():
            page_sorted = sorted(page_lines, key=lambda x: (x.bbox[1], x.bbox[0]))
            # индекс по (block_no,line_no) не нужен; работаем по порядку чтения
            for i, ln in enumerate(page_sorted):
                t = _norm_text(ln.text)
                # хотим только "2.1" / "3.2" / "5.2.1" (без хвоста)
                # (буквенные E.1/F.2/... не обрабатываем этим методом — там часто точки в аббревиатурах и больше шума)
                if not re.fullmatch(r"\d+\.\d+|\d+\.\d+\.\d+", t):
                    continue
                if i + 1 >= len(page_sorted):
                    continue
                nxt = page_sorted[i + 1]
                nxt_text = _norm_text(nxt.text)
                if not nxt_text or re.match(r"^[a-zа-яё]", nxt_text):
                    continue
                # если строка next выглядит как ALL-CAPS заголовок, это не run-in предложение
                if _letters_upper_ratio(nxt_text) >= 0.75:
                    continue
                # берём заголовок до первой точки, если она есть рано
                m = re.match(r"^(.{3,90}?)\.\s+[A-ZА-ЯЁ]", nxt_text)
                if not m:
                    continue
                title = m.group(1).strip()
                if len(title.split()) < 2 or len(title.split()) > 10:
                    continue
                if _looks_like_dialogue_or_prompt(title) or _looks_like_table_cell_label(title):
                    continue
                # должно быть похоже на заголовок: хотя бы чуть выделено (gap или size/bold)
                prev_gap, _next_gap = gaps_by_key.get((nxt.page, nxt.block_no, nxt.line_no), (0.0, 0.0))
                gap_norm = max(1.0, body_font_median)
                if (prev_gap / gap_norm) < 0.6 and nxt.avg_font_size > 0 and nxt.avg_font_size <= body_font_median * 1.05 and nxt.bold_ratio < 0.35:
                    continue

                merged_text = f"{t} {title}"
                out.append(
                    {
                        "page_num": p,
                        "text": merged_text,
                        "font_size": float(nxt.avg_font_size or 0.0),
                        "bbox": list(nxt.bbox),
                        "score": max(self.min_score, 3.0),
                        "reasons": ["number_prefix_run_in"],
                    }
                )
        return out

    def _page_heights(self, lines: List[Line]) -> Dict[int, float]:
        heights: Dict[int, float] = {}
        for ln in lines:
            heights[ln.page] = max(heights.get(ln.page, 0.0), ln.bbox[3])
        return heights

    def _page_widths(self, lines: List[Line]) -> Dict[int, float]:
        widths: Dict[int, float] = {}
        for ln in lines:
            widths[ln.page] = max(widths.get(ln.page, 0.0), ln.bbox[2])
        return widths

    def _compute_body_font_median(self, words: List[Dict[str, Any]]) -> float:
        sizes = [_safe_float(w.get("font_size")) for w in words]
        sizes = [s for s in sizes if s and s > 0]
        if not sizes:
            return 12.0
        return float(statistics.median(sizes))

    # ---------- filtering ----------
    def _detect_repeating_texts(self, lines: List[Line], total_pages: int) -> set[str]:
        """
        Колонтитулы/водяные знаки: повторяются на значимой доле страниц.
        """
        from collections import Counter

        # ВАЖНО: не учитываем слишком короткие строки (например, номера страниц "1"),
        # иначе повторяемость будет вычищать реальные номера секций.
        norm = []
        for ln in lines:
            t = _norm_text(ln.text).lower()
            if len(t) < 6:
                continue
            if re.fullmatch(r"\d{1,4}", t):
                continue
            norm.append(t)
        cnt = Counter(norm)
        min_pages = max(3, int(total_pages * self.repeat_text_min_pages_ratio))
        return {t for t, c in cnt.items() if c >= min_pages}

    def _filter_noise(self, lines: List[Line], *, total_pages: int) -> List[Line]:
        page_heights = self._page_heights(lines)
        page_widths = self._page_widths(lines)
        repeating = self._detect_repeating_texts(lines, total_pages)

        # TOC pages detection (по dotleader)
        by_page: Dict[int, List[Line]] = {}
        for ln in lines:
            by_page.setdefault(ln.page, []).append(ln)
        toc_pages = {p for p, ls in by_page.items() if _is_probably_toc_page(ls)}

        out: List[Line] = []
        for ln in lines:
            t_norm = _norm_text(ln.text)
            t_low = t_norm.lower()
            page_h = page_heights.get(ln.page, 0.0) or 1.0
            y0 = ln.bbox[1]
            y1 = ln.bbox[3]
            y_center = (y0 + y1) / 2.0
            y_rel = y_center / page_h

            # выкидываем мусор по тексту
            # ВАЖНО: короткие строки типа "1", "I", "E.2" нужны для склейки "номер + заголовок"
            if len(t_norm) < self.min_header_chars and not self._is_prefix_only_line(t_norm):
                continue
            if _looks_like_arxiv_footer(t_norm):
                continue
            if _looks_like_dialogue_or_prompt(t_norm):
                continue
            if _looks_like_author_line(t_norm):
                continue
            # короткие строки-метки аффилиаций: "2 UC Berkeley", "1 Google DeepMind"
            if re.match(r"^\d{1,2}\s+[A-Z]{2,}(\s+[A-Z][A-Za-z]+){0,4}$", t_norm):
                continue
            # аффилиации/организации без капса: "1 Google DeepMind", "2 UC Berkeley", "1 Shanghai AI Laboratory"
            if re.match(r"^\d{1,2}\s+\w+", t_norm):
                low = t_norm.lower()
                if any(
                    k in low
                    for k in (
                        "university",
                        "laboratory",
                        "lab",
                        "institute",
                        "school",
                        "department",
                        "google",
                        "deepmind",
                        "berkeley",
                        "shanghai",
                        "xjtu",
                        "itmo",
                        "университет",
                        "институт",
                        "лаборат",
                        "федеральное",
                    )
                ):
                    # защита: не сносить реальные заголовки вида "1 Introduction"
                    if not re.match(r"^\d+\s+(introduction|conclusion|appendix|related|background)\b", low):
                        continue
            if _is_caption_like(t_norm):
                continue
            if _looks_like_table_cell_label(t_norm):
                continue
            # URL/email почти никогда не заголовки
            if re.search(r"https?://", t_norm, flags=re.IGNORECASE) or re.search(r"\bwww\.", t_norm, flags=re.IGNORECASE):
                continue
            if "@" in t_norm:
                continue
            # числовые/табличные строки
            if _digit_heavy_short(t_norm):
                continue
            # строки, начинающиеся с "002 ..." и подобные (часто подписи/табличные фрагменты)
            if re.match(r"^\d{2,}\s+", t_norm) and not re.match(r"^\d+(?:\.\d+)+\s+", t_norm):
                continue

            # TOC: страницы оглавления — не теряем заголовок "СОДЕРЖАНИЕ", но выкидываем entries
            if ln.page in toc_pages and _is_dotleader_toc_line(t_norm):
                continue

            # повторяющиеся строки (часто колонтитулы)
            if t_low in repeating:
                # оставляем исключения: реальные разделы типа "abstract" могут повторяться? почти нет.
                continue

            # положение: верх/низ страницы (колонтитулы/номера)
            if y_rel < self.repeat_y_band or y_rel > (1.0 - self.repeat_y_band):
                # если это одиночный номер страницы — почти наверняка колонтитул
                if _is_page_number_line(t_norm):
                    # но не удаляем номера секций в колонке у нижней границы:
                    # удаляем только если число стоит примерно по центру страницы.
                    w = page_widths.get(ln.page, 0.0) or 612.0
                    cx = (ln.bbox[0] + ln.bbox[2]) / 2.0
                    if abs(cx - (w / 2.0)) <= (w * 0.18):
                        continue
                # если короткая строка вверху/внизу и без нумерации/ключевых слов — тоже шум
                # НО: заголовки секций в 2-колоночных PDF часто начинаются у нижней границы страницы.
                # Поэтому капсовые короткие строки не выкидываем.
                if (
                    NumberingPattern.extract_numbering(t_norm) is None
                    and not self._is_keyword_header(t_norm)
                    and not self._is_prefix_only_line(t_norm)
                    and not (ln.upper_ratio >= 0.85 and ln.word_count <= 10)
                ):
                    continue

            out.append(ln)
        return out

    # ---------- scoring ----------
    def _is_keyword_header(self, text: str) -> bool:
        t = _norm_text(text).strip()
        if not t:
            return False
        low = t.lower()
        if low in _EN_KEYWORDS:
            return True
        if low in _RU_KEYWORDS:
            return True
        # иногда "ACKNOWLEDGEMENT" / "REFERENCES" в капсе с хвостами
        if low in {"acknowledgement", "acknowledgements", "references", "appendix", "abstract"}:
            return True
        return False

    def _line_gap_features(self, page_lines_sorted: List[Line]) -> Dict[Tuple[int, int, int], Tuple[float, float]]:
        """
        Для каждой линии на странице вычисляем gap до предыдущей и до следующей линии (в пикселях).
        """
        gaps: Dict[Tuple[int, int, int], Tuple[float, float]] = {}
        for i, ln in enumerate(page_lines_sorted):
            prev_gap = 0.0
            next_gap = 0.0
            if i > 0:
                prev_gap = max(0.0, ln.bbox[1] - page_lines_sorted[i - 1].bbox[3])
            if i < len(page_lines_sorted) - 1:
                next_gap = max(0.0, page_lines_sorted[i + 1].bbox[1] - ln.bbox[3])
            gaps[(ln.page, ln.block_no, ln.line_no)] = (prev_gap, next_gap)
        return gaps

    def _score_line(
        self,
        ln: Line,
        *,
        body_font_median: float,
        prev_gap: float,
        next_gap: float,
    ) -> Tuple[float, List[str], Optional[Tuple[str, str, int]]]:
        reasons: List[str] = []
        score = 0.0

        if ln.word_count > self.max_header_words:
            return 0.0, ["too_long"], None

        num_info = NumberingPattern.extract_numbering(ln.text)
        if num_info:
            numbering, content, depth = num_info
            # ВАЖНО: нумерация бывает не заголовком, а списком/сноской.
            #  - "(1) ..." или "1) ..." -> чаще список, даём низкий вес
            #  - "1 ..." с очень маленьким шрифтом -> часто маркер/сноска
            is_list_numbering = bool(re.match(r"^\(?\d+\)\s+", ln.text))
            if is_list_numbering:
                score += 1.2
                reasons.append(f"numbering_list:{numbering}")
            else:
                score += 3.5
                reasons.append(f"numbering:{numbering}")

            # поднимаем доверие для вложенности
            score += min(1.0, 0.3 * max(0, depth - 1))

            # анти-эвристики против ложной "нумерации"
            n_type = NumberingPattern.get_numbering_type(numbering)
            content_norm = _norm_text(content)
            # "0 ..." почти всегда не заголовок
            if n_type == "arabic" and depth == 1 and numbering == "0":
                score -= 3.2
                reasons.append("arabic_zero_not_header")
            # "1 since ..." — типичный маркер/сноска/абзацная строка
            if n_type == "arabic" and depth == 1 and re.match(r"^[a-zа-яё]", content_norm):
                score -= 2.2
                reasons.append("arabic_number_sentence_like")
            # "1. The ..." — часто элемент списка/пример, а не заголовок
            if n_type == "arabic" and depth == 1 and re.match(r"^(the|a|an)\b", content_norm.lower()):
                score -= 2.0
                reasons.append("arabic_list_sentence_like")
            # "O. Isac, ..." — это ссылка/список авторов, а не приложение "A. ..."
            if n_type in {"letter", "letter_lower"} and depth == 1:
                if "," in ln.text[:28] or re.search(r"\b[A-Z]\.\s*[A-Z][a-z]+,", ln.text):
                    score -= 3.6
                    reasons.append("reference_like_letter_dot")
        else:
            numbering = ""
            content = ln.text
            depth = 0

        if self._is_keyword_header(ln.text):
            score += 3.2
            reasons.append("keyword")

        # font_size относительно тела
        font_ratio = None
        if body_font_median > 0 and ln.avg_font_size > 0:
            ratio = ln.avg_font_size / body_font_median
            font_ratio = ratio
            if ratio >= 1.35:
                score += 2.0
                reasons.append(f"font_ratio:{ratio:.2f}")
            elif ratio >= 1.20:
                score += 1.2
                reasons.append(f"font_ratio:{ratio:.2f}")
            elif ratio >= 1.08:
                score += 0.5
                reasons.append(f"font_ratio:{ratio:.2f}")
            elif ratio <= 0.80:
                # заметно меньше тела — часто сноски/суперскрипты/номера
                score -= 2.4
                reasons.append(f"small_font:{ratio:.2f}")

        # bold / caps
        if ln.bold_ratio >= 0.6:
            score += 1.0
            reasons.append("bold")
        elif ln.bold_ratio >= 0.35:
            score += 0.5
            reasons.append("semi_bold")

        if ln.upper_ratio >= 0.85 and ln.word_count <= 12:
            score += 0.9
            reasons.append("caps")
        elif ln.upper_ratio >= 0.55 and ln.word_count <= 12:
            score += 0.45
            reasons.append("mostly_caps")

        # интервалы (gap): заголовок чаще отделён
        gap_norm = max(1.0, body_font_median)  # нормируем примерно на pt
        prev_r = prev_gap / gap_norm
        next_r = next_gap / gap_norm
        if prev_r >= 2.0:
            score += 1.2
            reasons.append("gap_before_big")
        elif prev_r >= 1.2:
            score += 0.6
            reasons.append("gap_before")

        if next_r >= 2.0:
            score += 0.8
            reasons.append("gap_after_big")
        elif next_r >= 0.9:
            score += 0.3
            reasons.append("gap_after")
        if prev_gap / gap_norm <= 0.55 and next_gap / gap_norm <= 0.55 and not (ln.upper_ratio >= 0.85 and ln.word_count <= 8):
            # типичный межстрочный интервал абзаца
            score -= 1.2
            reasons.append("paragraph_like_gaps")

        # Важная эвристика для arXiv: если шрифт не проставился (font_size=0),
        # то ALL-CAPS строка должна считаться заголовком даже когда gap маленький.
        if ln.avg_font_size <= 0.0 and ln.upper_ratio >= 0.85 and ln.word_count <= 8:
            # анти-сигналы формул/шумных строк
            if not re.search(r"[=<>∈∀]", ln.text) and not re.search(r"\d", ln.text):
                score += 3.0
                reasons.append("caps_short_no_font")

        # анти-сигналы: TOC лидеры / явные метаданные
        if _is_dotleader_toc_line(ln.text):
            score -= 3.0
            reasons.append("toc_dotleader")

        if re.search(r"https?://", ln.text, flags=re.IGNORECASE) or re.search(r"\bwww\.", ln.text, flags=re.IGNORECASE):
            score -= 0.8
            reasons.append("url")

        if re.search(r"@", ln.text):
            score -= 0.6
            reasons.append("email")

        # одиночная цифра: оставляем как кандидат только если вокруг сильные сигналы (склейка)
        if _is_page_number_line(ln.text):
            score -= 2.0
            reasons.append("single_number")

        # Доп. защита от "псевдо-заголовков" с нумерацией и длинным текстом:
        # если это похоже на обычное предложение (много строчных) и нет других сигналов — штрафуем.
        if num_info and ln.upper_ratio < 0.25 and ln.word_count >= 10:
            score -= 1.4
            reasons.append("sentence_like_numbering")

        # Для ненумерованных строк добавляем анти-эвристики против абзацев:
        if not num_info and not self._is_keyword_header(ln.text):
            # начало со строчной буквы — крайне редко заголовок
            if re.match(r"^[a-zа-яё]", ln.text):
                score -= 1.4
                reasons.append("starts_lower")
            # длинная строка без форматных признаков чаще абзац
            if ln.word_count >= 14 and (font_ratio is None or font_ratio < 1.2) and ln.bold_ratio < 0.35 and ln.upper_ratio < 0.35:
                score -= 1.2
                reasons.append("long_plain_line")
            # пунктуация абзаца
            if ln.word_count >= 8 and re.search(r"[,:;]$", ln.text):
                score -= 0.6
                reasons.append("ends_with_punct")

        return score, reasons, num_info

    # ---------- candidate extraction ----------
    def detect_headers(self, words_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        words = words_data.get("words") or []
        total_pages = int(words_data.get("total_pages") or 0) or max((w.get("page") or 0) for w in words) if words else 0
        body_med = self._compute_body_font_median(words)

        lines = self.build_lines(words)
        lines = self._filter_noise(lines, total_pages=total_pages)

        # считаем gap-ы внутри страницы
        by_page: Dict[int, List[Line]] = {}
        for ln in lines:
            by_page.setdefault(ln.page, []).append(ln)

        gaps_by_key: Dict[Tuple[int, int, int], Tuple[float, float]] = {}
        for p, ls in by_page.items():
            ls_sorted = sorted(ls, key=lambda x: x.bbox[1])
            gaps_by_key.update(self._line_gap_features(ls_sorted))

        # первичный проход кандидатов
        candidates: List[Dict[str, Any]] = []
        for ln in lines:
            prev_gap, next_gap = gaps_by_key.get((ln.page, ln.block_no, ln.line_no), (0.0, 0.0))
            score, reasons, num_info = self._score_line(ln, body_font_median=body_med, prev_gap=prev_gap, next_gap=next_gap)
            # ВАЖНО: не пропускаем строки "только по факту нумерации" — иначе влезают списки/сноски.
            # Нумерация влияет на score, но если score не добрал порог — значит не заголовок.
            # Даем префиксным строкам ("1", "E.2") шанс на склейку, даже если score маленький.
            # При этом одиночные префиксы потом выкинем, если не склеились.
            is_prefix_only = self._is_prefix_only_line(ln.text)
            # быстрый жёсткий фильтр мусора прямо на уровне кандидатов
            if _looks_like_dialogue_or_prompt(ln.text) or _looks_like_table_cell_label(ln.text):
                continue
            # общий фильтр библиографии (доп. страховка)
            if _looks_like_bibliography_entry(ln.text) and not self._is_keyword_header(ln.text):
                # позволим только ALL-CAPS заголовки приложений
                if not (_letters_upper_ratio(ln.text) >= 0.85 and not re.search(r"\d", ln.text)):
                    continue
            # Если у строки нет font_size и нет явных визуальных сигналов (caps/bold/нумерации/keyword),
            # то это почти наверняка обычная строка текста -> не даём ей пройти даже при случайном score.
            if (
                ln.avg_font_size <= 0.0
                and ln.bold_ratio < 0.55
                and ln.upper_ratio < 0.55
                and not num_info
                and not self._is_keyword_header(ln.text)
                and not is_prefix_only
            ):
                continue
            # Для строк без нумерации/keyword дополнительно требуем явные визуальные признаки,
            # иначе абзацы (например, благодарности/библиография) начинают пролезать.
            if not num_info and not self._is_keyword_header(ln.text) and not is_prefix_only:
                if ln.upper_ratio < 0.60 and ln.bold_ratio < 0.60:
                    # если font_size известен и близок к телу — это скорее абзац
                    if ln.avg_font_size > 0 and body_med > 0 and ln.avg_font_size <= body_med * 1.15:
                        continue
                # одно-двухсловные "метки" без нумерации почти всегда мусор (таблицы/подписи),
                # исключение: keyword / капс / явный большой шрифт
                if ln.word_count <= 2 and ln.upper_ratio < 0.85 and (ln.avg_font_size <= 0 or ln.avg_font_size <= body_med * 1.25):
                    continue
                # строки, заканчивающиеся точкой, почти всегда абзацы/подписи, а не заголовки
                if ln.text.strip().endswith("."):
                    continue
            if score < self.min_score and not self._is_keyword_header(ln.text) and not is_prefix_only:
                continue

            candidates.append(
                {
                    "page_num": ln.page,
                    "text": ln.text,
                    "font_size": ln.avg_font_size,
                    "bbox": list(ln.bbox),
                    "score": score,
                    "reasons": reasons + (["prefix_only"] if is_prefix_only else []),
                }
            )

        # ВАЖНО: дальше merge/filter опираются на порядок в документе, поэтому сортируем заранее.
        candidates.sort(key=lambda h: (h.get("page_num", 0), (h.get("bbox") or [0, 0, 0, 0])[1], (h.get("bbox") or [0, 0, 0, 0])[0]))

        # склейка: номер/префикс в отдельном блоке слева + название справа на той же высоте
        candidates = self._merge_prefixes_by_geometry(candidates)

        # Восстановление 2.1/3.2/... через связку "номер-строка + следующий run-in"
        candidates.extend(self._extract_numbered_run_in_from_lines(lines, body_font_median=body_med, gaps_by_key=gaps_by_key))

        # фильтр библиографии: после REFERENCES обычно идут строки-элементы списка, их убираем
        candidates.sort(key=lambda h: (h.get("page_num", 0), (h.get("bbox") or [0, 0, 0, 0])[1], (h.get("bbox") or [0, 0, 0, 0])[0]))
        candidates = self._filter_bibliography_tail(candidates)
        candidates = self._filter_acknowledgement_paragraphs(candidates)

        # сортировка по документу
        candidates.sort(key=lambda h: (h.get("page_num", 0), (h.get("bbox") or [0, 0, 0, 0])[1]))
        return candidates

    def _filter_bibliography_tail(self, headers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        После заголовка REFERENCES/СПИСОК... часто идут строки библиографии (авторы/годы/doi),
        которые не являются заголовками. Убираем их, пока не встретили явный следующий раздел
        (например, приложение A/B/... в капсе).
        """
        out: List[Dict[str, Any]] = []
        in_refs = False
        for h in headers:
            t = _norm_text(h.get("text", ""))
            low = t.lower()
            if low in {"references", "список литературы", "список использованных источников", "список источников"}:
                in_refs = True
                out.append(h)
                continue
            if not in_refs:
                out.append(h)
                continue

            # В режиме REFERENCES держим только "реальные" заголовки и выбрасываем элементы списка литературы.
            # оставляем только явные заголовки/разделители
            if self._is_keyword_header(t):
                out.append(h)
                continue
            # крупные капсовые названия разделов/приложений
            if _letters_upper_ratio(t) >= 0.85 and len(t.split()) <= 18 and not re.search(r"\d", t):
                in_refs = False
                out.append(h)
                continue
            # буквенно-точечные "A.1 ..." (приложения) — тоже считаем заголовком и выходим из refs
            if re.match(r"^[A-Z]\.\d+", t):
                in_refs = False
                out.append(h)
                continue
            # всё остальное в REFERENCES — мусор
            continue

        return out

    def _filter_acknowledgement_paragraphs(self, headers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        После ACKNOWLEDGEMENT/Благодарности часто идёт обычный абзац. Убираем его, пока не начался следующий раздел.
        """
        out: List[Dict[str, Any]] = []
        in_ack = False
        for h in headers:
            t = _norm_text(h.get("text", ""))
            low = t.lower()
            if low in {"acknowledgement", "acknowledgements", "благодарности"}:
                in_ack = True
                out.append(h)
                continue
            if not in_ack:
                out.append(h)
                continue
            # следующий крупный раздел — выходим
            if self._is_keyword_header(t) or (t.isupper() and len(t.split()) <= 10) or re.match(r"^[A-Z]\s+", t):
                in_ack = False
                out.append(h)
                continue
            # абзацы благодарностей выкидываем
            if NumberingPattern.extract_numbering(t) is None and _letters_upper_ratio(t) < 0.55:
                continue
            out.append(h)
        return out

    # NOTE: _merge_number_line_headers был заменён на _merge_prefixes_by_geometry (устойчивее к разным блокам)

    # ---------- hierarchy ----------
    def _postprocess_levels(self, headers_sorted: List[Dict[str, Any]]) -> None:
        """
        Корректировки уровней на основе контекста:
        - если в документе есть много roman H1, то letter A/B/... трактуем как H2
        - если встретили Appendix/ПРИЛОЖЕНИЯ как H1, то letter внутри него сдвигаем на +1
        """
        roman_cnt = sum(1 for h in headers_sorted if (h.get("numbering_type") == "roman" and h.get("numbering_depth") == 1))
        roman_is_top = roman_cnt >= 3

        in_appendix = False
        for h in headers_sorted:
            txt = _norm_text(h.get("text", ""))
            low = txt.lower()
            lvl = int(h.get("level") or 1)

            if low in {"appendix", "приложения", "приложение"}:
                in_appendix = True
                h["level"] = 1
                continue

            ntype = h.get("numbering_type")
            depth = int(h.get("numbering_depth") or 0)
            if ntype == "letter":
                if in_appendix:
                    h["level"] = 1 + max(1, depth)
                elif roman_is_top:
                    h["level"] = 1 + max(1, depth)

            # keywords всегда H1
            if self._is_keyword_header(txt):
                h["level"] = 1

        # запрет прыжков >1
        prev = None
        for h in headers_sorted:
            cur = int(h.get("level") or 1)
            if prev is not None and cur > prev + 1:
                h["level"] = prev + 1
                cur = h["level"]
            prev = cur

    def build_hierarchy(self, headers: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[int, List[str]]]:
        detector = HeaderLevelDetector()
        headers_with_levels = detector.detect_levels(headers)
        # сортируем и делаем контекстные корректировки уровней
        headers_sorted = sorted(headers_with_levels, key=lambda h: (h.get("page_num", 0), (h.get("bbox") or [0, 0, 0, 0])[1]))
        self._postprocess_levels(headers_sorted)

        # строим дерево (stack)
        root: Dict[str, Any] = {"level": 0, "children": []}
        stack: List[Dict[str, Any]] = [root]
        for h in headers_sorted:
            lvl = int(h.get("level") or 1)
            node = {"header": h, "level": lvl, "children": []}
            while len(stack) > 1 and stack[-1]["level"] >= lvl:
                stack.pop()
            stack[-1]["children"].append(node)
            stack.append(node)

        by_level: Dict[int, List[str]] = {}
        for h in headers_sorted:
            by_level.setdefault(int(h.get("level") or 1), []).append(_norm_text(h.get("text", "")))

        return headers_sorted, root, by_level

    # ---------- end-to-end ----------
    def run_from_words_json(self, words_json_path: Path) -> Dict[str, Any]:
        data = self.load_words_from_json(words_json_path)
        headers = self.detect_headers(data)
        headers_with_levels, tree, by_level = self.build_hierarchy(headers)
        return {"headers": headers_with_levels, "hierarchy": tree, "headers_by_level": by_level}

    def run_from_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        data = self.load_words_from_pdf(pdf_path)
        headers = self.detect_headers(data)
        headers_with_levels, tree, by_level = self.build_hierarchy(headers)
        return {"headers": headers_with_levels, "hierarchy": tree, "headers_by_level": by_level}


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def main() -> None:
    parser = argparse.ArgumentParser(description="Экспериментальный пайплайн: заголовки + иерархия")
    parser.add_argument("--pdf", type=str, default=None, help="Путь к PDF (если нет --words-json)")
    parser.add_argument("--words-json", type=str, default=None, help="Путь к words_with_metadata.json")
    parser.add_argument(
        "--out-dir",
        type=str,
        default=str(Path(__file__).parent / "results" / "header_hierarchy_pipeline"),
        help="Куда сохранять результаты",
    )
    parser.add_argument("--min-score", type=float, default=2.6)
    args = parser.parse_args()

    pipe = HeaderHierarchyPipeline(min_score=float(args.min_score))

    if not args.pdf and not args.words_json:
        raise SystemExit("Нужно указать --pdf или --words-json")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.words_json:
        src = Path(args.words_json)
        result = pipe.run_from_words_json(src)
        stem = src.parent.name
    else:
        src = Path(args.pdf)
        result = pipe.run_from_pdf(src)
        stem = src.stem

    doc_out = out_dir / stem
    doc_out.mkdir(parents=True, exist_ok=True)

    with open(doc_out / "headers_with_levels.json", "w", encoding="utf-8") as f:
        json.dump(result["headers"], f, ensure_ascii=False, indent=2, default=_json_default)
    with open(doc_out / "hierarchy.json", "w", encoding="utf-8") as f:
        json.dump(result["hierarchy"], f, ensure_ascii=False, indent=2, default=_json_default)
    with open(doc_out / "headers_by_level.json", "w", encoding="utf-8") as f:
        json.dump(result["headers_by_level"], f, ensure_ascii=False, indent=2, default=_json_default)

    print(f"OK: сохранено в {doc_out}")
    print(f"  headers: {len(result['headers'])}")


if __name__ == "__main__":
    main()


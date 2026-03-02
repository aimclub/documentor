"""
Скрипт для детального анализа оглавления в Diplom2024.docx
"""
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NAMESPACES = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}

def get_paragraph_text(p: ET.Element) -> str:
    """Извлекает весь текст из параграфа."""
    texts = []
    for text_elem in p.findall('.//w:t', NAMESPACES):
        if text_elem.text:
            texts.append(text_elem.text)
    return ''.join(texts).strip()

def get_paragraph_style(p: ET.Element) -> str:
    """Получает стиль параграфа."""
    p_pr = p.find('w:pPr', NAMESPACES)
    if p_pr is not None:
        p_style = p_pr.find('w:pStyle', NAMESPACES)
        if p_style is not None:
            return p_style.get(f'{{{NAMESPACES["w"]}}}val') or p_style.get('val')
    return None

def analyze_docx(docx_path: Path):
    """Детальный анализ DOCX файла для поиска оглавления."""
    print(f"\n{'='*80}")
    print(f"Анализ файла: {docx_path.name}")
    print(f"{'='*80}\n")
    
    with zipfile.ZipFile(docx_path, 'r') as zip_file:
        doc_xml = zip_file.read('word/document.xml')
        root = ET.fromstring(doc_xml)
        
        body = root.find('w:body', NAMESPACES)
        if body is None:
            print("Тело документа не найдено!")
            return
        
        # 1. Ищем заголовок "Содержание" или "Оглавление"
        print("1. Поиск заголовка оглавления:")
        toc_header_found = False
        toc_header_idx = -1
        
        for i, para in enumerate(body.findall('w:p', NAMESPACES)):
            text = get_paragraph_text(para)
            text_lower = text.lower().strip()
            if text_lower in ['содержание', 'оглавление', 'contents', 'table of contents']:
                print(f"   [OK] Найден заголовок на позиции {i}: '{text}'")
                toc_header_found = True
                toc_header_idx = i
                break
        
        if not toc_header_found:
            print("   [NOT FOUND] Заголовок оглавления не найден")
        
        # 2. Ищем TOC поля
        print("\n2. Поиск TOC полей (w:fldChar, w:instrText):")
        fld_chars = root.findall('.//w:fldChar', NAMESPACES)
        instr_texts = root.findall('.//w:instrText', NAMESPACES)
        print(f"   Найдено w:fldChar: {len(fld_chars)}")
        print(f"   Найдено w:instrText: {len(instr_texts)}")
        
        for instr in instr_texts:
            if instr.text and 'TOC' in instr.text.upper():
                print(f"   [OK] Найдено TOC поле: '{instr.text[:100]}'")
        
        # 3. Ищем PAGEREF ссылки
        print("\n3. Поиск PAGEREF ссылок:")
        pageref_count = 0
        for instr in instr_texts:
            if instr.text and 'PAGEREF' in instr.text.upper():
                pageref_count += 1
                bookmark_match = __import__('re').search(r'PAGEREF\s+(_Toc\d+)', instr.text, __import__('re').IGNORECASE)
                if bookmark_match:
                    print(f"   [OK] PAGEREF {pageref_count}: {bookmark_match.group(1)}")
        if pageref_count == 0:
            print("   [NOT FOUND] PAGEREF ссылки не найдены")
        
        # 4. Ищем стили TOC
        print("\n4. Поиск параграфов со стилями TOC:")
        toc_styles = []
        for para in body.findall('w:p', NAMESPACES):
            style = get_paragraph_style(para)
            if style and style.upper().startswith('TOC'):
                text = get_paragraph_text(para)
                toc_styles.append((style, text))
                print(f"   [OK] {style}: '{text[:80]}'")
        if not toc_styles:
            print("   [NOT FOUND] Стили TOC не найдены")
        
        # 5. Ищем гиперссылки в TOC
        print("\n5. Поиск гиперссылок (w:hyperlink) в документе:")
        hyperlinks = root.findall('.//w:hyperlink', NAMESPACES)
        print(f"   Найдено гиперссылок: {len(hyperlinks)}")
        toc_hyperlinks = []
        for i, hlink in enumerate(hyperlinks[:30]):  # Первые 30
            hlink_text = get_paragraph_text(hlink)
            r_id = hlink.get(f'{{{NAMESPACES["r"]}}}id') or hlink.get('id')
            if hlink_text:
                toc_hyperlinks.append((hlink_text, r_id))
                print(f"   [{i+1}] Text: '{hlink_text[:80]}', rId: {r_id}")
        
        # 6. Анализируем содержимое TOC поля более детально
        print("\n6. Детальный анализ содержимого TOC поля:")
        if toc_header_idx >= 0:
            # Ищем параграфы между fldChar begin и fldChar end
            in_toc_field = False
            toc_content_paras = []
            for para in body.findall('w:p', NAMESPACES):
                # Проверяем, есть ли fldChar в параграфе
                fld_chars_in_para = para.findall('.//w:fldChar', NAMESPACES)
                for fld_char in fld_chars_in_para:
                    fld_type = fld_char.get(f'{{{NAMESPACES["w"]}}}fldCharType') or fld_char.get('fldCharType')
                    if fld_type == 'begin':
                        in_toc_field = True
                    elif fld_type == 'end':
                        in_toc_field = False
                        break
                
                if in_toc_field:
                    text = get_paragraph_text(para)
                    if text and text.strip():
                        toc_content_paras.append(text)
                        print(f"   TOC content: '{text[:100]}'")
        
        # 7. Анализируем параграфы после заголовка оглавления
        if toc_header_idx >= 0:
            print(f"\n7. Анализ параграфов после заголовка (первые 30):")
            paras_after = list(body.findall('w:p', NAMESPACES))[toc_header_idx + 1:toc_header_idx + 31]
            for i, para in enumerate(paras_after):
                text = get_paragraph_text(para)
                style = get_paragraph_style(para)
                # Проверяем наличие гиперссылок
                has_hyperlink = para.find('.//w:hyperlink', NAMESPACES) is not None
                if text:
                    # Проверяем, есть ли номер страницы в конце
                    has_page_num = bool(__import__('re').search(r'\d+\s*$', text))
                    has_separators = bool(__import__('re').search(r'[.\-]{3,}', text))
                    print(f"   [{i+1}] Style: {style or 'None'}, Page: {has_page_num}, Sep: {has_separators}, Hyperlink: {has_hyperlink}")
                    print(f"       Text: '{text[:100]}'")
        
        # 8. Ищем закладки (bookmarks)
        print("\n8. Поиск закладок (bookmarks):")
        bookmarks = root.findall('.//w:bookmarkStart', NAMESPACES)
        print(f"   Найдено закладок: {len(bookmarks)}")
        toc_bookmarks = []
        all_bookmarks = []
        for bm in bookmarks:
            bm_name = bm.get(f'{{{NAMESPACES["w"]}}}name') or bm.get('name')
            if bm_name:
                all_bookmarks.append(bm_name)
                if bm_name.startswith('_Toc'):
                    toc_bookmarks.append(bm_name)
        
        print(f"   Всего закладок _Toc: {len(toc_bookmarks)}")
        for i, bm_name in enumerate(toc_bookmarks[:20]):  # Первые 20
            print(f"   [OK] {bm_name}")
        if len(toc_bookmarks) > 20:
            print(f"   ... и ещё {len(toc_bookmarks) - 20} закладок")
        
        # Показываем все закладки для анализа
        print(f"\n   Все закладки (первые 30):")
        for i, bm_name in enumerate(all_bookmarks[:30]):
            print(f"   [{i+1}] {bm_name}")

if __name__ == '__main__':
    script_dir = Path(__file__).parent
    test_folder = script_dir / "test_folder"
    
    docx_path = test_folder / "Diplom2024.docx"
    if docx_path.exists():
        analyze_docx(docx_path)
    else:
        print(f"Файл не найден: {docx_path}")

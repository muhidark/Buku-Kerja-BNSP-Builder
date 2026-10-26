"""
SKKNI Extractor - Generator DOCX (Fase 3A)

Mengubah satu unit kompetensi (JSON hasil Fase 2C) menjadi dokumen Word:
1. KODE UNIT / JUDUL UNIT / DESKRIPSI UNIT
2. Tabel ELEMEN KOMPETENSI - KRITERIA UNJUK KERJA
3. BATASAN VARIABEL
4. PANDUAN PENILAIAN

Numbering memakai Word Multilevel Numbering asli (abstractNum + num di OOXML),
bukan angka yang ditempel sebagai teks. Nomor KUK ditulis eksplisit dari JSON.
"""

import copy
import json
from pathlib import Path
from typing import Optional

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, Twips


# --------------------------------------------------------------------------
# Konstanta format (acuan: contoh format bulet dan numbering.docx)
# --------------------------------------------------------------------------

FONT_NAME = 'Bookman Old Style'
FONT_SIZE_PT = 11
SPACING_AFTER_PT = 6          # w:spacing after=120
LINE_SPACING = 1.15           # w:spacing line=276 lineRule=auto
JUSTIFY = True

PAGE_W_TWIPS = 12189          # F4/folio
PAGE_H_TWIPS = 18709
MARGIN_TOP = 1440             # 2,54 cm
MARGIN_RIGHT = 1440           # 2,54 cm
MARGIN_BOTTOM = 2880          # 5,08 cm
MARGIN_LEFT = 1701            # 3,00 cm

TABLE_WIDTH_TWIPS = 9048      # 12189 - 1701 - 1440
COL_WIDTH_TWIPS = 4524

# Target indentasi (twips): level -> left indent; hanging tetap 0,75 cm
LEVEL_INDENT_TWIPS = {1: 425, 2: 845, 3: 1264}   # 0,75 / 1,49 / 2,23 cm
HANGING_TWIPS = 425                              # 0,75 cm (minimum)
KUK_INDENT_TWIPS = 425

# Jarak minimum antara nomor dan teks (0,25 cm) supaya tidak menempel.
HANGING_GAP_TWIPS = 142
# Perkiraan lebar karakter Bookman Old Style 11 pt (twips), sengaja sedikit
# dilebihkan agar nomor terpanjang pun tidak melewati tab stop.
DIGIT_TW = 135
DOT_TW = 67

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


# --------------------------------------------------------------------------
# Utilitas OOXML
# --------------------------------------------------------------------------

def _el(tag: str, **attrs) -> OxmlElement:
    e = OxmlElement(tag)
    for k, v in attrs.items():
        e.set(qn(k), str(v))
    return e


def _set_ind(pPr, left_tw: int, hanging_tw: int = 0):
    """Set w:ind teladan twips (menggantikan nilai lama)."""
    for old in pPr.findall(qn('w:ind')):
        pPr.remove(old)
    # Tanpa atribut leftChars/firstLineChars: nilai char-unit dapat membuat
    # renderer (LibreOffice) mengabaikan nilai twips dan menaruh teks di margin.
    attrs = {'w:left': left_tw}
    if hanging_tw:
        attrs.update({'w:hanging': hanging_tw})
    ind = _el('w:ind', **attrs)
    # w:ind harus setelah w:spacing, sebelum w:jc
    pPr.insert_element_before(ind, 'w:contextualSpacing', 'w:mirrorIndents',
                              'w:suppressOverlap', 'w:jc', 'w:textDirection',
                              'w:textAlignment', 'w:textboxTightWrap',
                              'w:outlineLvl', 'w:divId', 'w:cnfStyle', 'w:rPr',
                              'w:sectPr', 'w:pPrChange')


def _set_tabs(pPr, positions: list[int]):
    for old in pPr.findall(qn('w:tabs')):
        pPr.remove(old)
    tabs = _el('w:tabs')
    for pos in positions:
        tabs.append(_el('w:tab', **{'w:val': 'left', 'w:pos': pos}))
    pPr.insert_element_before(tabs, 'w:suppressAutoHyphens', 'w:kinsoku',
                              'w:wordWrap', 'w:overflowPunct', 'w:topLinePunct',
                              'w:autoSpaceDE', 'w:autoSpaceDN', 'w:bidi',
                              'w:adjustRightInd', 'w:snapToGrid', 'w:spacing',
                              'w:ind', 'w:contextualSpacing', 'w:mirrorIndents',
                              'w:suppressOverlap', 'w:jc', 'w:textDirection',
                              'w:textAlignment', 'w:textboxTightWrap',
                              'w:outlineLvl', 'w:divId', 'w:cnfStyle', 'w:rPr',
                              'w:sectPr', 'w:pPrChange')


def _set_numpr(paragraph, num_id: int, ilvl: int):
    """Pasang w:numPr (ilvl 0-based) pada paragraf."""
    pPr = paragraph._p.get_or_add_pPr()
    for old in pPr.findall(qn('w:numPr')):
        pPr.remove(old)
    numPr = _el('w:numPr')
    numPr.append(_el('w:ilvl', **{'w:val': ilvl}))
    numPr.append(_el('w:numId', **{'w:val': num_id}))
    pPr.insert_element_before(numPr, 'w:suppressLineNumbers', 'w:pBdr', 'w:shd',
                              'w:tabs', 'w:suppressAutoHyphens', 'w:kinsoku',
                              'w:wordWrap', 'w:overflowPunct', 'w:topLinePunct',
                              'w:autoSpaceDE', 'w:autoSpaceDN', 'w:bidi',
                              'w:adjustRightInd', 'w:snapToGrid', 'w:spacing',
                              'w:ind', 'w:contextualSpacing', 'w:mirrorIndents',
                              'w:suppressOverlap', 'w:jc', 'w:textDirection',
                              'w:textAlignment', 'w:textboxTightWrap',
                              'w:outlineLvl', 'w:divId', 'w:cnfStyle', 'w:rPr',
                              'w:sectPr', 'w:pPrChange')


def _lvl_text(ilvl: int) -> str:
    """Format Word untuk level ke-ilvl (0-based): %1., %1.%2., %1.%2.%3., ..."""
    return '.'.join(f'%{i + 1}' for i in range(ilvl + 1)) + '.'


def _add_multilevel_numbering(doc, group_ids: dict[str, int],
                              start_at: int = 1, levels: int = 3,
                              hanging: Optional[dict] = None) -> int:
    """
    Tambah abstractNum 3 level + satu w:num per kelompok (BV, PP).

    Setiap kelompok memakai numId sendiri sehingga penomoran dimulai ulang
    dari 1 tanpa saling memengaruhi.
    """
    numbering = doc.part.numbering_part.element
    existing_abs = [int(a.get(qn('w:abstractNumId')))
                    for a in numbering.findall(qn('w:abstractNum'))]
    existing_num = [int(n.get(qn('w:numId')))
                    for n in numbering.findall(qn('w:num'))]
    abs_id = (max(existing_abs) + 1) if existing_abs else 0

    abstract = _el('w:abstractNum', **{'w:abstractNumId': abs_id})
    abstract.append(_el('w:nsid', **{'w:val': '5C3A21D7'}))
    abstract.append(_el('w:multiLevelType', **{'w:val': 'multilevel'}))
    abstract.append(_el('w:tmpl', **{'w:val': '5C3A21D7'}))

    for ilvl in range(levels):
        left = _indent_for_level(ilvl + 1)
        hang = (hanging or {}).get(ilvl + 1, HANGING_TWIPS)
        lvl_texts = {ilvl: _lvl_text(ilvl)}
        lvl = _el('w:lvl', **{'w:ilvl': ilvl, 'w:tentative': '0'})
        lvl.append(_el('w:start', **{'w:val': start_at}))
        lvl.append(_el('w:numFmt', **{'w:val': 'decimal'}))
        # Pemisah nomor-teks memakai TAB bawaan OOXML (tanpa spasi manual).
        # Catatan: menuliskan <w:suff w:val="tab"/> eksplisit membuat
        # LibreOffice tidak memajukan teks ke tab stop, jadi dibiarkan default.
        lvl.append(_el('w:lvlText', **{'w:val': lvl_texts[ilvl]}))
        lvl.append(_el('w:lvlJc', **{'w:val': 'left'}))
        pPr = _el('w:pPr')
        tabs = _el('w:tabs')
        tabs.append(_el('w:tab', **{'w:val': 'left', 'w:pos': left}))
        pPr.append(tabs)
        pPr.append(_el('w:ind', **{'w:left': left, 'w:hanging': hang}))
        rPr = _el('w:rPr')
        rPr.append(_el('w:rFonts', **{'w:ascii': FONT_NAME, 'w:hAnsi': FONT_NAME}))
        rPr.append(_el('w:sz', **{'w:val': FONT_SIZE_PT * 2}))
        pPr.append(rPr)
        lvl.append(pPr)
        abstract.append(lvl)

    # abstractNum harus sebelum semua w:num
    first_num = numbering.find(qn('w:num'))
    if first_num is not None:
        first_num.addprevious(abstract)
    else:
        numbering.append(abstract)

    # Satu w:num per kelompok, dengan startOverride 1 untuk tiap level
    next_num_id = (max(existing_num) + 1) if existing_num else 1
    for grup, _ in group_ids.items():
        num = _el('w:num', **{'w:numId': next_num_id})
        num.append(_el('w:abstractNumId', **{'w:val': abs_id}))
        for ilvl in range(levels):
            ov = _el('w:lvlOverride', **{'w:ilvl': ilvl})
            ov.append(_el('w:startOverride', **{'w:val': start_at}))
            num.append(ov)
        numbering.append(num)
        group_ids[grup] = next_num_id
        next_num_id += 1

    return abs_id


# --------------------------------------------------------------------------
# Gaya dan halaman
# --------------------------------------------------------------------------

def _setup_page_and_styles(doc):
    section = doc.sections[0]
    section.page_width = Twips(PAGE_W_TWIPS)
    section.page_height = Twips(PAGE_H_TWIPS)
    section.top_margin = Twips(MARGIN_TOP)
    section.right_margin = Twips(MARGIN_RIGHT)
    section.bottom_margin = Twips(MARGIN_BOTTOM)
    section.left_margin = Twips(MARGIN_LEFT)

    normal = doc.styles['Normal']
    normal.font.name = FONT_NAME
    normal.font.size = Pt(FONT_SIZE_PT)
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn('w:rFonts'))
    if rfonts is None:
        rfonts = _el('w:rFonts')
        rpr.append(rfonts)
    for attr in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
        rfonts.set(qn(attr), FONT_NAME)

    pf = normal.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(SPACING_AFTER_PT)
    pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    pf.line_spacing = LINE_SPACING

    from docx.enum.style import WD_STYLE_TYPE

    def gaya(nama, base='Normal', bold=False, align=None, keep_next=False):
        try:
            st = doc.styles[nama]
        except KeyError:
            st = doc.styles.add_style(nama, WD_STYLE_TYPE.PARAGRAPH)
            st.base_style = doc.styles[base]
        st.font.name = FONT_NAME
        st.font.size = Pt(FONT_SIZE_PT)
        st.font.bold = bold
        if align is not None:
            st.paragraph_format.alignment = align
        st.paragraph_format.space_before = Pt(0)
        st.paragraph_format.space_after = Pt(SPACING_AFTER_PT)
        st.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        st.paragraph_format.line_spacing = LINE_SPACING
        st.paragraph_format.keep_with_next = keep_next
        return st

    gaya('SKKNI Identitas', bold=True, align=WD_ALIGN_PARAGRAPH.LEFT)
    gaya('SKKNI Judul', bold=True, align=WD_ALIGN_PARAGRAPH.LEFT)
    gaya('SKKNI Isi', align=WD_ALIGN_PARAGRAPH.JUSTIFY if JUSTIFY else None)
    gaya('SKKNI Kepala Bagian', bold=True, align=WD_ALIGN_PARAGRAPH.LEFT,
         keep_next=True)
    gaya('SKKNI Bernomor', align=WD_ALIGN_PARAGRAPH.JUSTIFY if JUSTIFY else None)
    gaya('SKKNI Tanpa Nomor', align=WD_ALIGN_PARAGRAPH.JUSTIFY if JUSTIFY else None)
    gaya('SKKNI KUK', align=WD_ALIGN_PARAGRAPH.JUSTIFY if JUSTIFY else None)
    gaya('SKKNI Sel Tabel', align=WD_ALIGN_PARAGRAPH.LEFT)
    gaya('SKKNI Kepala Tabel', bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)


# --------------------------------------------------------------------------
# Tabel Elemen / KUK
# --------------------------------------------------------------------------

def _set_cell_margins(table):
    tblPr = table._tbl.tblPr
    mar = _el('w:tblCellMar')
    for side in ('top', 'bottom'):
        mar.append(_el(f'w:{side}', **{'w:w': 0, 'w:type': 'dxa'}))
    for side in ('left', 'right'):
        mar.append(_el(f'w:{side}', **{'w:w': 108, 'w:type': 'dxa'}))
    tblPr.append(mar)


def _set_table_borders(table):
    """Border tunggal 0,5 pt di semua sisi (seperti dokumen referensi)."""
    tblPr = table._tbl.tblPr
    borders = _el('w:tblBorders')
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        borders.append(_el(f'w:{side}', **{'w:val': 'single', 'w:color': 'auto',
                                           'w:sz': 4, 'w:space': 0}))
    tblPr.append(borders)


def _row_no_split(row):
    trPr = row._tr.get_or_add_trPr()
    trPr.append(_el('w:cantSplit'))


def _row_repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    trPr.append(_el('w:tblHeader'))


def _add_kuk_paragraph(cell, nomor: str, uraian: str, first: bool):
    """Paragraf KUK: nomor eksplisit dari JSON + tab + uraian, hanging indent."""
    p = cell.paragraphs[0] if first else cell.add_paragraph()
    p.style = cell.part.document.styles['SKKNI KUK']
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    p._p.get_or_add_pPr()
    _set_ind(p._p.pPr, KUK_INDENT_TWIPS, KUK_INDENT_TWIPS)
    _set_tabs(p._p.pPr, [KUK_INDENT_TWIPS])
    run = p.add_run(f'{nomor}\t{uraian}')
    run.font.name = FONT_NAME
    run.font.size = Pt(FONT_SIZE_PT)
    return p


def build_elemen_table(doc, elemen_list: list[dict]):
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _set_table_borders(table)
    _set_cell_margins(table)

    # Lebar kolom tetap: 4524 + 4524 twips
    tblW = _el('w:tblW', **{'w:w': TABLE_WIDTH_TWIPS, 'w:type': 'dxa'})
    for old in table._tbl.tblPr.findall(qn('w:tblW')):
        table._tbl.tblPr.remove(old)
    table._tbl.tblPr.append(tblW)
    for grid_col in table._tbl.tblGrid.findall(qn('w:gridCol')):
        grid_col.set(qn('w:w'), str(COL_WIDTH_TWIPS))

    # Baris header
    hdr = table.rows[0]
    _row_repeat_header(hdr)
    _row_no_split(hdr)
    for idx, teks in enumerate(('ELEMEN KOMPETENSI', 'KRITERIA UNJUK KERJA')):
        cell = hdr.cells[idx]
        cell.width = Twips(COL_WIDTH_TWIPS)
        p = cell.paragraphs[0]
        p.style = doc.styles['SKKNI Kepala Tabel']
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(teks)
        r.bold = True
        r.font.name = FONT_NAME
        r.font.size = Pt(FONT_SIZE_PT)

    # Satu baris per elemen
    for e in elemen_list:
        row = table.add_row()
        _row_no_split(row)
        left, right = row.cells[0], row.cells[1]
        left.width = Twips(COL_WIDTH_TWIPS)
        right.width = Twips(COL_WIDTH_TWIPS)

        p = left.paragraphs[0]
        p.style = doc.styles['SKKNI Sel Tabel']
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_after = Pt(0)
        _set_ind(p._p.get_or_add_pPr(), KUK_INDENT_TWIPS, KUK_INDENT_TWIPS)
        _set_tabs(p._p.pPr, [KUK_INDENT_TWIPS])
        r = p.add_run(f"{e['nomor_elemen']}\t{e['nama_elemen']}")
        r.font.name = FONT_NAME
        r.font.size = Pt(FONT_SIZE_PT)

        for i, kuk in enumerate(e['kuk']):
            _add_kuk_paragraph(right, kuk['nomor_kuk'], kuk['uraian_kuk'], first=(i == 0))

    return table


# --------------------------------------------------------------------------
# Bagian bernomor (Batasan Variabel / Panduan Penilaian)
# --------------------------------------------------------------------------

def _lebar_nomor_tw(nomor: str) -> int:
    """Perkiraan lebar nomor + titik akhir dalam twips."""
    return sum(DIGIT_TW if ch.isdigit() else DOT_TW for ch in (nomor + '.'))


def hitung_hanging(unit: dict, levels: int = 3) -> dict[int, int]:
    """
    Hitung hanging indent per level agar nomor tidak menempel ke teks.

    Left indent (posisi teks) tetap sesuai acuan; hanya hanging yang
    disesuaikan dengan lebar nomor terpanjang pada level tersebut ditambah
    jarak minimum 0,25 cm.
    """
    maks = {lvl: 0 for lvl in range(1, levels + 1)}
    for bagian in ('batasan_variabel', 'panduan_penilaian'):
        for n in _walk((unit.get(bagian) or {}).get('sections', [])):
            if n.get('is_numbered') and n.get('nomor'):
                lvl = min(max(1, int(n.get('level', 1))), levels)
                maks[lvl] = max(maks[lvl], _lebar_nomor_tw(n['nomor']))

    hasil = {}
    for lvl in range(1, levels + 1):
        if not maks[lvl]:
            hasil[lvl] = HANGING_TWIPS
            continue
        perlu = maks[lvl] + HANGING_GAP_TWIPS
        batas = _indent_for_level(lvl) + 20      # jangan sampai masuk margin
        hasil[lvl] = max(HANGING_TWIPS, min(batas, perlu))
    return hasil


def _indent_for_level(level: int) -> int:
    """Indentasi (twips) untuk level 1..3; level >3 memakai pola lanjutan."""
    if level in LEVEL_INDENT_TWIPS:
        return LEVEL_INDENT_TWIPS[level]
    return LEVEL_INDENT_TWIPS[3] + (level - 3) * HANGING_TWIPS


def _pagination(paragraph, keep_together: bool = True,
                keep_with_next: bool = False):
    """
    Atur pagination paragraf:
    - keep_together (w:keepLines): paragraf multi-baris tidak dipecah antarhalaman
    - keep_with_next: hanya untuk heading, TIDAK dirantai ke seluruh paragraf
    - widowControl tetap aktif (bawaan Word)
    """
    pf = paragraph.paragraph_format
    pf.keep_together = keep_together
    pf.keep_with_next = keep_with_next
    pf.widow_control = True


def _add_numbered_paragraph(doc, node: dict, num_id: int,
                            hanging: Optional[dict] = None):
    p = doc.add_paragraph(style='SKKNI Bernomor')
    level = max(1, int(node.get('level', 1)))
    _set_numpr(p, num_id, level - 1)
    left = _indent_for_level(level)
    hang = (hanging or {}).get(level, HANGING_TWIPS)
    p._p.get_or_add_pPr()
    _set_ind(p._p.pPr, left, hang)
    _set_tabs(p._p.pPr, [left])
    # Heading level 1 (mis. "5. Aspek kritis") tidak boleh terpisah dari isinya.
    # Hanya heading, bukan seluruh paragraf, agar tidak merantai blok panjang.
    _pagination(p, keep_together=True,
                keep_with_next=(level == 1 and bool(node.get('items'))))
    r = p.add_run(node['teks'])
    r.font.name = FONT_NAME
    r.font.size = Pt(FONT_SIZE_PT)
    return p


def _add_plain_paragraph(doc, node: dict):
    """Paragraf tanpa nomor, indentasi mengikuti induk (parent_nomor)."""
    p = doc.add_paragraph(style='SKKNI Tanpa Nomor')
    parent = node.get('parent_nomor')
    parent_level = len(parent.split('.')) if parent else 1
    left = _indent_for_level(parent_level + 1) if parent else 0
    p._p.get_or_add_pPr()
    _set_ind(p._p.pPr, left, 0)
    _pagination(p, keep_together=True)
    r = p.add_run(node['teks'])
    r.font.name = FONT_NAME
    r.font.size = Pt(FONT_SIZE_PT)
    return p


def _walk(nodes):
    for n in nodes:
        yield n
        yield from _walk(n.get('items', []))


def add_numbered_section(doc, judul: str, bagian: dict, num_id: int,
                         hanging: Optional[dict] = None):
    head = doc.add_paragraph(judul, style='SKKNI Kepala Bagian')
    _pagination(head, keep_together=True, keep_with_next=True)
    for node in _walk(bagian.get('sections', [])):
        if node.get('is_numbered'):
            _add_numbered_paragraph(doc, node, num_id, hanging)
        else:
            _add_plain_paragraph(doc, node)


# --------------------------------------------------------------------------
# Penyusunan dokumen
# --------------------------------------------------------------------------

def tambah_unit(doc, unit: dict, page_break_before: bool = False) -> dict:
    """
    Tambahkan satu unit kompetensi ke dokumen yang sudah ada.

    Dipakai oleh generator satu unit maupun multi-unit. Setiap pemanggilan
    membuat abstractNum + dua numId baru, sehingga penomoran tiap unit
    dimulai dari 1 dan tidak berlanjut dari unit sebelumnya.
    """
    group_ids = {'batasan_variabel': None, 'panduan_penilaian': None}
    level_data = max(
        [n.get('level', 1) for n in _walk((unit.get('batasan_variabel') or {}).get('sections', []))] +
        [n.get('level', 1) for n in _walk((unit.get('panduan_penilaian') or {}).get('sections', []))] +
        [3])
    levels = max(3, level_data)
    hanging = hitung_hanging(unit, levels)
    abs_id = _add_multilevel_numbering(doc, group_ids, levels=levels, hanging=hanging)

    # Identitas (halaman baru bila bukan unit pertama)
    p = doc.add_paragraph(style='SKKNI Identitas')
    if page_break_before:
        p.paragraph_format.page_break_before = True
    p.add_run(f"KODE UNIT: {unit['kode_unit']}")
    p = doc.add_paragraph(style='SKKNI Judul')
    p.add_run(unit['judul_unit'])
    p = doc.add_paragraph(style='SKKNI Isi')
    p.add_run(unit['deskripsi_unit'])

    # Tabel
    build_elemen_table(doc, unit['elemen_kompetensi'])
    doc.add_paragraph(style='SKKNI Isi')

    # Batasan Variabel & Panduan Penilaian
    add_numbered_section(doc, 'BATASAN VARIABEL', unit['batasan_variabel'],
                         group_ids['batasan_variabel'], hanging)
    add_numbered_section(doc, 'PANDUAN PENILAIAN', unit['panduan_penilaian'],
                         group_ids['panduan_penilaian'], hanging)

    return {
        'kode_unit': unit['kode_unit'],
        'abstract_num_id': abs_id,
        'num_ids': dict(group_ids),
        'levels': levels,
        'level_melebihi_tiga': level_data > 3,
        'hanging_per_level': dict(hanging),
    }


def dokumen_baru() -> Document:
    """Dokumen kosong dengan halaman & gaya SKKNI (untuk multi-unit)."""
    doc = Document()
    _setup_page_and_styles(doc)
    return doc


def build_document(unit: dict) -> Document:
    doc = dokumen_baru()
    meta = tambah_unit(doc, unit)

    doc.core_properties.title = unit['judul_unit']
    doc.core_properties.subject = f"SKKNI {unit['kode_unit']}"
    doc._skkni_meta = meta
    return doc


def generate_docx(json_path: str, output_path: str) -> dict:
    """Generate DOCX dari satu file JSON unit."""
    with open(json_path, encoding='utf-8') as f:
        unit = json.load(f)

    doc = build_document(unit)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)

    return {
        'docx_path': str(output_path),
        'kode_unit': unit['kode_unit'],
        'judul_unit': unit['judul_unit'],
        'jumlah_elemen': len(unit['elemen_kompetensi']),
        'jumlah_kuk': sum(len(e['kuk']) for e in unit['elemen_kompetensi']),
        'num_ids': doc._skkni_meta['num_ids'],
        'abstract_num_id': doc._skkni_meta['abstract_num_id'],
        'levels': doc._skkni_meta['levels'],
        'level_melebihi_tiga': doc._skkni_meta['level_melebihi_tiga'],
        'hanging_per_level': doc._skkni_meta['hanging_per_level'],
        'unit': unit,
    }


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print('Penggunaan: python -m app.docx_generator <json_unit> [output.docx]')
        sys.exit(1)

    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else 'output/unit.docx'
    info = generate_docx(src, out)
    print(f"DOCX dibuat: {info['docx_path']}")
    print(f"Unit       : {info['kode_unit']} — {info['judul_unit']}")
    print(f"Elemen/KUK : {info['jumlah_elemen']} / {info['jumlah_kuk']}")
    print(f"numId      : {info['num_ids']} (abstractNum {info['abstract_num_id']})")

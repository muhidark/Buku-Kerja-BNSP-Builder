"""
SKKNI Extractor - Generator Ekspor Buku Kerja ke Format Microsoft Word (.docx) & Bundel .ZIP (Fase 3C).

Mengonversi seluruh 24 formulir Buku Kerja Asesor BNSP V.2023 (FR.APL.01 s/d FR.VA)
menjadi dokumen Word (.docx) siap sunting serta bundel .zip bernomor urut sesuai
Daftar Periksa Kelengkapan Dokumen Buku Kerja Skema Sertifikasi (Upgrading-RCC).
"""

import io
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from jinja2 import Environment, FileSystemLoader

from app.buku_kerja import DAFTAR_DOKUMEN_BUKU_KERJA, susun_data_buku_kerja, tentukan_dokumen_aktif

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

# Pemetaan kode dokumen ke nama berkas bernomor urut resmi BNSP V.2023
NAMA_BERKAS_DOKUMEN: Dict[str, str] = {
    "daftar_periksa": "00_DAFTAR_PERIKSA_KELENGKAPAN_DOKUMEN_PELATIHAN_UPGRADING-RCC.docx",
    "apl01": "01_FR.APL.01_Permohonan_Sertifikasi_Kompetensi.docx",
    "apl02": "02_FR.APL.02_Asesmen_Mandiri.docx",
    "mapa01": "04_FR.MAPA.01_Merencanakan_Aktivitas_dan_Proses_Asesmen.docx",
    "skema_dok": "05a_Dokumen_Skema_Sertifikasi.docx",
    "skkni_dok": "05b_Dokumen_Standar_Kompetensi_Kerja_SKKNI.docx",
    "peta_kelompok": "05c_Peta_Kelompok_Pekerjaan.docx",
    "mapa02": "06_FR.MAPA.02_Peta_Instrumen_Asesmen.docx",
    "ak07": "07_FR.AK.07_Ceklis_Penyesuaian_Wajar_dan_Beralasan.docx",
    "ak04": "08_FR.AK.04_Banding_Asesmen.docx",
    "ak01": "09_FR.AK.01_Persetujuan_Asesmen_dan_Kerahasiaan.docx",
    "ia01": "10_FR.IA.01_CL_Ceklis_Observasi_Aktivitas.docx",
    "ia02": "11_FR.IA.02_TPD_Tugas_Praktik_Demonstrasi.docx",
    "ia03": "12_FR.IA.03_PMO_Pertanyaan_Mendukung_Observasi.docx",
    "ia04a": "13a_FR.IA.04A_DIT_Penjelasan_Proyek_Singkat.docx",
    "ia04b": "13b_FR.IA.04B_DIT_Penilaian_Proyek_Singkat.docx",
    "ia05a": "14a_FR.IA.05A_DPT_Pertanyaan_Tertulis_Pilihan_Ganda.docx",
    "ia05b": "14b_FR.IA.05B_Kunci_Jawaban_Pilihan_Ganda.docx",
    "ia05c": "14c_FR.IA.05C_Lembar_Jawaban_Pilihan_Ganda.docx",
    "ia06a": "15a_FR.IA.06A_DPT_Pertanyaan_Tertulis_Esai.docx",
    "ia06b": "15b_FR.IA.06.B_Kunci_Jawaban_Pertanyaan_Tertulis_Esai.docx",
    "ia06c": "15c_FR.IA.06.C_Lembar_Jawaban_Pertanyaan_Tertulis_Esai.docx",
    "ia07": "16_FR.IA.07_DPL_Daftar_Pertanyaan_Lisan.docx",
    "ia08": "17_FR.IA.08_CVP_Ceklis_Verifikasi_Portofolio.docx",
    "ak02": "21_FR.AK.02_Rekaman_Asesmen_Kompetensi.docx",
    "ak03": "22_FR.AK.03_Umpan_Balik_dan_Catatan_Asesmen.docx",
    "ak05": "23_FR.AK.05_Laporan_Asesmen.docx",
    "ak06": "24_FR.AK.06_Meninjau_Proses_Asesmen.docx",
    "va": "25_FR.VA_Memberikan_Kontribusi_Validasi_Asesmen.docx",
}


def _set_cell_shading(cell, fill_hex: str) -> None:
    """Memberi warna latar belakang pada sel tabel Word."""
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:shd")):
        tcPr.remove(old)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_hex.lstrip("#"))
    tcPr.append(shd)


def _set_cell_margins(cell, top_dxa: int = 70, bottom_dxa: int = 70, left_dxa: int = 100, right_dxa: int = 100) -> None:
    """Mengatur padding internal sel tabel Word dalam satuan dxa (1/20 pt)."""
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:tcMar")):
        tcPr.remove(old)
    tcMar = OxmlElement("w:tcMar")
    for side, val in (("top", top_dxa), ("bottom", bottom_dxa), ("left", left_dxa), ("right", right_dxa)):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")
        tcMar.append(el)
    tcPr.append(tcMar)


def _set_table_borders(table, bordered: bool = True) -> None:
    """Mengatur garis tepi tabel Word (bordered hitam tipis atau tanpa border)."""
    tblPr = table._tbl.tblPr
    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    borders = OxmlElement("w:tblBorders")
    sides = ("top", "left", "bottom", "right", "insideH", "insideV")
    for side in sides:
        b = OxmlElement(f"w:{side}")
        if bordered:
            b.set(qn("w:val"), "single")
            b.set(qn("w:sz"), "4")
            b.set(qn("w:space"), "0")
            b.set(qn("w:color"), "334155")
        else:
            b.set(qn("w:val"), "none")
        borders.append(b)
    tblPr.append(borders)


class _BukuKerjaHtmlParser(HTMLParser):
    """
    Parser HTML ke AST ringan untuk elemen halaman cetak Buku Kerja:
    Menangkap sheet, heading/judul, paragraf, dan tabel (termasuk rowspan, colspan, th, bold, italic, list).
    """

    def __init__(self) -> None:
        super().__init__()
        self.in_paper_container = False
        self.paper_depth = 0

        self.items: List[Dict[str, Any]] = []
        self.current_table: Optional[Dict[str, Any]] = None
        self.current_row: Optional[List[Dict[str, Any]]] = None
        self.current_cell: Optional[Dict[str, Any]] = None

        self.current_block: Optional[Dict[str, Any]] = None
        self.bold_depth = 0
        self.italic_depth = 0
        self.in_script_or_style = False
        self.sheet_count = 0
        # Tumpukan daftar (ol/ul) agar <li> di luar tabel menjadi paragraf bernomor/berbutir
        self.list_stack: List[Dict[str, Any]] = []

    def _push_run(self, target_runs: List[Tuple[str, bool, bool]], text: str) -> None:
        if not text:
            return
        is_bold = self.bold_depth > 0
        is_italic = self.italic_depth > 0
        if target_runs and target_runs[-1][1] == is_bold and target_runs[-1][2] == is_italic:
            prev_text, b, i = target_runs[-1]
            target_runs[-1] = (prev_text + text, b, i)
        else:
            target_runs.append((text, is_bold, is_italic))

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        cls = attr_map.get("class", "")
        style = attr_map.get("style", "").lower()

        if tag in ("script", "style"):
            self.in_script_or_style = True
            return

        if not self.in_paper_container:
            if tag == "div" and "lsp-paper-container" in cls:
                self.in_paper_container = True
                self.paper_depth = 1
            return

        if tag == "div":
            self.paper_depth += 1
            if "lsp-page-sheet" in cls:
                is_landscape = "lsp-page-landscape" in cls
                self.items.append({"type": "sheet_start", "landscape": is_landscape})
                self.sheet_count += 1
                return

        if tag == "span" and "dots-line" in cls:
            dots = "................................................................................"
            if self.current_cell is not None:
                self._push_run(self.current_cell["runs"], dots)
            elif self.current_block is not None:
                self._push_run(self.current_block["runs"], dots)
            return

        if tag in ("strong", "b"):
            self.bold_depth += 1
            return
        if tag in ("em", "i"):
            self.italic_depth += 1
            return

        if tag == "br":
            if self.current_cell is not None:
                self._push_run(self.current_cell["runs"], "\n")
            elif self.current_block is not None:
                self._push_run(self.current_block["runs"], "\n")
            return

        if tag in ("ol", "ul"):
            if self.current_block is not None:
                self._flush_block()
            self.list_stack.append({"type": tag, "counter": 0})
            return

        if tag == "li":
            if self.current_cell is not None:
                if self.current_cell["runs"]:
                    self._push_run(self.current_cell["runs"], "\n• ")
                else:
                    self._push_run(self.current_cell["runs"], "• ")
                return
            # Di luar tabel: tiap butir menjadi paragraf tersendiri
            if self.current_block is not None:
                self._flush_block()
            prefix = "• "
            if self.list_stack and self.list_stack[-1]["type"] == "ol":
                self.list_stack[-1]["counter"] += 1
                prefix = f"{self.list_stack[-1]['counter']}. "
            self.current_block = {
                "type": "paragraph",
                "level": "normal",
                "tag": "li",
                "runs": [(prefix, False, False)],
                "added_bold": False,
            }
            return

        if tag == "table":
            if self.current_block is not None:
                self._flush_block()
            bordered = "lsp-table-borderless" not in cls
            self.current_table = {
                "type": "table",
                "bordered": bordered,
                "rows": [],
            }
            return

        if tag == "tr" and self.current_table is not None:
            self.current_row = []
            return

        if tag in ("td", "th") and self.current_row is not None:
            try:
                rowspan = max(1, int(attr_map.get("rowspan") or 1))
            except ValueError:
                rowspan = 1
            try:
                colspan = max(1, int(attr_map.get("colspan") or 1))
            except ValueError:
                colspan = 1

            is_header = (tag == "th") or ("background" in style and ("#f1f5f9" in style or "#f8fafc" in style or "#e0f2fe" in style or "#e2e8f0" in style))
            align_center = ("text-align: center" in style) or ("text-align:center" in style) or (attr_map.get("align") == "center") or (tag == "th")
            if tag == "th":
                self.bold_depth += 1

            width_pct = None
            lebar = (attr_map.get("width") or attr_map.get("colwidth") or "").strip()
            if lebar.endswith("%"):
                try:
                    width_pct = float(lebar[:-1])
                except ValueError:
                    width_pct = None
            elif lebar:
                try:  # atribut width dalam piksel/angka dianggap proporsi
                    width_pct = float(lebar)
                except ValueError:
                    width_pct = None

            self.current_cell = {
                "tag": tag,
                "rowspan": rowspan,
                "colspan": colspan,
                "is_header": is_header,
                "align_center": align_center,
                "width_pct": width_pct,
                "runs": [],
            }
            return

        # Blok di luar tabel
        if self.current_table is None:
            if tag in ("h1", "h2", "h3", "h4") or (
                tag == "div" and any(k in cls for k in ("lsp-doc-title", "lsp-section-title", "lsp-subsection-title", "lsp-doc-desc", "lsp-box-instruction"))
            ) or tag == "p" or (tag == "div" and "lsp-page-sheet" not in cls):
                self._flush_block()
                level = "normal"
                if "lsp-doc-title" in cls or tag in ("h1", "h2", "h3"):
                    level = "title"
                    self.bold_depth += 1
                elif "lsp-section-title" in cls or "lsp-subsection-title" in cls or tag == "h4":
                    level = "subtitle"
                    self.bold_depth += 1
                elif tag == "div" and ("font-weight: bold" in style or "font-weight:bold" in style):
                    level = "subtitle"
                    self.bold_depth += 1
                self.current_block = {
                    "type": "paragraph",
                    "level": level,
                    "tag": tag,
                    "runs": [],
                    "added_bold": level in ("title", "subtitle"),
                    "pre": "pre-wrap" in style,
                }

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self.in_script_or_style = False
            return

        if not self.in_paper_container:
            return

        if tag in ("ol", "ul"):
            if self.list_stack:
                self.list_stack.pop()
            return

        if tag in ("strong", "b"):
            self.bold_depth = max(0, self.bold_depth - 1)
            return
        if tag in ("em", "i"):
            self.italic_depth = max(0, self.italic_depth - 1)
            return

        if tag in ("td", "th") and self.current_cell is not None and self.current_row is not None:
            if tag == "th":
                self.bold_depth = max(0, self.bold_depth - 1)
            self.current_row.append(self.current_cell)
            self.current_cell = None
            return

        if tag == "tr" and self.current_row is not None and self.current_table is not None:
            if self.current_row:
                self.current_table["rows"].append(self.current_row)
            self.current_row = None
            return

        if tag == "table" and self.current_table is not None:
            if self.current_table["rows"]:
                self.items.append(self.current_table)
            self.current_table = None
            return

        if tag == "div":
            if self.current_block is not None and self.current_block.get("tag") == "div":
                self._flush_block()
            self.paper_depth -= 1
            if self.paper_depth <= 0:
                self.in_paper_container = False
            return

        if self.current_block is not None and tag == self.current_block.get("tag"):
            self._flush_block()

    def handle_data(self, data: str) -> None:
        if self.in_script_or_style or not self.in_paper_container:
            return
        # Normalisasi spasi; baris baru hanya dipertahankan pada blok white-space: pre-wrap
        if self.current_block is not None and self.current_block.get("pre"):
            cleaned = re.sub(r"[ \t]*\r?\n[ \t]*", "\n", data)
            cleaned = re.sub(r"[ \t]+", " ", cleaned)
        else:
            cleaned = re.sub(r"[ \t\r\n]+", " ", data)
        if not cleaned.strip():
            return

        if self.current_cell is not None:
            self._push_run(self.current_cell["runs"], cleaned)
        elif self.current_block is not None:
            self._push_run(self.current_block["runs"], cleaned)

    def _flush_block(self) -> None:
        if not self.current_block:
            return
        if self.current_block.get("added_bold"):
            self.bold_depth = max(0, self.bold_depth - 1)
        full_txt = "".join(r[0] for r in self.current_block["runs"]).strip()
        if full_txt:
            self.items.append(self.current_block)
        self.current_block = None


def _tulis_runs_ke_paragraf(paragraph, runs: List[Tuple[str, bool, bool]], font_size_pt: float = 9.5) -> None:
    """Menulis daftar run (teks, bold, italic) ke objek paragraf python-docx dengan merapikan spasi tepi."""
    if not runs:
        return
    # Trim leading/trailing whitespace pada run pertama dan terakhir
    cleaned_runs: List[Tuple[str, bool, bool]] = []
    for idx, (txt, b, i) in enumerate(runs):
        lines = [re.sub(r"^[ \t]+|[ \t]+$", "", ln) for ln in txt.split("\n")]
        norm_txt = "\n".join(lines)
        if idx == 0:
            norm_txt = norm_txt.lstrip()
        if idx == len(runs) - 1:
            norm_txt = norm_txt.rstrip()
        if norm_txt:
            cleaned_runs.append((norm_txt, b, i))

    for txt, is_bold, is_italic in cleaned_runs:
        # Pisahkan baris baru menjadi <w:br> agar tampil sebagai baris terpisah di Word/PDF
        bagian = txt.split("\n")
        for no_baris, teks_baris in enumerate(bagian):
            if no_baris:
                br = paragraph.add_run()
                br.add_break()
                br.font.name = "Arial"
                br.font.size = Pt(font_size_pt)
            if not teks_baris:
                continue
            run = paragraph.add_run(teks_baris)
            run.bold = is_bold
            run.italic = is_italic
            run.font.name = "Arial"
            run.font.size = Pt(font_size_pt)


def _render_tabel_ke_docx(doc: Document, tbl_ast: Dict[str, Any]) -> None:
    """Merender AST tabel (termasuk rowspan & colspan) menjadi tabel Word."""
    rows_ast = tbl_ast.get("rows") or []
    if not rows_ast:
        return

    num_rows = len(rows_ast)
    # Hitung jumlah kolom maksimum dengan memperhitungkan rowspan & colspan
    occupied: Dict[Tuple[int, int], bool] = {}
    max_cols = 0
    placed_cells: List[Tuple[int, int, int, int, Dict[str, Any]]] = []

    for r_idx, row in enumerate(rows_ast):
        c_idx = 0
        for cell_ast in row:
            while occupied.get((r_idx, c_idx)):
                c_idx += 1
            rs = min(cell_ast["rowspan"], num_rows - r_idx)
            cs = cell_ast["colspan"]
            for dr in range(rs):
                for dc in range(cs):
                    occupied[(r_idx + dr, c_idx + dc)] = True
            placed_cells.append((r_idx, c_idx, rs, cs, cell_ast))
            c_idx += cs
        if c_idx > max_cols:
            max_cols = c_idx

    if max_cols <= 0:
        return

    table = doc.add_table(rows=num_rows, cols=max_cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    _set_table_borders(table, bordered=tbl_ast.get("bordered", True))

    for r_idx, c_idx, rs, cs, cell_ast in placed_cells:
        if r_idx >= num_rows or c_idx >= max_cols:
            continue
        end_r = min(num_rows - 1, r_idx + rs - 1)
        end_c = min(max_cols - 1, c_idx + cs - 1)
        target_cell = table.cell(r_idx, c_idx)
        if end_r > r_idx or end_c > c_idx:
            try:
                target_cell.merge(table.cell(end_r, end_c))
            except Exception:
                pass

        _set_cell_margins(target_cell)
        if cell_ast.get("is_header"):
            _set_cell_shading(target_cell, "F1F5F9")

        p = target_cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(1)
        if cell_ast.get("align_center"):
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        _tulis_runs_ke_paragraf(p, cell_ast.get("runs") or [], font_size_pt=9.5)

    # Lebar kolom mengikuti atribut width (%) pada HTML; sisa dibagi rata
    try:
        sec_aktif = doc.sections[-1]
        lebar_tersedia = int(sec_aktif.page_width - sec_aktif.left_margin - sec_aktif.right_margin)
    except Exception:
        lebar_tersedia = None

    if lebar_tersedia:
        pct_map: Dict[int, float] = {}
        for r_idx, c_idx, rs, cs, cell_ast in placed_cells:
            if cs == 1 and cell_ast.get("width_pct") and c_idx not in pct_map:
                pct_map[c_idx] = float(cell_ast["width_pct"])
        if pct_map:
            total_pct = sum(pct_map.values())
            if total_pct > 100.0:
                skala = 100.0 / total_pct
                pct_map = {k: v * skala for k, v in pct_map.items()}
                total_pct = 100.0
            kolom_sisa = [j for j in range(max_cols) if j not in pct_map]
            per_sisa = ((100.0 - total_pct) / len(kolom_sisa)) if kolom_sisa else 0.0
            for j in kolom_sisa:
                pct_map[j] = per_sisa

            table.autofit = False
            tblPr = table._tbl.tblPr
            for old_layout in tblPr.findall(qn("w:tblLayout")):
                tblPr.remove(old_layout)
            layout = OxmlElement("w:tblLayout")
            layout.set(qn("w:type"), "fixed")
            tblPr.append(layout)

            lebar_kolom = [int(lebar_tersedia * (pct_map.get(j, 0) / 100.0)) for j in range(max_cols)]
            for j, w in enumerate(lebar_kolom):
                if w > 0:
                    table.columns[j].width = w
            # Hanya sel satu kolom; sel gabungan mengikuti lebar grid kolomnya
            for r_idx, c_idx, rs, cs, cell_ast in placed_cells:
                if cs == 1 and r_idx < num_rows and c_idx < max_cols and lebar_kolom[c_idx] > 0:
                    try:
                        table.cell(r_idx, c_idx).width = lebar_kolom[c_idx]
                    except Exception:
                        pass

    # Baris tabel tidak boleh terpotong; tabel pendek dijaga utuh dalam satu halaman
    for baris in table.rows:
        trPr = baris._tr.get_or_add_trPr()
        for old_split in trPr.findall(qn("w:cantSplit")):
            trPr.remove(old_split)
        trPr.append(OxmlElement("w:cantSplit"))
    if num_rows <= 8:
        for baris in table.rows[:-1]:
            for sel in baris.cells:
                for par in sel.paragraphs:
                    par.paragraph_format.keep_with_next = True

    # Spasi kecil antar tabel
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(0)
    spacer.paragraph_format.space_after = Pt(3)


def _buang_paragraf_kosong_akhir(doc: Document) -> None:
    """Menghapus paragraf kosong di akhir dokumen agar tidak menimbulkan halaman kosong."""
    for _ in range(3):
        paras = doc.paragraphs
        if not paras:
            return
        terakhir = paras[-1]
        if terakhir.text.strip() or terakhir.runs:
            return
        el = terakhir._element
        el.getparent().remove(el)


def buat_docx_buku_kerja_bytes(
    data: Dict[str, Any],
    dokumen_aktif: List[str],
    judul_halaman: str = "Buku Kerja Asesor V.2023",
) -> bytes:
    """
    Merender daftar kode dokumen (`dokumen_aktif`) untuk skema `data` menjadi
    berkas Microsoft Word (.docx) dalam bentuk bytes.
    """
    template = _jinja_env.get_template("cetak_apl.html")
    rendered_html = template.render(
        judul=judul_halaman,
        judul_halaman=judul_halaman,
        data=data,
        doc_mode=dokumen_aktif[0] if len(dokumen_aktif) == 1 else "all",
        dokumen_aktif=dokumen_aktif,
    )

    parser = _BukuKerjaHtmlParser()
    parser.feed(rendered_html)

    doc = Document()
    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Arial"
    normal_style.font.size = Pt(10)

    sheet_seen = 0
    for item in parser.items:
        tipe = item.get("type")
        if tipe == "sheet_start":
            is_land = item.get("landscape", False)
            if sheet_seen == 0:
                sec = doc.sections[0]
            else:
                _buang_paragraf_kosong_akhir(doc)
                sec = doc.add_section(WD_SECTION.NEW_PAGE)
            sheet_seen += 1

            if is_land:
                sec.orientation = WD_ORIENT.LANDSCAPE
                sec.page_width = Cm(29.7)
                sec.page_height = Cm(21.0)
                sec.top_margin = Cm(1.2)
                sec.bottom_margin = Cm(1.2)
                sec.left_margin = Cm(1.2)
                sec.right_margin = Cm(1.2)
            else:
                sec.orientation = WD_ORIENT.PORTRAIT
                sec.page_width = Cm(21.0)
                sec.page_height = Cm(29.7)
                sec.top_margin = Cm(1.5)
                sec.bottom_margin = Cm(1.5)
                sec.left_margin = Cm(1.5)
                sec.right_margin = Cm(1.5)
        elif tipe == "page_break":
            doc.add_page_break()
        elif tipe == "paragraph":
            lvl = item.get("level", "normal")
            p = doc.add_paragraph()
            if lvl == "title":
                p.paragraph_format.space_before = Pt(4)
                p.paragraph_format.space_after = Pt(6)
                _tulis_runs_ke_paragraf(p, item.get("runs") or [], font_size_pt=12.0)
            elif lvl == "subtitle":
                p.paragraph_format.space_before = Pt(6)
                p.paragraph_format.space_after = Pt(3)
                _tulis_runs_ke_paragraf(p, item.get("runs") or [], font_size_pt=10.5)
            else:
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(4)
                if item.get("tag") == "li":
                    p.paragraph_format.left_indent = Cm(0.55)
                    p.paragraph_format.first_line_indent = Cm(-0.4)
                _tulis_runs_ke_paragraf(p, item.get("runs") or [], font_size_pt=9.5)
        elif tipe == "table":
            _render_tabel_ke_docx(doc, item)

    _buang_paragraf_kosong_akhir(doc)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def buat_zip_buku_kerja_bytes(
    schema_id: str,
    doc_mode: str = "all",
    no_skema: str = "",
    nama_asesor: str = "",
    no_met: str = "",
    metode_mapa: str = "",
    kategori_asesi: int = 0,
) -> Optional[Tuple[bytes, str]]:
    """
    Membuat bundel .ZIP berisi berkas-berkas .docx Buku Kerja bernomor urut
    (01_FR.APL.01.docx s/d 25_FR.VA.docx) beserta 00_Buku_Kerja_Gabungan.docx.
    Mengembalikan tuple (zip_bytes, nama_file_zip) atau None bila skema tidak ditemukan.
    """
    data = susun_data_buku_kerja(
        schema_id=schema_id,
        no_skema=no_skema,
        nama_asesor=nama_asesor,
        no_met=no_met,
        metode_mapa=metode_mapa,
        kategori_asesi=kategori_asesi,
    )
    if not data:
        return None

    valid_modes = {d["kode"] for d in DAFTAR_DOKUMEN_BUKU_KERJA}
    mode_bersih = doc_mode.lower().strip() if doc_mode.lower().strip() in valid_modes else "all"
    dokumen_aktif = tentukan_dokumen_aktif(mode_bersih, data.get("metode_mapa", "observasi"))

    slug_skema = re.sub(r"[^a-zA-Z0-9_-]+", "_", data["nama_skema"]).strip("_") or schema_id
    zip_buf = io.BytesIO()

    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. Buat berkas .docx terpisah untuk setiap formulir dalam dokumen_aktif
        groups = data.get("kelompok_pekerjaan", {}).get("groups", [])
        for kode_dok in dokumen_aktif:
            # Bila instrumen per kelompok (IA.01, IA.02, IA.03, IA.04A, IA.04B) dan ada lebih dari 1 kelompok
            if kode_dok in ("ia01", "ia02", "ia03", "ia04a", "ia04b") and len(groups) > 1:
                nama_docx_base = NAMA_BERKAS_DOKUMEN.get(kode_dok, f"{kode_dok.upper()}.docx")
                match_prefix = re.match(r"^(\d+[a-z]?_FR\.[A-Z0-9\.]+)", nama_docx_base)
                prefix_str = match_prefix.group(1) if match_prefix else kode_dok.upper()

                for k_idx, grp in enumerate(groups, start=1):
                    slug_grp = re.sub(r"[^a-zA-Z0-9_-]+", "_", grp.get("nama") or f"Kelompok_{k_idx}").strip("_")[:30]
                    nama_file_kelompok = f"{prefix_str}_K{k_idx}_{slug_grp}.docx"
                    data_grp = dict(data)
                    data_grp["kelompok_pekerjaan"] = dict(data.get("kelompok_pekerjaan", {}))
                    data_grp["kelompok_pekerjaan"]["groups"] = [grp]
                    docx_bytes = buat_docx_buku_kerja_bytes(
                        data=data_grp,
                        dokumen_aktif=[kode_dok],
                        judul_halaman=f"{nama_file_kelompok} - {data['nama_skema']}",
                    )
                    zf.writestr(f"Buku_Kerja_{slug_skema}/{nama_file_kelompok}", docx_bytes)
            else:
                nama_docx = NAMA_BERKAS_DOKUMEN.get(kode_dok, f"{kode_dok.upper()}.docx")
                docx_bytes = buat_docx_buku_kerja_bytes(
                    data=data,
                    dokumen_aktif=[kode_dok],
                    judul_halaman=f"{nama_docx} - {data['nama_skema']}",
                )
                zf.writestr(f"Buku_Kerja_{slug_skema}/{nama_docx}", docx_bytes)

        # 2. Jika lebih dari 1 dokumen, sertakan juga 00_Buku_Kerja_Lengkap_Gabungan.docx
        if len(dokumen_aktif) > 1:
            gabungan_bytes = buat_docx_buku_kerja_bytes(
                data=data,
                dokumen_aktif=dokumen_aktif,
                judul_halaman=f"Buku Kerja Lengkap - {data['nama_skema']}",
            )
            zf.writestr(
                f"Buku_Kerja_{slug_skema}/00_Buku_Kerja_Lengkap_Gabungan.docx",
                gabungan_bytes,
            )

    nama_zip = f"Buku_Kerja_BNSP_2023_{slug_skema}_{mode_bersih}.zip"
    return zip_buf.getvalue(), nama_zip

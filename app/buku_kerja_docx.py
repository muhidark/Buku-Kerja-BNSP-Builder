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
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from jinja2 import Environment, FileSystemLoader

from app.buku_kerja import DAFTAR_DOKUMEN_BUKU_KERJA, susun_data_buku_kerja, tentukan_dokumen_aktif

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

# Pemetaan kode dokumen ke nama berkas bernomor urut resmi BNSP V.2023
NAMA_BERKAS_DOKUMEN: Dict[str, str] = {
    "apl01": "01_FR.APL.01_Permohonan_Sertifikasi_Kompetensi.docx",
    "apl02": "02_FR.APL.02_Asesmen_Mandiri.docx",
    "mapa01": "04_FR.MAPA.01_Merencanakan_Aktivitas_dan_Proses_Asesmen.docx",
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
                if self.sheet_count > 0:
                    self.items.append({"type": "page_break"})
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

        if tag == "li":
            if self.current_cell is not None:
                if self.current_cell["runs"]:
                    self._push_run(self.current_cell["runs"], "\n• ")
                else:
                    self._push_run(self.current_cell["runs"], "• ")
            elif self.current_block is not None:
                if self.current_block["runs"]:
                    self._push_run(self.current_block["runs"], "\n• ")
                else:
                    self._push_run(self.current_block["runs"], "• ")
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

            self.current_cell = {
                "tag": tag,
                "rowspan": rowspan,
                "colspan": colspan,
                "is_header": is_header,
                "align_center": align_center,
                "runs": [],
            }
            return

        # Blok di luar tabel
        if self.current_table is None:
            if tag in ("h1", "h2", "h3", "h4") or (
                tag == "div" and any(k in cls for k in ("lsp-doc-title", "lsp-section-title", "lsp-subsection-title", "lsp-doc-desc", "lsp-box-instruction"))
            ) or tag == "p":
                self._flush_block()
                level = "normal"
                if "lsp-doc-title" in cls or tag in ("h1", "h2", "h3"):
                    level = "title"
                    self.bold_depth += 1
                elif "lsp-section-title" in cls or "lsp-subsection-title" in cls or tag == "h4":
                    level = "subtitle"
                    self.bold_depth += 1
                self.current_block = {
                    "type": "paragraph",
                    "level": level,
                    "tag": tag,
                    "runs": [],
                    "added_bold": level in ("title", "subtitle"),
                }

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self.in_script_or_style = False
            return

        if not self.in_paper_container:
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
        # Normalisasi spasi berlebih tetapi pertahankan newline jika di dalam pre
        cleaned = re.sub(r"[ \t\r\n]+", " ", data)
        if not cleaned.strip() and cleaned != " ":
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
        run = paragraph.add_run(txt)
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

    # Spasi kecil antar tabel
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(0)
    spacer.paragraph_format.space_after = Pt(3)


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
    # Konfigurasi halaman A4 (210mm x 297mm) dengan margin 1.5 cm
    for section in doc.sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(1.5)
        section.bottom_margin = Cm(1.5)
        section.left_margin = Cm(1.5)
        section.right_margin = Cm(1.5)

    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Arial"
    normal_style.font.size = Pt(10)

    for item in parser.items:
        tipe = item.get("type")
        if tipe == "page_break":
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
                _tulis_runs_ke_paragraf(p, item.get("runs") or [], font_size_pt=9.5)
        elif tipe == "table":
            _render_tabel_ke_docx(doc, item)

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
        for kode_dok in dokumen_aktif:
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

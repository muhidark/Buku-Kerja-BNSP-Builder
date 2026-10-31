"""
SKKNI Extractor - Parser Dokumen Skema Sertifikasi (Fase 3D)

Membaca file DOCX skema sertifikasi, menemukan bagian "Kemasan / Paket
Kompetensi", lalu mengambil daftar kode unit dari TABEL di bagian tersebut.

Tidak memakai daftar manual: seluruh kode dibaca dari dokumen.
"""

import json
import re
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

UNIT_CODE_PATTERN = re.compile(r'[A-Z]\.\d{2}[A-Z]{2,3}\d{2}\.\d{3}\.\d')
JUDUL_BAGIAN = re.compile(r'kemasan\s*/\s*paket\s+kompetensi', re.IGNORECASE)
# Pembatas: heading bagian berikutnya (dipakai bila ada lebih dari satu tabel)
PENUTUP_BAGIAN = re.compile(
    r'^(persyaratan\s+dasar|hak\s+pemohon|kewajiban\s+pemegang|proses\s+sertifikasi|'
    r'surveilen|kode\s+etik|masa\s+berlaku|biaya|sanksi)', re.IGNORECASE)


def _iter_body(doc):
    """Iterasi elemen body sesuai urutan dokumen: ('p', Paragraph) / ('tbl', Table)."""
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag.endswith('}p'):
            yield 'p', Paragraph(child, doc)
        elif child.tag.endswith('}tbl'):
            yield 'tbl', Table(child, doc)


def _norm(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '')).strip()


def baca_skema(path: str | Path) -> dict:
    """
    Baca dokumen skema dan kembalikan daftar unit pada bagian Kemasan/Paket.

    Returns:
        dict: sumber, bagian, tabel_index, units[], peringatan[]
    """
    path = Path(path)
    doc = Document(str(path))

    elemen = list(_iter_body(doc))
    idx_judul = None
    for i, (jenis, obj) in enumerate(elemen):
        if jenis == 'p' and JUDUL_BAGIAN.search(_norm(obj.text)):
            idx_judul = i
            break

    if idx_judul is None:
        raise ValueError('Bagian "Kemasan / Paket Kompetensi" tidak ditemukan')

    # Batas akhir bagian: heading penutup berikutnya (jika ada)
    idx_akhir = len(elemen)
    for j in range(idx_judul + 1, len(elemen)):
        jenis, obj = elemen[j]
        if jenis == 'p' and PENUTUP_BAGIAN.match(_norm(obj.text)):
            idx_akhir = j
            break

    # Cari tabel unit di dalam rentang bagian
    tabel_units = []
    for k in range(idx_judul + 1, idx_akhir):
        jenis, obj = elemen[k]
        if jenis != 'tbl' or not obj.rows:
            continue
        header = [_norm(c.text).lower() for c in obj.rows[0].cells]
        if any('kode unit' in h for h in header):
            tabel_units.append((k, obj))

    if not tabel_units:
        raise ValueError('Tabel daftar unit kompetensi tidak ditemukan pada bagian Kemasan/Paket')

    peringatan = []
    if len(tabel_units) > 1:
        peringatan.append(f'Ditemukan {len(tabel_units)} tabel unit; hanya tabel pertama dipakai')

    posisi_body, tabel = tabel_units[0]
    tabel_index = sum(1 for jenis, _ in elemen[:posisi_body] if jenis == 'tbl')

    header = [_norm(c.text).lower() for c in tabel.rows[0].cells]
    kol_no = next((i for i, h in enumerate(header) if h in ('no', 'no.', 'nomor')), 0)
    kol_kode = next((i for i, h in enumerate(header) if 'kode unit' in h), None)
    kol_judul = next((i for i, h in enumerate(header) if 'judul unit' in h), None)
    if kol_kode is None:
        raise ValueError('Kolom "Kode Unit" tidak ditemukan pada tabel unit')

    units = []
    for r_i, row in enumerate(tabel.rows[1:], start=2):
        sel = row.cells
        kode = _norm(sel[kol_kode].text) if kol_kode < len(sel) else ''
        if not kode:
            continue
        judul = _norm(sel[kol_judul].text) if kol_judul is not None and kol_judul < len(sel) else ''
        no = _norm(sel[kol_no].text) if kol_no < len(sel) else ''
        valid = bool(UNIT_CODE_PATTERN.fullmatch(kode))
        units.append({
            'nomor_urut': int(no) if no.isdigit() else (len(units) + 1),
            'kode_unit': kode,
            'judul_skema': judul,
            'pola_kode_valid': valid,
            'sumber': {
                'dokumen': path.name,
                'bagian': 'Kemasan / Paket Kompetensi',
                'tabel_index': tabel_index,
                'baris_tabel': r_i,
            },
            'catatan': [] if valid else ['kode tidak sesuai pola SKKNI; perlu verifikasi'],
        })
        if not valid:
            peringatan.append(f'Baris {r_i}: kode "{kode}" tidak sesuai pola')

    # Duplikat
    seen = {}
    for u in units:
        seen.setdefault(u['kode_unit'], []).append(u['nomor_urut'])
    for kode, nomor in seen.items():
        if len(nomor) > 1:
            peringatan.append(f'Kode duplikat: {kode} (nomor urut {nomor})')
            for u in units:
                if u['kode_unit'] == kode:
                    u['catatan'].append('kode duplikat dalam dokumen skema')

    return {
        'sumber': path.name,
        'bagian': 'Kemasan / Paket Kompetensi',
        'tabel_index': tabel_index,
        'jumlah_unit': len(units),
        'units': units,
        'peringatan': peringatan,
    }


def baca_skema_pdf(path: str | Path) -> dict:
    """Baca dokumen skema format PDF dan ekstrak daftar unit kompetensi."""
    import fitz
    path = Path(path)
    doc = fitz.open(str(path))
    pattern = re.compile(r'\b([A-Z]\.[A-Z0-9]{5,8}\.\d{3}\.\d{1,2})\b')
    units = []
    seen = set()
    peringatan = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        text = page.get_text()
        for line in text.split('\n'):
            line = line.strip()
            m = pattern.search(line)
            if m:
                kode = m.group(1)
                if kode not in seen:
                    seen.add(kode)
                    judul = line.replace(kode, '').strip(' -:\t()[]0123456789.')
                    units.append({
                        'nomor_urut': len(units) + 1,
                        'kode_unit': kode,
                        'judul_skema': judul or f"Unit {kode}",
                    })

    if not units:
        peringatan.append('Tidak ada kode unit kompetensi yang terdeteksi pada dokumen PDF.')

    return {
        'sumber': str(path),
        'bagian': 'PDF Auto Extraction',
        'jumlah_unit': len(units),
        'units': units,
        'peringatan': peringatan,
    }


def baca_skema_berkas(path: str | Path) -> dict:
    """Deteksi jenis berkas (.docx atau .pdf) dan parse skema."""
    p = Path(path)
    if p.suffix.lower() == '.pdf':
        return baca_skema_pdf(p)
    return baca_skema(p)


def simpan_skema(hasil: dict, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(hasil, ensure_ascii=False, indent=2), encoding='utf-8')
    return output_path


if __name__ == '__main__':
    import sys

    src = sys.argv[1] if len(sys.argv) > 1 else 'data/skema/21. Content Creator.docx'
    out = sys.argv[2] if len(sys.argv) > 2 else 'data/json/schema_content_creator.json'
    hasil = baca_skema(src)
    simpan_skema(hasil, out)
    print(f'Skema   : {hasil["sumber"]}')
    print(f'Unit    : {hasil["jumlah_unit"]}')
    for u in hasil['units']:
        print(f'  {u["nomor_urut"]:2}. {u["kode_unit"]} — {u["judul_skema"][:60]}')
    if hasil['peringatan']:
        print('Peringatan:', hasil['peringatan'])

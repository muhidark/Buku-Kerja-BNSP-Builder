"""
SKKNI Extractor - Lapisan data baca-saja untuk antarmuka web (Fase 4A).

Semua angka berasal dari berkas yang benar-benar ada di proyek:
- PDF SKKNI       : data/pdf/
- Dokumen skema   : data/skema/
- JSON unit       : data/json/**, data/json/schema_content_creator/, data/json/cross_skkni/
- Hasil           : output/**

Tidak ada data dummy: bila sumber belum ada, nilainya 0 / status belum tersedia.
"""

import json
import os
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / 'data' / 'pdf'
SKEMA_DIR = ROOT / 'data' / 'skema'
JSON_DIR = ROOT / 'data' / 'json'
SCHEMA_JSON_DIR = JSON_DIR / 'schema_content_creator'
CROSS_JSON_DIR = JSON_DIR / 'cross_skkni'
OUT_DIR = ROOT / 'output'

PDF_NOMOR = re.compile(r'NOMOR\s+(\d+)\s+TAHUN\s+(\d{4})')


# --------------------------------------------------------------------------
# SKKNI (PDF)
# --------------------------------------------------------------------------

def _identitas_pdf(path: Path) -> dict:
    """Baca NOMOR/TAHUN penetapan dari beberapa halaman awal PDF."""
    import pymupdf as fitz

    try:
        with fitz.open(str(path)) as doc:
            halaman = doc.page_count
            teks = ' '.join(doc[i].get_text() for i in range(min(8, doc.page_count)))
        m = PDF_NOMOR.search(re.sub(r'\s+', ' ', teks))
        return {
            'halaman': halaman,
            'nomor': m.group(1) if m else None,
            'tahun': m.group(2) if m else None,
            'identitas': f'{m.group(1)}/{m.group(2)}' if m else 'belum teridentifikasi',
        }
    except Exception:
        return {'halaman': 0, 'nomor': None, 'tahun': None,
                'identitas': 'gagal dibaca'}


def daftar_skkni() -> list[dict]:
    if not PDF_DIR.exists():
        return []
    hasil = []
    for p in sorted(PDF_DIR.glob('*.pdf')):
        info = _identitas_pdf(p)
        hasil.append({
            'nama': p.name,
            'ukuran_kb': round(p.stat().st_size / 1024),
            'halaman': info['halaman'],
            'nomor': info['nomor'],
            'tahun': info['tahun'],
            'identitas': info['identitas'],
        })
    return hasil


# --------------------------------------------------------------------------
# Skema sertifikasi (DOCX)
# --------------------------------------------------------------------------

def daftar_skema() -> list[dict]:
    if not SKEMA_DIR.exists():
        return []
    from app.schema_parser import baca_skema

    hasil = []
    for p in sorted(SKEMA_DIR.glob('*.docx')):
        entri = {
            'nama': p.name,
            'ukuran_kb': round(p.stat().st_size / 1024),
            'jumlah_unit': 0,
            'status': 'belum dibaca',
        }
        try:
            skema = baca_skema(p)
            entri['jumlah_unit'] = skema['jumlah_unit']
            entri['status'] = 'terbaca'
        except Exception:
            entri['status'] = 'perlu verifikasi'
        hasil.append(entri)
    return hasil


# --------------------------------------------------------------------------
# Unit kompetensi (JSON hasil ekstraksi)
# --------------------------------------------------------------------------

def _baca_unit(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    if not data.get('kode_unit'):
        return None
    meta = data.get('metadata_sumber') or {}
    elemen = data.get('elemen_kompetensi') or []
    return {
        'kode_unit': data['kode_unit'],
        'judul_unit': data.get('judul_unit') or '-',
        'sumber': meta.get('nama_dokumen') or '-',
        'elemen': len(elemen),
        'kuk': sum(len(e.get('kuk') or []) for e in elemen),
        'validasi': (data.get('validasi') or {}).get('status') or '-',
        'catatan': (data.get('validasi') or {}).get('catatan') or [],
        'berkas': str(path.relative_to(ROOT)),
        'diperbarui': datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec='minutes'),
    }


def daftar_unit() -> list[dict]:
    """Gabungkan unit dari semua JSON hasil ekstraksi, satu baris per kode."""
    kandidat: list[Path] = []
    for d in (SCHEMA_JSON_DIR, CROSS_JSON_DIR):
        if d.exists():
            kandidat.extend(sorted(d.glob('*.json')))
    if JSON_DIR.exists():
        kandidat.extend(sorted(JSON_DIR.glob('*unit*_complete*.json')))

    unik: dict[str, dict] = {}
    for p in kandidat:
        data = _baca_unit(p)
        if not data:
            continue
        # Prioritaskan hasil pipeline skema (folder schema_content_creator)
        if data['kode_unit'] in unik and SCHEMA_JSON_DIR not in p.parents:
            continue
        unik[data['kode_unit']] = data

    return sorted(unik.values(), key=lambda u: (u['sumber'], u['kode_unit']))


# --------------------------------------------------------------------------
# Hasil (output)
# --------------------------------------------------------------------------

def daftar_hasil() -> list[dict]:
    if not OUT_DIR.exists():
        return []
    hasil = []
    for p in sorted(OUT_DIR.rglob('*')):
        if not p.is_file() or p.suffix.lower() not in ('.docx', '.pdf', '.json'):
            continue
        if 'preview' in p.parts or 'tmp' in p.parts:
            continue
        hasil.append({
            'nama': p.name,
            'folder': str(p.parent.relative_to(ROOT)),
            'tipe': p.suffix.lstrip('.').upper(),
            'ukuran_kb': round(p.stat().st_size / 1024),
            'diperbarui': datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='minutes'),
        })
    return sorted(hasil, key=lambda x: x['diperbarui'], reverse=True)


# --------------------------------------------------------------------------
# Status sistem & modul
# --------------------------------------------------------------------------

MODUL_EKSTRAKTOR = (
    'app.extractor',
    'app.unit_parser',
    'app.section_parser',
    'app.docx_generator',
    'app.multi_docx_generator',
    'app.schema_parser',
    'app.unit_matcher',
    'app.schema_pipeline',
)


def status_modul() -> dict:
    import importlib

    hasil = {}
    for nama in MODUL_EKSTRAKTOR:
        try:
            importlib.import_module(nama)
            hasil[nama] = True
        except Exception:
            hasil[nama] = False
    return hasil


def status_sistem() -> list[dict]:
    modul = status_modul()

    pdf_ok = modul['app.extractor'] and modul['app.unit_parser']
    docx_ok = modul['app.docx_generator'] and modul['app.multi_docx_generator']
    simpan_ok = OUT_DIR.exists() and os.access(OUT_DIR, os.W_OK)

    try:
        import fastapi
        versi_fastapi = fastapi.__version__
    except Exception:
        versi_fastapi = 'tidak tersedia'

    return [
        {'nama': 'Backend FastAPI', 'status': 'aktif',
         'detail': f'FastAPI {versi_fastapi}'},
        {'nama': 'Mesin PDF Extractor', 'status': 'aktif' if pdf_ok else 'bermasalah',
         'detail': 'extractor + unit_parser' if pdf_ok else 'modul tidak dapat diimpor'},
        {'nama': 'Mesin DOCX Generator', 'status': 'aktif' if docx_ok else 'bermasalah',
         'detail': 'docx_generator + multi_docx_generator' if docx_ok
                   else 'modul tidak dapat diimpor'},
        {'nama': 'Direktori penyimpanan', 'status': 'siap' if simpan_ok else 'bermasalah',
         'detail': str(OUT_DIR.relative_to(ROOT)) if simpan_ok else 'tidak dapat ditulis'},
    ]


# --------------------------------------------------------------------------
# Aktivitas (dari laporan nyata)
# --------------------------------------------------------------------------

def aktivitas(limit: int = 6) -> list[dict]:
    sumber = [
        (OUT_DIR / 'laporan_content_creator.json', 'Ekstraksi skema sertifikasi'),
        (OUT_DIR / 'cross_skkni' / 'laporan_pengujian.json', 'Pengujian lintas SKKNI'),
    ]
    kegiatan = []
    for path, judul in sumber:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            continue
        waktu = data.get('dibuat') or datetime.fromtimestamp(
            path.stat().st_mtime).isoformat(timespec='seconds')
        ringkas = data.get('ringkasan') or {}
        if judul.startswith('Ekstraksi'):
            detail = (f"{ringkas.get('unit_diekstrak', 0)} unit, "
                      f"{ringkas.get('total_elemen', 0)} elemen, "
                      f"{ringkas.get('total_kuk', 0)} KUK")
        else:
            detail = (f"{ringkas.get('unit_diproses', 0)} unit, "
                      f"{ringkas.get('pemeriksaan_berhasil', 0)} pemeriksaan berhasil")
        kegiatan.append({'waktu': waktu, 'judul': judul, 'detail': detail,
                         'berkas': str(path.relative_to(ROOT))})

    kegiatan.sort(key=lambda x: x.get('waktu') or '', reverse=True)
    return kegiatan[:limit]


# --------------------------------------------------------------------------
# Ringkasan
# --------------------------------------------------------------------------

def ringkasan() -> dict:
    from app import library, schema_library
    library.pastikan_dokumen_proyek()
    skkni = library.daftar_dokumen()
    skema = schema_library.daftar_skema()
    unit = daftar_unit()
    hasil = daftar_hasil()
    return {
        'dokumen_skkni': len(skkni),
        'skema_sertifikasi': len(skema),
        'unit_kompetensi': len(unit),
        'hasil_ekstraksi': len([h for h in hasil if h['tipe'] in ('DOCX', 'PDF')]),
        'json_unit': len([h for h in hasil if h['tipe'] == 'JSON']),
    }


def dashboard_data() -> dict:
    return {
        'stats': ringkasan(),
        'sistem': status_sistem(),
        'modul': status_modul(),
        'aktivitas': aktivitas(),
        'dibuat': datetime.now().isoformat(timespec='seconds'),
    }

"""
SKKNI Extractor - Layanan pembuatan dokumen Word (Fase 4E).

Mengubah hasil ekstraksi (JSON Fase 4D/3D) menjadi DOCX memakai generator yang
sudah ada (`app/multi_docx_generator.py`). Tidak ada ekstraksi ulang dan tidak
ada parser baru: seluruh isi diambil dari JSON yang sudah tersimpan.
"""

import hashlib
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from app import penyimpanan
from app import jobs, koreksi, library, schema_library, status_units
from app.logging_config import ambil_logger
from app.multi_docx_generator import generate_multi_docx

logger = ambil_logger('document')

ROOT = Path(__file__).resolve().parents[2]   # app/services/ -> proyek
DOC_DIR = ROOT / 'output' / 'web_documents'
META_DIR = ROOT / 'data' / 'web_documents'

ID_POLA = re.compile(r'^[0-9a-f]{32}$')

STATUS_SIAP = 'siap_ditinjau'
STATUS_DRAFT = 'draft_perlu_verifikasi'
STATUS_GAGAL = 'gagal'


class GalatDokumen(Exception):
    """Kesalahan aman untuk pengguna."""

    def __init__(self, pesan, kode=400, masalah=None):
        super().__init__(pesan)
        self.pesan = pesan
        self.kode = kode
        self.masalah = masalah or []


# --------------------------------------------------------------------------
# Utilitas
# --------------------------------------------------------------------------

def siapkan_direktori() -> None:
    penyimpanan.pastikan_direktori((DOC_DIR, META_DIR))


_tulis_atomik = penyimpanan.tulis_json_atomik


def _sekarang() -> str:
    return datetime.now().isoformat(timespec='seconds')


_baca = penyimpanan.baca_json


_sha256 = penyimpanan.sha256_berkas


def _peta_pdf() -> dict[str, Path]:
    peta = {p.name: p for p in (ROOT / 'data' / 'pdf').glob('*.pdf')}
    for d in library.daftar_dokumen():
        internal = d.get('nama_internal')
        if internal:
            p = ROOT / internal
            if p.exists():
                peta[p.name] = p
    return peta


# --------------------------------------------------------------------------
# Sumber JSON hasil ekstraksi
# --------------------------------------------------------------------------

def _cari_json(kode: str) -> Path | None:
    for folder in (jobs.JSON_OUT,
                   ROOT / 'data' / 'json' / 'schema_content_creator',
                   ROOT / 'data' / 'json' / 'cross_skkni'):
        p = folder / f'{kode}.json'
        if p.exists():
            return p
    return None


def unit_tersedia(schema_id: str) -> list[dict]:
    """Unit skema yang sudah punya JSON ekstraksi (untuk ditampilkan di UI)."""
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return []
    peta = schema_library.peta_kelengkapan()
    hasil = []
    for u in dok.get('units') or []:
        kode = u['kode_unit']
        path = _cari_json(kode)
        st = schema_library.status_unit(dok, kode, peta)
        hasil.append({
            'kode_unit': kode,
            'judul': u.get('judul_skema'),
            'nomor_urut': u.get('nomor_urut'),
            'ada_json': bool(path),
            'status': st,
        })
    return hasil


# --------------------------------------------------------------------------
# Validasi sebelum generate
# --------------------------------------------------------------------------

def validasi(schema_id: str, kode_list: list[str] | None = None) -> dict:
    """
    Periksa kesiapan unit sebelum DOCX dibuat.

    Returns:
        dict: {'lengkap': bool, 'masalah': [...], 'unit': [...]}
    """
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        raise GalatDokumen('Skema tidak ditemukan.', 404)

    urutan_skema = {u['kode_unit']: u for u in dok.get('units') or []}
    dipilih = list(kode_list) if kode_list else [u['kode_unit'] for u in dok.get('units') or []]

    if not dipilih:
        raise GalatDokumen('Tidak ada unit yang dipilih.', 400)
    if len(set(dipilih)) != len(dipilih):
        raise GalatDokumen('Daftar unit mengandung kode duplikat.', 400)

    asing = [k for k in dipilih if k not in urutan_skema]
    if asing:
        raise GalatDokumen('Kode unit tidak berasal dari skema ini: ' + ', '.join(asing), 400)

    pencocokan = (dok.get('hasil_pencocokan') or {}).get('units') or {}
    manual = dok.get('verifikasi_manual') or {}
    peta_pdf = _peta_pdf()
    sha_library = {}
    for d in library.daftar_dokumen():
        internal = d.get('nama_internal')
        if internal:
            sha_library[Path(internal).name] = d.get('sha256')

    masalah = []
    units = []

    for kode in dipilih:
        u_skema = urutan_skema[kode]
        cocok = pencocokan.get(kode) or {}
        path_json = _cari_json(kode)
        info_kor = koreksi.status_koreksi(kode)
        ada_koreksi = bool(info_kor.get('ada_koreksi'))
        konflik_koreksi = bool(info_kor.get('konflik'))
        koreksi_aktif = ada_koreksi and not konflik_koreksi

        entri = {
            'kode_unit': kode,
            'judul': u_skema.get('judul_skema'),
            'nomor_urut': u_skema.get('nomor_urut'),
            'pdf': cocok.get('pdf'),
            'halaman_pdf_0based': cocok.get('start_page'),
            'json': None,
            'struktur': None,
            'kelengkapan': None,
            'sha256_pdf': None,
            'dikoreksi_manual': koreksi_aktif,
            'konflik_koreksi': konflik_koreksi,
        }

        if not path_json and not ada_koreksi:
            masalah.append({'kode': kode, 'jenis': 'json_tidak_ada',
                            'pesan': 'JSON hasil ekstraksi belum tersedia.'})
            units.append(entri)
            continue

        if path_json:
            data = _baca(path_json)
            if not data and not ada_koreksi:
                masalah.append({'kode': kode, 'jenis': 'json_rusak',
                                'pesan': 'Berkas JSON tidak dapat dibaca.'})
                units.append(entri)
                continue
            entri['json'] = str(path_json.relative_to(ROOT))
        else:
            data = None
            entri['json'] = str(koreksi.path_koreksi(kode).relative_to(ROOT))

        if ada_koreksi:
            data = koreksi.terapkan_koreksi_ke_data(data, kode)

        if not data:
            masalah.append({'kode': kode, 'jenis': 'json_rusak',
                            'pesan': 'Berkas JSON tidak dapat dibaca.'})
            units.append(entri)
            continue

        entri['judul'] = data.get('judul_unit') or entri['judul']

        if not data.get('kode_unit') or not (data.get('judul_unit') or entri['judul']):
            masalah.append({'kode': kode, 'jenis': 'identitas',
                            'pesan': 'Kode atau judul unit tidak lengkap pada JSON.'})

        elemen = data.get('elemen_kompetensi') or []
        total_kuk = sum(len(e.get('kuk') or []) for e in elemen)
        entri['elemen'] = len(elemen)
        entri['kuk'] = total_kuk
        if not elemen or not total_kuk:
            masalah.append({'kode': kode, 'jenis': 'struktur',
                            'pesan': 'Elemen Kompetensi atau KUK tidak tersedia.'})

        if konflik_koreksi:
            masalah.append({'kode': kode, 'jenis': 'konflik_koreksi',
                            'pesan': 'Hasil mesin berubah sejak dikoreksi manual; perlu peninjauan ulang.'})

        # Verifikasi manual atau koreksi manual aktif menyelesaikan temuan validasi
        sudah_manual = (kode in manual) or koreksi_aktif
        entri['terverifikasi_manual'] = sudah_manual
        entri['waktu_manual'] = (
            info_kor.get('dikoreksi_pada')
            if koreksi_aktif
            else ((manual.get(kode) or {}).get('waktu') if kode in manual else None)
        )

        status_struktur = 'valid_struktur' if koreksi_aktif else (data.get('validasi') or {}).get('status')
        entri['struktur'] = status_struktur
        if status_struktur != 'valid_struktur':
            if sudah_manual:
                entri['struktur_manual'] = True
            else:
                masalah.append({'kode': kode, 'jenis': 'validasi_struktur',
                                'pesan': f'Validasi struktur: {status_struktur or "belum dijalankan"}.'})

        kelengkapan = 'valid_kelengkapan' if koreksi_aktif else (data.get('validasi_kelengkapan') or {}).get('status')
        entri['kelengkapan'] = kelengkapan
        hilang = [] if koreksi_aktif else ((data.get('validasi_kelengkapan') or {}).get('kuk_hilang') or [])
        if kelengkapan != 'valid_kelengkapan' and not sudah_manual:
            masalah.append({'kode': kode, 'jenis': 'validasi_kelengkapan',
                            'pesan': f'Validasi kelengkapan KUK: {kelengkapan or "belum dijalankan"}.'})
        if hilang:
            masalah.append({'kode': kode, 'jenis': 'kuk_hilang',
                            'pesan': 'Nomor KUK hilang: ' + ', '.join(hilang) + '.'})

        if cocok.get('status') == 'konflik':
            masalah.append({'kode': kode, 'jenis': 'konflik_sumber',
                            'pesan': 'Kode ditemukan di lebih dari satu PDF; perlu verifikasi.'})
        if not cocok.get('pdf'):
            masalah.append({'kode': kode, 'jenis': 'sumber_pdf',
                            'pesan': 'Sumber PDF SKKNI belum ditentukan.'})

        pdf = peta_pdf.get(cocok.get('pdf') or '')
        if pdf and cocok.get('pdf'):
            sha = _sha256(pdf)
            entri['sha256_pdf'] = sha
            acuan = sha_library.get(pdf.name)
            if acuan and acuan != sha:
                masalah.append({'kode': kode, 'jenis': 'hash_sumber',
                                'pesan': 'Hash PDF sumber berbeda dengan metadata perpustakaan.'})

        units.append(entri)

    # Urutan sesuai dokumen skema
    units.sort(key=lambda x: x.get('nomor_urut') or 0)

    return {'lengkap': not masalah, 'masalah': masalah, 'unit': units}


# --------------------------------------------------------------------------
# Generate
# --------------------------------------------------------------------------

def buat_dokumen(schema_id: str, kode_list: list[str] | None = None,
                 setujui_draft: bool = False) -> dict:
    siapkan_direktori()
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        raise GalatDokumen('Skema tidak ditemukan.', 404)

    periksa = validasi(schema_id, kode_list)
    masalah_gagal = [
        m for m in periksa['masalah']
        if m.get('jenis') in ('json_tidak_ada', 'json_rusak', 'struktur')
    ]
    if masalah_gagal:
        daftar_kode = ', '.join(sorted({m['kode'] for m in masalah_gagal}))
        raise GalatDokumen(
            f'Dokumen tidak dapat dibuat karena ada unit berstatus Gagal ({daftar_kode}): '
            'Elemen Kompetensi atau KUK belum terbaca.',
            409,
            periksa['masalah'],
        )
    if not periksa['lengkap'] and not setujui_draft:
        raise GalatDokumen(
            'Dokumen belum dapat dibuat final karena ada unit yang perlu diperiksa. '
            'Buat sebagai draft bila tetap ingin melanjutkan.',
            409, periksa['masalah'])

    unit_terpilih = [u for u in periksa['unit'] if u.get('json')]
    if not unit_terpilih:
        raise GalatDokumen('Tidak ada unit dengan JSON yang dapat dijadikan dokumen.', 409,
                           periksa['masalah'])

    did = uuid.uuid4().hex
    tujuan = DOC_DIR / f'{did}.docx'

    spesifikasi = [{'kode': u['kode_unit'], 'json': str(ROOT / u['json'])}
                   for u in unit_terpilih]

    status = STATUS_SIAP if periksa['lengkap'] else STATUS_DRAFT

    try:
        hasil = generate_multi_docx(spesifikasi, str(tujuan))
    except Exception as e:
        logger.error(f"Gagal generate multi-docx untuk skema {schema_id}: {e}", exc_info=True)
        gagal = {
            'id': did,
            'schema_id': schema_id,
            'nama_skema': dok.get('nama_skema'),
            'dibuat': _sekarang(),
            'status': STATUS_GAGAL,
            'pesan': f'Gagal membuat DOCX: {type(e).__name__}',
            'jumlah_unit': len(unit_terpilih),
            'units': [{'kode_unit': u['kode_unit']} for u in unit_terpilih],
            'berkas_docx': None,
        }
        _tulis_atomik(META_DIR / f'{did}.json', gagal)
        raise GalatDokumen('Pembuatan dokumen Word gagal. Periksa data unit.', 500)

    meta = {
        'id': did,
        'schema_id': schema_id,
        'nama_skema': dok.get('nama_skema'),
        'nama_asli': f"Skema {dok.get('nama_skema') or schema_id}",
        'dibuat': _sekarang(),
        'status': status,
        'persetujuan_draft': bool(setujui_draft and not periksa['lengkap']),
        'jumlah_unit': hasil['jumlah_unit'],
        'total_elemen': hasil['total_elemen'],
        'total_kuk': hasil['total_kuk'],
        'units': [{
            'kode_unit': u['kode_unit'],
            'judul_unit': u.get('judul'),
            'nomor_urut': u.get('nomor_urut'),
            'sumber_skkni': u.get('pdf'),
            'halaman_pdf_0based': u.get('halaman_pdf_0based'),
            'sha256_pdf': u.get('sha256_pdf'),
            'json': u.get('json'),
            'validasi_struktur': u.get('struktur'),
            'validasi_kelengkapan': u.get('kelengkapan'),
            'terverifikasi_manual': bool(u.get('terverifikasi_manual')),
            'waktu_verifikasi_manual': u.get('waktu_manual'),
        } for u in unit_terpilih],
        'masalah': periksa['masalah'],
        'berkas_docx': str(tujuan.relative_to(ROOT)),
        'ukuran_byte': tujuan.stat().st_size,
        'urutan_kode': hasil['urutan_kode'],
    }
    _tulis_atomik(META_DIR / f'{did}.json', meta)
    logger.info(f"Dokumen DOCX berhasil dibuat: id={did}, skema={dok.get('nama_skema')}, unit={hasil['jumlah_unit']}, status={status}")
    return meta


# --------------------------------------------------------------------------
# Riwayat & berkas
# --------------------------------------------------------------------------

def daftar_dokumen(limit: int = 50) -> list[dict]:
    if not META_DIR.exists():
        return []
    hasil = []
    for p in META_DIR.glob('*.json'):
        d = _baca(p)
        if d and d.get('id'):
            hasil.append(d)
    hasil.sort(key=lambda d: d.get('dibuat') or '', reverse=True)
    return hasil[:limit]


def ambil_dokumen(dok_id: str) -> dict | None:
    if not ID_POLA.match(dok_id or ''):
        return None
    return _baca(META_DIR / f'{dok_id}.json')


def jalur_docx(meta: dict) -> Path:
    """Path absolut DOCX; hanya untuk berkas yang terdaftar dan di dalam proyek."""
    rel = meta.get('berkas_docx')
    if not rel:
        raise GalatDokumen('Dokumen ini tidak memiliki berkas.', 404)
    target = (ROOT / rel).resolve()
    if DOC_DIR.resolve() not in target.parents:
        raise GalatDokumen('Lokasi berkas tidak sah.', 400)
    if not target.exists():
        raise GalatDokumen('Berkas DOCX tidak ditemukan.', 404)
    return target


def nama_unduhan(meta: dict) -> str:
    judul = meta.get('nama_skema') or 'SKKNI'
    aman = re.sub(r'[^A-Za-z0-9]+', '-', judul).strip('-') or 'SKKNI'
    return f'{aman} - {meta["jumlah_unit"]} Unit.docx'

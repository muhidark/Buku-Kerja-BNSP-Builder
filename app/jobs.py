"""
SKKNI Extractor - Job manager ekstraksi dari browser (Fase 4D).

Alur: skema -> pilih unit -> job -> mesin ekstraksi -> validasi KUK ->
JSON -> preview -> status.

Job berjalan di thread latar belakang (maksimum 2 bersamaan) dan statusnya
disimpan ke `data/jobs/<id>.json` secara atomik, sehingga progres tetap
terbaca meski halaman ditutup atau server dijalankan ulang.
"""

import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from app import library, schema_library
from app.logging_config import ambil_logger
from app.kuk_completeness_validator import periksa_unit
from app.section_parser import flatten_nodes
from app.unit_parser import parse_unit

logger = ambil_logger('jobs')

ROOT = Path(__file__).resolve().parent.parent
JOBS_DIR = ROOT / 'data' / 'jobs'
JSON_OUT = ROOT / 'data' / 'json' / 'browser_extraction'

PELAKSANA = ThreadPoolExecutor(max_workers=2, thread_name_prefix='ekstraksi')
_KUNCI = threading.Lock()


class GalatJob(Exception):
    def __init__(self, pesan, kode=400):
        super().__init__(pesan)
        self.pesan = pesan
        self.kode = kode


# --------------------------------------------------------------------------
# Utilitas
# --------------------------------------------------------------------------

def siapkan_direktori() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.mkdir(parents=True, exist_ok=True)


def _tulis_atomik(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _sekarang() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _baca(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


# --------------------------------------------------------------------------
# Lokasi PDF sumber
# --------------------------------------------------------------------------

def _peta_pdf() -> dict[str, Path]:
    """Nama berkas PDF (yang dipakai unit_matcher) -> path sebenarnya."""
    peta = {}
    for p in (ROOT / 'data' / 'pdf').glob('*.pdf'):
        peta[p.name] = p
    for d in library.daftar_dokumen():
        internal = d.get('nama_internal')
        if internal:
            p = ROOT / internal
            if p.exists():
                peta[p.name] = p
    return peta


# --------------------------------------------------------------------------
# Pembuatan job
# --------------------------------------------------------------------------

def buat_job(skema_doc: dict, kode_unit: str | None = None) -> dict:
    """Buat job untuk satu unit (kode_unit) atau seluruh unit (None/'')."""
    siapkan_direktori()
    units = skema_doc.get('units') or []
    if not units:
        raise GalatJob('Skema ini tidak memiliki daftar unit untuk diekstrak.', 409)

    pencocokan = (skema_doc.get('hasil_pencocokan') or {}).get('units') or {}

    if kode_unit:
        target = [u for u in units if u['kode_unit'] == kode_unit]
        if not target:
            raise GalatJob('Kode unit tidak ada pada skema ini.', 404)
    else:
        target = units

    jid = uuid.uuid4().hex
    job = {
        'id': jid,
        'schema_id': skema_doc['id'],
        'nama_skema': skema_doc.get('nama_skema') or skema_doc.get('nama_asli'),
        'mode': 'satu_unit' if kode_unit else 'seluruh_unit',
        'dibuat': _sekarang(),
        'selesai': None,
        'status': 'menunggu',
        'progress': {'total': len(target), 'selesai': 0, 'gagal': 0},
        'units': [],
        'pesan': None,
    }

    for u in target:
        kode = u['kode_unit']
        cocok = pencocokan.get(kode) or {}
        job['units'].append({
            'kode_unit': kode,
            'judul_skema': u.get('judul_skema'),
            'status': 'menunggu',
            'pdf': cocok.get('pdf'),
            'halaman_pdf_0based': cocok.get('start_page'),
            'halaman_akhir_0based': cocok.get('end_page'),
            'elemen': 0,
            'kuk': 0,
            'validasi_struktur': None,
            'validasi_kelengkapan': None,
            'berkas': None,
            'pesan': None,
        })

    _tulis_atomik(JOBS_DIR / f'{jid}.json', job)
    logger.info(f"Job ekstraksi dibuat: id={jid}, skema={skema_doc.get('nama_skema')}, target={len(target)} unit")
    PELAKSANA.submit(_jalankan, job['id'])
    return job


# --------------------------------------------------------------------------
# Pekerja
# --------------------------------------------------------------------------

def _jalankan(job_id: str) -> None:
    job = ambil_job(job_id)
    if not job:
        return

    logger.info(f"Job {job_id} dimulai.")
    job['status'] = 'berjalan'
    job['mulai'] = _sekarang()
    _simpan(job)

    peta = _peta_pdf()

    for entri in job['units']:
        entri['status'] = 'berjalan'
        _simpan(job)
        try:
            _proses_unit(entri, peta)
            entri['status'] = 'selesai'
            job['progress']['selesai'] += 1
            logger.info(f"Job {job_id}: Unit {entri['kode_unit']} berhasil diekstrak.")
        except GalatJob as e:
            entri['status'] = 'gagal'
            entri['pesan'] = e.pesan
            job['progress']['gagal'] += 1
            logger.warning(f"Job {job_id}: Unit {entri['kode_unit']} gagal: {e.pesan}")
        except Exception as e:
            entri['status'] = 'gagal'
            entri['pesan'] = f'Kesalahan internal: {type(e).__name__}'
            job['progress']['gagal'] += 1
            logger.error(f"Job {job_id}: Unit {entri['kode_unit']} mengalami kesalahan internal: {e}", exc_info=True)
        _simpan(job)

    job['status'] = 'gagal' if job['progress']['gagal'] == job['progress']['total'] else 'selesai'
    if job['progress']['gagal'] and job['progress']['selesai']:
        job['status'] = 'selesai_sebagian'
    job['selesai'] = _sekarang()
    _simpan(job)
    logger.info(f"Job {job_id} selesai: status={job['status']}, selesai={job['progress']['selesai']}, gagal={job['progress']['gagal']}.")


def _proses_unit(entri: dict, peta_pdf: dict) -> None:
    kode = entri['kode_unit']
    pdf_name = entri.get('pdf')
    if not pdf_name:
        raise GalatJob('Kode unit belum ditemukan pada PDF SKKNI yang tersedia.')

    pdf = peta_pdf.get(pdf_name)
    if not pdf or not pdf.exists():
        raise GalatJob(f'PDF sumber tidak ditemukan: {pdf_name}')

    start = entri.get('halaman_pdf_0based')
    end = entri.get('halaman_akhir_0based')
    if start is None:
        raise GalatJob('Rentang halaman unit tidak tersedia pada metadata pencocokan.')

    data = parse_unit(str(pdf), kode, int(start), int(end or start))

    kuk_nomor = [k['nomor_kuk'] for e in data.get('elemen_kompetensi') or []
                 for k in e.get('kuk') or []]

    if kuk_nomor:
        lengkap = periksa_unit(pdf, kode, int(start), int(end or start), kuk_nomor)
    else:
        lengkap = {'status': 'perlu_verifikasi',
                   'catatan': ['Tidak ada KUK yang dapat dibandingkan.'],
                   'kuk_pdf': [], 'kuk_hilang': [], 'kuk_ekstra': [], 'duplikat': []}

    data['validasi_kelengkapan'] = {
        'status': lengkap['status'],
        'kuk_pdf': lengkap.get('kuk_pdf', []),
        'kuk_json': sorted(kuk_nomor),
        'kuk_hilang': lengkap.get('kuk_hilang', []),
        'kuk_ekstra': lengkap.get('kuk_ekstra', []),
        'duplikat': lengkap.get('duplikat', []),
        'catatan': lengkap.get('catatan', []),
        'diperiksa_pada': _sekarang(),
        'metode': 'validator independen (find_tables + kata)',
    }
    data['sumber_ekstraksi'] = {
        'aplikasi': 'SKKNI Extractor',
        'jalur': 'browser (job manager)',
        'waktu': _sekarang(),
    }

    siapkan_direktori()
    tujuan = JSON_OUT / f'{kode}.json'
    _tulis_atomik(tujuan, data)

    entri['elemen'] = len(data.get('elemen_kompetensi') or [])
    entri['kuk'] = len(kuk_nomor)
    entri['validasi_struktur'] = (data.get('validasi') or {}).get('status')
    entri['catatan'] = (data.get('validasi') or {}).get('catatan') or []
    entri['validasi_kelengkapan'] = lengkap['status']
    entri['berkas'] = str(tujuan.relative_to(ROOT))

    BV = data.get('batasan_variabel') or {}
    PP = data.get('panduan_penilaian') or {}
    entri['batasan_variabel'] = len(flatten_nodes(BV.get('sections') or []))
    entri['panduan_penilaian'] = len(flatten_nodes(PP.get('sections') or []))


# --------------------------------------------------------------------------
# Baca status
# --------------------------------------------------------------------------

def _simpan(job: dict) -> None:
    with _KUNCI:
        job['diperbarui'] = _sekarang()
        _tulis_atomik(JOBS_DIR / f"{job['id']}.json", job)


def ambil_job(job_id: str) -> dict | None:
    if not job_id or len(job_id) != 32:
        return None
    return _baca(JOBS_DIR / f'{job_id}.json')


def daftar_job(limit: int = 20) -> list[dict]:
    if not JOBS_DIR.exists():
        return []
    hasil = []
    for p in JOBS_DIR.glob('*.json'):
        d = _baca(p)
        if d and d.get('id'):
            hasil.append(d)
    hasil.sort(key=lambda d: d.get('dibuat') or '', reverse=True)
    return hasil[:limit]


def pulihkan_job_macet() -> int:
    """Tandai job 'berjalan' yang tertinggal (server berhenti) sebagai terputus."""
    n = 0
    if not JOBS_DIR.exists():
        return n
    for p in JOBS_DIR.glob('*.json'):
        d = _baca(p)
        if d and d.get('status') in ('berjalan', 'menunggu'):
            d['status'] = 'terputus'
            d['pesan'] = 'Job terhenti karena aplikasi dimulai ulang.'
            d['selesai'] = _sekarang()
            _tulis_atomik(p, d)
            n += 1
    return n

"""
SKKNI Extractor - Perpustakaan PDF SKKNI (Fase 4B).

Menyimpan PDF unggahan di dalam proyek, metadata JSON (tanpa database),
dan menjalankan identifikasi unit memakai mesin Fase 1 yang sudah ada.

Prinsip:
- Nama berkas internal = ID acak, bukan nama asli (aman dari path traversal).
- Deteksi duplikat memakai SHA-256.
- Penulisan metadata atomik (tulis sementara lalu os.replace).
- Hanya menerima PDF yang lolos validasi signature, struktur, dan enkripsi.
"""

import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB_DIR = ROOT / 'data' / 'library'
PDF_STORE = LIB_DIR / 'pdf'
META_DIR = LIB_DIR / 'documents'
TMP_DIR = LIB_DIR / 'tmp'

BATAS_UKURAN = 50 * 1024 * 1024          # 50 MB
ID_POLA = re.compile(r'^[0-9a-f]{32}$')
NOMOR_TAHUN = re.compile(r'NOMOR\s+(\d+)\s+TAHUN\s+(\d{4})')
JUDUL_SKKNI = re.compile(
    r'STANDAR\s+KOMPETENSI\s+KERJA\s+NASIONAL\s+INDONESIA\s+KATEGORI\s+(.{3,120}?)'
    r'(?:\s+GOLONGAN|\s+SUB\s+GOLONGAN|\s+BIDANG)', re.I | re.S)


class GalatUpload(Exception):
    """Kesalahan yang aman ditampilkan ke pengguna."""

    def __init__(self, pesan, kode=400):
        super().__init__(pesan)
        self.pesan = pesan
        self.kode = kode


# --------------------------------------------------------------------------
# Utilitas berkas
# --------------------------------------------------------------------------

def siapkan_direktori() -> None:
    for d in (PDF_STORE, META_DIR, TMP_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _tulis_json_atomik(path: Path, data: dict) -> None:
    sementara = path.with_suffix(path.suffix + '.tmp')
    with open(sementara, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(sementara, path)


def _baca_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def _sha256_berkas(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for potong in iter(lambda: f.read(1024 * 1024), b''):
            h.update(potong)
    return h.hexdigest()


# --------------------------------------------------------------------------
# Validasi PDF
# --------------------------------------------------------------------------

def validasi_pdf(path: Path) -> dict:
    """Periksa signature, struktur, dan enkripsi. Mengembalikan info halaman."""
    with open(path, 'rb') as f:
        awal = f.read(1024)
        f.seek(max(0, path.stat().st_size - 2048))
        akhir = f.read()

    if b'%PDF-' not in awal[:16]:
        raise GalatUpload('Berkas bukan PDF yang sah (signature tidak ditemukan).')
    if b'%%EOF' not in akhir:
        raise GalatUpload('Struktur PDF tidak lengkap (penanda akhir berkas tidak ada).')

    import pymupdf as fitz

    try:
        doc = fitz.open(str(path))
    except Exception:
        raise GalatUpload('PDF tidak dapat dibuka; kemungkinan rusak.')

    try:
        if doc.needs_pass or doc.is_encrypted:
            raise GalatUpload('PDF terenkripsi dan memerlukan kata sandi.')
        if doc.page_count < 1:
            raise GalatUpload('PDF tidak memiliki halaman yang dapat dibaca.')
        # Coba baca halaman pertama agar PDF rusak terdeteksi lebih awal.
        _ = doc[0].get_text()
        halaman = doc.page_count
    except GalatUpload:
        raise
    except Exception:
        raise GalatUpload('Isi PDF tidak dapat dibaca; berkas mungkin rusak.')
    finally:
        doc.close()

    return {'halaman': halaman}


def baca_identitas(path: Path) -> dict:
    """Ambil nomor, tahun, dan judul SKKNI dari halaman awal (tanpa mengarang)."""
    import pymupdf as fitz

    hasil = {'nomor': None, 'tahun': None, 'judul': None}
    try:
        with fitz.open(str(path)) as doc:
            teks = ' '.join(doc[i].get_text() for i in range(min(8, doc.page_count)))
    except Exception:
        return hasil

    teks_rapi = re.sub(r'\s+', ' ', teks)
    m = NOMOR_TAHUN.search(teks_rapi)
    if m:
        hasil['nomor'], hasil['tahun'] = m.group(1), m.group(2)

    j = JUDUL_SKKNI.search(teks)
    if j:
        judul = re.sub(r'\s+', ' ', j.group(1)).strip(' .-')
        if 3 <= len(judul) <= 120:
            hasil['judul'] = judul
    return hasil


# --------------------------------------------------------------------------
# Metadata
# --------------------------------------------------------------------------

def _lokasi_metadata(doc_id: str) -> Path:
    if not ID_POLA.match(doc_id or ''):
        raise GalatUpload('ID dokumen tidak sah.', 404)
    return META_DIR / f'{doc_id}.json'


def daftar_dokumen() -> list[dict]:
    if not META_DIR.exists():
        return []
    hasil = []
    for p in META_DIR.glob('*.json'):
        data = _baca_json(p)
        if data and data.get('id'):
            hasil.append(data)
    hasil.sort(key=lambda d: d.get('tanggal_ditambah') or '', reverse=True)
    return hasil


def ambil_dokumen(doc_id: str) -> dict | None:
    try:
        path = _lokasi_metadata(doc_id)
    except GalatUpload:
        return None
    return _baca_json(path)


def simpan_metadata(doc: dict) -> None:
    doc['diperbarui'] = datetime.now().isoformat(timespec='seconds')
    _tulis_json_atomik(_lokasi_metadata(doc['id']), doc)


def jalur_pdf(doc: dict) -> Path:
    """Path absolut PDF; ditolak bila keluar dari direktori proyek."""
    target = (ROOT / doc['nama_internal']).resolve()
    if ROOT.resolve() not in target.parents:
        raise GalatUpload('Lokasi dokumen tidak sah.', 400)
    if not target.exists():
        raise GalatUpload('Berkas PDF tidak ditemukan.', 404)
    return target


# --------------------------------------------------------------------------
# Identifikasi unit (mesin Fase 1)
# --------------------------------------------------------------------------

def identifikasi(doc: dict) -> dict:
    """Jalankan identify_units dan simpan ringkasan ke metadata."""
    from app.extractor import identify_units

    path = jalur_pdf(doc)
    try:
        units = identify_units(str(path))
        daftar = []
        for u in units:
            judul = (u.get('title') or '').strip() or None
            daftar.append({
                'nomor': len(daftar) + 1,
                'kode_unit': u['code'],
                'judul_unit': judul,
                'halaman_pdf_0based': u['start_page'],
                'halaman_akhir_0based': u['end_page'],
                'halaman_tampil': u['start_page'] + 1,
                'status': 'teridentifikasi' if judul else 'perlu_verifikasi',
            })
        doc['units'] = daftar
        doc['jumlah_unit'] = len(daftar)
        doc['jumlah_unit_teridentifikasi'] = sum(1 for u in daftar
                                                 if u['status'] == 'teridentifikasi')
        doc['jumlah_unit_perlu_verifikasi'] = sum(1 for u in daftar
                                                  if u['status'] != 'teridentifikasi')
        if not daftar:
            doc['status_identifikasi'] = 'perlu_verifikasi'
            doc['pesan_identifikasi'] = 'Tidak ada kode unit yang dikenali pada PDF.'
        elif doc['jumlah_unit_perlu_verifikasi']:
            doc['status_identifikasi'] = 'perlu_verifikasi'
            doc['pesan_identifikasi'] = (
                f"{doc['jumlah_unit_perlu_verifikasi']} unit tidak memiliki judul "
                'yang dapat dibaca.')
        else:
            doc['status_identifikasi'] = 'lengkap'
            doc['pesan_identifikasi'] = None
    except Exception as e:
        doc['units'] = doc.get('units') or []
        doc['jumlah_unit'] = len(doc['units'])
        doc['jumlah_unit_teridentifikasi'] = 0
        doc['jumlah_unit_perlu_verifikasi'] = len(doc['units'])
        doc['status_identifikasi'] = 'perlu_verifikasi'
        doc['pesan_identifikasi'] = f'Identifikasi gagal: {type(e).__name__}'

    doc['identifikasi_pada'] = datetime.now().isoformat(timespec='seconds')
    simpan_metadata(doc)
    return doc


# --------------------------------------------------------------------------
# Unggah
# --------------------------------------------------------------------------

def unggah(nama_asli: str, aliran, ukuran_dilaporkan: int | None = None) -> tuple[dict, bool]:
    """
    Simpan PDF unggahan. Mengembalikan (metadata, duplikat).

    `aliran` adalah file-like objek dari UploadFile.
    """
    siapkan_direktori()

    if ukuran_dilaporkan and ukuran_dilaporkan > BATAS_UKURAN:
        raise GalatUpload(f'Ukuran berkas melebihi batas {BATAS_UKURAN // (1024 * 1024)} MB.',
                         413)

    nama_bersih = Path(nama_asli or 'dokumen.pdf').name
    if not nama_bersih.lower().endswith('.pdf'):
        raise GalatUpload('Hanya berkas PDF yang diterima.')

    doc_id = uuid.uuid4().hex
    sementara = TMP_DIR / f'{doc_id}.part'
    h = hashlib.sha256()
    total = 0

    try:
        with open(sementara, 'wb') as f:
            while True:
                potong = aliran.read(1024 * 1024)
                if not potong:
                    break
                total += len(potong)
                if total > BATAS_UKURAN:
                    raise GalatUpload(
                        f'Ukuran berkas melebihi batas {BATAS_UKURAN // (1024 * 1024)} MB.',
                        413)
                h.update(potong)
                f.write(potong)
            f.flush()
            os.fsync(f.fileno())

        if total == 0:
            raise GalatUpload('Berkas kosong.')

        info = validasi_pdf(sementara)
        sha = h.hexdigest()

        # Duplikat?
        for ada in daftar_dokumen():
            if ada.get('sha256') == sha:
                sementara.unlink(missing_ok=True)
                return ada, True

        tujuan = PDF_STORE / f'{doc_id}.pdf'
        os.replace(sementara, tujuan)

        identitas = baca_identitas(tujuan)
        doc = {
            'id': doc_id,
            'nama_asli': nama_bersih,
            'nama_internal': str(tujuan.relative_to(ROOT)),
            'sumber': 'unggahan',
            'sha256': sha,
            'ukuran_byte': total,
            'nomor': identitas['nomor'],
            'tahun': identitas['tahun'],
            'judul': identitas['judul'],
            'halaman': info['halaman'],
            'tanggal_ditambah': datetime.now().isoformat(timespec='seconds'),
            'status_identifikasi': 'belum_diproses',
            'units': [],
            'jumlah_unit': 0,
            'jumlah_unit_teridentifikasi': 0,
            'jumlah_unit_perlu_verifikasi': 0,
            'validasi_kelengkapan': None,
        }
        if not identitas['nomor'] or not identitas['tahun']:
            doc['status_identifikasi'] = 'perlu_verifikasi'
            doc['pesan_identifikasi'] = ('Nomor/tahun SKKNI tidak dapat dibaca dari '
                                         'halaman awal dokumen.')

        simpan_metadata(doc)
        return identifikasi(doc), False

    finally:
        sementara.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Dokumen bawaan proyek (data/pdf)
# --------------------------------------------------------------------------

def daftar_pdf_proyek() -> list[Path]:
    folder = ROOT / 'data' / 'pdf'
    return sorted(folder.glob('*.pdf')) if folder.exists() else []


def pastikan_dokumen_proyek() -> int:
    """Daftarkan PDF di data/pdf yang belum ada di perpustakaan (tanpa menyalin)."""
    siapkan_direktori()
    dikenal = {d.get('sha256') for d in daftar_dokumen()}
    baru = 0
    for p in daftar_pdf_proyek():
        try:
            sha = _sha256_berkas(p)
        except Exception:
            continue
        if sha in dikenal:
            continue
        doc_id = hashlib.sha256(('proyek:' + p.name).encode()).hexdigest()[:32]
        if _lokasi_metadata(doc_id).exists():
            continue
        identitas = baca_identitas(p)
        info = {'halaman': 0}
        try:
            info = validasi_pdf(p)
        except GalatUpload:
            pass
        doc = {
            'id': doc_id,
            'nama_asli': p.name,
            'nama_internal': str(p.relative_to(ROOT)),
            'sumber': 'proyek',
            'sha256': sha,
            'ukuran_byte': p.stat().st_size,
            'nomor': identitas['nomor'],
            'tahun': identitas['tahun'],
            'judul': identitas['judul'],
            'halaman': info['halaman'],
            'tanggal_ditambah': datetime.fromtimestamp(
                p.stat().st_mtime).isoformat(timespec='seconds'),
            'status_identifikasi': 'belum_diproses',
            'units': [],
            'jumlah_unit': 0,
            'jumlah_unit_teridentifikasi': 0,
            'jumlah_unit_perlu_verifikasi': 0,
            'validasi_kelengkapan': None,
        }
        simpan_metadata(doc)
        dikenal.add(sha)
        baru += 1
    return baru


# --------------------------------------------------------------------------
# Validasi kelengkapan & verifikasi manual
# --------------------------------------------------------------------------

def jalankan_validator(doc: dict) -> dict:
    """Periksa kelengkapan nomor KUK dengan modul validator independen."""
    from app.kuk_completeness_validator import periksa_dokumen

    path = jalur_pdf(doc)
    hasil = periksa_dokumen(path, doc.get('units') or [])
    doc['validasi_kelengkapan'] = {
        'versi': 3,
        'status': hasil['status'],
        'diperiksa_pada': datetime.now().isoformat(timespec='seconds'),
        'ringkasan': hasil['ringkasan'],
        'unit': {u['kode_unit']: u for u in hasil['units']},
        'catatan': hasil['catatan'],
    }
    simpan_metadata(doc)
    return doc


def tandai_manual(doc: dict, kode_unit: str) -> dict:
    """Pengguna menyatakan sudah membandingkan unit dengan PDF sumber."""
    if not any(u['kode_unit'] == kode_unit for u in doc.get('units') or []):
        raise GalatUpload('Kode unit tidak ada pada dokumen ini.', 404)
    doc.setdefault('verifikasi_manual', {})[kode_unit] = {
        'waktu': datetime.now().isoformat(timespec='seconds'),
        'oleh': 'pengguna_lokal',
    }
    simpan_metadata(doc)
    return doc


def bersihkan_tmp() -> None:
    """Hapus sisa berkas sementara (mis. setelah server berhenti mendadak)."""
    if TMP_DIR.exists():
        for p in TMP_DIR.glob('*.part'):
            try:
                if p.stat().st_mtime < datetime.now().timestamp() - 3600:
                    p.unlink()
            except OSError:
                pass

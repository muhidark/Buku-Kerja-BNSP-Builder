"""
Pengujian Versioning, Logging, dan Dokumentasi (Fase 5A.1).

Menguji:
1. Konsistensi versi 1.0.0 sebagai satu sumber kebenaran (single source of truth).
2. Endpoint API dan dashboard menggunakan versi 1.0.0.
3. Keberadaan dan konfigurasi logging terstruktur (rotasi 10 MB, 5 file).
4. Keberadaan dan kelengkapan 4 dokumen rilis pada direktori docs/.
"""

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.api.dashboard import dashboard
from app.api.system import health
from app.logging_config import BACKUP_COUNT, LOG_FILE, MAX_BYTES, ambil_logger
from app.main import VERSI, app
from app.version import __version__

lulus, gagal = [], []


def cek(nama, kondisi, detail=''):
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}" + (f" — {detail}" if detail and not kondisi else ''))


def main():
    print("=" * 100)
    print("PENGUJIAN VERSIONING, LOGGING, DAN DOKUMENTASI — FASE 5A.1")
    print("=" * 100)

    client = TestClient(app)

    # -------------------------------------------------------------
    # 1. PENGUJIAN VERSIONING
    # -------------------------------------------------------------
    print("\n1. PENGUJIAN VERSIONING (SINGLE SOURCE OF TRUTH)")
    cek('app.version.__version__ adalah 1.0.0', __version__ == '1.0.0', __version__)
    cek('app.main.VERSI cocok dengan __version__', VERSI == __version__, VERSI)
    cek('app.main.app.version cocok dengan __version__', app.version == __version__, app.version)

    # Uji endpoint /api/health
    r_health = client.get('/api/health')
    cek('/api/health status 200', r_health.status_code == 200)
    cek('/api/health memuat version 1.0.0', r_health.json().get('version') == '1.0.0', r_health.text)

    # Uji endpoint /api/dashboard
    r_dash = client.get('/api/dashboard')
    cek('/api/dashboard status 200', r_dash.status_code == 200)
    cek('/api/dashboard memuat version 1.0.0', r_dash.json().get('version') == '1.0.0', r_dash.text)

    # Uji HTML dashboard
    r_html = client.get('/')
    cek('Halaman dashboard status 200', r_html.status_code == 200)
    cek('Halaman dashboard menampilkan v1.0.0', '1.0.0' in r_html.text)

    # -------------------------------------------------------------
    # 2. PENGUJIAN LOGGING DAN ROTASI
    # -------------------------------------------------------------
    print("\n2. PENGUJIAN LOGGING DAN ROTASI")
    logger = ambil_logger('uji_regresi')
    pesan_uji = 'Pengujian penulisan log terstruktur Fase 5A.1'
    logger.info(pesan_uji)

    cek('Berkas log skkni_extractor.log terbentuk', LOG_FILE.exists())
    isi_log = LOG_FILE.read_text(encoding='utf-8')
    cek('Pesan log tercatat di berkas', pesan_uji in isi_log)

    cek('Batas ukuran rotasi berkas adalah 10 MB', MAX_BYTES == 10 * 1024 * 1024, str(MAX_BYTES))
    cek('Retensi berkas backup adalah 5 file', BACKUP_COUNT == 5, str(BACKUP_COUNT))

    # Cek handler pada root logger skkni
    root_skkni = logging.getLogger('skkni')
    file_handlers = [h for h in root_skkni.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    cek('RotatingFileHandler terpasang pada logger', len(file_handlers) >= 1)
    if file_handlers:
        fh = file_handlers[0]
        cek('Handler maxBytes sesuai', fh.maxBytes == 10 * 1024 * 1024)
        cek('Handler backupCount sesuai', fh.backupCount == 5)

    # -------------------------------------------------------------
    # 3. PENGUJIAN DOKUMENTASI
    # -------------------------------------------------------------
    print("\n3. PENGUJIAN DOKUMENTASI")
    docs_dir = ROOT / 'docs'
    cek('Direktori docs/ tersedia', docs_dir.exists())

    dokumen_wajib = {
        'INSTALL.md': ['Persyaratan Sistem', 'Virtual Environment', 'Menjalankan Aplikasi', 'run.sh'],
        'USER_GUIDE.md': ['Upload PDF SKKNI', 'Skema Sertifikasi', 'Ekstraksi', 'Preview', 'Generate'],
        'BACKUP_RESTORE.md': ['backup.py', 'restore.py', 'Dry-Run', 'manifest.json', 'force'],
        'RELEASE_NOTES_1.0.0.md': ['1.0.0', 'Fitur Utama', 'Keterbatasan', 'Pengujian'],
    }

    for nama_dok, kata_kunci in dokumen_wajib.items():
        p_dok = docs_dir / nama_dok
        ada = p_dok.exists() and p_dok.stat().st_size > 200
        cek(f'Dokumen docs/{nama_dok} tersedia', ada)
        if ada:
            teks = p_dok.read_text(encoding='utf-8')
            lengkap = all(k.lower() in teks.lower() for k in kata_kunci)
            cek(f'Dokumen docs/{nama_dok} memuat seluruh poin wajib', lengkap)

    print("\n" + "=" * 100)
    print(f"HASIL: {len(lulus)} lulus, {len(gagal)} gagal")
    if gagal:
        for g in gagal:
            print(f"  - {g}")
    print("=" * 100)
    return 0 if not gagal else 1




def test_version_logging():
    assert main() == 0


if __name__ == '__main__':
    sys.exit(main())

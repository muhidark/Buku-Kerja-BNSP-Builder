"""Satu tempat untuk seluruh path data proyek.

Sebelumnya `ROOT = Path(__file__).resolve().parent.parent` ditulis ulang di
sembilan modul. Menambah atau memindahkan direktori data berarti menyunting
banyak berkas, dan kesalahan tingkat (`parents[1]` vs `parents[2]`) baru
terlihat saat runtime.

Modul lain boleh tetap memakai `ROOT`-nya sendiri (kompatibilitas), tetapi kode
baru sebaiknya mengambil path dari sini.
"""

from __future__ import annotations

from pathlib import Path

#: Akar repositori proyek.
ROOT = Path(__file__).resolve().parent.parent

#: Direktori data utama.
DATA_DIR = ROOT / 'data'
PDF_DIR = DATA_DIR / 'pdf'
JSON_DIR = DATA_DIR / 'json'
LIBRARY_DIR = DATA_DIR / 'library'
SCHEMA_DIR = DATA_DIR / 'schema_library'
JOBS_DIR = DATA_DIR / 'jobs'
WEB_DOC_DIR = DATA_DIR / 'web_documents'

#: Basis data SQLite.
DB_PATH = DATA_DIR / 'app.db'

#: Direktori keluaran.
OUTPUT_DIR = ROOT / 'output'

#: Berkas pendukung aplikasi.
APP_DIR = ROOT / 'app'
TEMPLATE_DIR = APP_DIR / 'templates'
STATIC_DIR = APP_DIR / 'static'
LOG_DIR = ROOT / 'logs'
BACKUP_DIR = ROOT / 'backups'


#: Periksa sekali saat impor bahwa path benar; salah tingkat langsung gagal.
assert (ROOT / 'data').is_dir(), f'ROOT tidak menunjuk ke akar proyek: {ROOT}'

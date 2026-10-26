"""
Konfigurasi Pytest & Fixtures Global (Fase 5 - Langkah 5.1).

Menyediakan:
1. Isolasi dan proteksi basis data kerja data/app.db agar tidak tercemar oleh pengujian.
2. Otomatisasi pemulihan global db.DB_PATH dan db.DB_DIR antar pengujian.
3. Fixture klien pengujian dengan berbagai peran (tamu, admin, asesor).
4. Pengaturan marker pytest (seperti slow untuk test berat lintas SKKNI).
"""

import hashlib
import shutil
from pathlib import Path
from typing import Generator

import pytest
from starlette.testclient import TestClient

from app import db
from app.main import app
from app.paths import DB_PATH
from tests.dukungan import klien as _klien_dukungan


def _hitung_checksum_db(path: Path) -> str:
    """Hitung hash SHA-256 dari berkas basis data SQLite."""
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture(scope="session", autouse=True)
def jaga_integritas_basis_data() -> Generator[None, None, None]:
    """Cadangkan basis data sebelum pengujian dan pastikan checksum tetap utuh setelah selesai."""
    bak_path = DB_PATH.with_suffix(".db.testbak")
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, bak_path)
    awal_checksum = _hitung_checksum_db(DB_PATH)

    yield

    # Pulihkan berkas db jika mengalami perubahan selama rangkaian test
    if bak_path.exists():
        akhir_checksum = _hitung_checksum_db(DB_PATH)
        if akhir_checksum != awal_checksum:
            shutil.copy2(bak_path, DB_PATH)
        bak_path.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def pulihkan_modul_global() -> Generator[None, None, None]:
    """Pastikan modifikasi db.DB_PATH atau db.DB_DIR selalu dipulihkan ke semula."""
    asli_db_dir = db.DB_DIR
    asli_db_path = db.DB_PATH
    yield
    db.DB_DIR = asli_db_dir
    db.DB_PATH = asli_db_path


@pytest.fixture
def klien_tamu() -> TestClient:
    """Klien tanpa sesi (pengguna publik / tamu)."""
    return _klien_dukungan(app, None)


@pytest.fixture
def klien_admin() -> TestClient:
    """Klien dengan sesi peran admin."""
    return _klien_dukungan(app, "admin")


@pytest.fixture
def klien_asesor() -> TestClient:
    """Klien dengan sesi peran asesor."""
    return _klien_dukungan(app, "asesor")

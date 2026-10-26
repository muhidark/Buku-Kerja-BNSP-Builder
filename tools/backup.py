"""
SKKNI Extractor - Utilitas Backup Data (Fase 5A.1).

Mencadangkan data pengguna, perpustakaan PDF, skema DOCX, hasil ekstraksi JSON,
metadata pekerjaan, dan dokumen hasil ke dalam arsip ZIP ber-manifest SHA-256.
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Direktori default penyimpanan backup (di luar data yang dicadangkan)
DEFAULT_BACKUP_DIR = ROOT / 'backups'

# Direktori sumber data yang dicadangkan
SUMBER_DATA = [
    ROOT / 'data',
    ROOT / 'output' / 'web_documents',
]

# Pola yang harus dikecualikan dari arsip
POLA_ABAIKAN = {
    '.venv', '__pycache__', '.git', 'logs', 'backups',
    '.pytest_cache', '.mypy_cache', 'tmp',
}
AKHIRAN_ABAIKAN = ('.pyc', '.pyo', '.tmp', '.log', '.DS_Store')

from app.logging_config import ambil_logger

logger = ambil_logger('backup')


def _hitung_sha256(path: Path) -> str:
    """Hitung SHA-256 sebuah berkas secara streaming."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _ambil_versi() -> str:
    """Ambil versi aplikasi dari app.version jika ada."""
    try:
        from app.version import __version__
        return __version__
    except Exception:
        return '1.0.0'


def kumpulkan_berkas() -> list[Path]:
    """Kumpulkan seluruh berkas data produksi yang sah untuk dicadangkan."""
    berkas_valid = []
    for basis in SUMBER_DATA:
        if not basis.exists():
            continue
        for p in basis.rglob('*'):
            if not p.is_file():
                continue
            # Periksa apakah ada bagian path yang masuk dalam pola abaikan
            parts = set(p.relative_to(ROOT).parts)
            if parts & POLA_ABAIKAN:
                continue
            if p.name.startswith('.') or p.name.endswith(AKHIRAN_ABAIKAN):
                continue
            berkas_valid.append(p)
    return sorted(berkas_valid)


def buat_backup(out_dir: Path | str | None = None) -> tuple[Path, dict]:
    """
    Membuat arsip backup ZIP dari data proyek.

    Returns:
        tuple[Path, dict]: Jalur berkas ZIP yang dihasilkan dan isi manifest.
    """
    if out_dir is None:
        target_dir = DEFAULT_BACKUP_DIR
    else:
        target_dir = Path(out_dir)

    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    nama_dasar = f"backup_skkni_{timestamp_str}"
    nama_arsip = f"{nama_dasar}.zip"
    jalur_zip = target_dir / nama_arsip

    # Hindari menimpa berkas jika nama sudah ada
    counter = 1
    while jalur_zip.exists():
        nama_arsip = f"{nama_dasar}_{counter}.zip"
        jalur_zip = target_dir / nama_arsip
        counter += 1

    berkas_list = kumpulkan_berkas()
    if not berkas_list:
        raise RuntimeError('Tidak ada berkas yang ditemukan untuk dicadangkan.')

    logger.info(f"Memulai pembuatan backup ke {jalur_zip} ({len(berkas_list)} berkas)...")

    # Kumpulkan metadata dan hash setiap berkas
    entries = []
    total_ukuran = 0
    for p in berkas_list:
        rel_path = str(p.relative_to(ROOT)).replace('\\', '/')
        ukuran = p.stat().st_size
        sha256 = _hitung_sha256(p)
        entries.append({
            'path': rel_path,
            'sha256': sha256,
            'size': ukuran,
        })
        total_ukuran += ukuran

    manifest = {
        'format_versi': '1.0',
        'aplikasi': 'SKKNI Extractor',
        'versi_aplikasi': _ambil_versi(),
        'dibuat_pada': datetime.now().isoformat(timespec='seconds'),
        'nama_arsip': jalur_zip.name,
        'total_berkas': len(entries),
        'total_ukuran_byte': total_ukuran,
        'files': entries,
    }

    # Tulis ke arsip ZIP secara aman menggunakan berkas sementara
    jalur_tmp = jalur_zip.with_suffix('.tmp')
    try:
        with zipfile.ZipFile(jalur_tmp, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            # Tulis manifest di root arsip
            zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))

            # Masukkan seluruh berkas data
            for p, info in zip(berkas_list, entries):
                zf.write(p, arcname=info['path'])

        # Validasi integritas arsip ZIP
        with zipfile.ZipFile(jalur_tmp, 'r') as zf:
            uji_rusak = zf.testzip()
            if uji_rusak is not None:
                raise RuntimeError(f"Arsip backup korup pada entri: {uji_rusak}")
            # Pastikan manifest dapat dibaca kembali
            zf.read('manifest.json')

        # Pindahkan berkas sementara ke nama permanen
        jalur_tmp.replace(jalur_zip)
    finally:
        if jalur_tmp.exists():
            jalur_tmp.unlink()

    logger.info(f"Backup selesai: {jalur_zip} ({total_ukuran} bytes, {len(entries)} berkas).")
    return jalur_zip, manifest


def main():
    parser = argparse.ArgumentParser(description='Pencadangan data SKKNI Extractor')
    parser.add_argument('--outdir', '-o', type=str, default=None,
                        help='Direktori tujuan penyimpanan arsip backup')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    try:
        zip_path, manifest = buat_backup(args.outdir)
        print(f"Backup berhasil dibuat: {zip_path}")
        print(f"Total berkas   : {manifest['total_berkas']}")
        print(f"Total ukuran   : {manifest['total_ukuran_byte']} byte")
        print(f"Versi aplikasi : {manifest['versi_aplikasi']}")
        return 0
    except Exception as e:
        print(f"Galat saat membuat backup: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

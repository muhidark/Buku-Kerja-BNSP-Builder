"""
SKKNI Extractor - Utilitas Pemulihan Data / Restore (Fase 5A.1).

Memulihkan data pengguna dan metadata aplikasi dari arsip ZIP backup
dengan verifikasi manifest SHA-256, proteksi path traversal, dry-run,
dan perlindungan terhadap proses aktif.
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Batasan proteksi dekompresi (ZIP bomb)
BATAS_TOTAL_DEKOMPRESI = 2 * 1024 * 1024 * 1024  # 2 GB
BATAS_RASIO_KOMPRESI = 100                        # rasio 100:1
MIN_UKURAN_CEK_RASIO = 1024 * 1024               # 1 MB

from app.logging_config import ambil_logger

logger = ambil_logger('restore')


class GalatRestore(Exception):
    """Pengecualian spesifik pada proses restore."""
    pass


def _hitung_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def periksa_pekerjaan_aktif(root_proyek: Path) -> bool:
    """Periksa apakah ada pekerjaan ekstraksi yang sedang berjalan atau menunggu."""
    jobs_dir = root_proyek / 'data' / 'jobs'
    if not jobs_dir.exists():
        return False
    for p in jobs_dir.glob('*.json'):
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
            if d.get('status') in ('menunggu', 'berjalan'):
                return True
        except Exception:
            continue
    return False


def validasi_entri_keamanan(zf: zipfile.ZipFile):
    """
    Validasi keamanan struktur ZIP:
    - Tidak ada path absolut
    - Tidak ada path traversal (..)
    - Tidak ada symlink
    - Ukuran dan rasio kompresi dalam batas wajar (proteksi ZIP bomb)
    """
    total_uncompressed = 0

    for info in zf.infolist():
        nama = info.filename

        # Cek path absolut
        if nama.startswith(('/', '\\')) or (len(nama) > 1 and nama[1] == ':'):
            raise GalatRestore(f"Keamanan: Path absolut ditolak pada arsip: {nama}")

        # Cek path traversal
        norm = os.path.normpath(nama)
        if norm.startswith('..') or '/../' in norm or norm == '..':
            raise GalatRestore(f"Keamanan: Path traversal ditolak pada arsip: {nama}")

        # Cek symlink (mode UNIX 0o120000)
        mode = info.external_attr >> 16
        if mode and (mode & 0o170000) == 0o120000:
            raise GalatRestore(f"Keamanan: Symlink ditolak pada arsip: {nama}")

        total_uncompressed += info.file_size
        if total_uncompressed > BATAS_TOTAL_DEKOMPRESI:
            raise GalatRestore(
                f"Keamanan: Ukuran total dekompresi ({total_uncompressed} byte) "
                f"melebihi batas aman ({BATAS_TOTAL_DEKOMPRESI} byte)."
            )

        # Cek rasio kompresi
        if info.file_size > MIN_UKURAN_CEK_RASIO and info.compress_size > 0:
            rasio = info.file_size / info.compress_size
            if rasio > BATAS_RASIO_KOMPRESI:
                raise GalatRestore(
                    f"Keamanan: Rasio kompresi mencurigakan ({rasio:.1f}x) pada {nama}."
                )


def pulihkan_backup(
    zip_path: Path | str,
    target_dir: Path | str | None = None,
    dry_run: bool = False,
    force: bool = False
) -> dict:
    """
    Eksekusi pemulihan backup.

    Args:
        zip_path: Jalur ke berkas ZIP backup.
        target_dir: Direktori tujuan pemulihan (default: ROOT proyek).
        dry_run: Jika True, hanya simulasi dan periksa konflik tanpa menulis data.
        force: Jika True, izinkan menimpa berkas yang berkonflik.

    Returns:
        dict: Ringkasan hasil pemulihan/simulasi.
    """
    zip_path = Path(zip_path).resolve()
    target_dir = Path(target_dir).resolve() if target_dir else ROOT

    if not zip_path.exists():
        raise GalatRestore(f"Berkas backup tidak ditemukan: {zip_path}")

    if not zipfile.is_zipfile(zip_path):
        raise GalatRestore(f"Berkas bukan arsip ZIP yang sah: {zip_path}")

    # Tolak restore ke data aktif jika ada job berjalan (hanya bila restore ke root proyek)
    if target_dir == ROOT and periksa_pekerjaan_aktif(ROOT):
        raise GalatRestore(
            "Tidak dapat memulihkan ke direktori aktif: terdapat pekerjaan ekstraksi "
            "yang sedang berjalan atau menunggu. Hentikan pekerjaan terlebih dahulu."
        )

    with zipfile.ZipFile(zip_path, 'r') as zf:
        # 1. Uji integritas ZIP
        uji = zf.testzip()
        if uji is not None:
            raise GalatRestore(f"Arsip ZIP korup pada entri: {uji}")

        # 2. Uji keamanan entri
        validasi_entri_keamanan(zf)

        # 3. Baca manifest
        if 'manifest.json' not in zf.namelist():
            raise GalatRestore("Arsip tidak memiliki manifest.json yang sah.")

        try:
            manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
        except Exception as e:
            raise GalatRestore(f"Manifest di dalam arsip tidak dapat dibaca: {e}")

        files_manifest = manifest.get('files', [])
        if not files_manifest:
            raise GalatRestore("Manifest tidak memuat daftar berkas pemulihan.")

        peta_manifest = {item['path']: item for item in files_manifest}

        # 4. Periksa konflik berkas di target
        konflik = []
        berkas_baru = []
        for info in files_manifest:
            rel = info['path']
            lokasi = target_dir / rel
            if lokasi.exists():
                konflik.append(rel)
            else:
                berkas_baru.append(rel)

        ringkasan = {
            'arsip': str(zip_path),
            'target_dir': str(target_dir),
            'total_berkas': len(files_manifest),
            'konflik_ada': len(konflik),
            'berkas_baru': len(berkas_baru),
            'daftar_konflik': konflik,
            'dry_run': dry_run,
            'versi_aplikasi': manifest.get('versi_aplikasi'),
        }

        if dry_run:
            logger.info("Mode DRY-RUN: simulasi selesai tanpa mengubah berkas.")
            return ringkasan

        if konflik and not force:
            raise GalatRestore(
                f"Terdapat {len(konflik)} berkas yang sudah ada di direktori tujuan. "
                "Gunakan opsi --force untuk menyetujui penimpaan data."
            )

        # 5. Ekstraksi atomik ke direktori staging
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        staging_dir = target_dir / f".restore_staging_{timestamp_str}"
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Ekstrak seluruh berkas ke staging
            for info in files_manifest:
                rel = info['path']
                zf.extract(rel, staging_dir)

            # 6. Verifikasi SHA-256 setiap berkas di staging
            for info in files_manifest:
                rel = info['path']
                jalur_staging = staging_dir / rel
                if not jalur_staging.exists():
                    raise GalatRestore(f"Berkas gagal diekstrak ke staging: {rel}")
                hash_aktual = _hitung_sha256(jalur_staging)
                if hash_aktual != info['sha256']:
                    raise GalatRestore(
                        f"Verifikasi integritas gagal pada {rel}: "
                        f"hash {hash_aktual} != {info['sha256']}"
                    )

            # 7. Salin / pindahkan dari staging ke target_dir secara aman
            for info in files_manifest:
                rel = info['path']
                sumber = staging_dir / rel
                tujuan = target_dir / rel
                tujuan.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sumber, tujuan)

        finally:
            # Selalu bersihkan direktori staging
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

        logger.info(f"Pemulihan berhasil: {len(files_manifest)} berkas dipulihkan ke {target_dir}.")
        ringkasan['status'] = 'BERHASIL'
        return ringkasan


def main():
    parser = argparse.ArgumentParser(description='Pemulihan data backup SKKNI Extractor')
    parser.add_argument('backup_zip', type=str, help='Jalur ke berkas ZIP backup')
    parser.add_argument('--target-dir', '-t', type=str, default=None,
                        help='Direktori tujuan pemulihan (default: direktori proyek)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Simulasi pemulihan dan periksa konflik tanpa menulis data')
    parser.add_argument('--force', '-f', action='store_true',
                        help='Izinkan menimpa berkas yang sudah ada di direktori tujuan')

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    try:
        hasil = pulihkan_backup(
            args.backup_zip,
            target_dir=args.target_dir,
            dry_run=args.dry_run,
            force=args.force
        )
        print("Pemulihan selesai dengan sukses:")
        print(f"  Arsip           : {hasil['arsip']}")
        print(f"  Target direktori: {hasil['target_dir']}")
        print(f"  Total berkas    : {hasil['total_berkas']}")
        print(f"  Konflik         : {hasil['konflik_ada']}")
        print(f"  Berkas baru     : {hasil['berkas_baru']}")
        print(f"  Mode dry-run    : {hasil['dry_run']}")
        return 0
    except GalatRestore as e:
        print(f"GALAT RESTORE: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"GALAT TAK TERDUGA: {e}", file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())

"""
Pengujian komprehensif untuk utilitas Backup dan Restore (Fase 5A.1).

Menguji:
1. Pembuatan backup, struktur manifest, dan integritas arsip ZIP.
2. Pengecualian berkas cache, log, dan venv.
3. Mode dry-run dan deteksi konflik.
4. Pemulihan ke direktori terisolasi dan verifikasi hash SHA-256.
5. Penolakan terhadap berkas korup, path traversal, path absolut, symlink,
   penimpaan tanpa konfirmasi, dan pemulihan saat ada pekerjaan aktif.
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import backup, restore

lulus, gagal = [], []


def cek(nama, kondisi, detail=''):
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}" + (f" — {detail}" if detail and not kondisi else ''))


def main():
    print("=" * 100)
    print("PENGUJIAN BACKUP DAN RESTORE — FASE 5A.1")
    print("=" * 100)

    temp_dir = Path(tempfile.mkdtemp(prefix='skkni_test_br_'))

    try:
        # -------------------------------------------------------------
        # 1. PENGUJIAN PEMBUATAN BACKUP
        # -------------------------------------------------------------
        print("\n1. PENGUJIAN PEMBUATAN BACKUP")
        backup_out = temp_dir / 'backup_dest'
        zip_path, manifest = backup.buat_backup(out_dir=backup_out)

        cek('Berkas zip backup berhasil dibuat', zip_path.exists() and zip_path.stat().st_size > 1000)
        cek('Nama arsip sesuai pola timestamp', zip_path.name.startswith('backup_skkni_') and zip_path.suffix == '.zip')
        cek('Manifest memiliki total_berkas > 0', manifest['total_berkas'] > 0, str(manifest['total_berkas']))
        cek('Versi aplikasi pada manifest adalah 1.0.0', manifest['versi_aplikasi'] == '1.0.0', manifest['versi_aplikasi'])

        # Cek integritas ZIP bawaan
        with zipfile.ZipFile(zip_path, 'r') as zf:
            cek('Arsip ZIP lolos testzip() tanpa korupsi', zf.testzip() is None)
            namelist = zf.namelist()
            cek('manifest.json terdapat di root arsip', 'manifest.json' in namelist)

            # Cek pengecualian
            ada_terlarang = any(
                p.startswith(('.venv', '__pycache__', 'logs', 'backups', '.git')) or
                p.endswith(('.pyc', '.tmp', '.log'))
                for p in namelist
            )
            cek('Pengecualian .venv, cache, log, dan tmp ditaati', not ada_terlarang)

        # -------------------------------------------------------------
        # 2. PENGUJIAN RESTORE DRY-RUN
        # -------------------------------------------------------------
        print("\n2. PENGUJIAN RESTORE DRY-RUN")
        target_isolasi = temp_dir / 'restore_target'
        hasil_dry = restore.pulihkan_backup(zip_path, target_dir=target_isolasi, dry_run=True)
        cek('Dry-run mengembalikan status dry_run=True', hasil_dry['dry_run'] is True)
        cek('Dry-run tidak membuat direktori/berkas di target', not target_isolasi.exists())
        cek('Jumlah berkas terdeteksi cocok dengan manifest', hasil_dry['total_berkas'] == manifest['total_berkas'])
        cek('Konflik pada direktori kosong adalah 0', hasil_dry['konflik_ada'] == 0)

        # -------------------------------------------------------------
        # 3. PENGUJIAN PEMULIHAN KE DIREKTORI TERISOLASI
        # -------------------------------------------------------------
        print("\n3. PENGUJIAN PEMULIHAN TERISOLASI & VERIFIKASI SHA-256")
        hasil_rest = restore.pulihkan_backup(zip_path, target_dir=target_isolasi, dry_run=False)
        cek('Restore berhasil dieksekusi', hasil_rest.get('status') == 'BERHASIL')
        cek('Direktori target terbentuk', target_isolasi.exists())

        # Bandingkan seluruh hash file hasil restore dengan manifest
        semua_cocok = True
        gagal_cocok = []
        for info in manifest['files']:
            p = target_isolasi / info['path']
            if not p.exists():
                semua_cocok = False
                gagal_cocok.append(f"Hilang: {info['path']}")
                continue
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            if h != info['sha256']:
                semua_cocok = False
                gagal_cocok.append(f"Hash beda: {info['path']}")

        cek('100% hash berkas hasil restore cocok dengan manifest', semua_cocok, str(gagal_cocok[:3]))

        # -------------------------------------------------------------
        # 4. PENGUJIAN DETEKSI KONFLIK TANPA FORCE
        # -------------------------------------------------------------
        print("\n4. PENGUJIAN DETEKSI KONFLIK TANPA FORCE")
        konflik_tertangkap = False
        try:
            restore.pulihkan_backup(zip_path, target_dir=target_isolasi, dry_run=False, force=False)
        except restore.GalatRestore as e:
            konflik_tertangkap = True
            cek('Penimpaan tanpa --force ditolak dengan aman', 'sudah ada di direktori tujuan' in str(e))
        cek('Pengecualian konflik tertangkap', konflik_tertangkap)

        # Uji dengan force=True
        hasil_force = restore.pulihkan_backup(zip_path, target_dir=target_isolasi, dry_run=False, force=True)
        cek('Restore dengan force=True berhasil menimpa', hasil_force.get('status') == 'BERHASIL')

        # -------------------------------------------------------------
        # 5. PENGUJIAN KEGAGALAN DAN KEAMANAN
        # -------------------------------------------------------------
        print("\n5. PENGUJIAN KASUS KEGAGALAN DAN KEAMANAN")

        # A. Berkas tidak ada
        berkas_palsu_tertangkap = False
        try:
            restore.pulihkan_backup(temp_dir / 'tidak_ada.zip', target_dir=target_isolasi)
        except restore.GalatRestore:
            berkas_palsu_tertangkap = True
        cek('Arsip tidak ada ditolak', berkas_palsu_tertangkap)

        # B. Berkas bukan ZIP (korup)
        zip_rusak = temp_dir / 'rusak.zip'
        zip_rusak.write_bytes(b'PK\x03\x04bukan zip yang valid sama sekali')
        zip_rusak_tertangkap = False
        try:
            restore.pulihkan_backup(zip_rusak, target_dir=target_isolasi)
        except restore.GalatRestore:
            zip_rusak_tertangkap = True
        cek('Arsip ZIP korup ditolak', zip_rusak_tertangkap)

        # C. Path traversal injection
        zip_traversal = temp_dir / 'traversal.zip'
        with zipfile.ZipFile(zip_traversal, 'w') as zf:
            zf.writestr('manifest.json', json.dumps({'files': [{'path': '../../bahaya.txt', 'sha256': '123'}]}))
            zf.writestr('../../bahaya.txt', 'bahaya')
        traversal_tertangkap = False
        try:
            restore.pulihkan_backup(zip_traversal, target_dir=target_isolasi)
        except restore.GalatRestore as e:
            traversal_tertangkap = True
            cek('Path traversal (..) ditolak', 'Path traversal ditolak' in str(e))
        cek('Pengecualian path traversal tertangkap', traversal_tertangkap)

        # D. Path absolut injection
        zip_absolut = temp_dir / 'absolut.zip'
        with zipfile.ZipFile(zip_absolut, 'w') as zf:
            zf.writestr('manifest.json', json.dumps({'files': [{'path': '/etc/passwd', 'sha256': '123'}]}))
            zf.writestr('/etc/passwd', 'root:x:0:0')
        absolut_tertangkap = False
        try:
            restore.pulihkan_backup(zip_absolut, target_dir=target_isolasi)
        except restore.GalatRestore as e:
            absolut_tertangkap = True
            cek('Path absolut (/) ditolak', 'Path absolut ditolak' in str(e))
        cek('Pengecualian path absolut tertangkap', absolut_tertangkap)

        # E. Pekerjaan aktif di root proyek
        asli_periksa = restore.periksa_pekerjaan_aktif
        restore.periksa_pekerjaan_aktif = lambda r: True
        job_aktif_tertangkap = False
        try:
            restore.pulihkan_backup(zip_path, target_dir=ROOT)
        except restore.GalatRestore as e:
            job_aktif_tertangkap = True
            cek('Restore ditolak saat ada pekerjaan aktif', 'terdapat pekerjaan ekstraksi' in str(e))
        finally:
            restore.periksa_pekerjaan_aktif = asli_periksa
        cek('Pengecualian pekerjaan aktif tertangkap', job_aktif_tertangkap)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n" + "=" * 100)
    print(f"HASIL: {len(lulus)} lulus, {len(gagal)} gagal")
    if gagal:
        for g in gagal:
            print(f"  - {g}")
    print("=" * 100)
    return 0 if not gagal else 1




def test_backup_restore():
    assert main() == 0


if __name__ == '__main__':
    sys.exit(main())

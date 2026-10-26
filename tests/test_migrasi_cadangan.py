"""
Pengujian migrasi struktur bernomor & pencadangan harian
(langkah 4.3, temuan T-30 dan T-31).

Migrasi:
1. Basis data baru langsung mencapai versi struktur terbaru dan punya kolomnya.
2. Menjalankan inisialisasi dua kali tidak mengubah apa pun (idempoten).
3. Basis data "lama" (versi 0, kolom belum ada) dinaikkan versinya dan kolomnya
   ditambahkan — inilah yang dulu gagal dilakukan `CREATE TABLE IF NOT EXISTS`.

Pencadangan:
4. Cadangan dibuat paling banyak sekali per hari.
5. Rotasi menyisakan 7 arsip terbaru.
6. Kegagalan pembuatan cadangan tidak melempar keluar (aplikasi tetap jalan).
7. Dapat dimatikan lewat SKKNI_TANPA_CADANGAN=1.
"""

import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app import cadangan, db

lulus, gagal = [], []


def cek(nama: str, kondisi: bool, detail: str = '') -> None:
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}"
          + (f" — {detail}" if detail and not kondisi else ''))


def kolom(conn: sqlite3.Connection, tabel: str) -> set:
    """Nama kolom; mendukung koneksi ber-row_factory maupun tanpa."""
    hasil = set()
    for r in conn.execute(f'PRAGMA table_info({tabel})'):
        hasil.add(r['name'] if isinstance(r, sqlite3.Row) else r[1])
    return hasil


def main() -> int:
    print('=' * 100)
    print('PENGUJIAN MIGRASI STRUKTUR & PENCADANGAN — LANGKAH 4.3 (T-30, T-31)')
    print('=' * 100)

    simpan_dir, simpan_path = db.DB_DIR, db.DB_PATH
    try:
        # ------------------------------------------------ 1. basis data baru
        print('\n1. BASIS DATA BARU LANGSUNG PADA VERSI TERBARU')
        with tempfile.TemporaryDirectory() as tmp:
            db.DB_DIR = Path(tmp)
            db.DB_PATH = Path(tmp) / 'baru.db'
            db.inisialisasi_db()
            with db._ambil_koneksi() as c:
                cek('versi struktur = SKEMA_VERSI', db.versi_skema(c) == db.SKEMA_VERSI,
                    f'{db.versi_skema(c)} vs {db.SKEMA_VERSI}')
                cek('kolom must_change_password ada', 'must_change_password' in kolom(c, 'pengguna'))
                for k in ('kunci_hash', 'prefix', 'kedaluwarsa'):
                    cek(f'kolom {k} ada di kunci_api', k in kolom(c, 'kunci_api'))

            # -------------------------------------------- 2. idempoten
            print('\n2. MENJALANKAN LAGI TIDAK MENGUBAH APA PUN')
            with db._ambil_koneksi() as c:
                sebelum = {t: kolom(c, t) for t in ('pengguna', 'kunci_api', 'muk_versi', 'sesi')}
                versi_sebelum = db.versi_skema(c)
                jumlah_versi = c.execute('SELECT COUNT(*) AS n FROM muk_versi').fetchone()['n']

            dijalankan = db.inisialisasi_db()  # type: ignore[func-returns-value]

            with db._ambil_koneksi() as c:
                sesudah = {t: kolom(c, t) for t in sebelum}
                cek('skema tabel tidak berubah', sebelum == sesudah)
                cek('versi struktur tidak berubah', db.versi_skema(c) == versi_sebelum)
                cek('data muk_versi tidak bertambah',
                    c.execute('SELECT COUNT(*) AS n FROM muk_versi').fetchone()['n'] == jumlah_versi)

        # ------------------------------------------- 3. basis data "lama"
        print('\n3. BASIS DATA LAMA (versi 0, kolom belum ada) DINAIKKAN')
        with tempfile.TemporaryDirectory() as tmp:
            db.DB_DIR = Path(tmp)
            db.DB_PATH = Path(tmp) / 'lama.db'
            conn = sqlite3.connect(str(db.DB_PATH))
            conn.executescript("""
                CREATE TABLE pengguna (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    nama_lengkap TEXT NOT NULL,
                    email TEXT,
                    peran TEXT NOT NULL CHECK(peran IN ('admin', 'asesor')),
                    hash_kata_sandi TEXT NOT NULL,
                    garam TEXT NOT NULL,
                    no_met TEXT,
                    dibuat_pada TEXT NOT NULL
                );
                CREATE TABLE kunci_api (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kunci TEXT UNIQUE NOT NULL,
                    nama_klien TEXT NOT NULL,
                    peran TEXT NOT NULL DEFAULT 'klien',
                    aktif INTEGER NOT NULL DEFAULT 1,
                    dibuat_pada TEXT NOT NULL,
                    terakhir_digunakan TEXT
                );
            """)
            conn.execute('PRAGMA user_version = 0')
            conn.commit()
            cek('basis data lama dimulai pada versi 0',
                conn.execute('PRAGMA user_version').fetchone()[0] == 0)
            cek('kolom must_change_password belum ada',
                'must_change_password' not in kolom(conn, 'pengguna'))
            conn.close()

            db.inisialisasi_db()

            with db._ambil_koneksi() as c:
                cek('versi naik ke SKEMA_VERSI', db.versi_skema(c) == db.SKEMA_VERSI,
                    f'{db.versi_skema(c)}')
                cek('kolom baru benar-benar ditambahkan',
                    'must_change_password' in kolom(c, 'pengguna'))
                cek('kolom kunci_hash ditambahkan', 'kunci_hash' in kolom(c, 'kunci_api'))
    finally:
        db.DB_DIR, db.DB_PATH = simpan_dir, simpan_path

    # ------------------------------------------------------- 4. pencadangan
    print('\n4. PENCADANGAN HARIAN')
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)

        def pembuat(_dir: Path):
            f = _dir / f"backup_skkni_{time.strftime('%Y%m%d_%H%M%S')}.zip"
            f.write_bytes(b'x' * 2048)
            return f, {'berkas': 1}

        cek('awal: belum ada cadangan hari ini', not cadangan.sudah_hari_ini(d))
        arsip = cadangan.buat_sekarang(d, pembuat)
        cek('cadangan dibuat', arsip is not None and arsip.exists())
        cek('terdeteksi sebagai cadangan hari ini', cadangan.sudah_hari_ini(d))
        cek('pembuatan kedua dilewati',
            cadangan.jalankan_harian(d, pembuat, latar=False) is None)

        # ---------------------------------------------------- 5. rotasi
        print('\n5. ROTASI MENYISAKAN 7 ARSIP')
        for i in range(10):
            f = d / f'backup_skkni_2020010{i}_120000.zip'
            f.write_bytes(b'y')
            time.sleep(0.005)
        cek('ada lebih dari 7 arsip sebelum rotasi', len(cadangan.daftar_cadangan(d)) > 7,
            f'jumlah={len(cadangan.daftar_cadangan(d))}')
        cadangan.putar(d)
        cek('setelah rotasi tersisa 7', len(cadangan.daftar_cadangan(d)) == 7,
            f'jumlah={len(cadangan.daftar_cadangan(d))}')
        cek('yang tersisa adalah yang terbaru',
            cadangan.daftar_cadangan(d)[0].stat().st_mtime
            >= cadangan.daftar_cadangan(d)[-1].stat().st_mtime)
        info = cadangan.terakhir(d)
        cek('ringkasan cadangan terakhir tersedia',
            bool(info and info.get('waktu') and info.get('ukuran_kb')), str(info))

        # ------------------------------------- 6. kegagalan tidak melempar
        print('\n6. KEGAGALAN PEMBUATAN TIDAK MEMATIKAN APLIKASI')
        with tempfile.TemporaryDirectory() as tmp2:
            d2 = Path(tmp2)

            def pembuat_gagal(_dir: Path):
                raise RuntimeError('disk penuh')

            hasil = cadangan.buat_sekarang(d2, pembuat_gagal)
            cek('kegagalan dikembalikan sebagai None', hasil is None)

    # ------------------------------------------- 7. bisa dimatikan
    print('\n7. DAPAT DIMATIKAN LEWAT VARIABEL LINGKUNGAN')
    os.environ['SKKNI_TANPA_CADANGAN'] = '1'
    with tempfile.TemporaryDirectory() as tmp3:
        cek('jalankan_harian mengembalikan None saat dimatikan',
            cadangan.jalankan_harian(Path(tmp3), latar=False) is None)
    os.environ.pop('SKKNI_TANPA_CADANGAN', None)

    print('\n' + '=' * 100)
    print(f'HASIL: {len(lulus)} lulus, {len(gagal)} gagal')
    if gagal:
        for g in gagal:
            print(f'  - GAGAL: {g}')
    print('=' * 100)
    return 0 if not gagal else 1


if __name__ == '__main__':
    sys.exit(main())

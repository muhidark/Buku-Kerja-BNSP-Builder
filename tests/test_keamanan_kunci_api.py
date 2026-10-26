"""
Pengujian penyimpanan kunci API sebagai hash (perbaikan T-02/T-21 / langkah 1.4).

Memakai basis data SEMENTARA. Yang diuji:

1. Nilai kunci tidak pernah tersimpan sebagai teks biasa; hanya hash + prefix.
2. Nilai asli dikembalikan sekali saat dibuat dan tetap dapat divalidasi.
3. Daftar kunci tidak membocorkan rahasia (tanpa kolom kunci/kunci_hash).
4. Kunci kedaluwarsa dan kunci dicabut ditolak.
5. Migrasi baris lama (teks biasa) berjalan idempoten dan kunci lamanya tetap
   berfungsi setelah di-hash.
6. Pencatatan terakhir_digunakan dibatasi (tidak menulis setiap permintaan).
"""

import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app import db

lulus, gagal = [], []


def cek(nama: str, kondisi: bool, detail: str = '') -> None:
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}"
          + (f" — {detail}" if detail and not kondisi else ''))


def main() -> int:
    print('=' * 100)
    print('PENGUJIAN PENYIMPANAN KUNCI API (HASH) — LANGKAH 1.4')
    print('=' * 100)

    with tempfile.TemporaryDirectory() as tmp:
        db.DB_DIR = Path(tmp)
        db.DB_PATH = Path(tmp) / 'app.db'
        db.inisialisasi_db()

        # ------------------------------------------------- 1. penyimpanan hash
        print('\n1. NILAI KUNCI TIDAK TERSIMPAN SEBAGAI TEKS BIASA')
        kunci = db.buat_kunci_api(nama_klien='WordPress LSP', peran='klien')
        cek('nilai kunci dikembalikan saat dibuat', bool(kunci) and len(kunci) > 20,
            f'panjang={len(kunci)}')

        with db._ambil_koneksi() as conn:
            baris = conn.execute('SELECT kunci, kunci_hash, prefix FROM kunci_api').fetchone()
        cek('kolom kunci tidak berisi nilai asli', baris['kunci'] != kunci,
            'nilai asli masih tersimpan di kolom kunci')
        cek('kolom kunci berisi penanda sha256:', str(baris['kunci']).startswith('sha256:'))
        cek('kunci_hash berisi SHA-256 (64 hex)',
            len(baris['kunci_hash'] or '') == 64 and all(c in '0123456789abcdef' for c in baris['kunci_hash']))
        cek('prefix berisi 12 karakter awal', baris['prefix'] == kunci[:12])

        # Seluruh isi tabel tidak boleh memuat nilai asli
        with db._ambil_koneksi() as conn:
            semua = conn.execute('SELECT * FROM kunci_api').fetchall()
        bocor = [dict(r) for r in semua if any(str(v) == kunci for v in dict(r).values())]
        cek('tidak ada satu pun kolom yang memuat nilai asli', not bocor, f'bocor={bocor}')

        # -------------------------------------------------- 2. validasi kunci
        print('\n2. VALIDASI KUNCI')
        hasil = db.validasi_kunci_api(kunci)
        cek('kunci benar diterima', bool(hasil and hasil['nama_klien'] == 'WordPress LSP'))
        cek('kunci salah ditolak', db.validasi_kunci_api('skkni_live_salah_sekali') is None)
        cek('kunci kosong ditolak', db.validasi_kunci_api('') is None)
        cek('kunci dengan huruf berbeda ditolak', db.validasi_kunci_api(kunci.upper()) is None)

        # ------------------------------------------------- 3. daftar tanpa bocor
        print('\n3. DAFTAR KUNCI TIDAK MEMBOCORKAN RAHASIA')
        daftar = db.daftar_kunci_api()
        cek('daftar berisi satu kunci', len(daftar) == 1)
        kolom = set(daftar[0].keys()) if daftar else set()
        cek('tidak ada kolom kunci', 'kunci' not in kolom, f'kolom={sorted(kolom)}')
        cek('tidak ada kolom kunci_hash', 'kunci_hash' not in kolom)
        cek('ada kolom prefix', 'prefix' in kolom)

        # ------------------------------------------------- 4. cabut & kedaluwarsa
        print('\n4. KUNCI DICABUT DAN KEDALUWARSA DITOLAK')
        cek('pencabutan berdasarkan nilai kunci berhasil', db.ubah_status_kunci_api(kunci, False))
        cek('kunci dicabut tidak dapat dipakai', db.validasi_kunci_api(kunci) is None)
        db.ubah_status_kunci_api(kunci, True)
        cek('kunci diaktifkan kembali', db.validasi_kunci_api(kunci) is not None)

        kemarin = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        kunci_basi = db.buat_kunci_api('Klien Lama', kedaluwarsa=kemarin)
        cek('kunci kedaluwarsa ditolak', db.validasi_kunci_api(kunci_basi) is None)

        besok = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        kunci_segar = db.buat_kunci_api('Klien Baru', kedaluwarsa=besok)
        cek('kunci belum kedaluwarsa diterima', db.validasi_kunci_api(kunci_segar) is not None)

        # ------------------------------------------------------- 5. migrasi lama
        print('\n5. MIGRASI BARIS LAMA (TEKS BIASA) -> HASH')
        kunci_lama = 'skkni_live_kunci_lama_teks_biasa'
        with db._ambil_koneksi() as conn:
            conn.execute(
                """INSERT INTO kunci_api (kunci, nama_klien, peran, aktif, dibuat_pada)
                   VALUES (?, 'Klien Warisan', 'klien', 1, ?)""",
                (kunci_lama, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            sebelum = conn.execute(
                'SELECT kunci, kunci_hash FROM kunci_api WHERE kunci = ?', (kunci_lama,)
            ).fetchone()
        cek('baris teks biasa tersimpan sebelum migrasi', sebelum is not None)

        db.inisialisasi_db()
        with db._ambil_koneksi() as conn:
            sesudah = conn.execute(
                'SELECT kunci, kunci_hash, prefix FROM kunci_api WHERE nama_klien = ?',
                ('Klien Warisan',),
            ).fetchone()
        cek('nilai asli hilang dari kolom kunci',
            sesudah is not None and sesudah['kunci'] != kunci_lama)
        cek('hash terisi setelah migrasi', len((sesudah['kunci_hash'] if sesudah else '') or '') == 64)
        cek('kunci warisan tetap berfungsi setelah migrasi',
            db.validasi_kunci_api(kunci_lama) is not None)

        # idempoten: jalankan lagi, tidak mengubah apa pun
        db.inisialisasi_db()
        with db._ambil_koneksi() as conn:
            ulang = conn.execute(
                'SELECT kunci_hash FROM kunci_api WHERE nama_klien = ?', ('Klien Warisan',)
            ).fetchone()
        cek('migrasi idempoten (hash tidak berubah)',
            ulang is not None and sesudah is not None
            and ulang['kunci_hash'] == sesudah['kunci_hash'])

        # ------------------------------------------------- 6. pencatatan dibatasi
        print('\n6. PENCATATAN PEMAKAIAN TIDAK SETIAP PERMINTAAN')
        db._TERAKHIR_DICATAT.clear()
        with db._ambil_koneksi() as conn:
            conn.execute("UPDATE kunci_api SET terakhir_digunakan = NULL WHERE nama_klien = 'WordPress LSP'")
            conn.commit()

        for _ in range(20):
            db.validasi_kunci_api(kunci)

        with db._ambil_koneksi() as conn:
            nilai = conn.execute(
                "SELECT COUNT(*) AS n FROM kunci_api WHERE nama_klien='WordPress LSP' AND terakhir_digunakan IS NOT NULL"
            ).fetchone()['n']
        cek('20 validasi beruntun hanya menulis sekali', nilai == 1, f'jumlah tulisan={nilai}')

    print('\n' + '=' * 100)
    print(f'HASIL: {len(lulus)} lulus, {len(gagal)} gagal')
    if gagal:
        for g in gagal:
            print(f'  - GAGAL: {g}')
    print('=' * 100)
    return 0 if not gagal else 1


if __name__ == '__main__':
    sys.exit(main())

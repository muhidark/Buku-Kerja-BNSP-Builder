"""
Pengujian keamanan akun & kunci API (perbaikan T-02 / langkah 1.3).

Menguji pada basis data SEMENTARA (bukan data/app.db), sehingga tidak menyentuh
data kerja:

1. Basis data kosong -> hanya satu akun admin, kata sandi acak dicetak sekali
   di konsol, dan penanda wajib ganti sandi menyala.
2. Halaman login tidak memuat kata sandi apa pun.
3. Login dengan akun itu langsung diarahkan ke halaman ganti kata sandi.
4. Selama penanda menyala, tindakan pengubahan data DITAHAN (303 ke halaman
   ganti kata sandi), bukan hanya diberi peringatan.
5. Setelah kata sandi diganti, tindakan berjalan normal dan sesi lama mati.
6. Kunci API bawaan lama dibalas 401 dan tidak ada kunci yang dibuat otomatis.
"""

import contextlib
import io
import re
import sys
import tempfile
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
    print('PENGUJIAN KEAMANAN AKUN & KUNCI API — LANGKAH 1.3 (T-02)')
    print('=' * 100)

    with tempfile.TemporaryDirectory() as tmp:
        # Arahkan modul db ke basis data kosong SEBELUM app.main diimpor,
        # karena app.main memanggil db.inisialisasi_db() saat impor.
        db.DB_DIR = Path(tmp)
        db.DB_PATH = Path(tmp) / 'app.db'
        cek('basis data uji terpisah dari data kerja',
            db.DB_PATH.resolve().parent.name.startswith('tmp'),
            f'DB_PATH={db.DB_PATH}')

        keluaran = io.StringIO()
        with contextlib.redirect_stdout(keluaran):
            db.inisialisasi_db()
            from app.main import app  # noqa: PLC0415  (impor sengaja di dalam)
        konsol = keluaran.getvalue()

        # ------------------------------------------------- 1. akun pertama
        print('\n1. BASIS DATA KOSONG — SATU AKUN, SANDI ACAK, TAMPIL SEKALI')
        pengguna = db.daftar_pengguna()
        cek('hanya satu akun dibuat', len(pengguna) == 1, f'jumlah akun={len(pengguna)}')
        cek('akun pertama bernama admin', bool(pengguna and pengguna[0]['username'] == 'admin'))

        cocok = re.search(r'sandi\s*:\s*(\S+)', konsol)
        sandi_awal = cocok.group(1) if cocok else ''
        cek('kata sandi acak dicetak di konsol', bool(sandi_awal), 'pola "sandi : ..." tidak ditemukan')
        cek('kata sandi cukup panjang', len(sandi_awal) >= 12, f'panjang={len(sandi_awal)}')

        masuk = db.autentikasi('admin', sandi_awal) if sandi_awal else None
        cek('kata sandi dari konsol benar-benar berlaku', masuk is not None)
        cek('penanda wajib ganti sandi menyala', bool(masuk and masuk['must_change_password']))

        cek('tidak ada akun asesor bawaan',
            'asesor' not in {p['username'] for p in pengguna})
        cek('tidak ada kunci API dibuat otomatis', db.daftar_kunci_api() == [],
            f"jumlah kunci={len(db.daftar_kunci_api())}")

        # ------------------------------------------------- 2. halaman login
        print('\n2. HALAMAN LOGIN TIDAK MEMUAT KATA SANDI')
        from fastapi.testclient import TestClient  # noqa: PLC0415
        tamu = TestClient(app)
        halaman = tamu.get('/login')
        cek('halaman login terbuka', halaman.status_code == 200)
        for kata in ('admin123', 'asesor123', 'Akun Bawaan', 'password <code>'):
            cek(f'halaman login tidak memuat {kata!r}', kata not in halaman.text)

        # ------------------------------------------- 3. login dipaksa ganti
        print('\n3. LOGIN DIARAHKAN KE HALAMAN GANTI KATA SANDI')
        csrf = halaman.cookies.get('skkni_csrf') or ''
        r_login = tamu.post('/login', data={'csrf_token': csrf, 'username': 'admin',
                                           'password': sandi_awal},
                            follow_redirects=False)
        cek('login berhasil (303)', r_login.status_code == 303,
            f'status={r_login.status_code}')
        cek('diarahkan ke /akun/ganti-sandi',
            (r_login.headers.get('location') or '').startswith('/akun/ganti-sandi'),
            f"location={r_login.headers.get('location')!r}")
        sesi = r_login.cookies.get('skkni_session') or ''

        # ------------------------------------ 4. penanda benar-benar mengikat
        print('\n4. SELAMA PENANDA MENYALA, TINDAKAN DITAHAN')
        ber_sesi = TestClient(app)
        ber_sesi.cookies.set('skkni_session', sesi)
        csrf2 = ber_sesi.get('/skema').cookies.get('skkni_csrf') or ''

        # Halaman baca tetap terbuka (memang publik), tetapi harus menampilkan
        # peringatan bahwa kata sandi masih bawaan.
        r_dash = ber_sesi.get('/', follow_redirects=False)
        cek('halaman baca tetap terbuka dengan peringatan',
            r_dash.status_code == 200 and 'Ganti sekarang' in r_dash.text,
            f'status={r_dash.status_code}')

        r_aksi = ber_sesi.post('/skema/skema_apa_saja/periksa-ulang',
                               data={'csrf_token': csrf2}, follow_redirects=False)
        cek('POST tindakan ditahan (303 ke ganti sandi)',
            r_aksi.status_code == 303
            and str(r_aksi.headers.get('location', '')).startswith('/akun/ganti-sandi'),
            f"status={r_aksi.status_code} location={r_aksi.headers.get('location')!r}")

        r_api = ber_sesi.get('/api/unit/M.70MKT00.014.1/status', follow_redirects=False)
        cek('jalur /api tidak diblokir penanda (hanya baca)', r_api.status_code in (200, 404),
            f'status={r_api.status_code}')

        r_hal_ganti = ber_sesi.get('/akun/ganti-sandi')
        cek('halaman ganti sandi tetap terbuka', r_hal_ganti.status_code == 200)

        # ------------------------------------------ 5. ganti sandi & lanjutkan
        print('\n5. SETELAH KATA SANDI DIGANTI, APLIKASI NORMAL KEMBALI')
        sandi_baru = 'Sandi-Baru-Uji-2026'
        r_simpan = ber_sesi.post('/akun/ganti-sandi',
                                 data={'csrf_token': csrf2,
                                       'kata_sandi_lama': sandi_awal,
                                       'kata_sandi_baru': sandi_baru,
                                       'ulangi_kata_sandi': sandi_baru},
                                 follow_redirects=False)
        cek('ganti sandi berhasil (303 ke dashboard)',
            r_simpan.status_code == 303 and 'ganti-sandi' not in str(r_simpan.headers.get('location')),
            f"status={r_simpan.status_code} location={r_simpan.headers.get('location')!r}")

        sesi_baru = r_simpan.cookies.get('skkni_session') or ''
        cek('sesi lama dimatikan', bool(sesi_baru and sesi_baru != sesi))
        cek('sesi lama tidak berlaku lagi', db.ambil_pengguna_dari_sesi(sesi) is None)

        masuk_baru = db.autentikasi('admin', sandi_baru)
        cek('kata sandi baru berlaku', masuk_baru is not None)
        cek('penanda wajib ganti sandi sudah lepas',
            bool(masuk_baru and not masuk_baru['must_change_password']))
        cek('kata sandi lama tidak berlaku lagi', db.autentikasi('admin', sandi_awal) is None)

        lanjut = TestClient(app)
        lanjut.cookies.set('skkni_session', sesi_baru)
        r_dash2 = lanjut.get('/', follow_redirects=False)
        cek('dashboard terbuka setelah ganti sandi', r_dash2.status_code == 200,
            f'status={r_dash2.status_code}')

        # ------------------------------------------- 6. kunci API bawaan lama
        print('\n6. KUNCI API BAWAAN LAMA TIDAK BERLAKU')
        for kunci_lama in db.KUNCI_API_BAWAAN_LAMA:
            r = lanjut.get('/api/v1/status', headers={'X-API-Key': kunci_lama})
            cek(f'kunci {kunci_lama[:24]}... dibalas 401', r.status_code == 401,
                f'status={r.status_code}')

        # ----------------------------- 7. akun lama bersandi publik ditandai
        print('\n7. AKUN LAMA YANG MASIH MEMAKAI SANDI PUBLIK DITANDAI')
        # Deteksi dilakukan per username yang pernah memakai sandi publik.
        db.tambah_pengguna('asesor', 'asesor123', 'Asesor Lama', peran='asesor')
        db.inisialisasi_db()
        hasil = db.autentikasi('asesor', 'asesor123')
        cek('akun bersandi publik otomatis wajib ganti sandi',
            bool(hasil and hasil['must_change_password']))

    print('\n' + '=' * 100)
    print(f'HASIL: {len(lulus)} lulus, {len(gagal)} gagal')
    if gagal:
        for g in gagal:
            print(f'  - GAGAL: {g}')
    print('=' * 100)
    return 0 if not gagal else 1


def test_keamanan_akun():
    assert main() == 0


if __name__ == '__main__':
    sys.exit(main())

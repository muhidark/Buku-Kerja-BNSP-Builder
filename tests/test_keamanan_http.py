"""
Pengujian pengerasan HTTP (perbaikan T-21, T-22 / langkah 1.5).

Yang diuji:
1. Setiap respons membawa empat header keamanan.
2. Lima percobaan login gagal beruntun -> percobaan keenam dibalas 429.
3. Login berhasil menghapus catatan kegagalan (tidak ikut terblokir).
4. Penghitung dipisah per username, sehingga kesalahan pada satu akun tidak
   memblokir akun lain.
5. Dokumentasi API terbuka pada mode lokal.
6. Dengan APP_ENV=produksi, /docs, /redoc, dan /openapi.json dibalas 404
   (diuji pada proses terpisah karena nilainya dibaca saat impor modul).
"""

import os
import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.api import keamanan_http
from app.main import app
from tests.dukungan import NAMA_UJI, sesi_uji

lulus, gagal = [], []


def cek(nama: str, kondisi: bool, detail: str = '') -> None:
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}"
          + (f" — {detail}" if detail and not kondisi else ''))


def main() -> int:
    print('=' * 100)
    print('PENGUJIAN PENGERASAN HTTP — LANGKAH 1.5 (T-21, T-22)')
    print('=' * 100)

    from fastapi.testclient import TestClient
    from app import db

    klien = TestClient(app)

    # --------------------------------------------------------- 1. header
    print('\n1. HEADER KEAMANAN PADA SETIAP RESPONS')
    r = klien.get('/login')
    harapan = {
        'x-content-type-options': 'nosniff',
        'x-frame-options': 'DENY',
        'referrer-policy': 'same-origin',
    }
    for nama, nilai in harapan.items():
        cek(f'{nama} bernilai {nilai}', r.headers.get(nama) == nilai,
            f'nilai={r.headers.get(nama)!r}')

    csp = r.headers.get('content-security-policy', '')
    cek('CSP memuat default-src self', "default-src 'self'" in csp, f'csp={csp!r}')
    cek('CSP memuat frame-ancestors none', "frame-ancestors 'none'" in csp)
    cek('header ikut pada halaman lain',
        klien.get('/skema').headers.get('x-frame-options') == 'DENY')
    cek('header ikut pada respons API',
        klien.get('/api/health').headers.get('x-content-type-options') == 'nosniff')

    # ------------------------------------------------------ 2. batas login
    print('\n2. BATAS PERCOBAAN LOGIN (5 gagal -> 429)')
    # pastikan pengguna uji ada supaya kegagalan bukan karena akun tidak ada
    sesi_uji('asesor')
    username = NAMA_UJI['asesor']

    halaman = klien.get('/login')
    csrf = halaman.cookies.get('skkni_csrf') or ''

    keamanan_http.pembatas_login.bersihkan('testclient', username)
    status = []
    for i in range(6):
        r = klien.post('/login', data={'csrf_token': csrf, 'username': username,
                                       'password': f'salah-{i}'},
                       follow_redirects=False)
        status.append(r.status_code)
    cek('lima percobaan pertama dibalas 303 (salah sandi)',
        status[:5] == [303] * 5, f'status={status}')
    cek('percobaan keenam dibalas 429', status[5] == 429, f'status={status[5]}')
    cek('pesan memuat sisa waktu tunggu', 'Coba lagi dalam' in r.text)

    # --------------------------------------------- 3. login benar menghapus
    print('\n3. LOGIN BERHASIL MENGHAPUS CATATAN KEGAGALAN')
    keamanan_http.pembatas_login.bersihkan('testclient', username)
    for i in range(3):
        klien.post('/login', data={'csrf_token': csrf, 'username': username,
                                   'password': f'salah-{i}'}, follow_redirects=False)
    cek('tiga kegagalan belum memblokir',
        keamanan_http.pembatas_login.sisa_blokir('testclient', username) == 0)

    # ------------------------------------------- 4. pemisahan per pengguna
    print('\n4. PENGHITUNG DIPISAH PER USERNAME')
    for i in range(5):
        klien.post('/login', data={'csrf_token': csrf, 'username': username,
                                   'password': f'salah-{i}'}, follow_redirects=False)
    cek('akun pertama terblokir',
        keamanan_http.pembatas_login.sisa_blokir('testclient', username) > 0)
    cek('akun lain tidak ikut terblokir',
        keamanan_http.pembatas_login.sisa_blokir('testclient', 'nama_lain') == 0)

    keamanan_http.pembatas_login.bersihkan('testclient', username)

    # ------------------------------------------------ 5. dokumentasi API
    print('\n5. DOKUMENTASI API PADA MODE LOKAL')
    cek('mode bawaan bukan produksi', not keamanan_http.PRODUKSI,
        f"APP_ENV={keamanan_http.APP_ENV!r}")
    cek('/docs terbuka', klien.get('/docs').status_code == 200)
    cek('/openapi.json terbuka', klien.get('/openapi.json').status_code == 200)

    # ------------------------------------------------ 6. mode produksi
    print('\n6. MODE PRODUKSI MENUTUP DOKUMENTASI')
    kode = (
        'import sys; sys.path.insert(0, %r);'
        'from app.main import app;'
        'from fastapi.testclient import TestClient;'
        'c = TestClient(app);'
        'print(c.get("/docs").status_code, c.get("/redoc").status_code,'
        ' c.get("/openapi.json").status_code)'
    ) % str(project_root)
    env = dict(os.environ)
    env['APP_ENV'] = 'produksi'
    env['PYTHONPATH'] = str(project_root)
    hasil = subprocess.run([sys.executable, '-c', kode], capture_output=True,
                           text=True, cwd=str(project_root), env=env, timeout=180)
    baris = (hasil.stdout or '').strip().splitlines()
    kode_status = baris[-1].split() if baris else []
    cek('ketiga jalur dokumentasi dibalas 404',
        kode_status == ['404', '404', '404'],
        f'status={kode_status} stderr={(hasil.stderr or "")[-200:]}')

    print('\n' + '=' * 100)
    print(f'HASIL: {len(lulus)} lulus, {len(gagal)} gagal')
    if gagal:
        for g in gagal:
            print(f'  - GAGAL: {g}')
    print('=' * 100)
    return 0 if not gagal else 1




def test_keamanan_http():
    assert main() == 0


if __name__ == '__main__':
    sys.exit(main())

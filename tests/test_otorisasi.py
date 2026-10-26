"""
Pengujian otorisasi endpoint POST (perbaikan T-01 / langkah 1.2).

Sebelum perbaikan, hanya POST /skkni/{doc_id}/regulasi yang memeriksa peran;
12 endpoint POST lain memproses perubahan tanpa sesi sama sekali.

Yang diuji:
1. Setiap endpoint POST tanpa sesi harus DITOLAK oleh penjaga akses: 303 ke
   /login untuk halaman HTML, 403 untuk jalur /api.
2. Sesi asesor ditolak (403) pada endpoint khusus admin.
3. Sesi admin tetap lolos penjaga pada endpoint khusus admin.
4. Sesi asesor tetap lolos penjaga pada endpoint kerja biasa.
5. Parameter `next` tidak boleh menjadi open redirect.

Catatan: penolakan 403 di sini dipilah menjadi dua sebab — penolakan penjaga
akses (sesi/peran) dan penolakan token CSRF. Hanya yang pertama dihitung
sebagai kegagalan otorisasi; yang kedua berarti penjaga sudah meloloskan
permintaan dan lapisan berikutnya (CSRF) yang bekerja.
"""

import re
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app import library, schema_library as sl
from app.main import app
from tests.dukungan import klien

lulus, gagal = [], []

#: Potongan pesan yang hanya muncul bila penjaga akses yang menolak.
PESAN_PENJAGA = (
    'sesi tidak ditemukan',
    'sesi tidak ada',
    'peran tidak berwenang',
    'hanya untuk peran',
)


def cek(nama: str, kondisi: bool, detail: str = '') -> None:
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}"
          + (f" — {detail}" if detail and not kondisi else ''))


#: (metode, path, peran minimum, keterangan)
ENDPOINT = [
    ('POST', '/skkni/upload', 'admin', 'Unggah PDF SKKNI'),
    ('POST', '/skkni/{doc}/regulasi', 'admin', 'Kurasi status regulasi Kemnaker'),
    ('POST', '/skkni/{doc}/verifikasi', 'login', 'Verifikasi manual unit SKKNI'),
    ('POST', '/skema/upload', 'admin', 'Unggah dokumen skema'),
    ('POST', '/skema/{sid}/periksa-ulang', 'login', 'Pencocokan ulang unit skema'),
    ('POST', '/skema/{sid}/ekstrak', 'login', 'Ekstrak unit ke JSON'),
    ('POST', '/skema/{sid}/muk', 'login', 'Simpan konfigurasi MUK'),
    ('POST', '/skema/{sid}/verifikasi', 'login', 'Verifikasi manual unit skema'),
    ('POST', '/skema/{sid}/unit/{kode}/koreksi', 'admin', 'Simpan koreksi elemen/KUK'),
    ('POST', '/skema/{sid}/unit/{kode}/koreksi/kembalikan', 'admin', 'Batalkan koreksi unit'),
    ('POST', '/hasil/generate', 'login', 'Buat dokumen Word'),
]


def bentangkan(pola: str, sid: str, doc: str, kode: str) -> str:
    return pola.format(sid=sid, doc=doc, kode=kode)


def token_csrf(client) -> str:
    """Mengambil token CSRF dari halaman mana pun (nilainya = cookie)."""
    r = client.get('/skema')
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    return m.group(1) if m else ''


def ditolak_penjaga(r) -> bool:
    """True bila penolakan datang dari penjaga sesi/peran, bukan dari CSRF/validasi."""
    if r.status_code in (401,):
        return True
    if r.status_code == 303 and '/login' in (r.headers.get('location') or ''):
        return True
    if r.status_code != 403:
        return False
    isi = (r.text or '').lower()
    return any(p in isi for p in PESAN_PENJAGA)


def main() -> int:
    print('=' * 100)
    print('PENGUJIAN OTORISASI ENDPOINT POST — LANGKAH 1.2 (T-01)')
    print('=' * 100)

    daftar_skema = sl.daftar_skema()
    if not daftar_skema:
        print('ERROR: belum ada skema terdaftar, uji tidak dapat dijalankan.')
        return 1
    sid = daftar_skema[0]['id']

    daftar_dok = library.daftar_dokumen()
    doc = daftar_dok[0]['id'] if daftar_dok else 'tidak_ada_dokumen'
    unit = (daftar_skema[0].get('units') or [{}])[0].get('kode_unit', 'M.70MKT00.014.1')

    # ---------------------------------------------------------------- 1. tamu
    print('\n1. TANPA SESI — SEMUA HARUS DITOLAK')
    tamu = klien(app, peran=None)
    csrf_tamu = token_csrf(tamu)
    for metode, pola, _, nama in ENDPOINT:
        path = bentangkan(pola, sid, doc, unit)
        # CSRF sengaja disertakan agar penolakan pasti datang dari penjaga sesi.
        r = tamu.request(metode, path, data={'csrf_token': csrf_tamu},
                         follow_redirects=False)
        cek(f'{nama} ditolak tanpa sesi', ditolak_penjaga(r),
            f'status={r.status_code} location={r.headers.get("location")!r}')

    # -------------------------------------------------------------- 2. asesor
    print('\n2. SESI ASESOR — ENDPOINT KHUSUS ADMIN HARUS 403')
    asesor = klien(app, 'asesor')
    csrf_asesor = token_csrf(asesor)
    for metode, pola, minimal, nama in ENDPOINT:
        if minimal != 'admin':
            continue
        path = bentangkan(pola, sid, doc, unit)
        r = asesor.request(metode, path, data={'csrf_token': csrf_asesor},
                           follow_redirects=False)
        cek(f'{nama} ditolak untuk asesor', ditolak_penjaga(r),
            f'status={r.status_code} location={r.headers.get("location")!r}')

    # --------------------------------------------------------------- 3. admin
    print('\n3. SESI ADMIN — HARUS LOLOS PENJAGA PADA ENDPOINT ADMIN')
    # Sengaja memakai ID yang tidak ada: penjaga akses sudah diuji, dan route
    # berhenti dengan pesan "tidak ditemukan" sehingga tidak ada efek samping.
    sid_kosong, doc_kosong = 'skema_uji_tidak_ada', 'dokumen_uji_tidak_ada'
    admin = klien(app, 'admin')
    csrf_admin = token_csrf(admin)
    for metode, pola, minimal, nama in ENDPOINT:
        if minimal != 'admin':
            continue
        path = bentangkan(pola, sid_kosong, doc_kosong, unit)
        r = admin.request(metode, path, data={'csrf_token': csrf_admin},
                          follow_redirects=False)
        cek(f'{nama} lolos penjaga untuk admin', not ditolak_penjaga(r),
            f'status={r.status_code} location={r.headers.get("location")!r}')

    # ------------------------------------------------------ 4. asesor (kerja)
    print('\n4. SESI ASESOR — HARUS LOLOS PENJAGA PADA ENDPOINT KERJA')
    for metode, pola, minimal, nama in ENDPOINT:
        if minimal == 'admin':
            continue
        path = bentangkan(pola, sid_kosong, doc_kosong, unit)
        r = asesor.request(metode, path, data={'csrf_token': csrf_asesor},
                           follow_redirects=False)
        cek(f'{nama} lolos penjaga untuk asesor', not ditolak_penjaga(r),
            f'status={r.status_code} location={r.headers.get("location")!r}')

    # --------------------------------------------------- 5. halaman login aman
    print('\n5. PARAMETER next TIDAK BOLEH JADI OPEN REDIRECT')
    for jahat in ('https://jahat.example/', '//jahat.example/', '/\\jahat.example'):
        r = admin.get(f'/login?next={jahat}', follow_redirects=False)
        isi = r.text if r.status_code == 200 else ''
        cek(f'next={jahat!r} tidak diteruskan', 'jahat.example' not in isi,
            'nilai jahat muncul di halaman login')

    print('\n' + '=' * 100)
    print(f'HASIL: {len(lulus)} lulus, {len(gagal)} gagal')
    if gagal:
        for g in gagal:
            print(f'  - GAGAL: {g}')
    print('=' * 100)
    return 0 if not gagal else 1


if __name__ == '__main__':
    sys.exit(main())

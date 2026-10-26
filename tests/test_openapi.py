"""
Pengujian skema keamanan OpenAPI / Swagger (perbaikan T-04 / langkah 2.2).

Sebelum perbaikan, `components.securitySchemes` kosong sehingga Swagger UI tidak
menampilkan tombol Authorize dan dokumentasi API tidak bisa dipakai untuk
mencoba endpoint.

Catatan: tombol Authorize dibuat oleh JavaScript Swagger UI dari isi
`/openapi.json`, bukan tertulis di HTML `/docs`. Karena itu bukti yang
dikumpulkan di sini adalah: skema keamanan terdaftar, setiap operasi /api/v1
mendeklarasikan security, dan ketiga cara pengiriman kunci benar-benar bekerja.
"""

import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app import db
from app.main import app
from tests.dukungan import klien

lulus, gagal = [], []


def cek(nama: str, kondisi: bool, detail: str = '') -> None:
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}"
          + (f" — {detail}" if detail and not kondisi else ''))


def main() -> int:
    print('=' * 100)
    print('PENGUJIAN SKEMA KEAMANAN OPENAPI / SWAGGER — LANGKAH 2.2 (T-04)')
    print('=' * 100)

    klien_uji = klien(app, 'admin')

    # ------------------------------------------------- 1. skema keamanan
    print('\n1. components.securitySchemes TERISI')
    r = klien_uji.get('/openapi.json')
    cek('/openapi.json dibalas 200', r.status_code == 200, f'status={r.status_code}')
    spesifikasi = r.json()
    skema = spesifikasi.get('components', {}).get('securitySchemes', {})
    cek('securitySchemes tidak kosong', bool(skema), 'masih kosong')

    api_key = skema.get('APIKeyHeader', {})
    cek('skema X-API-Key terdaftar', api_key.get('type') == 'apiKey', f'{api_key}')
    cek('X-API-Key dikirim lewat header', api_key.get('in') == 'header', f"{api_key.get('in')!r}")
    cek('nama parameternya X-API-Key', api_key.get('name') == 'X-API-Key', f"{api_key.get('name')!r}")

    bearer = skema.get('BearerAuth', {})
    cek('skema Bearer terdaftar', bearer.get('type') == 'http', f'{bearer}')
    cek('Bearer memakai scheme bearer', bearer.get('scheme') == 'bearer', f"{bearer.get('scheme')!r}")

    # ------------------------------------------------ 2. security per operasi
    print('\n2. SETIAP OPERASI /api/v1 MENDEKLARASIKAN SECURITY')
    operasi_api = []
    for path, metode in spesifikasi.get('paths', {}).items():
        if not path.startswith('/api/v1'):
            continue
        for m, op in metode.items():
            if m in ('get', 'post', 'put', 'delete', 'patch'):
                operasi_api.append((m.upper(), path, op.get('security')))
    cek('ada operasi /api/v1 yang didokumentasikan', len(operasi_api) >= 9,
        f'jumlah={len(operasi_api)}')

    tanpa_security = [f'{m} {p}' for m, p, sec in operasi_api if not sec]
    cek('tidak ada operasi /api/v1 tanpa security', not tanpa_security,
        f'tanpa security: {tanpa_security}')

    pakai_bearer = [f'{m} {p}' for m, p, sec in operasi_api
                    if sec and any('BearerAuth' in s for s in sec)]
    cek('skema Bearer tercantum pada operasi', len(pakai_bearer) == len(operasi_api),
        f'{len(pakai_bearer)} dari {len(operasi_api)}')

    # -------------------------------------------------------- 3. /docs hidup
    print('\n3. HALAMAN SWAGGER TERSEDIA')
    cek('/docs dibalas 200', klien_uji.get('/docs').status_code == 200)
    cek('/redoc dibalas 200', klien_uji.get('/redoc').status_code == 200)

    # ---------------------------------------------- 4. tiga cara kirim kunci
    print('\n4. KETIGA CARA PENGIRIMAN KUNCI BEKERJA')
    kunci = db.buat_kunci_api(nama_klien='Uji OpenAPI', peran='klien',
                              kunci_khusus='skkni_test_openapi_999')
    try:
        r = klien_uji.get('/api/v1/status', headers={'X-API-Key': kunci})
        cek('header X-API-Key -> 200', r.status_code == 200, f'status={r.status_code}')

        r = klien_uji.get('/api/v1/status', headers={'Authorization': f'Bearer {kunci}'})
        cek('Authorization: Bearer -> 200', r.status_code == 200, f'status={r.status_code}')

        r = klien_uji.get(f'/api/v1/status?api_key={kunci}')
        cek('query ?api_key= -> 200', r.status_code == 200, f'status={r.status_code}')

        # Kompatibilitas: kunci tanpa awalan "Bearer "
        r = klien_uji.get('/api/v1/status', headers={'Authorization': kunci})
        cek('Authorization tanpa awalan Bearer -> 200', r.status_code == 200,
            f'status={r.status_code}')

        r = klien_uji.get('/api/v1/status', headers={'X-API-Key': 'kunci_palsu_xyz'})
        cek('kunci salah -> 401', r.status_code == 401, f'status={r.status_code}')

        r = klien_uji.get('/api/v1/status')
        cek('tanpa kunci -> 401', r.status_code == 401, f'status={r.status_code}')
        detail = ''
        try:
            detail = r.json().get('detail', '')
        except Exception:
            pass
        cek('pesan 401 memandu cara mengirim kunci',
            'X-API-Key' in detail or 'Bearer' in detail, f'detail={detail!r}')
    finally:
        with db._ambil_koneksi() as conn:
            conn.execute("DELETE FROM kunci_api WHERE nama_klien = 'Uji OpenAPI'")
            conn.commit()

    print('\n' + '=' * 100)
    print(f'HASIL: {len(lulus)} lulus, {len(gagal)} gagal')
    if gagal:
        for g in gagal:
            print(f'  - GAGAL: {g}')
    print('=' * 100)
    return 0 if not gagal else 1


def test_openapi():
    assert main() == 0


if __name__ == '__main__':
    sys.exit(main())

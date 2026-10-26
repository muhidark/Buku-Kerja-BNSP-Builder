"""
Pengujian API dan unduhan dokumen Word (Fase 4E).

Fokus: riwayat dokumen, endpoint unduh, ID aman, path traversal, dan CSRF.
"""

import json
import re
import shutil
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from fastapi.testclient import TestClient
from app import schema_library as sl
from app.main import app
from tests.dukungan import klien
from app.services import document_service as ds

DOC_UJI = project_root / 'output' / 'web_documents' / '_uji_dl'
META_UJI = project_root / 'data' / 'web_documents' / '_uji_dl'

lulus, gagal = [], []


def cek(nama, kondisi, detail=''):
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}" + (f" — {detail}" if detail and not kondisi else ''))


def pasang_uji():
    for d in (DOC_UJI, META_UJI):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
    ds.DOC_DIR = DOC_UJI
    ds.META_DIR = META_UJI


def bersihkan():
    ds.DOC_DIR = project_root / 'output' / 'web_documents'
    ds.META_DIR = project_root / 'data' / 'web_documents'
    for d in (DOC_UJI, META_UJI):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)


def main():
    print("=" * 100)
    print("PENGUJIAN UNDUHAN DOKUMEN WORD — FASE 4E")
    print("=" * 100)

    sid = next((d['id'] for d in sl.daftar_skema()
                if d['nama_skema'] == 'SOCIAL MEDIA MARKETING'), None)
    if not sid:
        print('ERROR: skema uji tidak tersedia.')
        return 1

    pasang_uji()
    skema = sl.ambil_skema(sid)
    kode = [u['kode_unit'] for u in skema['units']]
    meta = ds.buat_dokumen(sid, [kode[0], kode[2]], setujui_draft=True)
    did = meta['id']

    client = klien(app, 'admin')
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get('/skema').text).group(1)

    # -------------------------------------------------------------- 1 riwayat
    print("\n1. HALAMAN RIWAYAT")
    r = client.get('/hasil')
    cek('/hasil 200', r.status_code == 200)
    cek('nama skema tampil', (meta['nama_skema'] or '') in r.text)
    cek('status dokumen tampil', 'siap ditinjau' in r.text or 'draft perlu verifikasi' in r.text)
    cek('tautan unduh ada', f"/api/documents/{did}/download" in r.text)
    cek('tautan detail ada', f"/hasil/{did}" in r.text)
    cek('tidak ada path absolut di halaman', str(project_root) not in r.text)

    r = client.get(f'/hasil/{did}')
    cek('/hasil/{id} 200', r.status_code == 200)
    cek('detail memuat jumlah unit', str(meta['jumlah_unit']) in r.text)
    cek('detail memuat kode unit', kode[0] in r.text)
    cek('detail punya tombol unduh', f"/api/documents/{did}/download" in r.text)

    # ------------------------------------------------------------------ 2 API
    print("\n2. API RIWAYAT & METADATA")
    api = client.get('/api/documents')
    cek('API daftar 200', api.status_code == 200)
    data = api.json()
    cek('dokumen tercatat', any(d['id'] == did for d in data['dokumen']))
    cek('tidak ada path absolut di API', str(project_root) not in api.text)

    satu = client.get(f'/api/documents/{did}')
    cek('API detail 200', satu.status_code == 200)
    isi = satu.json()
    cek('metadata sesuai', isi['id'] == did and isi['jumlah_unit'] == 2)
    cek('metadata memuat hash sumber', all(u.get('sha256_pdf') for u in isi['units']))

    # -------------------------------------------------------------- 3 unduh
    print("\n3. UNDUHAN")
    r = client.get(f'/api/documents/{did}/download')
    cek('unduh 200', r.status_code == 200, str(r.status_code))
    cek('content-type DOCX', 'wordprocessingml' in r.headers.get('content-type', ''))
    cek('attachment + nama berkas',
        'attachment' in r.headers.get('content-disposition', '')
        and '.docx' in r.headers.get('content-disposition', ''))
    cek('isi ZIP/DOCX valid', r.content[:4] == b'PK\x03\x04', str(r.content[:4]))
    cek('ukuran wajar (>10 KB)', len(r.content) > 10000, str(len(r.content)))

    # ------------------------------------------------------ 4 ID & traversal
    print("\n4. ID AMAN & PATH TRAVERSAL")
    cek('ID pendek ditolak', client.get('/api/documents/abc/download').status_code == 404)
    cek('ID tidak dikenal 404', client.get('/api/documents/' + 'f' * 32 + '/download').status_code == 404)
    cek('ID huruf besar 404', client.get('/api/documents/' + did.upper() + '/download').status_code == 404)
    cek('traversal URL ditolak',
        client.get('/api/documents/..%2f..%2fetc%2fpasswd/download').status_code in (404, 400))

    # metadata dengan path di luar direktori
    jahat = dict(meta, id='a' * 32, berkas_docx='../../etc/passwd')
    (META_UJI / f"{jahat['id']}.json").write_text(json.dumps(jahat), encoding='utf-8')
    r = client.get(f"/api/documents/{'a' * 32}/download")
    cek('metadata dengan path luar ditolak', r.status_code in (400, 404), str(r.status_code))
    (META_UJI / f"{jahat['id']}.json").unlink()

    # berkas hilang dari disk
    path_docx = project_root / meta['berkas_docx']
    isi_asli = path_docx.read_bytes()
    path_docx.unlink()
    cek('berkas hilang -> 404', client.get(f'/api/documents/{did}/download').status_code == 404)
    path_docx.write_bytes(isi_asli)
    cek('berkas dipulihkan -> 200', client.get(f'/api/documents/{did}/download').status_code == 200)

    # ------------------------------------------------------------- 5 CSRF
    print("\n5. PROTEKSI CSRF")
    payload = {'schema_id': sid, 'semua_unit': True, 'draft': True}
    cek('API tanpa token 403',
        client.post('/api/documents/generate', json=payload).status_code == 403)
    cek('API token salah 403',
        client.post('/api/documents/generate', json={**payload, 'csrf_token': 'palsu'},
                    headers={'x-csrf-token': 'palsu'}).status_code == 403)
    cek('form tanpa token 403',
        client.post('/hasil/generate', data={'schema_id': sid},
                    follow_redirects=False).status_code == 403)

    r = client.post('/api/documents/generate',
                    json={**payload, 'csrf_token': token},
                    headers={'x-csrf-token': token})
    cek('API dengan token berhasil', r.status_code == 200, str(r.status_code))
    baru = r.json()
    cek('dokumen baru tercatat', ds.ambil_dokumen(baru['id']) is not None)

    # --------------------------------------------------- 6 persistensi
    print("\n6. PERSISTENSI RIWAYAT")
    cek('metadata ada di disk', (META_UJI / f'{did}.json').exists())
    client2 = klien(app, 'admin')
    r = client2.get('/hasil')
    cek('riwayat terbaca pada klien baru', r.status_code == 200 and meta['nama_skema'] in r.text)
    cek('dua dokumen tercatat', len(ds.daftar_dokumen()) == 2, str(len(ds.daftar_dokumen())))

    print("\n7. HALAMAN LAIN TETAP BEKERJA")
    for p in ('/', '/skema', '/skkni', '/unit', '/ekstraksi'):
        cek(f'{p} 200', client.get(p).status_code == 200)

    bersihkan()
    print("\n" + "=" * 100)
    print(f"HASIL: {len(lulus)} lulus, {len(gagal)} gagal")
    if gagal:
        for g in gagal:
            print(f"  - {g}")
    print("=" * 100)
    return 0 if not gagal else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    finally:
        bersihkan()

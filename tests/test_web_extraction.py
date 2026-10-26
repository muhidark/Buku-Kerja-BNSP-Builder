"""
Pengujian ekstraksi dari browser + job manager (Fase 4D).

Job dan JSON hasil ditulis ke direktori uji (`data/jobs/_uji`,
`data/json/browser_extraction/_uji`) agar tidak mengganggu data produksi.
"""

import hashlib
import json
import re
import shutil
import sys
import time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from fastapi.testclient import TestClient
from app import jobs, schema_library as sl
from app.main import app

UJI_DIR = project_root / 'data' / 'jobs' / '_uji'
JSON_UJI = project_root / 'data' / 'json' / 'browser_extraction' / '_uji'
SKEMA = project_root / 'data' / 'skema' / '21. Content Creator.docx'

lulus, gagal = [], []


def cek(nama, kondisi, detail=''):
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}" + (f" — {detail}" if detail and not kondisi else ''))


def pasang_direktori_uji():
    for d in (UJI_DIR, JSON_UJI):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
    jobs.JOBS_DIR = UJI_DIR
    jobs.JSON_OUT = JSON_UJI


def bersihkan():
    jobs.JOBS_DIR = project_root / 'data' / 'jobs'
    jobs.JSON_OUT = project_root / 'data' / 'json' / 'browser_extraction'
    for d in (UJI_DIR, JSON_UJI):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)


def token_csrf(client):
    m = re.search(r'name="csrf_token" value="([^"]+)"', client.get('/skema').text)
    return m.group(1) if m else ''


def skema_uji(client) -> dict:
    for d in client.get('/api/skema').json()['skema']:
        if d['nama_skema'] == 'CONTENT CREATOR':
            return d
    raise SystemExit('Skema CONTENT CREATOR tidak ada di perpustakaan.')


def tunggu(client, jid, batas=120):
    mulai = time.time()
    while time.time() - mulai < batas:
        j = client.get(f'/api/jobs/{jid}').json()
        if j.get('status') not in ('menunggu', 'berjalan'):
            return j
        time.sleep(0.4)
    return client.get(f'/api/jobs/{jid}').json()


def main():
    print("=" * 100)
    print("PENGUJIAN EKSTRAKSI BROWSER — FASE 4D")
    print("=" * 100)

    pasang_direktori_uji()
    client = TestClient(app)
    token = token_csrf(client)
    skema = skema_uji(client)
    sid = skema['id']
    asli = hashlib.sha256(SKEMA.read_bytes()).hexdigest()
    print(f"\nSkema: {skema['nama_skema']} | unit: {skema['jumlah_unit']} | id: {sid}")

    # ---------------------------------------------------------- 1 satu unit
    print("\n1. EKSTRAK SATU UNIT")
    kode = 'J.63OPR00.009.2'
    r = client.post(f'/skema/{sid}/ekstrak',
                    data={'csrf_token': token, 'kode_unit': kode},
                    follow_redirects=False)
    cek('redirect ke halaman job', r.status_code == 303 and '/job/' in r.headers.get('location', ''),
        str(r.status_code))
    jid = r.headers['location'].rsplit('/', 1)[-1]
    cek('ID job 32 heksadesimal', re.fullmatch(r'[0-9a-f]{32}', jid) is not None)

    job = tunggu(client, jid)
    cek('job selesai', job.get('status') == 'selesai', str(job.get('status')))
    cek('mode satu unit', job.get('mode') == 'satu_unit')
    cek('progres 1/1', job['progress'] == {'total': 1, 'selesai': 1, 'gagal': 0},
        str(job['progress']))

    u = job['units'][0]
    cek('unit selesai', u['status'] == 'selesai', str(u['status']))
    cek('elemen dan KUK terisi', u['elemen'] == 3 and u['kuk'] == 9,
        f"{u['elemen']}/{u['kuk']}")
    cek('validasi struktur lolos', u['validasi_struktur'] == 'valid_struktur',
        str(u['validasi_struktur']))
    cek('validasi kelengkapan lolos', u['validasi_kelengkapan'] == 'valid_kelengkapan',
        str(u['validasi_kelengkapan']))
    cek('halaman 0-based tercatat', u['halaman_pdf_0based'] == 39, str(u['halaman_pdf_0based']))

    # ---------------------------------------------------------- 2 JSON hasil
    print("\n2. BERKAS JSON HASIL")
    berkas = project_root / u['berkas']
    cek('berkas JSON ada', berkas.exists(), u['berkas'])
    isi = json.loads(berkas.read_text(encoding='utf-8'))
    cek('kunci utama lengkap',
        all(k in isi for k in ('kode_unit', 'judul_unit', 'elemen_kompetensi',
                               'batasan_variabel', 'panduan_penilaian',
                               'validasi_kelengkapan', 'metadata_sumber')))
    cek('KUK sesuai hasil ekstraksi',
        sum(len(e['kuk']) for e in isi['elemen_kompetensi']) == 9)
    vk = isi['validasi_kelengkapan']
    cek('blok validasi kelengkapan tersimpan', vk['status'] == 'valid_kelengkapan', str(vk.get('status')))
    cek('nomor KUK PDF tercatat', len(vk['kuk_pdf']) == 9, str(len(vk.get('kuk_pdf', []))))
    cek('tidak ada nomor hilang', vk['kuk_hilang'] == [])
    cek('metadata sumber menyebut PDF', 'SKKNI' in (isi['metadata_sumber'] or {}).get('nama_dokumen', ''))
    cek('jejak ekstraksi browser', (isi.get('sumber_ekstraksi') or {}).get('jalur', '').startswith('browser'))

    # ------------------------------------------------------------ 3 preview
    print("\n3. PREVIEW HASIL")
    r = client.get(f'/skema/{sid}/unit/{kode}')
    cek('preview 200', r.status_code == 200)
    cek('tabel elemen/KUK tampil', 'Kriteria Unjuk Kerja' in r.text)
    cek('batasan variabel tampil', 'Batasan Variabel' in r.text)
    cek('panduan penilaian tampil', 'Panduan Penilaian' in r.text)
    cek('badge validasi tampil', 'valid kelengkapan' in r.text)
    cek('halaman 1-based ditampilkan', '(1-based)' in r.text)

    r = client.get(f'/skema/{sid}/unit/J.63OPR00.007.2')
    cek('unit belum diekstrak menampilkan pesan', 'belum diekstrak' in r.text, r.text[:120])

    cek('kode tidak sah 404', client.get(f'/skema/{sid}/unit/../../etc/passwd').status_code in (404, 400))

    # ------------------------------------------------------- 4 seluruh unit
    print("\n4. EKSTRAK SELURUH UNIT")
    r = client.post(f'/skema/{sid}/ekstrak',
                    data={'csrf_token': token, 'kode_unit': ''}, follow_redirects=False)
    jid2 = r.headers['location'].rsplit('/', 1)[-1]
    job2 = tunggu(client, jid2, batas=240)
    cek('job batch selesai', job2.get('status') in ('selesai', 'selesai_sebagian'),
        str(job2.get('status')))
    cek('total unit = 10', job2['progress']['total'] == 10, str(job2['progress']))
    cek('semua unit selesai', job2['progress']['selesai'] == 10, str(job2['progress']))
    cek('tidak ada kegagalan', job2['progress']['gagal'] == 0)
    cek('mode seluruh unit', job2.get('mode') == 'seluruh_unit')

    hasil = [u for u in job2['units'] if u['status'] == 'selesai']
    cek('10 unit punya JSON', len(hasil) == 10, str(len(hasil)))
    cek('semua JSON ada di disk', all((project_root / u['berkas']).exists() for u in hasil))
    cek('semua unit punya elemen', all(u['elemen'] > 0 for u in hasil))
    cek('semua unit punya KUK', all(u['kuk'] > 0 for u in hasil))
    valid = [u for u in hasil if u['validasi_struktur'] == 'valid_struktur']
    perlu = [u for u in hasil if u['validasi_struktur'] != 'valid_struktur']
    cek('mayoritas unit valid_struktur', len(valid) >= 9,
        str([(u['kode_unit'], u['validasi_struktur']) for u in perlu]))
    cek('unit perlu_verifikasi menyertakan catatan alasan',
        all(u.get('catatan') for u in perlu),
        str([(u['kode_unit'], u.get('catatan')) for u in perlu]))
    cek('tidak ada KUK hilang di semua unit',
        all((json.loads((project_root / u['berkas']).read_text(encoding='utf-8'))
             ['validasi_kelengkapan']['kuk_hilang']) == [] for u in hasil))

    # -------------------------------------------------------- 5 status job
    print("\n5. STATUS JOB")
    r = client.get(f'/job/{jid2}')
    cek('halaman job 200', r.status_code == 200)
    cek('menampilkan nama skema', 'CONTENT CREATOR' in r.text)
    cek('menampilkan progress bar', 'progress-bar' in r.text)
    cek('job tersimpan di disk', (UJI_DIR / f'{jid2}.json').exists())
    cek('job tidak dikenal 404', client.get('/job/' + '0' * 32).status_code == 404)
    cek('ID job tidak sah 404', client.get('/api/jobs/../app').status_code in (404, 400))

    # ------------------------------------------------------------ 6 gagal
    print("\n6. PENANGANAN KEGAGALAN")
    peta_asli = jobs._peta_pdf
    jobs._peta_pdf = lambda: {}
    try:
        r = client.post(f'/skema/{sid}/ekstrak',
                        data={'csrf_token': token, 'kode_unit': kode}, follow_redirects=False)
        jid3 = r.headers['location'].rsplit('/', 1)[-1]
        job3 = tunggu(client, jid3, batas=60)
    finally:
        jobs._peta_pdf = peta_asli
    cek('job tanpa PDF berstatus gagal', job3.get('status') == 'gagal', str(job3.get('status')))
    cek('pesan kegagalan jelas', 'PDF sumber tidak ditemukan' in (job3['units'][0].get('pesan') or ''),
        str(job3['units'][0].get('pesan')))
    cek('kegagalan tidak merusak aplikasi', client.get('/skema').status_code == 200)

    # -------------------------------------------------------- 7 keamanan
    print("\n7. KEAMANAN")
    cek('ekstrak tanpa token 403', client.post(
        f'/skema/{sid}/ekstrak', data={'kode_unit': kode},
        follow_redirects=False).status_code == 403)
    cek('kode unit asing ditolak', client.post(
        f'/skema/{sid}/ekstrak', data={'csrf_token': token, 'kode_unit': 'X.00XXX00.000.0'},
        follow_redirects=True).text.count('tidak ada pada skema') >= 1)

    # ------------------------------------------------- 8 sumber tidak berubah
    print("\n8. DOKUMEN SUMBER TIDAK BERUBAH")
    cek('SHA-256 DOCX skema sama', hashlib.sha256(SKEMA.read_bytes()).hexdigest() == asli)

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

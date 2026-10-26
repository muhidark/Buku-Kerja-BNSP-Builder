"""
Pengujian end-to-end Fase 4F.

Alur: upload SKKNI -> upload skema -> pencocokan -> ekstraksi -> validasi ->
preview -> generate DOCX -> download, ditambah kasus negatif, job terputus,
dan persistensi setelah "restart". Semua penulisan memakai direktori uji.
"""

import hashlib
import io
import json
import re
import shutil
import sys
import time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from fastapi.testclient import TestClient
from app import jobs, library, schema_library as sl
from app.main import app
from app.services import document_service as ds

UJI = project_root / 'data' / 'qa_e2e'
SKEMA_DOCX = project_root / 'data' / 'skema' / '21. Content Creator.docx'
SKKNI_PDF = project_root / 'data' / 'pdf' / 'SKKNI 2018-056.pdf.pdf'

lulus, gagal = [], []


def cek(nama, kondisi, detail=''):
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}" + (f" — {detail}" if detail and not kondisi else ''))


def siapkan():
    if UJI.exists():
        shutil.rmtree(UJI)
    for sub in ('library/pdf', 'library/documents', 'library/tmp',
                'schema/docx', 'schema/documents', 'schema/tmp',
                'jobs', 'json', 'docs', 'meta'):
        (UJI / sub).mkdir(parents=True, exist_ok=True)

    library.LIB_DIR = UJI / 'library'
    library.PDF_STORE = UJI / 'library' / 'pdf'
    library.META_DIR = UJI / 'library' / 'documents'
    library.TMP_DIR = UJI / 'library' / 'tmp'

    sl.SKEMA_DIR = UJI / 'schema'
    sl.DOCX_STORE = UJI / 'schema' / 'docx'
    sl.META_DIR = UJI / 'schema' / 'documents'
    sl.TMP_DIR = UJI / 'schema' / 'tmp'
    sl._CACHE_INDEKS.update({'tanda': None, 'indeks': None})

    jobs.JOBS_DIR = UJI / 'jobs'
    jobs.JSON_OUT = UJI / 'json'
    ds.DOC_DIR = UJI / 'docs'
    ds.META_DIR = UJI / 'meta'


def pulihkan():
    library.LIB_DIR = project_root / 'data' / 'library'
    library.PDF_STORE = library.LIB_DIR / 'pdf'
    library.META_DIR = library.LIB_DIR / 'documents'
    library.TMP_DIR = library.LIB_DIR / 'tmp'
    sl.SKEMA_DIR = project_root / 'data' / 'schema_library'
    sl.DOCX_STORE = sl.SKEMA_DIR / 'docx'
    sl.META_DIR = sl.SKEMA_DIR / 'documents'
    sl.TMP_DIR = sl.SKEMA_DIR / 'tmp'
    jobs.JOBS_DIR = project_root / 'data' / 'jobs'
    jobs.JSON_OUT = project_root / 'data' / 'json' / 'browser_extraction'
    ds.DOC_DIR = project_root / 'output' / 'web_documents'
    ds.META_DIR = project_root / 'data' / 'web_documents'
    if UJI.exists():
        shutil.rmtree(UJI, ignore_errors=True)


def token(client):
    m = re.search(r'name="csrf_token" value="([^"]+)"', client.get('/skema').text)
    return m.group(1) if m else ''


def main():
    print("=" * 100)
    print("PENGUJIAN END-TO-END — FASE 4F")
    print("=" * 100)

    sha_pdf = hashlib.sha256(SKKNI_PDF.read_bytes()).hexdigest()
    sha_skema = hashlib.sha256(SKEMA_DOCX.read_bytes()).hexdigest()

    siapkan()
    c = TestClient(app)
    tok = token(c)

    # ------------------------------------------------------- 1 upload SKKNI
    print("\n1. UPLOAD SKKNI")
    isi_pdf = SKKNI_PDF.read_bytes() + b'\n% uji e2e\n'
    r = c.post('/skkni/upload', files={'berkas': ('e2e.pdf', isi_pdf, 'application/pdf')},
               data={'csrf_token': tok}, follow_redirects=True)
    cek('PDF valid diterima', 'berhasil diunggah' in r.text, r.text[:120])
    docs = library.daftar_dokumen()
    unggahan = [d for d in docs if d['sumber'] == 'unggahan']
    cek('dokumen unggahan tercatat', len(unggahan) == 1,
        f"{len(unggahan)} unggahan / {len(docs)} dokumen")
    cek('unit teridentifikasi', unggahan[0]['jumlah_unit'] == 17,
        str(unggahan[0]['jumlah_unit']))

    r = c.post('/skkni/upload', files={'berkas': ('e2e.pdf', isi_pdf, 'application/pdf')},
               data={'csrf_token': tok}, follow_redirects=True)
    cek('duplikat PDF ditolak', 'sudah ada di perpustakaan' in r.text)

    r = c.post('/skkni/upload', files={'berkas': ('x.pdf', b'%PDF-1.4\nrusak', 'application/pdf')},
               data={'csrf_token': tok}, follow_redirects=True)
    cek('PDF rusak ditolak', 'rusak' in r.text or 'tidak lengkap' in r.text)

    # -------------------------------------------------------- 2 upload skema
    print("\n2. UPLOAD SKEMA & PENCOCOKAN")
    isi_docx = SKEMA_DOCX.read_bytes() + b'\n% uji e2e\n'
    r = c.post('/skema/upload',
               files={'berkas': ('skema-e2e.docx', isi_docx,
                                 'application/vnd.openxmlformats-officedocument'
                                 '.wordprocessingml.document')},
               data={'csrf_token': tok}, follow_redirects=True)
    cek('DOCX skema diterima', 'berhasil diunggah' in r.text, r.text[:120])
    skema = sl.daftar_skema()[0]
    cek('sepuluh unit terbaca', skema['jumlah_unit'] == 10, str(skema['jumlah_unit']))
    ring = (skema['hasil_pencocokan'] or {}).get('ringkasan') or {}
    # PDF salinan berisi kode yang sama dengan PDF proyek -> konflik itu wajar
    # dan justru menjadi bahan uji "konflik sumber SKKNI".
    cek('semua unit tercocokkan', ring.get('ditemukan', 0) + ring.get('konflik', 0) == 10,
        str(ring))
    cek('konflik sumber terdeteksi', ring.get('konflik', 0) >= 1, str(ring.get('konflik')))

    r = c.post('/skema/upload',
               files={'berkas': ('rusak.docx', b'PK\x03\x04bukan docx',
                                 'application/vnd.openxmlformats-officedocument'
                                 '.wordprocessingml.document')},
               data={'csrf_token': tok}, follow_redirects=True)
    cek('DOCX rusak ditolak', 'rusak' in r.text or 'tidak dapat dibaca' in r.text)

    # --------------------------------------------------------- 3 ekstraksi
    print("\n3. EKSTRAKSI & PREVIEW")
    sid = skema['id']
    r = c.post(f'/skema/{sid}/ekstrak', data={'csrf_token': tok, 'kode_unit': ''},
               follow_redirects=False)
    jid = r.headers['location'].rsplit('/', 1)[-1]
    for _ in range(180):
        job = c.get(f'/api/jobs/{jid}').json()
        if job['status'] not in ('menunggu', 'berjalan'):
            break
        time.sleep(0.4)
    cek('job selesai', job['status'] == 'selesai', job['status'])
    cek('10 unit selesai', job['progress']['selesai'] == 10, str(job['progress']))
    peta_cocok = (sl.ambil_skema(sid).get('hasil_pencocokan') or {}).get('units') or {}

    def _siap(kode):
        if (peta_cocok.get(kode) or {}).get('status') != 'ditemukan':
            return False
        p = jobs.JSON_OUT / f'{kode}.json'
        if not p.exists():
            return False
        return (json.loads(p.read_text(encoding='utf-8')).get('validasi') or {}).get(
            'status') == 'valid_struktur'

    kode_json = next(u['kode_unit'] for u in job['units'] if _siap(u['kode_unit']))
    r = c.get(f'/skema/{sid}/unit/{kode_json}')
    cek('preview 200', r.status_code == 200 and 'Kriteria Unjuk Kerja' in r.text)

    # ------------------------------------------------------ 4 job terputus
    print("\n4. SERVER BERHENTI SAAT EKSTRAKSI")
    # Job sintetis berstatus berjalan -> harus ditandai terputus saat start.
    jid2 = 'b' * 32
    (UJI / 'jobs' / f'{jid2}.json').write_text(
        json.dumps({'id': jid2, 'status': 'berjalan', 'schema_id': sid,
                    'nama_skema': 'uji', 'mode': 'satu_unit', 'dibuat': 'uji',
                    'units': [], 'progress': {'total': 0, 'selesai': 0, 'gagal': 0}}),
        encoding='utf-8')
    n = jobs.pulihkan_job_macet()
    cek('job macet ditandai terputus', n >= 1, str(n))
    cek('status terputus', jobs.ambil_job(jid2)['status'] == 'terputus')
    cek('halaman job tetap dapat dibuka', c.get(f'/job/{jid2}').status_code == 200)

    # ------------------------------------------------------ 5 unit hilang
    print("\n5. UNIT TIDAK DITEMUKAN / KONFLIK")
    semua = sl.pdf_sumber()
    asli_pdf_sumber = sl.pdf_sumber
    sl.pdf_sumber = lambda: []
    try:
        dok2 = sl.cocokkan_ulang(sl.ambil_skema(sid))
        cek('unit menjadi belum_ditemukan',
            all(u['status'] == 'belum_ditemukan'
                for u in dok2['hasil_pencocokan']['units'].values()))
    finally:
        sl.pdf_sumber = asli_pdf_sumber

    indeks_asli = sl.indeks_skkni
    palsu = {'index': {kode_json: [
        {'pdf': 'A.pdf', 'start_page': 1, 'end_page': 2, 'judul_pdf': 'X'},
        {'pdf': 'B.pdf', 'start_page': 3, 'end_page': 4, 'judul_pdf': 'Y'}]},
        'dokumen': {'A.pdf': 1, 'B.pdf': 1}, 'galat': []}
    sl.indeks_skkni = lambda paksa=False: palsu
    try:
        dok3 = sl.cocokkan_ulang(sl.ambil_skema(sid))
        cek('konflik terdeteksi',
            dok3['hasil_pencocokan']['units'][kode_json]['status'] == 'konflik')
    finally:
        sl.indeks_skkni = indeks_asli
        sl.cocokkan_ulang(sl.ambil_skema(sid))

    # --------------------------------------------------------- 6 dokumen
    print("\n6. GENERATE DOCX & DOWNLOAD")
    v = ds.validasi(sid, [kode_json])
    cek('validasi satu unit', v['lengkap'] is True, str(v['masalah']))
    meta = ds.buat_dokumen(sid, [kode_json])
    cek('dokumen dibuat', (project_root / meta['berkas_docx']).exists())
    cek('status siap_ditinjau', meta['status'] == 'siap_ditinjau', meta['status'])

    r = c.get(f"/api/documents/{meta['id']}/download")
    cek('download 200', r.status_code == 200 and r.content[:4] == b'PK\x03\x04')
    cek('CSRF generate ditolak',
        c.post('/api/documents/generate', json={'schema_id': sid}).status_code == 403)
    cek('ID unduhan tidak sah 404',
        c.get('/api/documents/' + 'a' * 32 + '/download').status_code == 404)
    cek('traversal unduhan ditolak',
        c.get('/api/documents/..%2f..%2fetc%2fpasswd/download').status_code in (400, 404))

    # --------------------------------------------------------- 7 "restart"
    print("\n7. RESTART APLIKASI")
    c2 = TestClient(app)
    cek('/hasil 200 setelah restart', c2.get('/hasil').status_code == 200)
    cek('dokumen masih tercatat', ds.ambil_dokumen(meta['id']) is not None)
    cek('unduhan masih berfungsi',
        c2.get(f"/api/documents/{meta['id']}/download").status_code == 200)
    cek('job masih terbaca', c2.get(f'/job/{jid}').status_code == 200)
    cek('skema masih terbaca', c2.get(f'/skema/{sid}').status_code == 200)
    cek('SKKNI masih terbaca', len(library.daftar_dokumen()) >= 1)

    # ------------------------------------------------- 8 data asli utuh
    print("\n8. DATA ASLI TIDAK BERUBAH")
    cek('PDF sumber utuh', hashlib.sha256(SKKNI_PDF.read_bytes()).hexdigest() == sha_pdf)
    cek('DOCX skema utuh', hashlib.sha256(SKEMA_DOCX.read_bytes()).hexdigest() == sha_skema)

    pulihkan()
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
        pulihkan()

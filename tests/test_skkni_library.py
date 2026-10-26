"""
Pengujian perpustakaan PDF SKKNI (Fase 4B).

Memakai direktori perpustakaan sementara di dalam proyek
(`data/library/_uji`) agar metadata dan berkas asli tidak tersentuh.
"""

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from fastapi.testclient import TestClient
from app import library
from app.main import app

UJI_DIR = project_root / 'data' / 'library' / '_uji'
SUMBER = project_root / 'data' / 'pdf' / 'SKKNI 2018-056.pdf.pdf'

lulus, gagal = [], []


def cek(nama, kondisi, detail=''):
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}" + (f" — {detail}" if detail and not kondisi else ''))


def pasang_direktori_uji():
    if UJI_DIR.exists():
        shutil.rmtree(UJI_DIR)
    for sub in ('pdf', 'documents', 'tmp'):
        (UJI_DIR / sub).mkdir(parents=True, exist_ok=True)
    library.LIB_DIR = UJI_DIR
    library.PDF_STORE = UJI_DIR / 'pdf'
    library.META_DIR = UJI_DIR / 'documents'
    library.TMP_DIR = UJI_DIR / 'tmp'


def bersihkan():
    library.LIB_DIR = project_root / 'data' / 'library'
    library.PDF_STORE = library.LIB_DIR / 'pdf'
    library.META_DIR = library.LIB_DIR / 'documents'
    library.TMP_DIR = library.LIB_DIR / 'tmp'
    if UJI_DIR.exists():
        shutil.rmtree(UJI_DIR, ignore_errors=True)


def token_csrf(client):
    halaman = client.get('/skkni')
    m = re.search(r'name="csrf_token" value="([^"]+)"', halaman.text)
    return m.group(1) if m else ''


def unggah(client, nama, isi, token):
    return client.post('/skkni/upload',
                       files={'berkas': (nama, isi, 'application/pdf')},
                       data={'csrf_token': token},
                       follow_redirects=True)


def main():
    print("=" * 100)
    print("PENGUJIAN PERPUSTAKAAN SKKNI — FASE 4B")
    print("=" * 100)

    if not SUMBER.exists():
        print(f"ERROR: PDF sumber tidak ditemukan: {SUMBER}")
        return 1

    asli_sha = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (project_root / 'data' / 'pdf').glob('*.pdf')}
    json_sha = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (project_root / 'data' / 'json' / 'schema_content_creator').glob('*.json')}

    pasang_direktori_uji()
    client = TestClient(app)
    token = token_csrf(client)
    print(f"\nDirektori uji: {UJI_DIR.relative_to(project_root)} | token: {len(token)} karakter")

    # ------------------------------------------------------------------ 1 valid
    print("\n1. UNGGAH PDF VALID")
    isi_salinan = SUMBER.read_bytes() + b'\n% salinan uji fase 4B\n'
    r = unggah(client, 'SKKNI Uji 2018-056.pdf', isi_salinan, token)
    cek('HTTP 200 setelah redirect', r.status_code == 200, str(r.status_code))
    cek('pesan sukses tampil', 'berhasil diunggah' in r.text)

    docs = library.daftar_dokumen()
    unggahan = [x for x in docs if x['sumber'] == 'unggahan']
    proyek = [x for x in docs if x['sumber'] == 'proyek']
    cek('satu dokumen unggahan tersimpan', len(unggahan) == 1, str(len(unggahan)))
    cek('dokumen proyek terdaftar otomatis', len(proyek) == 4, str(len(proyek)))
    d = docs[0]
    cek('nama asli disimpan sebagai metadata', d['nama_asli'] == 'SKKNI Uji 2018-056.pdf')
    cek('nama internal berupa ID acak',
        re.fullmatch(r'data/library/_uji/pdf/[0-9a-f]{32}\.pdf', d['nama_internal']) is not None,
        d['nama_internal'])
    cek('SHA-256 64 heksadesimal', re.fullmatch(r'[0-9a-f]{64}', d['sha256']) is not None)
    cek('berkas benar-benar ada di disk',
        (project_root / d['nama_internal']).exists())
    cek('metadata JSON valid',
        json.loads((library.META_DIR / f"{d['id']}.json").read_text(encoding='utf-8'))['id'] == d['id'])
    cek('tidak ada berkas sementara tersisa', not list(library.TMP_DIR.glob('*.part')))

    # ------------------------------------------------------- 2 - 7 identifikasi
    print("\n2. IDENTIFIKASI DOKUMEN")
    cek('nomor SKKNI teridentifikasi', d['nomor'] == '56', str(d['nomor']))
    cek('tahun SKKNI teridentifikasi', d['tahun'] == '2018', str(d['tahun']))
    cek('jumlah halaman terbaca', d['halaman'] == 75, str(d['halaman']))
    cek('status identifikasi lengkap', d['status_identifikasi'] == 'lengkap',
        d['status_identifikasi'])
    cek('unit kompetensi teridentifikasi', d['jumlah_unit'] == 17, str(d['jumlah_unit']))

    print("\n3. DAFTAR UNIT")
    unit = d['units']
    cek('semua unit punya kode', all(u['kode_unit'] for u in unit))
    cek('kode unik', len({u['kode_unit'] for u in unit}) == len(unit))
    cek('halaman tampil = 0-based + 1',
        all(u['halaman_tampil'] == u['halaman_pdf_0based'] + 1 for u in unit))
    cek('rentang halaman menaik',
        [u['halaman_pdf_0based'] for u in unit] == sorted(u['halaman_pdf_0based'] for u in unit))
    contoh = next(u for u in unit if u['kode_unit'] == 'J.63OPR00.009.2')
    cek('unit acuan J.63OPR00.009.2 ada', contoh['halaman_pdf_0based'] == 39,
        str(contoh['halaman_pdf_0based']))
    cek('halaman tampil unit acuan = 40 (1-based)', contoh['halaman_tampil'] == 40,
        str(contoh['halaman_tampil']))

    # -------------------------------------------------------- 4 penolakan berkas
    print("\n4. PENOLAKAN BERKAS")
    jumlah_awal = len(library.daftar_dokumen())

    r = unggah(client, 'dokumen.txt', b'ini bukan pdf sama sekali', token)
    cek('file non-PDF ditolak', 'Hanya berkas PDF' in r.text)
    cek('tidak menambah dokumen', len(library.daftar_dokumen()) == jumlah_awal)

    r = unggah(client, 'rusak.pdf', b'%PDF-1.4\n' + b'\x00' * 400, token)
    cek('PDF rusak ditolak', ('rusak' in r.text or 'tidak dapat dibuka' in r.text
                              or 'tidak lengkap' in r.text), r.text[:200])
    cek('tidak menambah dokumen (rusak)', len(library.daftar_dokumen()) == jumlah_awal)

    r = unggah(client, 'SKKNI Uji 2018-056.pdf', isi_salinan, token)
    cek('duplikat ditolak', 'sudah ada di perpustakaan' in r.text)
    cek('duplikat tidak menambah dokumen', len(library.daftar_dokumen()) == jumlah_awal)
    cek('duplikat menampilkan dokumen yang ada', 'SKKNI Uji 2018-056.pdf' in r.text)

    batas_asli = library.BATAS_UKURAN
    library.BATAS_UKURAN = 2048
    try:
        r = unggah(client, 'besar.pdf', isi_salinan, token)
        cek('berkas melebihi batas ditolak', 'melebihi batas' in r.text, r.text[:200])
        cek('tidak menambah dokumen (batas)', len(library.daftar_dokumen()) == jumlah_awal)
    finally:
        library.BATAS_UKURAN = batas_asli

    # --------------------------------------------------------------- 5 tampilan
    print("\n5. HALAMAN DAFTAR & DETAIL")
    r = client.get('/skkni')
    cek('daftar 200', r.status_code == 200)
    cek('menampilkan nama dokumen', 'SKKNI Uji 2018-056.pdf' in r.text)
    cek('menampilkan nomor/tahun', '56 / 2018' in r.text)

    r = client.get(f"/skkni?q=2018")
    cek('pencarian dokumen berdasarkan tahun', 'SKKNI Uji 2018-056.pdf' in r.text)
    r = client.get('/skkni?q=tidakadayangcocok')
    cek('pencarian kosong menampilkan pesan', 'Tidak ada dokumen' in r.text)

    r = client.get(f'/skkni/{d["id"]}')
    cek('detail 200', r.status_code == 200)
    cek('detail memuat kode unit', 'J.63OPR00.009.2' in r.text)
    cek('detail memuat label halaman 1-based', '(1-based)' in r.text)
    cek('detail memuat bagian validasi', 'Validasi Kelengkapan KUK' in r.text)
    cek('detail memuat sha256 pendek', d['sha256'][:16] in r.text)

    print("\n6. PENCARIAN & PAGINATION UNIT")
    r = client.get(f'/skkni/{d["id"]}?q=J.59MTM00.011.1')
    cek('cari kode unit', 'J.59MTM00.011.1' in r.text and 'J.63OPR00.007.2' not in r.text)

    r = client.get(f'/skkni/{d["id"]}?q=internet')
    cek('cari judul unit (tanpa peduli huruf besar/kecil)',
        'Internet Based Applications Literacy' in r.text)

    r = client.get(f'/skkni/{d["id"]}?q=zzz')
    cek('pencarian unit kosong menampilkan pesan', 'Tidak ada unit' in r.text)

    r1 = client.get(f'/skkni/{d["id"]}?page=1')
    r2 = client.get(f'/skkni/{d["id"]}?page=2')
    cek('pagination halaman 2 berbeda',
        'Halaman 2 dari 2' in r2.text and 'Halaman 1 dari 2' in r1.text)
    r9 = client.get(f'/skkni/{d["id"]}?page=99')
    cek('nomor halaman berlebih dibatasi', 'Halaman 2 dari 2' in r9.text)

    # ---------------------------------------------------------------- 7 keamanan
    print("\n7. KEAMANAN")
    r = client.post('/skkni/upload', files={'berkas': ('x.pdf', isi_salinan)},
                    follow_redirects=False)
    cek('unggah tanpa token ditolak 403', r.status_code == 403, str(r.status_code))

    r = client.post('/skkni/upload',
                    files={'berkas': ('x.pdf', isi_salinan)},
                    data={'csrf_token': 'token-palsu'},
                    follow_redirects=False)
    cek('token palsu ditolak 403', r.status_code == 403, str(r.status_code))

    r = unggah(client, '../../keluar.pdf', isi_salinan + b'% traversal\n', token)
    tersimpan = library.daftar_dokumen()
    cek('nama traversal tidak menulis di luar direktori',
        all('/' not in x['nama_asli'] and '..' not in x['nama_asli'] for x in tersimpan))
    cek('tidak ada berkas keluar proyek',
        not (project_root / 'data' / 'keluar.pdf').exists()
        and not (project_root / 'keluar.pdf').exists())

    r = client.get('/skkni/..%2f..%2fetc%2fpasswd')
    cek('path traversal pada URL ditolak', r.status_code == 404, str(r.status_code))

    r = client.delete(f'/skkni/{d["id"]}')
    cek('tidak ada endpoint hapus permanen', r.status_code == 405, str(r.status_code))

    print("\n8. METADATA RUSAK")
    rusak = library.META_DIR / 'rusak.json'
    rusak.write_text('{ bukan json', encoding='utf-8')
    r = client.get('/skkni')
    cek('daftar tetap 200 meski ada metadata rusak', r.status_code == 200)
    cek('metadata rusak dilewati', 'SKKNI Uji 2018-056.pdf' in r.text)
    r = client.get('/api/skkni')
    cek('API tetap valid', r.status_code == 200 and r.json()['jumlah'] >= 1)
    rusak.unlink()

    # ------------------------------------------------------- 9 data tidak berubah
    print("\n9. DATA ASLI TIDAK BERUBAH")
    asli_sekarang = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (project_root / 'data' / 'pdf').glob('*.pdf')}
    json_sekarang = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (project_root / 'data' / 'json' / 'schema_content_creator').glob('*.json')}
    cek('PDF proyek tidak berubah', asli_sekarang == asli_sha)
    cek('JSON hasil ekstraksi tidak berubah', json_sekarang == json_sha)

    print("\n10. KONSISTENSI API")
    api = client.get('/api/skkni').json()
    cek('jumlah API = isi perpustakaan', api['jumlah'] == len(library.daftar_dokumen()))
    cek('setiap dokumen punya id 32 heksadesimal',
        all(re.fullmatch(r'[0-9a-f]{32}', x['id']) for x in api['dokumen']))

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

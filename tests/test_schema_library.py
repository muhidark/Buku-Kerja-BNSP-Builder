"""
Pengujian perpustakaan skema sertifikasi (Fase 4C).

Direktori penyimpanan dialihkan ke `data/schema_library/_uji` agar dokumen
asli dan metadata produksi tidak tersentuh.
"""

import hashlib
import io
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from fastapi.testclient import TestClient
from app import schema_library as sl
from app.main import app

from tests.dukungan import klien
UJI_DIR = project_root / 'data' / 'schema_library' / '_uji'
SUMBER = project_root / 'data' / 'skema' / '21. Content Creator.docx'

lulus, gagal = [], []


def cek(nama, kondisi, detail=''):
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}" + (f" — {detail}" if detail and not kondisi else ''))


def pasang_direktori_uji():
    if UJI_DIR.exists():
        shutil.rmtree(UJI_DIR)
    for sub in ('docx', 'documents', 'tmp'):
        (UJI_DIR / sub).mkdir(parents=True, exist_ok=True)
    sl.SKEMA_DIR = UJI_DIR
    sl.DOCX_STORE = UJI_DIR / 'docx'
    sl.META_DIR = UJI_DIR / 'documents'
    sl.TMP_DIR = UJI_DIR / 'tmp'


def bersihkan():
    sl.SKEMA_DIR = project_root / 'data' / 'schema_library'
    sl.DOCX_STORE = sl.SKEMA_DIR / 'docx'
    sl.META_DIR = sl.SKEMA_DIR / 'documents'
    sl.TMP_DIR = sl.SKEMA_DIR / 'tmp'
    if UJI_DIR.exists():
        shutil.rmtree(UJI_DIR, ignore_errors=True)


def token_csrf(client):
    r = client.get('/skema')
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    return m.group(1) if m else ''


def unggah(client, nama, isi, token, tipe='application/vnd.openxmlformats-officedocument.wordprocessingml.document'):
    return client.post('/skema/upload',
                       files={'berkas': (nama, isi, tipe)},
                       data={'csrf_token': token}, follow_redirects=True)


def main():
    print("=" * 100)
    print("PENGUJIAN PERPUSTAKAAN SKEMA — FASE 4C")
    print("=" * 100)

    if not SUMBER.exists():
        print(f"ERROR: dokumen skema tidak ditemukan: {SUMBER}")
        return 1

    asli = hashlib.sha256(SUMBER.read_bytes()).hexdigest()
    pasang_direktori_uji()
    client = klien(app, 'admin')
    token = token_csrf(client)

    # -------------------------------------------------------------- 1 valid
    print("\n1. UNGGAH DOCX VALID")
    r = unggah(client, '21. Content Creator.docx', SUMBER.read_bytes(), token)
    cek('HTTP 200 setelah redirect', r.status_code == 200, str(r.status_code))
    cek('pesan sukses', 'berhasil diunggah' in r.text)

    docs = sl.daftar_skema()
    cek('satu skema tersimpan', len(docs) == 1, str(len(docs)))
    d = docs[0]
    cek('nama asli tersimpan', d['nama_asli'] == '21. Content Creator.docx')
    cek('nama internal acak', re.fullmatch(r'data/schema_library/_uji/docx/[0-9a-f]{32}\.docx',
                                           d['nama_internal']) is not None, d['nama_internal'])
    cek('SHA-256 valid', re.fullmatch(r'[0-9a-f]{64}', d['sha256']) is not None)
    cek('berkas ada di disk', (project_root / d['nama_internal']).exists())
    cek('tidak ada berkas sementara', not list(sl.TMP_DIR.glob('*.part')))

    # --------------------------------------------------------- 2 informasi
    print("\n2. INFORMASI SKEMA")
    cek('nama skema terbaca', d['nama_skema'] == 'CONTENT CREATOR', str(d['nama_skema']))
    cek('judul dokumen terbaca', 'SKEMA SERTIFIKASI' in (d['judul_dokumen'] or ''))
    cek('jenis skema terbaca', d['jenis_skema'] == 'KKNI / Okupasi / Klaster',
        str(d['jenis_skema']))
    cek('jumlah unit = 10', d['jumlah_unit'] == 10, str(d['jumlah_unit']))
    cek('status identifikasi lengkap', d['status_identifikasi'] == 'lengkap')

    # ------------------------------------------------------------ 3 unit
    print("\n3. DAFTAR UNIT")
    kode = [u['kode_unit'] for u in d['units']]
    cek('10 kode unit unik', len(set(kode)) == 10)
    cek('nomor urut 1..10', [u['nomor_urut'] for u in d['units']] == list(range(1, 11)))
    cek('urutan sesuai dokumen', kode[:3] == ['J.63OPR00.009.2', 'J.63OPR00.007.2',
                                              'J.63OPR00.010.2'], str(kode[:3]))
    cek('semua kode sesuai pola', all(re.fullmatch(r'[A-Z]\.\d{2}[A-Z]{2,3}\d{2}\.\d{3}\.\d', k)
                                      for k in kode))

    # ------------------------------------------------------- 4 penolakan
    print("\n4. PENOLAKAN BERKAS")
    jumlah = len(sl.daftar_skema())

    r = unggah(client, 'skema.doc', b'\xd0\xcf\x11\xe0' + b'\x00' * 100, token)
    cek('.doc ditolak', 'Hanya dokumen .docx' in r.text, r.text[:160])

    r = unggah(client, 'skema.pdf', SUMBER.read_bytes(), token)
    cek('PDF ditolak', 'Hanya dokumen .docx' in r.text)

    r = unggah(client, 'rusak.docx', b'PK\x03\x04' + b'x' * 400, token)
    cek('DOCX rusak ditolak', ('rusak' in r.text or 'tidak dapat dibaca' in r.text
                               or 'tidak lengkap' in r.text), r.text[:200])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('halo.txt', 'bukan dokumen word')
    r = unggah(client, 'salahstruktur.docx', buf.getvalue(), token)
    cek('ZIP tanpa struktur Word ditolak', 'Struktur DOCX tidak lengkap' in r.text, r.text[:200])

    r = unggah(client, '21. Content Creator.docx', SUMBER.read_bytes(), token)
    cek('duplikat ditolak', 'sudah ada' in r.text)
    cek('duplikat tidak menambah data', len(sl.daftar_skema()) == jumlah)

    batas_asli = sl.BATAS_UKURAN
    sl.BATAS_UKURAN = 1024
    try:
        r = unggah(client, 'besar.docx', SUMBER.read_bytes(), token)
        cek('berkas melebihi batas ditolak', 'melebihi batas' in r.text, r.text[:160])
        cek('tidak menambah data (batas)', len(sl.daftar_skema()) == jumlah)
    finally:
        sl.BATAS_UKURAN = batas_asli

    batas_unzip = sl.BATAS_UNCOMPRESSED
    sl.BATAS_UNCOMPRESSED = 1024
    try:
        r = unggah(client, 'bom.docx', SUMBER.read_bytes(), token)
        cek('ZIP bomb (isi membengkak) ditolak', 'batas aman' in r.text, r.text[:160])
    finally:
        sl.BATAS_UNCOMPRESSED = batas_unzip

    cek('tidak ada berkas sementara tertinggal', not list(sl.TMP_DIR.glob('*.part')))

    # -------------------------------------------------------- 5 keamanan
    print("\n5. KEAMANAN")
    r = client.post('/skema/upload', files={'berkas': ('x.docx', SUMBER.read_bytes())},
                    follow_redirects=False)
    cek('unggah tanpa token 403', r.status_code == 403, str(r.status_code))

    r = client.post('/skema/upload', files={'berkas': ('x.docx', SUMBER.read_bytes())},
                    data={'csrf_token': 'palsu'}, follow_redirects=False)
    cek('token palsu 403', r.status_code == 403)

    r = unggah(client, '../../keluar.docx', SUMBER.read_bytes() + b'\n% uji traversal\n', token)
    cek('nama traversal tidak keluar direktori',
        all('/' not in x['nama_asli'] and '..' not in x['nama_asli'] for x in sl.daftar_skema()))

    cek('tidak ada endpoint hapus', client.delete(f"/skema/{d['id']}").status_code == 405)
    cek('path traversal URL ditolak',
        client.get('/skema/..%2f..%2fetc%2fpasswd').status_code == 404)

    # ---------------------------------------------------------- 6 tampilan
    print("\n6. HALAMAN DAFTAR & DETAIL")
    r = client.get('/skema')
    cek('daftar 200', r.status_code == 200)
    cek('nama skema tampil', 'CONTENT CREATOR' in r.text)
    cek('kolom jumlah unit tampil', 'Jumlah Unit' in r.text)

    r = client.get('/skema?q=content')
    cek('pencarian skema', 'CONTENT CREATOR' in r.text)
    r = client.get('/skema?q=tidakada')
    cek('pencarian kosong', 'Tidak ada skema' in r.text)

    r = client.get(f"/skema/{d['id']}")
    cek('detail 200', r.status_code == 200)
    cek('detail memuat kode unit', 'J.63OPR00.009.2' in r.text)
    cek('detail memuat tombol periksa ulang', 'Periksa Ulang Ketersediaan Unit' in r.text)
    cek('detail memuat kolom sumber SKKNI', 'Sumber SKKNI' in r.text)

    r = client.get(f"/skema/{d['id']}?q=013")
    # Panel "Buat Dokumen Word" memang memuat semua unit; yang diperiksa
    # adalah tabel daftar unit (tabel pertama).
    tabel = re.search(r'<table.*?</table>', r.text, re.S).group(0)
    cek('pencarian unit pada detail', 'M.70MKT00.013.1' in tabel
        and 'J.63OPR00.007.2' not in tabel)

    # --------------------------------------------------- 7 penyimpanan tetap
    print("\n7. PENYIMPANAN METADATA")
    berkas = sl.META_DIR / f"{d['id']}.json"
    cek('metadata tersimpan di disk', berkas.exists())
    isi = json.loads(berkas.read_text(encoding='utf-8'))
    wajib = ('id', 'nama_asli', 'nama_internal', 'sha256', 'nama_skema', 'tanggal_ditambah',
             'jumlah_unit', 'units', 'status_identifikasi', 'hasil_pencocokan')
    cek('metadata memuat kunci wajib', all(k in isi for k in wajib),
        str([k for k in wajib if k not in isi]))

    client2 = klien(app, 'admin')
    r = client2.get(f"/skema/{d['id']}")
    cek('dokumen masih terbaca pada klien baru', r.status_code == 200
        and 'CONTENT CREATOR' in r.text)

    # -------------------------------------------------- 8 sumber tidak berubah
    print("\n8. DOKUMEN SUMBER TIDAK BERUBAH")
    cek('SHA-256 dokumen asli sama', hashlib.sha256(SUMBER.read_bytes()).hexdigest() == asli)

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

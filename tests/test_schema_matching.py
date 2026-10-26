"""
Pengujian pencocokan unit skema ke perpustakaan SKKNI (Fase 4C).

Menguji urutan unit, pencocokan persis, unit tidak ditemukan, konflik,
perbedaan judul, dan fitur "Periksa Ulang Ketersediaan Unit".
"""

import re
import shutil
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from fastapi.testclient import TestClient
from app import schema_library as sl
from app.schema_parser import baca_skema
from app.main import app

from tests.dukungan import klien
UJI_DIR = project_root / 'data' / 'schema_library' / '_uji_matching'
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
    sl._CACHE_INDEKS['tanda'] = None
    sl._CACHE_INDEKS['indeks'] = None


def bersihkan():
    sl.SKEMA_DIR = project_root / 'data' / 'schema_library'
    sl.DOCX_STORE = sl.SKEMA_DIR / 'docx'
    sl.META_DIR = sl.SKEMA_DIR / 'documents'
    sl.TMP_DIR = sl.SKEMA_DIR / 'tmp'
    sl._CACHE_INDEKS['tanda'] = None
    sl._CACHE_INDEKS['indeks'] = None
    if UJI_DIR.exists():
        shutil.rmtree(UJI_DIR, ignore_errors=True)


def token_csrf(client):
    r = client.get('/skema')
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    return m.group(1) if m else ''


def main():
    print("=" * 100)
    print("PENGUJIAN PENCOCOKAN SKEMA — FASE 4C")
    print("=" * 100)

    pasang_direktori_uji()
    client = klien(app, 'admin')
    token = token_csrf(client)

    r = client.post('/skema/upload',
                    files={'berkas': ('21. Content Creator.docx', SUMBER.read_bytes(),
                                      'application/vnd.openxmlformats-officedocument'
                                      '.wordprocessingml.document')},
                    data={'csrf_token': token}, follow_redirects=True)
    docs = sl.daftar_skema()
    if not docs:
        print('ERROR: unggahan gagal:', r.text[:200])
        bersihkan()
        return 1

    dok = docs[0]
    pc = dok['hasil_pencocokan'] or {}
    ringkas = pc.get('ringkasan') or {}
    sumber_dokumen = pc.get('pdf_diperiksa') or {}
    print(f"\nSkema: {dok['nama_skema']} | unit: {dok['jumlah_unit']} | sumber PDF: {len(sumber_dokumen)}")
    print(f"Sumber: {list(sumber_dokumen)}")

    # ------------------------------------------------------------ 1 urutan
    print("\n1. URUTAN & KODE")
    kode_skema = [u['kode_unit'] for u in dok['units']]
    kode_parser = [u['kode_unit'] for u in baca_skema(SUMBER)['units']]
    cek('urutan sama dengan schema_parser', kode_skema == kode_parser)
    cek('10 unit tanpa tambahan otomatis', len(kode_skema) == 10, str(len(kode_skema)))
    cek('kode tidak diubah', all(a == b for a, b in zip(kode_skema, kode_parser)))
    cek('nomor urut berurutan', [u['nomor_urut'] for u in dok['units']] == list(range(1, 11)))

    # --------------------------------------------------------- 2 pencocokan
    print("\n2. HASIL PENCOCOKAN")
    cek('10 unit ditemukan', ringkas.get('ditemukan') == 10, str(ringkas))
    cek('tidak ada unit belum ditemukan', ringkas.get('tidak_ditemukan') == 0)
    cek('tidak ada konflik', ringkas.get('konflik') == 0)
    cek('semua unit punya PDF sumber',
        all((pc['units'][k].get('pdf') for k in kode_skema)))
    cek('semua unit punya halaman awal',
        all(isinstance(pc['units'][k].get('start_page'), int) for k in kode_skema))
    cek('pdf sumber berasal dari perpustakaan',
        set(pc['units'][k]['pdf'] for k in kode_skema) <= set(sumber_dokumen))
    contoh = pc['units']['J.63OPR00.009.2']
    cek('unit acuan memakai SKKNI 2018-056', contoh['pdf'] == 'SKKNI 2018-056.pdf.pdf',
        contoh['pdf'])
    cek('halaman unit acuan 39 (0-based)', contoh['start_page'] == 39, str(contoh['start_page']))

    # ------------------------------------------------------- 3 beda judul
    print("\n3. PERBANDINGAN JUDUL")
    beda = [k for k in kode_skema if pc['units'][k].get('judul_berbeda')]
    cek('jumlah judul berbeda konsisten dengan ringkasan',
        len(beda) == ringkas.get('judul_berbeda', 0), f"{len(beda)} vs {ringkas.get('judul_berbeda')}")
    cek('setiap unit menyimpan judul skema dan judul PDF',
        all(pc['units'][k].get('judul_skema') and pc['units'][k].get('judul_pdf')
            for k in kode_skema))

    # ------------------------------------------------ 4 unit tidak ditemukan
    print("\n4. UNIT TIDAK DITEMUKAN (SKKNI SUMBER DIKURANGI)")
    semua_pdf = sl.pdf_sumber()
    asli_pdf_sumber = sl.pdf_sumber
    sl.pdf_sumber = lambda: [p for p in semua_pdf if '2018-056' not in p.name]
    try:
        dok = sl.cocokkan_ulang(dok)
        pc2 = dok['hasil_pencocokan']
        cek('unit dari SKKNI yang hilang menjadi belum_ditemukan',
            pc2['units']['J.63OPR00.009.2']['status'] == 'belum_ditemukan',
            pc2['units']['J.63OPR00.009.2']['status'])
        cek('ringkasan mencatat 3 unit belum ditemukan',
            pc2['ringkasan']['tidak_ditemukan'] == 3,
            str(pc2['ringkasan']['tidak_ditemukan']))
    finally:
        sl.pdf_sumber = asli_pdf_sumber

    # ------------------------------------------------ 5 periksa ulang (fitur J)
    print("\n5. PERIKSA ULANG SETELAH SUMBER LENGKAP")
    r = client.post(f"/skema/{dok['id']}/periksa-ulang", data={'csrf_token': token},
                    follow_redirects=True)
    cek('periksa ulang HTTP 200', r.status_code == 200)
    cek('pesan pembaruan tampil', 'Pencocokan diperbarui' in r.text)
    dok = sl.ambil_skema(dok['id'])
    cek('semua unit ditemukan kembali',
        dok['hasil_pencocokan']['ringkasan']['ditemukan'] == 10,
        str(dok['hasil_pencocokan']['ringkasan']))
    cek('tidak ada ekstraksi/DOCX baru saat periksa ulang',
        not list((project_root / 'output').glob('*periksa*')))

    # --------------------------------------------------------- 6 konflik
    print("\n6. KONFLIK KODE")
    indeks_asli = sl.indeks_skkni
    palsu = {
        'index': {
            'J.63OPR00.009.2': [
                {'pdf': 'A.pdf', 'start_page': 1, 'end_page': 2, 'judul_pdf': 'Judul A'},
                {'pdf': 'B.pdf', 'start_page': 5, 'end_page': 6, 'judul_pdf': 'Judul B'},
            ]
        },
        'dokumen': {'A.pdf': 10, 'B.pdf': 12},
        'galat': [],
    }
    sl.indeks_skkni = lambda paksa=False: palsu
    try:
        dok = sl.cocokkan_ulang(dok)
        unit = dok['hasil_pencocokan']['units']['J.63OPR00.009.2']
        cek('kode ganda menjadi konflik', unit['status'] == 'konflik', unit['status'])
        cek('ringkasan mencatat konflik', dok['hasil_pencocokan']['ringkasan']['konflik'] == 1)
        cek('konflik mencatat dua kandidat', unit['jumlah_kandidat'] == 2)
        cek('konflik tidak dipakai otomatis',
            any('verifikasi manual' in c for c in unit['catatan']))
    finally:
        sl.indeks_skkni = indeks_asli

    # ---------------------------------------------------- 7 beda judul (paksa)
    print("\n7. PERBEDAAN JUDUL (UJI PAKSA)")
    sl.indeks_skkni = lambda paksa=False: {
        'index': {'J.63OPR00.009.2': [{'pdf': 'SKKNI 2018-056.pdf.pdf', 'start_page': 39,
                                       'end_page': 41, 'judul_pdf': 'Judul Yang Berbeda'}]},
        'dokumen': {'SKKNI 2018-056.pdf.pdf': 17}, 'galat': [],
    }
    try:
        dok = sl.cocokkan_ulang(dok)
        unit = dok['hasil_pencocokan']['units']['J.63OPR00.009.2']
        cek('judul berbeda terdeteksi', unit['judul_berbeda'] is True)
        cek('ringkasan menghitung judul berbeda',
            dok['hasil_pencocokan']['ringkasan']['judul_berbeda'] == 1)
    finally:
        sl.indeks_skkni = indeks_asli

    # kembalikan pencocokan sebenarnya
    dok = sl.cocokkan_ulang(dok)
    cek('pencocokan kembali normal',
        dok['hasil_pencocokan']['ringkasan']['ditemukan'] == 10)

    # --------------------------------------------------- 8 status berlapis
    print("\n8. STATUS BERLAPIS")
    peta = sl.peta_kelengkapan()
    st = sl.status_unit(dok, 'J.63OPR00.009.2', peta)
    cek('unit punya JSON -> sudah_diekstrak', st['sudah_diekstrak'] is True)
    cek('unit punya status valid_struktur', st['valid_struktur'] is True)
    st2 = sl.status_unit(dok, 'J.63OPR00.001.2', peta)
    cek('unit tanpa JSON -> belum diekstrak', st2['sudah_diekstrak'] is False)
    cek('terverifikasi manual tidak otomatis', st['terverifikasi_manual'] is False)

    # ------------------------------------------------------------ 9 API
    print("\n9. API & HALAMAN")
    api = client.get('/api/skema').json()
    cek('API daftar skema', api['jumlah'] >= 1)
    det = client.get(f"/api/skema/{dok['id']}").json()
    cek('API detail memuat status_unit', len(det.get('status_unit', {})) == 10)
    cek('API detail memuat hasil pencocokan', det['hasil_pencocokan']['ringkasan']['ditemukan'] == 10)

    r = client.get(f"/skema/{dok['id']}")
    cek('halaman detail 200', r.status_code == 200)
    cek('detail menampilkan sumber SKKNI', 'SKKNI 2018-056.pdf.pdf' in r.text)

    # pencarian judul unit
    judul = dok['units'][2]['judul_skema']
    kata = judul.split()[1] if len(judul.split()) > 1 else judul
    r = client.get(f"/skema/{dok['id']}?q={kata}")
    cek('pencarian judul unit', dok['units'][2]['kode_unit'] in r.text, kata)

    bersihkan()
    print("\n" + "=" * 100)
    print(f"HASIL: {len(lulus)} lulus, {len(gagal)} gagal")
    if gagal:
        for g in gagal:
            print(f"  - {g}")
    print("=" * 100)
    return 0 if not gagal else 1




def test_schema_matching():
    assert main() == 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    finally:
        bersihkan()

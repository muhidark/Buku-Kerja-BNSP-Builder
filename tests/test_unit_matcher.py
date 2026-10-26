"""
Pengujian Unit Matcher (Fase 3D).

Memastikan setiap kode unit dari dokumen skema dipetakan PERSIS ke satu unit
pada PDF SKKNI yang tersedia, dengan urutan tetap seperti dokumen skema.
"""

import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.unit_matcher import cocokkan, indeks_pdf

SKEMA_JSON = project_root / 'data' / 'json' / 'schema_content_creator.json'
PDF_DIR = project_root / 'data' / 'pdf'
PDFS = [PDF_DIR / 'SKKNI 2018-056.pdf.pdf',
        PDF_DIR / 'SKKNI 2018-107.pdf.pdf',
        PDF_DIR / 'SKKNI 2022-124.pdf.pdf']

lulus, gagal = [], []


def cek(nama, kondisi, detail=''):
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}" + (f" — {detail}" if detail and not kondisi else ''))


def main():
    print("=" * 100)
    print("PENGUJIAN UNIT MATCHER — FASE 3D")
    print("=" * 100)

    skema = json.loads(SKEMA_JSON.read_text(encoding='utf-8'))
    idx = indeks_pdf(PDFS)
    hasil = cocokkan(skema['units'], PDFS, indeks=idx)

    print(f"\nIndeks: {idx['dokumen']}")

    print("\n1. HASIL PENCOCOKAN")
    cek('10 unit dicocokkan', len(hasil['units']) == 10, str(len(hasil['units'])))
    cek('semua unit ditemukan', hasil['statistik']['ditemukan'] == 10,
        str(hasil['statistik']))
    cek('tidak ada unit tidak ditemukan', not hasil['tidak_ditemukan'],
        str(hasil['tidak_ditemukan']))
    cek('tidak ada konflik kode', not hasil['konflik'], str(hasil['konflik']))

    print("\n2. URUTAN & SUMBER")
    kode_skema = [u['kode_unit'] for u in skema['units']]
    kode_hasil = [u['kode_unit'] for u in hasil['units']]
    cek('urutan sama dengan dokumen skema', kode_skema == kode_hasil,
        str([(a, b) for a, b in zip(kode_skema, kode_hasil) if a != b][:3]))
    cek('setiap unit punya PDF sumber',
        all(u['pdf'] in {p.name for p in PDFS} for u in hasil['units']))
    cek('rentang halaman valid',
        all(isinstance(u['start_page'], int) and isinstance(u['end_page'], int)
            and 0 <= u['start_page'] <= u['end_page'] for u in hasil['units']))
    cek('judul PDF terisi untuk semua unit',
        all(u.get('judul_pdf') for u in hasil['units']),
        str([u['kode_unit'] for u in hasil['units'] if not u.get('judul_pdf')]))

    print("\n3. DISTRIBUSI SUMBER")
    for nama in ('SKKNI 2018-056.pdf.pdf', 'SKKNI 2018-107.pdf.pdf', 'SKKNI 2022-124.pdf.pdf'):
        n = sum(1 for u in hasil['units'] if u['pdf'] == nama)
        print(f"     {nama}: {n} unit")
    cek('distribusi 3/5/2 sesuai dokumen',
        [sum(1 for u in hasil['units'] if u['pdf'] == p.name) for p in PDFS] == [3, 5, 2])

    print("\n4. UJI SINTETIS: KONFLIK & TIDAK DITEMUKAN")
    fake_index = {
        'index': {
            'J.63OPR00.009.2': [
                {'pdf': 'A.pdf', 'start_page': 1, 'end_page': 2, 'judul_pdf': 'X'},
                {'pdf': 'B.pdf', 'start_page': 5, 'end_page': 6, 'judul_pdf': 'X'},
            ],
        },
        'dokumen': {'A.pdf': 1, 'B.pdf': 1},
        'galat': [],
    }
    uji = cocokkan([
        {'nomor_urut': 1, 'kode_unit': 'J.63OPR00.009.2', 'judul_skema': 'X'},
        {'nomor_urut': 2, 'kode_unit': 'TIDAK.ADA.000.0', 'judul_skema': 'Y'},
    ], PDFS, indeks=fake_index)

    cek('konflik kode terdeteksi', len(uji['konflik']) == 1
        and uji['units'][0]['status'] == 'konflik', str(uji['konflik']))
    cek('kode tidak ditemukan ditandai', uji['units'][1]['status'] == 'tidak_ditemukan')
    cek('konflik tidak otomatis dipakai sebagai final',
        'verifikasi manual' in ' '.join(uji['units'][0]['catatan']).lower())

    print("\n" + "=" * 100)
    print(f"HASIL: {len(lulus)} lulus, {len(gagal)} gagal")
    if gagal:
        for g in gagal:
            print(f"  - {g}")
    print("=" * 100)
    return 0 if not gagal else 1


if __name__ == '__main__':
    sys.exit(main())

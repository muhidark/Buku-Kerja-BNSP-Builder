"""
Pengujian lengkap unit kompetensi (Fase 2B).

Menguji:
- identitas unit
- Elemen Kompetensi & KUK (regresi terhadap baseline Fase 2A)
- Batasan Variabel
- Panduan Penilaian
- validasi struktur & metadata
- verifikasi deterministik terhadap teks PDF
"""

import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import pymupdf as fitz

from app.unit_parser import parse_unit, save_unit_json
from app.section_parser import flatten_nodes, normalize_text

PDF = project_root / 'data' / 'pdf' / 'SKKNI 2023-101.pdf.pdf'
FASE1 = project_root / 'data' / 'json' / 'hasil_identifikasi.json'
BASELINE = project_root / 'tests' / 'baseline' / 'fase2a_unit_001.json'
OUTPUT = project_root / 'data' / 'json' / 'test_unit_001_complete.json'

TARGET = 'M.73ADV00.001.1'

lulus, gagal = [], []


def cek(nama: str, kondisi: bool, detail: str = ''):
    (lulus if kondisi else gagal).append(nama)
    tanda = 'PASS' if kondisi else 'FAIL'
    print(f"  [{tanda}] {nama}" + (f" — {detail}" if detail and not kondisi else ''))


def cetak_pohon(nodes, level=1):
    for n in nodes:
        print(f"{'    ' * (level - 1)}{n['nomor']} {n['judul']}  [hal {n['halaman_pdf']}]")
        cetak_pohon(n.get('items', []), level + 1)


def main():
    print("=" * 100)
    print("PENGUJIAN LENGKAP UNIT KOMPETENSI — FASE 2B")
    print("=" * 100)

    with open(FASE1, encoding='utf-8') as f:
        fase1 = json.load(f)

    target = next(u for u in fase1['units'] if u['code'] == TARGET)
    start_page, end_page = target['start_page'], target['end_page']

    print(f"\nDokumen        : {PDF.name}")
    print(f"Kode unit      : {TARGET}")
    print(f"Rentang halaman: {start_page}-{end_page} (0-based, dari JSON Fase 1)")
    print(f"Jumlah halaman PDF: {fitz.open(PDF).page_count}")

    data = parse_unit(str(PDF), TARGET, start_page, end_page)
    save_unit_json(data, str(OUTPUT))

    # ---------------------------------------------------------------- identitas
    print("\n1. IDENTITAS UNIT")
    cek('kode_unit sesuai', data['kode_unit'] == TARGET, str(data['kode_unit']))
    cek('judul_unit terisi', bool(data['judul_unit']))
    cek('judul_unit sama dengan hasil Fase 1',
        data['judul_unit'] == target['title'], str(data['judul_unit']))
    cek('deskripsi_unit terisi', bool(data['deskripsi_unit']))
    print(f"     Judul    : {data['judul_unit']}")
    print(f"     Deskripsi: {data['deskripsi_unit'][:90]}...")

    # ------------------------------------------------------------ elemen & KUK
    print("\n2. ELEMEN KOMPETENSI & KUK")
    elemen = data['elemen_kompetensi']
    total_kuk = sum(len(e['kuk']) for e in elemen)
    print(f"     Jumlah elemen: {len(elemen)} | Jumlah KUK: {total_kuk}")
    cek('jumlah elemen = 4', len(elemen) == 4, str(len(elemen)))
    cek('jumlah KUK = 8', total_kuk == 8, str(total_kuk))

    # -------------------------------------------------------------- regresi 2A
    print("\n3. REGRESI TERHADAP BASELINE FASE 2A")
    with open(BASELINE, encoding='utf-8') as f:
        base = json.load(f)

    cek('kode/judul/deskripsi tidak berubah',
        (base['kode_unit'], base['judul_unit'], base['deskripsi_unit']) ==
        (data['kode_unit'], data['judul_unit'], data['deskripsi_unit']))

    base_elemen = [(e['nomor_elemen'], e['nama_elemen']) for e in base['elemen_kompetensi']]
    now_elemen = [(e['nomor_elemen'], e['nama_elemen']) for e in elemen]
    cek('daftar elemen identik', base_elemen == now_elemen)

    base_kuk = [(k['nomor_kuk'], k['uraian_kuk'], k['halaman_pdf'])
                for e in base['elemen_kompetensi'] for k in e['kuk']]
    now_kuk = [(k['nomor_kuk'], k['uraian_kuk'], k['halaman_pdf'])
               for e in elemen for k in e['kuk']]
    cek('daftar KUK identik (nomor, uraian, halaman)', base_kuk == now_kuk,
        f"{len(base_kuk)} vs {len(now_kuk)}")

    # -------------------------------------------------------- batasan variabel
    bv = data['batasan_variabel']
    pp = data['panduan_penilaian']
    bv_nodes = flatten_nodes(bv['sections'])
    pp_nodes = flatten_nodes(pp['sections'])

    print("\n4. BATASAN VARIABEL")
    print(f"     Halaman: {bv['halaman_awal']}-{bv['halaman_akhir']} | subbagian: {len(bv_nodes)}")
    cetak_pohon(bv['sections'])
    cek('heading BATASAN VARIABEL ditemukan', bv['ditemukan'])
    cek('isi Batasan Variabel tidak kosong', len(bv_nodes) > 0)
    cek('4 bagian utama', len(bv['sections']) == 4, str(len(bv['sections'])))
    cek('19 subbagian bernomor', len([n for n in bv_nodes if n['is_numbered']]) == 19,
        str(len([n for n in bv_nodes if n['is_numbered']])))
    cek('judul bagian 1', bv['sections'][0]['judul'] == 'Konteks variabel',
        bv['sections'][0]['judul'])
    cek('judul bagian 4', bv['sections'][3]['judul'] == 'Norma dan standar',
        bv['sections'][3]['judul'])

    nomor_bv = {n['nomor'] for n in bv_nodes}
    for wajib in ('1', '1.1', '1.2', '1.3', '2', '2.1', '2.1.1', '2.2.3', '3', '4.2.1'):
        cek(f'nomor {wajib} ada di Batasan Variabel', wajib in nomor_bv)

    bv_bernomor = [n for n in bv_nodes if n['is_numbered']]
    bv_paragraf = [n for n in bv_nodes if not n['is_numbered']]
    cek('19 subbagian bernomor', len(bv_bernomor) == 19, str(len(bv_bernomor)))
    cek('2 paragraf tanpa nomor', len(bv_paragraf) == 2, str(len(bv_paragraf)))

    teks_bv = normalize_text(bv['teks_mentah'])
    cek('heading bagian 3 bersih dari keterangan',
        next(n for n in bv_nodes if n['nomor'] == '3')['teks'] == 'Peraturan yang diperlukan')
    paragraf_3 = next(n for n in bv_paragraf if n['parent_nomor'] == '3')
    cek('"(Tidak ada.)" bagian 3 tersimpan sebagai paragraf',
        paragraf_3['teks'] == '(Tidak ada.)' and not paragraf_3['is_numbered'])
    paragraf_41 = next(n for n in bv_paragraf if n['parent_nomor'] == '4.1')
    cek('"(Tidak ada.)" bagian 4.1 tersimpan sebagai paragraf',
        paragraf_41['teks'] == '(Tidak ada.)' and not paragraf_41['is_numbered'])

    print("\n5. PANDUAN PENILAIAN")
    print(f"     Halaman: {pp['halaman_awal']}-{pp['halaman_akhir']} | subbagian: {len(pp_nodes)}")
    cetak_pohon(pp['sections'])
    cek('heading PANDUAN PENILAIAN ditemukan', pp['ditemukan'])
    cek('isi Panduan Penilaian tidak kosong', len(pp_nodes) > 0)
    cek('5 bagian utama', len(pp['sections']) == 5, str(len(pp['sections'])))
    cek('32 subbagian bernomor', len([n for n in pp_nodes if n['is_numbered']]) == 32,
        str(len([n for n in pp_nodes if n['is_numbered']])))
    cek('1 paragraf tanpa nomor', len([n for n in pp_nodes if not n['is_numbered']]) == 1,
        str(len([n for n in pp_nodes if not n['is_numbered']])))

    nomor_pp = {n['nomor'] for n in pp_nodes}
    for wajib in ('1', '1.1', '1.2.1', '1.2.3', '2', '3.1', '3.1.10', '3.2.4', '4.4', '5.1'):
        cek(f'nomor {wajib} ada di Panduan Penilaian', wajib in nomor_pp)

    cek('Panduan Penilaian berakhir di dalam unit',
        pp['halaman_akhir'] is not None and pp['halaman_akhir'] <= end_page,
        str(pp['halaman_akhir']))

    # --------------------------------------------------------- integritas lain
    print("\n6. INTEGRITAS & KETERLACAKAN")
    semua_node = bv_nodes + pp_nodes
    cek('semua node bernomor punya nomor',
        all(n['nomor'] for n in semua_node if n['is_numbered']))
    cek('paragraf tanpa nomor punya induk',
        all(n['parent_nomor'] for n in semua_node if not n['is_numbered']))
    cek('semua subbagian punya halaman sumber',
        all(n['halaman_pdf'] is not None for n in semua_node))
    cek('semua subbagian punya teks mentah',
        all(n.get('teks_mentah') for n in semua_node))
    cek('tidak ada node berisi nomor halaman saja',
        not any(n['teks'].strip().isdigit() for n in semua_node))
    cek('tidak ada teks dari unit berikutnya',
        'M.73ADV00.002.1' not in (bv['teks_mentah'] + pp['teks_mentah'])
        and 'KODE UNIT' not in (bv['teks_mentah'] + pp['teks_mentah']).upper())
    cek('metadata sumber lengkap',
        data['metadata_sumber']['nama_dokumen'] == PDF.name
        and data['metadata_sumber']['rentang_halaman_pdf'] == [start_page, end_page])

    # Nomor duplikat per induk + induk ada
    duplikat = []
    def cek_duplikat(nodes, induk):
        seen = set()
        for n in nodes:
            if not n['is_numbered']:
                continue
            if n['nomor'] in seen:
                duplikat.append((n['nomor'], induk))
            seen.add(n['nomor'])
            cek_duplikat(n.get('items', []), n['nomor'])
    cek_duplikat(bv['sections'], 'root')
    cek_duplikat(pp['sections'], 'root')
    cek('tidak ada nomor duplikat per induk', not duplikat, str(duplikat))

    # Batasan Variabel tidak tercampur Panduan Penilaian
    cek('BV tidak memuat heading PANDUAN PENILAIAN',
        'PANDUAN PENILAIAN' not in bv['teks_mentah'].upper())
    cek('PP tidak memuat heading BATASAN VARIABEL',
        'BATASAN VARIABEL' not in pp['teks_mentah'].upper())

    # -------------------------------------------------- verifikasi deterministik
    print("\n7. VERIFIKASI DETERMINISTIK TERHADAP TEKS PDF")
    doc = fitz.open(PDF)

    def halaman_teks(p1, p2):
        return normalize_text(' '.join(doc[p].get_text() for p in range(p1, p2 + 1)))

    diperiksa, cocok, tidak_cocok = 0, 0, []
    for node in semua_node:
        teks_hal = halaman_teks(node['halaman_pdf'], node['halaman_akhir'])
        for baris in node['teks_mentah'].split('\n'):
            b = normalize_text(baris)
            if not b:
                continue
            diperiksa += 1
            if b in teks_hal:
                cocok += 1
            else:
                tidak_cocok.append((node['nomor'], b[:70]))

    # KUK: baris mentah juga harus ada di halaman asalnya
    kuk_diperiksa, kuk_cocok, kuk_tidak = 0, 0, []
    for e in elemen:
        for k in e['kuk']:
            teks_hal = halaman_teks(k['halaman_pdf'], k['halaman_pdf'])
            for baris in (k.get('teks_mentah') or '').split('\n'):
                b = normalize_text(baris)
                if not b:
                    continue
                kuk_diperiksa += 1
                if b in teks_hal:
                    kuk_cocok += 1
                else:
                    kuk_tidak.append((k['nomor_kuk'], b[:70]))

    print(f"     Baris BV+PP : {cocok}/{diperiksa} baris ditemukan identik di teks PDF")
    print(f"     Baris KUK   : {kuk_cocok}/{kuk_diperiksa} baris ditemukan identik di teks PDF")
    cek('seluruh baris bagian ditemukan di PDF', cocok == diperiksa and diperiksa > 0,
        str(tidak_cocok[:3]))
    cek('seluruh baris KUK ditemukan di PDF', kuk_cocok == kuk_diperiksa and kuk_diperiksa > 0,
        str(kuk_tidak[:3]))

    doc.close()

    # ------------------------------------------------------------ round-trip
    print("\n8. JSON & VALIDASI AKHIR")
    with open(OUTPUT, encoding='utf-8') as f:
        ulang = json.load(f)
    cek('JSON dapat dibaca ulang tanpa kehilangan data', ulang == data)
    cek('status validasi = valid_struktur', data['validasi']['status'] == 'valid_struktur',
        str(data['validasi']['catatan']))
    cek('geometri kolom berkeyakinan high',
        data['geometri_tabel']['keyakinan'] == 'high',
        str(data['geometri_tabel']))
    print(f"     Batas kolom: {data['geometri_tabel']['batas_kolom_pt']} pt "
          f"(x1 kiri {data['geometri_tabel']['x1_maks_kolom_kiri']}, "
          f"x0 kanan {data['geometri_tabel']['x0_min_kolom_kanan']})")

    # --------------------------------------------------------------- ringkasan
    print("\n" + "=" * 100)
    print(f"HASIL: {len(lulus)} lulus, {len(gagal)} gagal")
    if gagal:
        print("GAGAL:")
        for g in gagal:
            print(f"  - {g}")
    print(f"Output: {OUTPUT}")
    print("=" * 100)

    return 0 if not gagal else 1




def test_unit_complete():
    assert main() == 0


if __name__ == '__main__':
    sys.exit(main())

"""
Pengujian Fase 2C — validasi struktur data dan metadata penomoran.

Menguji:
- field wajib pada setiap node (nomor, level, parent_nomor, teks, halaman_pdf, is_numbered)
- pemisahan nomor dari teks
- hierarki dan urutan penomoran
- paragraf tanpa nomor seperti "(Tidak ada.)"
- dua kelompok penomoran terpisah, masing-masing mulai dari 1
- restart penomoran pada unit baru
- penandaan penomoran tidak berurutan dan level di atas 3
- regresi Fase 1, 2A, 2B
"""

import json
import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.unit_parser import parse_unit
from app.section_parser import (
    parse_numbered_outline, validate_section, flatten_nodes, normalize_text,
)

PDF = project_root / 'data' / 'pdf' / 'SKKNI 2023-101.pdf.pdf'
FASE1 = project_root / 'data' / 'json' / 'hasil_identifikasi.json'
OUTPUT = project_root / 'data' / 'json' / 'test_unit_001_complete.json'

lulus, gagal = [], []


def cek(nama, kondisi, detail=''):
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}" + (f" — {detail}" if detail and not kondisi else ''))


def blok(baris, x0=86.3, y0=100.0, page=0):
    """Bangun block sintetis dengan bentuk sama seperti hasil PyMuPDF."""
    lines = [{'text': t, 'bbox': [x0, y0 + i * 21, 540, y0 + i * 21 + 12]}
             for i, t in enumerate(baris)]
    return {
        'text': '\n'.join(baris),
        'lines': lines,
        'bbox': [x0, y0, 540, y0 + 21 * len(baris)],
        'x0': x0, 'y0': y0, 'x1': 540, 'y1': y0 + 21 * len(baris),
        'page_idx': page,
    }


def main():
    print("=" * 100)
    print("PENGUJIAN FASE 2C — STRUKTUR DATA & METADATA PENOMORAN")
    print("=" * 100)

    with open(FASE1, encoding='utf-8') as f:
        fase1 = json.load(f)

    with open(OUTPUT, encoding='utf-8') as f:
        data = json.load(f)

    bv, pp = data['batasan_variabel'], data['panduan_penilaian']
    node_bv, node_pp = flatten_nodes(bv['sections']), flatten_nodes(pp['sections'])
    semua = node_bv + node_pp

    # ------------------------------------------------------- field wajib
    print("\n1. FIELD WAJIB PADA SETIAP NODE")
    wajib = ('nomor', 'level', 'parent_nomor', 'teks', 'halaman_pdf', 'is_numbered')
    hilang = [(n.get('nomor'), f) for n in semua for f in wajib if f not in n]
    cek('semua node punya 6 field wajib', not hilang, str(hilang[:3]))
    cek('level berupa bilangan bulat',
        all(isinstance(n['level'], int) and n['level'] >= 1 for n in semua))
    cek('is_numbered berupa boolean',
        all(isinstance(n['is_numbered'], bool) for n in semua))
    cek('parent_nomor null hanya pada akar',
        all((n['parent_nomor'] is None) == (n['level'] == 1) for n in semua),
        str([(n['nomor'], n['parent_nomor'], n['level']) for n in semua
             if (n['parent_nomor'] is None) != (n['level'] == 1)][:3]))

    # ------------------------------------------------ nomor vs teks
    print("\n2. PEMISAHAN NOMOR DARI TEKS")
    bercampur = []
    for n in semua:
        if not n['is_numbered']:
            continue
        if n['teks'].startswith(n['nomor']):
            bercampur.append(n['nomor'])
    cek('teks tidak diawali nomor (tidak tergabung permanen)', not bercampur, str(bercampur[:5]))
    contoh = next(n for n in semua if n['nomor'] == '2.2.3')
    cek('contoh 2.2.3: nomor dan teks terpisah',
        contoh['nomor'] == '2.2.3' and contoh['teks'].startswith('Data pendukung'),
        contoh['teks'][:60])
    cek('teks_mentah tetap menyimpan baris asli bernomor',
        contoh['teks_mentah'].startswith('2.2.3 '), contoh['teks_mentah'][:40])

    # ------------------------------------------------- hierarki & level
    print("\n3. HIERARKI & URUTAN PENOMORAN")
    salah_level = [n['nomor'] for n in semua
                   if n['is_numbered'] and n['level'] != len(n['nomor'].split('.'))]
    cek('level = jumlah segmen nomor', not salah_level, str(salah_level[:5]))

    def induk_benar(nodes, induk):
        for n in nodes:
            if n['is_numbered']:
                if (induk is None and n['parent_nomor'] is not None) or \
                   (induk is not None and n['parent_nomor'] != induk['nomor']):
                    return False
                if induk is not None and n['level'] != induk['level'] + 1:
                    return False
            if not induk_benar(n.get('items', []), n if n['is_numbered'] else induk):
                return False
        return True

    cek('parent_nomor dan level konsisten', induk_benar(bv['sections'], None)
        and induk_benar(pp['sections'], None))
    cek('tidak ada catatan validasi penomoran',
        not bv['catatan'] and not pp['catatan'], str(bv['catatan'] + pp['catatan']))

    # ------------------------------------------- paragraf tanpa nomor
    print("\n4. PARAGRAF TANPA NOMOR")
    paragraf = [n for n in semua if not n['is_numbered']]
    cek('3 paragraf tanpa nomor tersimpan terpisah', len(paragraf) == 3,
        str([(p['teks'], p['parent_nomor']) for p in paragraf]))
    cek('semua paragraf berisi "(Tidak ada.)"',
        all(p['teks'] == '(Tidak ada.)' for p in paragraf),
        str([p['teks'] for p in paragraf]))
    cek('paragraf punya induk dan level induk+1',
        all(p['parent_nomor'] for p in paragraf)
        and all(p['level'] >= 2 for p in paragraf))
    induk_paragraf = sorted(p['parent_nomor'] for p in paragraf)
    cek('induk paragraf benar (3, 4.1, 2)', induk_paragraf == ['2', '3', '4.1'],
        str(induk_paragraf))

    # ------------------------------------------- kelompok terpisah
    print("\n5. DUA KELOMPOK PENOMORAN TERPISAH")
    cek('grup BV = batasan_variabel', bv['penomoran']['grup'] == 'batasan_variabel')
    cek('grup PP = panduan_penilaian', pp['penomoran']['grup'] == 'panduan_penilaian')
    cek('BV dimulai dari 1', bv['penomoran']['nomor_akar'][0] == '1',
        str(bv['penomoran']['nomor_akar']))
    cek('PP dimulai dari 1', pp['penomoran']['nomor_akar'][0] == '1',
        str(pp['penomoran']['nomor_akar']))
    cek('level maksimum 3 pada kedua kelompok',
        bv['penomoran']['jumlah_level_maks'] == 3
        and pp['penomoran']['jumlah_level_maks'] == 3)
    cek('tidak ada level di atas 3', not bv['penomoran']['level_melebihi_tiga']
        and not pp['penomoran']['level_melebihi_tiga'])
    cek('jumlah bernomor BV 19 / PP 32',
        bv['penomoran']['jumlah_node_bernomor'] == 19
        and pp['penomoran']['jumlah_node_bernomor'] == 32)
    cek('metadata kelompok di level unit'
        , data['penomoran']['kelompok_terpisah'] is True
        and data['penomoran']['restart_per_unit'] is True
        and data['penomoran']['nomor_dipisah_dari_teks'] is True)
    cek('rencana indentasi Word tersimpan',
        data['penomoran']['rencana_word_multilevel']['level_3']['left_indent_cm'] == 2.23)

    # ------------------------------------------------ restart per unit
    print("\n6. RESTART PENOMORAN PADA UNIT BARU")
    unit2 = next(u for u in fase1['units'] if u['code'] == 'M.73ADV00.002.1')
    d2 = parse_unit(str(PDF), 'M.73ADV00.002.1', unit2['start_page'], unit2['end_page'])
    cek('unit 2 BV mulai dari 1', d2['batasan_variabel']['penomoran']['nomor_akar'][0] == '1',
        str(d2['batasan_variabel']['penomoran']['nomor_akar']))
    cek('unit 2 PP mulai dari 1', d2['panduan_penilaian']['penomoran']['nomor_akar'][0] == '1',
        str(d2['panduan_penilaian']['penomoran']['nomor_akar']))
    cek('penomoran unit 1 tidak terbawa ke unit 2',
        d2['batasan_variabel']['penomoran']['nomor_akar']
        == ['1', '2', '3', '4'])

    ulang = parse_unit(str(PDF), 'M.73ADV00.001.1', 21, 24)
    cek('hasil parse unit 1 deterministik (tanpa state global)',
        json.dumps(ulang, sort_keys=True, ensure_ascii=False)
        == json.dumps(data, sort_keys=True, ensure_ascii=False))

    # ------------------------------------------------- uji sintetis
    print("\n7. UJI SINTETIS ATURAN VALIDASI")

    # (a) penomoran tidak berurutan: 1, 2, 4
    roots, _ = parse_numbered_outline(
        [blok(['1. Satu']), blok(['2. Dua']), blok(['4. Empat'])], 936.0)
    cat = validate_section({'ditemukan': True, 'sections': roots}, 'UJI')
    cek('penomoran tidak berurutan ditandai',
        any('tidak berurutan' in c for c in cat), str(cat))

    # (b) lebih dari tiga level: 1, 1.1, 1.1.1, 1.1.1.1
    roots, _ = parse_numbered_outline(
        [blok(['1. Satu']), blok(['1.1 Dua']), blok(['1.1.1 Tiga']),
         blok(['1.1.1.1 Empat'])], 936.0)
    level4 = [n for n in flatten_nodes(roots) if n['level'] == 4]
    cat = validate_section({'ditemukan': True, 'sections': roots}, 'UJI')
    cek('level 4 dipertahankan apa adanya', len(level4) == 1
        and level4[0]['nomor'] == '1.1.1.1')
    cek('level di atas 3 dilaporkan untuk penentuan format',
        any('di atas 3' in c for c in cat), str(cat))

    # (c) paragraf tanpa nomor
    roots, _ = parse_numbered_outline(
        [blok(['1. Satu'], x0=86.3), blok(['(Tidak ada.)'], x0=114.7, y0=140.0)], 936.0)
    anak = roots[0]['items'][0]
    cek('paragraf "(Tidak ada.)" jadi node sendiri',
        roots[0]['teks'] == 'Satu' and anak['teks'] == '(Tidak ada.)'
        and anak['is_numbered'] is False and anak['parent_nomor'] == '1'
        and anak['level'] == 2, json.dumps(anak, ensure_ascii=False)[:120])

    # (d) nomor tidak dibuat ulang / tidak dikoreksi
    roots, _ = parse_numbered_outline(
        [blok(['7. Tujuh']), blok(['7.3 Tujuh tiga'])], 936.0)
    nomor = [n['nomor'] for n in flatten_nodes(roots)]
    cek('nomor asli tidak dikoreksi otomatis', nomor == ['7', '7.3'], str(nomor))
    cat = validate_section({'ditemukan': True, 'sections': roots}, 'UJI')
    cek('nomor tidak dimulai dari 1 ditandai',
        any('tidak dimulai dari nomor 1' in c for c in cat), str(cat))

    # ------------------------------------------------------ regresi
    print("\n8. REGRESI FASE 1, 2A, 2B")
    for nama in ('test_extractor.py', 'test_unit_parser.py', 'test_unit_complete.py'):
        r = subprocess.run([sys.executable, str(project_root / 'tests' / nama)],
                           capture_output=True, text=True, cwd=str(project_root))
        cek(f'{nama} lulus', r.returncode == 0,
            (r.stdout + r.stderr).strip().splitlines()[-1] if r.returncode else '')

    # ---------------------------------------------------- ringkasan
    print("\n" + "=" * 100)
    print(f"HASIL: {len(lulus)} lulus, {len(gagal)} gagal")
    if gagal:
        print("GAGAL:")
        for g in gagal:
            print(f"  - {g}")
    print("=" * 100)
    return 0 if not gagal else 1


if __name__ == '__main__':
    sys.exit(main())

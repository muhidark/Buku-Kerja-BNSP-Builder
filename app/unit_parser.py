"""
SKKNI Extractor - Parser Unit Kompetensi (Fase 2A + 2B)

Mengekstrak dari PDF SKKNI:
- identitas unit (kode, judul, deskripsi)
- Elemen Kompetensi dan KUK
- Batasan Variabel
- Panduan Penilaian

Batas kolom tabel dideteksi dinamis dari geometri header dan sebaran x0 block
(tidak memakai threshold tetap).

Prioritas: akurasi dan ketertelusuran, bukan kecepatan.
"""

import re
import json
from pathlib import Path
from typing import Optional

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from app.section_parser import (
    HEADING_BATASAN,
    HEADING_PANDUAN,
    collect_unit_blocks,
    extract_blocks,
    is_footer_or_header_block,
    find_header_lines,
    detect_column_geometry,
    extract_section,
    validate_section,
    flatten_nodes,
    normalize_text,
)


UNIT_CODE_PATTERN = re.compile(r'[A-Z]\.\d{2}[A-Z]{2,3}\d{2}\.\d{3}\.\d')

# Label yang mengakhiri blok identitas (judul/deskripsi), mana pun yang lebih dulu
# "JUDUL UNI" muncul pada SKKNI 2018-107 (salah ketik sumber), jadi label
# dibuat toleran; teks judul tetap diambil apa adanya.
IDENTITY_STOP = (r'(?:ELEMEN\s+KOMPETENSI|BATASAN\s+VARIABEL|PANDUAN\s+PENILAIAN'
                 r'|KODE\s+UNIT|JUDUL\s+UNI(?:T)?|DESKRIPSI\s+UNIT)')


def visual_order_text(doc, start_page: int, end_page: int) -> str:
    """
    Gabungkan teks halaman menurut posisi visual (atas->bawah, kiri->kanan).

    Urutan stream PyMuPDF tidak selalu sama dengan urutan baca; fungsi ini
    membuat batas bagian dapat ditentukan dengan andal.
    """
    parts = []
    for page_idx in range(start_page, end_page + 1):
        page = doc[page_idx]
        blocks = extract_blocks(page)
        blocks.sort(key=lambda b: (round(b['y0'], 1), b['x0']))
        for b in blocks:
            if is_footer_or_header_block(b, page.rect.height):
                continue
            parts.append(b['text'])
    return '\n'.join(parts)
KUK_PATTERN = re.compile(r'^(\d+\.\d+)\s+(.+)$')
KUK_NUMBER_ONLY = re.compile(r'^(\d+\.\d+)\s*$')
ELEMEN_PATTERN = re.compile(r'^(\d+)\.\s+(.+)$')
POLA_KUK_AWAL = re.compile(r'^\s*\d+\.\d+(?:\.\d+)?\s')
RE_HALAMAN_SAJA = re.compile(r'^-\s*\d+\s*-$')


# --------------------------------------------------------------------------
# Identitas unit
# --------------------------------------------------------------------------

def extract_identity(doc, start_page: int, end_page: int) -> dict:
    """
    Ekstrak identitas unit: kode, judul, deskripsi (teks asli, tanpa parafrasa).
    Ditelusuri dari halaman pertama unit.
    """
    # Teks disusun menurut POSISI (y lalu x), bukan urutan stream PyMuPDF.
    # Pada sebagian PDF (mis. SKKNI 2018-107) blok Batasan Variabel muncul
    # lebih dulu di stream daripada header tabel, sehingga pembacaan stream
    # membuat deskripsi menyerap Batasan Variabel.
    text = visual_order_text(doc, start_page, end_page)

    code_match = UNIT_CODE_PATTERN.search(text)
    code = code_match.group(0) if code_match else None

    # Batas akhir identitas: komponen struktural berikutnya, mana pun yang
    # lebih dulu muncul secara visual (bukan hanya ELEMEN KOMPETENSI).
    title_match = re.search(
        r'JUDUL\s+UNI(?:T)?\s*:\s*\n?(.+?)(?=\n?\s*' + IDENTITY_STOP + r')',
        text,
        re.DOTALL | re.IGNORECASE
    )
    title = normalize_text(title_match.group(1)) if title_match else None

    desc_match = re.search(
        r'DESKRIPSI\s+UNIT\s*:\s*\n?(.+?)(?=\n?\s*' + IDENTITY_STOP + r')',
        text,
        re.DOTALL | re.IGNORECASE
    )
    description = normalize_text(desc_match.group(1)) if desc_match else None

    return {
        'kode_unit': code,
        'judul_unit': title,
        'deskripsi_unit': description,
        'halaman_pdf': start_page
    }


# --------------------------------------------------------------------------
# Tabel Elemen / KUK
# --------------------------------------------------------------------------

def locate_table_blocks(blocks: list[dict]) -> tuple[list[dict], Optional[dict], list[str]]:
    """
    Tentukan blok tabel Elemen/KUK berdasarkan POSISI header dan BATASAN VARIABEL.

    Tidak memakai urutan daftar block: pada sebagian PDF (mis. SKKNI 2018-107)
    blok tabel muncul setelah blok Batasan Variabel dalam urutan PyMuPDF,
    walaupun secara visual tabel berada di atasnya.

    Returns:
        (table_blocks, header_block, catatan)
    """
    notes = []
    header = None
    batasan = None

    # Jangan berhenti saat menemukan BATASAN: pada sebagian PDF header tabel
    # muncul setelahnya dalam urutan daftar block.
    for b in blocks:
        first = b['lines'][0]['text'].strip().upper() if b['lines'] else ''
        if header is None and first == 'ELEMEN KOMPETENSI':
            header = b
        if batasan is None and first == HEADING_BATASAN:
            batasan = b

    if header is None:
        return [], None, notes

    hpos = (header['page_idx'], header['y0'])
    bpos = (batasan['page_idx'], batasan['y0']) if batasan is not None else None

    if bpos is None:
        notes.append('BATASAN VARIABEL tidak ditemukan; tabel diambil sampai akhir halaman')

    table = []
    for b in blocks:
        pos = (b['page_idx'], b['y0'])
        if pos <= hpos:
            continue
        if bpos is not None and pos >= bpos:
            continue
        if is_table_header(b):
            continue
        table.append(b)

    return table, header, notes


def split_block_by_columns(block: dict, boundary: float) -> list[dict]:
    """
    Pecah block yang menyeberangi batas kolom menjadi bagian per kolom.

    Sebagian PDF menggabungkan sel Elemen dan sel KUK dalam satu block
    (x0 di kolom kiri, x1 melewati kolom kanan). Tanpa pemecahan, seluruh
    KUK hilang ke kolom Elemen.
    """
    if not (block['x0'] < boundary <= block['x1']):
        kolom = 'elemen' if block['x0'] < boundary else 'kuk'
        return [{**block, 'kolom': kolom}]

    # Blok lebar penuh: batas kolom global bisa meleset beberapa poin.
    # Pakai celah x0 terbesar DI DALAM blok ini agar pemisahan tepat.
    xs = sorted({round(ln['bbox'][0], 1) for ln in block['lines']})
    batas = boundary
    celah, titik = 0.0, None
    for a, b in zip(xs, xs[1:]):
        if b - a > celah:
            celah, titik = b - a, (a + b) / 2
    if titik is not None and celah >= 40:
        batas = titik

    kiri, kanan = [], []
    for ln in block['lines']:
        (kiri if ln['bbox'][0] < batas else kanan).append(ln)

    if not kiri or not kanan:
        kolom = 'elemen' if block['x0'] < boundary else 'kuk'
        return [{**block, 'kolom': kolom}]

    hasil = []
    for grup, kolom in ((kiri, 'elemen'), (kanan, 'kuk')):
        bbox = [min(l['bbox'][0] for l in grup), min(l['bbox'][1] for l in grup),
                max(l['bbox'][2] for l in grup), max(l['bbox'][3] for l in grup)]
        hasil.append({
            'text': '\n'.join(l['text'] for l in grup),
            'lines': grup,
            'bbox': bbox,
            'x0': bbox[0], 'y0': bbox[1], 'x1': bbox[2], 'y1': bbox[3],
            'page_idx': block['page_idx'],
            'kolom': kolom,
        })
    return hasil


def is_table_header(block: dict) -> bool:
    """Header tabel berulang di halaman lanjutan."""
    text_upper = block['text'].upper()
    return 'ELEMEN KOMPETENSI' in text_upper and 'KRITERIA UNJUK KERJA' in text_upper


def classify_column(block: dict, boundary: float) -> str:
    """Klasifikasi block ke kolom 'elemen' atau 'kuk' berdasar batas kolom dinamis."""
    return 'elemen' if block['x0'] < boundary else 'kuk'


def parse_kuk_text(text: str) -> list[dict]:
    """
    Parse teks kolom KUK menjadi KUK individual.
    Setiap KUK dimulai pola "X.Y "; baris lain menjadi lanjutan.
    """
    kuk_list = []
    current = None
    buf = []

    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        m = KUK_PATTERN.match(line)
        if m:
            if current:
                kuk_list.append({'nomor_kuk': current,
                                 'uraian_kuk': normalize_text(' '.join(buf))})
            current = m.group(1)
            buf = [m.group(2)]
        elif KUK_NUMBER_ONLY.match(line):
            # Varian layout: nomor KUK berdiri sendiri di baris, teks di baris berikut
            if current:
                kuk_list.append({'nomor_kuk': current,
                                 'uraian_kuk': normalize_text(' '.join(buf))})
            current = KUK_NUMBER_ONLY.match(line).group(1)
            buf = []
        elif current:
            buf.append(line)

    if current:
        kuk_list.append({'nomor_kuk': current,
                         'uraian_kuk': normalize_text(' '.join(buf))})

    return kuk_list


def parse_elemen_text(text: str) -> Optional[dict]:
    """Parse teks kolom Elemen: "X. Nama elemen"."""
    full = normalize_text(text)
    m = ELEMEN_PATTERN.match(full)
    if not m:
        return None
    return {'nomor_elemen': m.group(1), 'nama_elemen': m.group(2).strip()}


def ekstrak_elemen_kuk_per_kata(doc, start_page: int, end_page: int,
                                elemen_header_bbox, kuk_header_bbox) -> tuple[list[dict], list[str], dict]:
    """
    Cadangan pembacaan tabel Elemen/KUK di tingkat KATA.

    Dipakai ketika dua kolom tabel tergabung dalam satu block teks sehingga
    deteksi batas kolom berbasis block gagal (mis. SKKNI terbitan 2024).
    Setiap kata dipisahkan menurut koordinat x-nya, bukan menurut block.

    Returns:
        (elemen_list, catatan, geometri)
    """
    notes = []
    if not elemen_header_bbox:
        return [], ['Header tabel ELEMEN tidak ditemukan untuk pembacaan per-kata'], {}

    # Batas kolom. Titik tengah antara header ELEMEN dan header KUK terlalu ke kanan
    # pada PDF yang menggabungkan kolom, karena nomor KUK (mis. "1.1") dicetak lebih
    # ke kiri daripada teks KUK-nya. Karena itu dipakai posisi nomor KUK yang benar-benar
    # ada di halaman, bukan posisi teks header KUK.
    nomor_kuk_x = []
    for idx in range(start_page, end_page + 1):
        for w in doc[idx].get_text('words'):
            if w[0] > elemen_header_bbox[2] and KUK_NUMBER_ONLY.match(w[4].strip()):
                nomor_kuk_x.append(w[0])

    if nomor_kuk_x:
        batas = (elemen_header_bbox[2] + min(nomor_kuk_x)) / 2.0
    elif kuk_header_bbox:
        batas = (elemen_header_bbox[2] + kuk_header_bbox[0]) / 2.0
    else:
        batas = elemen_header_bbox[2] + 40.0

    baris_kiri, baris_kanan = [], []
    halaman_elemen, halaman_kuk = {}, {}

    for idx in range(start_page, end_page + 1):
        halaman = doc[idx]
        kata = halaman.get_text('words')
        if not kata:
            continue

        per_baris = {}
        for w in kata:
            x0, y0, teks = w[0], w[1], w[4]
            per_baris.setdefault(round(y0 / 2) * 2, []).append((x0, teks))

        kiri_hal, kanan_hal = [], []
        ada_header = False
        for y in sorted(per_baris):
            urut = sorted(per_baris[y], key=lambda t: t[0])
            k = ' '.join(t[1] for t in urut if t[0] < batas).strip()
            r = ' '.join(t[1] for t in urut if t[0] >= batas).strip()
            if k.upper() == 'ELEMEN KOMPETENSI':
                ada_header = True
                continue
            if r.upper() == 'KRITERIA UNJUK KERJA':
                continue
            if k or r:
                kiri_hal.append((k, r, idx))

        # Halaman lanjutan hanya dianggap bagian tabel bila header tabel berulang.
        if idx > start_page and not ada_header:
            break

        # Kolom kiri dan kanan harus dipotong pada titik yang sama: heading bagian
        # berikutnya (BATASAN VARIABEL / PANDUAN PENILAIAN) menandai akhir tabel.
        for k, r, hal in kiri_hal:
            if k.upper().startswith(('BATASAN VARIABEL', 'PANDUAN PENILAIAN')):
                baris_kiri.append(('__STOP__', hal))
                break
            if k:
                baris_kiri.append((k, hal))
            if r:
                baris_kanan.append((r, hal))
        if baris_kiri and baris_kiri[-1][0] == '__STOP__':
            break

    # Buang penanda berhenti
    baris_kiri = [b for b in baris_kiri if b[0] != '__STOP__']

    elemen_list = []
    for teks, hal in baris_kiri:
        if RE_HALAMAN_SAJA.match(teks):
            continue
        m = ELEMEN_PATTERN.match(normalize_text(teks))
        if m:
            elemen_list.append({
                'nomor_elemen': m.group(1),
                'nama_elemen': m.group(2).strip(),
                'kuk': [],
                'halaman_pdf': hal,
                'teks_mentah': teks,
            })
        elif elemen_list and teks.strip():
            # Lanjutan nama elemen yang terpotong ke baris berikutnya
            elemen_list[-1]['nama_elemen'] = (
                elemen_list[-1]['nama_elemen'] + ' ' + teks.strip()
            ).strip()
            elemen_list[-1]['teks_mentah'] += '\n' + teks

    if not elemen_list:
        return [], ['Pembacaan per-kata tidak menemukan elemen'], {}

    kuk_list = []
    for teks, hal in baris_kanan:
        if RE_HALAMAN_SAJA.match(teks):
            continue
        m = KUK_PATTERN.match(teks)
        if m:
            kuk_list.append({'nomor_kuk': m.group(1), 'uraian_kuk': m.group(2),
                             'halaman_pdf': hal})
            continue
        m2 = KUK_NUMBER_ONLY.match(teks)
        if m2:
            kuk_list.append({'nomor_kuk': m2.group(1), 'uraian_kuk': '', 'halaman_pdf': hal})
            continue
        if kuk_list:
            kuk_list[-1]['uraian_kuk'] = (
                kuk_list[-1]['uraian_kuk'] + ' ' + teks
            ).strip() if kuk_list[-1]['uraian_kuk'] else teks

    for kuk in kuk_list:
        kuk['uraian_kuk'] = normalize_text(kuk['uraian_kuk'])
        kuk['teks_mentah'] = kuk['uraian_kuk']
        prefix = kuk['nomor_kuk'].split('.')[0]
        target = next((e for e in elemen_list if e['nomor_elemen'] == prefix), None)
        if target is None:
            notes.append(f"KUK {kuk['nomor_kuk']} tidak cocok dengan elemen manapun")
        else:
            target['kuk'].append(kuk)

    for e in elemen_list:
        if not e['kuk']:
            notes.append(f"Elemen {e['nomor_elemen']} tidak memiliki KUK")

    geometry = {
        'boundary': round(batas, 2),
        'left_max_x1': elemen_header_bbox[2],
        'right_min_x0': kuk_header_bbox[0] if kuk_header_bbox else None,
        'confidence': 'medium',
        'keyakinan': 'per_kata',
        'metode': 'per_kata',
        'catatan': ['Tabel dibaca dengan metode per-kata: dua kolom tergabung dalam satu block teks'],
        'header_elemen_bbox': elemen_header_bbox,
        'header_kuk_bbox': kuk_header_bbox,
    }
    return elemen_list, notes, geometry


def extract_elemen_kuk(doc, start_page: int, end_page: int) -> tuple[list[dict], list[str], dict]:
    """
    Ekstrak Elemen Kompetensi dan KUK dengan batas kolom dinamis.

    Returns:
        (elemen_list, catatan, geometri)
    """
    notes = []
    all_blocks, page_height = collect_unit_blocks(doc, start_page, end_page)

    table_blocks, header_block, region_notes = locate_table_blocks(all_blocks)
    notes.extend(region_notes)

    if header_block is None:
        return [], ['Tabel Elemen Kompetensi tidak ditemukan'], {}

    table_blocks = [b for b in table_blocks
                    if not is_footer_or_header_block(b, page_height)]
    table_blocks.sort(key=lambda b: (b['page_idx'], b['y0']))

    # Deteksi geometri kolom dinamis dari header tabel + sebaran data
    elemen_h, kuk_h = find_header_lines([header_block])
    geometry = detect_column_geometry(table_blocks, elemen_h, kuk_h)
    notes.extend(geometry['catatan'])

    boundary = geometry['boundary']

    # Cadangan: sebagian PDF (mis. SKKNI terbitan 2024) menyatukan kedua kolom
    # tabel ke dalam satu block teks. Pada kasus itu tidak ada celah koordinat x0
    # antar kolom, sehingga batas hasil hitungan block jatuh di kiri header ELEMEN
    # dan semua block terbaca sebagai kolom KUK. Pembacaan per-kata dipakai sebagai
    # pengganti, dan hasilnya ditandai di geometri ('metode': 'per_kata').
    batas_header_elemen = elemen_h[2] if elemen_h else None
    if boundary is None or (batas_header_elemen and boundary <= batas_header_elemen):
        elemen_kata, notes_kata, geo_kata = ekstrak_elemen_kuk_per_kata(
            doc, start_page, end_page, elemen_h, kuk_h)
        if elemen_kata:
            notes.extend(notes_kata)
            return elemen_kata, notes, geo_kata

    if boundary is None:
        return [], notes + ['Batas kolom tidak dapat ditentukan'], geometry

    # Klasifikasi per kolom; block yang menyeberangi batas dipecah per baris
    elemen_blocks, kuk_blocks = [], []
    for b in table_blocks:
        for part in split_block_by_columns(b, boundary):
            kolom = part.get('kolom', 'elemen' if part['x0'] < boundary else 'kuk')
            # Sel KUK dapat digambar selebar halaman ketika sel elemen pada
            # baris lanjutan kosong. Kenali dari pola nomor KUK di awal teks.
            if kolom == 'elemen' and POLA_KUK_AWAL.match(part['text']):
                kolom = 'kuk'
            (kuk_blocks if kolom == 'kuk' else elemen_blocks).append(part)

    # Parse elemen
    elemen_list = []
    for b in elemen_blocks:
        elem = parse_elemen_text(b['text'])
        if elem:
            elem['kuk'] = []
            elem['halaman_pdf'] = b['page_idx']
            elem['bbox'] = b['bbox']
            elem['teks_mentah'] = b['text']
            elemen_list.append(elem)
        else:
            notes.append(f"Block kolom elemen tidak dapat diparse: {b['text'][:60]!r}")

    # Parse KUK
    if kuk_blocks:
        kuk_blocks_sorted = sorted(kuk_blocks, key=lambda b: (b['page_idx'], b['y0']))
        kuk_full_text = '\n'.join(b['text'] for b in kuk_blocks_sorted)
        kuk_list = parse_kuk_text(kuk_full_text)

        page_map, bbox_map, raw_map = {}, {}, {}
        for b in kuk_blocks_sorted:
            for line in b['text'].split('\n'):
                m = KUK_PATTERN.match(line.strip())
                if m:
                    page_map.setdefault(m.group(1), b['page_idx'])
                    bbox_map.setdefault(m.group(1), b['bbox'])
                    raw_map.setdefault(m.group(1), b['text'])

        for kuk in kuk_list:
            nomor = kuk['nomor_kuk']
            kuk['halaman_pdf'] = page_map.get(nomor, start_page)
            kuk['bbox'] = bbox_map.get(nomor)
            kuk['teks_mentah'] = raw_map.get(nomor)
            prefix = nomor.split('.')[0]
            target = next((e for e in elemen_list if e['nomor_elemen'] == prefix), None)
            if target is None:
                notes.append(f"KUK {nomor} tidak cocok dengan elemen manapun")
            else:
                target['kuk'].append(kuk)

    for elem in elemen_list:
        if not elem['kuk']:
            notes.append(f"Elemen {elem['nomor_elemen']} tidak memiliki KUK")

    return elemen_list, notes, geometry


# --------------------------------------------------------------------------
# Validasi
# --------------------------------------------------------------------------

def validate_unit(unit_data: dict) -> tuple[str, list[str], list[dict]]:
    """
    Validasi struktur unit hasil ekstraksi (mencakup tabel dan kedua bagian).

    Status:
    - valid_struktur  : lolos seluruh pemeriksaan otomatis
    - perlu_verifikasi: ada ketidaksesuaian ringan / bagian ditandai manual
    - gagal_ekstraksi : bagian inti tidak terbaca
    """
    notes = list(unit_data.get('validasi', {}).get('catatan', []))

    if not unit_data.get('kode_unit'):
        notes.append('Kode unit kosong')
    if not unit_data.get('judul_unit'):
        notes.append('Judul unit kosong')
    if not unit_data.get('deskripsi_unit'):
        notes.append('Deskripsi unit tidak ditemukan')

    elemen = unit_data.get('elemen_kompetensi') or []
    if not elemen:
        notes.append('Tabel Elemen Kompetensi tidak ditemukan')
        return 'gagal_ekstraksi', notes, []

    for e in elemen:
        if not e.get('nomor_elemen'):
            notes.append(f"Elemen tanpa nomor: {str(e.get('nama_elemen'))[:50]}")
        for k in e.get('kuk', []):
            if not k.get('nomor_kuk'):
                notes.append(f"KUK tanpa nomor di elemen {e.get('nomor_elemen')}")
            if k.get('nomor_kuk', '').split('.')[0] != e.get('nomor_elemen'):
                notes.append(
                    f"KUK {k.get('nomor_kuk')} tidak sesuai elemen {e.get('nomor_elemen')}")
        if not e.get('kuk'):
            notes.append(f"Elemen {e.get('nomor_elemen')} tidak memiliki KUK")

    semua_kuk = [k.get('nomor_kuk') for e in elemen for k in e.get('kuk', [])]
    duplikat = sorted({n for n in semua_kuk if semua_kuk.count(n) > 1})
    if duplikat:
        notes.append(f"Nomor KUK duplikat: {duplikat}")

    # Peringatan format SUMBER (bukan kesalahan ekstraksi): tidak mengubah teks
    # dan tidak memengaruhi status kesesuaian teks.
    peringatan = []

    for e in elemen:
        for k in e.get('kuk', []):
            uraian = k.get('uraian_kuk', '')
            if len(uraian) > 500:
                notes.append(
                    f"KUK {k.get('nomor_kuk')} sangat panjang ({len(uraian)} karakter)")
            if uraian and not re.search(r'[.!?)]$', uraian):
                peringatan.append({
                    'kategori': 'peringatan_format_sumber',
                    'nomor_kuk': k.get('nomor_kuk'),
                    'halaman_pdf': k.get('halaman_pdf'),
                    'pesan': ('KUK tidak diakhiri tanda baca pada PDF sumber; '
                              'teks dibiarkan apa adanya'),
                })

    # Batasan Variabel & Panduan Penilaian
    for key, nama in (('batasan_variabel', 'BATASAN VARIABEL'),
                      ('panduan_penilaian', 'PANDUAN PENILAIAN')):
        bagian = unit_data.get(key) or {}
        notes.extend(validate_section(bagian, nama))

        teks = bagian.get('teks_mentah', '') or ''
        # Kode unit lain boleh disebut sebagai rujukan; yang menandakan kebocoran
        # adalah adanya baris label "KODE UNIT" di dalam bagian.
        if 'KODE UNIT' in teks.upper():
            notes.append(f'{nama}: memuat label KODE UNIT (kemungkinan bocor ke unit berikutnya)')

        for node in flatten_nodes(bagian.get('sections', [])):
            if re.fullmatch(r'\d{1,3}', (node.get('teks') or '').strip()):
                notes.append(f'{nama}: nomor {node.get("nomor")} hanya berisi angka halaman')

    # Dua kelompok penomoran harus terpisah dan masing-masing mulai dari 1
    bv_pen = (unit_data.get('batasan_variabel') or {}).get('penomoran') or {}
    pp_pen = (unit_data.get('panduan_penilaian') or {}).get('penomoran') or {}
    for label, pen in (('BATASAN VARIABEL', bv_pen), ('PANDUAN PENILAIAN', pp_pen)):
        akar = pen.get('nomor_akar') or []
        if akar and akar[0] != '1':
            notes.append(f'{label}: penomoran tidak dimulai dari 1 (mulai {akar[0]})')

    geo = unit_data.get('geometri_tabel') or {}
    if geo.get('keyakinan') == 'low':
        notes.append('Batas kolom tabel berkeyakinan rendah')

    # Bagian yang menandakan teks dari luar tabel ikut terbaca sebagai elemen/KUK.
    PENANDA_BAGIAN = ('konteks variabel', 'peralatan dan perlengkapan', 'peraturan yang diperlukan',
                      'norma dan standar', 'panduan penilaian', 'batasan variabel',
                      'konteks penilaian', 'persyaratan kompetensi')
    for e in elemen:
        nama = (e.get('nama_elemen') or '').lower()
        if any(p in nama for p in PENANDA_BAGIAN):
            notes.append(f"Elemen {e.get('nomor_elemen')} berisi teks bagian lain, bukan nama elemen")

    # Status ditentukan oleh inti tabel (elemen + KUK), bukan oleh rincian bagian lain.
    # Dengan begitu bagian BATASAN VARIABEL yang gagal terbaca tidak membuat unit
    # berstatus gagal total, tetapi tetap muncul sebagai catatan untuk diperiksa.
    inti_gagal = (not elemen) or any(not e.get('kuk') for e in elemen)

    if inti_gagal:
        status = 'gagal_ekstraksi'
    elif notes:
        status = 'perlu_verifikasi'
    else:
        status = 'valid_struktur'

    return status, notes, peringatan


# --------------------------------------------------------------------------
# Orkestrasi
# --------------------------------------------------------------------------

def parse_unit(pdf_path: str, kode_unit: str, start_page: int, end_page: int) -> dict:
    """
    Parse satu unit kompetensi secara lengkap (identitas, elemen/KUK,
    batasan variabel, panduan penilaian) beserta metadata sumber.
    """
    doc = fitz.open(pdf_path)

    try:
        identity = extract_identity(doc, start_page, end_page)
        elemen_list, extraction_notes, geometry = extract_elemen_kuk(
            doc, start_page, end_page)

        all_blocks, page_height = collect_unit_blocks(doc, start_page, end_page)

        bv = extract_section(all_blocks, HEADING_BATASAN,
                             stop_headings=(HEADING_PANDUAN,), page_height=page_height,
                             grup='batasan_variabel')
        pp = extract_section(all_blocks, HEADING_PANDUAN,
                             stop_headings=(HEADING_BATASAN,), page_height=page_height,
                             grup='panduan_penilaian')

        unit_data = {
            'metadata_sumber': {
                'nama_dokumen': Path(pdf_path).name,
                'kode_unit': identity['kode_unit'],
                'rentang_halaman_pdf': [start_page, end_page],
                'indeks_halaman': '0-based (indeks halaman PDF)',
                'tinggi_halaman_pt': round(page_height, 2)
            },
            'kode_unit': identity['kode_unit'],
            'judul_unit': identity['judul_unit'],
            'deskripsi_unit': identity['deskripsi_unit'],
            'elemen_kompetensi': elemen_list,
            'batasan_variabel': {
                'ditemukan': bv['ditemukan'],
                'halaman_awal': bv['halaman_awal'],
                'halaman_akhir': bv['halaman_akhir'],
                'status_validasi': 'ok',
                'penomoran': bv['penomoran'],
                'sections': bv['sections'],
                'catatan': bv['notes'],
                'teks_mentah': bv['teks_mentah']
            },
            'panduan_penilaian': {
                'ditemukan': pp['ditemukan'],
                'halaman_awal': pp['halaman_awal'],
                'halaman_akhir': pp['halaman_akhir'],
                'status_validasi': 'ok',
                'penomoran': pp['penomoran'],
                'sections': pp['sections'],
                'catatan': pp['notes'],
                'teks_mentah': pp['teks_mentah']
            },
            'penomoran': {
                'kelompok': {
                    'batasan_variabel': bv['penomoran'],
                    'panduan_penilaian': pp['penomoran']
                },
                'kelompok_terpisah': True,
                'restart_per_unit': True,
                'nomor_dipisah_dari_teks': True,
                'rencana_word_multilevel': {
                    'level_1': {'format': '1.', 'left_indent_cm': 0.75, 'hanging_cm': -0.75},
                    'level_2': {'format': '1.1.', 'left_indent_cm': 1.49, 'hanging_cm': -0.75},
                    'level_3': {'format': '1.1.1.', 'left_indent_cm': 2.23, 'hanging_cm': -0.75}
                }
            },
            'geometri_tabel': {
                'batas_kolom_pt': geometry.get('boundary'),
                'x1_maks_kolom_kiri': geometry.get('left_max_x1'),
                'x0_min_kolom_kanan': geometry.get('right_min_x0'),
                'keyakinan': geometry.get('confidence'),
                'metode': geometry.get('metode', 'block'),
                'header_elemen_bbox': geometry.get('header_elemen_bbox'),
                'header_kuk_bbox': geometry.get('header_kuk_bbox'),
                'catatan': geometry.get('catatan', [])
            },
            'validasi': {
                'status': 'perlu_verifikasi',
                'catatan': extraction_notes
            }
        }

        status, validation_notes, peringatan = validate_unit(unit_data)
        unit_data['validasi']['status'] = status
        unit_data['validasi']['catatan'] = validation_notes
        unit_data['validasi']['peringatan_format_sumber'] = peringatan
        unit_data['batasan_variabel']['status_validasi'] = (
            'ok' if not validate_section(unit_data['batasan_variabel'], 'BATASAN VARIABEL')
            else 'perlu_verifikasi')
        unit_data['panduan_penilaian']['status_validasi'] = (
            'ok' if not validate_section(unit_data['panduan_penilaian'], 'PANDUAN PENILAIAN')
            else 'perlu_verifikasi')

        return unit_data

    finally:
        doc.close()


def save_unit_json(unit_data: dict, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(unit_data, f, ensure_ascii=False, indent=2)


def _print_nodes(nodes: list[dict], level: int = 1) -> int:
    count = 0
    for n in nodes:
        indent = '    ' * (level - 1)
        teks = n.get('teks', '')
        potong = teks if len(teks) <= 90 else teks[:87] + '...'
        print(f"{indent}{n.get('nomor')}. {potong}  [hal {n.get('halaman_pdf')}]")
        count += 1
        count += _print_nodes(n.get('items', []), level + 1)
    return count


def print_unit_summary(unit_data: dict) -> None:
    """Cetak ringkasan lengkap unit."""
    print(f"Kode Unit      : {unit_data['kode_unit']}")
    print(f"Judul Unit     : {unit_data['judul_unit']}")
    print(f"Deskripsi      : {(unit_data['deskripsi_unit'] or '')[:100]}...")
    print(f"Jumlah Elemen  : {len(unit_data['elemen_kompetensi'])}")
    total_kuk = sum(len(e['kuk']) for e in unit_data['elemen_kompetensi'])
    print(f"Total KUK      : {total_kuk}")
    print(f"Status Validasi: {unit_data['validasi']['status']}")

    bv = unit_data.get('batasan_variabel', {})
    pp = unit_data.get('panduan_penilaian', {})
    print(f"Batasan Variabel : {'ditemukan' if bv.get('ditemukan') else 'TIDAK ditemukan'} "
          f"(hal {bv.get('halaman_awal')}-{bv.get('halaman_akhir')}), "
          f"{len(flatten_nodes(bv.get('sections', [])))} subbagian")
    print(f"Panduan Penilaian: {'ditemukan' if pp.get('ditemukan') else 'TIDAK ditemukan'} "
          f"(hal {pp.get('halaman_awal')}-{pp.get('halaman_akhir')}), "
          f"{len(flatten_nodes(pp.get('sections', [])))} subbagian")

    if unit_data['validasi']['catatan']:
        print("\nCatatan Validasi:")
        for note in unit_data['validasi']['catatan']:
            print(f"  - {note}")

    print("\nElemen dan KUK:")
    for e in unit_data['elemen_kompetensi']:
        print(f"\n  Elemen {e['nomor_elemen']}: {e['nama_elemen']}")
        for k in e['kuk']:
            u = k['uraian_kuk']
            print(f"    {k['nomor_kuk']} (hal {k['halaman_pdf']}): "
                  f"{u[:85]}{'...' if len(u) > 85 else ''}")

    print("\nBATASAN VARIABEL:")
    _print_nodes(bv.get('sections', []))
    print("\nPANDUAN PENILAIAN:")
    _print_nodes(pp.get('sections', []))


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Penggunaan: python -m app.unit_parser <pdf> [kode] [start] [end]")
        sys.exit(1)

    pdf = sys.argv[1]
    kode = sys.argv[2] if len(sys.argv) > 2 else 'M.73ADV00.001.1'
    s = int(sys.argv[3]) if len(sys.argv) > 3 else 21
    e = int(sys.argv[4]) if len(sys.argv) > 4 else 24

    data = parse_unit(pdf, kode, s, e)
    print_unit_summary(data)

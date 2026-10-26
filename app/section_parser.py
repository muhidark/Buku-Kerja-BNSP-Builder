"""
SKKNI Extractor - Parser Bagian Bernomor (Fase 2B)

Berisi:
- deteksi batas kolom tabel secara dinamis (berbasis header + geometri data)
- ekstraksi bagian bernomor bertingkat (BATASAN VARIABEL, PANDUAN PENILAIAN)
- metadata sumber (halaman, bbox, teks mentah)

Prinsip: tidak mengubah nomor/isi; jika ragu, tandai perlu verifikasi.
"""

import re
from typing import Optional

try:
    import pymupdf as fitz
except ImportError:
    import fitz


HEADING_BATASAN = 'BATASAN VARIABEL'
HEADING_PANDUAN = 'PANDUAN PENILAIAN'
HEADING_ELEMEN = 'ELEMEN KOMPETENSI'
HEADING_KUK = 'KRITERIA UNJUK KERJA'

# Pola nomor bertingkat. Dua bentuk yang dipakai PDF SKKNI:
#   "1. Konteks variabel" / "1."          -> ada titik setelah nomor
#   "1.1 Unit kompetensi ..."             -> tanpa titik, langsung teks
# Angka telanjang ("38") TIDAK dianggap nomor karena itu nomor halaman.
NUMBERING_WITH_DOT = re.compile(r'^(\d+(?:\.\d+)*)\.(?:\s+(.*))?$')
NUMBERING_WITH_TEXT = re.compile(r'^(\d+(?:\.\d+)+)\s+(.+)$')
# Nomor saja di baris sendiri (teks pada baris/block berikutnya)
BARE_NUMBER = re.compile(r'^(\d+(?:\.\d+)*)\.?$')
NUMBERING_LINE = NUMBERING_WITH_DOT


def parse_numbering_line(line: str):
    """Kembalikan (nomor, sisa_teks) bila baris diawali nomor, selain itu None."""
    m = NUMBERING_WITH_DOT.match(line)
    if m:
        return m.group(1), (m.group(2) or '').strip()
    m = NUMBERING_WITH_TEXT.match(line)
    if m:
        return m.group(1), m.group(2).strip()
    return None

# Baris lanjutan kalimat: dimulai huruf kecil atau tanda baca sambungan.
# Tanda "(" sengaja tidak termasuk agar "(Tidak ada.)" menjadi paragraf sendiri.
CONTINUATION_START = re.compile(r'^[a-z\[,;:)\-]')


def extract_blocks(page) -> list[dict]:
    """
    Ekstrak text blocks + lines + bbox dari satu halaman.
    """
    out = []
    for b in page.get_text('dict')['blocks']:
        if b['type'] != 0:
            continue
        lines = []
        for line in b['lines']:
            line_text = ''.join(s['text'] for s in line['spans'])
            if line_text.strip():
                lines.append({
                    'text': line_text,
                    'bbox': list(line['bbox'])
                })
        if not lines:
            continue
        text = '\n'.join(l['text'] for l in lines)
        bbox = list(b['bbox'])
        out.append({
            'text': text.strip(),
            'lines': lines,
            'bbox': bbox,
            'x0': bbox[0], 'y0': bbox[1], 'x1': bbox[2], 'y1': bbox[3]
        })
    return out


def collect_unit_blocks(doc, start_page: int, end_page: int) -> tuple[list[dict], float]:
    """
    Kumpulkan semua block dari rentang halaman unit, dengan page_idx dan tinggi halaman.
    """
    blocks = []
    page_height = 0.0
    for page_idx in range(start_page, end_page + 1):
        page = doc[page_idx]
        page_height = page.rect.height
        for b in extract_blocks(page):
            b['page_idx'] = page_idx
            blocks.append(b)
    return blocks, page_height


def is_footer_or_header_block(block: dict, page_height: float) -> bool:
    """
    Block nomor halaman: isinya hanya 1-3 digit dan berada di area atas/bawah halaman.
    """
    text = block['text'].strip()
    if not re.fullmatch(r'\d{1,3}', text):
        return False
    # Beberapa SKKNI menaruh nomor halaman ~85 pt dari tepi bawah (bukan 45).
    return block['y0'] > page_height - 110 or block['y0'] < 70


def find_heading_block(blocks: list[dict], heading: str) -> Optional[int]:
    """Cari indeks block yang merupakan heading (teks baris pertama == heading)."""
    for i, b in enumerate(blocks):
        first = b['lines'][0]['text'].strip() if b['lines'] else ''
        if first.upper() == heading:
            return i
        if it := b['text'].strip().upper():
            if it == heading:
                return i
    return None


def find_header_lines(blocks: list[dict]) -> tuple[Optional[list[float]], Optional[list[float]]]:
    """
    Cari bbox baris header tabel: 'ELEMEN KOMPETENSI' dan 'KRITERIA UNJUK KERJA'.
    """
    elemen_bbox = None
    kuk_bbox = None
    for b in blocks:
        for line in b['lines']:
            t = line['text'].strip().upper()
            if t == HEADING_ELEMEN and elemen_bbox is None:
                elemen_bbox = list(line['bbox'])
            elif t == HEADING_KUK and kuk_bbox is None:
                kuk_bbox = list(line['bbox'])
        if elemen_bbox and kuk_bbox:
            break
    return elemen_bbox, kuk_bbox


def detect_column_geometry(table_blocks: list[dict],
                           elemen_header_bbox: Optional[list[float]],
                           kuk_header_bbox: Optional[list[float]]) -> dict:
    """
    Deteksi batas kolom Elemen vs KUK secara dinamis.

    Pendekatan:
    1. Ambil x0 semua block isi tabel.
    2. Cari celah terbesar pada nilai x0 (dua kolom terpisah rapat).
    3. Batas = titik tengah antara x1 maksimum kolom kiri dan x0 minimum kolom kanan.
    4. Validasi terhadap koordinat header: batas harus di antara x1 header ELEMEN
       dan x1 header KUK, serta di kanan x1 header ELEMEN.

    Returns:
        dict: boundary, left_x1, right_x0, confidence, catatan
    """
    notes = []
    result = {
        'boundary': None,
        'left_max_x1': None,
        'right_min_x0': None,
        'confidence': 'low',
        'catatan': notes,
        'header_elemen_bbox': elemen_header_bbox,
        'header_kuk_bbox': kuk_header_bbox
    }

    xs = sorted({round(b['x0'], 1) for b in table_blocks})
    if len(xs) < 2:
        notes.append('Block tabel terlalu sedikit untuk mendeteksi dua kolom')
        return result

    # Cari celah terbesar antar nilai x0 berurutan
    best_gap = 0.0
    best_i = None
    for i in range(len(xs) - 1):
        gap = xs[i + 1] - xs[i]
        if gap > best_gap:
            best_gap = gap
            best_i = i

    if best_i is None or best_gap < 8.0:
        notes.append(f'Celah antar kolom tidak jelas (celah terbesar {best_gap:.1f} pt)')
        return result

    left_max = xs[best_i]
    right_min = xs[best_i + 1]

    # x1 maksimum di kolom kiri
    # Blok yang menyeberangi dua kolom tidak dipakai untuk mengukur tepi kiri,
    # karena x1-nya mencapai kolom kanan dan membuat batas meleset.
    left_blocks = [b for b in table_blocks
                   if round(b['x0'], 1) <= left_max and b['x1'] < right_min]
    right_blocks = [b for b in table_blocks if round(b['x0'], 1) >= right_min]
    left_max_x1 = max((b['x1'] for b in left_blocks), default=None)

    boundary = None
    if left_max_x1 is not None:
        boundary = (left_max_x1 + right_min) / 2.0
        # Jangan sampai melewati x0 kolom kanan
        boundary = min(boundary, right_min - 0.5)
    else:
        boundary = (left_max + right_min) / 2.0

    result['boundary'] = round(boundary, 2)
    result['left_max_x1'] = round(left_max_x1, 2) if left_max_x1 is not None else None
    result['right_min_x0'] = round(right_min, 2)

    # Validasi terhadap header
    if elemen_header_bbox and kuk_header_bbox:
        h_elemen_x1 = elemen_header_bbox[2]
        h_kuk_x0 = kuk_header_bbox[0]
        h_kuk_x1 = kuk_header_bbox[2]

        if boundary <= h_elemen_x1:
            notes.append(
                f'Batas kolom ({boundary:.1f}) tidak melewati tepi kanan header ELEMEN ({h_elemen_x1:.1f})')
        if boundary >= h_kuk_x1:
            notes.append(
                f'Batas kolom ({boundary:.1f}) melampaui tepi kanan header KUK ({h_kuk_x1:.1f})')
        if h_elemen_x1 < boundary < h_kuk_x0:
            result['confidence'] = 'high'
        elif boundary < h_kuk_x1:
            result['confidence'] = 'medium'
    else:
        notes.append('Header tabel tidak lengkap; batas kolom hanya dari geometri data')

    # Verifikasi: kolom kanan harus didominasi block yang diawali nomor KUK (X.Y)
    kuk_like = sum(1 for b in right_blocks
                   if parse_numbering_line(b['lines'][0]['text'].strip()))
    if right_blocks and kuk_like / len(right_blocks) < 0.5:
        notes.append('Banyak block kolom kanan tidak diawali nomor; periksa batas kolom')
        if result['confidence'] == 'high':
            result['confidence'] = 'medium'

    return result


def normalize_text(text: str) -> str:
    """Normalisasi spasi untuk perbandingan/penyimpanan teks gabungan."""
    return re.sub(r'\s+', ' ', text).strip()


def parse_numbered_outline(blocks: list[dict], page_height: float,
                           stop_headings: tuple[str, ...] = ()) -> tuple[list[dict], list[str]]:
    """
    Parse block menjadi pohon bagian bernomor bertingkat dengan metadata penomoran.

    Aturan:
    - Baris berawalan nomor ("1.", "1.1", "1.2.1") memulai node bernomor baru.
      Nomor disimpan terpisah dari teks (tidak digabung permanen).
    - Baris lanjutan (huruf kecil / tanda baca) digabung ke teks node aktif.
    - Baris tanpa nomor yang berdiri sendiri (mis. "(Tidak ada.)") menjadi
      paragraf biasa: is_numbered=False, dengan parent_nomor dan level posisinya.
    - Nomor tidak diubah, tidak dibuat ulang, tidak diurutkan ulang.
    - Block nomor halaman dibuang.

    Returns:
        (nodes, notes) dengan nodes berupa list node depth-1 (rekursif via "items").
    """
    notes = []
    roots = []
    stack = []      # [(level, node)] hanya node bernomor
    current = None  # node penerima baris lanjutan
    current_x0 = None  # x0 blok asal node aktif (untuk deteksi teks judul)
    pending_nomor = None  # nomor yang menunggu teks pada baris berikutnya
    pending_baris = ''    # baris mentah nomor tersebut


    for block in blocks:
        if is_footer_or_header_block(block, page_height):
            continue

        for baris_ke, line in enumerate([l['text'] for l in block['lines']]):
            line = line.strip()
            if not line:
                continue

            def buat_node(nomor: str, sisa: str, baris: list[str]):
                level = len(nomor.split('.'))
                while stack and stack[-1][0] >= level:
                    stack.pop()
                parent = stack[-1][1] if stack else None
                if parent is None and level != 1:
                    notes.append(f'Nomor {nomor} (level {level}) muncul tanpa induk')
                if parent is not None and level != parent['level'] + 1:
                    notes.append(
                        f'Lompatan level: {nomor} (level {level}) '
                        f'di bawah {parent["nomor"]} (level {parent["level"]})')
                node = {
                    'nomor': nomor,
                    'level': level,
                    'parent_nomor': parent['nomor'] if parent else None,
                    'is_numbered': True,
                    'judul': sisa,
                    'teks': sisa,
                    'halaman_pdf': block['page_idx'],
                    'halaman_akhir': block['page_idx'],
                    'bbox': block['bbox'],
                    'teks_mentah': list(baris),
                    'items': []
                }
                (parent['items'] if parent else roots).append(node)
                stack.append((level, node))
                return node

            # Nomor berdiri sendiri: teks menyusul pada baris berikutnya
            bare = BARE_NUMBER.match(line)
            if bare and not pending_nomor:
                pending_nomor = bare.group(1)
                pending_baris = line
                continue

            parsed = parse_numbering_line(line)

            if parsed is not None:
                nomor, sisa = parsed
                current = buat_node(nomor, sisa, [line])
                current_x0 = block['x0']

            elif pending_nomor:
                nomor, pending_nomor = pending_nomor, None
                current = buat_node(nomor, line, [pending_baris, line])
                current_x0 = block['x0']

            else:
                parent = stack[-1][1] if stack else None

                # (a) Teks judul pada baris terpisah setelah nomor ("1." lalu "Konteks variabel")
                if (current is not None and not current['judul']
                        and current_x0 is not None
                        and abs(block['x0'] - current_x0) < 3.0):
                    current['judul'] = line
                    current['teks'] = line
                    current['teks_mentah'].append(line)
                    current['halaman_akhir'] = block['page_idx']

                # (a2) Baris masih dalam block yang sama: satu block PDF adalah
                # satu unit teks, jadi baris-barisnya adalah lanjutan paragraf
                # (PyMuPDF kadang memecah kalimat menjadi banyak baris pendek).
                elif baris_ke > 0 and current is not None:
                    current['teks'] = (current['teks'] + ' ' + line).strip()
                    current['teks_mentah'].append(line)
                    current['halaman_akhir'] = block['page_idx']

                # (b3) Baris lanjutan berhuruf besar pada subbutir (level >= 2)
                # yang lebih menjorok, mis. nama dokumen/judul undang-undang.
                # Tidak bergantung pada huruf kecil; tidak menggabungkan
                # "(Tidak ada.)" dan tidak mengganggu heading level 1.
                elif (current is not None
                      and line != '(Tidak ada.)'
                      and current.get('level', 1) >= 2
                      and not re.search(r'[.!?:;)]$', current['teks'])
                      and current_x0 is not None
                      and block['x0'] > current_x0 + 5):
                    current['teks'] = (current['teks'] + ' ' + line).strip()
                    current['teks_mentah'].append(line)
                    current['halaman_akhir'] = block['page_idx']

                # (b) Baris lanjutan kalimat (diawali huruf kecil / tanda baca)
                elif current is not None and CONTINUATION_START.match(line):
                    current['teks'] = (current['teks'] + ' ' + line).strip()
                    current['teks_mentah'].append(line)
                    current['halaman_akhir'] = block['page_idx']

                # (b5) Lanjutan paragraf tanpa nomor yang kalimatnya belum
                # selesai (mis. terpotong antar halaman: "(KUK) dan ...").
                elif (current is not None
                      and not current.get('is_numbered', True)
                      and line != '(Tidak ada.)'
                      and not re.search(r'[.!?:;)]$', current['teks'])
                      and (line.startswith('(') or CONTINUATION_START.match(line))):
                    current['teks'] = (current['teks'] + ' ' + line).strip()
                    current['teks_mentah'].append(line)
                    current['halaman_akhir'] = block['page_idx']

                # (c) Paragraf tanpa nomor (mis. "(Tidak ada.)")
                else:
                    level = parent['level'] + 1 if parent else 1
                    node = {
                        'nomor': None,
                        'level': level,
                        'parent_nomor': parent['nomor'] if parent else None,
                        'is_numbered': False,
                        'judul': line,
                        'teks': line,
                        'halaman_pdf': block['page_idx'],
                        'halaman_akhir': block['page_idx'],
                        'bbox': block['bbox'],
                        'teks_mentah': [line],
                        'items': []
                    }
                    (parent['items'] if parent else roots).append(node)
                    current = node
                    current_x0 = block['x0']

    # Nomor tanpa teks sampai akhir bagian: tetap disimpan, ditandai
    if pending_nomor:
        nomor = pending_nomor
        level = len(nomor.split('.'))
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else None
        node = {
            'nomor': nomor,
            'level': level,
            'parent_nomor': parent['nomor'] if parent else None,
            'is_numbered': True,
            'judul': '',
            'teks': '',
            'halaman_pdf': parent['halaman_pdf'] if parent else None,
            'halaman_akhir': parent['halaman_akhir'] if parent else None,
            'bbox': parent['bbox'] if parent else None,
            'teks_mentah': nomor,
            'items': []
        }
        (parent['items'] if parent else roots).append(node)
        notes.append(f'Nomor {nomor} tidak memiliki teks')

    def rapikan(nodes):
        for n in nodes:
            n['teks'] = normalize_text(n['teks'])
            n['judul'] = normalize_text(n.get('judul', ''))
            n['teks_mentah'] = '\n'.join(n['teks_mentah'])
            rapikan(n.get('items', []))
            if not n.get('items'):
                n['judul'] = n['teks']
            elif not n.get('judul'):
                n['judul'] = n['teks']

    rapikan(roots)

    return roots, notes


def flatten_nodes(nodes: list[dict]) -> list[dict]:
    """Ratak bagian pohon menjadi list node (untuk validasi)."""
    out = []
    for n in nodes:
        out.append(n)
        out.extend(flatten_nodes(n.get('items', [])))
    return out


def ringkas_penomoran(sections: list[dict], grup: str) -> dict:
    """
    Ringkasan penomoran satu kelompok (BATASAN VARIABEL / PANDUAN PENILAIAN).

    Setiap kelompok berdiri sendiri dan dimulai dari nomor 1, sehingga dapat
    dipetakan ke Word Multilevel Numbering dengan restart per unit.
    """
    flat = flatten_nodes(sections)
    bernomor = [n for n in flat if n.get('is_numbered')]
    tanpa_nomor = [n for n in flat if not n.get('is_numbered')]
    level_maks = max((n.get('level', 1) for n in flat), default=0)

    akar = [n['nomor'] for n in sections if n.get('is_numbered')]

    return {
        'grup': grup,
        'mulai_dari': 1,
        'jumlah_level_maks': level_maks,
        'jumlah_node_bernomor': len(bernomor),
        'jumlah_paragraf_tanpa_nomor': len(tanpa_nomor),
        'level_melebihi_tiga': sorted({n['level'] for n in flat if n.get('level', 0) > 3}),
        'nomor_akar': akar,
        'mulai_dari_satu': bool(akar) and akar[0] == '1',
        'restart_per_unit': True,
    }


def extract_section(blocks: list[dict], heading: str, stop_headings: tuple[str, ...],
                    page_height: float, grup: str = '') -> dict:
    """
    Ekstrak satu bagian bernomor berdasarkan heading.

    Returns:
        dict: ditemukan, halaman_awal, halaman_akhir, sections, notes, teks_mentah, penomoran
    """
    notes = []
    idx = find_heading_block(blocks, heading)

    if idx is None:
        return {
            'ditemukan': False,
            'halaman_awal': None,
            'halaman_akhir': None,
            'sections': [],
            'notes': [f'Heading "{heading}" tidak ditemukan'],
            'teks_mentah': '',
            'penomoran': ringkas_penomoran([], grup)
        }

    heading_block = blocks[idx]
    hpos = (heading_block['page_idx'], heading_block['y0'])

    # Batas akhir ditentukan POSISI (bukan urutan daftar), karena sebagian PDF
    # menaruh blok tabel setelah blok bagian dalam urutan PyMuPDF.
    stop_pos = None
    for b in blocks:
        first = b['lines'][0]['text'].strip().upper() if b['lines'] else ''
        pos = (b['page_idx'], b['y0'])
        if first in stop_headings and pos > hpos:
            if stop_pos is None or pos < stop_pos:
                stop_pos = pos

    body_blocks = []
    for b in blocks:
        pos = (b['page_idx'], b['y0'])
        if pos <= hpos:
            continue
        if stop_pos is not None and pos >= stop_pos:
            continue
        body_blocks.append(b)

    # Urutkan sesuai posisi visual (atas -> bawah, halaman demi halaman)
    body_blocks.sort(key=lambda b: (b['page_idx'], b['y0']))

    # Buang block nomor halaman
    body_blocks = [b for b in body_blocks
                   if not is_footer_or_header_block(b, page_height)]

    sections, outline_notes = parse_numbered_outline(body_blocks, page_height)
    notes.extend(outline_notes)

    pages = [b['page_idx'] for b in body_blocks]

    return {
        'ditemukan': True,
        'halaman_awal': heading_block['page_idx'],
        'halaman_akhir': max(pages) if pages else heading_block['page_idx'],
        'sections': sections,
        'notes': notes,
        'teks_mentah': '\n'.join(b['text'] for b in body_blocks),
        'penomoran': ringkas_penomoran(sections, grup),
        'bbox_heading': heading_block['bbox']
    }


def validate_section(section: dict, nama: str) -> list[str]:
    """
    Validasi struktur dan penomoran satu bagian.

    Pemeriksaan:
    - heading ditemukan dan isi tidak kosong
    - field wajib ada pada setiap node (nomor, level, parent_nomor, is_numbered,
      teks, halaman_pdf)
    - level konsisten dengan jumlah segmen nomor
    - level anak = level induk + 1 dan parent_nomor menunjuk induk yang benar
    - urutan nomor anak berurutan mulai 1 (tidak berurutan -> ditandai)
    - nomor tidak duplikat pada induk yang sama
    - kelompok dimulai dari nomor 1
    - level penomoran di atas 3 dilaporkan (untuk penentuan format Word)
    """
    notes = []

    if not section.get('ditemukan'):
        notes.append(f'{nama}: heading tidak ditemukan')
        return notes

    if not section.get('sections'):
        notes.append(f'{nama}: tidak ada bagian bernomor yang terbaca')
        return notes

    flat = flatten_nodes(section['sections'])
    wajib = ('nomor', 'level', 'parent_nomor', 'is_numbered', 'teks', 'halaman_pdf')

    # Field wajib
    for n in flat:
        for f in wajib:
            if f not in n:
                notes.append(f'{nama}: node nomor {n.get("nomor") or "(tanpa nomor)"} '
                             f'tidak memiliki field {f}')

    # Halaman
    tanpa_halaman = [n for n in flat if n.get('halaman_pdf') is None]
    if tanpa_halaman:
        notes.append(f'{nama}: {len(tanpa_halaman)} bagian tanpa referensi halaman')

    # Level vs jumlah segmen nomor
    for n in flat:
        if not n.get('is_numbered'):
            if not (n.get('teks') or '').strip():
                notes.append(f'{nama}: paragraf tanpa nomor kosong di halaman {n.get("halaman_pdf")}')
            continue
        segmen = len(str(n['nomor']).split('.'))
        if n.get('level') != segmen:
            notes.append(f'{nama}: level {n.get("level")} tidak sesuai nomor {n["nomor"]} '
                         f'({segmen} segmen)')

    # Konsistensi induk + urutan nomor
    def periksa_induk(nodes, induk, label):
        nomor_anak = []
        seen = set()
        for n in nodes:
            if not n.get('is_numbered'):
                continue
            nomor = n['nomor']
            if nomor in seen:
                notes.append(f'{nama}: nomor {nomor} duplikat di bawah {label}')
            seen.add(nomor)

            if induk is None:
                if n.get('parent_nomor') is not None:
                    notes.append(f'{nama}: nomor {nomor} di akar tetapi parent_nomor '
                                 f'{n.get("parent_nomor")}')
            else:
                if n.get('parent_nomor') != induk['nomor']:
                    notes.append(f'{nama}: parent_nomor {n.get("parent_nomor")} pada {nomor} '
                                 f'tidak sama dengan induk {induk["nomor"]}')
                if n.get('level') != induk.get('level', 0) + 1:
                    notes.append(f'{nama}: level {n.get("level")} pada {nomor} bukan '
                                 f'{induk.get("level", 0) + 1} (anak {induk["nomor"]})')

            nomor_anak.append(nomor)
            periksa_induk(n.get('items', []), n, nomor)

        # Urutan: 1..n untuk akar, induk.1..induk.n untuk anak
        if nomor_anak:
            prefix = '' if induk is None else induk['nomor'] + '.'
            harapan = [f'{prefix}{i}' for i in range(1, len(nomor_anak) + 1)]
            if nomor_anak != harapan:
                notes.append(f'{nama}: penomoran tidak berurutan di bawah {label}: '
                             f'{nomor_anak} (diharapkan {harapan})')

    periksa_induk(section['sections'], None, 'root')

    # Mulai dari 1
    akar = [n['nomor'] for n in section['sections'] if n.get('is_numbered')]
    if akar and akar[0] != '1':
        notes.append(f'{nama}: kelompok tidak dimulai dari nomor 1 (mulai {akar[0]})')

    # Level > 3 dilaporkan untuk penentuan format
    level_besar = sorted({n['level'] for n in flat if n.get('level', 0) > 3})
    if level_besar:
        notes.append(f'{nama}: terdapat level penomoran di atas 3 (level {level_besar}); '
                     f'perlu penentuan format Word Multilevel Numbering')

    return notes

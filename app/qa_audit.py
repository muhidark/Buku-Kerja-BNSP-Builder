"""
SKKNI Extractor - Audit QA independen (Fase 4F).

Memeriksa tiga lapis:
1. PDF -> JSON : isi PDF sumber vs JSON hasil ekstraksi (dua arah).
2. JSON -> DOCX: isi JSON vs dokumen Word (dua arah) + struktur OOXML.
3. DOCX render : nomor yang benar-benar tampil pada PDF hasil LibreOffice.

Metode pembacaan PDF di sini memakai `page.get_text("words")` yang dikelompokkan
per baris, berbeda dari parser utama yang memakai `get_text("blocks"/"dict")`.
Keduanya tetap memakai PyMuPDF, sehingga PDF hasil pindai tanpa lapisan teks
tidak dapat diaudit oleh keduanya.
"""

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

import pymupdf as fitz
from docx import Document
from docx.oxml.ns import qn

from app import jobs, library, schema_library
from app.kuk_completeness_validator import muat_kuk_json, periksa_unit
from app.section_parser import flatten_nodes

ROOT = Path(__file__).resolve().parent.parent
QA_DIR = ROOT / 'output' / 'qa'
RENDER_DIR = QA_DIR / 'render'

SKEMA_UJI = 'SOCIAL MEDIA MARKETING'

# Baris PDF yang bukan isi unit (label/header/footer) dan tidak perlu dicocokkan.
ABAIKAN = re.compile(
    r'^(kode unit|judul unit|deskripsi unit|elemen kompetensi|kriteria unjuk kerja|'
    r'batasan variabel|panduan penilaian|halaman|daftar isi|no\.?$|\d+$)', re.I)

INDEKS = re.compile(r'^\s*(\d+(?:\.\d+)*)\.?\s')


# --------------------------------------------------------------------------
# Utilitas
# --------------------------------------------------------------------------

def _rapat(s: str) -> str:
    """Normalisasi untuk perbandingan: hanya spasi/baris, tanda baca dipertahankan."""
    return re.sub(r'\s+', '', s or '')


def _baris_pdf(path: Path, mulai: int, akhir: int) -> list[dict]:
    """Baris teks per halaman memakai alur kata (bukan blok)."""
    hasil = []
    with fitz.open(str(path)) as doc:
        for p in range(max(0, mulai), min(akhir, doc.page_count - 1) + 1):
            halaman = doc[p]
            baris: dict[tuple[int, int], list[str]] = {}
            for w in halaman.get_text('words'):
                kunci = (w[5], w[6])
                baris.setdefault(kunci, []).append((w[0], w[4]))
            for kunci in sorted(baris):
                teks = ' '.join(t for _, t in sorted(baris[kunci]))
                if teks.strip():
                    hasil.append({'halaman': p + 1, 'teks': teks.strip()})
    return hasil


def _teks_semantik(data: dict) -> str:
    """Teks JSON yang relevan saja.

    `penomoran` dan `geometri_tabel` menyimpan salinan nomor/teks untuk
    keperluan generator; bila ikut dibandingkan, teks yang dihapus dari bagian
    semantik tetap terlihat "ada" di JSON.
    """
    bagian = [data.get('kode_unit') or '', data.get('judul_unit') or '',
              data.get('deskripsi_unit') or '']
    for e in data.get('elemen_kompetensi') or []:
        bagian.append(str(e.get('nomor_elemen') or ''))
        bagian.append(e.get('nama_elemen') or '')
        for k in e.get('kuk') or []:
            bagian.append(str(k.get('nomor_kuk') or ''))
            bagian.append(k.get('uraian_kuk') or '')
    for nama in ('batasan_variabel', 'panduan_penilaian'):
        for n in flatten_nodes((data.get(nama) or {}).get('sections') or []):
            bagian.append(str(n.get('nomor') or ''))
            bagian.append(n.get('teks') or '')
    return _rapat(' '.join(bagian))


def _kuk_json(data: dict) -> list[str]:
    return [k['nomor_kuk'] for e in data.get('elemen_kompetensi') or []
            for k in e.get('kuk') or [] if k.get('nomor_kuk')]


def _temuan(kode, tahap, jenis, keparahan, pesan, **extra) -> dict:
    return {'kode_unit': kode, 'tahap': tahap, 'jenis': jenis,
            'keparahan': keparahan, 'pesan': pesan, **extra}


# --------------------------------------------------------------------------
# 1. Audit PDF -> JSON
# --------------------------------------------------------------------------

def audit_pdf_json(kode: str, pdf: Path, mulai: int, akhir: int, data: dict) -> dict:
    temuan = []
    baris = _baris_pdf(pdf, mulai, akhir)
    teks_pdf = _rapat(' '.join(b['teks'] for b in baris))
    teks_json = _teks_semantik(data)

    # --- identitas
    if data.get('kode_unit') != kode:
        temuan.append(_temuan(kode, 'pdf_json', 'kode_berbeda', 'Critical',
                              f"JSON memuat kode {data.get('kode_unit')}"))
    if not data.get('judul_unit') or _rapat(data['judul_unit'])[:30] not in teks_pdf:
        temuan.append(_temuan(kode, 'pdf_json', 'judul', 'Critical',
                              'Judul unit tidak ditemukan pada PDF'))
    desk = data.get('deskripsi_unit') or ''
    if not desk or _rapat(desk)[:40] not in teks_pdf:
        temuan.append(_temuan(kode, 'pdf_json', 'deskripsi', 'Critical',
                              'Deskripsi unit tidak ditemukan pada PDF'))

    # --- elemen: baca dari tabel PDF (jalur independen), bandingkan dengan JSON
    elemen_pdf = []
    with fitz.open(str(pdf)) as doc:
        for p in range(max(0, mulai), min(akhir, doc.page_count - 1) + 1):
            halaman = doc[p]
            if 'ELEMEN KOMPETENSI' not in halaman.get_text().upper():
                continue
            for t in halaman.find_tables().tables:
                for baris_t in t.extract():
                    if not baris_t or len(baris_t) < 2:
                        continue
                    sel = (baris_t[0] or '').strip()
                    if 'ELEMEN' in sel.upper():
                        continue
                    m = re.match(r'^(\d{1,2})\s*\.?\s*\n?\.??', sel)
                    if m:
                        n = int(m.group(1))
                        if 1 <= n <= 20:
                            elemen_pdf.append(n)
    elemen_json = [int(re.sub(r'\D', '', str(e.get('nomor_elemen'))))
                   for e in data.get('elemen_kompetensi') or [] if e.get('nomor_elemen')]
    if sorted(set(elemen_pdf)) != sorted(set(elemen_json)):
        temuan.append(_temuan(kode, 'pdf_json', 'jumlah_elemen', 'Critical',
                              f'Elemen PDF {sorted(set(elemen_pdf))} vs JSON {sorted(set(elemen_json))}'))

    # --- KUK: nomor independen + duplikat sisi JSON
    nomor_json = _kuk_json(data)
    if len(nomor_json) != len(set(nomor_json)):
        dup = sorted({n for n in nomor_json if nomor_json.count(n) > 1})
        temuan.append(_temuan(kode, 'pdf_json', 'kuk_duplikat_json', 'Critical',
                              'Nomor KUK duplikat pada JSON: ' + ', '.join(dup)))
    if nomor_json:
        cek = periksa_unit(pdf, kode, mulai, akhir, nomor_json)
        for n in cek['kuk_hilang']:
            temuan.append(_temuan(kode, 'pdf_json', 'kuk_hilang', 'Critical',
                                  f'KUK {n} ada di PDF tetapi tidak di JSON'))
        for n in cek['kuk_ekstra']:
            temuan.append(_temuan(kode, 'pdf_json', 'kuk_tanpa_bukti', 'Major',
                                  f'KUK {n} ada di JSON tetapi tidak terbaca di PDF'))
        for n in cek['duplikat']:
            temuan.append(_temuan(kode, 'pdf_json', 'kuk_duplikat_pdf', 'Major',
                                  f'KUK {n} muncul lebih dari sekali pada PDF'))
        for h in cek['halaman_tanpa_bukti']:
            temuan.append(_temuan(kode, 'pdf_json', 'tabel_tidak_terbaca', 'Major',
                                  f'Halaman {h} tidak dapat dibaca dengan yakin',
                                  halaman=h))
    else:
        temuan.append(_temuan(kode, 'pdf_json', 'kuk_kosong', 'Critical',
                              'JSON tidak memiliki nomor KUK'))

    # --- isi JSON harus ada di PDF (JSON -> PDF)
    potongan = [('deskripsi', desk)]
    for e in data.get('elemen_kompetensi') or []:
        potongan.append((f"elemen {e.get('nomor_elemen')}", e.get('nama_elemen') or ''))
        for k in e.get('kuk') or []:
            potongan.append((f"KUK {k.get('nomor_kuk')}", k.get('uraian_kuk') or ''))
    for nama_bagian in ('batasan_variabel', 'panduan_penilaian'):
        for n in flatten_nodes((data.get(nama_bagian) or {}).get('sections') or []):
            potongan.append((f"{nama_bagian} {n['nomor']}", n['teks']))

    for label, teks in potongan:
        # Uraian KUK yang dipotong harus tetap terdeteksi walau pendek.
        batas = 10 if label.startswith('KUK') else 25
        if len(teks) < batas:
            continue
        if _rapat(teks)[:60] not in teks_pdf:
            sev = 'Critical' if label.startswith('KUK') else 'Major'
            temuan.append(_temuan(kode, 'pdf_json', 'teks_tidak_ada_di_pdf', sev,
                                  f'Isi JSON tidak ditemukan pada PDF: {label}',
                                  teks_json=teks[:160]))

    # --- teks PDF yang tidak masuk JSON (PDF -> JSON)
    sudah_dilapor = set()
    for b in baris:
        t = b['teks']
        if ABAIKAN.match(t):
            continue
        # Baris lanjutan label (": Judul ...") dibersihkan dulu dari tanda label.
        bersih = re.sub(r'^[:\-\u2013\.\s]+', '', t)
        # Nomor di awal baris dibandingkan terpisah dari uraiannya.
        tanpa_nomor = re.sub(r'^\d+(?:\.\d+)*\.?\s*', '', bersih)
        if len(tanpa_nomor) < 40:
            continue
        if _rapat(tanpa_nomor)[:50] not in teks_json:
            sudah_dilapor.add(_rapat(tanpa_nomor)[:50])
            temuan.append(_temuan(kode, 'pdf_json', 'teks_pdf_tidak_masuk_json', 'Major',
                                  'Baris PDF tidak ditemukan pada JSON',
                                  halaman=b['halaman'], teks_pdf=bersih[:200]))

    # Pemeriksaan tingkat kalimat: menangkap teks PDF yang hilang walau
    # barisnya terpecah atau lebih pendek dari ambang baris.
    for b in baris:
        for s in re.split(r'(?<=[.!?])\s+', b['teks']):
            bersih = re.sub(r'^[:\-\u2013\.\s]+', '', s).strip()
            bersih = re.sub(r'^\d+(?:\.\d+)*\.?\s*', '', bersih)
            if len(bersih) < 55 or ABAIKAN.match(bersih):
                continue
            kunci = _rapat(bersih)[:50]
            if kunci in sudah_dilapor:
                continue
            if kunci not in teks_json:
                sudah_dilapor.add(kunci)
                temuan.append(_temuan(kode, 'pdf_json', 'kalimat_pdf_tidak_masuk_json',
                                      'Major', 'Kalimat PDF tidak ditemukan pada JSON',
                                      halaman=b['halaman'], teks_pdf=bersih[:200]))

    # --- Batasan Variabel harus berada sebelum Panduan Penilaian
    teks_urut = ' '.join(b['teks'] for b in baris)
    i_bv = teks_urut.upper().find('BATASAN VARIABEL')
    i_pp = teks_urut.upper().find('PANDUAN PENILAIAN')
    if i_bv == -1:
        temuan.append(_temuan(kode, 'pdf_json', 'bv_hilang', 'Critical',
                              'Heading Batasan Variabel tidak ditemukan pada PDF'))
    if i_pp == -1:
        temuan.append(_temuan(kode, 'pdf_json', 'pp_hilang', 'Critical',
                              'Heading Panduan Penilaian tidak ditemukan pada PDF'))
    if i_bv != -1 and i_pp != -1 and i_bv > i_pp:
        temuan.append(_temuan(kode, 'pdf_json', 'urutan_bagian', 'Major',
                              'Batasan Variabel muncul setelah Panduan Penilaian'))

    # Setiap paragraf harus berada pada bagian yang benar (BV sebelum PP).
    if i_bv != -1 and i_pp != -1 and i_bv < i_pp:
        seg_bv = _rapat(teks_urut[i_bv:i_pp])
        seg_pp = _rapat(teks_urut[i_pp:])
        for bagian, posisi, segmen in (('batasan_variabel', 'bv_salah_bagian', seg_bv),
                                       ('panduan_penilaian', 'pp_salah_bagian', seg_pp)):
            for n in flatten_nodes((data.get(bagian) or {}).get('sections') or []):
                teks = n.get('teks') or ''
                if len(teks) < 12:
                    continue
                kunci = _rapat(teks)[:40]
                if kunci in segmen:
                    continue
                # Teks pendek yang muncul di kedua bagian (mis. "(Tidak ada.)")
                # tidak dapat dipastikan posisinya.
                bagian_lain = seg_pp if bagian == 'batasan_variabel' else seg_bv
                if kunci in bagian_lain:
                    temuan.append(_temuan(kode, 'pdf_json', posisi, 'Major',
                                          f"Paragraf {bagian} {n.get('nomor')} berada di bagian "
                                          'lain pada PDF'))
                elif kunci not in _rapat(teks_pdf):
                    continue   # sudah dilaporkan sebagai teks tidak ditemukan

    return {
        'kode_unit': kode,
        'pdf': pdf.name,
        'halaman_pdf_0based': [mulai, akhir],
        'elemen_pdf': sorted(set(elemen_pdf)),
        'kuk_pdf': sorted(set(_kuk_json(data))) if not nomor_json else
                   sorted(set(periksa_unit(pdf, kode, mulai, akhir, nomor_json)['kuk_pdf'])),
        'kuk_json': nomor_json,
        'jumlah_elemen': len(elemen_json),
        'jumlah_kuk': len(nomor_json),
        'temuan': temuan,
    }


# --------------------------------------------------------------------------
# 2. Audit JSON -> DOCX
# --------------------------------------------------------------------------

def audit_docx(meta: dict) -> dict:
    from app.services import document_service as ds

    temuan = []
    path = ds.jalur_docx(meta)
    doc = Document(str(path))

    kode_doc = [p.text.split(':', 1)[1].strip() for p in doc.paragraphs
                if p.text.strip().startswith('KODE UNIT:')]
    urutan_json = [u['kode_unit'] for u in meta['units']]
    if kode_doc != urutan_json:
        temuan.append(_temuan('-', 'json_docx', 'urutan_unit', 'Critical',
                              f'Urutan DOCX {kode_doc} != JSON {urutan_json}'))

    if len(doc.tables) != len(urutan_json):
        temuan.append(_temuan('-', 'json_docx', 'jumlah_tabel', 'Critical',
                              f'{len(doc.tables)} tabel untuk {len(urutan_json)} unit'))

    teks_doc = ' '.join(p.text for p in doc.paragraphs)
    for t in doc.tables:
        for r in t.rows:
            for c in r.cells:
                teks_doc += ' ' + ' '.join(p.text for p in c.paragraphs)
    rapat_doc = _rapat(teks_doc)

    total_teks = cocok_teks = 0
    kuk_docx_peta = {}
    for u, tabel in zip(meta['units'], doc.tables):
        kode = u['kode_unit']
        data = json.loads((ROOT / u['json']).read_text(encoding='utf-8'))

        kuk_json = _kuk_json(data)
        kuk_docx = []
        for r in tabel.rows[1:]:
            kuk_docx.extend(p.text.split('\t', 1)[0].strip() for p in r.cells[1].paragraphs)
        kuk_docx_peta[u['kode_unit']] = len(kuk_docx)
        if kuk_docx != kuk_json:
            temuan.append(_temuan(kode, 'json_docx', 'kuk_berbeda', 'Critical',
                                  'Nomor KUK DOCX tidak sama dengan JSON',
                                  teks_json=str(kuk_json), teks_pdf=str(kuk_docx)))

        if len(tabel.columns) != 2:
            temuan.append(_temuan(kode, 'json_docx', 'kolom_tabel', 'Major',
                                  f'Tabel {len(tabel.columns)} kolom'))

        # KUK harus berada pada baris elemen yang benar
        for r, e in zip(tabel.rows[1:], data['elemen_kompetensi']):
            nomor_sel = [p.text.split('\t', 1)[0].strip() for p in r.cells[1].paragraphs]
            if nomor_sel != [k['nomor_kuk'] for k in e['kuk']]:
                temuan.append(_temuan(kode, 'json_docx', 'kuk_elemen', 'Critical',
                                      f"KUK elemen {e['nomor_elemen']} tidak cocok"))

        # cakupan teks dua arah
        potongan = [data.get('deskripsi_unit') or '']
        for e in data['elemen_kompetensi']:
            potongan.append(e.get('nama_elemen') or '')
            potongan.extend(k.get('uraian_kuk') or '' for k in e['kuk'])
        for bagian in ('batasan_variabel', 'panduan_penilaian'):
            potongan.extend(n['teks'] for n in flatten_nodes((data.get(bagian) or {}).get('sections') or []))

        for teks in potongan:
            if len(teks) < 25:
                continue
            total_teks += 1
            if _rapat(teks)[:60] in rapat_doc:
                cocok_teks += 1
            else:
                temuan.append(_temuan(kode, 'json_docx', 'teks_hilang_docx', 'Major',
                                      'Teks JSON tidak ditemukan pada DOCX',
                                      teks_json=teks[:160]))

    # --- OOXML: numbering & indentasi (nilai pada paragraf, bukan template bawaan)
    num_ids, ilvl_indent = set(), {}
    for p in doc.paragraphs:
        pPr = p._p.pPr
        if pPr is None:
            continue
        numPr = pPr.find(qn('w:numPr'))
        if numPr is None:
            continue
        num_ids.add(int(numPr.find(qn('w:numId')).get(qn('w:val'))))
        ind = pPr.find(qn('w:ind'))
        if ind is None:
            continue
        ilvl = int(numPr.find(qn('w:ilvl')).get(qn('w:val')))
        ilvl_indent.setdefault(ilvl, (ind.get(qn('w:left')), ind.get(qn('w:hanging'))))

    harapan_numid = 2 * len(urutan_json)
    if len(num_ids) != harapan_numid:
        temuan.append(_temuan('-', 'json_docx', 'numbering_unit', 'Major',
                              f'{len(num_ids)} numId, seharusnya {harapan_numid}'))

    target_left = {0: 425, 1: 845, 2: 1264}
    for lvl, left_target in target_left.items():
        aktual = ilvl_indent.get(lvl)
        if not aktual:
            temuan.append(_temuan('-', 'json_docx', 'indentasi_hilang', 'Minor',
                                  f'Level {lvl + 1} tidak memiliki indentasi'))
            continue
        left, hang = int(aktual[0] or 0), int(aktual[1] or 0)
        if abs(left - left_target) > 2:
            temuan.append(_temuan('-', 'json_docx', 'indentasi', 'Minor',
                                  f'Level {lvl + 1}: left {left}, target {left_target}'))
        if not (300 <= hang <= left):
            temuan.append(_temuan('-', 'json_docx', 'hanging', 'Minor',
                                  f'Level {lvl + 1}: hanging {hang} di luar rentang wajar'))

    # header tabel berulang
    for tabel in doc.tables:
        tr = tabel.rows[0]._tr
        if tr.find(qn('w:trPr')) is None or tr.find(qn('w:trPr')).find(qn('w:tblHeader')) is None:
            temuan.append(_temuan('-', 'json_docx', 'header_tabel', 'Minor',
                                  'Header tabel tidak ditandai berulang'))

    return {'file': str(path.relative_to(ROOT)), 'temuan': temuan,
            'teks_diperiksa': total_teks, 'teks_cocok': cocok_teks,
            'num_id': len(num_ids), 'kuk_docx': kuk_docx_peta}


# --------------------------------------------------------------------------
# 3. Render & nomor tampilan
# --------------------------------------------------------------------------

def render_pdf(docx_path: Path) -> Path | None:
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    target = RENDER_DIR / (docx_path.stem + '.pdf')
    if target.exists():
        return target
    try:
        subprocess.run(['flatpak', 'run', 'org.libreoffice.LibreOffice', '--headless',
                        '--convert-to', 'pdf', '--outdir', str(RENDER_DIR), str(docx_path)],
                       check=True, capture_output=True, timeout=240)
    except Exception:
        return None
    return target if target.exists() else None


def audit_render(pdf: Path, urutan: list[str]) -> dict:
    temuan = []
    doc = fitz.open(str(pdf))
    mulai = {}
    for i, page in enumerate(doc):
        m = re.search(r'KODE UNIT: (\S+)', page.get_text())
        if m:
            mulai[m.group(1)] = i + 1
    if list(mulai) != urutan:
        temuan.append(_temuan('-', 'render', 'urutan_render', 'Major',
                              f'Urutan halaman {list(mulai)} != {urutan}'))
    for kode, hal in mulai.items():
        if hal == 0:
            temuan.append(_temuan(kode, 'render', 'halaman_awal', 'Minor',
                                  'Unit tidak mulai di halaman baru'))

    # jarak nomor ke teks pada hasil render
    jarak = []
    for page in doc:
        for b in page.get_text('dict')['blocks']:
            for l in b.get('lines', []):
                sp = l.get('spans') or []
                if len(sp) >= 3 and re.fullmatch(r'\d+(?:\.\d+)*\.', sp[0]['text'].strip()):
                    jarak.append(sp[-1]['bbox'][0] - sp[0]['bbox'][2])
    if jarak and (min(jarak) < 4 or max(jarak) > 12):
        temuan.append(_temuan('-', 'render', 'jarak_nomor', 'Minor',
                              f'Jarak nomor-teks {min(jarak):.1f}-{max(jarak):.1f} pt'))

    kosong = [i + 1 for i, p in enumerate(doc) if len(p.get_text().strip()) < 40]
    if kosong:
        temuan.append(_temuan('-', 'render', 'halaman_kosong', 'Minor',
                              f'Halaman kosong: {kosong}'))

    # numbering tampil: setiap kemunculan BATASAN VARIABEL diikuti nomor 1
    for i, page in enumerate(doc):
        t = page.get_text()
        for bagian in ('BATASAN VARIABEL', 'PANDUAN PENILAIAN'):
            if bagian in t:
                sesudah = t.split(bagian, 1)[1]
                nomor = INDEKS.findall(sesudah)[:1]
                if nomor and nomor[0].split('.')[0] != '1':
                    temuan.append(_temuan('-', 'render', 'numbering_restart', 'Major',
                                          f'{bagian} halaman {i + 1} mulai dari {nomor[0]}'))
    doc.close()
    return {'halaman': doc.page_count if False else None, 'temuan': temuan,
            'mulai_unit': mulai}


# --------------------------------------------------------------------------
# Orkestrasi
# --------------------------------------------------------------------------

def unit_uji() -> list[dict]:
    dok = next((d for d in schema_library.daftar_skema()
                if d.get('nama_skema') == SKEMA_UJI), None)
    if not dok:
        return []
    peta = (dok.get('hasil_pencocokan') or {}).get('units') or {}
    hasil = []
    for u in dok.get('units') or []:
        kode = u['kode_unit']
        path_json = jobs.JSON_OUT / f'{kode}.json'
        if not path_json.exists():
            path_json = ROOT / 'data' / 'json' / 'schema_content_creator' / f'{kode}.json'
        hasil.append({
            'kode_unit': kode,
            'judul': u.get('judul_skema'),
            'pdf': (peta.get(kode) or {}).get('pdf'),
            'mulai': (peta.get(kode) or {}).get('start_page'),
            'akhir': (peta.get(kode) or {}).get('end_page'),
            'json': path_json if path_json.exists() else None,
            'terverifikasi_manual': kode in (dok.get('verifikasi_manual') or {}),
        })
    return hasil


def _ringkas_unit(h: dict, peta_docx: dict | None = None) -> dict:
    t = h.get('temuan') or []
    krit = any(x['keparahan'] == 'Critical' for x in t)
    major = any(x['keparahan'] == 'Major' for x in t)
    teks = [x for x in t if x['jenis'].startswith('teks')]
    kuk = [x for x in t if x['jenis'].startswith('kuk')]
    return {
        'kode_unit': h['kode_unit'],
        'pdf': h.get('pdf'),
        'jumlah_elemen': h.get('jumlah_elemen'),
        'jumlah_kuk': h.get('jumlah_kuk'),
        'kuk_pdf': h.get('kuk_pdf'),
        'kuk_json': h.get('kuk_json'),
        'kuk_docx': (peta_docx or {}).get(h['kode_unit']),
        'temuan': t,
        'status': ('gagal' if krit else 'perlu_verifikasi' if major
                   else 'lolos_struktur' if t else 'lolos_perbandingan_teks'),
        'lolos_struktur': not any(x['jenis'] in
                                  ('kode_berbeda', 'judul', 'deskripsi', 'jumlah_elemen')
                                  for x in t),
        'lolos_kelengkapan_nomor': not kuk,
        'lolos_perbandingan_teks': not teks,
    }


def jalankan_audit(dokumen_meta: dict | None = None) -> dict:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    units = unit_uji()
    peta_pdf = {p.name: p for p in (ROOT / 'data' / 'pdf').glob('*.pdf')}
    for d in library.daftar_dokumen():
        internal = d.get('nama_internal')
        if internal and (ROOT / internal).exists():
            peta_pdf[Path(internal).name] = ROOT / internal

    hasil_pdf = []
    for u in units:
        if not u['json']:
            hasil_pdf.append({'kode_unit': u['kode_unit'], 'temuan': [
                _temuan(u['kode_unit'], 'pdf_json', 'json_hilang', 'Critical',
                        'JSON hasil ekstraksi tidak tersedia.')]})
            continue
        pdf = peta_pdf.get(u['pdf'] or '')
        if not pdf:
            hasil_pdf.append({'kode_unit': u['kode_unit'], 'temuan': [
                _temuan(u['kode_unit'], 'pdf_json', 'pdf_hilang', 'Critical',
                        'PDF sumber tidak ditemukan di perpustakaan.')]})
            continue
        data = json.loads(u['json'].read_text(encoding='utf-8'))
        hasil_pdf.append(audit_pdf_json(u['kode_unit'], pdf, u['mulai'], u['akhir'], data))

    hasil_docx = None
    hasil_render = None
    if dokumen_meta:
        hasil_docx = audit_docx(dokumen_meta)
        pdf_render = render_pdf(ROOT / dokumen_meta['berkas_docx'])
        if pdf_render:
            hasil_render = audit_render(pdf_render, [u['kode_unit'] for u in dokumen_meta['units']])
            hasil_render['file'] = str(pdf_render.relative_to(ROOT))
            hasil_render['halaman'] = fitz.open(str(pdf_render)).page_count

    semua = []
    for h in hasil_pdf:
        semua.extend(h.get('temuan') or [])
    if hasil_docx:
        semua.extend(hasil_docx['temuan'])
    if hasil_render:
        semua.extend(hasil_render['temuan'])

    hitung = {k: sum(1 for t in semua if t['keparahan'] == k)
              for k in ('Critical', 'Major', 'Minor')}

    if hitung['Critical'] or hitung['Major']:
        status = 'gagal'
    elif hitung['Minor']:
        status = 'perlu_verifikasi'
    else:
        status = 'lolos_perbandingan_teks'

    laporan = {
        'dibuat': datetime.now().isoformat(timespec='seconds'),
        'skema': SKEMA_UJI,
        'dokumen_diaudit': dokumen_meta['id'] if dokumen_meta else None,
        'unit': [_ringkas_unit(h, (hasil_docx or {}).get('kuk_docx')) for h in hasil_pdf],
        'docx': hasil_docx,
        'render': hasil_render,
        'ringkasan': {
            'unit_diaudit': len(hasil_pdf),
            'temuan_total': len(semua),
            'critical': hitung['Critical'],
            'major': hitung['Major'],
            'minor': hitung['Minor'],
            'teks_diperiksa': (hasil_docx or {}).get('teks_diperiksa'),
            'teks_cocok': (hasil_docx or {}).get('teks_cocok'),
            'status': status,
        },
        'temuan': semua,
        'catatan': [
            'Audit PDF memakai get_text("words"), parser utama memakai blocks/dict; '
            'keduanya PyMuPDF sehingga PDF tanpa lapisan teks tidak dapat diaudit.',
            'Perbandingan teks memakai normalisasi spasi/baris; huruf, angka, dan tanda '
            'baca tidak diubah.',
            'Status terverifikasi_manual tidak diberikan otomatis oleh audit.',
        ],
    }
    return laporan


# --------------------------------------------------------------------------
# Laporan
# --------------------------------------------------------------------------

def simpan_laporan(laporan: dict) -> tuple[Path, Path]:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    j = QA_DIR / 'laporan_qa_v1.json'
    j.write_text(json.dumps(laporan, ensure_ascii=False, indent=2), encoding='utf-8')
    h = QA_DIR / 'laporan_qa_v1.html'
    h.write_text(_html(laporan), encoding='utf-8')
    return j, h


def _html(laporan: dict) -> str:
    r = laporan['ringkasan']
    warna = {'Critical': '#b42318', 'Major': '#a8650a', 'Minor': '#46586c'}
    baris_unit = ''
    peta_temuan = {t['kode_unit']: t for t in laporan['temuan']}
    for u in laporan['unit']:
        t = u.get('temuan') or []
        krit = sum(1 for x in t if x['keparahan'] == 'Critical')
        maj = sum(1 for x in t if x['keparahan'] == 'Major')
        mino = sum(1 for x in t if x['keparahan'] == 'Minor')
        baris_unit += (
            f"<tr><td><code>{u['kode_unit']}</code></td>"
            f"<td>{u.get('jumlah_elemen') or 0}</td>"
            f"<td>{len(u.get('kuk_pdf') or [])}</td>"
            f"<td>{len(u.get('kuk_json') or [])}</td>"
            f"<td>{u.get('kuk_docx') if u.get('kuk_docx') is not None else '-'}</td>"
            f"<td>{'gagal' if krit else 'perlu_verifikasi' if maj else 'lolos_perbandingan_teks'}</td>"
            f"<td>{krit} / {maj} / {mino}</td></tr>")

    detail = ''
    for t in laporan['temuan']:
        detail += (
            f"<tr><td><code>{t['kode_unit']}</code></td><td>{t['tahap']}</td>"
            f"<td>{t['jenis']}</td>"
            f"<td><b style='color:{warna.get(t['keparahan'], '#333')}'>{t['keparahan']}</b></td>"
            f"<td>{t['pesan']}</td>"
            f"<td>{t.get('halaman') or '-'}</td>"
            f"<td><code>{str(t.get('teks_pdf') or '')[:120]}</code></td>"
            f"<td><code>{str(t.get('teks_json') or '')[:120]}</code></td></tr>")

    return f"""<!doctype html><html lang="id"><head><meta charset="utf-8">
<title>Laporan QA v1 · SKKNI Extractor</title>
<style>
 body{{font-family:system-ui,Arial,sans-serif;margin:28px;color:#1b2733;background:#f6f8fb}}
 h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:16px;margin:26px 0 8px}}
 .muted{{color:#6b7a8c;font-size:13px}}
 .cards{{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}}
 .card{{background:#fff;border:1px solid #e2e8f0;border-radius:9px;padding:12px 16px;min-width:150px}}
 .card b{{display:block;font-size:24px}}
 table{{width:100%;border-collapse:collapse;background:#fff;font-size:12.5px}}
 th,td{{border:1px solid #e2e8f0;padding:6px 8px;text-align:left;vertical-align:top}}
 th{{background:#eef3f9;font-size:11.5px;text-transform:uppercase;letter-spacing:.4px}}
 code{{font-size:11.5px;background:#f1f5f9;padding:1px 4px;border-radius:4px}}
</style></head><body>
<h1>Laporan QA v1 — SKKNI Extractor</h1>
<p class="muted">Dibuat {laporan['dibuat']} · skema {laporan['skema']} ·
dokumen {laporan.get('dokumen_diaudit') or '-'}</p>
<div class="cards">
 <div class="card">Unit diaudit<b>{r['unit_diaudit']}</b></div>
 <div class="card">Temuan<b>{r['temuan_total']}</b></div>
 <div class="card">Critical<b>{r['critical']}</b></div>
 <div class="card">Major<b>{r['major']}</b></div>
 <div class="card">Minor<b>{r['minor']}</b></div>
 <div class="card">Status<b>{r['status']}</b></div>
 <div class="card">Teks diperiksa<b>{r.get('teks_diperiksa') or 0}</b></div>
 <div class="card">Teks cocok<b>{r.get('teks_cocok') or 0}</b></div>
</div>
<h2>Rekap per unit</h2>
<table><thead><tr><th>Unit</th><th>Elemen</th><th>KUK PDF</th><th>KUK JSON</th>
<th>KUK DOCX</th><th>Status</th><th>Critical / Major / Minor</th></tr></thead>
<tbody>{baris_unit}</tbody></table>
<h2>Temuan</h2>
<table><thead><tr><th>Unit</th><th>Tahap</th><th>Jenis</th><th>Keparahan</th><th>Pesan</th>
<th>Halaman</th><th>Teks PDF</th><th>Teks JSON</th></tr></thead>
<tbody>{detail or '<tr><td colspan="8">Tidak ada temuan.</td></tr>'}</tbody></table>
<h2>Catatan</h2><ul class="muted">{''.join(f'<li>{c}</li>' for c in laporan['catatan'])}</ul>
</body></html>"""


if __name__ == '__main__':
    import sys
    from app.services import document_service as ds

    docs = ds.daftar_dokumen()
    meta = None
    if docs:
        meta = next((d for d in docs if d.get('status') == 'siap_ditinjau'), docs[0])
    lap = jalankan_audit(meta)
    j, h = simpan_laporan(lap)
    print(json.dumps(lap['ringkasan'], ensure_ascii=False, indent=2))
    print('JSON:', j)
    print('HTML:', h)

"""
SKKNI Extractor - Pipeline Skema -> PDF -> JSON -> DOCX (Fase 3D)

Alur:
1. Baca dokumen skema (schema_parser)          -> data/json/schema_content_creator.json
2. Cocokkan kode ke PDF SKKNI (unit_matcher)
3. Ekstrak tiap unit (unit_parser)             -> data/json/schema_content_creator/<kode>.json
4. Validasi struktur & teks
5. Gabungkan menjadi satu DOCX (multi_docx_generator)
6. Tulis laporan                              -> output/laporan_content_creator.json
"""

import json
import re
import subprocess
import shutil
from pathlib import Path

import pymupdf as fitz

from app.schema_parser import baca_skema, simpan_skema
from app.unit_matcher import cocokkan
from app.unit_parser import parse_unit, save_unit_json
from app.section_parser import flatten_nodes, normalize_text
from app.multi_docx_generator import generate_multi_docx

ROOT = Path(__file__).resolve().parent.parent
JSON_DIR = ROOT / 'data' / 'json' / 'schema_content_creator'
OUT_DIR = ROOT / 'output'
NAMA_FINAL = 'SKKNI Content Creator - 10 Unit Kompetensi.docx'
NAMA_DRAFT = 'SKKNI Content Creator - 10 Unit Kompetensi - DRAFT_BELUM_LENGKAP.docx'

LABEL_STRUKTUR = ('BATASAN VARIABEL', 'PANDUAN PENILAIAN', 'ELEMEN KOMPETENSI',
                  'KRITERIA UNJUK KERJA', 'KODE UNIT', 'JUDUL UNIT')


def _rapat(s: str) -> str:
    return re.sub(r'\s+', '', s or '')


def validasi_unit(unit: dict, skema: dict, match: dict, pdf_path: Path) -> dict:
    """Validasi satu unit hasil ekstraksi (15 butir pada spesifikasi Fase 3D)."""
    kode = unit['kode_unit']
    elemen = unit['elemen_kompetensi']
    bv, pp = unit['batasan_variabel'], unit['panduan_penilaian']
    bv_nodes = flatten_nodes(bv['sections'])
    pp_nodes = flatten_nodes(pp['sections'])
    semua = bv_nodes + pp_nodes
    kuk = [k for e in elemen for k in e['kuk']]

    cek = {}
    cek['kode_sesuai_skema'] = (kode == skema['kode_unit'])
    cek['judul_sesuai_pdf'] = bool(unit['judul_unit']) and (
        not match.get('judul_pdf')
        or _rapat(unit['judul_unit']).lower()[:40] == _rapat(match['judul_pdf']).lower()[:40])
    cek['punya_elemen'] = len(elemen) > 0
    cek['semua_elemen_punya_kuk'] = all(e['kuk'] for e in elemen)
    nomor_kuk = [k['nomor_kuk'] for k in kuk]
    cek['kuk_tidak_duplikat'] = len(nomor_kuk) == len(set(nomor_kuk))
    cek['batasan_variabel_ada'] = bv['ditemukan'] and bool(bv_nodes)
    cek['panduan_penilaian_ada'] = pp['ditemukan'] and bool(pp_nodes)
    cek['penomoran_konsisten'] = not any(
        'tidak berurutan' in c or 'duplikat' in c or 'Lompatan' in c
        for c in (unit['validasi'].get('catatan') or []))
    cek['tanpa_teks_unit_lain'] = not any(
        'KODE UNIT' in (b.get('teks_mentah') or '').upper() for b in (bv, pp))
    teks_node = [n['teks'] for n in semua if len(n['teks']) > 25]
    cek['deskripsi_bersih'] = not any(
        l in (unit['deskripsi_unit'] or '').upper() for l in LABEL_STRUKTUR)
    cek['ada_info_pdf'] = bool(unit['metadata_sumber'].get('nama_dokumen'))

    # Perbandingan teks PDF -> JSON (baris mentah)
    doc = fitz.open(str(pdf_path))
    teks_unit_pdf = _rapat(' '.join(doc[p].get_text()
                                    for p in range(match['start_page'], match['end_page'] + 1)))

    def teks_hal(a, b):
        b = b if b is not None else a
        return normalize_text(' '.join(doc[p].get_text() for p in range(a, b + 1)))

    dicek = cocok = 0
    beda = []
    for n in semua:
        t = teks_hal(n['halaman_pdf'], n['halaman_akhir'])
        for baris in (n['teks_mentah'] or '').split('\n'):
            b = normalize_text(baris)
            if not b:
                continue
            dicek += 1
            if b in t:
                cocok += 1
            else:
                beda.append({'nomor': n['nomor'], 'baris': b[:80]})
    for k in kuk:
        t = teks_hal(k['halaman_pdf'], k['halaman_pdf'])
        for baris in (k.get('teks_mentah') or '').split('\n'):
            b = normalize_text(baris)
            if not b:
                continue
            dicek += 1
            if b in t:
                cocok += 1
            else:
                beda.append({'nomor': k['nomor_kuk'], 'baris': b[:80]})
    doc.close()

    cek['teks_pdf_cocok'] = not beda
    # Status internal parser tidak boleh 'gagal_ekstraksi': indikasi sel tabel
    # tidak terbaca. Catatan geometri ringan tetap dicatat sebagai peringatan.
    cek['parser_tidak_gagal'] = unit['validasi']['status'] != 'gagal_ekstraksi'

    # Duplikasi teks: sumber PDF kadang memang mengulang kalimat. Duplikasi
    # yang terbukti ada di PDF dikategorikan peringatan format sumber.
    from collections import Counter
    hitung = Counter(teks_node)
    duplikat = [t for t, n in hitung.items() if n > 1]
    duplikat_sumber = [t for t in duplikat if teks_unit_pdf.count(_rapat(t)) > 1]
    cek['tanpa_duplikasi_teks'] = not (set(duplikat) - set(duplikat_sumber))

    peringatan = list(unit['validasi'].get('peringatan_format_sumber', []))
    for t in duplikat_sumber:
        peringatan.append({
            'kategori': 'peringatan_format_sumber',
            'jenis': 'teks_berulang_pada_pdf',
            'teks': t[:120],
            'pesan': 'Kalimat yang sama muncul lebih dari sekali pada PDF sumber; '
                     'teks dibiarkan apa adanya',
        })

    gagal = [k for k, v in cek.items() if not v]
    return {
        'cek': cek,
        'gagal': gagal,
        'teks': {'dicek': dicek, 'cocok': cocok, 'selisih': beda},
        'peringatan_format_sumber': peringatan,
        'catatan_validasi': unit['validasi'].get('catatan', []),
        'status': 'valid_struktur' if not gagal else 'perlu_verifikasi',
    }


def proses(skema_path: str | Path | None = None,
           pdf_paths: list[str | Path] | None = None,
           render_pdf: bool = True) -> dict:
    """Jalankan seluruh pipeline Fase 3D dan kembalikan laporan."""
    skema_path = Path(skema_path or ROOT / 'data' / 'skema' / '21. Content Creator.docx')
    pdf_paths = [Path(p) for p in (pdf_paths or [
        ROOT / 'data' / 'pdf' / 'SKKNI 2018-056.pdf.pdf',
        ROOT / 'data' / 'pdf' / 'SKKNI 2018-107.pdf.pdf',
        ROOT / 'data' / 'pdf' / 'SKKNI 2022-124.pdf.pdf',
    ])]

    hilang = [str(p) for p in [skema_path] + pdf_paths if not p.exists()]
    if hilang:
        raise FileNotFoundError(f'Berkas tidak ditemukan: {hilang}')

    # 1-2. Skema + pencocokan
    skema = baca_skema(skema_path)
    simpan_skema(skema, JSON_DIR.parent / 'schema_content_creator.json')

    cocok = cocokkan(skema['units'], pdf_paths)

    # 3. Ekstraksi tiap unit
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    units_json = []
    hasil_unit = []
    gagal_ekstrak = []

    for entri in cocok['units']:
        if entri['status'] != 'ditemukan':
            gagal_ekstrak.append({'kode_unit': entri['kode_unit'],
                                  'alasan': entri['status']})
            continue

        pdf = next(p for p in pdf_paths if p.name == entri['pdf'])
        try:
            unit = parse_unit(str(pdf), entri['kode_unit'],
                              entri['start_page'], entri['end_page'])
        except Exception as e:
            gagal_ekstrak.append({'kode_unit': entri['kode_unit'],
                                  'alasan': f'{type(e).__name__}: {e}'})
            continue

        unit['metadata_sumber']['nama_dokumen'] = entri['pdf']
        unit['metadata_sumber']['skkni'] = entri['pdf']
        path_json = JSON_DIR / f"{entri['kode_unit']}.json"
        save_unit_json(unit, str(path_json))

        v = validasi_unit(unit, entri, entri, pdf)
        units_json.append(unit)
        hasil_unit.append({
            'nomor_urut': entri['nomor_urut'],
            'kode_unit': unit['kode_unit'],
            'judul': unit['judul_unit'],
            'judul_skema': entri['judul_skema'],
            'sumber_skkni': entri['pdf'],
            'halaman_pdf': [entri['start_page'], entri['end_page']],
            'elemen': len(unit['elemen_kompetensi']),
            'kuk': sum(len(e['kuk']) for e in unit['elemen_kompetensi']),
            'validasi': v['status'],
            'gagal_cek': v['gagal'],
            'teks': v['teks'],
            'peringatan_format_sumber': v['peringatan_format_sumber'],
            'json': str(path_json.relative_to(ROOT)),
        })

    # 5. DOCX (final hanya jika semua unit lengkap)
    lengkap = (len(units_json) == len(skema['units'])
               and not cocok['tidak_ditemukan'] and not cocok['konflik'])
    nama = NAMA_FINAL if lengkap else NAMA_DRAFT
    docx_path = OUT_DIR / nama

    spec = {'units': [{'kode': u['kode_unit'],
                       'skkni': next(h['sumber_skkni'] for h in hasil_unit
                                     if h['kode_unit'] == u['kode_unit'])}
                      for u in units_json]}
    info_docx = generate_multi_docx(spec, str(docx_path), json_dir=JSON_DIR)

    # 6. Render PDF
    pdf_out = docx_path.with_suffix('.pdf')
    dirender = False
    if render_pdf and shutil.which('flatpak'):
        subprocess.run(['flatpak', 'run', 'org.libreoffice.LibreOffice', '--headless',
                        '--convert-to', 'pdf', '--outdir', str(OUT_DIR), str(docx_path)],
                       capture_output=True, text=True, timeout=420)
        dirender = pdf_out.exists()

    halaman = 0
    if dirender:
        with fitz.open(str(pdf_out)) as d:
            halaman = d.page_count

    # 7. Laporan
    total_elemen = sum(h['elemen'] for h in hasil_unit)
    total_kuk = sum(h['kuk'] for h in hasil_unit)
    perlu_verifikasi = sum(1 for h in hasil_unit if h['validasi'] != 'valid_struktur')

    laporan = {
        'sumber_skema': skema_path.name,
        'dokumen_skkni': [p.name for p in pdf_paths],
        'tabel': hasil_unit,
        'ringkasan': {
            'unit_skema': len(skema['units']),
            'unit_ditemukan': cocok['statistik']['ditemukan'],
            'unit_diekstrak': len(units_json),
            'unit_perlu_verifikasi': perlu_verifikasi,
            'unit_gagal_ekstrak': len(gagal_ekstrak),
            'total_elemen': total_elemen,
            'total_kuk': total_kuk,
            'halaman_docx': halaman,
            'tabel_word': len(units_json),
            'dokumen_lengkap': lengkap,
            'nama_docx': str(docx_path.relative_to(ROOT)),
            'pdf_render': str(pdf_out.relative_to(ROOT)) if dirender else None,
            'peringatan_format_sumber': sum(len(h['peringatan_format_sumber'])
                                            for h in hasil_unit),
        },
        'tidak_ditemukan': cocok['tidak_ditemukan'],
        'konflik': cocok['konflik'],
        'gagal_ekstrak': gagal_ekstrak,
        'peringatan_skema': skema['peringatan'],
        'info_docx': {k: v for k, v in info_docx.items() if k != 'unit'},
        'metadata_unit': info_docx['unit'],
    }

    out_laporan = OUT_DIR / 'laporan_content_creator.json'
    out_laporan.parent.mkdir(parents=True, exist_ok=True)
    out_laporan.write_text(json.dumps(laporan, ensure_ascii=False, indent=2), encoding='utf-8')
    laporan['_path_laporan'] = str(out_laporan.relative_to(ROOT))
    return laporan


if __name__ == '__main__':
    hasil = proses()
    print('Unit skema   :', hasil['ringkasan']['unit_skema'])
    print('Ditemukan    :', hasil['ringkasan']['unit_ditemukan'])
    print('Diekstrak    :', hasil['ringkasan']['unit_diekstrak'])
    print('Elemen / KUK :', hasil['ringkasan']['total_elemen'], '/', hasil['ringkasan']['total_kuk'])
    print('Halaman DOCX :', hasil['ringkasan']['halaman_docx'])
    print('DOCX         :', hasil['ringkasan']['nama_docx'])
    print('Laporan      :', hasil['_path_laporan'])

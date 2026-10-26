"""
Validator kelengkapan nomor KUK yang INDEPENDEN dari parser utama (Fase 4B).

Perbedaan metode dengan `app/unit_parser.py`:
- Parser utama memisahkan kolom memakai koordinat blok teks (`get_text("blocks")`).
- Validator ini memakai deteksi tabel PyMuPDF (`page.find_tables()`) lalu membaca
  sel kolom KRITERIA UNJUK KERJA, dengan cadangan deteksi kata (`get_text("words")`)
  bila tabel tidak terdeteksi.

Keduanya tetap memakai PyMuPDF, sehingga kegagalan pembacaan PDF yang sama
(mis. PDF hasil pindai tanpa lapisan teks) dapat memengaruhi keduanya. Validator
ini memeriksa NOMOR KUK saja, bukan kebenaran uraian teks.
"""

import json
import re
from app import penyimpanan
from pathlib import Path

import pymupdf as fitz

ROOT = Path(__file__).resolve().parent.parent
JSON_DIRS = (
    ROOT / 'data' / 'json' / 'schema_content_creator',
    ROOT / 'data' / 'json' / 'cross_skkni',
    # Hasil ekstraksi dari antarmuka web (jobs.py). Tanpa folder ini, validator
    # tidak menemukan JSON yang baru dibuat lewat tombol "Ekstrak" sehingga
    # seluruh unit berstatus "tidak dapat dibandingkan".
    ROOT / 'data' / 'json' / 'browser_extraction',
)

# Nomor KUK pada sel tabel. PDF kerap memecah nomor menjadi "3", ".", "1"
# pada baris berbeda, sehingga teks diratakan lebih dulu lalu dicocokkan
# sebagai pasangan angka diikuti huruf kapital (awal uraian KUK).
POLA_PASANGAN = re.compile(r'(?<![\w.])(\d{1,2})\s+(\d{1,3})\s+(?=[A-Z(])')
POLA_KATA = re.compile(r'^(\d{1,2})\.(\d{1,3})$')


def _nomor(a: str, b: str) -> str:
    return f'{int(a)}.{int(b)}'


def _nomor_dari_teks(teks: str) -> list[str]:
    """Ambil semua pasangan nomor KUK dari teks sel yang sudah diratakan."""
    rapi = re.sub(r'[.\n\r\t]+', ' ', teks or '')
    rapi = re.sub(r'\s+', ' ', rapi)
    hasil = []
    for m in POLA_PASANGAN.finditer(rapi):
        a, b = int(m.group(1)), int(m.group(2))
        if 1 <= a <= 9 and 1 <= b <= 40:
            hasil.append(f'{a}.{b}')
    return hasil


def _dari_tabel(halaman) -> list[tuple[str, str]]:
    """(nomor, kunci sel) dari kolom KRITERIA UNJUK KERJA pada tabel halaman."""
    hasil = []
    try:
        tabel = halaman.find_tables()
    except Exception:
        return hasil

    for t_i, t in enumerate(tabel.tables):
        try:
            baris = t.extract()
        except Exception:
            continue
        for r_i, sel in enumerate(baris):
            if len(sel) < 2:
                continue
            teks = (sel[1] or '').strip()
            # Hanya baris header yang dilewati. Jangan memakai pencarian kata
            # "kriteria" di mana pun, karena uraian KUK sering memuat kata itu
            # (mis. "diperiksa sesuai dengan kriteria pengguna").
            if not teks or teks.upper().startswith('KRITERIA UNJUK KERJA'):
                continue
            for n in _nomor_dari_teks(teks):
                hasil.append((n, f'tabel{t_i}-baris{r_i}'))
    return hasil


def _dari_kata(halaman) -> list[str]:
    """Cadangan: token 'n.n' di separuh kanan halaman (area kolom KUK)."""
    hasil = []
    lebar = halaman.rect.width
    try:
        kata = halaman.get_text('words')
    except Exception:
        return hasil
    for w in kata:
        x0, _, _, _, teks = w[0], w[1], w[2], w[3], w[4]
        if x0 < lebar * 0.35:
            continue
        m = POLA_KATA.match(teks.strip())
        if m:
            hasil.append(_nomor(m.group(1), m.group(2)))
    return hasil


def _kunci(nomor: str) -> tuple[int, int]:
    a, b = nomor.split('.')
    return int(a), int(b)


def periksa_unit(pdf_path, kode_unit: str, start_page: int, end_page: int,
                 kuk_json: list[str]) -> dict:
    """
    Bandingkan nomor KUK pada PDF dengan daftar nomor pada JSON.

    `start_page`/`end_page` memakai indeks PDF 0-based (sama dengan metadata).
    """
    kemunculan: dict[str, list[int]] = {}
    asal_sel: dict[str, set] = {}
    metode_dipakai = {'tabel': 0, 'kata': 0}
    halaman_tanpa_bukti = []
    catatan = []

    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return {
            'kode_unit': kode_unit,
            'kuk_pdf': [],
            'kuk_json': sorted(kuk_json, key=_kunci),
            'kuk_hilang': sorted(kuk_json, key=_kunci),
            'kuk_ekstra': [],
            'duplikat': [],
            'halaman_tanpa_bukti': [],
            'status': 'perlu_verifikasi',
            'catatan': ['PDF tidak dapat dibuka oleh validator.'],
        }

    try:
        for p in range(max(0, start_page), min(end_page, doc.page_count - 1) + 1):
            halaman = doc[p]
            teks_hal = halaman.get_text()
            # Hanya halaman tabel Elemen/KUK yang diperiksa. Halaman Batasan
            # Variabel dan Panduan Penilaian memakai penomoran serupa (1.1.)
            # sehingga tidak boleh dihitung sebagai KUK.
            halaman_tabel = 'ELEMEN KOMPETENSI' in teks_hal.upper()
            if not halaman_tabel:
                continue

            pasangan = _dari_tabel(halaman)
            if pasangan:
                metode_dipakai['tabel'] += 1
            else:
                kata = _dari_kata(halaman)
                pasangan = [(n, f'kata{ i }') for i, n in enumerate(kata)]
                if kata:
                    metode_dipakai['kata'] += 1
                else:
                    halaman_tanpa_bukti.append(p + 1)
            for n, sel in pasangan:
                kemunculan.setdefault(n, []).append(p + 1)
                asal_sel.setdefault(n, set()).add(f'{p + 1}:{sel}')
    finally:
        doc.close()

    kuk_pdf = sorted(kemunculan, key=_kunci)
    himpunan_pdf = set(kuk_pdf)
    himpunan_json = set(kuk_json)

    hilang = sorted(himpunan_pdf - himpunan_json, key=_kunci)
    ekstra = sorted(himpunan_json - himpunan_pdf, key=_kunci)
    if halaman_tanpa_bukti:
        # Bagian tabel tidak terbaca: nomor JSON tidak boleh disebut "ekstra"
        # karena bisa saja berada di bagian yang gagal dibaca.
        ekstra = []
        catatan.append('Perbandingan tidak lengkap karena ada bagian tabel yang '
                       'tidak dapat dibaca.')
    # Duplikat = nomor yang muncul di lebih dari satu sel/baris, bukan karena
    # nomor tersebut disebut ulang di dalam uraian teks yang sama.
    duplikat = sorted([n for n, sel in asal_sel.items() if len(sel) > 1], key=_kunci)

    if hilang:
        catatan.append('Nomor KUK ada pada PDF tetapi tidak ada pada JSON.')
    if ekstra:
        catatan.append('Nomor KUK ada pada JSON tetapi tidak terkonfirmasi pada PDF.')
    if duplikat:
        catatan.append('Nomor KUK yang sama muncul lebih dari sekali pada PDF.')
    if halaman_tanpa_bukti:
        catatan.append('Bagian tabel tidak dapat dibaca dengan yakin pada halaman: '
                       + ', '.join(str(h) for h in halaman_tanpa_bukti) + '.')
    if not kuk_pdf and not hilang:
        catatan.append('Tidak ada nomor KUK yang terdeteksi pada rentang halaman unit.')

    status = ('valid_kelengkapan'
              if not hilang and not ekstra and not duplikat and not halaman_tanpa_bukti and kuk_pdf
              else 'perlu_verifikasi')

    return {
        'kode_unit': kode_unit,
        'halaman_pdf_0based': [start_page, end_page],
        'kuk_pdf': kuk_pdf,
        'kuk_json': sorted(himpunan_json, key=_kunci),
        'kuk_hilang': hilang,
        'kuk_ekstra': ekstra,
        'duplikat': duplikat,
        'halaman_tanpa_bukti': halaman_tanpa_bukti,
        'kemunculan': {n: h for n, h in sorted(kemunculan.items(), key=lambda x: _kunci(x[0]))},
        'metode': metode_dipakai,
        'status': status,
        'catatan': catatan,
    }


def muat_kuk_json(kode_unit: str) -> list[str] | None:
    """Daftar nomor KUK dari JSON hasil ekstraksi (bila tersedia)."""
    for folder in JSON_DIRS:
        p = folder / f'{kode_unit}.json'
        if not p.exists():
            continue
        data = penyimpanan.baca_json(p)
        if data is None:
            return None
        nomor = [k['nomor_kuk'] for e in data.get('elemen_kompetensi') or []
                 for k in e.get('kuk') or [] if k.get('nomor_kuk')]
        return nomor
    return None


def periksa_dokumen(pdf_path, units: list[dict]) -> dict:
    """Periksa seluruh unit pada satu dokumen."""
    hasil = []
    tanpa_json = []
    catatan = []

    for u in units:
        kode = u['kode_unit']
        kuk_json = muat_kuk_json(kode)
        if kuk_json is None:
            tanpa_json.append(kode)
            hasil.append({
                'kode_unit': kode,
                'kuk_pdf': [],
                'kuk_json': [],
                'kuk_hilang': [],
                'kuk_ekstra': [],
                'duplikat': [],
                'halaman_tanpa_bukti': [],
                'status': 'tidak_dapat_dibandingkan',
                'catatan': ['JSON unit belum tersedia; ekstraksi belum dijalankan untuk '
                            'unit ini sehingga nomor KUK tidak dapat dibandingkan.'],
            })
            continue
        hasil.append(periksa_unit(pdf_path, kode,
                                  u.get('halaman_pdf_0based', 0),
                                  u.get('halaman_akhir_0based', u.get('halaman_pdf_0based', 0)),
                                  kuk_json))

    if tanpa_json:
        catatan.append('Unit tanpa JSON (belum diekstrak): ' + ', '.join(tanpa_json) + '.')

    terbandingkan = [h for h in hasil if h['status'] != 'tidak_dapat_dibandingkan']
    bermasalah = [h['kode_unit'] for h in terbandingkan
                  if h['status'] != 'valid_kelengkapan']
    total_hilang = sum(len(h['kuk_hilang']) for h in hasil)
    total_ekstra = sum(len(h['kuk_ekstra']) for h in hasil)
    total_duplikat = sum(len(h['duplikat']) for h in hasil)

    status = ('valid_kelengkapan'
              if terbandingkan and not bermasalah and not tanpa_json
              else 'perlu_verifikasi')
    return {
        'status': status,
        'ringkasan': {
            'unit_diperiksa': len(hasil),
            'unit_terbandingkan': len(terbandingkan),
            'unit_tanpa_json': len(tanpa_json),
            'unit_lengkap': len(terbandingkan) - len(bermasalah),
            'unit_bermasalah': len(bermasalah),
            'nomor_hilang': total_hilang,
            'nomor_ekstra': total_ekstra,
            'nomor_duplikat': total_duplikat,
        },
        'units': hasil,
        'catatan': catatan,
    }

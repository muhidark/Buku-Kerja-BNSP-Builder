"""
Pengujian validator kelengkapan KUK (Fase 4B).

Fokus: validator harus menemukan nomor KUK yang hilang dari JSON walaupun
parser utama menyatakan hasilnya cocok. Kasus acuan: M.70MKT00.013.1.
"""

import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import pymupdf as fitz

from app import kuk_completeness_validator as v
from app.kuk_completeness_validator import (muat_kuk_json, periksa_dokumen,
                                            periksa_unit)

PDF_124 = project_root / 'data' / 'pdf' / 'SKKNI 2022-124.pdf.pdf'
KODE = 'M.70MKT00.013.1'
HAL_AWAL, HAL_AKHIR = 66, 70          # indeks PDF 0-based

lulus, gagal = [], []


def cek(nama, kondisi, detail=''):
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}" + (f" — {detail}" if detail and not kondisi else ''))


def pdf_sintetis(path: Path, baris: list[str], ulang: list[str] = ()) -> Path:
    """PDF kecil tanpa garis tabel: menguji jalur cadangan deteksi kata."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((80, 80), 'ELEMEN KOMPETENSI            KRITERIA UNJUK KERJA',
                     fontsize=9)
    y = 110
    for teks in baris:
        page.insert_text((90, y), teks, fontsize=9)
        y += 16
    for teks in ulang:                       # nomor ganda di kolom kanan
        page.insert_text((400, y), teks, fontsize=9)
        y += 16
    doc.save(str(path))
    doc.close()
    return path


def main():
    print("=" * 100)
    print("PENGUJIAN VALIDATOR KELENGKAPAN KUK — FASE 4B")
    print("=" * 100)

    if not PDF_124.exists():
        print(f"ERROR: PDF tidak ditemukan: {PDF_124}")
        return 1

    kuk_json = muat_kuk_json(KODE)
    print(f"\n{KODE} | JSON: {len(kuk_json or [])} nomor -> {kuk_json}")

    # ------------------------------------------------------------ 1 data lengkap
    print("\n1. DATA LENGKAP (SETELAH PERBAIKAN PARSER)")
    hasil = periksa_unit(PDF_124, KODE, HAL_AWAL, HAL_AKHIR, kuk_json)
    cek('semua nomor JSON terdeteksi di PDF',
        set(hasil['kuk_pdf']) == set(kuk_json), str(hasil['kuk_pdf']))
    cek('tidak ada nomor hilang', not hasil['kuk_hilang'])
    cek('tidak ada nomor ekstra', not hasil['kuk_ekstra'])
    cek('status valid_kelengkapan', hasil['status'] == 'valid_kelengkapan', hasil['status'])
    cek('13 nomor KUK terdeteksi', len(hasil['kuk_pdf']) == 13, str(len(hasil['kuk_pdf'])))

    # ------------------------------------------------- 2 KUK sengaja dihilangkan
    print("\n2. KUK SENGAJA DIHILANGKAN DARI SALINAN JSON")
    salinan = [n for n in kuk_json if n not in ('3.3', '3.4')]
    hasil2 = periksa_unit(PDF_124, KODE, HAL_AWAL, HAL_AKHIR, salinan)
    cek('3.3 terdeteksi hilang', '3.3' in hasil2['kuk_hilang'], str(hasil2['kuk_hilang']))
    cek('3.4 terdeteksi hilang', '3.4' in hasil2['kuk_hilang'], str(hasil2['kuk_hilang']))
    cek('tepat dua nomor hilang', hasil2['kuk_hilang'] == ['3.3', '3.4'],
        str(hasil2['kuk_hilang']))
    cek('status perlu_verifikasi', hasil2['status'] == 'perlu_verifikasi')
    cek('tidak mengarang teks KUK', 'teks' not in json.dumps(hasil2))
    cek('JSON produksi tidak diubah',
        json.loads((project_root / 'data' / 'json' / 'schema_content_creator'
                    / f'{KODE}.json').read_text(encoding='utf-8'))['elemen_kompetensi'][2]['kuk'][-1]['nomor_kuk'] == '3.4')

    # ------------------------------------------------------- 3 nomor berlebih
    print("\n3. NOMOR PADA JSON TANPA BUKTI DI PDF")
    hasil3 = periksa_unit(PDF_124, KODE, HAL_AWAL, HAL_AKHIR, kuk_json + ['3.5'])
    cek('3.5 dilaporkan sebagai ekstra', hasil3['kuk_ekstra'] == ['3.5'], str(hasil3['kuk_ekstra']))
    cek('status perlu_verifikasi', hasil3['status'] == 'perlu_verifikasi')

    # -------------------------------------------------- 4 tabel lintas halaman
    print("\n4. TABEL LINTAS HALAMAN")
    cek('nomor dari halaman 1 unit terbaca', '3.1' in hasil['kemunculan'])
    cek('3.3 terbaca pada halaman berikutnya',
        hasil['kemunculan'].get('3.3') == [68], str(hasil['kemunculan'].get('3.3')))
    cek('3.4 terbaca pada halaman berikutnya',
        hasil['kemunculan'].get('3.4') == [68], str(hasil['kemunculan'].get('3.4')))
    cek('dua halaman tabel diperiksa', hasil['metode']['tabel'] == 2, str(hasil['metode']))

    # ------------------------------------------------ 5 blok KUK selebar halaman
    print("\n5. BLOK KUK SELEBAR HALAMAN")
    cek('3.3 (blok lebar) terdeteksi', '3.3' in hasil['kuk_pdf'])
    cek('3.4 (blok lebar) terdeteksi', '3.4' in hasil['kuk_pdf'])

    # ---------------------------------------------------------- 6 duplikat
    print("\n6. NOMOR DUPLIKAT")
    tmp = project_root / 'output' / 'tmp_kuk_duplikat.pdf'
    tmp.parent.mkdir(parents=True, exist_ok=True)
    pdf_sintetis(tmp, ['1 Mengidentifikasi alat'],
                 ulang=['1.1 Informasi alat', '1.1 Informasi alat diulang'])
    d = periksa_unit(tmp, 'UJI.000.001.1', 0, 0, ['1.1'])
    cek('duplikat 1.1 terdeteksi', d['duplikat'] == ['1.1'], str(d['duplikat']))
    cek('status perlu_verifikasi pada duplikat', d['status'] == 'perlu_verifikasi')
    cek('jalur cadangan kata dipakai', d['metode']['kata'] == 1, str(d['metode']))
    tmp.unlink(missing_ok=True)

    # ------------------------------------------------- 7 tabel tidak terbaca
    print("\n7. BAGIAN TABEL TIDAK TERBACA")
    tmp2 = project_root / 'output' / 'tmp_kuk_kosong.pdf'
    pdf_sintetis(tmp2, ['Elemen tanpa nomor KUK yang dapat dibaca'])
    k = periksa_unit(tmp2, 'UJI.000.002.1', 0, 0, ['1.1'])
    cek('halaman tanpa bukti dilaporkan', k['halaman_tanpa_bukti'] == [1],
        str(k['halaman_tanpa_bukti']))
    cek('nomor JSON tidak disebut ekstra saat tabel tidak terbaca',
        k['kuk_ekstra'] == [], str(k['kuk_ekstra']))
    cek('catatan perbandingan tidak lengkap',
        any('tidak dapat dibaca' in c for c in k['catatan']), str(k['catatan']))
    cek('status perlu_verifikasi', k['status'] == 'perlu_verifikasi')
    tmp2.unlink(missing_ok=True)

    # ------------------------------------------------------ 8 periksa dokumen
    print("\n8. PERIKSA DOKUMEN (UNIT TANPA JSON)")
    units = [
        {'kode_unit': KODE, 'halaman_pdf_0based': HAL_AWAL, 'halaman_akhir_0based': HAL_AKHIR},
        {'kode_unit': 'TIDAK.ADA.999.9', 'halaman_pdf_0based': 0, 'halaman_akhir_0based': 1},
    ]
    dok = periksa_dokumen(PDF_124, units)
    cek('unit tanpa JSON ditandai', dok['units'][1]['status'] == 'tidak_dapat_dibandingkan',
        dok['units'][1]['status'])
    cek('ringkasan menghitung unit tanpa JSON', dok['ringkasan']['unit_tanpa_json'] == 1)
    cek('ringkasan menghitung unit terbandingkan', dok['ringkasan']['unit_terbandingkan'] == 1)
    cek('status dokumen perlu_verifikasi', dok['status'] == 'perlu_verifikasi')
    cek('tidak ada nomor hilang pada unit lengkap', dok['ringkasan']['nomor_hilang'] == 0)

    # ------------------------------------------- 9 independensi dari parser
    print("\n9. INDEPENDENSI METODE")
    sumber = Path(v.__file__).read_text(encoding='utf-8')
    cek('tidak mengimpor unit_parser',
        'from app.unit_parser' not in sumber and 'import app.unit_parser' not in sumber)
    cek('memakai find_tables', 'find_tables' in sumber)
    cek('punya jalur cadangan kata', 'get_text(\'words\')' in sumber)

    print("\n" + "=" * 100)
    print(f"HASIL: {len(lulus)} lulus, {len(gagal)} gagal")
    if gagal:
        for g in gagal:
            print(f"  - {g}")
    print("=" * 100)
    return 0 if not gagal else 1


if __name__ == '__main__':
    sys.exit(main())

"""
Pengujian Editor Koreksi Per-Unit (Fase 4F - Langkah 2).

Memverifikasi:
1. Teks elemen & KUK dapat diubah dan disimpan lewat form / API tanpa menimpa
   berkas hasil mesin di ``browser_extraction/``.
2. Saat halaman dimuat ulang, teks koreksi yang tampil.
3. Tidak ada karakter yang hilang: simpan -> muat ulang -> bandingkan persis (==).
4. Klik "Kembalikan ke hasil mesin" menghapus berkas koreksi dan mengembalikan
   teks serta status ke semula.
5. Ekspor JSON LSP, Smart Paste, Buku Kerja APL, dan DOCX menggunakan teks koreksi.
"""

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from docx import Document
from fastapi.testclient import TestClient
from app import koreksi, schema_library as sl, status_units
from app.buku_kerja import susun_data_buku_kerja
from app.lsp_exporter import ambil_json_unit, unit_ke_lsp_dict, unit_ke_smart_paste_text
from app.main import app
from tests.dukungan import klien
from app.services import document_service as ds

DOC_UJI = project_root / 'output' / 'web_documents' / '_uji_koreksi'
META_UJI = project_root / 'data' / 'web_documents' / '_uji_koreksi'

lulus, gagal = [], []


def cek(nama: str, kondisi: bool, detail: str = '') -> None:
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}" + (f" — {detail}" if detail and not kondisi else ''))


def ambil_csrf(client: TestClient, url: str) -> str:
    r = client.get(url)
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    return m.group(1) if m else ''


def main() -> int:
    print('=' * 100)
    print('PENGUJIAN EDITOR KOREKSI PER-UNIT — FASE 4F')
    print('=' * 100)

    sid = next((d['id'] for d in sl.daftar_skema()
                if d.get('nama_skema') == 'SOCIAL MEDIA MARKETING'), None)
    if not sid:
        print('ERROR: Skema SOCIAL MEDIA MARKETING tidak ditemukan.')
        return 1

    kode = 'J.63OPR00.005.2'
    jalur_mesin = koreksi.cari_berkas_mesin(kode)
    sha_mesin_awal = hashlib.sha256(jalur_mesin.read_bytes()).hexdigest()

    for d in (DOC_UJI, META_UJI):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
    ds.DOC_DIR = DOC_UJI
    ds.META_DIR = META_UJI

    client = klien(app, 'admin')

    try:
        koreksi.hapus_koreksi(kode)

        # ------------------------------------------------------------------
        # 1. Halaman Editor Koreksi & Tautan PDF
        # ------------------------------------------------------------------
        print('\n1. HALAMAN EDITOR KOREKSI')
        r_ed = client.get(f'/skema/{sid}/unit/{kode}/koreksi')
        cek('GET /skema/{id}/unit/{kode}/koreksi HTTP 200', r_ed.status_code == 200)
        cek('form editor memuat kode unit', kode in r_ed.text)
        cek('status awal unit adalah Perlu diperiksa', 'Perlu diperiksa' in r_ed.text)
        cek('tautan Buka PDF hal. X tersedia', '/pdf#page=' in r_ed.text)

        # Pastikan route PDF inline berfungsi
        m_pdf = re.search(r'href="(/skkni/[0-9a-f]{32}/pdf)#page=\d+"', r_ed.text)
        cek('URL endpoint PDF inline ditemukan', m_pdf is not None)
        if m_pdf:
            r_pdf = client.get(m_pdf.group(1))
            cek('GET /skkni/{doc_id}/pdf mengembalikan PDF inline 200',
                r_pdf.status_code == 200
                and r_pdf.headers.get('content-type') == 'application/pdf'
                and 'inline' in r_pdf.headers.get('content-disposition', ''))

        # ------------------------------------------------------------------
        # 2. Simpan Koreksi & Presisi Karakter 100%
        # ------------------------------------------------------------------
        print('\n2. SIMPAN KOREKSI & PRESISI KARAKTER')
        token = ambil_csrf(client, f'/skema/{sid}/unit/{kode}/koreksi')

        teks_elemen_1 = 'Mengidentifikasi perangkat lunak & konfigurasi khusus (Uji Presisi: "Kutipan", [Kurung], 100% Akurat!)'
        teks_kuk_1_1 = '1) Perangkat lunak diidentifikasi sesuai spesifikasi teknis; 2) Parameter diuji coba (a -> b <= c) tanpa kehilangan 1 karakter pun.'
        teks_kuk_1_2 = 'Hasil identifikasi didokumentasikan secara lengkap pada lembar kerja asesor.'

        r_simpan = client.post(
            f'/skema/{sid}/unit/{kode}/koreksi',
            data={
                'csrf_token': token,
                'judul_unit': 'Mengoperasikan Piranti Lunak Pengolah Kata Tingkat Maju (Terkoreksi)',
                'elemen_nomor': ['1', '2'],
                'elemen_nama': [teks_elemen_1, 'Menyimpan dan mencetak dokumen hasil olahan'],
                'kuk_elemen': ['1', '1', '2'],
                'kuk_nomor': ['1.1', '1.2', '2.1'],
                'kuk_uraian': [teks_kuk_1_1, teks_kuk_1_2, 'Dokumen disimpan dalam format standar.'],
            },
            follow_redirects=True,
        )
        cek('POST simpan koreksi HTTP 200', r_simpan.status_code == 200)
        cek('pesan sukses tampil', 'berhasil disimpan' in r_simpan.text)
        cek('berkas koreksi dibuat di data/json/koreksi/', koreksi.path_koreksi(kode).is_file())
        cek('berkas hasil mesin TIDAK tertimpa (SHA-256 tetap identik)',
            hashlib.sha256(jalur_mesin.read_bytes()).hexdigest() == sha_mesin_awal)

        # Muat ulang dari disk dan bandingkan karakter persis
        tersimpan = koreksi.ambil_koreksi(kode)
        cek('nama elemen 1 sama persis tanpa karakter hilang',
            tersimpan['elemen'][0]['nama'] == teks_elemen_1,
            repr(tersimpan['elemen'][0]['nama']))
        cek('uraian KUK 1.1 sama persis tanpa karakter hilang',
            tersimpan['elemen'][0]['kuk'][0]['uraian'] == teks_kuk_1_1,
            repr(tersimpan['elemen'][0]['kuk'][0]['uraian']))
        cek('hash_hasil_mesin tercatat sesuai SHA-256 berkas mesin',
            tersimpan['hash_hasil_mesin'] == sha_mesin_awal)

        # Muat ulang halaman editor & halaman pratinjau
        r_reload = client.get(f'/skema/{sid}/unit/{kode}/koreksi')
        cek('halaman editor menampilkan teks koreksi setelah dimuat ulang',
            'Parameter diuji coba' in r_reload.text and 'Siap dipakai' in r_reload.text)

        r_prev = client.get(f'/skema/{sid}/unit/{kode}')
        cek('halaman pratinjau unit menampilkan teks koreksi',
            'Parameter diuji coba' in r_prev.text and '● Siap dipakai' in r_prev.text)

        # ------------------------------------------------------------------
        # 3. Ekspor JSON LSP, Smart Paste, Buku Kerja, dan DOCX Memakai Koreksi
        # ------------------------------------------------------------------
        print('\n3. EKSPOR JSON, SMART PASTE, BUKU KERJA, DAN DOCX MEMAKAI TEKS KOREKSI')
        unit_final = ambil_json_unit(kode)
        lsp_dict = unit_ke_lsp_dict(unit_final)
        smart_txt = unit_ke_smart_paste_text(unit_final)

        cek('JSON LSP menggunakan teks KUK hasil koreksi',
            any(teks_kuk_1_1 in k for k in lsp_dict['elemen'][0]['kuk']),
            str(lsp_dict['elemen'][0]['kuk']))
        cek('Smart Paste menggunakan teks KUK hasil koreksi',
            teks_kuk_1_1 in smart_txt)

        bk = susun_data_buku_kerja(sid)
        unit_bk = next(u for u in bk['daftar_unit'] if u['kode_unit'] == kode)
        cek('Buku Kerja APL-02 menggunakan teks KUK hasil koreksi',
            any(teks_kuk_1_1 in k for k in unit_bk['elemen'][0]['kuk']))

        meta_docx = ds.buat_dokumen(sid, [kode], setujui_draft=False)
        doc_word = Document(str(ds.jalur_docx(meta_docx)))
        semua_teks_tabel = '\n'.join(
            cell.text for tbl in doc_word.tables for row in tbl.rows for cell in row.cells
        )
        cek('dokumen Word (.docx) menggunakan teks KUK hasil koreksi',
            teks_kuk_1_1 in semua_teks_tabel)

        # ------------------------------------------------------------------
        # 4. Kembalikan ke Hasil Mesin
        # ------------------------------------------------------------------
        print('\n4. KEMBALIKAN KE HASIL MESIN')
        r_kembali = client.post(
            f'/skema/{sid}/unit/{kode}/koreksi/kembalikan',
            data={'csrf_token': token},
            follow_redirects=True,
        )
        cek('POST kembalikan ke hasil mesin HTTP 200', r_kembali.status_code == 200)
        cek('berkas koreksi terhapus dari disk', not koreksi.path_koreksi(kode).exists())

        st_setelah = status_units.status_unit(kode)
        cek('status unit kembali ke semula (perlu)', st_setelah['status'] == 'perlu', str(st_setelah))
        cek('teks koreksi tidak lagi muncul di unit final',
            teks_kuk_1_1 not in json.dumps(ambil_json_unit(kode), ensure_ascii=False))

    finally:
        koreksi.hapus_koreksi(kode)
        ds.DOC_DIR = project_root / 'output' / 'web_documents'
        ds.META_DIR = project_root / 'data' / 'web_documents'
        for d in (DOC_UJI, META_UJI):
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)

    print('\n' + '=' * 100)
    print(f'HASIL: {len(lulus)} lulus, {len(gagal)} gagal')
    if gagal:
        for g in gagal:
            print(f'  - {g}')
    print('=' * 100)
    return 0 if not gagal else 1


if __name__ == '__main__':
    sys.exit(main())

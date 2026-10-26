"""
Pengujian Audit Riwayat & Deteksi Konflik Koreksi (Fase 4F - Langkah 3).

Memverifikasi:
1. Saat koreksi disimpan, ``hash_hasil_mesin`` tercatat dan status unit ``siap``.
2. Ekstraksi ulang yang mengubah isi berkas JSON mesin memicu penanda konflik
   (``konflik_koreksi=True``, status unit ``perlu`` dengan alasan hasil mesin berubah).
3. Halaman editor menampilkan peringatan konflik serta perbandingan berdampingan
   antara teks asli/baru hasil mesin dan teks koreksi manual.
4. Resolusi konflik "Pertahankan Koreksi Manual" memperbarui ``hash_hasil_mesin``
   dan mengembalikan status unit menjadi ``siap``.
"""

import json
import re
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from fastapi.testclient import TestClient
from app import koreksi, schema_library as sl, status_units
from app.main import app

from tests.dukungan import klien
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
    print('PENGUJIAN AUDIT RIWAYAT & DETEKSI KONFLIK KOREKSI — FASE 4F')
    print('=' * 100)

    sid = next((d['id'] for d in sl.daftar_skema()
                if d.get('nama_skema') == 'SOCIAL MEDIA MARKETING'), None)
    if not sid:
        print('ERROR: Skema SOCIAL MEDIA MARKETING tidak ditemukan.')
        return 1

    kode = 'J.63OPR00.004.2'
    jalur_mesin = koreksi.cari_berkas_mesin(kode)
    isi_mesin_asli = jalur_mesin.read_text(encoding='utf-8')
    client = klien(app, 'admin')

    try:
        koreksi.hapus_koreksi(kode)

        # ------------------------------------------------------------------
        # 1. Simpan Koreksi Manual pada Kondisi Mesin Awal
        # ------------------------------------------------------------------
        print('\n1. SIMPAN KOREKSI MANUAL AWAL')
        data_awal = json.loads(isi_mesin_asli)
        elemen_koreksi = koreksi.normalisasi_elemen_koreksi(data_awal['elemen_kompetensi'])
        teks_mesin_1_1_awal = elemen_koreksi[0]['kuk'][0]['uraian']
        teks_koreksi_1_1 = 'Uraian KUK 1.1 yang telah disempurnakan secara manual oleh Admin LSP.'
        elemen_koreksi[0]['kuk'][0]['uraian'] = teks_koreksi_1_1

        koreksi.simpan_koreksi(kode, elemen_koreksi, oleh='muhadi')

        info_awal = koreksi.status_koreksi(kode)
        st_awal = status_units.status_unit(kode)
        cek('ada_koreksi bernilai True', info_awal['ada_koreksi'] is True)
        cek('konflik bernilai False sebelum ekstraksi ulang', info_awal['konflik'] is False)
        cek('status unit adalah siap (Dikoreksi manual)',
            st_awal['status'] == 'siap' and st_awal['alasan'] == 'Dikoreksi manual',
            str(st_awal))

        # ------------------------------------------------------------------
        # 2. Simulasi Ekstraksi Ulang yang Mengubah Berkas JSON Mesin
        # ------------------------------------------------------------------
        print('\n2. EKSTRAKSI ULANG MENGUBAH JSON MESIN -> MEMICU KONFLIK')
        data_ekstrak_ulang = json.loads(isi_mesin_asli)
        teks_mesin_1_1_baru = 'Uraian KUK 1.1 hasil ekstraksi ulang mesin versi baru dari PDF.'
        data_ekstrak_ulang['elemen_kompetensi'][0]['kuk'][0]['uraian_kuk'] = teks_mesin_1_1_baru
        jalur_mesin.write_text(
            json.dumps(data_ekstrak_ulang, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

        info_konflik = koreksi.status_koreksi(kode)
        st_konflik = status_units.status_unit(kode)
        cek('status_koreksi mendeteksi konflik (konflik=True)', info_konflik['konflik'] is True)
        cek('hash_hasil_mesin berbeda dengan hash_mesin_sekarang',
            info_konflik['hash_hasil_mesin'] != info_konflik['hash_mesin_sekarang'])
        cek('status_unit berubah menjadi perlu akibat konflik',
            st_konflik['status'] == 'perlu' and st_konflik['konflik_koreksi'] is True,
            str(st_konflik))
        cek('alasan menjelaskan hasil mesin berubah sejak dikoreksi',
            'Hasil mesin berubah sejak dikoreksi' in st_konflik['alasan'],
            st_konflik['alasan'])

        # ------------------------------------------------------------------
        # 3. Tampilan Riwayat & Perbandingan Berdampingan di Halaman Editor
        # ------------------------------------------------------------------
        print('\n3. RIWAYAT MENAMPILKAN TEKS MESIN VS TEKS KOREKSI BERDAMPINGAN')
        r_ed = client.get(f'/skema/{sid}/unit/{kode}/koreksi')
        cek('halaman editor HTTP 200 saat terjadi konflik', r_ed.status_code == 200)
        cek('kotak peringatan Konflik Koreksi Terdeteksi tampil',
            'Konflik Koreksi Terdeteksi' in r_ed.text)
        cek('teks hasil mesin baru ditampilkan di tabel perbandingan',
            teks_mesin_1_1_baru in r_ed.text)
        cek('teks koreksi manual juga ditampilkan berdampingan',
            teks_koreksi_1_1 in r_ed.text)
        cek('penanda ✎ Diubah tampil pada baris yang berbeda',
            '✎ Diubah' in r_ed.text)

        # ------------------------------------------------------------------
        # 4. Resolusi Konflik: Pertahankan Koreksi Manual
        # ------------------------------------------------------------------
        print('\n4. RESOLUSI KONFLIK: PERTAHANKAN KOREKSI MANUAL')
        token = ambil_csrf(client, f'/skema/{sid}/unit/{kode}/koreksi')
        r_pertahankan = client.post(
            f'/skema/{sid}/unit/{kode}/koreksi',
            data={'csrf_token': token, 'aksi': 'pertahankan'},
            follow_redirects=True,
        )
        cek('POST aksi=pertahankan HTTP 200', r_pertahankan.status_code == 200)
        cek('pesan konfirmasi pertahankan tampil',
            'Koreksi manual dipertahankan' in r_pertahankan.text)

        info_selesai = koreksi.status_koreksi(kode)
        st_selesai = status_units.status_unit(kode)
        cek('konflik hilang setelah dipertahankan (konflik=False)', info_selesai['konflik'] is False)
        cek('hash_hasil_mesin diperbarui ke hash mesin terbaru',
            info_selesai['hash_hasil_mesin'] == info_selesai['hash_mesin_sekarang'])
        cek('status unit kembali menjadi siap', st_selesai['status'] == 'siap', str(st_selesai))

    finally:
        jalur_mesin.write_text(isi_mesin_asli, encoding='utf-8')
        koreksi.hapus_koreksi(kode)

    print('\n' + '=' * 100)
    print(f'HASIL: {len(lulus)} lulus, {len(gagal)} gagal')
    if gagal:
        for g in gagal:
            print(f'  - {g}')
    print('=' * 100)
    return 0 if not gagal else 1




def test_koreksi_konflik():
    assert main() == 0


if __name__ == '__main__':
    sys.exit(main())

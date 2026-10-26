"""
Pengujian penyimpanan sebagian (per bagian) konfigurasi MUK
(langkah 3.4, temuan T-08).

Dua hal yang dijaga:

1. Server: mengirim hanya satu bagian (mis. `{"ia02": {...}}`) tidak boleh
   menghapus bagian lain. Tanpa jaminan ini, tombol "Simpan bagian ini" justru
   berbahaya.
2. Template: halaman MUK harus memuat penanda perubahan (badge "belum
   disimpan"), peringatan sebelum menutup tab, tombol simpan per bagian, dan
   peta bagian -> kunci payload.

Data kerja disnapshoot dan dipulihkan di akhir agar test tidak mengubah
konfigurasi MUK milik pengguna.
"""

import json
import re
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app import db, schema_library as sl
from app.buku_kerja import muat_konfigurasi_muk, simpan_konfigurasi_muk
from app.main import app
from tests.dukungan import klien

TEMPLATE = project_root / 'app' / 'templates' / 'skema_muk.html'
lulus, gagal = [], []


def cek(nama: str, kondisi: bool, detail: str = '') -> None:
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}"
          + (f" — {detail}" if detail and not kondisi else ''))


def main() -> int:
    print('=' * 100)
    print('PENGUJIAN SIMPAN PER BAGIAN & PENANDA PERUBAHAN MUK — LANGKAH 3.4 (T-08)')
    print('=' * 100)

    daftar = sl.daftar_skema()
    if not daftar:
        print('ERROR: belum ada skema terdaftar.')
        return 1
    sid = daftar[0]['id']

    # ---------------------------------------------------- 1. template memuat hook
    print('\n1. TEMPLATE MUK MEMUAT PENANDA & TOMBOL SIMPAN PER BAGIAN')
    tpl = TEMPLATE.read_text(encoding='utf-8')
    for fitur, pola in [
        ('bilah simpan', 'id="muk-simpan-bar"'),
        ('penanda belum disimpan', "className = 'muk-kotor'"),
        ('tombol simpan per bagian', 'onclick="simpanBagianAktif()"'),
        ('peta bagian -> payload', 'var BAGIAN_PANEL'),
        ('pengawas beforeunload', "addEventListener('beforeunload'"),
        ('validasi per bagian', 'function validasiBagian'),
        ('payload dipisah dari pengiriman', 'function susunPayload()'),
    ]:
        cek(f'{fitur} ada', pola in tpl)

    cek('tombol simpan seluruh tetap ada', 'onsubmit="siapkanPayloadMuk()"' in tpl)

    # ------------------------------------------- 2. simpan sebagian tidak menghapus
    print('\n2. SIMPAN SEBAGIAN TIDAK MENGHAPUS BAGIAN LAIN')
    sampel = 'uji-simpan-bagian-3-4'
    berkas_muk = project_root / 'data' / 'schema_library' / 'muk' / f'{sid}.json'
    cadangan_json = berkas_muk.read_text(encoding='utf-8') if berkas_muk.exists() else None
    with db._ambil_koneksi() as conn:
        cadangan_versi = [dict(r) for r in conn.execute(
            'SELECT * FROM muk_versi WHERE schema_id = ?', (sid,))]

    try:
        simpan_konfigurasi_muk(sid, {
            'personel': {'nama_asesor': sampel, 'nama_tuk': 'TUK Awal'},
            'ia02': {'skenario': 'skenario awal', 'durasi_waktu': '90 Menit'},
        }, kode_versi='v1', nama_versi='Versi Uji', is_aktif=True)

        awal = muat_konfigurasi_muk(sid, kode_versi='v1')
        cek('personel tersimpan', awal['personel']['nama_asesor'] == sampel)
        cek('ia02 tersimpan', awal['ia02']['skenario'] == 'skenario awal')

        c = klien(app, 'admin')
        halaman = c.get(f'/skema/{sid}/muk').text
        cocok_csrf = re.search(r'name="csrf_token" value="([^"]+)"', halaman)
        csrf = cocok_csrf.group(1) if cocok_csrf else ''
        cek('token CSRF terbaca dari halaman MUK', len(csrf) > 20)

        # Kirim HANYA bagian ia02, seperti tombol "Simpan bagian ini".
        r = c.post(f'/skema/{sid}/muk', data={
            'csrf_token': csrf,
            'kode_versi': 'v1',
            'nama_versi': 'Versi Uji',
            'muk_json': json.dumps({'ia02': {'skenario': 'skenario baru'}}),
        }, follow_redirects=False)
        cek('POST bagian tunggal diterima', r.status_code == 303, f'status={r.status_code}')

        sesudah = muat_konfigurasi_muk(sid, kode_versi='v1')
        cek('ia02 berubah sesuai kiriman', sesudah['ia02']['skenario'] == 'skenario baru',
            f"nilai={sesudah['ia02'].get('skenario')!r}")
        cek('personel TIDAK terhapus', sesudah['personel']['nama_asesor'] == sampel,
            f"nilai={sesudah['personel'].get('nama_asesor')!r}")
        cek('field personel lain tetap utuh', sesudah['personel']['nama_tuk'] == 'TUK Awal',
            f"nilai={sesudah['personel'].get('nama_tuk')!r}")

        # Kirim hanya personel: ia02 harus tetap
        c.post(f'/skema/{sid}/muk', data={
            'csrf_token': csrf,
            'kode_versi': 'v1',
            'nama_versi': 'Versi Uji',
            'muk_json': json.dumps({'personel': {'nama_asesor': 'Nama Baru'}}),
        }, follow_redirects=False)
        akhir = muat_konfigurasi_muk(sid, kode_versi='v1')
        cek('personel berubah', akhir['personel']['nama_asesor'] == 'Nama Baru')
        cek('ia02 tetap dari kiriman sebelumnya',
            akhir['ia02']['skenario'] == 'skenario baru',
            f"nilai={akhir['ia02'].get('skenario')!r}")
        cek('field personel lain tidak kosong', akhir['personel']['nama_tuk'] == 'TUK Awal',
            f"nilai={akhir['personel'].get('nama_tuk')!r}")
    finally:
        # pulihkan data kerja
        if cadangan_json is not None:
            berkas_muk.write_text(cadangan_json, encoding='utf-8')
        with db._ambil_koneksi() as conn:
            conn.execute('DELETE FROM muk_versi WHERE schema_id = ?', (sid,))
            for r in cadangan_versi:
                kolom = ', '.join(r.keys())
                tanda = ', '.join('?' * len(r))
                conn.execute(f'INSERT INTO muk_versi ({kolom}) VALUES ({tanda})', tuple(r.values()))
            conn.commit()
        print('\n[data konfigurasi MUK dipulihkan]')

    print('\n' + '=' * 100)
    print(f'HASIL: {len(lulus)} lulus, {len(gagal)} gagal')
    if gagal:
        for g in gagal:
            print(f'  - GAGAL: {g}')
    print('=' * 100)
    return 0 if not gagal else 1




def test_muk_simpan_bagian():
    assert main() == 0


if __name__ == '__main__':
    sys.exit(main())

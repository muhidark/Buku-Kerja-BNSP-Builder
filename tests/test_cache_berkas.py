"""
Pengujian cache pembacaan JSON (langkah 4.1, temuan T-18).

Yang dijaga adalah KEBENARAN cache, bukan kecepatannya:
1. Pembacaan kedua memakai cache (hit), dan hasilnya sama.
2. Berkas yang berubah otomatis dianggap basi (mtime/ukuran berubah).
3. Mengubah nilai hasil tidak merusak isi cache (pengembalian berupa salinan).
4. Berkas yang hilang menghasilkan None tanpa melempar galat.
5. Satu render halaman skema benar-benar memakai cache (ada hit), sehingga
   pembacaan berulang dalam satu permintaan tidak diulang ke disk.

Catatan jujur yang ikut diuji: untuk pembacaan TUNGGAL cache tidak lebih cepat
daripada `json.loads` (salinan + stat + lock lebih mahal daripada parse berkas
kecil). Keuntungannya hanya muncul saat berkas yang sama dibaca berkali-kali
dalam satu render.
"""

import json
import sys
import tempfile
import time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app import cache_berkas
from app import schema_library as sl

lulus, gagal = [], []


def cek(nama: str, kondisi: bool, detail: str = '') -> None:
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}"
          + (f" — {detail}" if detail and not kondisi else ''))


def main() -> int:
    print('=' * 100)
    print('PENGUJIAN CACHE PEMBACAAN JSON — LANGKAH 4.1 (T-18)')
    print('=' * 100)

    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / 'contoh.json'
        f.write_text(json.dumps({'nilai': 1}), encoding='utf-8')
        cache_berkas.bersihkan()

        # ---------------------------------------------------------- 1. hit
        print('\n1. PEMBACAAN BERULANG MEMAKAI CACHE')
        a = cache_berkas.baca_json(f)
        stat1 = cache_berkas.statistik()
        b = cache_berkas.baca_json(f)
        stat2 = cache_berkas.statistik()
        cek('pembacaan pertama adalah miss', stat1['miss'] == 1 and stat1['hit'] == 0, str(stat1))
        cek('pembacaan kedua adalah hit', stat2['hit'] == 1, str(stat2))
        cek('isi tetap sama', a == b == {'nilai': 1}, f'{a} vs {b}')

        # ------------------------------------------------ 2. mutasi aman
        print('\n2. MENGUBAH HASIL TIDAK MERUSAK CACHE')
        b['nilai'] = 999
        c = cache_berkas.baca_json(f)
        cek('nilai cache tidak ikut berubah', c['nilai'] == 1, f"nilai={c['nilai']}")

        # ------------------------------------------------ 3. otomatis basi
        print('\n3. BERKAS BERUBAH -> CACHE BASI OTOMATIS')
        time.sleep(0.01)
        f.write_text(json.dumps({'nilai': 2}), encoding='utf-8')
        d = cache_berkas.baca_json(f)
        cek('nilai baru terbaca', d['nilai'] == 2, f"nilai={d['nilai']}")

        # ------------------------------------------------ 4. berkas hilang
        print('\n4. BERKAS HILANG / RUSAK')
        f.unlink()
        cek('berkas hilang -> None', cache_berkas.baca_json(f) is None)
        rusak = Path(tmp) / 'rusak.json'
        rusak.write_text('{bukan json', encoding='utf-8')
        cek('berkas rusak -> None (tidak melempar)', cache_berkas.baca_json(rusak) is None)

    # ---------------------------------------- 5. dipakai pada render nyata
    print('\n5. DIPAKAI PADA RENDER HALAMAN SKEMA')
    cache_berkas.bersihkan()
    daftar = sl.daftar_skema()
    if not daftar:
        print('  (tidak ada skema; bagian ini dilewati)')
    else:
        from app.main import app
        from tests.dukungan import klien
        c = klien(app, 'admin')
        r = c.get(f"/skema/{daftar[0]['id']}")
        cek('halaman skema dibalas 200', r.status_code == 200, f'status={r.status_code}')
        stat = cache_berkas.statistik()
        cek('ada pembacaan yang dilayani cache (hit > 0)', stat['hit'] > 0, str(stat))
        cek('jumlah hit lebih banyak daripada miss (pola N+1 tertangani)',
            stat['hit'] > stat['miss'], str(stat))

        # hasil cache tidak boleh mengubah data yang ditampilkan
        cache_berkas.bersihkan()
        r_dingin = c.get(f"/skema/{daftar[0]['id']}")
        r_hangat = c.get(f"/skema/{daftar[0]['id']}")
        cek('tampilan sama dengan/ tanpa cache', r_dingin.text == r_hangat.text,
            'HTML berbeda antara render dingin dan hangat')

    print('\n' + '=' * 100)
    print(f'HASIL: {len(lulus)} lulus, {len(gagal)} gagal')
    if gagal:
        for g in gagal:
            print(f'  - GAGAL: {g}')
    print('=' * 100)
    return 0 if not gagal else 1


if __name__ == '__main__':
    sys.exit(main())

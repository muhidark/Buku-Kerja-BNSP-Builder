"""
Pengujian struktur kode setelah pemecahan `app/main.py` (langkah 4.2, T-19).

Yang dijaga:
1. `app/main.py` hanya menyusun aplikasi — tidak lagi memuat rute halaman.
2. Aturan gerbang 409 hanya ada di satu fungsi (`web_common.cek_gerbang`),
   bukan disalin di setiap tempat yang mencetak/mengunduh.
3. Helper penyimpanan (tulis JSON atomik, SHA-256, siapkan direktori) hanya
   punya satu implementasi, yaitu `app.penyimpanan`.
4. Seluruh halaman utama masih bisa dibuka setelah pemecahan (uji asap).
5. Gerbang 409 tetap benar: menolak bila ada unit Gagal, membiarkan bila tidak.
"""

import re
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app import web_common
from app.paths import ROOT

lulus, gagal = [], []


def cek(nama: str, kondisi: bool, detail: str = '') -> None:
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}"
          + (f" — {detail}" if detail and not kondisi else ''))


def main() -> int:
    print('=' * 100)
    print('PENGUJIAN STRUKTUR KODE — LANGKAH 4.2 (T-19)')
    print('=' * 100)

    app_dir = ROOT / 'app'

    # ---------------------------------------------------- 1. main.py ramping
    print('\n1. app/main.py HANYA MENYUSUN APLIKASI')
    teks_main = (app_dir / 'main.py').read_text(encoding='utf-8')
    jumlah_baris = len(teks_main.splitlines())
    cek('main.py di bawah 300 baris', jumlah_baris < 300, f'{jumlah_baris} baris')
    rute_di_main = re.findall(r"@app\.(get|post)\('([^']+)'", teks_main)
    cek('main.py hanya memuat rute inti (dashboard/unit/ekstraksi)',
        {p for _m, p in rute_di_main} == {'/', '/unit', '/ekstraksi'},
        str(sorted(p for _m, p in rute_di_main)))
    for domain in ('/skkni', '/skema', '/login', '/hasil'):
        cek(f'tidak ada rute {domain} yang tertinggal di main.py',
            all(not p.startswith(domain) for _m, p in rute_di_main))

    # -------------------------------------------- 2. modul rute terpisah
    print('\n2. RUTE TERPISAH PER DOMAIN')
    modul_rute = sorted((app_dir / 'routes').glob('*.py'))
    cek('ada modul rute selain __init__', len([m for m in modul_rute if m.name != '__init__.py']) >= 5,
        str([m.name for m in modul_rute]))
    for m in modul_rute:
        if m.name == '__init__.py':
            continue
        isi = m.read_text(encoding='utf-8')
        cek(f'{m.name} di bawah 400 baris', len(isi.splitlines()) < 400,
            f'{len(isi.splitlines())} baris')
        cek(f'{m.name} memakai APIRouter (bukan app global)', 'router = APIRouter()' in isi)

    # ------------------------------ 3. aturan gerbang hanya di satu tempat
    print('\n3. ATURAN GERBANG 409 HANYA DI SATU FUNGSI')
    penyalinan = []
    for m in app_dir.rglob('*.py'):
        if m.name in ('web_common.py', 'status_units.py'):
            continue
        isi = m.read_text(encoding='utf-8')
        if "ada_gagal" in isi and "status == 'gagal'" in isi:
            penyalinan.append(m.relative_to(ROOT).as_posix())
    cek('tidak ada salinan blok gerbang di modul lain', not penyalinan, str(penyalinan))
    cek('cek_gerbang tersedia di web_common', hasattr(web_common, 'cek_gerbang'))

    # kebenaran cek_gerbang tanpa menyentuh basis data
    cek('tanpa unit gagal -> None', web_common.cek_gerbang('x', {'ada_gagal': False}) is None)
    hasil = web_common.cek_gerbang('x', {
        'ada_gagal': True,
        'penahan': [{'kode_unit': 'M.70MKT00.011.1', 'alasan': 'KUK 0', 'status': 'gagal'},
                    {'kode_unit': 'M.70MKT00.012.1', 'alasan': 'perlu', 'status': 'perlu'}],
    })
    cek('dengan unit gagal -> daftar unit gagal', isinstance(hasil, tuple) and 'M.70MKT00.011.1' in hasil[1],
        str(hasil))
    cek('unit berstatus "perlu" tidak ikut disebut', isinstance(hasil, tuple) and 'M.70MKT00.012.1' not in hasil[1],
        str(hasil))

    # --------------------------- 4. helper penyimpanan satu implementasi
    print('\n4. HELPER PENYIMPANAN HANYA SATU IMPLEMENTASI')
    for nama in ('tulis_json_atomik', 'sha256_berkas', 'pastikan_direktori'):
        definisi = [m.relative_to(ROOT).as_posix() for m in app_dir.rglob('*.py')
                    if re.search(rf'^def {nama}\(', m.read_text(encoding='utf-8'), re.M)]
        cek(f'{nama} didefinisikan tepat sekali', len(definisi) == 1, str(definisi))
        cek(f'{nama} ada di app/penyimpanan.py', definisi == ['app/penyimpanan.py'], str(definisi))

    # baca_json punya dua pintu (cache & langsung) tetapi satu tempat parsing.
    # Pengecualian yang disengaja: skrip audit justru INGIN gagal keras bila
    # korpus JSON rusak, karena itu tanda kerusakan data yang harus terlihat.
    SKRIP_AUDIT = {'app/qa_audit.py', 'app/unit_matcher.py'}
    parse_ganda = []
    for m in app_dir.rglob('*.py'):
        if m.name in ('penyimpanan.py', 'cache_berkas.py'):
            continue
        if m.relative_to(ROOT).as_posix() in SKRIP_AUDIT:
            continue
        isi_modul = m.read_text(encoding='utf-8')
        # Hanya pembacaan BERKAS yang dihitung. `json.loads` atas string dari
        # basis data atau isian formulir bukan duplikasi pembacaan berkas.
        if re.search(r'json\.loads\([^)]*read_text', isi_modul):
            parse_ganda.append(m.relative_to(ROOT).as_posix())
    cek('tidak ada modul lain yang mem-parse JSON sendiri', not parse_ganda, str(parse_ganda))
    isi_cache = (app_dir / 'cache_berkas.py').read_text(encoding='utf-8')
    cek('cache_berkas memakai penyimpanan.baca_json', 'penyimpanan.baca_json' in isi_cache)
    cek('cache_berkas tidak mem-parse JSON sendiri', 'json.loads(' not in isi_cache)

    # ------------------------------------------------ 5. uji asap halaman
    print('\n5. SELURUH HALAMAN UTAMA MASIH TERBUKA')
    from app.main import app
    from tests.dukungan import klien

    c = klien(app, 'admin')
    daftar_skema = __import__('app.schema_library', fromlist=['x']).daftar_skema()
    halaman = ['/', '/skkni', '/skema', '/unit', '/ekstraksi', '/hasil']
    if daftar_skema:
        sid = daftar_skema[0]['id']
        halaman += [f'/skema/{sid}', f'/skema/{sid}/muk', f'/skema/{sid}/cetak-apl']
    for path in halaman:
        r = c.get(path)
        cek(f'GET {path} -> 200', r.status_code == 200, f'status={r.status_code}')
        cek(f'GET {path} memuat HTML lengkap', '</html>' in r.text, 'tidak ada penutup html')

    print('\n' + '=' * 100)
    print(f'HASIL: {len(lulus)} lulus, {len(gagal)} gagal')
    if gagal:
        for g in gagal:
            print(f'  - GAGAL: {g}')
    print('=' * 100)
    return 0 if not gagal else 1


def test_struktur_kode():
    assert main() == 0


if __name__ == '__main__':
    sys.exit(main())

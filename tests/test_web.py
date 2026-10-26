"""
Pengujian antarmuka web (Fase 4A).

Memakai FastAPI TestClient: halaman, API, aset statis, navigasi, dan
kesesuaian statistik dengan berkas nyata di proyek.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from fastapi.testclient import TestClient
from app.main import app
from app import web_data
from app.version import __version__

client = TestClient(app)

lulus, gagal = [], []

HALAMAN = ['/', '/skkni', '/skema', '/unit', '/ekstraksi', '/hasil']


def cek(nama, kondisi, detail=''):
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}" + (f" — {detail}" if detail and not kondisi else ''))


def main():
    print("=" * 100)
    print("PENGUJIAN WEB — FASE 4A")
    print("=" * 100)

    # 1 ------------------------------------------------------------- dashboard
    print("\n1. DASHBOARD")
    r = client.get('/')
    cek('dashboard HTTP 200', r.status_code == 200, str(r.status_code))
    html = r.text
    cek('judul halaman benar', '<title>Dashboard · SKKNI Extractor</title>' in html)
    cek('kartu statistik lengkap', all(x in html for x in
        ('Dokumen SKKNI', 'Skema Sertifikasi', 'Unit Kompetensi', 'Dokumen Hasil')))
    cek('status sistem tampil', 'Status Sistem' in html and 'Backend FastAPI' in html)
    cek('bagian aktivitas ada', 'Aktivitas' in html)

    # 2 ------------------------------------------------------------- semua halaman
    print("\n2. SEMUA HALAMAN")
    isi = {}
    for path in HALAMAN:
        rr = client.get(path)
        isi[path] = rr.text
        cek(f'{path} HTTP 200', rr.status_code == 200, str(rr.status_code))
        cek(f'{path} HTML utuh', '<!doctype html>' in rr.text.lower()
            and '</html>' in rr.text and 'style.css' in rr.text)

    print("\n3. TEMPLATE")
    sisa = [p for p, t in isi.items() if re.search(r'{[{%]', t)]
    cek('tidak ada placeholder template tersisa', not sisa, str(sisa))
    cek('tidak ada traceback di halaman', all('Traceback' not in t for t in isi.values()))
    cek('setiap halaman punya judul unik',
        len({re.search(r'<title>(.*?)</title>', t).group(1) for t in isi.values()}) == len(HALAMAN))

    # 4 ---------------------------------------------------------------- API
    print("\n4. ENDPOINT API")
    h = client.get('/api/health')
    cek('/api/health HTTP 200', h.status_code == 200)
    cek('/api/health JSON benar', h.json() == {'status': 'ok', 'application': 'SKKNI Extractor',
                                               'version': __version__}, str(h.json()))
    cek('/api/health content-type JSON', 'application/json' in h.headers.get('content-type', ''))

    d = client.get('/api/dashboard')
    cek('/api/dashboard HTTP 200', d.status_code == 200)
    data = d.json()
    kunci = ('dokumen_skkni', 'skema_sertifikasi', 'unit_kompetensi', 'hasil_ekstraksi')
    cek('statistik wajib tersedia', all(k in data['stats'] for k in kunci), str(data['stats']))
    cek('statistik berupa bilangan bulat >= 0',
        all(isinstance(data['stats'][k], int) and data['stats'][k] >= 0 for k in kunci))
    cek('status sistem berupa daftar', isinstance(data['sistem'], list) and len(data['sistem']) == 4)
    cek('status modul berupa dict boolean',
        isinstance(data['modul'], dict) and all(isinstance(v, bool) for v in data['modul'].values()))
    cek('aktivitas berupa daftar', isinstance(data['aktivitas'], list))
    cek('metadata aplikasi ada', data.get('application') == 'SKKNI Extractor'
        and data.get('version') == __version__)

    # 5 -------------------------------------------------------------- aset statis
    print("\n5. ASET STATIS")
    css = client.get('/static/css/style.css')
    cek('CSS termuat', css.status_code == 200 and 'text/css' in css.headers.get('content-type', ''))
    cek('CSS berisi variabel tema', '--navy' in css.text and '--green' in css.text)
    cek('CSS punya media query responsif', '@media' in css.text)
    js = client.get('/static/js/app.js')
    cek('JS termuat', js.status_code == 200 and 'javascript' in js.headers.get('content-type', ''))
    cek('JS tanpa dependensi eksternal',
        'http://' not in js.text and 'https://' not in js.text and 'cdn' not in js.text.lower())
    cek('halaman tanpa CDN', all('http://' not in t and 'https://' not in t for t in isi.values()))

    # 6 ------------------------------------------------------------- navigasi
    print("\n6. NAVIGASI")
    tautan = re.findall(r'class="nav-item[^"]*"\s+href="([^"]+)"', isi['/'])
    tautan += re.findall(r'href="([^"]+)"\s+class="nav-item', isi['/'])
    tautan = sorted(set(tautan))
    cek('enam tautan navigasi', tautan == sorted(HALAMAN), str(tautan))
    cek('setiap tautan mengembalikan 200',
        all(client.get(t).status_code == 200 for t in tautan))
    cek('navigasi aktif ditandai di setiap halaman',
        all('is-active' in isi[p] for p in HALAMAN))
    aktif_benar = all(
        f'class="nav-item is-active"' in isi[p] and
        re.search(r'class="nav-item is-active"[^>]*>\s*<span[^>]*>[^<]*</span>\s*<span>([^<]+)</span>', isi[p])
        for p in HALAMAN)
    cek('hanya satu item aktif per halaman',
        all(t.count('nav-item is-active') == 1 for t in isi.values()) and aktif_benar)

    # 7 --------------------------------------------------------- bukan data dummy
    print("\n7. DATA NYATA (BUKAN DUMMY)")
    from app import library
    library.pastikan_dokumen_proyek()
    jumlah_pdf = len(library.daftar_dokumen())
    from app import schema_library
    jumlah_skema = len(schema_library.daftar_skema())
    kode_unik = {u['kode_unit'] for u in web_data.daftar_unit()}
    # Samakan dengan aturan aplikasi: folder preview/tmp bukan dokumen hasil.
    hasil_doc = [p for p in (project_root / 'output').rglob('*')
                 if p.is_file() and p.suffix.lower() in ('.docx', '.pdf')
                 and 'preview' not in p.parts and 'tmp' not in p.parts]
    cek('jumlah SKKNI = jumlah dokumen perpustakaan',
        data['stats']['dokumen_skkni'] == jumlah_pdf,
        f"{data['stats']['dokumen_skkni']} vs {jumlah_pdf}")
    cek('jumlah skema = dokumen perpustakaan skema',
        data['stats']['skema_sertifikasi'] == jumlah_skema,
        f"{data['stats']['skema_sertifikasi']} vs {jumlah_skema}")
    cek('jumlah unit = kode unik pada JSON', data['stats']['unit_kompetensi'] == len(kode_unik),
        f"{data['stats']['unit_kompetensi']} vs {len(kode_unik)}")
    cek('jumlah hasil = DOCX/PDF di output', data['stats']['hasil_ekstraksi'] == len(hasil_doc),
        f"{data['stats']['hasil_ekstraksi']} vs {len(hasil_doc)}")
    cek('setiap unit di halaman /unit berasal dari JSON nyata',
        all((project_root / u['berkas']).exists() for u in web_data.daftar_unit()))
    if data['aktivitas']:
        cek('aktivitas menunjuk berkas laporan nyata',
            all((project_root / a['berkas']).exists() for a in data['aktivitas']))

    print("\n8. MODUL EKSTRAKTOR LAMA")
    modul = ['app.extractor', 'app.unit_parser', 'app.section_parser',
             'app.docx_generator', 'app.multi_docx_generator',
             'app.schema_parser', 'app.unit_matcher', 'app.schema_pipeline']
    cek('delapan modul dapat diimpor', all(data['modul'].get(m) for m in modul),
        str([m for m in modul if not data['modul'].get(m)]))
    import importlib
    cek('modul inti punya fungsi utama',
        all(hasattr(importlib.import_module(m), f)
            for m, f in [('app.extractor', 'identify_units'),
                         ('app.unit_parser', 'parse_unit'),
                         ('app.schema_parser', 'baca_skema'),
                         ('app.unit_matcher', 'cocokkan'),
                         ('app.multi_docx_generator', 'generate_multi_docx')]))

    print("\n9. KEAMANAN LOKAL")
    cek('tidak ada header CORS longgar',
        'access-control-allow-origin' not in
        {k.lower() for k in client.get('/api/health').headers})
    cek('unggah tanpa token ditolak', client.post(
        '/skkni/upload', files={'berkas': ('a.pdf', b'%PDF-1.4')}).status_code == 403)
    cek('tidak ada unggah di halaman lain',
        client.post('/', files={'berkas': ('a.pdf', b'x')}).status_code == 405)
    cek('path traversal statis ditolak',
        client.get('/static/../app/main.py').status_code in (404, 400))
    cek('direktori proyek absolut', Path(web_data.ROOT).is_absolute())
    cek('tidak ada akses shell dari rute',
        not any('os.system' in (project_root / 'app' / f).read_text()
                for f in ('main.py', 'web_data.py')))

    # 10 ------------------------------------------------------------- regresi
    print("\n10. REGRESI FASE 1 - 3D")
    skrip = ['test_extractor.py', 'test_unit_parser.py', 'test_unit_complete.py',
             'test_unit_numbering.py', 'test_docx_generator.py', 'test_multi_docx.py',
             'test_schema_parser.py', 'test_unit_matcher.py']
    for nama in skrip:
        p = subprocess.run([sys.executable, str(project_root / 'tests' / nama)],
                           capture_output=True, text=True, cwd=str(project_root))
        akhir = (p.stdout + p.stderr).strip().splitlines()
        cek(f'{nama} lulus', p.returncode == 0, akhir[-1] if akhir and p.returncode else '')

    print("\n" + "=" * 100)
    print(f"HASIL: {len(lulus)} lulus, {len(gagal)} gagal")
    if gagal:
        for g in gagal:
            print(f"  - {g}")
    print("=" * 100)
    return 0 if not gagal else 1


if __name__ == '__main__':
    sys.exit(main())

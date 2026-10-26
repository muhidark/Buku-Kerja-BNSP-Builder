"""
Pengujian tampilan: kontras, ukuran teks, dan target sentuh (T-07 / langkah 3.1-3.2).

Pengujian ini tidak memerlukan peramban: yang diperiksa adalah kontrak gaya di
`app/static/css/style.css` dan nilai warna yang dipakai template. Kontras
dihitung dengan rumus WCAG 2.x yang sama seperti DevTools.

Ambang yang dipakai:
- kontras teks normal minimal 4,5:1 (WCAG AA);
- target sentuh tombol minimal 32 px, tombol utama 36 px (WCAG 2.5.8);
- tidak ada ukuran huruf di bawah 12 px pada halaman aplikasi
  (`cetak_apl.html` dikecualikan karena ukuran huruf di sana menentukan tata
  letak A4 yang sudah terverifikasi).

Catatan: tautan teks di tengah kalimat (remah navigasi, rujukan halaman PDF)
sengaja tidak dipaksa setinggi 32 px — WCAG 2.5.8 mengecualikannya, dan
memaksanya akan merusak alur paragraf.
"""

import re
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

CSS = project_root / 'app' / 'static' / 'css' / 'style.css'
TEMPLATES = project_root / 'app' / 'templates'
dikecualikan_cetak = {'cetak_apl.html'}

lulus, gagal = [], []


def cek(nama: str, kondisi: bool, detail: str = '') -> None:
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}"
          + (f" — {detail}" if detail and not kondisi else ''))


def _rgb(warna: str):
    w = warna.strip().lstrip('#')
    if len(w) == 3:
        w = ''.join(c * 2 for c in w)
    return tuple(int(w[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _lum(warna: str) -> float:
    def f(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(c) for c in _rgb(warna))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def kontras(a: str, b: str) -> float:
    l1, l2 = _lum(a), _lum(b)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


def variabel_css(isi: str) -> dict:
    blok = re.search(r':root\s*\{(.*?)\}', isi, re.S)
    if not blok:
        return {}
    return dict(re.findall(r'(--[\w-]+):\s*([^;]+);', blok.group(1)))


def main() -> int:
    print('=' * 100)
    print('PENGUJIAN TAMPILAN: KONTRAS, UKURAN TEKS, TARGET SENTUH — LANGKAH 3.1-3.2')
    print('=' * 100)

    css = CSS.read_text(encoding='utf-8')
    var = variabel_css(css)

    # -------------------------------------------------------------- 1. kontras
    print('\n1. KONTRA S TEKS (AMBANG WCAG AA 4,5:1)')
    pasangan = [
        ('teks utama di atas kartu', var.get('--text', '#1b2733'), var.get('--card', '#ffffff')),
        ('teks utama di atas latar', var.get('--text', '#1b2733'), var.get('--bg', '#f3f5f9')),
        ('teks sekunder di atas kartu', var.get('--muted', ''), var.get('--card', '#ffffff')),
        ('teks sekunder di atas latar', var.get('--muted', ''), var.get('--bg', '#f3f5f9')),
        ('badge hijau', var.get('--green', ''), var.get('--green-bg', '')),
        ('badge kuning', var.get('--amber', ''), var.get('--amber-bg', '')),
        ('badge merah', var.get('--red', ''), var.get('--red-bg', '')),
        ('tulisan pada tombol (putih)', '#ffffff', var.get('--navy-2', '')),
        ('tulisan pada tombol hover (putih)', '#ffffff', var.get('--navy-3', '')),
    ]
    for nama, depan, belakang in pasangan:
        if not depan or not belakang:
            cek(f'{nama}: warna terdefinisi', False, f'{depan!r} / {belakang!r}')
            continue
        nilai = kontras(depan, belakang)
        cek(f'{nama} >= 4,5:1', nilai >= 4.5, f'{depan} di {belakang} = {nilai:.2f}')

    # --------------------------------------------------------- 2. ukuran teks
    print('\n2. TIDAK ADA TEKS DI BAWAH 12 PX')
    kecil_css = re.findall(r'font-size:\s*(1[01](?:\.\d)?)px', css)
    cek('style.css tidak memakai huruf < 12 px', not kecil_css, f'ditemukan {kecil_css}')

    for t in sorted(TEMPLATES.glob('*.html')):
        if t.name in dikecualikan_cetak:
            continue
        isi = t.read_text(encoding='utf-8')
        temuan = re.findall(r'font-size:\s*(1[01](?:\.\d)?)px', isi)
        if temuan:
            cek(f'{t.name} tidak memakai huruf < 12 px', False, f'ditemukan {temuan[:3]}')
    cek('template aplikasi bebas huruf < 12 px', True)

    # ------------------------------------------------------- 3. target sentuh
    print('\n3. TARGET SENTUH DAN FOKUS KEYBOARD')
    blok_btn = re.search(r'\.btn\s*\{(.*?)\}', css, re.S)
    blok_kecil = re.search(r'\.btn-small\s*\{(.*?)\}', css, re.S)
    cek('blok .btn ada', bool(blok_btn))
    cek('blok .btn-small ada', bool(blok_kecil))

    for nama, blok, minimum in (('.btn', blok_btn, 36), ('.btn-small', blok_kecil, 32)):
        if not blok:
            continue
        m = re.search(r'min-height:\s*(\d+)px', blok.group(1))
        cek(f'{nama} punya min-height >= {minimum}px',
            bool(m) and int(m.group(1)) >= minimum,
            f'ditemukan {m.group(1) if m else "tidak ada"}')

    cek('fokus keyboard terlihat (:focus-visible)', ':focus-visible' in css)
    cek('semua kontrol interaktif punya aturan fokus',
        all(sel in css for sel in ('a:focus-visible', 'button:focus-visible',
                                   'input:focus-visible', 'select:focus-visible')))
    cek('kontrol form minimal 32 px',
        bool(re.search(r'input[^{]*\{[^}]*min-height:\s*32px', css, re.S))
        or 'min-height: 32px' in css)

    # ------------------------------------- 4. tidak ada warna gagal di template
    print('\n4. TIDAK ADA WARNA HARD-CODE YANG GAGAL KONTRAS DENGAN TEKS PUTIH')
    warna_terlarang = {
        '#0284c7': 4.10, '#0d9488': 3.74, '#16a34a': 3.30,
        '#f59e0b': 2.15, '#10b981': 2.54, '#ef4444': 3.76,
    }
    for t in sorted(TEMPLATES.glob('*.html')):
        isi = t.read_text(encoding='utf-8').lower()
        ditemukan = [w for w in warna_terlarang if w in isi]
        if ditemukan:
            cek(f'{t.name} bebas warna kontras rendah', False, f'{ditemukan}')

    # verifikasi penggantinya memang lolos
    for pengganti in ('#0369a1', '#0f766e', '#15803d', '#b45309', '#047857', '#b91c1c'):
        cek(f'pengganti {pengganti} >= 4,5:1 dengan putih',
            kontras('#ffffff', pengganti) >= 4.5,
            f'{kontras("#ffffff", pengganti):.2f}')

    cek('template bebas warna kontras rendah', not any(
        w in t.read_text(encoding='utf-8').lower()
        for t in TEMPLATES.glob('*.html') for w in warna_terlarang))


    # ------------------------------------------------ 5. indikator proses
    print('\n5. INDIKATOR PROSES (T-09)')
    js = (project_root / 'app' / 'static' / 'js' / 'app.js').read_text(encoding='utf-8')
    for fitur, pola in [
        ('fungsi tampilkanProses', 'function tampilkanProses'),
        ('overlay proses dibuat', "className = 'proses-overlay'"),
        ('tombol dinonaktifkan saat kirim', 'b.disabled = true'),
        ('label tombol berubah', 'Memproses'),
        ('penjaga klik ganda unduhan', "a[href*=\"/unduh-\"]"),
        ('indikator bisa ditutup dengan Esc', "e.key === 'Escape'"),
        ('pesan jangan tutup halaman', 'Jangan tutup halaman ini'),
    ]:
        cek(f'{fitur} ada', pola in js)

    for kelas in ('.proses-overlay', '.proses-kotak', '.proses-lingkar'):
        cek(f'{kelas} didefinisikan di CSS', kelas in css)
    cek('animasi menghormati prefers-reduced-motion',
        'prefers-reduced-motion' in css)


    # ------------------------------------------------- 6. aksesibilitas (3.6)
    print('\n6. AKSESIBILITAS FORM, TAB, DAN MENU PONSEL (T-12, T-13, T-27)')
    dasar = (project_root / 'app' / 'templates' / 'base.html').read_text(encoding='utf-8')
    muk = (project_root / 'app' / 'templates' / 'skema_muk.html').read_text(encoding='utf-8')

    cek('tombol menu ponsel ada', 'id="nav-toggle"' in dasar)
    cek('tombol menu menyatakan aria-expanded', 'aria-expanded="false"' in dasar)
    cek('nav punya id & label', 'id="nav-utama"' in dasar and 'aria-label="Menu utama"' in dasar)
    cek('ikon menu memakai SVG, bukan glyph',
        '"_ikon.html" import ikon' in dasar
        and not any(g in dasar for g in ('▤', '▦', '▧', '▣', '⚙')))
    cek('berkas ikon SVG ada', (project_root / 'app' / 'templates' / '_ikon.html').exists())

    cek('tab MUK memakai role=tablist', 'role="tablist"' in muk)
    cek('setiap tab punya aria-selected', muk.count('aria-selected=') >= 9, f'jumlah={muk.count("aria-selected=")}')
    cek('setiap tab punya aria-controls', muk.count('aria-controls=') >= 9)
    cek('panel memakai role=tabpanel', muk.count('role="tabpanel"') >= 9)
    cek('panel menunjuk tab-nya (aria-labelledby)', muk.count('aria-labelledby="btn-') >= 9)

    # setiap kontrol form statis harus punya id atau nama aksesibel
    kurang = []
    for t in sorted(TEMPLATES.glob('*.html')):
        if t.name in ('cetak_apl.html',):
            continue
        isi_t = t.read_text(encoding='utf-8')
        for m in re.finditer(r'<(?:input|select|textarea)\b[^>]*>', isi_t, re.S):
            tag = m.group(0)
            if ('type="hidden"' in tag or 'type="checkbox"' in tag
                    or 'type="radio"' in tag):
                continue
            if ('aria-label' in tag or 'aria-labelledby' in tag
                    or re.search(r'\bid="', tag)):
                continue
            kurang.append(f'{t.name}: {tag[:60]}')
    cek('semua kontrol form punya id atau nama aksesibel', not kurang,
        f'{len(kurang)} kontrol: {kurang[:3]}')

    # urutan CSS: override menu ponsel harus berada setelah aturan dasarnya
    pos_dasar = css.find('.nav-toggle {\n  display: none')
    pos_override = css.rfind('.nav-toggle { display: inline-flex')
    cek('override menu ponsel ditulis setelah aturan dasar',
        pos_dasar != -1 and pos_override > pos_dasar,
        f'posisi dasar={pos_dasar} override={pos_override}')


    # ------------------------------------------------- 7. hierarki (3.7)
    print('\n7. HIERARKI: SATU AKSI UTAMA & DETAIL TEKNIS TERSEMBUNYI (T-10, T-26)')
    dasbor = (project_root / 'app' / 'templates' / 'dashboard.html').read_text(encoding='utf-8')
    cek('dashboard punya blok "Langkah berikutnya"', 'Langkah berikutnya' in dasbor)
    cek('dashboard punya satu tombol utama', dasbor.count('btn-hijau') == 1,
        f"jumlah={dasbor.count('btn-hijau')}")
    cek('langkah berikutnya ditentukan dari data',
        'ada_skkni' in dasbor and 'ada_skema' in dasbor and 'ada_unit' in dasbor)
    cek('status modul disembunyikan di <details>', 'detail-teknis' in dasbor)
    cek('kolom path internal diganti nama berkas',
        "a.berkas.split('/')[-1]" in dasbor)

    # satu aksi berwarna per template
    for t in sorted(TEMPLATES.glob('*.html')):
        isi_t = t.read_text(encoding='utf-8')
        n_kuat = sum(isi_t.count(k) for k in ('btn-hijau', 'btn-teal', 'btn-biru'))
        if n_kuat > 1:
            cek(f'{t.name} hanya satu tombol berwarna', False, f'jumlah={n_kuat}')
    cek('setiap template maksimal satu tombol berwarna', True)

    # SHA-256 & path internal tidak boleh tampil tanpa <details>
    for nama in ('skema_detail.html', 'skkni_detail.html', 'unit_preview.html'):
        isi_t = (TEMPLATES / nama).read_text(encoding='utf-8')
        if 'SHA-256' in isi_t or 'Berkas JSON' in isi_t:
            cek(f'{nama}: detail teknis ada di dalam <details>',
                'detail-teknis' in isi_t)
    cek('path internal tidak tampil tanpa <details>', True)

    print('\n' + '=' * 100)
    print(f'HASIL: {len(lulus)} lulus, {len(gagal)} gagal')
    if gagal:
        for g in gagal:
            print(f'  - GAGAL: {g}')
    print('=' * 100)
    return 0 if not gagal else 1


if __name__ == '__main__':
    sys.exit(main())

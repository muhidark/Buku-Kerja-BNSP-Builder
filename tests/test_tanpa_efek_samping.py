"""
Pengujian bahwa GET tidak mengubah data (perbaikan T-25 / langkah 4.4).

Sebelum perbaikan, membuka `/skkni` menjalankan identifikasi untuk setiap PDF
dan membuka `/skkni/{id}` menjalankan validasi kelengkapan — keduanya menulis
berkas metadata. Akibatnya "uji baca saja" tetap mengubah data dan waktu buka
halaman tumbuh linear dengan jumlah dokumen (T-17).

Pengujian memakai SALINAN metadata di direktori sementara, dengan satu dokumen
yang sengaja dibuat "belum diidentifikasi" dan "belum divalidasi" — justru
kondisi yang dulu memicu penulisan.
"""

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app import library
from app.main import app
from tests.dukungan import klien

lulus, gagal = [], []


def cek(nama: str, kondisi: bool, detail: str = '') -> None:
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}"
          + (f" — {detail}" if detail and not kondisi else ''))


def sidik(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    print('=' * 100)
    print('PENGUJIAN GET TIDAK MENGUBAH DATA — LANGKAH 4.4 (T-25)')
    print('=' * 100)

    asli = sorted(library.META_DIR.glob('*.json'))
    if not asli:
        print('ERROR: tidak ada metadata dokumen untuk diuji.')
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        meta_uji = tmpdir / 'documents'
        meta_uji.mkdir()
        # salin metadata, lalu buat satu dokumen "belum diproses"
        target = None
        for sumber in asli:
            isi = json.loads(sumber.read_text(encoding='utf-8'))
            tujuan = meta_uji / sumber.name
            tujuan.write_text(json.dumps(isi, ensure_ascii=False, indent=2), encoding='utf-8')
            if target is None:
                isi.pop('units', None)
                isi.pop('validasi_kelengkapan', None)
                isi['status_identifikasi'] = 'belum_diproses'
                isi['jumlah_unit'] = 0
                tujuan.write_text(json.dumps(isi, ensure_ascii=False, indent=2), encoding='utf-8')
                target = isi['id']

        simpan_asli = library.META_DIR
        library.META_DIR = meta_uji
        try:
            # -------------------------------------------------- 1. berkas utuh
            print('\n1. MEMBUKA HALAMAN TIDAK MENGUBAH BERKAS METADATA')
            sebelum = {p.name: sidik(p) for p in meta_uji.glob('*.json')}
            mtime_sebelum = {p.name: p.stat().st_mtime_ns for p in meta_uji.glob('*.json')}

            c = klien(app, 'admin')
            for _ in range(3):
                cek_halaman = c.get('/skkni')
                cek('/skkni dibalas 200', cek_halaman.status_code == 200,
                    f'status={cek_halaman.status_code}')
                r = c.get(f'/skkni/{target}')
                cek(f'/skkni/{{id}} dibalas 200', r.status_code == 200, f'status={r.status_code}')

            sesudah = {p.name: sidik(p) for p in meta_uji.glob('*.json')}
            mtime_sesudah = {p.name: p.stat().st_mtime_ns for p in meta_uji.glob('*.json')}

            cek('isi metadata tidak berubah', sebelum == sesudah,
                'ada berkas yang berubah setelah halaman dibuka')
            cek('waktu ubah berkas tidak berubah', mtime_sebelum == mtime_sesudah,
                'mtime berubah -> masih ada penulisan saat GET')

            dok = library.ambil_dokumen(target)
            cek('dokumen uji tetap "belum_diproses"',
                (dok or {}).get('status_identifikasi') == 'belum_diproses',
                f"status={(dok or {}).get('status_identifikasi')!r}")
            cek('belum ada hasil validasi tersimpan',
                not (dok or {}).get('validasi_kelengkapan'))

            # ------------------------------------- 2. halaman menawarkan aksi
            print('\n2. HALAMAN MENAWARKAN TINDAKAN EKSPLISIT, BUKAN MENULIS DIAM-DIAM')
            isi = c.get(f'/skkni/{target}').text
            cek('tombol identifikasi ditampilkan', 'Identifikasi unit sekarang' in isi)
            cek('form mengarah ke endpoint POST', f'/skkni/{target}/identifikasi' in isi)

            # --------------------------------------- 3. aksi eksplisit menulis
            print('\n3. AKSI EKSPLISIT (POST) BOLEH MENULIS')
            import re
            cocok = re.search(r'name="csrf_token" value="([^"]+)"', isi)
            csrf = cocok.group(1) if cocok else ''
            r = c.post(f'/skkni/{target}/identifikasi', data={'csrf_token': csrf},
                       follow_redirects=False)
            cek('POST identifikasi diterima (303)', r.status_code == 303, f'status={r.status_code}')
            sesudah_aksi = {p.name: sidik(p) for p in meta_uji.glob('*.json')}
            cek('aksi eksplisit memang mengubah metadata', sesudah_aksi != sesudah,
                'tidak ada perubahan setelah POST identifikasi')
        finally:
            library.META_DIR = simpan_asli
            print('\n[direktori metadata dipulihkan]')

    print('\n' + '=' * 100)
    print(f'HASIL: {len(lulus)} lulus, {len(gagal)} gagal')
    if gagal:
        for g in gagal:
            print(f'  - GAGAL: {g}')
    print('=' * 100)
    return 0 if not gagal else 1




def test_tanpa_efek_samping():
    assert main() == 0


if __name__ == '__main__':
    sys.exit(main())

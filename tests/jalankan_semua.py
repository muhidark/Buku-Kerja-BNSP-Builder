"""Menjalankan SELURUH berkas test sekaligus (menutup temuan T-05).

Aplikasi ini menyimpan test sebagai skrip biasa, bukan kelas unittest/pytest,
sehingga `python -m unittest` hanya menemukan sebagian kecil berkas. Skrip ini
menjalankan setiap tests/test_*.py sebagai proses terpisah, mencatat keluarannya,
lalu meringkas lulus/gagal.

Pemakaian:
    .venv/bin/python tests/jalankan_semua.py            # semua berkas
    .venv/bin/python tests/jalankan_semua.py -v         # tampilkan keluaran yang gagal
    .venv/bin/python tests/jalankan_semua.py koreksi    # hanya berkas yang namanya cocok
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / 'tests'
BATAS_DETIK = 900


def daftar_berkas(penyaring: str = '') -> list[Path]:
    berkas = sorted(p for p in TESTS.glob('test_*.py') if p.is_file())
    if penyaring:
        berkas = [p for p in berkas if penyaring.lower() in p.name.lower()]
    return berkas


def jalankan(path: Path) -> tuple[bool, float, str]:
    env = dict(os.environ)
    env['PYTHONPATH'] = str(ROOT)
    env.setdefault('PYTHONIOENCODING', 'utf-8')
    mulai = time.monotonic()
    try:
        hasil = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=BATAS_DETIK,
        )
    except subprocess.TimeoutExpired:
        return False, time.monotonic() - mulai, f'MELEWATI BATAS WAKTU {BATAS_DETIK} detik'
    durasi = time.monotonic() - mulai
    keluaran = (hasil.stdout or '') + (hasil.stderr or '')
    lulus = hasil.returncode == 0
    # Skrip lama tidak selalu memakai exit code untuk menandai kegagalan, jadi
    # baca juga ringkasan bawaannya: "HASIL: <n> lulus, <m> gagal".
    ringkasan = re.findall(r'HASIL:\s*(\d+)\s*lulus,\s*(\d+)\s*gagal', keluaran)
    if ringkasan:
        total_lulus, total_gagal = ringkasan[-1]
        if int(total_gagal) > 0 or int(total_lulus) == 0:
            lulus = False
    elif hasil.returncode == 0 and 'Traceback (most recent call last)' in keluaran:
        lulus = False
    return lulus, durasi, keluaran


def main(argv: list[str]) -> int:
    verbose = '-v' in argv or '--verbose' in argv
    penyaring = next((a for a in argv[1:] if not a.startswith('-')), '')

    berkas = daftar_berkas(penyaring)
    if not berkas:
        print(f'Tidak ada berkas test yang cocok dengan penyaring {penyaring!r}.')
        return 2

    print(f'Menjalankan {len(berkas)} berkas test dari {TESTS}\n')
    gagal: list[tuple[str, str]] = []
    lulus_total = 0
    mulai_semua = time.monotonic()

    for path in berkas:
        lulus, durasi, keluaran = jalankan(path)
        tanda = 'LULUS' if lulus else 'GAGAL'
        print(f'  [{tanda}] {path.name:<38} {durasi:6.1f} s')
        if lulus:
            lulus_total += 1
        else:
            gagal.append((path.name, keluaran))

    total_durasi = time.monotonic() - mulai_semua
    print(f'\nRingkasan: {lulus_total}/{len(berkas)} berkas lulus '
          f'dalam {total_durasi:.1f} detik')

    if gagal:
        print(f'\n{len(gagal)} berkas gagal:')
        for nama, _ in gagal:
            print(f'  - {nama}')
        if verbose:
            for nama, keluaran in gagal:
                print(f'\n{"=" * 70}\n{nama}\n{"=" * 70}')
                baris = keluaran.strip().splitlines()
                print('\n'.join(baris[-40:]))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

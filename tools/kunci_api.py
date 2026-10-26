"""
Pengelolaan kunci API dari terminal (bootstrap & pemeliharaan).

Kunci API tidak lagi dibuat otomatis saat aplikasi pertama dijalankan dan
tidak dicetak di dokumentasi. Kunci dibuat lewat perintah ini, atau lewat
endpoint admin `POST /api/v1/keys` bila sudah punya kunci admin.

Pemakaian:
    .venv/bin/python -m tools.kunci_api daftar
    .venv/bin/python -m tools.kunci_api buat --nama "WordPress LSP" --peran klien
    .venv/bin/python -m tools.kunci_api cabut 3
    .venv/bin/python -m tools.kunci_api aktifkan 3

Nilai kunci lengkap hanya ditampilkan SEKALI saat dibuat. Salin ke pengelola
kata sandi atau konfigurasi klien; setelah itu yang tersimpan hanya hash-nya.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db


def perintah_daftar(_: argparse.Namespace) -> int:
    baris = db.daftar_kunci_api()
    if not baris:
        print('Belum ada kunci API terdaftar.')
        return 0
    print(f"{'ID':<5} {'PREFIX':<16} {'PERAN':<8} {'AKTIF':<6} {'KLIEN'}")
    print('-' * 78)
    for b in baris:
        prefix = b.get('prefix') or (b.get('kunci') or '')[:12] or '-'
        print(f"{b['id']:<5} {prefix:<16} {b['peran']:<8} "
              f"{'ya' if b['aktif'] else 'tidak':<6} {b['nama_klien']}")
    return 0


def perintah_buat(args: argparse.Namespace) -> int:
    kunci = db.buat_kunci_api(
        nama_klien=args.nama,
        peran=args.peran,
        kunci_khusus=args.kunci,
    )
    print('\nKunci API dibuat. Nilai ini HANYA ditampilkan sekali:\n')
    print(f'  {kunci}\n')
    print(f"  klien : {args.nama}")
    print(f"  peran : {args.peran}\n")
    print('Simpan sekarang. Setelah ini yang tersimpan hanya hash-nya.')
    return 0


def _ubah_status(args: argparse.Namespace, aktif: bool) -> int:
    ok = db.ubah_status_kunci_api_id(args.id, aktif)
    if not ok:
        print(f'Kunci API dengan id {args.id} tidak ditemukan.', file=sys.stderr)
        return 1
    print(f"Kunci API id {args.id} {'diaktifkan' if aktif else 'dicabut'}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='python -m tools.kunci_api',
        description='Membuat, mencabut, dan mendaftar kunci API eksternal.',
    )
    sub = parser.add_subparsers(dest='perintah', required=True)

    p_daftar = sub.add_parser('daftar', help='Menampilkan seluruh kunci terdaftar')
    p_daftar.set_defaults(fungsi=perintah_daftar)

    p_buat = sub.add_parser('buat', help='Membuat kunci API baru')
    p_buat.add_argument('--nama', required=True, help='Nama klien (mis. "WordPress LSP")')
    p_buat.add_argument('--peran', default='klien', choices=['klien', 'admin'])
    p_buat.add_argument('--kunci', default=None,
                        help='Nilai kunci tetap (opsional; kosongkan agar dibuat acak)')
    p_buat.set_defaults(fungsi=perintah_buat)

    p_cabut = sub.add_parser('cabut', help='Menonaktifkan kunci API berdasarkan id')
    p_cabut.add_argument('id', type=int)
    p_cabut.set_defaults(fungsi=lambda a: _ubah_status(a, False))

    p_aktif = sub.add_parser('aktifkan', help='Mengaktifkan kembali kunci API berdasarkan id')
    p_aktif.add_argument('id', type=int)
    p_aktif.set_defaults(fungsi=lambda a: _ubah_status(a, True))

    args = parser.parse_args(argv)
    db.inisialisasi_db()
    return args.fungsi(args)


if __name__ == '__main__':
    sys.exit(main())

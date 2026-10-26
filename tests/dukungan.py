"""Bantuan bersama untuk berkas test: klien HTTP yang sudah punya sesi login.

Sejak langkah 1.2 (perbaikan T-01) seluruh endpoint POST yang mengubah data
mewajibkan sesi. Test lama memanggil POST tanpa sesi, sehingga perlu klien yang
sudah masuk. Berkas ini menyediakan:

    from tests.dukungan import klien
    client = klien(app, 'admin')   # atau 'asesor'

Pengguna uji dibuat sekali dengan nama tetap ('uji_admin', 'uji_asesor') agar
tidak menumpuk di data/app.db setiap kali test dijalankan. Kata sandinya acak
karena test tidak perlu mengetahuinya — sesi dibuat langsung lewat db.buat_sesi.

Catatan: ini masih menulis ke data/app.db milik aplikasi (temuan T-14). Basis
data terpisah untuk test dikerjakan pada langkah 5.1.
"""

from __future__ import annotations

import secrets
from typing import Any, Dict, Optional, Tuple

from fastapi.testclient import TestClient

from app import db

NAMA_UJI = {
    'admin': 'uji_admin',
    'asesor': 'uji_asesor',
}


def pastikan_pengguna(peran: str = 'admin') -> Dict[str, Any]:
    """Mengembalikan baris pengguna uji untuk peran tersebut, membuat bila perlu."""
    username = NAMA_UJI.get(peran)
    if not username:
        raise ValueError(f'Peran uji tidak dikenal: {peran!r}')

    for baris in db.daftar_pengguna():
        if baris['username'] == username:
            return baris

    db.tambah_pengguna(
        username=username,
        kata_sandi=secrets.token_urlsafe(24),
        nama_lengkap=f'Pengguna Uji {peran.title()}',
        peran=peran,
        email=f'{username}@uji.local',
    )
    for baris in db.daftar_pengguna():
        if baris['username'] == username:
            return baris
    raise RuntimeError(f'Gagal membuat pengguna uji {username}.')


def sesi_uji(peran: str = 'admin') -> Tuple[str, Dict[str, Any]]:
    """Membuat satu sesi baru untuk pengguna uji (sesi lama dibersihkan dulu)."""
    pengguna = pastikan_pengguna(peran)
    db.hapus_semua_sesi_pengguna(pengguna['id'])
    token = db.buat_sesi(pengguna['id'], durasi_detik=3600)
    return token, pengguna


def klien(app: Any, peran: Optional[str] = 'admin') -> TestClient:
    """TestClient yang sudah membawa cookie sesi untuk peran tertentu.

    `peran=None` menghasilkan klien tamu (tanpa sesi) untuk menguji penolakan.
    """
    client = TestClient(app)
    if peran:
        token, _ = sesi_uji(peran)
        client.cookies.set('skkni_session', token)
    return client


def klien_tamu(app: Any) -> TestClient:
    """TestClient tanpa sesi (pengguna belum masuk)."""
    return klien(app, peran=None)

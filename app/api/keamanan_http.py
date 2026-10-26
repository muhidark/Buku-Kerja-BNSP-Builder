"""Pengerasan HTTP: header keamanan, batas percobaan login, dan mode produksi.

Menutup temuan T-21 (belum ada batas percobaan login) dan T-22 (tanpa header
keamanan; /docs & /openapi.json selalu terbuka).

Catatan jujur tentang batas kemampuan:
- Penghitung gagal login disimpan di memori proses. Aplikasi ini dijalankan
  sebagai satu proses uvicorn (run.sh), jadi ini cukup. Bila nanti dijalankan
  dengan beberapa worker, penghitung menjadi per-worker — pindahkan ke SQLite
  atau Redis saat itu terjadi.
- CSP memasang 'unsafe-inline' untuk gaya dan skrip karena template masih
  memuat keduanya secara inline. Artinya CSP di sini mencegah pemuatan kode
  dari domain luar, bukan injeksi inline. Setelah gaya inline dipindahkan ke
  kelas CSS (langkah 3.3), 'unsafe-inline' dapat dicabut.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Dict, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

#: Mode aplikasi: 'lokal' (default) atau 'produksi'.
APP_ENV = os.environ.get('APP_ENV', 'lokal').strip().lower()
PRODUKSI = APP_ENV in ('produksi', 'production', 'prod')

KEBIAKAN_CSP = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'"
)

HEADER_KEAMANAN = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'same-origin',
    'Content-Security-Policy': KEBIAKAN_CSP,
}


class HeaderKeamanan(BaseHTTPMiddleware):
    """Menambahkan header keamanan pada setiap respons."""

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        respons = await call_next(request)
        for nama, nilai in HEADER_KEAMANAN.items():
            # Jangan menimpa header yang sudah disetel secara khusus.
            if nama not in respons.headers:
                respons.headers[nama] = nilai
        return respons


class PembatasLogin:
    """Membatasi percobaan login gagal per (IP, username).

    Setelah MAKS_GAGAL kegagalan, pasangan itu diblokir selama JEDA_DETIK.
    Login berhasil menghapus catatan. Memori dibersihkan berkala agar tidak
    tumbuh tanpa batas.
    """

    MAKS_GAGAL = 5
    JEDA_DETIK = 60
    UMUR_CATATAN = 3600

    def __init__(self) -> None:
        self._kunci: Dict[Tuple[str, str], list] = {}
        self._lock = threading.Lock()
        self._terakhir_bersih = time.monotonic()

    @staticmethod
    def _kunci_entri(ip: str, username: str) -> Tuple[str, str]:
        return (ip or '-', (username or '').strip().lower())

    def sisa_blokir(self, ip: str, username: str) -> int:
        """Sisa detik blokir (0 bila tidak diblokir)."""
        kunci = self._kunci_entri(ip, username)
        with self._lock:
            data = self._kunci.get(kunci)
            if not data:
                return 0
            blokir_sampai = data[2]
            sisa = int(blokir_sampai - time.monotonic())
            return max(0, sisa)

    def catat_gagal(self, ip: str, username: str) -> int:
        """Mencatat satu kegagalan; mengembalikan sisa blokir setelah dicatat."""
        kunci = self._kunci_entri(ip, username)
        with self._lock:
            self._bersihkan_bila_perlu()
            data = self._kunci.setdefault(kunci, [0, time.monotonic(), 0.0])
            data[0] += 1
            if data[0] >= self.MAKS_GAGAL:
                data[2] = time.monotonic() + self.JEDA_DETIK
                # Setelah blokir berakhir, hitungan dimulai dari nol lagi.
                data[0] = 0
                return self.JEDA_DETIK
            return 0

    def bersihkan(self, ip: str, username: str) -> None:
        """Menghapus catatan kegagalan setelah login berhasil."""
        with self._lock:
            self._kunci.pop(self._kunci_entri(ip, username), None)

    def _bersihkan_bila_perlu(self) -> None:
        sekarang = time.monotonic()
        if sekarang - self._terakhir_bersih < 60:
            return
        self._terakhir_bersih = sekarang
        kedaluwarsa = [k for k, v in self._kunci.items()
                       if v[2] < sekarang and (sekarang - v[1]) > self.UMUR_CATATAN]
        for k in kedaluwarsa:
            self._kunci.pop(k, None)


#: Instance tunggal yang dipakai route login.
pembatas_login = PembatasLogin()


def ip_klien(request: Request) -> str:
    """Alamat IP klien untuk penghitung login.

    X-Forwarded-For sengaja TIDAK dipercaya: aplikasi berjalan langsung di
    127.0.0.1 tanpa reverse proxy, sehingga header itu hanya bisa dipalsukan
    untuk menghindari batas percobaan.
    """
    return request.client.host if request.client else '-'

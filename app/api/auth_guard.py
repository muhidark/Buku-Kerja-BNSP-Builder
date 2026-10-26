"""Penjaga akses tunggal untuk semua aksi yang mengubah data.

Sebelum modul ini ada (temuan T-01), dari 13 endpoint POST hanya
`/skkni/{doc_id}/regulasi` yang memeriksa peran. Unggah SKKNI, unggah skema,
simpan MUK, ekstrak unit, koreksi unit, dan buat dokumen semuanya menerima
perubahan tanpa sesi sama sekali.

Kontrak:
- Permintaan halaman HTML tanpa sesi  -> 303 ke /login?next=<path>
- Permintaan /api tanpa sesi          -> 403 JSON
- Peran tidak berwenang               -> 403
- Halaman baca (GET) tidak dijaga di sini; penguncian baca menyeluruh adalah
  tahap tersendiri (mode read-only publik + login admin).

Kewenangan yang dipakai aplikasi:
- admin  : unggah SKKNI, unggah skema, kurasi status regulasi, koreksi unit.
- asesor : susun MUK, ekstrak, verifikasi manual, cetak & buat dokumen.
- Hanya perlu login (tanpa syarat peran): ekstrak, periksa-ulang, MUK, generate.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, NoReturn, Optional
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app import db

NAMA_COOKIE_SESI = 'skkni_session'

PERAN_ADMIN = 'admin'
PERAN_ASESOR = 'asesor'


class PerluLogin(Exception):
    """Permintaan halaman HTML datang tanpa sesi yang sah."""

    def __init__(self, path: str = '/') -> None:
        self.path = path
        super().__init__(f'Sesi tidak ditemukan untuk {path}.')


def pengguna_dari_request(request: Request) -> Optional[Dict[str, Any]]:
    """Mengembalikan pengguna aktif dari cookie sesi, atau None."""
    token = request.cookies.get(NAMA_COOKIE_SESI, '')
    if not token:
        return None
    return db.ambil_pengguna_dari_sesi(token)


def _tolak(request: Request, pesan: str) -> NoReturn:
    """Menolak permintaan: JSON 403 untuk /api, redirect login untuk halaman."""
    if request.url.path.startswith('/api/'):
        raise HTTPException(status_code=403, detail=pesan)
    raise PerluLogin(request.url.path)


def wajib_login(peran: Optional[str] = None) -> Callable[..., Dict[str, Any]]:
    """Dependency FastAPI: wajib sesi sah, opsional wajib peran tertentu.

    Pemakaian:
        @app.post('/skema/{schema_id}/muk')
        def simpan_muk_skema(..., pengguna=Depends(wajib_login())): ...

        @app.post('/skkni/upload')
        async def unggah_skkni(..., pengguna=Depends(wajib_login(PERAN_ADMIN))): ...
    """

    def _cek(request: Request) -> Dict[str, Any]:
        pengguna = pengguna_dari_request(request)
        if not pengguna:
            _tolak(request, 'Sesi tidak ditemukan atau sudah berakhir. Silakan masuk.')
        if peran and pengguna.get('peran') != peran:
            if request.url.path.startswith('/api/'):
                raise HTTPException(
                    status_code=403,
                    detail='Peran tidak berwenang untuk tindakan ini.',
                )
            raise HTTPException(
                status_code=403,
                detail=(
                    'Tindakan ini hanya untuk peran '
                    f'{peran}. Anda masuk sebagai {pengguna.get("peran")}.'
                ),
            )
        return pengguna

    return _cek


def tujuan_aman(nilai: Optional[str], bawaan: str = '/') -> str:
    """Menyaring parameter `next` agar tidak menjadi open redirect.

    Hanya menerima path lokal: diawali '/', bukan '//' (protokol-relative),
    tanpa skema 'http://', dan tanpa backslash.
    """
    if not nilai:
        return bawaan
    calon = nilai.strip()
    if not calon.startswith('/') or calon.startswith('//'):
        return bawaan
    if '\\' in calon or '://' in calon or calon.startswith('/\\'):
        return bawaan
    return calon[:500]


def pasang_penanganan_galat(app: Any) -> None:
    """Mendaftarkan penanganan PerluLogin pada instance FastAPI."""

    @app.exception_handler(PerluLogin)
    async def _perlu_login(request: Request, exc: PerluLogin):  # noqa: ANN202
        if request.url.path.startswith('/api/'):
            return JSONResponse(
                {'detail': 'Sesi tidak ditemukan atau sudah berakhir.'},
                status_code=403,
            )
        tujuan = quote(str(exc.path or request.url.path), safe='/')
        return RedirectResponse(url=f'/login?next={tujuan}', status_code=303)

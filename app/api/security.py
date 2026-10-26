"""Perlindungan CSRF sederhana untuk operasi unggah (Fase 4B).

Pola double-submit cookie: token dikirim sebagai cookie HttpOnly + SameSite=Lax
dan sebagai field tersembunyi pada form. Permintaan lintas situs tidak membawa
cookie tersebut, sehingga token tidak dapat dipalsukan.
"""

import hmac
import secrets

from fastapi import HTTPException, Request
from fastapi.responses import Response

NAMA_COOKIE = 'skkni_csrf'
PANJANG_MIN = 20


def token_dari_cookie(request: Request) -> str:
    token = request.cookies.get(NAMA_COOKIE)
    if token and len(token) >= PANJANG_MIN:
        return token
    return secrets.token_urlsafe(32)


def set_cookie_token(response: Response, token: str) -> None:
    response.set_cookie(
        NAMA_COOKIE, token,
        httponly=True, samesite='lax', path='/', max_age=60 * 60 * 8,
    )


def periksa_token(request: Request, token_form: str | None) -> None:
    """Tolak permintaan bila token form tidak sama dengan cookie."""
    asli = request.cookies.get(NAMA_COOKIE) or ''
    if not asli or not token_form:
        raise HTTPException(status_code=403, detail='Token keamanan tidak ditemukan.')
    if not hmac.compare_digest(asli, token_form):
        raise HTTPException(status_code=403, detail='Token keamanan tidak sah.')

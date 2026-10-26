"""Perkakas bersama untuk halaman HTML: template, render, dan gerbang dokumen.

Dipisahkan dari `main.py` (temuan T-19) karena dipakai oleh beberapa modul rute.
Sebelumnya blok penolakan gerbang 409 disalin di empat tempat; sekarang hanya
ada satu fungsi, `cek_gerbang()`, sehingga perubahannya cukup di satu titik.
"""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import db, status_units
from app.api import security
from app.paths import TEMPLATE_DIR
from app.version import __version__

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

VERSI = __version__

#: Menu utama. `ikon` adalah nama ikon SVG di app/templates/_ikon.html.
HALAMAN = [
    {'path': '/', 'label': 'Dashboard', 'ikon': 'dashboard'},
    {'path': '/skkni', 'label': 'Dokumen SKKNI', 'ikon': 'dokumen'},
    {'path': '/skema', 'label': 'Skema Sertifikasi', 'ikon': 'skema'},
    {'path': '/unit', 'label': 'Unit Kompetensi', 'ikon': 'unit'},
    {'path': '/ekstraksi', 'label': 'Ekstraksi', 'ikon': 'ekstraksi'},
    {'path': '/hasil', 'label': 'Hasil Ekstraksi', 'ikon': 'hasil'},
]


def render(request: Request, template: str, **konteks: Any) -> HTMLResponse:
    """Render template dengan konteks navigasi standar dan pengguna sesi."""
    token_sesi = request.cookies.get('skkni_session', '')
    pengguna = db.ambil_pengguna_dari_sesi(token_sesi)
    konteks.setdefault('pengguna_aktif', pengguna)
    konteks.setdefault('csrf_token', security.token_dari_cookie(request))
    konteks.setdefault('halaman', HALAMAN)
    konteks.setdefault('versi', VERSI)
    path = request.url.path
    konteks.setdefault('aktif', '/skkni' if path.startswith('/skkni') else path)
    return templates.TemplateResponse(request, template, konteks)


def halaman_tidak_ditemukan(request: Request, judul: str, pesan: str,
                            status: int = 404) -> HTMLResponse:
    html = render(request, 'tidak_ditemukan.html', judul=judul, pesan=pesan)
    html.status_code = status
    return html


def redirect_daftar(dasar: str, pesan: str = '', tipe: str = '',
                    doc_id: str = '') -> RedirectResponse:
    params = []
    if pesan:
        params.append(f'pesan={quote(pesan)}')
    if tipe:
        params.append(f'tipe={quote(tipe)}')
    if doc_id:
        params.append(f'doc={quote(doc_id)}')
    return RedirectResponse(url=dasar + ('?' + '&'.join(params) if params else ''),
                            status_code=303)


def ke_skkni(pesan: str = '', tipe: str = '', doc_id: str = '') -> RedirectResponse:
    return redirect_daftar('/skkni', pesan, tipe, doc_id)


def ke_skema(pesan: str = '', tipe: str = '', doc_id: str = '') -> RedirectResponse:
    return redirect_daftar('/skema', pesan, tipe, doc_id)


# --------------------------------------------------------------------------
# Gerbang dokumen (satu salinan aturan, bukan empat)
# --------------------------------------------------------------------------

RINGKASAN_GERBANG_PER_KODE: dict[str, str] = {
    'ada_gagal': 'Ada unit berstatus Gagal (0 elemen/KUK)',
    'ada_perlu': 'Ada unit yang perlu diperiksa',
}


def cek_gerbang(schema_id: str,
                gerbang: Optional[dict] = None) -> Optional[HTMLResponse]:
    """Mengembalikan halaman penolakan 409 bila ada unit Gagal, selain itu None.

    Dipakai oleh cetak HTML, unduh DOCX, dan unduh ZIP — sebelumnya ketiganya
    menyalin blok yang sama. Satu perubahan aturan cukup di sini (T-19).
    """
    g = gerbang or status_units.evaluasi_gerbang_skema(schema_id)
    if not g.get('ada_gagal'):
        return None
    daftar = '; '.join(
        f"{u['kode_unit']} ({u['alasan']})" for u in g.get('penahan', [])
        if u.get('status') == 'gagal'
    )
    return g, daftar

"""Masuk/keluar dan pengelolaan kata sandi akun.

Dipindahkan dari `app/main.py` (temuan T-19) tanpa mengubah perilaku: decorator
`@app.` menjadi `@router.` dan helper halaman diambil dari `app.web_common`.
"""

from typing import Any, Dict
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import db
from app.api import auth_guard, keamanan_http, security

from app.logging_config import ambil_logger
from app.web_common import redirect_daftar, render

#: Jumlah unit per halaman pada daftar panjang (dulu konstanta di app/main.py).
BATAS_UNIT_PER_HALAMAN = 10

logger = ambil_logger(__name__)

router = APIRouter()


@router.get('/login', response_class=HTMLResponse)
def halaman_login(request: Request, pesan: str = '', tipe: str = '', next: str = ''):
    token = security.token_dari_cookie(request)
    resp = render(request, 'login.html', judul='Masuk Akun', pesan=pesan, tipe=tipe,
                   csrf_token=token, tujuan=auth_guard.tujuan_aman(next))
    security.set_cookie_token(resp, token)
    return resp


@router.post('/login')
async def proses_login(request: Request):
    form = await request.form()
    csrf_token = str(form.get('csrf_token') or '')
    security.periksa_token(request, csrf_token)

    username = str(form.get('username') or '').strip()
    password = str(form.get('password') or '').strip()
    tujuan = auth_guard.tujuan_aman(str(form.get('next') or request.query_params.get('next') or ''))

    # Batas percobaan login per (IP, username): 5 gagal -> blokir 60 detik.
    ip = keamanan_http.ip_klien(request)
    sisa = keamanan_http.pembatas_login.sisa_blokir(ip, username)
    if sisa > 0:
        raise HTTPException(
            status_code=429,
            detail=(f'Terlalu banyak percobaan masuk yang gagal. '
                    f'Coba lagi dalam {sisa} detik.'),
        )

    pengguna = db.autentikasi(username, password)
    if not pengguna:
        # Kegagalan ke-5 tetap dijawab sebagai "sandi salah"; blokir berlaku
        # pada percobaan BERIKUTNYA agar perilakunya tidak berubah di tengah
        # rangkaian dan tidak membocorkan kapan ambang tercapai.
        keamanan_http.pembatas_login.catat_gagal(ip, username)
        sisa = keamanan_http.pembatas_login.sisa_blokir(ip, username)
        if sisa > 0:
            logger.warning('Percobaan login gagal berulang untuk %r dari %s; '
                           'percobaan berikutnya diblokir %s detik.', username, ip, sisa)
        return RedirectResponse(
            url='/login?tipe=galat&pesan=' + quote('Nama pengguna atau kata sandi salah.')
            + (f'&next={quote(tujuan, safe="/")}' if tujuan != '/' else ''),
            status_code=303,
        )

    keamanan_http.pembatas_login.bersihkan(ip, username)

    token_sesi = db.buat_sesi(pengguna['id'])
    if pengguna.get('must_change_password'):
        resp = RedirectResponse(url='/akun/ganti-sandi', status_code=303)
        resp.set_cookie('skkni_session', token_sesi, httponly=True, samesite='lax', path='/', max_age=60 * 60 * 24 * 7)
        return resp

    sudah_kembali = tujuan != '/'
    pesan = (f'Selamat datang, {pengguna["nama_lengkap"]}!'
             if not sudah_kembali
             else f'Selamat datang, {pengguna["nama_lengkap"]}. Silakan lanjutkan tindakan Anda.')
    tujuan_akhir = f'{tujuan}{"&" if "?" in tujuan else "?"}tipe=sukses&pesan={quote(pesan)}' if sudah_kembali else f'/?tipe=sukses&pesan={quote(pesan)}'
    resp = RedirectResponse(url=tujuan_akhir, status_code=303)
    resp.set_cookie('skkni_session', token_sesi, httponly=True, samesite='lax', path='/', max_age=60 * 60 * 24 * 7)
    return resp


@router.get('/akun/ganti-sandi', response_class=HTMLResponse)
def halaman_ganti_sandi(request: Request, pesan: str = '', tipe: str = '',
                        pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login())):
    token = security.token_dari_cookie(request)
    resp = render(
        request, 'akun_ganti_sandi.html', judul='Ganti Kata Sandi',
        pesan=pesan, tipe=tipe,
        wajib=bool(pengguna.get('must_change_password')),
        csrf_token=token,
    )
    security.set_cookie_token(resp, token)
    return resp


@router.post('/akun/ganti-sandi')
def proses_ganti_sandi(request: Request,
                       kata_sandi_lama: str = Form(''),
                       kata_sandi_baru: str = Form(''),
                       ulangi_kata_sandi: str = Form(''),
                       csrf_token: str = Form(''),
                       pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login())):
    security.periksa_token(request, csrf_token)

    def _gagal(pesan: str) -> RedirectResponse:
        return redirect_daftar('/akun/ganti-sandi', pesan, 'galat')

    if not db.autentikasi(pengguna['username'], kata_sandi_lama):
        return _gagal('Kata sandi saat ini salah.')
    if len(kata_sandi_baru or '') < 8:
        return _gagal('Kata sandi baru minimal 8 karakter.')
    if kata_sandi_baru != ulangi_kata_sandi:
        return _gagal('Ulangi kata sandi baru tidak sama.')
    if kata_sandi_baru == kata_sandi_lama:
        return _gagal('Kata sandi baru harus berbeda dari kata sandi saat ini.')

    try:
        db.ubah_kata_sandi(pengguna['id'], kata_sandi_baru)
    except ValueError as e:
        return _gagal(str(e))

    # Seluruh sesi lama dihapus agar sesi yang mungkin bocor tidak ikut hidup.
    db.hapus_semua_sesi_pengguna(pengguna['id'])
    token_baru = db.buat_sesi(pengguna['id'])
    resp = RedirectResponse(
        url='/?tipe=sukses&pesan=' + quote('Kata sandi berhasil diganti.'),
        status_code=303,
    )
    resp.set_cookie('skkni_session', token_baru, httponly=True, samesite='lax', path='/', max_age=60 * 60 * 24 * 7)
    return resp


@router.post('/logout')
def proses_logout(request: Request, csrf_token: str = Form('')):
    security.periksa_token(request, csrf_token)
    token_sesi = request.cookies.get('skkni_session', '')
    if token_sesi:
        db.hapus_sesi(token_sesi)
    resp = RedirectResponse(url='/login?tipe=info&pesan=' + quote('Anda telah berhasil keluar.'), status_code=303)
    resp.delete_cookie('skkni_session', path='/')
    return resp

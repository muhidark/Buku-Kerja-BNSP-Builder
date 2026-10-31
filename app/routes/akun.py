"""Masuk/keluar dan pengelolaan kata sandi akun.

Dipindahkan dari `app/main.py` (temuan T-19) tanpa mengubah perilaku: decorator
`@app.` menjadi `@router.` dan helper halaman diambil dari `app.web_common`.
"""

import json
import base64
from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app import db, schema_library
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
    is_json_request = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('accept', '')
        or request.headers.get('content-type', '').startswith('application/json')
    )

    if request.headers.get('content-type', '').startswith('application/json'):
        body = await request.json()
        username = str(body.get('username') or '').strip()
        password = str(body.get('password') or '').strip()
        csrf_token = str(body.get('csrf_token') or '')
        tujuan = auth_guard.tujuan_aman(str(body.get('next') or ''))
        schema_id_klaim = str(body.get('schema_id_klaim') or '').strip()
    else:
        form = await request.form()
        csrf_token = str(form.get('csrf_token') or '')
        username = str(form.get('username') or '').strip()
        password = str(form.get('password') or '').strip()
        tujuan = auth_guard.tujuan_aman(str(form.get('next') or request.query_params.get('next') or ''))
        schema_id_klaim = str(form.get('schema_id_klaim') or '').strip()

    security.periksa_token(request, csrf_token)

    # Batas percobaan login per (IP, username): 5 gagal -> blokir 60 detik.
    ip = keamanan_http.ip_klien(request)
    ua = request.headers.get('user-agent', '')
    sisa = keamanan_http.pembatas_login.sisa_blokir(ip, username)
    if sisa > 0:
        if is_json_request:
            return JSONResponse({
                'sukses': False,
                'pesan': f'Terlalu banyak percobaan masuk yang gagal. Coba lagi dalam {sisa} detik.'
            }, status_code=429)
        raise HTTPException(
            status_code=429,
            detail=(f'Terlalu banyak percobaan masuk yang gagal. '
                    f'Coba lagi dalam {sisa} detik.'),
        )

    pengguna = db.autentikasi(username, password)
    if not pengguna:
        keamanan_http.pembatas_login.catat_gagal(ip, username)
        db.catat_audit_ip(ip, 'login_gagal', None, None, ua)
        sisa = keamanan_http.pembatas_login.sisa_blokir(ip, username)
        if sisa > 0:
            logger.warning('Percobaan login gagal berulang untuk %r dari %s; '
                           'percobaan berikutnya diblokir %s detik.', username, ip, sisa)
        if is_json_request:
            return JSONResponse({'sukses': False, 'pesan': 'Nama pengguna atau kata sandi salah.'}, status_code=401)
        return RedirectResponse(
            url='/login?tipe=galat&pesan=' + quote('Nama pengguna atau kata sandi salah.')
            + (f'&next={quote(tujuan, safe="/")}' if tujuan != '/' else ''),
            status_code=303,
        )

    keamanan_http.pembatas_login.bersihkan(ip, username)
    db.catat_audit_ip(ip, 'login_kata_sandi', pengguna['id'], None, ua)

    # Klaim skema temporary jika ada
    if schema_id_klaim:
        schema_library.klaim_skema(schema_id_klaim, pengguna['id'], pengguna['username'])

    token_sesi = db.buat_sesi(pengguna['id'])
    if pengguna.get('must_change_password'):
        if is_json_request:
            resp = JSONResponse({'sukses': True, 'redirect_url': '/akun/ganti-sandi'})
        else:
            resp = RedirectResponse(url='/akun/ganti-sandi', status_code=303)
        resp.set_cookie('skkni_session', token_sesi, httponly=True, samesite='lax', path='/', max_age=60 * 60 * 24 * 7)
        return resp

    sudah_kembali = tujuan != '/'
    pesan = (f'Selamat datang, {pengguna["nama_lengkap"]}!'
             if not sudah_kembali
             else f'Selamat datang, {pengguna["nama_lengkap"]}. Silakan lanjutkan tindakan Anda.')
    tujuan_akhir = f'{tujuan}{"&" if "?" in tujuan else "?"}tipe=sukses&pesan={quote(pesan)}' if sudah_kembali else f'/?tipe=sukses&pesan={quote(pesan)}'

    if is_json_request:
        resp = JSONResponse({
            'sukses': True,
            'pesan': pesan,
            'redirect_url': tujuan if tujuan != '/' else '/skema',
            'pengguna': {'id': pengguna['id'], 'nama_lengkap': pengguna['nama_lengkap'], 'peran': pengguna['peran']}
        })
    else:
        resp = RedirectResponse(url=tujuan_akhir, status_code=303)
    resp.set_cookie('skkni_session', token_sesi, httponly=True, samesite='lax', path='/', max_age=60 * 60 * 24 * 7)
    return resp


@router.post('/auth/daftar')
async def proses_daftar(request: Request):
    """Pendaftaran mandiri akun asesor cepat dan ramah pengguna."""
    is_json_request = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('accept', '')
        or request.headers.get('content-type', '').startswith('application/json')
    )

    if request.headers.get('content-type', '').startswith('application/json'):
        body = await request.json()
        nama_lengkap = str(body.get('nama_lengkap') or '').strip()
        username = str(body.get('username') or '').strip()
        email = str(body.get('email') or '').strip()
        password = str(body.get('password') or '').strip()
        no_met = str(body.get('no_met') or '').strip()
        institusi = str(body.get('institusi') or '').strip()
        csrf_token = str(body.get('csrf_token') or '')
        tujuan = auth_guard.tujuan_aman(str(body.get('next') or ''))
        schema_id_klaim = str(body.get('schema_id_klaim') or '').strip()
    else:
        form = await request.form()
        nama_lengkap = str(form.get('nama_lengkap') or '').strip()
        username = str(form.get('username') or '').strip()
        email = str(form.get('email') or '').strip()
        password = str(form.get('password') or '').strip()
        no_met = str(form.get('no_met') or '').strip()
        institusi = str(form.get('institusi') or '').strip()
        csrf_token = str(form.get('csrf_token') or '')
        tujuan = auth_guard.tujuan_aman(str(form.get('next') or request.query_params.get('next') or ''))
        schema_id_klaim = str(form.get('schema_id_klaim') or '').strip()

    security.periksa_token(request, csrf_token)

    ip = keamanan_http.ip_klien(request)
    ua = request.headers.get('user-agent', '')

    # Validasi input
    if not nama_lengkap:
        pesan = 'Nama lengkap asesor wajib diisi.'
        if is_json_request:
            return JSONResponse({'sukses': False, 'pesan': pesan}, status_code=400)
        return RedirectResponse(f'/login?tipe=galat&pesan={quote(pesan)}', status_code=303)

    if not username:
        # Jika username kosong tetapi email diisi, gunakan bagian depan email
        if email and '@' in email:
            username = email.split('@')[0]
        else:
            username = nama_lengkap.lower().replace(' ', '_')

    try:
        pengguna = db.daftar_pengguna_mandiri(
            username=username,
            kata_sandi=password,
            nama_lengkap=nama_lengkap,
            email=email,
            no_met=no_met,
            institusi=institusi,
            ip_pendaftar=ip,
            user_agent=ua,
        )
    except ValueError as e:
        pesan = str(e)
        if is_json_request:
            return JSONResponse({'sukses': False, 'pesan': pesan}, status_code=400)
        return RedirectResponse(f'/login?tipe=galat&pesan={quote(pesan)}', status_code=303)

    # Klaim skema jika ada sesi skema temporary yang sedang terbuka
    if schema_id_klaim:
        schema_library.klaim_skema(schema_id_klaim, pengguna['id'], pengguna['username'])

    token_sesi = db.buat_sesi(pengguna['id'])
    pesan_sukses = f'Akun berhasil dibuat. Selamat datang, {pengguna["nama_lengkap"]}!'
    tujuan_akhir = tujuan if tujuan and tujuan != '/' else '/skema'

    if is_json_request:
        resp = JSONResponse({
            'sukses': True,
            'pesan': pesan_sukses,
            'redirect_url': tujuan_akhir,
            'pengguna': {'id': pengguna['id'], 'nama_lengkap': pengguna['nama_lengkap'], 'peran': pengguna['peran']}
        })
    else:
        resp = RedirectResponse(f'{tujuan_akhir}?tipe=sukses&pesan={quote(pesan_sukses)}', status_code=303)

    resp.set_cookie('skkni_session', token_sesi, httponly=True, samesite='lax', path='/', max_age=60 * 60 * 24 * 7)
    return resp


@router.post('/auth/google')
async def proses_google_auth(request: Request):
    """Autentikasi & Registrasi instan via Google Pop-up / Credential."""
    ip = keamanan_http.ip_klien(request)
    ua = request.headers.get('user-agent', '')

    data = await request.json()
    csrf_token = str(data.get('csrf_token') or '')
    security.periksa_token(request, csrf_token)

    credential = data.get('credential')
    google_id = data.get('google_id')
    email = data.get('email')
    nama_lengkap = data.get('nama_lengkap') or data.get('name')
    schema_id_klaim = str(data.get('schema_id_klaim') or '').strip()
    tujuan = auth_guard.tujuan_aman(str(data.get('next') or ''))

    # Jika dikirim Google JWT ID Token (dari Google Identity Services button)
    if credential:
        try:
            # Decode JWT payload
            parts = credential.split('.')
            if len(parts) >= 2:
                # Add base64 padding
                payload_b64 = parts[1] + '=' * (-len(parts[1]) % 4)
                payload_json = json.loads(base64.urlsafe_b64decode(payload_b64).decode('utf-8'))
                google_id = payload_json.get('sub')
                email = payload_json.get('email')
                nama_lengkap = payload_json.get('name')
        except Exception as e:
            logger.warning('Gagal mendekode JWT Google: %s', e)

    if not google_id and not email:
        return JSONResponse({'sukses': False, 'pesan': 'Kredensial akun Google tidak valid.'}, status_code=400)

    # Masuk atau buat akun baru via Google
    pengguna = db.masuk_atau_daftar_google(
        google_id=str(google_id or email),
        email=email or '',
        nama_lengkap=nama_lengkap or 'Asesor BNSP',
        ip_address=ip,
        user_agent=ua,
    )

    # Klaim skema temporary jika ada
    if schema_id_klaim:
        schema_library.klaim_skema(schema_id_klaim, pengguna['id'], pengguna['username'])

    token_sesi = db.buat_sesi(pengguna['id'])
    tujuan_akhir = tujuan if tujuan and tujuan != '/' else '/skema'

    resp = JSONResponse({
        'sukses': True,
        'pesan': f'Berhasil masuk sebagai {pengguna["nama_lengkap"]}.',
        'redirect_url': tujuan_akhir,
        'pengguna': {'id': pengguna['id'], 'nama_lengkap': pengguna['nama_lengkap'], 'peran': pengguna['peran']}
    })
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

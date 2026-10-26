"""
SKKNI Extractor - Aplikasi web lokal (Fase 4A + 4B).

Menjalankan:
    ./run.sh
    atau .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
"""

import json
import math
import re
from pathlib import Path
from typing import Any, Dict
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import db, jobs, koreksi, library, schema_library, status_units, web_data
from app.api import auth_guard
from app.api import keamanan_http
from app.buku_kerja import (
    DAFTAR_DOKUMEN_BUKU_KERJA,
    simpan_konfigurasi_muk,
    susun_data_buku_kerja,
    tentukan_dokumen_aktif,
)
from app.buku_kerja_docx import (
    NAMA_BERKAS_DOKUMEN,
    buat_docx_buku_kerja_bytes,
    buat_zip_buku_kerja_bytes,
)
from app.lsp_exporter import ambil_json_unit, skema_ke_lsp_data, unit_ke_lsp_dict, unit_ke_smart_paste_text
from app.section_parser import flatten_nodes
from app.services import document_service
from app.api import dashboard as api_dashboard
from app.api import documents as api_documents
from app.api import jobs as api_jobs
from app.api import security
from app.api import skema as api_skema
from app.api import skkni as api_skkni
from app.api import system as api_system
from app.api import v1 as api_v1

from app.version import __version__
from app.logging_config import inisialisasi_logging, ambil_logger

logger = inisialisasi_logging()
db.inisialisasi_db()

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'

BATAS_UNIT_PER_HALAMAN = 10
VERSI = __version__

app = FastAPI(
    title='Sistem Pembuatan Dokumen Buku Kerja Asessor V.2023',
    version=VERSI,
    # Dokumentasi API dimatikan saat APP_ENV=produksi (temuan T-22).
    docs_url=None if keamanan_http.PRODUKSI else '/docs',
    redoc_url=None if keamanan_http.PRODUKSI else '/redoc',
    openapi_url=None if keamanan_http.PRODUKSI else '/openapi.json',
)

app.add_middleware(keamanan_http.HeaderKeamanan)

jobs.pulihkan_job_macet()
auth_guard.pasang_penanganan_galat(app)

app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

app.include_router(api_system.router)
app.include_router(api_dashboard.router)
app.include_router(api_skkni.router)
app.include_router(api_skema.router)
app.include_router(api_jobs.router)
app.include_router(api_documents.router)
app.include_router(api_v1.router)

HALAMAN = [
    {'path': '/', 'label': 'Dashboard', 'ikon': '▤'},
    {'path': '/skkni', 'label': 'Dokumen SKKNI', 'ikon': '▦'},
    {'path': '/skema', 'label': 'Skema Sertifikasi', 'ikon': '▧'},
    {'path': '/unit', 'label': 'Unit Kompetensi', 'ikon': '▤'},
    {'path': '/ekstraksi', 'label': 'Ekstraksi', 'ikon': '⚙'},
    {'path': '/hasil', 'label': 'Hasil Ekstraksi', 'ikon': '▣'},
]


def _render(request: Request, template: str, **konteks) -> HTMLResponse:
    """Render template dengan konteks navigasi standar dan informasi pengguna sesi."""
    token_sesi = request.cookies.get('skkni_session', '')
    pengguna = db.ambil_pengguna_dari_sesi(token_sesi)
    konteks.setdefault('pengguna_aktif', pengguna)
    konteks.setdefault('csrf_token', security.token_dari_cookie(request))
    konteks.setdefault('halaman', HALAMAN)
    konteks.setdefault('versi', VERSI)
    path = request.url.path
    konteks.setdefault('aktif', '/skkni' if path.startswith('/skkni') else path)
    return templates.TemplateResponse(request, template, konteks)


def _redirect_daftar(dasar: str, pesan: str = '', tipe: str = '',
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


def _ke_skkni(pesan: str = '', tipe: str = '', doc_id: str = '') -> RedirectResponse:
    return _redirect_daftar('/skkni', pesan, tipe, doc_id)


def _ke_skema(pesan: str = '', tipe: str = '', doc_id: str = '') -> RedirectResponse:
    return _redirect_daftar('/skema', pesan, tipe, doc_id)


@app.get('/login', response_class=HTMLResponse)
def halaman_login(request: Request, pesan: str = '', tipe: str = '', next: str = ''):
    token = security.token_dari_cookie(request)
    resp = _render(request, 'login.html', judul='Masuk Akun', pesan=pesan, tipe=tipe,
                   csrf_token=token, tujuan=auth_guard.tujuan_aman(next))
    security.set_cookie_token(resp, token)
    return resp


@app.post('/login')
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


@app.get('/akun/ganti-sandi', response_class=HTMLResponse)
def halaman_ganti_sandi(request: Request, pesan: str = '', tipe: str = '',
                        pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login())):
    token = security.token_dari_cookie(request)
    resp = _render(
        request, 'akun_ganti_sandi.html', judul='Ganti Kata Sandi',
        pesan=pesan, tipe=tipe,
        wajib=bool(pengguna.get('must_change_password')),
        csrf_token=token,
    )
    security.set_cookie_token(resp, token)
    return resp


@app.post('/akun/ganti-sandi')
def proses_ganti_sandi(request: Request,
                       kata_sandi_lama: str = Form(''),
                       kata_sandi_baru: str = Form(''),
                       ulangi_kata_sandi: str = Form(''),
                       csrf_token: str = Form(''),
                       pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login())):
    security.periksa_token(request, csrf_token)

    def _gagal(pesan: str) -> RedirectResponse:
        return _redirect_daftar('/akun/ganti-sandi', pesan, 'galat')

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


@app.post('/logout')
def proses_logout(request: Request, csrf_token: str = Form('')):
    security.periksa_token(request, csrf_token)
    token_sesi = request.cookies.get('skkni_session', '')
    if token_sesi:
        db.hapus_sesi(token_sesi)
    resp = RedirectResponse(url='/login?tipe=info&pesan=' + quote('Anda telah berhasil keluar.'), status_code=303)
    resp.delete_cookie('skkni_session', path='/')
    return resp


@app.get('/', response_class=HTMLResponse)
def halaman_dashboard(request: Request):
    data = web_data.dashboard_data()
    return _render(request, 'dashboard.html', data=data, judul='Dashboard')


# ------------------------------------------------------------------ perpustakaan

@app.get('/skkni', response_class=HTMLResponse)
def halaman_skkni(request: Request, q: str = '', pesan: str = '', tipe: str = '',
                  doc: str = ''):
    library.pastikan_dokumen_proyek()
    documents = library.daftar_dokumen()

    # Identifikasi ringan dijalankan sekali per dokumen (hasil disimpan di metadata).
    for d in documents:
        if d.get('status_identifikasi') in ('belum_diproses', None) and not d.get('units'):
            d = library.identifikasi(d)

    kata = (q or '').strip().lower()
    if kata:
        documents = [d for d in documents
                     if kata in ' '.join(str(d.get(k) or '') for k in
                                         ('nama_asli', 'nomor', 'tahun', 'judul')).lower()]

    token = security.token_dari_cookie(request)
    peta_reg = db.ambil_peta_regulasi()
    for d in documents:
        nomor_str = str(d.get('nomor') or '').strip()
        tahun_str = str(d.get('tahun') or '').strip()
        kode_pola = f"{tahun_str}-{nomor_str.zfill(3)}" if nomor_str and tahun_str else (d.get('id') or '')
        reg_info = peta_reg.get(kode_pola) or peta_reg.get(d.get('id') or '')
        d['status_regulasi'] = reg_info.get('status_regulasi') if reg_info else 'berlaku'
        d['kepmen_pengganti'] = reg_info.get('kepmen_pengganti', '') if reg_info else ''

    resp = _render(
        request, 'skkni.html', judul='Dokumen SKKNI',
        daftar=documents, q=q, pesan=pesan, tipe=tipe, doc_sorot=doc,
        csrf_token=token,
        batas_mb=library.BATAS_UKURAN // (1024 * 1024),
        total_semua=len(library.daftar_dokumen()),
    )
    security.set_cookie_token(resp, token)
    return resp


@app.post('/skkni/{doc_id}/regulasi')
def perbarui_regulasi_skkni(request: Request, doc_id: str,
                            status_regulasi: str = Form('berlaku'),
                            kepmen_pengganti: str = Form(''),
                            catatan: str = Form(''),
                            csrf_token: str = Form(''),
                            pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login(auth_guard.PERAN_ADMIN))):
    """Kurasi status regulasi Kemnaker — khusus Admin / Kurator Master (T-01)."""
    security.periksa_token(request, csrf_token)

    dok = library.ambil_dokumen(doc_id)
    if not dok:
        return _ke_skkni('Dokumen SKKNI tidak ditemukan.', 'galat')

    nomor_str = str(dok.get('nomor') or '').strip()
    tahun_str = str(dok.get('tahun') or '').strip()
    kode_pola = f"{tahun_str}-{nomor_str.zfill(3)}" if nomor_str and tahun_str else doc_id

    db.simpan_status_regulasi(
        kode_skkni=kode_pola,
        status_regulasi=status_regulasi,
        nomor_kepmen=f"Kepmenaker No. {nomor_str} Tahun {tahun_str}" if nomor_str else "",
        judul_skkni=dok.get('judul') or dok.get('nama_asli') or "",
        kepmen_pengganti=kepmen_pengganti,
        catatan=catatan,
    )
    # Simpan juga pada doc_id langsung
    if kode_pola != doc_id:
        db.simpan_status_regulasi(
            kode_skkni=doc_id,
            status_regulasi=status_regulasi,
            nomor_kepmen=f"Kepmenaker No. {nomor_str} Tahun {tahun_str}" if nomor_str else "",
            judul_skkni=dok.get('judul') or dok.get('nama_asli') or "",
            kepmen_pengganti=kepmen_pengganti,
            catatan=catatan,
        )

    return RedirectResponse(
        url=f'/skkni/{doc_id}?tipe=sukses&pesan=' + quote('Status regulasi SKKNI Kemnaker berhasil diperbarui.'),
        status_code=303,
    )


@app.post('/skkni/upload')
async def unggah_skkni(request: Request,
                       berkas: UploadFile = File(...),
                       csrf_token: str = Form(''),
                       pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login(auth_guard.PERAN_ADMIN))):
    """Unggah PDF SKKNI baru — khusus Admin (T-01)."""
    security.periksa_token(request, csrf_token)
    try:
        if not berkas.filename:
            raise library.GalatUpload('Berkas tidak memiliki nama.')
        doc, duplikat = await run_in_threadpool(
            library.unggah, berkas.filename, berkas.file, berkas.size)
    except library.GalatUpload as e:
        await berkas.close()
        return _ke_skkni(e.pesan, 'galat')
    except Exception:
        await berkas.close()
        return _ke_skkni('Unggahan gagal diproses. Periksa berkas lalu coba lagi.', 'galat')
    await berkas.close()

    if duplikat:
        return _ke_skkni(
            f'Dokumen ini sudah ada di perpustakaan: {doc.get("nama_asli")} '
            f'({doc.get("nomor") or "?"}/{doc.get("tahun") or "?"}).',
            'info', doc['id'])
    return _ke_skkni(
        f'PDF berhasil diunggah dan diidentifikasi: {doc.get("jumlah_unit", 0)} unit '
        f'ditemukan.', 'sukses', doc['id'])


@app.get('/skkni/{doc_id}', response_class=HTMLResponse)
def detail_skkni(request: Request, doc_id: str, q: str = '', page: int = 1,
                 pesan: str = '', tipe: str = ''):
    doc = library.ambil_dokumen(doc_id)
    if not doc:
        html = _render(request, 'tidak_ditemukan.html', judul='Dokumen tidak ditemukan',
                       pesan='Dokumen SKKNI tidak ditemukan di perpustakaan.')
        html.status_code = 404
        return html

    if not doc.get('units') and doc.get('status_identifikasi') in ('belum_diproses', None):
        doc = library.identifikasi(doc)

    validasi_lama = doc.get('validasi_kelengkapan')
    if doc.get('units') and (not validasi_lama or validasi_lama.get('versi') != 3):
        doc = library.jalankan_validator(doc)

    validasi = doc.get('validasi_kelengkapan') or {}
    peta_validasi = validasi.get('unit') or {}
    manual = doc.get('verifikasi_manual') or {}

    semua_unit_dok = list(doc.get('units') or [])
    peta_status_3 = {}
    ringkasan_status_3 = {'siap': 0, 'perlu': 0, 'gagal': 0}
    for u_item in semua_unit_dok:
        kd = u_item.get('kode_unit')
        if not kd:
            continue
        st3 = status_units.status_unit(
            kd,
            verifikasi_manual=manual.get(kd),
            wajib_json=False,
        )
        peta_status_3[kd] = st3
        ringkasan_status_3[st3['status']] = ringkasan_status_3.get(st3['status'], 0) + 1

    unit = list(semua_unit_dok)
    kata = (q or '').strip().lower()
    if kata:
        unit = [u for u in unit
                if kata in (u.get('kode_unit') or '').lower()
                or kata in (u.get('judul_unit') or '').lower()]

    total = len(unit)
    halaman_total = max(1, math.ceil(total / BATAS_UNIT_PER_HALAMAN))
    halaman = min(max(1, page), halaman_total)
    mulai = (halaman - 1) * BATAS_UNIT_PER_HALAMAN

    token = security.token_dari_cookie(request)
    peta_reg = db.ambil_peta_regulasi()
    nomor_str = str(doc.get('nomor') or '').strip()
    tahun_str = str(doc.get('tahun') or '').strip()
    kode_pola = f"{tahun_str}-{nomor_str.zfill(3)}" if nomor_str and tahun_str else doc_id
    reg_info = peta_reg.get(kode_pola) or peta_reg.get(doc_id) or {}
    status_reg = reg_info.get('status_regulasi', 'berlaku')
    kepmen_ganti = reg_info.get('kepmen_pengganti', '')
    catatan_reg = reg_info.get('catatan', '')

    resp = _render(
        request, 'skkni_detail.html', judul='Detail SKKNI',
        dok=doc, units=unit[mulai:mulai + BATAS_UNIT_PER_HALAMAN],
        q=q, page=halaman, halaman_total=halaman_total, total_unit=total,
        validasi=validasi, peta_validasi=peta_validasi, manual=manual,
        peta_status_3=peta_status_3, ringkasan_status_3=ringkasan_status_3,
        status_regulasi=status_reg, kepmen_pengganti=kepmen_ganti, catatan_regulasi=catatan_reg,
        pesan=pesan, tipe=tipe, csrf_token=token,
    )
    security.set_cookie_token(resp, token)
    return resp


@app.get('/skkni/{doc_id}/pdf')
def buka_pdf_skkni(request: Request, doc_id: str):
    doc = library.ambil_dokumen(doc_id)
    if not doc:
        html = _render(request, 'tidak_ditemukan.html', judul='Dokumen tidak ditemukan',
                       pesan='Dokumen SKKNI tidak ditemukan di perpustakaan.')
        html.status_code = 404
        return html
    try:
        jalur = library.jalur_pdf(doc)
    except library.GalatUpload as e:
        html = _render(request, 'tidak_ditemukan.html', judul='Berkas PDF tidak ditemukan',
                       pesan=e.pesan)
        html.status_code = e.kode
        return html
    nama_aman = re.sub(r'[^A-Za-z0-9._ -]+', '_', Path(doc.get('nama_asli') or 'skkni.pdf').name)
    return FileResponse(
        path=str(jalur),
        media_type='application/pdf',
        headers={'Content-Disposition': f'inline; filename="{nama_aman}"'},
    )


@app.post('/skkni/{doc_id}/verifikasi')
def verifikasi_manual(request: Request, doc_id: str,
                      kode_unit: str = Form(...), csrf_token: str = Form(''),
                      pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login())):
    security.periksa_token(request, csrf_token)
    doc = library.ambil_dokumen(doc_id)
    if not doc:
        return _render(request, 'tidak_ditemukan.html', judul='Dokumen tidak ditemukan',
                       pesan='Dokumen SKKNI tidak ditemukan di perpustakaan.')
    library.tandai_manual(doc, kode_unit)
    return RedirectResponse(
        url=f'/skkni/{doc_id}?pesan={quote("Unit ditandai terverifikasi manual.")}&tipe=sukses',
        status_code=303)


# ------------------------------------------------------------------ halaman lain

@app.get('/skema', response_class=HTMLResponse)
def halaman_skema(request: Request, q: str = '', pesan: str = '', tipe: str = '',
                  doc: str = ''):
    daftar = schema_library.daftar_skema()

    kata = (q or '').strip().lower()
    if kata:
        daftar = [d for d in daftar
                  if kata in ' '.join(str(d.get(k) or '') for k in
                                      ('nama_skema', 'nama_asli', 'jenis_skema')).lower()]

    token = security.token_dari_cookie(request)
    resp = _render(
        request, 'skema.html', judul='Skema Sertifikasi',
        daftar=daftar, q=q, pesan=pesan, tipe=tipe, doc_sorot=doc,
        csrf_token=token,
        batas_mb=schema_library.BATAS_UKURAN // (1024 * 1024),
        total_semua=len(schema_library.daftar_skema()),
    )
    security.set_cookie_token(resp, token)
    return resp


@app.post('/skema/upload')
async def unggah_skema(request: Request,
                       berkas: UploadFile = File(...),
                       csrf_token: str = Form(''),
                       pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login(auth_guard.PERAN_ADMIN))):
    """Unggah dokumen skema sertifikasi — khusus Admin (T-01)."""
    security.periksa_token(request, csrf_token)
    try:
        if not berkas.filename:
            raise schema_library.GalatSkema('Berkas tidak memiliki nama.')
        doc, duplikat = await run_in_threadpool(
            schema_library.unggah, berkas.filename, berkas.file, berkas.size)
    except schema_library.GalatSkema as e:
        await berkas.close()
        return _ke_skema(e.pesan, 'galat')
    except Exception:
        await berkas.close()
        return _ke_skema('Unggahan gagal diproses. Periksa berkas lalu coba lagi.', 'galat')
    await berkas.close()

    if duplikat:
        return _ke_skema(
            f'Dokumen skema ini sudah ada: {doc.get("nama_skema") or doc.get("nama_asli")}.',
            'info', doc['id'])
    jumlah = doc.get('jumlah_unit', 0)
    if not jumlah:
        return _ke_skema('Dokumen tersimpan, tetapi daftar unit tidak dikenali. '
                         'Periksa detail untuk verifikasi manual.', 'galat', doc['id'])
    return _ke_skema(f'Skema berhasil diunggah: {jumlah} unit kompetensi terbaca.',
                     'sukses', doc['id'])


@app.get('/skema/{schema_id}', response_class=HTMLResponse)
def detail_skema(request: Request, schema_id: str, q: str = '', page: int = 1,
                 pesan: str = '', tipe: str = ''):
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        html = _render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                       pesan='Dokumen skema tidak ditemukan di perpustakaan.')
        html.status_code = 404
        return html

    daftar_browser = {p.stem for p in jobs.JSON_OUT.glob('*.json')} if jobs.JSON_OUT.exists() else set()
    ada_json = {u['kode_unit'] for u in document_service.unit_tersedia(schema_id) if u['ada_json']}
    peta_dasar = schema_library.peta_kelengkapan()
    peta_status = {u['kode_unit']: schema_library.status_unit(dok, u['kode_unit'], peta_dasar)
                   for u in dok.get('units') or []}
    gerbang = status_units.evaluasi_gerbang_skema(schema_id)
    peta_status_3 = gerbang.get('peta_unit') or {}
    for kd, st3 in peta_status_3.items():
        if st3.get('elemen_count', 0) > 0 or st3.get('ada_koreksi'):
            ada_json.add(kd)

    unit = list(dok.get('units') or [])
    kata = (q or '').strip().lower()
    if kata:
        unit = [u for u in unit
                if kata in (u.get('kode_unit') or '').lower()
                or kata in (u.get('judul_skema') or '').lower()]

    total = len(unit)
    halaman_total = max(1, math.ceil(total / BATAS_UNIT_PER_HALAMAN))
    halaman = min(max(1, page), halaman_total)
    mulai = (halaman - 1) * BATAS_UNIT_PER_HALAMAN

    skema_lsp_list, skema_smart_text = skema_ke_lsp_data(dok)
    skema_lsp_json = json.dumps(skema_lsp_list, ensure_ascii=False, indent=2)

    token = security.token_dari_cookie(request)
    resp = _render(
        request, 'skema_detail.html', judul='Detail Skema',
        dok=dok, units=unit[mulai:mulai + BATAS_UNIT_PER_HALAMAN],
        peta_status=peta_status, peta_status_3=peta_status_3, gerbang=gerbang,
        q=q, page=halaman, ada_browser=daftar_browser,
        ada_json=ada_json,
        skema_lsp_json=skema_lsp_json, skema_smart_text=skema_smart_text,
        skema_lsp_count=len(skema_lsp_list),
        halaman_total=halaman_total, total_unit=total,
        pesan=pesan, tipe=tipe, csrf_token=token,
    )
    security.set_cookie_token(resp, token)
    return resp


@app.post('/skema/{schema_id}/periksa-ulang')
def periksa_ulang_skema(request: Request, schema_id: str, csrf_token: str = Form(''),
                        pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login())):
    security.periksa_token(request, csrf_token)
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return _ke_skema('Skema tidak ditemukan.', 'galat')
    try:
        dok = schema_library.cocokkan_ulang(dok)
    except schema_library.GalatSkema as e:
        return _ke_skema(e.pesan, 'galat', schema_id)
    ringkas = (dok.get('hasil_pencocokan') or {}).get('ringkasan') or {}
    return RedirectResponse(
        url=(f"/skema/{schema_id}?tipe=sukses&pesan="
             + quote(f"Pencocokan diperbarui: {ringkas.get('ditemukan', 0)} ditemukan, "
                     f"{ringkas.get('tidak_ditemukan', 0)} belum ditemukan, "
                     f"{ringkas.get('konflik', 0)} konflik.")),
        status_code=303)


@app.post('/skema/{schema_id}/ekstrak')
def ekstrak_unit(request: Request, schema_id: str,
                 kode_unit: str = Form(''), csrf_token: str = Form(''),
                 pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login())):
    security.periksa_token(request, csrf_token)
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return _ke_skema('Skema tidak ditemukan.', 'galat')
    try:
        job = jobs.buat_job(dok, kode_unit or None)
    except jobs.GalatJob as e:
        return _ke_skema(e.pesan, 'galat', schema_id)
    return RedirectResponse(url=f"/job/{job['id']}", status_code=303)


@app.get('/skema/{schema_id}/cetak-apl', response_class=HTMLResponse)
def cetak_apl_skema(
    request: Request,
    schema_id: str,
    doc: str = 'all',
    no_skema: str = '',
    nama_asesor: str = '',
    no_met: str = '',
    metode_mapa: str = '',
    kategori_asesi: int = 0,
):
    data = susun_data_buku_kerja(
        schema_id=schema_id,
        no_skema=no_skema,
        nama_asesor=nama_asesor,
        no_met=no_met,
        metode_mapa=metode_mapa,
        kategori_asesi=kategori_asesi,
    )
    if not data:
        html = _render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                       pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html

    gerbang = data.get('gerbang') or status_units.evaluasi_gerbang_skema(schema_id)
    if gerbang.get('ada_gagal'):
        gagal_list = [f"{u['kode_unit']} ({u['alasan']})" for u in gerbang['penahan'] if u['status'] == 'gagal']
        html = _render(
            request,
            'tidak_ditemukan.html',
            judul='Dokumen belum dapat dicetak',
            pesan='Cetak Buku Kerja ditahan karena ada unit berstatus Gagal: ' + '; '.join(gagal_list),
        )
        html.status_code = 409
        return html

    valid_modes = {d['kode'] for d in DAFTAR_DOKUMEN_BUKU_KERJA}
    doc_mode = doc.lower().strip() if doc.lower().strip() in valid_modes else 'all'
    dokumen_aktif = tentukan_dokumen_aktif(doc_mode, data.get('metode_mapa', 'observasi'))

    label_map = {d['kode']: d['label'] for d in DAFTAR_DOKUMEN_BUKU_KERJA}
    judul_halaman = f"{label_map.get(doc_mode, 'Buku Kerja Asesor')} - {data['nama_skema']}"

    return _render(
        request, 'cetak_apl.html',
        judul=judul_halaman,
        judul_halaman=judul_halaman,
        data=data,
        doc_mode=doc_mode,
        dokumen_aktif=dokumen_aktif,
    )


@app.get('/skema/{schema_id}/unduh-buku-kerja-docx')
def unduh_buku_kerja_docx(
    request: Request,
    schema_id: str,
    doc: str = 'all',
    no_skema: str = '',
    nama_asesor: str = '',
    no_met: str = '',
    metode_mapa: str = '',
    kategori_asesi: int = 0,
):
    data = susun_data_buku_kerja(
        schema_id=schema_id,
        no_skema=no_skema,
        nama_asesor=nama_asesor,
        no_met=no_met,
        metode_mapa=metode_mapa,
        kategori_asesi=kategori_asesi,
    )
    if not data:
        html = _render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                       pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html

    gerbang = data.get('gerbang') or status_units.evaluasi_gerbang_skema(schema_id)
    if gerbang.get('ada_gagal'):
        gagal_list = [f"{u['kode_unit']} ({u['alasan']})" for u in gerbang['penahan'] if u['status'] == 'gagal']
        html = _render(
            request,
            'tidak_ditemukan.html',
            judul='Dokumen belum dapat diunduh',
            pesan='Unduh Buku Kerja (.docx) ditahan karena ada unit berstatus Gagal: ' + '; '.join(gagal_list),
        )
        html.status_code = 409
        return html

    valid_modes = {d['kode'] for d in DAFTAR_DOKUMEN_BUKU_KERJA}
    doc_mode = doc.lower().strip() if doc.lower().strip() in valid_modes else 'all'
    dokumen_aktif = tentukan_dokumen_aktif(doc_mode, data.get('metode_mapa', 'observasi'))

    slug_skema = re.sub(r'[^a-zA-Z0-9_-]+', '_', data['nama_skema']).strip('_') or schema_id
    if len(dokumen_aktif) == 1:
        nama_berkas = NAMA_BERKAS_DOKUMEN.get(dokumen_aktif[0], f"{dokumen_aktif[0].upper()}.docx")
        nama_unduh = f"{slug_skema}_{nama_berkas}"
    else:
        nama_unduh = f"Buku_Kerja_Lengkap_{slug_skema}_{doc_mode}.docx"

    docx_bytes = buat_docx_buku_kerja_bytes(
        data=data,
        dokumen_aktif=dokumen_aktif,
        judul_halaman=f"Buku Kerja - {data['nama_skema']}",
    )
    return Response(
        content=docx_bytes,
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={'Content-Disposition': f'attachment; filename="{nama_unduh}"'},
    )


@app.get('/skema/{schema_id}/unduh-buku-kerja-zip')
def unduh_buku_kerja_zip(
    request: Request,
    schema_id: str,
    doc: str = 'all',
    no_skema: str = '',
    nama_asesor: str = '',
    no_met: str = '',
    metode_mapa: str = '',
    kategori_asesi: int = 0,
):
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        html = _render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                       pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html

    gerbang = status_units.evaluasi_gerbang_skema(schema_id)
    if gerbang.get('ada_gagal'):
        gagal_list = [f"{u['kode_unit']} ({u['alasan']})" for u in gerbang['penahan'] if u['status'] == 'gagal']
        html = _render(
            request,
            'tidak_ditemukan.html',
            judul='Dokumen belum dapat diunduh',
            pesan='Unduh Paket ZIP Buku Kerja ditahan karena ada unit berstatus Gagal: ' + '; '.join(gagal_list),
        )
        html.status_code = 409
        return html

    hasil_zip = buat_zip_buku_kerja_bytes(
        schema_id=schema_id,
        doc_mode=doc,
        no_skema=no_skema,
        nama_asesor=nama_asesor,
        no_met=no_met,
        metode_mapa=metode_mapa,
        kategori_asesi=kategori_asesi,
    )
    if not hasil_zip:
        html = _render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                       pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html

    zip_bytes, nama_zip = hasil_zip
    return Response(
        content=zip_bytes,
        media_type='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{nama_zip}"'},
    )


@app.get('/skema/{schema_id}/muk', response_class=HTMLResponse)
def halaman_muk_skema(
    request: Request,
    schema_id: str,
    versi: str = '',
    pesan: str = '',
    tipe: str = '',
):
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        html = _render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                       pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html

    data = susun_data_buku_kerja(schema_id=schema_id, kode_versi=versi)
    token = security.token_dari_cookie(request)
    resp = _render(
        request, 'skema_muk.html',
        judul=f"Pengaturan MUK - {dok.get('nama_skema', '')}",
        dok=dok,
        data=data,
        versi_terpilih=versi or data.get('versi_aktif', 'v1'),
        pesan=pesan,
        tipe=tipe,
        csrf_token=token,
    )
    security.set_cookie_token(resp, token)
    return resp


@app.post('/skema/{schema_id}/muk')
async def simpan_muk_skema(request: Request, schema_id: str,
                           pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login())):
    form = await request.form()
    csrf_token = str(form.get('csrf_token') or '')
    security.periksa_token(request, csrf_token)

    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return _ke_skema('Skema tidak ditemukan.', 'galat')

    dibuat_oleh = pengguna['id']

    kode_versi = str(form.get('kode_versi') or 'v1').strip().lower()
    nama_versi = str(form.get('nama_versi') or 'Paket MUK Utama').strip()
    deskripsi_versi = str(form.get('deskripsi_versi') or '').strip()

    muk_json_raw = form.get('muk_json')
    if not muk_json_raw:
        return RedirectResponse(
            url=f'/skema/{schema_id}/muk?tipe=galat&pesan=' + quote('Data konfigurasi MUK kosong.'),
            status_code=303,
        )
    try:
        payload = json.loads(str(muk_json_raw))
        simpan_konfigurasi_muk(
            schema_id,
            payload,
            kode_versi=kode_versi,
            nama_versi=nama_versi,
            deskripsi=deskripsi_versi,
            dibuat_oleh=dibuat_oleh,
            is_aktif=True,
        )
    except Exception as e:
        return RedirectResponse(
            url=f'/skema/{schema_id}/muk?tipe=galat&pesan=' + quote(f'Gagal menyimpan MUK: {e}'),
            status_code=303,
        )

    return RedirectResponse(
        url=f'/skema/{schema_id}/muk?versi={kode_versi}&tipe=sukses&pesan=' + quote(f'Seluruh pengaturan MUK & Kelompok Pekerjaan ({nama_versi}) berhasil disimpan.'),
        status_code=303,
    )


@app.get('/skema/{schema_id}/unit/{kode_unit}', response_class=HTMLResponse)
def preview_unit(request: Request, schema_id: str, kode_unit: str,
                 pesan: str = '', tipe: str = ''):
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        html = _render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                       pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html

    if not re.fullmatch(r'[A-Z]\.\d{2}[A-Z]{2,3}\d{2}\.\d{3}\.\d', kode_unit or ''):
        html = _render(request, 'tidak_ditemukan.html', judul='Kode unit tidak sah',
                       pesan='Format kode unit tidak dikenali.')
        html.status_code = 404
        return html

    data = ambil_json_unit(kode_unit)
    jalur_mesin = koreksi.cari_berkas_mesin(kode_unit)
    berkas = str(jalur_mesin.relative_to(jobs.ROOT)) if jalur_mesin else f'data/json/browser_extraction/{kode_unit}.json'

    unit_skema = next((u for u in dok.get('units') or [] if u['kode_unit'] == kode_unit), None)
    cocok = ((dok.get('hasil_pencocokan') or {}).get('units') or {}).get(kode_unit)
    ver_manual = (dok.get('verifikasi_manual') or {}).get(kode_unit)
    info_status = status_units.status_unit(
        kode_unit,
        data=data,
        verifikasi_manual=ver_manual,
        hasil_cocok=cocok,
        wajib_json=True,
    )

    bv = pp = []
    unit_lsp_json = ''
    unit_smart_text = ''
    if data:
        bv = flatten_nodes((data.get('batasan_variabel') or {}).get('sections') or [])
        pp = flatten_nodes((data.get('panduan_penilaian') or {}).get('sections') or [])
        unit_dict = unit_ke_lsp_dict(data)
        unit_lsp_json = json.dumps([unit_dict], ensure_ascii=False, indent=2)
        unit_smart_text = unit_ke_smart_paste_text(data)

    token = security.token_dari_cookie(request)
    resp = _render(
        request, 'unit_preview.html', judul='Hasil Ekstraksi Unit',
        dok=dok, kode=kode_unit, data=data, unit_skema=unit_skema,
        info_status=info_status,
        bv=bv, pp=pp,
        unit_lsp_json=unit_lsp_json, unit_smart_text=unit_smart_text,
        berkas=berkas, pesan=pesan, tipe=tipe, csrf_token=token,
    )
    security.set_cookie_token(resp, token)
    return resp


@app.get('/skema/{schema_id}/unit/{kode_unit}/koreksi', response_class=HTMLResponse)
def halaman_koreksi_unit(request: Request, schema_id: str, kode_unit: str,
                         pesan: str = '', tipe: str = ''):
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        html = _render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                       pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html

    if not re.fullmatch(r'[A-Z]\.\d{2}[A-Z]{2,3}\d{2}\.\d{3}\.\d', kode_unit or ''):
        html = _render(request, 'tidak_ditemukan.html', judul='Kode unit tidak sah',
                       pesan='Format kode unit tidak dikenali.')
        html.status_code = 404
        return html

    unit_skema = next((u for u in dok.get('units') or [] if u['kode_unit'] == kode_unit), None)
    data_mesin = koreksi.muat_json_mesin(kode_unit)
    data_final = koreksi.ambil_unit_final(kode_unit)
    info_koreksi = (data_final or {}).get('_koreksi') or koreksi.status_koreksi(kode_unit)

    cocok = ((dok.get('hasil_pencocokan') or {}).get('units') or {}).get(kode_unit)
    ver_manual = (dok.get('verifikasi_manual') or {}).get(kode_unit)
    info_status = status_units.status_unit(
        kode_unit,
        data=data_final,
        info_koreksi=info_koreksi,
        verifikasi_manual=ver_manual,
        hasil_cocok=cocok,
        wajib_json=True,
    )

    elemen_sumber = (data_final or {}).get('elemen_kompetensi') or []
    elemen_form = koreksi.normalisasi_elemen_koreksi(elemen_sumber)
    if not elemen_form:
        elemen_form = [{
            'nomor': 1,
            'nama': '',
            'kuk': [{'nomor': '1.1', 'uraian': ''}],
        }]

    elemen_mesin_norm = koreksi.normalisasi_elemen_koreksi(
        (data_mesin or {}).get('elemen_kompetensi') or []
    )
    peta_el_mesin = {el['nomor']: el['nama'] for el in elemen_mesin_norm}
    peta_kuk_mesin = {
        k['nomor']: k['uraian']
        for el in elemen_mesin_norm
        for k in (el.get('kuk') or [])
    }

    judul_unit = (
        (data_final or {}).get('judul_unit')
        or (unit_skema or {}).get('judul_skema')
        or info_status.get('judul_unit')
        or ''
    )

    token = security.token_dari_cookie(request)
    resp = _render(
        request, 'unit_koreksi.html', judul=f'Koreksi Unit {kode_unit}',
        dok=dok, kode=kode_unit, judul_unit=judul_unit,
        unit_skema=unit_skema, data_mesin=data_mesin, data=data_final,
        elemen_form=elemen_form, elemen_mesin=elemen_mesin_norm,
        peta_el_mesin=peta_el_mesin, peta_kuk_mesin=peta_kuk_mesin,
        info_koreksi=info_koreksi, info_status=info_status,
        pesan=pesan, tipe=tipe, csrf_token=token,
    )
    security.set_cookie_token(resp, token)
    return resp


@app.post('/skema/{schema_id}/unit/{kode_unit}/koreksi')
async def simpan_koreksi_unit(request: Request, schema_id: str, kode_unit: str,
                              pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login(auth_guard.PERAN_ADMIN))):
    """Menyimpan koreksi manual teks elemen/KUK — khusus Admin (T-01)."""
    form = await request.form()
    csrf_token = str(form.get('csrf_token') or '')
    security.periksa_token(request, csrf_token)

    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return _ke_skema('Skema tidak ditemukan.', 'galat')

    aksi = str(form.get('aksi') or '').strip()
    if aksi == 'pertahankan':
        koreksi.pertahankan_koreksi(kode_unit)
        return RedirectResponse(
            url=(f'/skema/{schema_id}/unit/{kode_unit}/koreksi?tipe=sukses&pesan='
                 + quote('Koreksi manual dipertahankan terhadap hasil ekstraksi mesin terbaru.')),
            status_code=303,
        )

    judul_unit = form.get('judul_unit')
    judul_str = str(judul_unit) if judul_unit is not None else None
    elemen_json_raw = form.get('elemen_json')

    elemen_input: list[dict] = []
    if elemen_json_raw:
        try:
            elemen_input = json.loads(str(elemen_json_raw))
        except Exception:
            return RedirectResponse(
                url=(f'/skema/{schema_id}/unit/{kode_unit}/koreksi?tipe=galat&pesan='
                     + quote('Format data koreksi tidak valid.')),
                status_code=303,
            )
    else:
        daftar_el_no = form.getlist('elemen_nomor')
        daftar_el_nama = form.getlist('elemen_nama')
        daftar_kuk_el = form.getlist('kuk_elemen')
        daftar_kuk_no = form.getlist('kuk_nomor')
        daftar_kuk_ur = form.getlist('kuk_uraian')

        peta_el: dict[int, dict] = {}
        urutan_el: list[int] = []
        for idx, no_str in enumerate(daftar_el_no):
            try:
                no_el = int(str(no_str).strip())
            except ValueError:
                no_el = idx + 1
            nama_el = str(daftar_el_nama[idx]) if idx < len(daftar_el_nama) else ''
            peta_el[no_el] = {'nomor': no_el, 'nama': nama_el, 'kuk': []}
            urutan_el.append(no_el)

        for k_idx, no_kuk_raw in enumerate(daftar_kuk_no):
            el_ref_raw = daftar_kuk_el[k_idx] if k_idx < len(daftar_kuk_el) else ''
            no_kuk_str = str(no_kuk_raw).strip()
            uraian_str = str(daftar_kuk_ur[k_idx]) if k_idx < len(daftar_kuk_ur) else ''
            try:
                no_el = int(str(el_ref_raw).strip())
            except ValueError:
                if '.' in no_kuk_str:
                    try:
                        no_el = int(no_kuk_str.split('.', 1)[0])
                    except ValueError:
                        no_el = urutan_el[0] if urutan_el else 1
                else:
                    no_el = urutan_el[0] if urutan_el else 1
            if no_el not in peta_el:
                peta_el[no_el] = {'nomor': no_el, 'nama': '', 'kuk': []}
                urutan_el.append(no_el)
            peta_el[no_el]['kuk'].append({
                'nomor': no_kuk_str or f"{no_el}.{len(peta_el[no_el]['kuk']) + 1}",
                'uraian': uraian_str,
            })

        elemen_input = [peta_el[n] for n in urutan_el]

    try:
        koreksi.simpan_koreksi(kode_unit, elemen_input, judul_unit=judul_str)
    except ValueError as e:
        return RedirectResponse(
            url=(f'/skema/{schema_id}/unit/{kode_unit}/koreksi?tipe=galat&pesan='
                 + quote(str(e))),
            status_code=303,
        )

    lanjut = str(form.get('lanjut') or '').strip()
    if lanjut == 'skema':
        return RedirectResponse(
            url=(f'/skema/{schema_id}?tipe=sukses&pesan='
                 + quote(f'Koreksi unit {kode_unit} disimpan. Status unit kini Siap dipakai.')),
            status_code=303,
        )
    return RedirectResponse(
        url=(f'/skema/{schema_id}/unit/{kode_unit}/koreksi?tipe=sukses&pesan='
             + quote(f'Koreksi unit {kode_unit} berhasil disimpan.')),
        status_code=303,
    )


@app.post('/skema/{schema_id}/unit/{kode_unit}/koreksi/kembalikan')
def kembalikan_koreksi_unit(request: Request, schema_id: str, kode_unit: str,
                            csrf_token: str = Form(''),
                            pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login(auth_guard.PERAN_ADMIN))):
    security.periksa_token(request, csrf_token)
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return _ke_skema('Skema tidak ditemukan.', 'galat')
    dihapus = koreksi.hapus_koreksi(kode_unit)
    pesan = (
        f'Koreksi manual unit {kode_unit} dihapus; kembali menggunakan hasil ekstraksi mesin.'
        if dihapus
        else f'Unit {kode_unit} sudah menggunakan hasil ekstraksi mesin.'
    )
    return RedirectResponse(
        url=f'/skema/{schema_id}/unit/{kode_unit}/koreksi?tipe=info&pesan={quote(pesan)}',
        status_code=303,
    )


@app.get('/api/unit/{kode_unit}/status')
def api_status_unit(kode_unit: str):
    return status_units.status_unit(kode_unit, wajib_json=True)


@app.get('/job/{job_id}', response_class=HTMLResponse)
def halaman_job(request: Request, job_id: str):
    job = jobs.ambil_job(job_id)
    if not job:
        html = _render(request, 'tidak_ditemukan.html', judul='Job tidak ditemukan',
                       pesan='Job ekstraksi tidak ditemukan atau sudah dihapus.')
        html.status_code = 404
        return html
    return _render(request, 'skema_job.html', judul='Job Ekstraksi', job=job)


@app.post('/skema/{schema_id}/verifikasi')
def verifikasi_unit_skema(request: Request, schema_id: str,
                          kode_unit: str = Form(...), csrf_token: str = Form(''),
                          pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login())):
    security.periksa_token(request, csrf_token)
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return _ke_skema('Skema tidak ditemukan.', 'galat')
    schema_library.tandai_manual(dok, kode_unit)
    return RedirectResponse(
        url=f'/skema/{schema_id}?tipe=sukses&pesan=' + quote(
            'Unit ditandai terverifikasi manual.'),
        status_code=303)


@app.get('/unit', response_class=HTMLResponse)
def halaman_unit(request: Request):
    return _render(request, 'unit.html', judul='Unit Kompetensi',
                   daftar=web_data.daftar_unit())


@app.get('/ekstraksi', response_class=HTMLResponse)
def halaman_ekstraksi(request: Request):
    return _render(request, 'ekstraksi.html', judul='Ekstraksi',
                   skkni=web_data.daftar_skkni(),
                   skema=web_data.daftar_skema())


@app.get('/hasil', response_class=HTMLResponse)
def halaman_hasil(request: Request, pesan: str = '', tipe: str = ''):
    return _render(request, 'hasil.html', judul='Dokumen Word',
                   daftar=document_service.daftar_dokumen(),
                   pesan=pesan, tipe=tipe)


@app.get('/hasil/{doc_id}', response_class=HTMLResponse)
def detail_dokumen(request: Request, doc_id: str, pesan: str = '', tipe: str = ''):
    meta = document_service.ambil_dokumen(doc_id)
    if not meta:
        html = _render(request, 'tidak_ditemukan.html', judul='Dokumen tidak ditemukan',
                       pesan='Dokumen Word tidak ditemukan pada riwayat.')
        html.status_code = 404
        return html
    return _render(request, 'hasil_detail.html', judul='Detail Dokumen Word',
                   dok=meta, pesan=pesan, tipe=tipe)


@app.post('/hasil/generate')
def generate_dari_browser(request: Request,
                          schema_id: str = Form(...),
                          kode_unit: list[str] | None = Form(None),
                          draft: str = Form(''),
                          csrf_token: str = Form(''),
                          pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login())):
    security.periksa_token(request, csrf_token)
    pilihan = [k for k in (kode_unit or []) if k]
    try:
        meta = document_service.buat_dokumen(
            schema_id, pilihan or None,
            setujui_draft=bool(draft))
    except document_service.GalatDokumen as e:
        rincian = '; '.join(f"{m['kode']}: {m['pesan']}" for m in e.masalah[:3])
        pesan = e.pesan + (f' ({rincian})' if rincian else '')
        return RedirectResponse(
            url=f"/skema/{schema_id}?tipe=galat&pesan={quote(pesan)}", status_code=303)
    return RedirectResponse(
        url=f"/hasil/{meta['id']}?tipe=sukses&pesan=" + quote(
            f" Dokumen dibuat: {meta['jumlah_unit']} unit, status {meta['status']}."),
        status_code=303)


# ------------------------------------------------------------------ galat

@app.exception_handler(StarletteHTTPException)
async def galat_http(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith('/api/'):
        return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
    html = _render(request, 'tidak_ditemukan.html',
                   judul='Halaman tidak ditemukan' if exc.status_code == 404
                   else 'Permintaan ditolak',
                   pesan=str(exc.detail))
    html.status_code = exc.status_code
    return html


@app.exception_handler(RequestValidationError)
async def galat_validasi(request: Request, exc: RequestValidationError):
    if request.url.path.startswith('/api/'):
        return JSONResponse({'detail': 'Permintaan tidak valid.'}, status_code=422)
    if request.url.path.startswith('/hasil'):
        return _redirect_daftar('/skema',
                                'Permintaan tidak sesuai. Pilih minimal satu unit.',
                                'galat')
    return _ke_skkni('Berkas belum dipilih atau format permintaan tidak sesuai.', 'galat')


@app.exception_handler(Exception)
async def penanganan_galat(request: Request, exc: Exception):
    """Jangan pernah menampilkan traceback ke pengguna, catat ke log."""
    logger.error(f"Galat internal pada {request.method} {request.url.path}: {exc}", exc_info=True)
    return HTMLResponse(
        '<!doctype html><meta charset="utf-8">'
        '<title>Terjadi kesalahan</title>'
        '<div style="font-family:system-ui;padding:2rem">'
        '<h1>Terjadi kesalahan internal</h1>'
        '<p>Permintaan tidak dapat diproses. Periksa log server untuk detail.</p>'
        '<p><a href="/">Kembali ke dashboard</a></p></div>',
        status_code=500,
    )

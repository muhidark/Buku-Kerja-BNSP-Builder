"""
SKKNI Extractor - Aplikasi web lokal.

Berkas ini hanya menyusun aplikasi: konfigurasi, middleware, penanganan galat,
dan pendaftaran router. Rute halaman tinggal di `app/routes/` (temuan T-19:
sebelumnya seluruh 1.293 baris berada di sini, dengan blok gerbang 409 yang
disalin empat kali).

Menjalankan:
    ./run.sh
    atau .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import cadangan, db, jobs, web_data
from app.api import auth_guard, keamanan_http
from app.api import dashboard as api_dashboard
from app.api import documents as api_documents
from app.api import jobs as api_jobs
from app.api import skema as api_skema
from app.api import skkni as api_skkni
from app.api import system as api_system
from app.api import v1 as api_v1
from app.logging_config import inisialisasi_logging
from app.paths import STATIC_DIR
from app.routes import akun as rute_akun
from app.routes import cetak as rute_cetak
from app.routes import hasil as rute_hasil
from app.routes import skema as rute_skema
from app.routes import skkni as rute_skkni
from app.routes import unit_muk as rute_unit_muk
from app.web_common import VERSI, ke_skkni, redirect_daftar, render

logger = inisialisasi_logging()
db.inisialisasi_db()

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
# Pencadangan harian di latar belakang (T-31): sekali per hari, rotasi 7 arsip.
cadangan.jalankan_harian()

app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')

# --- API JSON (sudah punya router sendiri sejak Fase 4) ---
app.include_router(api_system.router)
app.include_router(api_dashboard.router)
app.include_router(api_skkni.router)
app.include_router(api_skema.router)
app.include_router(api_jobs.router)
app.include_router(api_documents.router)
app.include_router(api_v1.router)

# --- Halaman HTML, dipisah per domain ---
app.include_router(rute_akun.router)
app.include_router(rute_skkni.router)
app.include_router(rute_skema.router)
app.include_router(rute_unit_muk.router)
app.include_router(rute_cetak.router)
app.include_router(rute_hasil.router)


# ------------------------------------------------------------------ halaman inti

@app.get('/', response_class=HTMLResponse)
def halaman_dashboard(request: Request):
    data = web_data.dashboard_data()
    return render(request, 'dashboard.html', data=data, judul='Dashboard')


@app.get('/unit', response_class=HTMLResponse)
def halaman_unit(request: Request):
    return render(request, 'unit.html', judul='Unit Kompetensi',
                  daftar=web_data.daftar_unit())


@app.get('/ekstraksi', response_class=HTMLResponse)
def halaman_ekstraksi(request: Request):
    return render(request, 'ekstraksi.html', judul='Ekstraksi',
                  skkni=web_data.daftar_skkni(),
                  skema=web_data.daftar_skema())


# ------------------------------------------------------------------ galat

@app.exception_handler(StarletteHTTPException)
async def galat_http(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith('/api/'):
        return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
    html = render(request, 'tidak_ditemukan.html',
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
        return redirect_daftar('/skema',
                               'Permintaan tidak sesuai. Pilih minimal satu unit.',
                               'galat')
    return ke_skkni('Berkas belum dipilih atau format permintaan tidak sesuai.', 'galat')


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

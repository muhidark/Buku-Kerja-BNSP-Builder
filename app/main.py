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
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import jobs, library, schema_library, web_data
from app.buku_kerja import susun_data_buku_kerja
from app.lsp_exporter import skema_ke_lsp_data, unit_ke_lsp_dict, unit_ke_smart_paste_text
from app.section_parser import flatten_nodes
from app.services import document_service
from app.api import dashboard as api_dashboard
from app.api import documents as api_documents
from app.api import jobs as api_jobs
from app.api import security
from app.api import skema as api_skema
from app.api import skkni as api_skkni
from app.api import system as api_system

from app.version import __version__
from app.logging_config import inisialisasi_logging, ambil_logger

logger = inisialisasi_logging()

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / 'templates'
STATIC_DIR = BASE_DIR / 'static'

BATAS_UNIT_PER_HALAMAN = 10
VERSI = __version__

app = FastAPI(
    title='Sistem Pembuatan Dokumen Buku Kerja Asessor V.2023',
    version=VERSI,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

jobs.pulihkan_job_macet()

app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

app.include_router(api_system.router)
app.include_router(api_dashboard.router)
app.include_router(api_skkni.router)
app.include_router(api_skema.router)
app.include_router(api_jobs.router)
app.include_router(api_documents.router)

HALAMAN = [
    {'path': '/', 'label': 'Dashboard', 'ikon': '▤'},
    {'path': '/skkni', 'label': 'Dokumen SKKNI', 'ikon': '▦'},
    {'path': '/skema', 'label': 'Skema Sertifikasi', 'ikon': '▧'},
    {'path': '/unit', 'label': 'Unit Kompetensi', 'ikon': '▤'},
    {'path': '/ekstraksi', 'label': 'Ekstraksi', 'ikon': '⚙'},
    {'path': '/hasil', 'label': 'Hasil Ekstraksi', 'ikon': '▣'},
]


def _render(request: Request, template: str, **konteks) -> HTMLResponse:
    """Render template dengan konteks navigasi standar."""
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
    resp = _render(
        request, 'skkni.html', judul='Dokumen SKKNI',
        daftar=documents, q=q, pesan=pesan, tipe=tipe, doc_sorot=doc,
        csrf_token=token,
        batas_mb=library.BATAS_UKURAN // (1024 * 1024),
        total_semua=len(library.daftar_dokumen()),
    )
    security.set_cookie_token(resp, token)
    return resp


@app.post('/skkni/upload')
async def unggah_skkni(request: Request,
                       berkas: UploadFile = File(...),
                       csrf_token: str = Form('')):
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

    unit = list(doc.get('units') or [])
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
    resp = _render(
        request, 'skkni_detail.html', judul='Detail SKKNI',
        dok=doc, units=unit[mulai:mulai + BATAS_UNIT_PER_HALAMAN],
        q=q, page=halaman, halaman_total=halaman_total, total_unit=total,
        validasi=validasi, peta_validasi=peta_validasi, manual=manual,
        pesan=pesan, tipe=tipe, csrf_token=token,
    )
    security.set_cookie_token(resp, token)
    return resp


@app.post('/skkni/{doc_id}/verifikasi')
def verifikasi_manual(request: Request, doc_id: str,
                      kode_unit: str = Form(...), csrf_token: str = Form('')):
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
                       csrf_token: str = Form('')):
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
        peta_status=peta_status, q=q, page=halaman, ada_browser=daftar_browser,
        ada_json=ada_json,
        skema_lsp_json=skema_lsp_json, skema_smart_text=skema_smart_text,
        skema_lsp_count=len(skema_lsp_list),
        halaman_total=halaman_total, total_unit=total,
        pesan=pesan, tipe=tipe, csrf_token=token,
    )
    security.set_cookie_token(resp, token)
    return resp


@app.post('/skema/{schema_id}/periksa-ulang')
def periksa_ulang_skema(request: Request, schema_id: str, csrf_token: str = Form('')):
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
                 kode_unit: str = Form(''), csrf_token: str = Form('')):
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
    no_met: str = ''
):
    data = susun_data_buku_kerja(
        schema_id=schema_id,
        no_skema=no_skema,
        nama_asesor=nama_asesor,
        no_met=no_met
    )
    if not data:
        html = _render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                       pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html

    doc_mode = doc.lower() if doc.lower() in ['all', 'apl01', 'apl02'] else 'all'
    judul_map = {
        'all': f"FR.APL.01 & FR.APL.02 - {data['nama_skema']}",
        'apl01': f"FR.APL.01 Permohonan - {data['nama_skema']}",
        'apl02': f"FR.APL.02 Asesmen Mandiri - {data['nama_skema']}",
    }
    judul_halaman = judul_map.get(doc_mode, "Cetak Dokumen APL")

    return _render(
        request, 'cetak_apl.html',
        judul=judul_halaman,
        judul_halaman=judul_halaman,
        data=data,
        doc_mode=doc_mode
    )


@app.get('/skema/{schema_id}/unit/{kode_unit}', response_class=HTMLResponse)
def preview_unit(request: Request, schema_id: str, kode_unit: str):
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

    berkas = jobs.JSON_OUT / f'{kode_unit}.json'
    data = None
    if berkas.exists():
        try:
            data = json.loads(berkas.read_text(encoding='utf-8'))
        except Exception:
            data = None

    unit_skema = next((u for u in dok.get('units') or [] if u['kode_unit'] == kode_unit), None)
    bv = pp = []
    unit_lsp_json = ''
    unit_smart_text = ''
    if data:
        bv = flatten_nodes((data.get('batasan_variabel') or {}).get('sections') or [])
        pp = flatten_nodes((data.get('panduan_penilaian') or {}).get('sections') or [])
        unit_dict = unit_ke_lsp_dict(data)
        unit_lsp_json = json.dumps([unit_dict], ensure_ascii=False, indent=2)
        unit_smart_text = unit_ke_smart_paste_text(data)

    return _render(
        request, 'unit_preview.html', judul='Hasil Ekstraksi Unit',
        dok=dok, kode=kode_unit, data=data, unit_skema=unit_skema,
        bv=bv, pp=pp,
        unit_lsp_json=unit_lsp_json, unit_smart_text=unit_smart_text,
        berkas=str(berkas.relative_to(jobs.ROOT)),
    )


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
                          kode_unit: str = Form(...), csrf_token: str = Form('')):
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
                          csrf_token: str = Form('')):
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

"""Halaman skema sertifikasi, pencocokan, dan ekstraksi.

Dipindahkan dari `app/main.py` (temuan T-19) tanpa mengubah perilaku: decorator
`@app.` menjadi `@router.` dan helper halaman diambil dari `app.web_common`.
"""

import json
import math
from typing import Any, Dict
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app import jobs, schema_library, status_units
from app.api import auth_guard, security
from app.lsp_exporter import skema_ke_lsp_data

from app.services import document_service
from app.logging_config import ambil_logger
from app.web_common import ke_skema, render

#: Jumlah unit per halaman pada daftar panjang (dulu konstanta di app/main.py).
BATAS_UNIT_PER_HALAMAN = 10

logger = ambil_logger(__name__)

router = APIRouter()


@router.get('/skema', response_class=HTMLResponse)
def halaman_skema(request: Request, q: str = '', pesan: str = '', tipe: str = '',
                  doc: str = ''):
    daftar = schema_library.daftar_skema()

    kata = (q or '').strip().lower()
    if kata:
        daftar = [d for d in daftar
                  if kata in ' '.join(str(d.get(k) or '') for k in
                                      ('nama_skema', 'nama_asli', 'jenis_skema')).lower()]

    token = security.token_dari_cookie(request)
    resp = render(
        request, 'skema.html', judul='Skema Sertifikasi',
        daftar=daftar, q=q, pesan=pesan, tipe=tipe, doc_sorot=doc,
        csrf_token=token,
        batas_mb=schema_library.BATAS_UKURAN // (1024 * 1024),
        total_semua=len(schema_library.daftar_skema()),
    )
    security.set_cookie_token(resp, token)
    return resp


@router.post('/skema/upload')
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
        return ke_skema(e.pesan, 'galat')
    except Exception:
        await berkas.close()
        return ke_skema('Unggahan gagal diproses. Periksa berkas lalu coba lagi.', 'galat')
    await berkas.close()

    if duplikat:
        return ke_skema(
            f'Dokumen skema ini sudah ada: {doc.get("nama_skema") or doc.get("nama_asli")}.',
            'info', doc['id'])
    jumlah = doc.get('jumlah_unit', 0)
    if not jumlah:
        return ke_skema('Dokumen tersimpan, tetapi daftar unit tidak dikenali. '
                         'Periksa detail untuk verifikasi manual.', 'galat', doc['id'])
    return ke_skema(f'Skema berhasil diunggah: {jumlah} unit kompetensi terbaca.',
                     'sukses', doc['id'])


@router.get('/skema/{schema_id}', response_class=HTMLResponse)
def detail_skema(request: Request, schema_id: str, q: str = '', page: int = 1,
                 pesan: str = '', tipe: str = ''):
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        html = render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
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
    resp = render(
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


@router.post('/skema/{schema_id}/periksa-ulang')
def periksa_ulang_skema(request: Request, schema_id: str, csrf_token: str = Form(''),
                        pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login())):
    security.periksa_token(request, csrf_token)
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return ke_skema('Skema tidak ditemukan.', 'galat')
    try:
        dok = schema_library.cocokkan_ulang(dok)
    except schema_library.GalatSkema as e:
        return ke_skema(e.pesan, 'galat', schema_id)
    ringkas = (dok.get('hasil_pencocokan') or {}).get('ringkasan') or {}
    return RedirectResponse(
        url=(f"/skema/{schema_id}?tipe=sukses&pesan="
             + quote(f"Pencocokan diperbarui: {ringkas.get('ditemukan', 0)} ditemukan, "
                     f"{ringkas.get('tidak_ditemukan', 0)} belum ditemukan, "
                     f"{ringkas.get('konflik', 0)} konflik.")),
        status_code=303)


@router.post('/skema/{schema_id}/ekstrak')
def ekstrak_unit(request: Request, schema_id: str,
                 kode_unit: str = Form(''), csrf_token: str = Form(''),
                 pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login())):
    security.periksa_token(request, csrf_token)
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return ke_skema('Skema tidak ditemukan.', 'galat')
    try:
        job = jobs.buat_job(dok, kode_unit or None)
    except jobs.GalatJob as e:
        return ke_skema(e.pesan, 'galat', schema_id)
    return RedirectResponse(url=f"/job/{job['id']}", status_code=303)


@router.post('/skema/{schema_id}/verifikasi')
def verifikasi_unit_skema(request: Request, schema_id: str,
                          kode_unit: str = Form(...), csrf_token: str = Form(''),
                          pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login())):
    security.periksa_token(request, csrf_token)
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return ke_skema('Skema tidak ditemukan.', 'galat')
    schema_library.tandai_manual(dok, kode_unit)
    return RedirectResponse(
        url=f'/skema/{schema_id}?tipe=sukses&pesan=' + quote(
            'Unit ditandai terverifikasi manual.'),
        status_code=303)

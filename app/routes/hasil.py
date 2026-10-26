"""Dokumen Word hasil, halaman job, dan status unit.

Dipindahkan dari `app/main.py` (temuan T-19) tanpa mengubah perilaku: decorator
`@app.` menjadi `@router.` dan helper halaman diambil dari `app.web_common`.
"""

from typing import Any, Dict
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import jobs, status_units
from app.api import auth_guard, security

from app.services import document_service
from app.logging_config import ambil_logger
from app.web_common import render

#: Jumlah unit per halaman pada daftar panjang (dulu konstanta di app/main.py).
BATAS_UNIT_PER_HALAMAN = 10

logger = ambil_logger(__name__)

router = APIRouter()


@router.get('/api/unit/{kode_unit}/status')
def api_status_unit(kode_unit: str):
    return status_units.status_unit(kode_unit, wajib_json=True)


@router.get('/job/{job_id}', response_class=HTMLResponse)
def halaman_job(request: Request, job_id: str):
    job = jobs.ambil_job(job_id)
    if not job:
        html = render(request, 'tidak_ditemukan.html', judul='Job tidak ditemukan',
                       pesan='Job ekstraksi tidak ditemukan atau sudah dihapus.')
        html.status_code = 404
        return html
    return render(request, 'skema_job.html', judul='Job Ekstraksi', job=job)


@router.get('/hasil', response_class=HTMLResponse)
def halaman_hasil(request: Request, pesan: str = '', tipe: str = ''):
    return render(request, 'hasil.html', judul='Dokumen Word',
                   daftar=document_service.daftar_dokumen(),
                   pesan=pesan, tipe=tipe)


@router.get('/hasil/{doc_id}', response_class=HTMLResponse)
def detail_dokumen(request: Request, doc_id: str, pesan: str = '', tipe: str = ''):
    meta = document_service.ambil_dokumen(doc_id)
    if not meta:
        html = render(request, 'tidak_ditemukan.html', judul='Dokumen tidak ditemukan',
                       pesan='Dokumen Word tidak ditemukan pada riwayat.')
        html.status_code = 404
        return html
    return render(request, 'hasil_detail.html', judul='Detail Dokumen Word',
                   dok=meta, pesan=pesan, tipe=tipe)


@router.post('/hasil/generate')
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

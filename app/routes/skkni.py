"""Halaman perpustakaan dokumen SKKNI dan aksinya.

Dipindahkan dari `app/main.py` (temuan T-19) tanpa mengubah perilaku: decorator
`@app.` menjadi `@router.` dan helper halaman diambil dari `app.web_common`.
"""

import math
import re
from pathlib import Path
from typing import Any, Dict
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app import db, library, status_units
from app.api import auth_guard, security

from app.logging_config import ambil_logger
from app.web_common import ke_skkni, render

#: Jumlah unit per halaman pada daftar panjang (dulu konstanta di app/main.py).
BATAS_UNIT_PER_HALAMAN = 10

logger = ambil_logger(__name__)

router = APIRouter()


@router.get('/skkni', response_class=HTMLResponse)
def halaman_skkni(request: Request, q: str = '', pesan: str = '', tipe: str = '',
                  doc: str = ''):
    library.pastikan_dokumen_proyek()
    documents = library.daftar_dokumen()

    # Dokumen yang belum diidentifikasi TIDAK lagi diproses di sini: GET tidak
    # boleh menulis (temuan T-25), dan pekerjaan itu membuat waktu buka halaman
    # tumbuh linear dengan jumlah PDF (T-17). Pengguna menjalankannya lewat
    # tombol "Identifikasi" (POST /skkni/{id}/identifikasi).

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

    resp = render(
        request, 'skkni.html', judul='Dokumen SKKNI',
        daftar=documents, q=q, pesan=pesan, tipe=tipe, doc_sorot=doc,
        csrf_token=token,
        batas_mb=library.BATAS_UKURAN // (1024 * 1024),
        total_semua=len(library.daftar_dokumen()),
    )
    security.set_cookie_token(resp, token)
    return resp


@router.post('/skkni/{doc_id}/regulasi')
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
        return ke_skkni('Dokumen SKKNI tidak ditemukan.', 'galat')

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


@router.post('/skkni/upload')
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
        return ke_skkni(e.pesan, 'galat')
    except Exception:
        await berkas.close()
        return ke_skkni('Unggahan gagal diproses. Periksa berkas lalu coba lagi.', 'galat')
    await berkas.close()

    if duplikat:
        return ke_skkni(
            f'Dokumen ini sudah ada di perpustakaan: {doc.get("nama_asli")} '
            f'({doc.get("nomor") or "?"}/{doc.get("tahun") or "?"}).',
            'info', doc['id'])
    return ke_skkni(
        f'PDF berhasil diunggah dan diidentifikasi: {doc.get("jumlah_unit", 0)} unit '
        f'ditemukan.', 'sukses', doc['id'])


@router.get('/skkni/{doc_id}', response_class=HTMLResponse)
def detail_skkni(request: Request, doc_id: str, q: str = '', page: int = 1,
                 pesan: str = '', tipe: str = ''):
    doc = library.ambil_dokumen(doc_id)
    if not doc:
        html = render(request, 'tidak_ditemukan.html', judul='Dokumen tidak ditemukan',
                       pesan='Dokumen SKKNI tidak ditemukan di perpustakaan.')
        html.status_code = 404
        return html

    # GET hanya membaca. Bila data belum ada, halaman menampilkan tombol untuk
    # menjalankannya (POST), bukan diam-diam menulis seperti sebelumnya (T-25).
    belum_diidentifikasi = (
        not doc.get('units')
        and doc.get('status_identifikasi') in ('belum_diproses', None)
    )
    validasi_lama = doc.get('validasi_kelengkapan')
    validasi_basi = bool(doc.get('units')) and (
        not validasi_lama or validasi_lama.get('versi') != 3
    )
    if validasi_basi and validasi_lama:
        # Sudah ada hasil versi lama: tampilkan apa adanya, minta validasi ulang.
        pass

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

    resp = render(
        request, 'skkni_detail.html', judul='Detail SKKNI',
        dok=doc, units=unit[mulai:mulai + BATAS_UNIT_PER_HALAMAN],
        q=q, page=halaman, halaman_total=halaman_total, total_unit=total,
        validasi=validasi, peta_validasi=peta_validasi, manual=manual,
        peta_status_3=peta_status_3, ringkasan_status_3=ringkasan_status_3,
        status_regulasi=status_reg, kepmen_pengganti=kepmen_ganti, catatan_regulasi=catatan_reg,
        pesan=pesan, tipe=tipe, csrf_token=token,
        belum_diidentifikasi=belum_diidentifikasi, validasi_basi=validasi_basi,
    )
    security.set_cookie_token(resp, token)
    return resp


@router.get('/skkni/{doc_id}/pdf')
def buka_pdf_skkni(request: Request, doc_id: str):
    doc = library.ambil_dokumen(doc_id)
    if not doc:
        html = render(request, 'tidak_ditemukan.html', judul='Dokumen tidak ditemukan',
                       pesan='Dokumen SKKNI tidak ditemukan di perpustakaan.')
        html.status_code = 404
        return html
    try:
        jalur = library.jalur_pdf(doc)
    except library.GalatUpload as e:
        html = render(request, 'tidak_ditemukan.html', judul='Berkas PDF tidak ditemukan',
                       pesan=e.pesan)
        html.status_code = e.kode
        return html
    nama_aman = re.sub(r'[^A-Za-z0-9._ -]+', '_', Path(doc.get('nama_asli') or 'skkni.pdf').name)
    return FileResponse(
        path=str(jalur),
        media_type='application/pdf',
        headers={'Content-Disposition': f'inline; filename="{nama_aman}"'},
    )


@router.post('/skkni/{doc_id}/identifikasi')
def identifikasi_ulang_skkni(request: Request, doc_id: str,
                             csrf_token: str = Form(''),
                             pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login())):
    """Menjalankan identifikasi unit secara eksplisit (bukan efek samping GET)."""
    security.periksa_token(request, csrf_token)
    doc = library.ambil_dokumen(doc_id)
    if not doc:
        return ke_skkni('Dokumen SKKNI tidak ditemukan.', 'galat')
    doc = library.identifikasi(doc)
    pesan = (f"Identifikasi selesai: {doc.get('jumlah_unit', 0)} unit dikenali."
             if doc.get('status_identifikasi') == 'lengkap'
             else doc.get('pesan_identifikasi') or 'Identifikasi selesai dengan catatan.')
    return RedirectResponse(
        url=f'/skkni/{doc_id}?tipe=sukses&pesan={quote(pesan)}', status_code=303)


@router.post('/skkni/{doc_id}/validasi')
def validasi_ulang_skkni(request: Request, doc_id: str,
                         csrf_token: str = Form(''),
                         pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login())):
    """Menjalankan pemeriksaan kelengkapan KUK secara eksplisit."""
    security.periksa_token(request, csrf_token)
    doc = library.ambil_dokumen(doc_id)
    if not doc:
        return ke_skkni('Dokumen SKKNI tidak ditemukan.', 'galat')
    if not doc.get('units'):
        return ke_skkni('Jalankan identifikasi unit lebih dulu.', 'galat', doc_id)
    doc = library.jalankan_validator(doc)
    ringkas = (doc.get('validasi_kelengkapan') or {}).get('ringkasan') or {}
    return RedirectResponse(
        url=f'/skkni/{doc_id}?tipe=sukses&pesan=' + quote(
            f"Validasi kelengkapan selesai: {ringkas.get('jumlah_unit_lengkap', 0)} unit lengkap, "
            f"{ringkas.get('jumlah_unit_hilang', 0)} unit perlu diperiksa."),
        status_code=303)


@router.post('/skkni/{doc_id}/verifikasi')
def verifikasi_manual(request: Request, doc_id: str,
                      kode_unit: str = Form(...), csrf_token: str = Form(''),
                      pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login())):
    security.periksa_token(request, csrf_token)
    doc = library.ambil_dokumen(doc_id)
    if not doc:
        return render(request, 'tidak_ditemukan.html', judul='Dokumen tidak ditemukan',
                       pesan='Dokumen SKKNI tidak ditemukan di perpustakaan.')
    library.tandai_manual(doc, kode_unit)
    return RedirectResponse(
        url=f'/skkni/{doc_id}?pesan={quote("Unit ditandai terverifikasi manual.")}&tipe=sukses',
        status_code=303)

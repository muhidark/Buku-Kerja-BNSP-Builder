"""Halaman skema sertifikasi, pencocokan, dan ekstraksi.

Dipindahkan dari `app/main.py` (temuan T-19) tanpa mengubah perilaku: decorator
`@app.` menjadi `@router.` dan helper halaman diambil dari `app.web_common`.
"""

import json
import math
from typing import Any, Dict, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app import db, jobs, schema_library, status_units
from app.api import auth_guard, keamanan_http, security
from app.lsp_exporter import skema_ke_lsp_data

from app.services import document_service
from app.logging_config import ambil_logger
from app.web_common import ke_skema, render

#: Jumlah unit per halaman pada daftar panjang (dulu konstanta di app/main.py).
BATAS_UNIT_PER_HALAMAN = 10

logger = ambil_logger(__name__)

router = APIRouter()


def pastikan_hak_akses_skema(doc: dict, request: Request, aksi_tulis: bool = False) -> Optional[dict]:
    """Isolasi Data LSP / Multi-Tenancy:
    Memastikan skema dan MUK hanya dapat diakses/diubah oleh pemiliknya atau peran Admin."""
    pengguna = auth_guard.pengguna_dari_request(request)
    doc_owner = doc.get('owner_id')

    # Jika skema belum berpemilik (temporary guest session / skema awal)
    if not doc_owner:
        return pengguna

    # Jika skema telah berpemilik, akses wajib login
    if not pengguna:
        raise HTTPException(
            status_code=403,
            detail="Instrumen skema ini adalah rahasia kerja pengguna terdaftar. Silakan masuk terlebih dahulu."
        )

    # Hanya pemilik skema atau Admin yang berhak melihat dan memodifikasi
    if pengguna.get('peran') != 'admin' and doc_owner != pengguna['id']:
        raise HTTPException(
            status_code=403,
            detail="Akses Ditolak: Anda tidak memiliki izin untuk melihat atau mengelola instrumen skema milik pengguna lain."
        )

    return pengguna


@router.get('/skema', response_class=HTMLResponse)
def halaman_skema(request: Request, q: str = '', pesan: str = '', tipe: str = '',
                  doc: str = ''):
    pengguna = auth_guard.pengguna_dari_request(request)
    is_admin = bool(pengguna and pengguna.get('peran') == 'admin')
    owner_id = pengguna['id'] if pengguna else None

    # Multi-tenancy: Hanya tampilkan skema milik pengguna saat ini (atau semua skema bila Admin)
    semua_skema = schema_library.daftar_skema(owner_id=owner_id, is_admin=is_admin)
    kata = (q or '').strip().lower()

    from app import buku_kerja, status_units

    enriched_daftar = []
    total_unit_semua = 0
    total_siap_unduh = 0

    for d in semua_skema:
        sid = d.get('id')
        if not sid:
            continue

        if kata:
            gabungan_teks = ' '.join(str(d.get(k) or '') for k in ('nama_skema', 'nama_asli', 'jenis_skema', 'nomor_dokumen')).lower()
            if kata not in gabungan_teks:
                continue

        try:
            gerbang = status_units.evaluasi_gerbang_skema(sid)
            ada_gagal = gerbang.get('ada_gagal', False)
        except Exception:
            gerbang = {'ada_gagal': False, 'status': 'siap'}
            ada_gagal = False

        units = d.get('units') or []
        jumlah_unit = len(units) if units else (d.get('jumlah_unit') or 0)
        total_unit_semua += jumlah_unit

        try:
            cfg = buku_kerja.muat_konfigurasi_muk(sid, d.get('nama_skema') or '', units)
            kelompok = cfg.get('kelompok_pekerjaan') or []
            metode_mapa = (cfg.get('personel') or {}).get('metode_mapa') or 'observasi'
        except Exception:
            kelompok = []
            metode_mapa = 'observasi'

        siap_unduh = (not ada_gagal) and (jumlah_unit > 0)
        if siap_unduh:
            total_siap_unduh += 1

        d_copy = dict(d)
        d_copy['jumlah_unit_final'] = jumlah_unit
        d_copy['jumlah_kelompok'] = len(kelompok)
        d_copy['metode_mapa'] = metode_mapa
        d_copy['siap_unduh'] = siap_unduh
        d_copy['gerbang'] = gerbang
        enriched_daftar.append(d_copy)

    token = security.token_dari_cookie(request)
    resp = render(
        request, 'skema.html',
        judul='Katalog Buku Kerja Berdasarkan Skema Asesmen',
        daftar=enriched_daftar,
        q=q,
        pesan=pesan,
        tipe=tipe,
        doc_sorot=doc,
        csrf_token=token,
        batas_mb=schema_library.BATAS_UKURAN // (1024 * 1024),
        total_semua=len(semua_skema),
        total_unit_semua=total_unit_semua,
        total_siap_unduh=total_siap_unduh,
        pengguna_aktif=pengguna,
    )
    security.set_cookie_token(resp, token)
    return resp


@router.post('/skema/{schema_id}/hapus')
def hapus_skema_route(request: Request, schema_id: str):
    """Hapus dokumen skema dan seluruh berkas Buku Kerja terkait."""
    dok = schema_library.ambil_skema(schema_id)
    if dok:
        pastikan_hak_akses_skema(dok, request, aksi_tulis=True)
    sukses = schema_library.hapus_skema(schema_id)
    if sukses:
        return RedirectResponse(url='/skema?tipe=sukses&pesan=' + quote('Skema sertifikasi berhasil dihapus.'), status_code=303)
    return RedirectResponse(url='/skema?tipe=galat&pesan=' + quote('Gagal menghapus skema sertifikasi.'), status_code=303)


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
            schema_library.unggah, berkas.filename, berkas.file, berkas.size, pengguna['id'], pengguna['username'])
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



# --------------------------------------------------------------------------
# Alur Baru: Skema -> Cek Unit -> (Upload SKKNI jika kurang) -> Siap Unduh
# --------------------------------------------------------------------------

@router.post('/skema/unggah-alur')
async def unggah_skema_alur(request: Request,
                            berkas: UploadFile = File(...),
                            csrf_token: str = Form('')):
    """Unggah skema dari landing page: mengarahkan ke upload SKKNI atau siap unduh."""
    try:
        if not berkas.filename:
            return JSONResponse({'sukses': False, 'pesan': 'Berkas belum dipilih.'}, status_code=400)
        pengguna = auth_guard.pengguna_dari_request(request)
        owner_id = pengguna['id'] if pengguna else None
        owner_username = pengguna['username'] if pengguna else None
        doc, _duplikat = await run_in_threadpool(
            schema_library.unggah, berkas.filename, berkas.file, berkas.size, owner_id, owner_username)
    except schema_library.GalatSkema as e:
        await berkas.close()
        return JSONResponse({'sukses': False, 'pesan': e.pesan}, status_code=400)
    except Exception as e:
        await berkas.close()
        logger.error(f"Gagal memproses unggah skema: {e}")
        return JSONResponse({'sukses': False, 'pesan': 'Dokumen skema gagal diproses.'}, status_code=500)
    await berkas.close()

    schema_id = doc['id']
    peta_dasar = schema_library.peta_kelengkapan()
    units = doc.get('units') or []
    
    unit_kurang = []
    for u in units:
        st = schema_library.status_unit(doc, u['kode_unit'], peta_dasar)
        if not st.get('teridentifikasi'):
            unit_kurang.append(u)

    if unit_kurang:
        tujuan_url = f"/skema/{schema_id}/upload-skkni"
        return JSONResponse({
            'sukses': True,
            'schema_id': schema_id,
            'nama_skema': doc.get('nama_skema') or doc.get('nama_asli'),
            'total_unit': len(units),
            'unit_kurang': len(unit_kurang),
            'tujuan_url': tujuan_url,
        })
    else:
        # Jika semua unit sudah teridentifikasi, jalankan job ekstraksi jika ada yang belum diekstrak
        try:
            jobs.buat_job(doc)
        except Exception:
            pass
        tujuan_url = f"/skema/{schema_id}/siap-unduh"
        return JSONResponse({
            'sukses': True,
            'schema_id': schema_id,
            'nama_skema': doc.get('nama_skema') or doc.get('nama_asli'),
            'total_unit': len(units),
            'unit_kurang': 0,
            'tujuan_url': tujuan_url,
        })


@router.get('/skema/{schema_id}/upload-skkni', response_class=HTMLResponse)
def halaman_upload_skkni_alur(request: Request, schema_id: str):
    """Tampilan langkah 2a: jika unit kompetensi belum ada dokumen SKKNI-nya."""
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        html = render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                      pesan='Dokumen skema tidak ditemukan di sistem.')
        html.status_code = 404
        return html

    peta_dasar = schema_library.peta_kelengkapan()
    unit_kurang = []
    unit_lengkap = []
    for u in dok.get('units') or []:
        st = schema_library.status_unit(dok, u['kode_unit'], peta_dasar)
        if not st.get('teridentifikasi'):
            unit_kurang.append(u)
        else:
            unit_lengkap.append(u)

    # Bila semua unit sudah lengkap, langsung arahkan ke layar siap unduh
    if not unit_kurang:
        return RedirectResponse(url=f"/skema/{schema_id}/siap-unduh", status_code=303)

    token = security.token_dari_cookie(request)
    resp = render(
        request, 'alur_upload_skkni.html',
        judul='Lengkapi Dokumen SKKNI',
        dok=dok,
        unit_kurang=unit_kurang,
        unit_lengkap=unit_lengkap,
        csrf_token=token,
    )
    security.set_cookie_token(resp, token)
    return resp


@router.post('/skema/{schema_id}/set-metode-mapa')
async def set_metode_mapa(request: Request, schema_id: str):
    """Simpan pilihan metode asesmen MAPA (observasi / dit / portofolio)."""
    try:
        body = await request.json()
        metode = str(body.get('metode_mapa') or 'observasi').strip().lower()
    except Exception:
        metode = 'observasi'

    if metode not in ('observasi', 'dit', 'portofolio'):
        return JSONResponse({'sukses': False, 'pesan': 'Pilihan metode asesmen tidak valid.'}, status_code=400)

    from app import buku_kerja
    buku_kerja.simpan_konfigurasi_muk(schema_id, {'personel': {'metode_mapa': metode}})
    return JSONResponse({'sukses': True, 'metode_mapa': metode, 'pesan': f'Pendekatan asesmen berhasil diubah ke: {metode.upper()}'})


@router.post('/skema/{schema_id}/simpan-muk-bagian')
async def simpan_muk_bagian(request: Request, schema_id: str):
    """Menyimpan pembaruan sebagian konfigurasi MUK (IA.02 s/d IA.08) via AJAX dari formulir pemeriksaan."""
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return JSONResponse({'sukses': False, 'pesan': 'Skema tidak ditemukan.'}, status_code=404)
    pastikan_hak_akses_skema(dok, request, aksi_tulis=True)

    try:
        payload = await request.json()
    except Exception as e:
        return JSONResponse({'sukses': False, 'pesan': f'Format data tidak valid: {e}'}, status_code=400)

    if not isinstance(payload, dict):
        return JSONResponse({'sukses': False, 'pesan': 'Payload harus berupa objek JSON.'}, status_code=400)

    from app import buku_kerja
    try:
        buku_kerja.simpan_konfigurasi_muk(schema_id, payload)
    except Exception as e:
        logger.error(f"Gagal simpan_muk_bagian: {e}")
        return JSONResponse({'sukses': False, 'pesan': f'Gagal menyimpan konfigurasi MUK: {e}'}, status_code=500)

    return JSONResponse({
        'sukses': True,
        'pesan': 'Perubahan instrumen berhasil disimpan dan diterapkan ke dokumen cetak A4.'
    })


@router.post('/skema/{schema_id}/unggah-skkni-alur')
async def unggah_skkni_alur(request: Request, schema_id: str,
                            berkas: UploadFile = File(...),
                            csrf_token: str = Form('')):
    """Unggah SKKNI PDF, verifikasi status regulasi Kemnaker RI, dan ekstrak unit."""
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return JSONResponse({'sukses': False, 'pesan': 'Skema tidak ditemukan.'}, status_code=404)

    try:
        from app import library
        from app.services import kemnaker_sync
        if not berkas.filename:
            return JSONResponse({'sukses': False, 'pesan': 'Berkas belum dipilih.'}, status_code=400)
        
        doc_skkni, _duplikat = await run_in_threadpool(
            library.unggah, berkas.filename, berkas.file, berkas.size)
        
        # Validasi otomatis ke Kemnaker RI
        try:
            kemnaker_sync.sinkronkan_dokumen_tunggal(doc_skkni['id'])
            dok_cek = library.ambil_dokumen(doc_skkni['id'])
            if dok_cek:
                doc_skkni = dok_cek
        except Exception as e:
            logger.warning(f"Gagal sinkronisasi Kemnaker: {e}")

        st_reg = str(doc_skkni.get('status_regulasi') or '').lower()
        if st_reg == 'dicabut':
            # STOP: Regulasi dicabut
            return JSONResponse({
                'sukses': False,
                'dicabut': True,
                'nomor_kepmen': doc_skkni.get('nomor_kepmen') or doc_skkni.get('nomor'),
                'tahun': doc_skkni.get('tahun'),
                'pengganti': doc_skkni.get('kepmen_pengganti') or doc_skkni.get('catatan_regulasi'),
                'pesan': 'SKKNI telah DICABUT oleh Kemnaker RI.',
            })

        # Jika masih berlaku: cocokkan ulang skema
        dok = schema_library.cocokkan_ulang(dok)

        # Jalankan ekstraksi unit
        try:
            jobs.buat_job(dok)
        except Exception as e:
            logger.warning(f"Job ekstraksi: {e}")

        # Periksa sisa unit yang belum ada SKKNI
        peta_dasar = schema_library.peta_kelengkapan()
        sisa_kurang = [
            u for u in dok.get('units') or []
            if not schema_library.status_unit(dok, u['kode_unit'], peta_dasar).get('teridentifikasi')
        ]

        if not sisa_kurang:
            return JSONResponse({
                'sukses': True,
                'selesai': True,
                'redirect_url': f"/skema/{schema_id}/siap-unduh",
                'pesan': 'Dokumen SKKNI valid! Seluruh unit kompetensi kini telah lengkap.',
            })
        else:
            return JSONResponse({
                'sukses': True,
                'selesai': False,
                'sisa': len(sisa_kurang),
                'pesan': f"Dokumen SKKNI valid! Tersisa {len(sisa_kurang)} unit yang masih membutuhkan SKKNI.",
            })

    except Exception as e:
        logger.error(f"Gagal upload SKKNI alur: {e}")
        return JSONResponse({'sukses': False, 'pesan': f"Gagal memproses berkas: {e}"}, status_code=500)
    finally:
        await berkas.close()


@router.get('/skema/{schema_id}/siap-unduh', response_class=HTMLResponse)
def halaman_siap_unduh(request: Request, schema_id: str):
    """Tampilan langkah 2b: Dokumen SKKNI terekstraksi, verifikasi mutu, & siap diunduh."""
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        html = render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                      pesan='Dokumen skema tidak ditemukan di sistem.')
        html.status_code = 404
        return html

    units = dok.get('units') or []
    gerbang = status_units.evaluasi_gerbang_skema(schema_id)
    ringkasan = gerbang.get('ringkasan') or {'total': len(units), 'siap': 0, 'perlu': 0, 'gagal': 0}
    daftar_unit = gerbang.get('daftar_unit') or []
    total_u = max(1, ringkasan.get('total', 1))
    persen_siap = round((ringkasan.get('siap', 0) / total_u) * 100)

    lsp_list, _ = skema_ke_lsp_data(dok)
    peta_lsp = {u['kode_unit']: u for u in lsp_list}

    total_elemen = 0
    total_kuk = 0
    for u in units:
        kd = u['kode_unit']
        data_lsp = peta_lsp.get(kd)
        if data_lsp:
            total_elemen += len(data_lsp.get('elemen', []))
            total_kuk += sum(len(el.get('kuk', [])) for el in data_lsp.get('elemen', []))

    token = security.token_dari_cookie(request)
    from app import buku_kerja
    cfg_muk = buku_kerja.muat_konfigurasi_muk(
        schema_id, dok.get('nama_skema') or '', [], dok.get('nomor_dokumen') or ''
    )
    personel = cfg_muk.get('personel') or {}

    resp = render(
        request, 'alur_siap_unduh.html',
        judul='Dokumen Siap Diunduh',
        dok=dok,
        gerbang=gerbang,
        ringkasan=ringkasan,
        persen_siap=persen_siap,
        daftar_unit=daftar_unit,
        total_unit=len(units),
        total_elemen=total_elemen,
        total_kuk=total_kuk,
        personel=personel,
        csrf_token=token,
    )
    security.set_cookie_token(resp, token)
    return resp


@router.post('/skema/{schema_id}/simpan-identitas-muk')
async def simpan_identitas_muk(request: Request, schema_id: str):
    """Simpan identitas asesi, TUK, skema, asesor, penyusun, dan validator sebelum masuk ke MUK."""
    form = await request.form()
    nama_penyusun = str(form.get('nama_penyusun') or '').strip()
    met_penyusun = str(form.get('met_penyusun') or '').strip()
    nama_validator = str(form.get('nama_validator') or '').strip()
    met_validator = str(form.get('met_validator') or '').strip()

    if not nama_penyusun or not met_penyusun:
        return JSONResponse({'sukses': False, 'pesan': 'Nama Penyusun dan No. MET Penyusun wajib diisi.'}, status_code=400)
    if not nama_validator or not met_validator:
        return JSONResponse({'sukses': False, 'pesan': 'Nama Validator dan No. MET Validator wajib diisi.'}, status_code=400)

    from app import buku_kerja
    payload = {
        'personel': {
            'nama_asesi': str(form.get('nama_asesi') or '').strip(),
            'nama_tuk': str(form.get('nama_tuk') or '').strip(),
            'nomor_skema': str(form.get('nomor_skema') or '').strip(),
            'skema_sertifikasi': str(form.get('skema_sertifikasi') or '').strip(),
            'nama_asesor': str(form.get('nama_asesor') or '').strip(),
            'no_met': str(form.get('no_met_asesor') or '').strip(),
            'nama_penyusun': nama_penyusun,
            'met_penyusun': met_penyusun,
            'nama_validator': nama_validator,
            'met_validator': met_validator,
        }
    }
    buku_kerja.simpan_konfigurasi_muk(schema_id, payload)
    return JSONResponse({
        'sukses': True,
        'redirect_url': f'/skema/{schema_id}/kelompok-kerja',
        'pesan': 'Identitas Buku Kerja berhasil disimpan.'
    })


@router.get('/skema/{schema_id}/kelompok-kerja', response_class=HTMLResponse)
def halaman_kelompok_kerja(request: Request, schema_id: str):
    """Halaman penyusunan Kelompok Kerja (Kelompok Pekerjaan) Asesmen V.2023."""
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        html = render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                      pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html
    pastikan_hak_akses_skema(dok, request)

    from app.buku_kerja import susun_data_buku_kerja
    data = susun_data_buku_kerja(schema_id=schema_id)
    kp_info = data.get('kelompok_pekerjaan') or {}
    muk_raw = data.get('muk_raw') or {}
    raw_kp = muk_raw.get('kelompok_pekerjaan') or []

    daftar_unit = data.get('daftar_unit') or []
    if not raw_kp and daftar_unit:
        raw_kp = [{
            'id': 'kp_1',
            'nama': f"Kelompok Pekerjaan 1 ({dok.get('nama_skema', '')})",
            'urutan': 1,
            'units': [u['kode_unit'] for u in daftar_unit]
        }]

    token = security.token_dari_cookie(request)
    resp = render(
        request, 'alur_kelompok_kerja.html',
        judul=f"Penyusunan Kelompok Kerja - {dok.get('nama_skema', '')}",
        dok=dok,
        data=data,
        daftar_unit=daftar_unit,
        raw_kp=raw_kp,
        kp_info=kp_info,
        csrf_token=token,
    )
    security.set_cookie_token(resp, token)
    return resp


@router.post('/skema/{schema_id}/simpan-kelompok-kerja')
async def simpan_kelompok_kerja(request: Request, schema_id: str):
    """Simpan struktur kelompok pekerjaan sebelum mengunduh Buku Kerja."""
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return JSONResponse({'sukses': False, 'pesan': 'Skema tidak ditemukan.'}, status_code=404)

    content_type = request.headers.get('content-type', '')
    if 'application/json' in content_type:
        body = await request.json()
        groups = body.get('kelompok_pekerjaan') or []
    else:
        form = await request.form()
        kp_json_str = form.get('kelompok_pekerjaan_json')
        if kp_json_str:
            groups = json.loads(str(kp_json_str))
        else:
            groups = []

    if not groups:
        return JSONResponse({'sukses': False, 'pesan': 'Kelompok pekerjaan minimal harus memiliki 1 kelompok.'}, status_code=400)

    from app import buku_kerja
    payload = {'kelompok_pekerjaan': groups}
    buku_kerja.simpan_konfigurasi_muk(schema_id, payload)

    return JSONResponse({
        'sukses': True,
        'redirect_url': f'/skema/{schema_id}/pemeriksaan',
        'pesan': 'Kelompok kerja berhasil disimpan. Melanjutkan ke Pemeriksaan Dokumen...'
    })


@router.get('/skema/{schema_id}/pemeriksaan', response_class=HTMLResponse)
def halaman_pemeriksaan_dokumen(request: Request, schema_id: str, doc: str = 'daftar_periksa', metode_mapa: str = ''):
    """Halaman pemeriksaan step-by-step instrumen formulir mengacu pada 0_Daftar Periksa Kelengkapan Dokumen Upgrading-RCC."""
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        html = render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                      pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html
    pastikan_hak_akses_skema(dok, request)

    from app.buku_kerja import susun_data_buku_kerja, ambil_daftar_periksa_rcc
    data = susun_data_buku_kerja(schema_id=schema_id, metode_mapa=metode_mapa)
    if not data:
        html = render(request, 'tidak_ditemukan.html', judul='Data Skema tidak lengkap',
                      pesan='Tidak dapat menyusun data Buku Kerja.')
        html.status_code = 500
        return html

    # Susun daftar periksa lengkap 27 butir resmi Upgrading-RCC BNSP
    daftar_periksa = ambil_daftar_periksa_rcc(schema_id, dok)

    # Cari item aktif berdasarkan 'id' atau 'doc_code'
    clean_doc = (doc or 'daftar_periksa').strip().lower()
    item_aktif = next((item for item in daftar_periksa if item['id'].lower() == clean_doc or (item.get('doc_code') and item['doc_code'].lower() == clean_doc)), None)
    if not item_aktif:
        item_aktif = daftar_periksa[0]

    active_idx = daftar_periksa.index(item_aktif)
    prev_item = daftar_periksa[active_idx - 1] if active_idx > 0 else None
    next_item = daftar_periksa[active_idx + 1] if active_idx < len(daftar_periksa) - 1 else None

    # Kelompokkan tahapan untuk sidebar
    kategori_map = {}
    for it in daftar_periksa:
        kat = it['kategori']
        if kat not in kategori_map:
            kategori_map[kat] = []
        kategori_map[kat].append(it)

    tahapan_grouped = [{"kategori": k, "dokumen_list": v} for k, v in kategori_map.items()]

    token = security.token_dari_cookie(request)
    resp = render(
        request, 'alur_pemeriksaan_dokumen.html',
        judul=f"Pemeriksaan Dokumen: {item_aktif['kode']} - {dok.get('nama_skema', '')}",
        dok=dok,
        data=data,
        daftar_periksa=daftar_periksa,
        tahapan_grouped=tahapan_grouped,
        item_aktif=item_aktif,
        active_idx=active_idx,
        prev_item=prev_item,
        next_item=next_item,
        total_items=len(daftar_periksa),
        csrf_token=token,
    )
    security.set_cookie_token(resp, token)
    return resp


@router.get('/skema/{schema_id}/unduh-buku-kerja', response_class=HTMLResponse)
def halaman_unduh_buku_kerja(request: Request, schema_id: str):
    """Halaman pengunduhan Buku Kerja Asesor V.2023 lengkap (ZIP, Gabungan DOCX, & 24 Satuan)."""
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        html = render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                      pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html
    pastikan_hak_akses_skema(dok, request)

    from app.buku_kerja import susun_data_buku_kerja
    data = susun_data_buku_kerja(schema_id=schema_id)
    personel = (data.get('muk_raw') or {}).get('personel') or {}

    tahapan_dokumen = [
        {
            "kategori": "Tahap 0: Ceklis Verifikasi Kelengkapan",
            "deskripsi": "Daftar periksa kelengkapan seluruh dokumen pelatihan Upgrading-RCC Asesor Kompetensi",
            "ikon": "list-checks",
            "badge_color": "bg-purple-50 text-purple-700 border-purple-200",
            "dokumen_list": [
                {"kode": "daftar_periksa", "nomor": "0. DAFTAR PERIKSA", "judul": "Daftar Periksa Kelengkapan Dokumen Upgrading-RCC", "tipe": "Ceklis Master", "berkas": "00_DAFTAR_PERIKSA_KELENGKAPAN_DOKUMEN_PELATIHAN_UPGRADING-RCC.docx"},
            ]
        },
        {
            "kategori": "Tahap 1: Pendaftaran & Asesmen Mandiri",
            "deskripsi": "Instrumen administratif pendaftaran peserta dan asesmen mandiri oleh asesi (FR.APL)",
            "ikon": "file-check-2",
            "badge_color": "bg-blue-50 text-blue-700 border-blue-200",
            "dokumen_list": [
                {"kode": "apl01", "nomor": "FR.APL.01", "judul": "Permohonan Sertifikasi Kompetensi", "tipe": "Administrasi", "berkas": "01_FR.APL.01_Permohonan_Sertifikasi_Kompetensi.docx"},
                {"kode": "apl02", "nomor": "FR.APL.02", "judul": "Asesmen Mandiri", "tipe": "Asesmen Diri", "berkas": "02_FR.APL.02_Asesmen_Mandiri.docx"},
            ]
        },
        {
            "kategori": "Tahap 2: Perencanaan & Instrumen Asesmen (MAPA)",
            "deskripsi": "Perencanaan aktivitas asesmen, pemetaan kelompok pekerjaan, penyesuaian wajar, dan persetujuan asesmen",
            "ikon": "clipboard-list",
            "badge_color": "bg-indigo-50 text-indigo-700 border-indigo-200",
            "dokumen_list": [
                {"kode": "mapa01", "nomor": "FR.MAPA.01", "judul": "Merencanakan Aktivitas dan Proses Asesmen", "tipe": "Rencana Asesmen", "berkas": "04_FR.MAPA.01_Merencanakan_Aktivitas_dan_Proses_Asesmen.docx"},
                {"kode": "skema_dok", "nomor": "SKEMA", "judul": "Dokumen Skema Sertifikasi (Unggahan)", "tipe": "Dokumen Skema", "berkas": "05a_Dokumen_Skema_Sertifikasi.docx"},
                {"kode": "skkni_dok", "nomor": "SKKNI", "judul": "Dokumen Standar Kompetensi Kerja (SKKNI)", "tipe": "Dokumen Standar", "berkas": "05b_Dokumen_Standar_Kompetensi_Kerja_SKKNI.docx"},
                {"kode": "peta_kelompok", "nomor": "PETA-KP", "judul": "Peta Kelompok Pekerjaan", "tipe": "Struktur KP", "berkas": "05c_Peta_Kelompok_Pekerjaan.docx"},
                {"kode": "mapa02", "nomor": "FR.MAPA.02", "judul": "Peta Instrumen Asesmen", "tipe": "Matriks Bukti", "berkas": "06_FR.MAPA.02_Peta_Instrumen_Asesmen.docx"},
                {"kode": "ak07", "nomor": "FR.AK.07", "judul": "Ceklis Penyesuaian yang Wajar dan Beralasan", "tipe": "Penyesuaian", "berkas": "07_FR.AK.07_Ceklis_Penyesuaian_Wajar_dan_Beralasan.docx"},
                {"kode": "ak04", "nomor": "FR.AK.04", "judul": "Banding Asesmen", "tipe": "Prosedur Banding", "berkas": "08_FR.AK.04_Banding_Asesmen.docx"},
                {"kode": "ak01", "nomor": "FR.AK.01", "judul": "Persetujuan Asesmen dan Kerahasiaan", "tipe": "Persetujuan", "berkas": "09_FR.AK.01_Persetujuan_Asesmen_dan_Kerahasiaan.docx"},
            ]
        },
        {
            "kategori": "Tahap 3: Pelaksanaan & Materi Uji Kompetensi (IA / MUK)",
            "deskripsi": "Instrumen uji praktik demonstrasi, observasi tempat kerja, tugas proyek terstruktur, pertanyaan tertulis PG/esai, lisan, dan portofolio",
            "ikon": "file-code-2",
            "badge_color": "bg-amber-50 text-amber-700 border-amber-200",
            "dokumen_list": [
                {"kode": "ia01", "nomor": "FR.IA.01", "judul": "CL: Ceklis Observasi Aktivitas di Tempat Kerja", "tipe": "Observasi Langsung", "berkas": "10_FR.IA.01_CL_Ceklis_Observasi_Aktivitas.docx"},
                {"kode": "ia02", "nomor": "FR.IA.02", "judul": "TPD: Tugas Praktik Demonstrasi", "tipe": "Demonstrasi Praktik", "berkas": "11_FR.IA.02_TPD_Tugas_Praktik_Demonstrasi.docx"},
                {"kode": "ia03", "nomor": "FR.IA.03", "judul": "PMO: Pertanyaan Untuk Mendukung Observasi", "tipe": "Tanya Jawab Lisan", "berkas": "12_FR.IA.03_PMO_Pertanyaan_Mendukung_Observasi.docx"},
                {"kode": "ia04a", "nomor": "FR.IA.04A", "judul": "DIT: Penjelasan Proyek Singkat / Studi Kasus", "tipe": "Instruksi Proyek", "berkas": "13a_FR.IA.04A_DIT_Penjelasan_Proyek_Singkat.docx"},
                {"kode": "ia04b", "nomor": "FR.IA.04B", "judul": "DIT: Lembar Penilaian Proyek Singkat", "tipe": "Rubrik Penilaian", "berkas": "13b_FR.IA.04B_DIT_Penilaian_Proyek_Singkat.docx"},
                {"kode": "ia05a", "nomor": "FR.IA.05A", "judul": "DPT: Pertanyaan Tertulis Pilihan Ganda", "tipe": "Lembar Soal PG", "berkas": "14a_FR.IA.05A_DPT_Pertanyaan_Tertulis_Pilihan_Ganda.docx"},
                {"kode": "ia05b", "nomor": "FR.IA.05B", "judul": "Lembar Kunci Jawaban Pilihan Ganda", "tipe": "Kunci Asesor", "berkas": "14b_FR.IA.05B_Kunci_Jawaban_Pilihan_Ganda.docx"},
                {"kode": "ia05c", "nomor": "FR.IA.05C", "judul": "Lembar Jawaban Asesi Pilihan Ganda", "tipe": "Lembar Asesi", "berkas": "14c_FR.IA.05C_Lembar_Jawaban_Pilihan_Ganda.docx"},
                {"kode": "ia06a", "nomor": "FR.IA.06A", "judul": "DPT: Pertanyaan Tertulis Esai", "tipe": "Lembar Soal Esai", "berkas": "15a_FR.IA.06A_DPT_Pertanyaan_Tertulis_Esai.docx"},
                {"kode": "ia06b", "nomor": "FR.IA.06B", "judul": "Lembar Kunci Jawaban Pertanyaan Tertulis Esai", "tipe": "Kunci Asesor", "berkas": "15b_FR.IA.06.B_Kunci_Jawaban_Pertanyaan_Tertulis_Esai.docx"},
                {"kode": "ia06c", "nomor": "FR.IA.06C", "judul": "Lembar Jawaban Asesi Pertanyaan Tertulis Esai", "tipe": "Lembar Asesi", "berkas": "15c_FR.IA.06.C_Lembar_Jawaban_Pertanyaan_Tertulis_Esai.docx"},
                {"kode": "ia07", "nomor": "FR.IA.07", "judul": "DPL: Daftar Pertanyaan Lisan", "tipe": "Tanya Jawab Lisan", "berkas": "16_FR.IA.07_DPL_Daftar_Pertanyaan_Lisan.docx"},
                {"kode": "ia08", "nomor": "FR.IA.08", "judul": "CVP: Ceklis Verifikasi Portofolio", "tipe": "Portofolio", "berkas": "17_FR.IA.08_CVP_Ceklis_Verifikasi_Portofolio.docx"},
            ]
        },
        {
            "kategori": "Tahap 4: Rekomendasi, Laporan & Validasi Asesmen",
            "deskripsi": "Rekaman asesmen kompetensi, formulir umpan balik, laporan akhir asesmen, kaji ulang, dan kontribusi validasi",
            "ikon": "award",
            "badge_color": "bg-emerald-50 text-emerald-700 border-emerald-200",
            "dokumen_list": [
                {"kode": "ak02", "nomor": "FR.AK.02", "judul": "Rekaman Asesmen Kompetensi", "tipe": "Rekap Nilai & Rekomendasi", "berkas": "21_FR.AK.02_Rekaman_Asesmen_Kompetensi.docx"},
                {"kode": "ak03", "nomor": "FR.AK.03", "judul": "Umpan Balik dan Catatan Asesmen", "tipe": "Umpan Balik", "berkas": "22_FR.AK.03_Umpan_Balik_dan_Catatan_Asesmen.docx"},
                {"kode": "ak05", "nomor": "FR.AK.05", "judul": "Laporan Asesmen", "tipe": "Laporan Resmi", "berkas": "23_FR.AK.05_Laporan_Asesmen.docx"},
                {"kode": "ak06", "nomor": "FR.AK.06", "judul": "Meninjau Proses Asesmen", "tipe": "Kaji Ulang", "berkas": "24_FR.AK.06_Meninjau_Proses_Asesmen.docx"},
                {"kode": "va", "nomor": "FR.VA", "judul": "Memberikan Kontribusi dalam Validasi Asesmen", "tipe": "Validasi Panduan Mutu", "berkas": "25_FR.VA_Memberikan_Kontribusi_Validasi_Asesmen.docx"},
            ]
        }
    ]

    token = security.token_dari_cookie(request)
    resp = render(
        request, 'alur_unduh_buku_kerja.html',
        judul=f"Unduh Buku Kerja V.2023 - {dok.get('nama_skema', '')}",
        dok=dok,
        data=data,
        personel=personel,
        tahapan_dokumen=tahapan_dokumen,
        csrf_token=token,
    )
    security.set_cookie_token(resp, token)
    return resp


@router.post('/skema/{schema_id}/verifikasi-unit')
def verifikasi_unit_alur(request: Request, schema_id: str,
                         kode_unit: str = Form(...), csrf_token: str = Form('')):
    """Tandai satu unit terverifikasi manual."""
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return JSONResponse({'sukses': False, 'pesan': 'Skema tidak ditemukan.'}, status_code=404)
    schema_library.tandai_manual(dok, kode_unit)
    return JSONResponse({'sukses': True, 'kode_unit': kode_unit, 'pesan': f'Unit {kode_unit} diverifikasi.'})


@router.post('/skema/{schema_id}/verifikasi-semua-alur')
def verifikasi_semua_alur(request: Request, schema_id: str, csrf_token: str = Form('')):
    """Tandai semua unit pada skema terverifikasi manual sekaligus."""
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return JSONResponse({'sukses': False, 'pesan': 'Skema tidak ditemukan.'}, status_code=404)
    for u in dok.get('units') or []:
        kd = u.get('kode_unit')
        if kd:
            schema_library.tandai_manual(dok, kd)
    return JSONResponse({'sukses': True, 'pesan': 'Seluruh unit berhasil diverifikasi manual.'})


@router.get('/skema/{schema_id}/unduh-docx-skkni')
def unduh_docx_skkni(request: Request, schema_id: str):
    """Unduh dokumen Word (.docx) hasil ekstraksi seluruh unit pada skema."""
    import re
    from fastapi.responses import FileResponse
    from app.paths import ROOT
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return JSONResponse({'detail': 'Skema tidak ditemukan.'}, status_code=404)

    # Catat jejak audit IP unduh SKKNI
    ip = keamanan_http.ip_klien(request)
    ua = request.headers.get('user-agent', '')
    pengguna = auth_guard.pengguna_dari_request(request)
    db.catat_audit_ip(ip, 'unduh_skkni_docx', pengguna['id'] if pengguna else None, schema_id, ua)

    slug = re.sub(r'[^A-Za-z0-9_\-]', '_', dok.get('nama_skema') or schema_id)
    out_dir = ROOT / 'output'
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"Dokumen_SKKNI_{slug}.docx"

    units = dok.get('units') or []
    try:
        from app import multi_docx_generator
        multi_docx_generator.generate_multi_docx(units, str(out_file))
    except Exception as e:
        logger.error(f"Gagal generate multi docx: {e}")
        return JSONResponse({'detail': f'Gagal membuat dokumen Word: {e}'}, status_code=500)

    return FileResponse(
        out_file,
        filename=f"Dokumen_SKKNI_{slug}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get('/skema/{schema_id}/unduh-skema-asli')
def unduh_skema_asli(request: Request, schema_id: str):
    """Unduh berkas Word (.docx) skema sertifikasi asli yang diunggah."""
    from fastapi.responses import FileResponse
    from app.paths import ROOT
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return JSONResponse({'detail': 'Skema tidak ditemukan.'}, status_code=404)

    # Catat jejak audit IP unduh skema
    ip = keamanan_http.ip_klien(request)
    ua = request.headers.get('user-agent', '')
    pengguna = auth_guard.pengguna_dari_request(request)
    db.catat_audit_ip(ip, 'unduh_skema_asli', pengguna['id'] if pengguna else None, schema_id, ua)

    docx_path = ROOT / 'data' / 'schema_library' / 'docx' / f"{schema_id}.docx"
    if not docx_path.exists():
        return JSONResponse({'detail': 'Berkas skema asli tidak ditemukan.'}, status_code=404)

    nama_file = dok.get('nama_asli') or f"Skema_{schema_id}.docx"
    return FileResponse(
        docx_path,
        filename=nama_file,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
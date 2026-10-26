"""Pratinjau unit, penyuntingan MUK, dan koreksi manual.

Dipindahkan dari `app/main.py` (temuan T-19) tanpa mengubah perilaku: decorator
`@app.` menjadi `@router.` dan helper halaman diambil dari `app.web_common`.
"""

import json
import re
from typing import Any, Dict
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import jobs, koreksi, schema_library, status_units
from app.api import auth_guard, security
from app.buku_kerja import simpan_konfigurasi_muk, susun_data_buku_kerja
from app.lsp_exporter import ambil_json_unit, unit_ke_lsp_dict, unit_ke_smart_paste_text

from app.section_parser import flatten_nodes
from app.logging_config import ambil_logger
from app.web_common import ke_skema, render

#: Jumlah unit per halaman pada daftar panjang (dulu konstanta di app/main.py).
BATAS_UNIT_PER_HALAMAN = 10

logger = ambil_logger(__name__)

router = APIRouter()


@router.get('/skema/{schema_id}/muk', response_class=HTMLResponse)
def halaman_muk_skema(
    request: Request,
    schema_id: str,
    versi: str = '',
    pesan: str = '',
    tipe: str = '',
):
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        html = render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                       pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html

    data = susun_data_buku_kerja(schema_id=schema_id, kode_versi=versi)
    token = security.token_dari_cookie(request)
    resp = render(
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


@router.post('/skema/{schema_id}/muk')
async def simpan_muk_skema(request: Request, schema_id: str,
                           pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login())):
    form = await request.form()
    csrf_token = str(form.get('csrf_token') or '')
    security.periksa_token(request, csrf_token)

    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return ke_skema('Skema tidak ditemukan.', 'galat')

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


@router.get('/skema/{schema_id}/unit/{kode_unit}', response_class=HTMLResponse)
def preview_unit(request: Request, schema_id: str, kode_unit: str,
                 pesan: str = '', tipe: str = ''):
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        html = render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                       pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html

    if not re.fullmatch(r'[A-Z]\.\d{2}[A-Z]{2,3}\d{2}\.\d{3}\.\d', kode_unit or ''):
        html = render(request, 'tidak_ditemukan.html', judul='Kode unit tidak sah',
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
    resp = render(
        request, 'unit_preview.html', judul='Hasil Ekstraksi Unit',
        dok=dok, kode=kode_unit, data=data, unit_skema=unit_skema,
        info_status=info_status,
        bv=bv, pp=pp,
        unit_lsp_json=unit_lsp_json, unit_smart_text=unit_smart_text,
        berkas=berkas, pesan=pesan, tipe=tipe, csrf_token=token,
    )
    security.set_cookie_token(resp, token)
    return resp


@router.get('/skema/{schema_id}/unit/{kode_unit}/koreksi', response_class=HTMLResponse)
def halaman_koreksi_unit(request: Request, schema_id: str, kode_unit: str,
                         pesan: str = '', tipe: str = ''):
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        html = render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                       pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html

    if not re.fullmatch(r'[A-Z]\.\d{2}[A-Z]{2,3}\d{2}\.\d{3}\.\d', kode_unit or ''):
        html = render(request, 'tidak_ditemukan.html', judul='Kode unit tidak sah',
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
    resp = render(
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


@router.post('/skema/{schema_id}/unit/{kode_unit}/koreksi')
async def simpan_koreksi_unit(request: Request, schema_id: str, kode_unit: str,
                              pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login(auth_guard.PERAN_ADMIN))):
    """Menyimpan koreksi manual teks elemen/KUK — khusus Admin (T-01)."""
    form = await request.form()
    csrf_token = str(form.get('csrf_token') or '')
    security.periksa_token(request, csrf_token)

    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return ke_skema('Skema tidak ditemukan.', 'galat')

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


@router.post('/skema/{schema_id}/unit/{kode_unit}/koreksi/kembalikan')
def kembalikan_koreksi_unit(request: Request, schema_id: str, kode_unit: str,
                            csrf_token: str = Form(''),
                            pengguna: Dict[str, Any] = Depends(auth_guard.wajib_login(auth_guard.PERAN_ADMIN))):
    security.periksa_token(request, csrf_token)
    dok = schema_library.ambil_skema(schema_id)
    if not dok:
        return ke_skema('Skema tidak ditemukan.', 'galat')
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

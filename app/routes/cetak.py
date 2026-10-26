"""Pracetak A4 Buku Kerja serta unduhan DOCX/ZIP.

Dipindahkan dari `app/main.py` (temuan T-19) tanpa mengubah perilaku: decorator
`@app.` menjadi `@router.` dan helper halaman diambil dari `app.web_common`.
"""

import re

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from app import schema_library, status_units
from app.buku_kerja import DAFTAR_DOKUMEN_BUKU_KERJA, susun_data_buku_kerja, tentukan_dokumen_aktif
from app.buku_kerja_docx import NAMA_BERKAS_DOKUMEN, buat_docx_buku_kerja_bytes, buat_zip_buku_kerja_bytes

from app.logging_config import ambil_logger
from app.web_common import render

#: Jumlah unit per halaman pada daftar panjang (dulu konstanta di app/main.py).
BATAS_UNIT_PER_HALAMAN = 10

logger = ambil_logger(__name__)

router = APIRouter()


@router.get('/skema/{schema_id}/cetak-apl', response_class=HTMLResponse)
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
        html = render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                       pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html

    gerbang = data.get('gerbang') or status_units.evaluasi_gerbang_skema(schema_id)
    if gerbang.get('ada_gagal'):
        gagal_list = [f"{u['kode_unit']} ({u['alasan']})" for u in gerbang['penahan'] if u['status'] == 'gagal']
        html = render(
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

    return render(
        request, 'cetak_apl.html',
        judul=judul_halaman,
        judul_halaman=judul_halaman,
        data=data,
        doc_mode=doc_mode,
        dokumen_aktif=dokumen_aktif,
    )


@router.get('/skema/{schema_id}/unduh-buku-kerja-docx')
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
        html = render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                       pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html

    gerbang = data.get('gerbang') or status_units.evaluasi_gerbang_skema(schema_id)
    if gerbang.get('ada_gagal'):
        gagal_list = [f"{u['kode_unit']} ({u['alasan']})" for u in gerbang['penahan'] if u['status'] == 'gagal']
        html = render(
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


@router.get('/skema/{schema_id}/unduh-buku-kerja-zip')
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
        html = render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                       pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html

    gerbang = status_units.evaluasi_gerbang_skema(schema_id)
    if gerbang.get('ada_gagal'):
        gagal_list = [f"{u['kode_unit']} ({u['alasan']})" for u in gerbang['penahan'] if u['status'] == 'gagal']
        html = render(
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
        html = render(request, 'tidak_ditemukan.html', judul='Skema tidak ditemukan',
                       pesan='Dokumen skema tidak ditemukan.')
        html.status_code = 404
        return html

    zip_bytes, nama_zip = hasil_zip
    return Response(
        content=zip_bytes,
        media_type='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{nama_zip}"'},
    )

"""
SKKNI Extractor - REST API Eksternal v1 (Fase 4).

Menyediakan antarmuka REST API terproteksi API Key (header X-API-Key atau Bearer Token)
untuk sinkronisasi langsung dengan sistem eksternal (WordPress LSP Plugin, SIMLSP, LMS, dsb):
1. GET /api/v1/status & /api/v1/ping: Pengecekan status layanan dan validasi kredensial.
2. GET /api/v1/skkni: Katalog SKKNI lengkap dengan status regulasi Kemnaker (Berlaku / Dicabut).
3. GET /api/v1/skkni/{identifier}: Detail dokumen SKKNI atau ekstraksi unit kompetensi spesifik (Elemen, KUK, BV, PP).
4. GET /api/v1/skema: Daftar skema sertifikasi dan unit kompetensinya.
5. GET /api/v1/skema/{schema_id}/muk: Sinkronisasi instrumen MUK, kelompok pekerjaan, dan instrumen asesmen.
6. POST /api/v1/documents/render: Render dokumen Buku Kerja siap cetak (HTML / DOCX).
7. GET /api/v1/keys & POST /api/v1/keys: Manajemen API Key (khusus peran admin).
"""

import io
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, Security
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app import db, library, schema_library
from app.buku_kerja import (
    DAFTAR_DOKUMEN_BUKU_KERJA,
    ringkas_bv_pp_unit,
    susun_data_buku_kerja,
    tentukan_dokumen_aktif,
)
from app.buku_kerja_docx import NAMA_BERKAS_DOKUMEN, _jinja_env, buat_docx_buku_kerja_bytes
from app.lsp_exporter import ambil_json_unit, skema_ke_lsp_data, unit_ke_lsp_dict
from app.version import __version__

router = APIRouter(prefix="/api/v1", tags=["api_v1"])


# ==============================================================================
# Skema Permintaan & Tanggapan Pydantic
# ==============================================================================

class DokumenRenderRequest(BaseModel):
    schema_id: str = Field(..., description="ID unik skema sertifikasi")
    format: str = Field("html", description="Format output: 'html' atau 'docx'")
    form_code: str = Field("all", description="Kode formulir (misal 'all', 'FR.IA.02', 'ia02', 'observasi')")
    versi: Optional[str] = Field("", description="Kode versi MUK yang ingin dirender")
    no_skema: Optional[str] = Field("", description="Nomor skema kustom")
    nama_asesor: Optional[str] = Field("", description="Nama asesor kustom")
    no_met: Optional[str] = Field("", description="Nomor registrasi MET asesor")
    metode_mapa: Optional[str] = Field("", description="Metode MAPA: observasi, portofolio, atau gabungan")
    kategori_asesi: Optional[int] = Field(0, description="Kategori asesi (1, 2, atau 3)")
    download: bool = Field(False, description="Jika true pada HTML, unduh sebagai berkas lampiran")


class BuatApiKeyRequest(BaseModel):
    nama_klien: str = Field(..., description="Nama sistem atau aplikasi klien (misal: WordPress LSP)")
    peran: Optional[str] = Field("klien", description="Peran: 'klien' atau 'admin'")
    kunci_khusus: Optional[str] = Field(None, description="String kunci API kustom jika diinginkan")


# ==============================================================================
# Dependency Autentikasi API Key
# ==============================================================================

api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description=(
        "Kunci API klien. Buat dengan `python -m tools.kunci_api buat --nama <klien>`; "
        "nilainya hanya ditampilkan sekali saat dibuat."
    ),
)

bearer_auth = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="Kunci API yang sama, dikirim sebagai header Authorization: Bearer <kunci>.",
)


async def autentikasi_api_key(
    request: Request,
    x_api_key: Optional[str] = Security(api_key_header),
    kredensial: Optional[HTTPAuthorizationCredentials] = Security(bearer_auth),
) -> Dict[str, Any]:
    """
    Memvalidasi API Key dari:
    1. Header `X-API-Key: <kunci>`
    2. Header `Authorization: Bearer <kunci>` (atau nilai kunci saja)
    3. Query param `?api_key=<kunci>`

    Kedua skema dideklarasikan sebagai dependency keamanan FastAPI supaya
    `components.securitySchemes` terisi dan Swagger UI menampilkan tombol
    Authorize (temuan T-04).
    """
    token = None
    if x_api_key and x_api_key.strip():
        token = x_api_key.strip()
    elif kredensial and kredensial.credentials and kredensial.credentials.strip():
        token = kredensial.credentials.strip()
    else:
        # Kompatibilitas: sebagian klien lama mengirim kunci tanpa awalan
        # "Bearer ". HTTPBearer menolak bentuk itu, jadi dibaca langsung di sini.
        mentah = (request.headers.get("authorization") or "").strip()
        if mentah and len(mentah.split()) == 1:
            token = mentah
        elif "api_key" in request.query_params:
            token = request.query_params.get("api_key", "").strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail=(
                "Kredensial API tidak ditemukan. Sertakan header X-API-Key atau "
                "Authorization: Bearer <kunci>, atau parameter ?api_key=<kunci>."
            ),
        )

    klien = db.validasi_kunci_api(token)
    if not klien:
        raise HTTPException(
            status_code=401,
            detail="API Key tidak valid, tidak aktif, atau telah dicabut.",
        )

    return klien


# ==============================================================================
# Endpoint Status & Pemeriksaan Koneksi
# ==============================================================================

@router.get("/status")
@router.get("/ping")
def periksa_status(klien: Dict[str, Any] = Depends(autentikasi_api_key)):
    """Pemeriksaan status ketersediaan API dan konfirmasi validitas kredensial."""
    return {
        "status": "online",
        "versi": __version__,
        "waktu_server": datetime.now(timezone.utc).isoformat(),
        "klien": {
            "id": klien["id"],
            "nama_klien": klien["nama_klien"],
            "peran": klien["peran"],
        },
        "fitur": [
            "skkni_catalog",
            "skkni_unit_extraction",
            "skema_catalog",
            "muk_sync_v2023",
            "kelompok_pekerjaan",
            "document_rendering_html_docx",
        ],
    }


# ==============================================================================
# Endpoint Katalog Dokumen SKKNI & Unit Ekstraksi
# ==============================================================================

@router.get("/skkni")
def ambil_katalog_skkni(
    q: Optional[str] = Query(None, description="Filter pencarian nomor, judul, atau bidang SKKNI"),
    status: Optional[str] = Query(None, description="Filter status regulasi Kemnaker: berlaku / dicabut"),
    page: int = Query(1, ge=1, description="Nomor halaman (mulai dari 1)"),
    per_page: int = Query(20, ge=1, le=100, description="Jumlah data per halaman"),
    klien: Dict[str, Any] = Depends(autentikasi_api_key),
):
    """Mengambil katalog seluruh dokumen SKKNI beserta status regulasi Kemnaker."""
    docs = library.daftar_dokumen()
    peta_reg = db.ambil_peta_regulasi()

    hasil = []
    for d in docs:
        doc_id = d["id"]
        reg = peta_reg.get(doc_id, {})
        status_regulasi = reg.get("status_regulasi", "berlaku")
        kepmen_pengganti = reg.get("kepmen_pengganti") or ""
        catatan = reg.get("catatan") or ""

        if status and status.lower() != status_regulasi.lower():
            continue

        nomor = d.get("nomor") or ""
        judul = d.get("judul") or ""
        bidang = d.get("bidang") or ""

        if q:
            q_low = q.lower()
            if not (q_low in nomor.lower() or q_low in judul.lower() or q_low in bidang.lower()):
                continue

        hasil.append({
            "id": doc_id,
            "nomor": nomor,
            "tahun": d.get("tahun"),
            "judul": judul,
            "bidang": bidang,
            "jumlah_unit": d.get("jumlah_unit", 0),
            "status_regulasi": status_regulasi,
            "nomor_kepmen": reg.get("nomor_kepmen") or nomor,
            "kepmen_pengganti": kepmen_pengganti if status_regulasi == "dicabut" else None,
            "catatan_regulasi": catatan or None,
            "tanggal_ditambah": d.get("tanggal_ditambah"),
        })

    total = len(hasil)
    start_idx = (page - 1) * per_page
    items = hasil[start_idx : start_idx + per_page]

    return {
        "status": "sukses",
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_halaman": (total + per_page - 1) // per_page if total > 0 else 1,
        "data": items,
    }


@router.get("/skkni/{identifier}")
def ambil_detail_skkni_atau_unit(
    identifier: str,
    klien: Dict[str, Any] = Depends(autentikasi_api_key),
):
    """
    Mengambil data detail SKKNI atau ekstraksi unit kompetensi.
    - Bila `identifier` cocok dengan doc_id SKKNI (misal skkni_xxx): mengembalikan ringkasan dokumen dan daftar unitnya.
    - Bila `identifier` cocok dengan kode unit (misal M.702090.001.01): mengembalikan unit lengkap beserta Elemen, KUK, Batasan Variabel, dan Panduan Penilaian.
    """
    # 1. Cek kecocokan doc_id SKKNI di perpustakaan
    doc = library.ambil_dokumen(identifier)
    if doc:
        peta_reg = db.ambil_peta_regulasi()
        reg = peta_reg.get(identifier, {})
        return {
            "status": "sukses",
            "tipe": "dokumen_skkni",
            "id": identifier,
            "nomor": doc.get("nomor"),
            "tahun": doc.get("tahun"),
            "judul": doc.get("judul"),
            "bidang": doc.get("bidang"),
            "jumlah_unit": doc.get("jumlah_unit", 0),
            "status_regulasi": reg.get("status_regulasi", "berlaku"),
            "kepmen_pengganti": reg.get("kepmen_pengganti"),
            "catatan_regulasi": reg.get("catatan"),
            "units": doc.get("units", []),
        }

    # 2. Cek kecocokan kode unit kompetensi
    unit_json = ambil_json_unit(identifier)
    if unit_json:
        bv_pp = ringkas_bv_pp_unit(unit_json)
        lsp_dict = unit_ke_lsp_dict(unit_json)
        return {
            "status": "sukses",
            "tipe": "unit_kompetensi",
            "kode_unit": unit_json.get("kode_unit") or identifier,
            "judul_unit": unit_json.get("judul_unit") or "",
            "deskripsi": unit_json.get("deskripsi") or "",
            "elemen": unit_json.get("elemen", []),
            "batasan_variabel": unit_json.get("batasan_variabel", {}),
            "panduan_penilaian": unit_json.get("panduan_penilaian", {}),
            "ringkasan_bv_pp": bv_pp,
            "format_lsp_wordpress": lsp_dict,
        }

    raise HTTPException(
        status_code=404,
        detail=f"Dokumen SKKNI atau Unit Kompetensi '{identifier}' tidak ditemukan."
    )


# ==============================================================================
# Endpoint Skema Sertifikasi & MUK Terpadu
# ==============================================================================

@router.get("/skema")
def ambil_katalog_skema(
    q: Optional[str] = Query(None, description="Pencarian kode atau nama skema"),
    klien: Dict[str, Any] = Depends(autentikasi_api_key),
):
    """Mengambil katalog seluruh skema sertifikasi yang tersimpan di sistem."""
    docs = schema_library.daftar_skema()
    hasil = []
    for d in docs:
        nama = d.get("nama_skema") or ""
        kode = d.get("kode_skema") or d.get("nomor_skema") or ""
        if q:
            q_low = q.lower()
            if not (q_low in nama.lower() or q_low in kode.lower()):
                continue

        units = d.get("units") or []
        hasil.append({
            "id": d["id"],
            "kode_skema": kode,
            "nama_skema": nama,
            "jenis_skema": d.get("jenis_skema"),
            "jumlah_unit": len(units),
            "units": [{"kode_unit": u.get("kode_unit"), "judul_unit": u.get("judul_unit")} for u in units],
            "tanggal_ditambah": d.get("tanggal_ditambah"),
        })

    return {
        "status": "sukses",
        "total": len(hasil),
        "data": hasil,
    }


@router.get("/skema/{schema_id}/muk")
def ambil_sinkronisasi_muk(
    schema_id: str,
    versi: Optional[str] = Query("", description="Kode versi MUK tertentu (opsional, default versi aktif)"),
    klien: Dict[str, Any] = Depends(autentikasi_api_key),
):
    """
    Sinkronisasi instrumen MUK lengkap untuk aplikasi eksternal (WordPress LSP Plugin, SIMLSP).
    Menghasilkan data terstruktur berisi kelompok pekerjaan, instrumen asesmen (IA.01 s/d IA.11),
    dan referensi Batasan Variabel/Panduan Penilaian.
    """
    data = susun_data_buku_kerja(schema_id, kode_versi=versi or "")
    if not data:
        raise HTTPException(status_code=404, detail=f"Skema '{schema_id}' tidak ditemukan.")

    return {
        "status": "sukses",
        "skema": {
            "id": schema_id,
            "kode_skema": data.get("no_skema") or data.get("kode_skema"),
            "nama_skema": data.get("nama_skema"),
            "jenis_skema": data.get("jenis_skema"),
            "kategori_asesi": data.get("kategori_asesi"),
        },
        "versi_muk": {
            "aktif": data.get("versi_aktif", "v1"),
            "daftar_versi": data.get("daftar_versi_muk", []),
        },
        "kelompok_pekerjaan": data.get("kelompok_pekerjaan", []),
        "ringkasan_kompetensi": {
            "total_unit": len(data.get("daftar_unit", [])),
            "total_elemen": data.get("total_elemen", 0),
            "total_kuk": data.get("total_kuk", 0),
        },
        "daftar_unit": data.get("daftar_unit", []),
        "instrumen": {
            "ia_01": data.get("ia_01", {}),
            "ia_02": data.get("ia_02", {}),
            "ia_03": data.get("ia_03", {}),
            "ia_04a": data.get("ia_04a", {}),
            "ia_04b": data.get("ia_04b", {}),
            "ia_05": data.get("ia_05", {}),
            "ia_06": data.get("ia_06", {}),
            "ia_07": data.get("ia_07", {}),
            "ia_08": data.get("ia_08", {}),
            "ia_11": data.get("ia_11", {}),
            "va": data.get("va", {}),
            "ak_07": data.get("ak_07", {}),
            "peta_kelompok": data.get("peta_kelompok", {}),
        },
        "referensi_bv_pp": data.get("referensi_bv_pp", {}),
    }


# ==============================================================================
# Endpoint Generator / Perender Dokumen Buku Kerja (HTML / DOCX)
# ==============================================================================

@router.post("/documents/render")
def render_dokumen(
    req: DokumenRenderRequest,
    klien: Dict[str, Any] = Depends(autentikasi_api_key),
):
    """
    Merender formulir Buku Kerja BNSP V.2023 ke dalam bentuk HTML siap cetak atau berkas Word (.docx).
    Mendukung formulir satuan (misal 'FR.IA.02'), kelompok metode ('observasi', 'dit', 'portofolio'),
    atau buku kerja lengkap ('all').
    """
    data = susun_data_buku_kerja(
        schema_id=req.schema_id,
        no_skema=req.no_skema or "",
        nama_asesor=req.nama_asesor or "",
        no_met=req.no_met or "",
        metode_mapa=req.metode_mapa or "",
        kategori_asesi=req.kategori_asesi or 0,
        kode_versi=req.versi or "",
    )
    if not data:
        raise HTTPException(status_code=404, detail=f"Skema '{req.schema_id}' tidak ditemukan.")

    # Normalisasi format kode form
    fc_raw = req.form_code.lower().replace(".", "").replace("-", "_").strip()
    alias_map = {
        "fria01": "ia01", "fria02": "ia02", "fria03": "ia03",
        "fria04a": "ia04a", "fria04b": "ia04b", "fria05a": "ia05a",
        "fria05b": "ia05b", "fria05c": "ia05c", "fria06a": "ia06a",
        "fria06b": "ia06b", "fria06c": "ia06c", "fria07": "ia07",
        "fria08": "ia08", "fria11": "ia11", "frapl01": "apl01",
        "frapl02": "apl02", "frmapa01": "mapa01", "frmapa02": "mapa02",
        "frak01": "ak01", "frak02": "ak02", "frak03": "ak03",
        "frak04": "ak04", "frak05": "ak05", "frak06": "ak06",
        "frak07": "ak07", "frva": "va",
    }
    fc = alias_map.get(fc_raw, fc_raw)
    valid_modes = {d["kode"] for d in DAFTAR_DOKUMEN_BUKU_KERJA}
    mode_bersih = fc if fc in valid_modes else "all"
    dokumen_aktif = tentukan_dokumen_aktif(mode_bersih, data.get("metode_mapa", "observasi"))

    slug_skema = re.sub(r"[^a-zA-Z0-9_-]+", "_", data["nama_skema"]).strip("_") or req.schema_id

    if req.format.lower() == "docx":
        docx_bytes = buat_docx_buku_kerja_bytes(
            data=data,
            dokumen_aktif=dokumen_aktif,
            judul_halaman=f"Buku Kerja BNSP - {data['nama_skema']}",
        )
        filename = f"Buku_Kerja_{slug_skema}_{mode_bersih}.docx"
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    else:
        # Render HTML
        template = _jinja_env.get_template("cetak_apl.html")
        rendered_html = template.render(
            judul=f"Buku Kerja - {data['nama_skema']}",
            judul_halaman=f"Buku Kerja - {data['nama_skema']}",
            data=data,
            doc_mode=mode_bersih,
            dokumen_aktif=dokumen_aktif,
        )
        if req.download:
            return HTMLResponse(
                content=rendered_html,
                headers={"Content-Disposition": f'attachment; filename="Buku_Kerja_{slug_skema}_{mode_bersih}.html"'},
            )
        return {
            "status": "sukses",
            "schema_id": req.schema_id,
            "mode": mode_bersih,
            "versi": data.get("versi_aktif", "v1"),
            "jumlah_dokumen": len(dokumen_aktif),
            "dokumen_aktif": dokumen_aktif,
            "html": rendered_html,
        }


# ==============================================================================
# Endpoint Manajemen API Key (Khusus Admin)
# ==============================================================================

@router.get("/keys")
def ambil_daftar_kunci_api(klien: Dict[str, Any] = Depends(autentikasi_api_key)):
    """Mengambil daftar seluruh kunci API terdaftar (khusus peran admin)."""
    if klien.get("peran") != "admin":
        raise HTTPException(status_code=403, detail="Akses ditolak. Endpoint ini hanya untuk peran admin.")
    return {
        "status": "sukses",
        "data": db.daftar_kunci_api(),
    }


@router.post("/keys")
def buat_kunci_api_baru(
    req: BuatApiKeyRequest,
    klien: Dict[str, Any] = Depends(autentikasi_api_key),
):
    """Membuat kunci API baru untuk klien eksternal (khusus peran admin)."""
    if klien.get("peran") != "admin":
        raise HTTPException(status_code=403, detail="Akses ditolak. Endpoint ini hanya untuk peran admin.")

    kunci = db.buat_kunci_api(
        nama_klien=req.nama_klien,
        peran=req.peran or "klien",
        kunci_khusus=req.kunci_khusus,
    )
    return {
        "status": "sukses",
        "pesan": "Kunci API berhasil dibuat.",
        "kunci": kunci,
        "nama_klien": req.nama_klien,
        "peran": req.peran or "klien",
    }

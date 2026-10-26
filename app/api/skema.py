"""API perpustakaan skema sertifikasi (Fase 4C)."""

import json
import re
from fastapi import APIRouter, HTTPException, Response

from app import schema_library
from app.buku_kerja import susun_data_buku_kerja
from app.lsp_exporter import ambil_json_unit, skema_ke_lsp_data, unit_ke_lsp_dict, unit_ke_smart_paste_text

router = APIRouter(prefix="/api/skema", tags=["skema"])


@router.get("")
def daftar():
    docs = schema_library.daftar_skema()
    return {
        "jumlah": len(docs),
        "skema": [
            {
                "id": d["id"],
                "nama_asli": d.get("nama_asli"),
                "nama_skema": d.get("nama_skema"),
                "jenis_skema": d.get("jenis_skema"),
                "jumlah_unit": d.get("jumlah_unit", 0),
                "status_identifikasi": d.get("status_identifikasi"),
                "pencocokan": (d.get("hasil_pencocokan") or {}).get("ringkasan"),
                "tanggal_ditambah": d.get("tanggal_ditambah"),
            }
            for d in docs
        ],
    }


@router.get("/{schema_id}")
def detail(schema_id: str):
    doc = schema_library.ambil_skema(schema_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Skema tidak ditemukan.")
    peta = schema_library.peta_kelengkapan()
    return {
        **doc,
        "status_unit": {u["kode_unit"]: schema_library.status_unit(doc, u["kode_unit"], peta)
                        for u in doc.get("units") or []},
    }


@router.get("/{schema_id}/export-lsp")
def export_skema_lsp(schema_id: str, download: bool = False):
    """Ekspor seluruh unit pada skema dalam format JSON LSP dan teks Smart Paste."""
    doc = schema_library.ambil_skema(schema_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Skema tidak ditemukan.")

    lsp_list, smart_text = skema_ke_lsp_data(doc)
    if download:
        nama_file = re.sub(r'[^A-Za-z0-9_\-\.]', '_', doc.get('nama_skema') or schema_id)
        konten = json.dumps(lsp_list, ensure_ascii=False, indent=2)
        return Response(
            content=konten,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{nama_file}_lsp.json"'}
        )

    return {
        "schema_id": schema_id,
        "nama_skema": doc.get("nama_skema"),
        "total_unit_diekstrak": len(lsp_list),
        "lsp_json": lsp_list,
        "smart_paste_text": smart_text
    }


@router.get("/{schema_id}/unit/{kode_unit}/export-lsp")
def export_unit_lsp(schema_id: str, kode_unit: str, download: bool = False):
    """Ekspor satu unit dalam format JSON LSP dan teks Smart Paste."""
    data = ambil_json_unit(kode_unit)
    if not data:
        raise HTTPException(status_code=404, detail="JSON ekstraksi unit belum ditemukan.")

    lsp_dict = unit_ke_lsp_dict(data)
    smart_text = unit_ke_smart_paste_text(data)

    if download:
        konten = json.dumps([lsp_dict], ensure_ascii=False, indent=2)
        return Response(
            content=konten,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{kode_unit}_lsp.json"'}
        )

    return {
        "kode_unit": kode_unit,
        "judul_unit": data.get("judul_unit"),
        "lsp_json": [lsp_dict],
        "smart_paste_text": smart_text
    }


@router.get("/{schema_id}/buku-kerja")
def get_buku_kerja_data(
    schema_id: str,
    no_skema: str = "",
    nama_asesor: str = "",
    no_met: str = ""
):
    """Mengambil data terstruktur Buku Kerja Asesor V.2023 (FR.APL.01 & FR.APL.02)."""
    data = susun_data_buku_kerja(
        schema_id=schema_id,
        no_skema=no_skema,
        nama_asesor=nama_asesor,
        no_met=no_met
    )
    if not data:
        raise HTTPException(status_code=404, detail="Skema tidak ditemukan.")
    return data

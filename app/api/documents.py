"""API dokumen Word (Fase 4E)."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api import security
from app.services import document_service as ds

router = APIRouter(prefix="/api/documents", tags=["documents"])


class PermintaanGenerate(BaseModel):
    schema_id: str
    unit_kode: list[str] | None = None
    semua_unit: bool = True
    draft: bool = False
    csrf_token: str | None = None


@router.post("/generate")
def generate(payload: PermintaanGenerate, request: Request):
    token = payload.csrf_token or request.headers.get("x-csrf-token")
    security.periksa_token(request, token)

    kode = None if payload.semua_unit else (payload.unit_kode or None)
    try:
        meta = ds.buat_dokumen(payload.schema_id, kode, setujui_draft=payload.draft)
    except ds.GalatDokumen as e:
        raise HTTPException(status_code=e.kode,
                            detail={"pesan": e.pesan, "masalah": e.masalah})
    return meta


@router.get("")
def daftar():
    docs = ds.daftar_dokumen()
    return {
        "jumlah": len(docs),
        "dokumen": [
            {
                "id": d["id"],
                "schema_id": d.get("schema_id"),
                "nama_skema": d.get("nama_skema"),
                "jumlah_unit": d.get("jumlah_unit"),
                "total_elemen": d.get("total_elemen"),
                "total_kuk": d.get("total_kuk"),
                "status": d.get("status"),
                "dibuat": d.get("dibuat"),
                "ukuran_byte": d.get("ukuran_byte"),
                "unduh": f"/api/documents/{d['id']}/download" if d.get("berkas_docx") else None,
            }
            for d in docs
        ],
    }


@router.get("/{doc_id}")
def detail(doc_id: str):
    meta = ds.ambil_dokumen(doc_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan.")
    return meta


@router.get("/{doc_id}/download")
def unduh(doc_id: str):
    meta = ds.ambil_dokumen(doc_id)
    if not meta or meta.get("status") == ds.STATUS_GAGAL:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan.")
    try:
        path = ds.jalur_docx(meta)
    except ds.GalatDokumen as e:
        raise HTTPException(status_code=e.kode, detail=e.pesan)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=ds.nama_unduhan(meta),
    )

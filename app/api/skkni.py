"""API perpustakaan SKKNI (Fase 4B)."""

from fastapi import APIRouter, HTTPException

from app import library

router = APIRouter(prefix="/api/skkni", tags=["skkni"])


@router.get("")
def daftar():
    docs = library.daftar_dokumen()
    return {
        "jumlah": len(docs),
        "dokumen": [
            {
                "id": d["id"],
                "nama_asli": d.get("nama_asli"),
                "nomor": d.get("nomor"),
                "tahun": d.get("tahun"),
                "judul": d.get("judul"),
                "halaman": d.get("halaman"),
                "jumlah_unit": d.get("jumlah_unit", 0),
                "sumber": d.get("sumber"),
                "status_identifikasi": d.get("status_identifikasi"),
                "tanggal_ditambah": d.get("tanggal_ditambah"),
            }
            for d in docs
        ],
    }


@router.get("/{doc_id}")
def detail(doc_id: str):
    doc = library.ambil_dokumen(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan.")
    return doc

"""
SKKNI Extractor - Modul Generator Buku Kerja Asesor & Dokumen Cetak BNSP (FR.APL.01 & FR.APL.02).

Menyediakan penyusunan data terstruktur untuk template dokumen cetak fisik:
- FR.APL.01: Permohonan Sertifikasi Kompetensi (Murni Template / Blank Asesi)
- FR.APL.02: Asesmen Mandiri (Terisi Unit, Elemen, dan KUK lengkap dari SKKNI)
- Buku Kerja Asesor V.2023 Foundation
"""

import re
from typing import Any, Dict, List, Optional
from app import schema_library
from app.lsp_exporter import ambil_json_unit


def deteksi_standar_skkni(kode_unit: str, fallback_standar: str = "") -> str:
    """Deteksi referensi SKKNI berdasarkan pola kode unit."""
    kode = kode_unit.strip().upper()
    if "J.63OPR" in kode:
        return "SKKNI 2018-056"
    elif "M.70MKT" in kode:
        return "SKKNI 2022-124"
    elif "J.59MTM" in kode:
        return "SKKNI 2018-107"
    elif "M.73ADV" in kode:
        return "SKKNI 2023-101"
    elif fallback_standar:
        return fallback_standar
    return "Standar Khusus / SKKNI"


def susun_data_buku_kerja(
    schema_id: str,
    no_skema: str = "",
    nama_asesor: str = "",
    no_met: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Menyusun data lengkap skema dan seluruh unit kompetensi (Elemen + KUK)
    untuk dicetak sebagai dokumen template APL 01 dan APL 02.
    """
    doc = schema_library.ambil_skema(schema_id)
    if not doc:
        return None

    nama_skema = (doc.get("nama_skema") or doc.get("nama_asli") or "Skema Sertifikasi").strip()
    jenis_skema = (doc.get("jenis_skema") or "Okupasi").strip()
    
    # Ambil nomor skema dari argumen atau metadata
    nomor_skema = no_skema.strip() or doc.get("kode_skema") or doc.get("nomor_skema") or ""

    units_raw = doc.get("units") or []
    daftar_unit: List[Dict[str, Any]] = []

    for idx, u in enumerate(units_raw):
        kode = u.get("kode_unit") or ""
        judul = u.get("judul_skema") or ""

        # Ambil detail ekstraksi jika ada di cache JSON
        data_ekstraksi = ambil_json_unit(kode)
        if data_ekstraksi:
            judul = data_ekstraksi.get("judul_unit") or judul
            deskripsi = data_ekstraksi.get("deskripsi_unit") or ""
            raw_elemen = data_ekstraksi.get("elemen_kompetensi") or []
        else:
            deskripsi = ""
            raw_elemen = []

        elemen_list = []
        for e_idx, el in enumerate(raw_elemen):
            e_no = el.get("nomor_elemen") or (e_idx + 1)
            e_nama = (el.get("nama_elemen") or "").strip()
            
            kuks = []
            for k in el.get("kuk") or []:
                k_no = str(k.get("nomor_kuk") or "").strip()
                k_ur = str(k.get("uraian_kuk") or "").strip()
                teks_kuk = f"{k_no} {k_ur}".strip()
                if teks_kuk:
                    kuks.append(teks_kuk)

            elemen_list.append({
                "nomor": e_no,
                "nama": e_nama,
                "kuk": kuks
            })

        # Jika belum ada hasil ekstraksi, sediakan elemen minimal placeholder
        if not elemen_list:
            elemen_list.append({
                "nomor": 1,
                "nama": f"Melaksanakan pekerjaan {judul or kode}",
                "kuk": ["1.1 Menerapkan prosedur kerja sesuai standar yang berlaku."]
            })

        standar_acuan = deteksi_standar_skkni(kode)

        daftar_unit.append({
            "nomor_urut": idx + 1,
            "kode_unit": kode,
            "judul_unit": judul,
            "deskripsi_unit": deskripsi,
            "standar_acuan": standar_acuan,
            "elemen": elemen_list
        })

    # Bukti persyaratan default untuk APL 01
    persyaratan_dasar = [
        "Fotokopi Ijazah Pendidikan Terakhir",
        "Surat Keterangan Pengalaman Kerja / Magang yang Relevan",
        "Portofolio / Bukti Hasil Pekerjaan yang Relevan"
    ]
    persyaratan_admin = [
        "Fotokopi Kartu Tanda Penduduk (KTP / Identitas Diri)",
        "Pas Foto Formal 3x4 (Background Merah/Biru)"
    ]

    return {
        "schema_id": schema_id,
        "nama_skema": nama_skema,
        "jenis_skema": jenis_skema,
        "nomor_skema": nomor_skema,
        "nama_asesor": nama_asesor.strip(),
        "no_met": no_met.strip(),
        "jumlah_unit": len(daftar_unit),
        "daftar_unit": daftar_unit,
        "persyaratan_dasar": persyaratan_dasar,
        "persyaratan_admin": persyaratan_admin,
    }

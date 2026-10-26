"""
SKKNI Extractor - Integrasi API Kemnaker RI (Sinkronisasi Status Regulasi).

Fitur:
1. Pengecekan otomatis status SKKNI (Berlaku / Dicabut) ke server resmi Kemnaker RI:
   https://skkni-api.kemnaker.go.id/v1/public/documents
2. Ekstraksi otomatis Kepmenaker Pengganti bila SKKNI telah dicabut (misal: 2018-107).
3. Penyimpanan cache lokal di data/kemnaker_catalog.json agar aplikasi tetap cepat & offline-first.
4. Sinkronisasi satu dokumen atau seluruh dokumen di perpustakaan lokal.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app import db, library
from app.logging_config import ambil_logger
from app.paths import DATA_DIR, ROOT

logger = ambil_logger("kemnaker_sync")

KATALOG_PATH = DATA_DIR / "kemnaker_catalog.json"
BASE_API = "https://skkni-api.kemnaker.go.id/v1/public/documents"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SKKNI-Extractor/1.0"
TIMEOUT_DETIK = 8


def ekstrak_nomor_tahun_dari_teks_atau_nama(
    nomor: Optional[Any], tahun: Optional[Any], nama_berkas: str = ""
) -> Tuple[Optional[str], Optional[str]]:
    """Ekstrak nomor dan tahun dari input atau nama berkas bila belum ada."""
    no_str = str(nomor).strip() if nomor else ""
    th_str = str(tahun).strip() if tahun else ""

    if no_str and th_str:
        # Bersihkan format nomor agar berupa angka murni bila memungkinkan
        if no_str.isdigit():
            no_str = str(int(no_str))
        return no_str, th_str

    # Coba ekstrak dari nama berkas bila ada
    if nama_berkas:
        # Pola: SKKNI 2007-115 atau 2007_115
        m1 = re.search(r"(\d{4})[-_](\d+)", nama_berkas)
        if m1:
            th_str = m1.group(1)
            no_str = str(int(m1.group(2)))
            return no_str, th_str

        # Pola: 115-2007 atau 115_2007
        m2 = re.search(r"(\d+)[-_](\d{4})", nama_berkas)
        if m2:
            no_str = str(int(m2.group(1)))
            th_str = m2.group(2)
            return no_str, th_str

    return (no_str or None, th_str or None)


def _format_pengganti(notes: Optional[str]) -> str:
    """Format string catatan pengganti dari Kemnaker (misal: '2018-107')."""
    if not notes:
        return ""
    catatan = str(notes).strip()
    m = re.search(r"(\d{4})[-_](\d+)", catatan)
    if m:
        th, no = m.group(1), str(int(m.group(2)))
        return f"Kepmenaker No. {no} Tahun {th} (SKKNI {th}-{no.zfill(3)})"
    return catatan


def muat_katalog_lokal() -> List[Dict[str, Any]]:
    """Muat data katalog Kemnaker dari cache lokal."""
    if not KATALOG_PATH.exists():
        return []
    try:
        data = json.loads(KATALOG_PATH.read_text(encoding="utf-8"))
        return data.get("documents", [])
    except Exception as e:
        logger.warning(f"Gagal membaca katalog lokal Kemnaker: {e}")
        return []


def unduh_katalog_kemnaker(maks_halaman: int = 26) -> Dict[str, Any]:
    """Unduh katalog dokumen SKKNI lengkap dari API Kemnaker RI dan simpan ke basis data."""
    semua_dokumen: List[Dict[str, Any]] = []
    logger.info("Memulai pengunduhan katalog SKKNI dari Kemnaker RI...")

    for halaman in range(1, maks_halaman + 1):
        url = f"{BASE_API}?page={halaman}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_DETIK) as resp:
                if resp.status != 200:
                    break
                payload = json.loads(resp.read().decode("utf-8"))
                items = payload.get("data", [])
                if not items:
                    break
                semua_dokumen.extend(items)
        except Exception as e:
            logger.warning(f"Gagal mengambil halaman {halaman} dari Kemnaker: {e}")
            break

    if not semua_dokumen:
        return {"sukses": False, "pesan": "Tidak dapat terhubung ke skkni-api.kemnaker.go.id"}

    # Simpan ke cache JSON lokal
    cache_payload = {
        "diperbarui_pada": datetime.now().isoformat(),
        "total": len(semua_dokumen),
        "documents": semua_dokumen,
    }
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        KATALOG_PATH.write_text(json.dumps(cache_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.error(f"Gagal menulis cache katalog Kemnaker: {e}")

    # Simpan ke SQLite tabel regulasi_skkni
    tersimpan = 0
    for d in semua_dokumen:
        no = str(d.get("number") or "").strip()
        pub = str(d.get("published_at") or "").strip()
        th = pub[:4] if len(pub) >= 4 else ""
        if not no or not th:
            continue

        status = "dicabut" if d.get("availability") == "cancelled" else "berlaku"
        pengganti = _format_pengganti(d.get("notes"))
        kode_pola = f"{th}-{str(int(no)).zfill(3)}" if no.isdigit() else f"{th}-{no}"
        nomor_kepmen = d.get("number_kepmen") or f"Nomor {no} Tahun {th}"
        judul = d.get("sector") or d.get("title") or ""

        db.simpan_status_regulasi(
            kode_skkni=kode_pola,
            status_regulasi=status,
            nomor_kepmen=nomor_kepmen,
            judul_skkni=judul,
            kepmen_pengganti=pengganti,
            catatan=d.get("notes") or "",
        )
        tersimpan += 1

    logger.info(f"Katalog Kemnaker berhasil disinkronkan: {len(semua_dokumen)} dokumen ({tersimpan} regulasi tersimpan).")
    return {
        "sukses": True,
        "total_diunduh": len(semua_dokumen),
        "tersimpan_db": tersimpan,
        "waktu": cache_payload["diperbarui_pada"],
    }


def cari_regulasi_kemnaker(
    nomor: Optional[Any], tahun: Optional[Any], nama_berkas: str = "", unduh_jika_kosong: bool = True
) -> Optional[Dict[str, Any]]:
    """Cari status regulasi SKKNI tertentu dari katalog lokal atau langsung ke server Kemnaker."""
    no_target, th_target = ekstrak_nomor_tahun_dari_teks_atau_nama(nomor, tahun, nama_berkas)
    if not (no_target and th_target):
        return None

    # 1. Cek dari katalog lokal terlebih dahulu
    katalog = muat_katalog_lokal()
    if not katalog and unduh_jika_kosong:
        res = unduh_katalog_kemnaker(maks_halaman=26)
        if res.get("sukses"):
            katalog = muat_katalog_lokal()

    for d in katalog:
        d_no = str(d.get("number") or "").strip()
        d_pub = str(d.get("published_at") or "")
        d_nk = str(d.get("number_kepmen") or "")
        d_fn = str(d.get("file_name") or "")

        nomor_sama = False
        if no_target.isdigit() and d_no.isdigit():
            nomor_sama = int(no_target) == int(d_no)
        else:
            nomor_sama = no_target == d_no or f"Nomor {no_target} " in d_nk or f"-{no_target}" in d_fn

        tahun_sama = th_target in d_nk or th_target in d_fn or th_target in d_pub

        if nomor_sama and tahun_sama:
            status = "dicabut" if d.get("availability") == "cancelled" else "berlaku"
            return {
                "ditemukan": True,
                "nomor": no_target,
                "tahun": th_target,
                "status_regulasi": status,
                "kepmen_pengganti": _format_pengganti(d.get("notes")),
                "nomor_kepmen": d_nk or f"Nomor {no_target} Tahun {th_target}",
                "judul": d.get("sector") or d.get("title") or "",
                "file_name": d_fn,
                "notes": d.get("notes") or "",
            }

    return None


def sinkronkan_dokumen_tunggal(doc_id: str) -> Dict[str, Any]:
    """Sinkronkan status dokumen lokal tertentu dengan server Kemnaker RI."""
    dok = library.ambil_dokumen(doc_id)
    if not dok:
        return {"sukses": False, "pesan": "Dokumen tidak ditemukan di perpustakaan lokal."}

    no = dok.get("nomor")
    th = dok.get("tahun")
    nama = dok.get("nama_asli") or ""

    info = cari_regulasi_kemnaker(no, th, nama_berkas=nama, unduh_jika_kosong=True)
    if not info:
        return {
            "sukses": False,
            "pesan": f"Data SKKNI tidak ditemukan pada portal Kemnaker RI untuk {nama}.",
        }

    nomor_str = str(info["nomor"])
    tahun_str = str(info["tahun"])
    status_reg = info["status_regulasi"]
    pengganti = info["kepmen_pengganti"]
    nomor_kepmen = info["nomor_kepmen"]
    judul = info["judul"]

    kode_pola = f"{tahun_str}-{nomor_str.zfill(3)}"

    # Simpan ke SQLite untuk kedua identitas
    db.simpan_status_regulasi(
        kode_skkni=kode_pola,
        status_regulasi=status_reg,
        nomor_kepmen=nomor_kepmen,
        judul_skkni=judul or dok.get("judul") or "",
        kepmen_pengganti=pengganti,
        catatan=info.get("notes") or "",
    )
    if kode_pola != doc_id:
        db.simpan_status_regulasi(
            kode_skkni=doc_id,
            status_regulasi=status_reg,
            nomor_kepmen=nomor_kepmen,
            judul_skkni=judul or dok.get("judul") or "",
            kepmen_pengganti=pengganti,
            catatan=info.get("notes") or "",
        )

    # Perbarui metadata dokumen jika sebelumnya nomor/tahun/judul belum ada
    perubahan = False
    if not dok.get("nomor") and nomor_str:
        dok["nomor"] = nomor_str
        perubahan = True
    if not dok.get("tahun") and tahun_str:
        dok["tahun"] = tahun_str
        perubahan = True
    if (not dok.get("judul") or dok.get("judul") == "—") and judul:
        dok["judul"] = judul
        perubahan = True
    if perubahan:
        library.simpan_metadata(dok)

    return {
        "sukses": True,
        "doc_id": doc_id,
        "nomor": nomor_str,
        "tahun": tahun_str,
        "judul": judul,
        "status_regulasi": status_reg,
        "kepmen_pengganti": pengganti,
        "pesan": (
            f"Status berhasil disinkronkan dari Kemnaker: "
            f"{'DICABUT' if status_reg == 'dicabut' else 'BERLAKU'}"
            + (f" (Pengganti: {pengganti})" if pengganti else "")
        ),
    }


def sinkronkan_seluruh_perpustakaan() -> Dict[str, Any]:
    """Perbarui status seluruh dokumen SKKNI lokal berdasarkan data Kemnaker."""
    unduh_res = unduh_katalog_kemnaker(maks_halaman=26)
    if not unduh_res.get("sukses"):
        return unduh_res

    dokumen_lokal = library.daftar_dokumen()
    diperbarui = 0

    for dok in dokumen_lokal:
        did = dok.get("id")
        if not did:
            continue
        res = sinkronkan_dokumen_tunggal(did)
        if res.get("sukses"):
            diperbarui += 1

    return {
        "sukses": True,
        "total_dokumen_lokal": len(dokumen_lokal),
        "terupdate": diperbarui,
        "total_katalog_kemnaker": unduh_res.get("total_diunduh", 0),
    }

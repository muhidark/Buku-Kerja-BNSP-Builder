"""
SKKNI Extractor - Modul Generator Buku Kerja Asesor & Manajemen Materi Uji Kompetensi (MUK) V.2023.

Menyediakan penyusunan data terstruktur & penyimpanan konfigurasi per skema untuk:
- 01. FR.APL.01: Permohonan Sertifikasi Kompetensi (Murni Template / Blank Asesi)
- 02. FR.APL.02: Asesmen Mandiri (Terisi Unit, Elemen [Dapatkah Saya...?], dan KUK lengkap dari SKKNI)
- 04. FR.MAPA.01: Merencanakan Aktivitas dan Proses Asesmen (Observasi / DIT / Portofolio)
- 05c. Peta Kelompok Pekerjaan
- 06. FR.MAPA.02: Peta Instrumen Asesmen
- 07. FR.AK.07: Ceklis Penyesuaian yang Wajar dan Beralasan
- 08. FR.AK.04: Banding Asesmen
- 09. FR.AK.01: Persetujuan Asesmen dan Kerahasiaan
- 10. FR.IA.01: CL - Ceklis Observasi Aktivitas di Tempat Kerja / Simulasi
- 11. FR.IA.02: TPD - Tugas Praktik Demonstrasi
- 12. FR.IA.03: PMO - Pertanyaan Untuk Mendukung Observasi
- 13a. FR.IA.04A: DIT - Penjelasan Proyek Singkat / Kegiatan Terstruktur
- 13b. FR.IA.04B: DIT - Penilaian Proyek Singkat / Kegiatan Terstruktur
- 14a/b/c. FR.IA.05A, FR.IA.05B, FR.IA.05C: Soal, Kunci, & Lembar Jawaban Pilihan Ganda
- 15a/b/c. FR.IA.06A, FR.IA.06.B, FR.IA.06.C: Soal, Kunci, & Lembar Jawaban Pertanyaan Tertulis Esai
- 16. FR.IA.07: DPL - Daftar Pertanyaan Lisan
- 17. FR.IA.08: CVP - Ceklis Verifikasi Portofolio
- 21. FR.AK.02: Rekaman Asesmen Kompetensi
- 22. FR.AK.03: Umpan Balik dan Catatan Asesmen
- 23. FR.AK.05: Laporan Asesmen
- 24. FR.AK.06: Meninjau Proses Asesmen
- 25. FR.VA: Memberikan Kontribusi dalam Validasi Asesmen (Form Kosongan)
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app import penyimpanan
from app import db, schema_library, status_units
from app.lsp_exporter import ambil_json_unit
from scripts.migrasi_muk_v2 import ekstrak_menit_durasi, migrasikan_objek_muk, pisahkan_kuk

ROOT = Path(__file__).resolve().parent.parent
MUK_DIR = ROOT / "data" / "schema_library" / "muk"

# Daftar dokumen yang didukung beserta label resminya
DAFTAR_DOKUMEN_BUKU_KERJA = [
    {"kode": "all", "label": "📚 Semua Dokumen (Paket Lengkap Urutan 0–25)"},
    {"kode": "daftar_periksa", "label": "0. DAFTAR PERIKSA — Kelengkapan Dokumen Upgrading-RCC"},
    {"kode": "paket_observasi", "label": "📦 Paket Metode Observasi Langsung (CLO + TPD + PMO + DPT)"},
    {"kode": "paket_dit", "label": "📦 Paket Metode Proyek Singkat / Kegiatan Terstruktur (DIT + DPT)"},
    {"kode": "paket_portofolio", "label": "📦 Paket Metode Verifikasi Portofolio (CVP + DPT)"},
    {"kode": "apl01", "label": "1. FR.APL.01 — Permohonan Sertifikasi Kompetensi"},
    {"kode": "apl02", "label": "2. FR.APL.02 — Asesmen Mandiri"},
    {"kode": "mapa01", "label": "4. FR.MAPA.01 — Merencanakan Aktivitas dan Proses Asesmen"},
    {"kode": "skema_dok", "label": "5a. SKEMA — Dokumen Skema Sertifikasi yang Diunggah"},
    {"kode": "skkni_dok", "label": "5b. SKKNI — Dokumen Standar Kompetensi Kerja (SKKNI) Terekstraksi"},
    {"kode": "peta_kelompok", "label": "5c. Peta Kelompok Pekerjaan"},
    {"kode": "mapa02", "label": "6. FR.MAPA.02 — Peta Instrumen Asesmen"},
    {"kode": "ak07", "label": "7. FR.AK.07 — Ceklis Penyesuaian yang Wajar dan Beralasan"},
    {"kode": "ak04", "label": "8. FR.AK.04 — Banding Asesmen"},
    {"kode": "ak01", "label": "9. FR.AK.01 — Persetujuan Asesmen dan Kerahasiaan"},
    {"kode": "ia01", "label": "10. FR.IA.01 — CL: Ceklis Observasi Aktivitas di Tempat Kerja"},
    {"kode": "ia02", "label": "11. FR.IA.02 — TPD: Tugas Praktik Demonstrasi"},
    {"kode": "ia03", "label": "12. FR.IA.03 — PMO: Pertanyaan Untuk Mendukung Observasi"},
    {"kode": "ia04a", "label": "13a. FR.IA.04A — DIT: Penjelasan Proyek Singkat / Kegiatan Terstruktur"},
    {"kode": "ia04b", "label": "13b. FR.IA.04B — DIT: Penilaian Proyek Singkat / Kegiatan Terstruktur"},
    {"kode": "ia05a", "label": "14a. FR.IA.05A — DPT: Pertanyaan Tertulis Pilihan Ganda"},
    {"kode": "ia05b", "label": "14b. FR.IA.05B — Lembar Kunci Jawaban Pilihan Ganda"},
    {"kode": "ia05c", "label": "14c. FR.IA.05C — Lembar Jawaban Pilihan Ganda"},
    {"kode": "ia06a", "label": "15a. FR.IA.06A — DPT: Daftar Pertanyaan Tertulis Esai"},
    {"kode": "ia06b", "label": "15b. FR.IA.06.B — Lembar Kunci Jawaban Pertanyaan Tertulis Esai"},
    {"kode": "ia06c", "label": "15c. FR.IA.06.C — Lembar Jawaban Pertanyaan Tertulis Esai"},
    {"kode": "ia07", "label": "16. FR.IA.07 — DPL: Daftar Pertanyaan Lisan"},
    {"kode": "ia08", "label": "17. FR.IA.08 — CVP: Ceklis Verifikasi Portofolio"},
    {"kode": "ak02", "label": "21. FR.AK.02 — Rekaman Asesmen Kompetensi"},
    {"kode": "ak03", "label": "22. FR.AK.03 — Umpan Balik dan Catatan Asesmen"},
    {"kode": "ak05", "label": "23. FR.AK.05 — Laporan Asesmen"},
    {"kode": "ak06", "label": "24. FR.AK.06 — Meninjau Proses Asesmen"},
    {"kode": "va", "label": "25. FR.VA — Memberikan Kontribusi dalam Validasi Asesmen"},
]

DIMENSI_KOMPETENSI_LABELS = {
    "TS": "TS - Task Skills",
    "TMS": "TMS - Task Management Skills",
    "CMS": "CMS - Contingency Management Skills",
    "JRES": "JRES - Job/Role Environment Skills",
    "TRS": "TRS - Transfer Skills",
}


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
    elif "J.591" in kode or "J.59" in kode:
        return "SKKNI 2024-171"
    elif fallback_standar:
        return fallback_standar
    return "Standar Khusus / SKKNI"


def format_elemen_apl02(nama_elemen: str) -> str:
    """
    Mengubah kalimat judul elemen menjadi kalimat tanya 'Dapatkah Saya ...?'
    sesuai standar pengisian FR.APL.02 BNSP.
    """
    teks = (nama_elemen or "").strip()
    if not teks:
        return "Dapatkah Saya melaksanakan elemen kompetensi ini?"
    teks_bersih = teks.rstrip(".?!")
    if teks_bersih.lower().startswith("dapatkah saya"):
        return teks_bersih + "?"
    huruf_awal = teks_bersih[0].lower() + teks_bersih[1:] if len(teks_bersih) > 1 else teks_bersih.lower()
    return f"Dapatkah Saya {huruf_awal}?"


def parse_kunci_jawaban_ia05(raw_kunci: str, jumlah_soal: int = 10) -> Dict[int, str]:
    """
    Mem-parse teks multiline kunci jawaban menjadi dictionary {nomor_soal: jawaban}.
    Mendukung format:
    - "1. B" / "1: B" / "1 - B" / "1 B"
    - "B" per baris (otomatis diurutkan 1, 2, 3...)
    """
    if not raw_kunci or not raw_kunci.strip():
        return {}
    lines = re.split(r"\r\n|\r|\n", raw_kunci.strip())
    parsed: Dict[int, str] = {}
    auto_idx = 1
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(\d+)[\.\:\-\s\)]+\s*([A-Za-z0-9]+)", line)
        if m:
            num = int(m.group(1))
            ans = m.group(2).strip().upper()
            parsed[num] = ans
            auto_idx = max(auto_idx, num + 1)
        elif re.match(r"^[A-Za-z0-9]+$", line):
            parsed[auto_idx] = line.upper()
            auto_idx += 1
        else:
            parsed[auto_idx] = line
            auto_idx += 1
    return parsed


def _jalur_muk(schema_id: str) -> Path:
    aman = re.sub(r"[^a-zA-Z0-9_-]", "", schema_id or "")
    if not aman:
        raise ValueError("ID skema tidak sah.")
    MUK_DIR.mkdir(parents=True, exist_ok=True)
    return MUK_DIR / f"{aman}.json"


def _bersih_teks_item_skkni(teks: str) -> str:
    """Membersihkan teks butir BV/PP dan menyaring nilai kosong / '(Tidak ada.)'."""
    t = re.sub(r"\s+", " ", (teks or "")).strip()
    if not t:
        return ""
    t_low = t.lower().strip("(). ")
    if t_low in ("tidak ada", "tidak diperlukan", "-"):
        return ""
    return t


def _kumpulkan_daun_section(nodes: List[Dict[str, Any]]) -> List[str]:
    """Mengambil butir teks terdalam (leaf nodes) dari pohon section BV/PP."""
    hasil: List[str] = []
    for node in nodes or []:
        sub = node.get("items") or []
        if sub:
            hasil.extend(_kumpulkan_daun_section(sub))
        else:
            t = _bersih_teks_item_skkni(node.get("teks") or node.get("judul") or "")
            if t:
                hasil.append(t)
    return hasil


def ringkas_bv_pp_unit(raw_bv: Optional[Dict[str, Any]], raw_pp: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Mengekstrak komponen terstruktur Batasan Variabel (BV) & Panduan Penilaian (PP)
    dari JSON unit kompetensi SKKNI untuk asisten penyusunan MUK otomatis:
    - BV: konteks_variabel, peralatan, perlengkapan, peraturan, norma_standar
    - PP: konteks_penilaian, persyaratan_kompetensi, pengetahuan, keterampilan, sikap_kerja, aspek_kritis
    """
    bv_sections = (raw_bv or {}).get("sections") or []
    pp_sections = (raw_pp or {}).get("sections") or []

    konteks_variabel: List[str] = []
    peralatan: List[str] = []
    perlengkapan: List[str] = []
    peraturan: List[str] = []
    norma_standar: List[str] = []

    for sec in bv_sections:
        no = str(sec.get("nomor") or "").strip()
        jdl = (sec.get("teks") or sec.get("judul") or "").lower()
        items = sec.get("items") or []

        if no == "1" or "konteks" in jdl:
            konteks_variabel.extend(_kumpulkan_daun_section(items))
        elif no == "2" or "peralatan" in jdl or "perlengkapan" in jdl:
            for sub in items:
                sub_no = str(sub.get("nomor") or "").strip()
                sub_jdl = (sub.get("teks") or sub.get("judul") or "").lower()
                sub_items = sub.get("items") or []
                if sub_no == "2.1" or "peralatan" in sub_jdl:
                    peralatan.extend(_kumpulkan_daun_section(sub_items) if sub_items else _kumpulkan_daun_section([sub]))
                elif sub_no == "2.2" or "perlengkapan" in sub_jdl:
                    perlengkapan.extend(_kumpulkan_daun_section(sub_items) if sub_items else _kumpulkan_daun_section([sub]))
                else:
                    peralatan.extend(_kumpulkan_daun_section([sub]))
        elif no == "3" or "peraturan" in jdl:
            peraturan.extend(_kumpulkan_daun_section(items))
        elif no == "4" or "norma" in jdl or "standar" in jdl:
            norma_standar.extend(_kumpulkan_daun_section(items))

    konteks_penilaian: List[str] = []
    persyaratan_kompetensi: List[str] = []
    pengetahuan: List[str] = []
    keterampilan: List[str] = []
    sikap_kerja: List[str] = []
    aspek_kritis: List[str] = []

    for sec in pp_sections:
        no = str(sec.get("nomor") or "").strip()
        jdl = (sec.get("teks") or sec.get("judul") or "").lower()
        items = sec.get("items") or []

        if no == "1" or "konteks" in jdl:
            konteks_penilaian.extend(_kumpulkan_daun_section(items))
        elif no == "2" or "persyaratan" in jdl:
            persyaratan_kompetensi.extend(_kumpulkan_daun_section(items))
        elif no == "3" or "pengetahuan" in jdl or "keterampilan" in jdl:
            for sub in items:
                sub_no = str(sub.get("nomor") or "").strip()
                sub_jdl = (sub.get("teks") or sub.get("judul") or "").lower()
                sub_items = sub.get("items") or []
                if sub_no == "3.1" or "pengetahuan" in sub_jdl:
                    pengetahuan.extend(_kumpulkan_daun_section(sub_items) if sub_items else _kumpulkan_daun_section([sub]))
                elif sub_no == "3.2" or "keterampilan" in sub_jdl:
                    keterampilan.extend(_kumpulkan_daun_section(sub_items) if sub_items else _kumpulkan_daun_section([sub]))
                else:
                    pengetahuan.extend(_kumpulkan_daun_section([sub]))
        elif no == "4" or "sikap" in jdl:
            sikap_kerja.extend(_kumpulkan_daun_section(items))
        elif no == "5" or "aspek kritis" in jdl or "kritis" in jdl:
            aspek_kritis.extend(_kumpulkan_daun_section(items))

    ada_isi = bool(
        konteks_variabel or peralatan or perlengkapan or peraturan or norma_standar
        or pengetahuan or keterampilan or sikap_kerja or aspek_kritis
    )
    return {
        "ada_isi": ada_isi,
        "konteks_variabel": konteks_variabel,
        "peralatan": peralatan,
        "perlengkapan": perlengkapan,
        "peraturan": peraturan,
        "norma_standar": norma_standar,
        "konteks_penilaian": konteks_penilaian,
        "persyaratan_kompetensi": persyaratan_kompetensi,
        "pengetahuan": pengetahuan,
        "keterampilan": keterampilan,
        "sikap_kerja": sikap_kerja,
        "aspek_kritis": aspek_kritis,
    }


def agregasi_referensi_bv_pp_skema(daftar_unit: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Mengagregasi seluruh Batasan Variabel & Panduan Penilaian lintas unit kompetensi skema."""
    peralatan_unik: List[str] = []
    perlengkapan_unik: List[str] = []
    norma_unik: List[str] = []
    aspek_kritis_list: List[Dict[str, str]] = []
    pengetahuan_list: List[Dict[str, str]] = []
    keterampilan_list: List[Dict[str, str]] = []
    sikap_kerja_list: List[Dict[str, str]] = []
    unit_dengan_bv_pp = 0

    for u in daftar_unit or []:
        kode = u.get("kode_unit") or ""
        judul = u.get("judul_unit") or ""
        ringkasan = u.get("ringkasan_bv_pp")
        if not ringkasan:
            ringkasan = ringkas_bv_pp_unit(u.get("batasan_variabel"), u.get("panduan_penilaian"))

        if ringkasan.get("ada_isi"):
            unit_dengan_bv_pp += 1

        for item in ringkasan.get("peralatan") or []:
            if item.lower() not in {x.lower() for x in peralatan_unik}:
                peralatan_unik.append(item)
        for item in ringkasan.get("perlengkapan") or []:
            if item.lower() not in {x.lower() for x in perlengkapan_unik}:
                perlengkapan_unik.append(item)
        for item in ringkasan.get("norma_standar") or []:
            if item.lower() not in {x.lower() for x in norma_unik}:
                norma_unik.append(item)

        for ak in ringkasan.get("aspek_kritis") or []:
            aspek_kritis_list.append({"kode_unit": kode, "judul_unit": judul, "teks": ak})
        for pg in ringkasan.get("pengetahuan") or []:
            pengetahuan_list.append({"kode_unit": kode, "judul_unit": judul, "teks": pg})
        for kt in ringkasan.get("keterampilan") or []:
            keterampilan_list.append({"kode_unit": kode, "judul_unit": judul, "teks": kt})
        for sk in ringkasan.get("sikap_kerja") or []:
            sikap_kerja_list.append({"kode_unit": kode, "judul_unit": judul, "teks": sk})

    return {
        "unit_dengan_bv_pp": unit_dengan_bv_pp,
        "total_unit": len(daftar_unit or []),
        "peralatan_unik": peralatan_unik,
        "perlengkapan_unik": perlengkapan_unik,
        "norma_unik": norma_unik,
        "aspek_kritis_list": aspek_kritis_list,
        "pengetahuan_list": pengetahuan_list,
        "keterampilan_list": keterampilan_list,
        "sikap_kerja_list": sikap_kerja_list,
    }


def default_instrumen_untuk_kelompok(
    grp: Dict[str, Any],
    nama_skema: str = "Skema Sertifikasi",
    ref_skkni: Optional[Dict[str, Any]] = None,
    units_detail: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Menyusun paket instrumen default (IA.01, IA.02, IA.03, IA.04A, IA.04B) untuk satu kelompok pekerjaan."""
    nama_kelompok = grp.get("nama") or "Kelompok Pekerjaan"
    units = grp.get("units") or []
    ref = ref_skkni or {}

    unit_pertama = units[0] if units else "Unit 1"
    unit_kedua = units[1] if len(units) > 1 else unit_pertama

    langkah_default = [
        f"1. Mempersiapkan perlengkapan dan peralatan untuk pelaksanaan tugas {nama_kelompok}.",
        "2. Melaksanakan tahapan pekerjaan sesuai SOP, standar industri, dan regulasi K3.",
        "3. Memeriksa kualitas hasil kerja serta menyusun laporan penyelesaian tugas kepada asesor.",
    ]

    ia03_questions = [
        {
            "order": 1,
            "unit_kode": unit_pertama,
            "kuk": ["1.1"],
            "dimensi": "CMS",
            "pertanyaan": f"Jika pada saat pelaksanaan tugas {nama_kelompok} terjadi kendala teknis tak terduga (misalnya peralatan utama mati mendadak, data rusak, atau koneksi terputus), tindakan darurat dan sistematis apa yang pertama kali Anda lakukan?",
            "kunci_jawaban": "Asesi mampu menjelaskan prosedur darurat penanganan insiden, isolasi masalah, dan pelaporan kepada penanggung jawab sesuai SOP keselamatan kerja.",
        },
        {
            "order": 2,
            "unit_kode": unit_pertama,
            "kuk": ["1.2"],
            "dimensi": "TRS",
            "pertanyaan": f"Jika lingkungan kerja atau peralatan/sistem yang digunakan pada {nama_kelompok} mengalami pembaruan spesifikasi atau SOP baru, bagaimana strategi Anda untuk beradaptasi cepat agar hasil kerja tetap memenuhi standar?",
            "kunci_jawaban": "Asesi mampu menerapkan prinsip transfer skills, mempelajari manual/SOP baru, serta melakukan penyesuaian fungsional secara mandiri.",
        },
        {
            "order": 3,
            "unit_kode": unit_kedua,
            "kuk": ["2.1"],
            "dimensi": "JRES",
            "pertanyaan": f"Sebutkan prosedur dasar Keselamatan dan Kesehatan Kerja (K3) serta standar komunikasi profesional yang wajib Anda patuhi selama melaksanakan tugas {nama_kelompok}!",
            "kunci_jawaban": "Asesi mematuhi regulasi K3 lingkungan kerja, penggunaan APD/ergonomi yang tepat, dan komunikasi profesional kepada asesor maupun rekan kerja.",
        },
        {
            "order": 4,
            "unit_kode": unit_kedua,
            "kuk": ["2.2"],
            "dimensi": "TS",
            "pertanyaan": f"Jelaskan langkah-langkah kritis dalam memverifikasi ketepatan dan kualitas hasil kerja {nama_kelompok} sebelum diserahkan kepada pihak terkait!",
            "kunci_jawaban": "Asesi melakukan verifikasi kualitas (quality control) terhadap spesifikasi keluaran, memastikan kesesuaian SOP, dan melengkapi bukti serah terima.",
        },
    ]

    ia04_questions = [
        {
            "order": 1,
            "lingkup": f"Perencanaan dan persiapan pelaksanaan {nama_kelompok}",
            "unit_kode": unit_pertama,
            "kuk": ["1.1"],
            "dimensi": "(TS, TMS)",
            "pertanyaan": f"Jelaskan tahapan perencanaan dan persiapan yang Anda lakukan dalam menyelesaikan proyek singkat {nama_kelompok} ini!",
        },
        {
            "order": 2,
            "lingkup": f"Kesesuaian mutu hasil kerja {nama_kelompok} terhadap SOP industri",
            "unit_kode": unit_kedua,
            "kuk": ["2.1"],
            "dimensi": "(TS, JRES)",
            "pertanyaan": f"Bagaimana Anda memastikan hasil keluaran proyek {nama_kelompok} telah memenuhi spesifikasi teknis dan standar kualitas yang ditetapkan?",
        },
        {
            "order": 3,
            "lingkup": "Penanganan kendala teknis dan manajemen waktu pengerjaan proyek",
            "unit_kode": units[-1] if units else unit_pertama,
            "kuk": ["2.2"],
            "dimensi": "(CMS, TRS)",
            "pertanyaan": "Jika terjadi perubahan kebutuhan mendadak atau kendala peralatan saat pengerjaan proyek, langkah antisipasi apa yang Anda terapkan?",
        },
    ]

    perlengkapan_text = (
        "\n".join(ref.get("perlengkapan_unik", []))
        if ref.get("perlengkapan_unik")
        else (
            "Alat Keselamatan & Kesehatan Kerja (K3)\n"
            "Perangkat media penyimpanan / flashdisk / cloud\n"
            "Bahan penunjang demonstrasi / dokumen kerja\n"
            "Formulir checklist laporan pekerjaan"
        )
    )
    peralatan_text = (
        "\n".join(ref.get("peralatan_unik", []))
        if ref.get("peralatan_unik")
        else (
            "Komputer / laptop / gawai penunjang\n"
            "Perangkat kerja spesifik bidang profesi\n"
            "Aksesori / peripheral pendukung teknis\n"
            "Alat Tulis Kantor (ATK)"
        )
    )

    return {
        "ia01": {
            "fokus_observasi": f"Observasi aktivitas praktik {nama_kelompok}",
            "kondisi_kerja": "Tempat kerja nyata atau tempat kerja simulasi dengan peralatan standar",
            "indikator_kritis": [],
        },
        "ia02": {
            "skenario": (
                f"Anda seorang asesi sedang melaksanakan sertifikasi skema {nama_skema}. "
                f"Pada tugas demonstrasi ini, Anda diminta menyelesaikan tugas praktik untuk {nama_kelompok} "
                "secara profesional, terstruktur, dan memenuhi standar keselamatan kerja yang berlaku."
            ),
            "langkah_kerja": "\n".join(langkah_default),
            "hasil_kerja": (
                f"Hasil pekerjaan {nama_kelompok} berupa demonstrasi fisik/praktik langsung, bukti karya/dokumen pendukung, "
                "dan lembar verifikasi hasil pekerjaan yang diserahkan kepada asesor."
            ),
            "perlengkapan": perlengkapan_text,
            "peralatan": peralatan_text,
            "durasi_menit": 120,
            "durasi_waktu": "120 Menit",
        },
        "ia03": {
            "panduan": "",
            "questions": ia03_questions,
        },
        "ia04a": {
            "judul_kegiatan": f"Proyek Terstruktur {nama_kelompok}",
            "judul_proyek": f"Proyek Terstruktur {nama_kelompok}",
            "situasi": (
                f"Anda ditugaskan sebagai tenaga profesional pada bidang {nama_skema} untuk menyelesaikan "
                f"proyek kerja {nama_kelompok} sesuai brief dan standar operasional prosedur (SOP) industri."
            ),
            "tugas": (
                f"Menyusun perencanaan, menyiapkan perangkat/dokumen kerja, mengeksekusi tahapan kerja {nama_kelompok}, "
                "serta mempresentasikan hasil akhir proyek di hadapan asesor."
            ),
            "tindakan": "\n".join(langkah_default),
            "data_informasi": f"Dokumen brief proyek, SOP tempat kerja, standar K3, dan perangkat kerja pendukung {nama_kelompok}.",
            "hasil": f"Dokumen perencanaan, produk/karya hasil kerja {nama_kelompok}, dan materi presentasi hasil proyek.",
            "hal_demonstrasi": (
                "1. Penjelasan alur perencanaan dan konsep kerja.\n"
                "2. Demonstrasi hasil proyek singkat / produk kerja yang telah diselesaikan.\n"
                "3. Tanya jawab terkait pemenuhan kriteria unjuk kerja dan pemecahan masalah (problem solving)."
            ),
            "waktu_proyek": "240 menit",
            "waktu_presentasi": "30 menit",
            "questions": ia04_questions,
        },
        "ia04b": {
            "questions": ia04_questions,
        },
    }


def default_konfigurasi_muk(nama_skema: str, daftar_unit: List[Dict[str, Any]], nomor_skema: str = "") -> Dict[str, Any]:
    """Menyusun konfigurasi default MUK & Kelompok Pekerjaan (v2) untuk suatu skema."""
    semua_kode = [u["kode_unit"] for u in daftar_unit if u.get("kode_unit")]
    ref_skkni = agregasi_referensi_bv_pp_skema(daftar_unit)

    kelompok_awal = []
    if semua_kode:
        kp1 = {
            "id": "kp_1",
            "nama": f"Kelompok Pekerjaan 1 ({nama_skema})",
            "urutan": 1,
            "units": semua_kode,
            "durasi_menit": 120,
        }
        kp1["instrumen"] = default_instrumen_untuk_kelompok(kp1, nama_skema=nama_skema, ref_skkni=ref_skkni)
        kelompok_awal.append(kp1)

    ia02_mirror = kelompok_awal[0]["instrumen"]["ia02"] if kelompok_awal else {
        "skenario": f"Skenario praktik skema {nama_skema}",
        "langkah_kerja": "1. Persiapan\n2. Pelaksanaan\n3. Pelaporan",
        "hasil_kerja": "Bukti hasil kerja praktik",
        "perlengkapan": "Perlengkapan standar kerja",
        "peralatan": "Peralatan standar kerja",
        "durasi_menit": 120,
        "durasi_waktu": "120 Menit",
    }
    ia03_mirror = kelompok_awal[0]["instrumen"]["ia03"] if kelompok_awal else {"panduan": "", "questions": []}
    ia04_mirror = kelompok_awal[0]["instrumen"]["ia04a"] if kelompok_awal else {
        "judul_kegiatan": f"Proyek Terstruktur Skema {nama_skema}",
        "situasi": "", "tugas": "", "tindakan": "", "data_informasi": "",
        "hasil": "", "hal_demonstrasi": "", "waktu_proyek": "240 menit",
        "waktu_presentasi": "30 menit", "questions": [],
    }

    return {
        "schema_muk_version": 2,
        "personel": {
            "nomor_skema": nomor_skema,
            "nama_asesor": "",
            "no_met": "",
            "nama_tuk": "TUK Sewaktu",
            "jenis_tuk": "sewaktu",
            "metode_mapa": "observasi",
            "kategori_asesi": 1,
            "nama_penyusun": "",
            "met_penyusun": "",
            "nama_validator": "",
            "met_validator": "",
            "nama_manajer_sertifikasi": "",
            "tanggal_pelaksanaan": "",
            "tanggal_penyusunan": "",
        },
        "kelompok_pekerjaan": kelompok_awal,
        "ia02": ia02_mirror,
        "ia03": ia03_mirror,
        "ia04": ia04_mirror,
        "ia05": {
            "jumlah_soal": 10,
            "pertanyaan": "",
            "kunci": "",
        },
        "ia06": {
            "waktu": "60 Menit",
            "questions": [
                {"order": 1, "pertanyaan": "", "kunci_jawaban": ""},
                {"order": 2, "pertanyaan": "", "kunci_jawaban": ""},
                {"order": 3, "pertanyaan": "", "kunci_jawaban": ""},
                {"order": 4, "pertanyaan": "", "kunci_jawaban": ""},
                {"order": 5, "pertanyaan": "", "kunci_jawaban": ""},
            ],
        },
        "ia07": {
            "questions": [
                {"order": 1, "pertanyaan": "", "kunci_jawaban": ""},
                {"order": 2, "pertanyaan": "", "kunci_jawaban": ""},
                {"order": 3, "pertanyaan": "", "kunci_jawaban": ""},
            ],
        },
        "ia08": {
            "bukti_portofolio": ["", "", "", ""],
            "klarifikasi": [
                {"no_unit": "", "no_elemen": "", "materi": ""},
                {"no_unit": "", "no_elemen": "", "materi": ""},
                {"no_unit": "", "no_elemen": "", "materi": ""},
                {"no_unit": "", "no_elemen": "", "materi": ""},
                {"no_unit": "", "no_elemen": "", "materi": ""},
                {"no_unit": "", "no_elemen": "", "materi": ""},
            ],
            "bukti_tambahan": "",
        },
    }


def muat_konfigurasi_muk(
    schema_id: str,
    nama_skema: str = "Skema Sertifikasi",
    daftar_unit: Optional[List[Dict[str, Any]]] = None,
    nomor_skema: str = "",
    kode_versi: str = "",
) -> Dict[str, Any]:
    """Memuat konfigurasi MUK per skema (bisa spesifik versi dari DB SQLite atau default aktif)."""
    unit_list = daftar_unit or []
    default_cfg = default_konfigurasi_muk(nama_skema, unit_list, nomor_skema=nomor_skema)

    # 1. Coba ambil dari multi-versi SQLite
    saved_db = None
    if kode_versi:
        row = db.ambil_versi_muk(schema_id, kode_versi)
        if row and row.get("payload"):
            saved_db = row["payload"]
    else:
        # Cari versi aktif di SQLite
        semua_v = db.daftar_versi_muk_skema(schema_id)
        aktif_v = next((v for v in semua_v if v.get("is_aktif")), None)
        if aktif_v:
            row = db.ambil_versi_muk(schema_id, aktif_v["kode_versi"])
            if row and row.get("payload"):
                saved_db = row["payload"]

    saved = saved_db
    # 2. Bila belum ada di SQLite, muat dari file JSON legasi
    if not saved:
        try:
            jalur = _jalur_muk(schema_id)
            if jalur.exists():
                saved = penyimpanan.baca_json(jalur)
        except Exception:
            pass

    if not isinstance(saved, dict):
        return default_cfg

    # Otomatis migrasikan struktur v1 ke v2 jika diperlukan
    if saved.get("schema_muk_version") != 2:
        saved = migrasikan_objek_muk(saved)

    # Gabungkan sub-dictionary level skema/akar dengan aman
    for key in ["personel", "ia05", "ia06", "ia07", "ia08"]:
        if isinstance(saved.get(key), dict):
            default_cfg[key].update({k: v for k, v in saved[key].items() if v is not None})

    if isinstance(saved.get("kelompok_pekerjaan"), list) and len(saved["kelompok_pekerjaan"]) > 0:
        cleaned_groups = []
        for idx, grp in enumerate(saved["kelompok_pekerjaan"], start=1):
            if not isinstance(grp, dict):
                continue
            grp_copy = dict(grp)
            if "durasi_menit" not in grp_copy:
                grp_copy["durasi_menit"] = ekstrak_menit_durasi(
                    grp_copy.get("durasi_waktu") or grp_copy.get("durasi_label") or "120 Menit"
                )
            if not isinstance(grp_copy.get("instrumen"), dict) or not grp_copy["instrumen"]:
                grp_copy["instrumen"] = default_instrumen_untuk_kelompok(
                    grp_copy, nama_skema=nama_skema, ref_skkni=default_cfg.get("referensi_skkni")
                )
            cleaned_groups.append(grp_copy)
        if cleaned_groups:
            default_cfg["kelompok_pekerjaan"] = cleaned_groups

    # Perbarui mirror akar kompatibilitas mundur dari kelompok 1
    if default_cfg["kelompok_pekerjaan"]:
        k1_ins = default_cfg["kelompok_pekerjaan"][0].get("instrumen") or {}
        if isinstance(k1_ins.get("ia02"), dict):
            default_cfg["ia02"] = dict(k1_ins["ia02"])
        if isinstance(k1_ins.get("ia03"), dict):
            default_cfg["ia03"] = dict(k1_ins["ia03"])
        if isinstance(k1_ins.get("ia04a"), dict):
            default_cfg["ia04"] = dict(k1_ins["ia04a"])
    else:
        for key in ["ia02", "ia03", "ia04"]:
            if isinstance(saved.get(key), dict):
                default_cfg[key].update({k: v for k, v in saved[key].items() if v is not None})

    default_cfg["schema_muk_version"] = 2
    return default_cfg


def simpan_konfigurasi_muk(
    schema_id: str,
    payload: Dict[str, Any],
    kode_versi: str = "v1",
    nama_versi: str = "Paket MUK Utama",
    deskripsi: str = "",
    dibuat_oleh: Optional[int] = None,
    is_aktif: bool = True,
) -> Dict[str, Any]:
    """Menyimpan konfigurasi MUK & Kelompok Pekerjaan ke file disk dan basis data SQLite (multi-versi)."""
    doc = schema_library.ambil_skema(schema_id)
    nama_skema = (doc or {}).get("nama_skema") or "Skema Sertifikasi"
    nomor_skema = (doc or {}).get("nomor_dokumen") or ""
    units_raw = (doc or {}).get("units") or []
    daftar_unit = [
        {"kode_unit": u.get("kode_unit", ""), "judul_unit": u.get("judul_skema", "")}
        for u in units_raw
    ]

    cfg = muat_konfigurasi_muk(schema_id, nama_skema, daftar_unit, nomor_skema, kode_versi=kode_versi)

    # 1. Update Parsial per Kelompok: {"kelompok_id": "kp_1", "bagian": "ia02", "data": {...}}
    kelompok_id = str(payload.get("kelompok_id") or "").strip()
    bagian = str(payload.get("bagian") or "").strip().lower()

    if kelompok_id and bagian:
        target_grp = next((g for g in cfg["kelompok_pekerjaan"] if g.get("id") == kelompok_id), None)
        if not target_grp and cfg["kelompok_pekerjaan"]:
            target_grp = cfg["kelompok_pekerjaan"][0]
        elif not target_grp:
            target_grp = {
                "id": kelompok_id,
                "nama": f"Kelompok Pekerjaan 1 ({nama_skema})",
                "urutan": 1,
                "units": [u["kode_unit"] for u in daftar_unit],
                "durasi_menit": 120,
                "instrumen": {},
            }
            cfg["kelompok_pekerjaan"].append(target_grp)

        if not isinstance(target_grp.get("instrumen"), dict):
            target_grp["instrumen"] = default_instrumen_untuk_kelompok(target_grp, nama_skema)

        bdata = payload.get("data") if isinstance(payload.get("data"), dict) else payload.get(bagian, {})
        if not isinstance(bdata, dict):
            bdata = {}

        if bagian == "ia01":
            cur_ia01 = target_grp["instrumen"].setdefault("ia01", {})
            for k in ["fokus_observasi", "kondisi_kerja"]:
                if k in bdata:
                    cur_ia01[k] = str(bdata[k] or "").strip()
            if isinstance(bdata.get("indikator_kritis"), list):
                cur_ia01["indikator_kritis"] = bdata["indikator_kritis"]

        elif bagian == "ia02":
            cur_ia02 = target_grp["instrumen"].setdefault("ia02", {})
            for k in ["skenario", "langkah_kerja", "hasil_kerja", "perlengkapan", "peralatan", "durasi_waktu"]:
                if k in bdata:
                    cur_ia02[k] = str(bdata[k] or "").strip()
            durasi_val = bdata.get("durasi_menit") or bdata.get("durasi_waktu") or cur_ia02.get("durasi_waktu") or "120"
            durasi_m = ekstrak_menit_durasi(durasi_val)
            cur_ia02["durasi_menit"] = durasi_m
            cur_ia02["durasi_waktu"] = f"{durasi_m} Menit"
            target_grp["durasi_menit"] = durasi_m
            if target_grp.get("urutan") == 1 or cfg["kelompok_pekerjaan"][0].get("id") == target_grp.get("id"):
                cfg["ia02"].update(cur_ia02)

        elif bagian == "ia03":
            cur_ia03 = target_grp["instrumen"].setdefault("ia03", {})
            if "panduan" in bdata:
                cur_ia03["panduan"] = str(bdata["panduan"] or "").strip()
            if isinstance(bdata.get("questions"), list):
                clean_q3 = []
                for idx_q, q in enumerate(bdata["questions"], start=1):
                    if not isinstance(q, dict):
                        continue
                    pert = str(q.get("pertanyaan") or "").strip()
                    if not pert:
                        continue
                    kuk_list = q.get("kuk") if isinstance(q.get("kuk"), list) else pisahkan_kuk(q.get("kuk") or q.get("elemen_kuk"))
                    dim_str = str(q.get("dimensi") or "TS").strip().upper()
                    clean_q3.append({
                        "order": idx_q,
                        "unit_kode": str(q.get("unit_kode") or "").strip(),
                        "kuk": kuk_list,
                        "elemen_kuk": "; ".join(kuk_list) if kuk_list else str(q.get("elemen_kuk") or "").strip(),
                        "dimensi": dim_str,
                        "pertanyaan": pert,
                        "kunci_jawaban": str(q.get("kunci_jawaban") or "").strip(),
                    })
                cur_ia03["questions"] = clean_q3
            if target_grp.get("urutan") == 1 or cfg["kelompok_pekerjaan"][0].get("id") == target_grp.get("id"):
                cfg["ia03"] = cur_ia03

        elif bagian in ("ia04", "ia04a"):
            cur_ia04a = target_grp["instrumen"].setdefault("ia04a", {})
            for k in [
                "judul_kegiatan", "judul_proyek", "situasi", "tugas", "tindakan",
                "data_informasi", "hasil", "hal_demonstrasi",
                "waktu_proyek", "waktu_presentasi",
            ]:
                if k in bdata:
                    cur_ia04a[k] = str(bdata[k] or "").strip()
            if target_grp.get("urutan") == 1 or cfg["kelompok_pekerjaan"][0].get("id") == target_grp.get("id"):
                cfg["ia04"].update(cur_ia04a)

        elif bagian == "ia04b":
            cur_ia04b = target_grp["instrumen"].setdefault("ia04b", {})
            if isinstance(bdata.get("questions"), list):
                clean_q4 = []
                for idx_q, q in enumerate(bdata["questions"], start=1):
                    if not isinstance(q, dict):
                        continue
                    pert = str(q.get("pertanyaan") or "").strip()
                    lingkup = str(q.get("lingkup") or "").strip()
                    if not pert and not lingkup:
                        continue
                    kuk_list = q.get("kuk") if isinstance(q.get("kuk"), list) else pisahkan_kuk(q.get("kuk") or q.get("elemen_kuk"))
                    dim_str = str(q.get("dimensi") or "(TS, TMS)").strip()
                    clean_q4.append({
                        "order": idx_q,
                        "lingkup": lingkup or "-",
                        "unit_kode": str(q.get("unit_kode") or "").strip(),
                        "kuk": kuk_list,
                        "elemen_kuk": "; ".join(kuk_list) if kuk_list else str(q.get("elemen_kuk") or "").strip(),
                        "dimensi": dim_str,
                        "pertanyaan": pert,
                    })
                cur_ia04b["questions"] = clean_q4
            if target_grp.get("urutan") == 1 or cfg["kelompok_pekerjaan"][0].get("id") == target_grp.get("id"):
                cfg["ia04"]["questions"] = cur_ia04b.get("questions", [])

    # 2. Update Personel
    if isinstance(payload.get("personel"), dict):
        for k, v in payload["personel"].items():
            cfg["personel"][k] = str(v).strip() if not isinstance(v, int) else v
        try:
            kat = int(cfg["personel"].get("kategori_asesi", 1))
            cfg["personel"]["kategori_asesi"] = kat if 1 <= kat <= 5 else 1
        except (ValueError, TypeError):
            cfg["personel"]["kategori_asesi"] = 1

    # 3. Update Keseluruhan Kelompok Pekerjaan
    if isinstance(payload.get("kelompok_pekerjaan"), list):
        clean_kp = []
        for idx, grp in enumerate(payload["kelompok_pekerjaan"], start=1):
            if not isinstance(grp, dict):
                continue
            nama_grp = str(grp.get("nama") or "").strip()
            if not nama_grp:
                continue
            units_grp = []
            for uc in (grp.get("units") or []):
                uc_str = str(uc).strip()
                if uc_str and uc_str not in units_grp:
                    units_grp.append(uc_str)
            durasi_m = int(grp.get("durasi_menit") or 0)
            if not durasi_m:
                durasi_m = ekstrak_menit_durasi(grp.get("durasi_waktu") or "120 Menit")
            grp_id = str(grp.get("id") or f"kp_{idx}")
            ins = grp.get("instrumen")
            if not isinstance(ins, dict) or not ins:
                existing_grp = next((ex for ex in cfg.get("kelompok_pekerjaan", []) if str(ex.get("id")) == grp_id), None)
                if existing_grp and isinstance(existing_grp.get("instrumen"), dict) and existing_grp["instrumen"]:
                    ins = existing_grp["instrumen"]
                else:
                    ins = default_instrumen_untuk_kelompok(grp, nama_skema)
            clean_kp.append({
                "id": grp_id,
                "nama": nama_grp,
                "urutan": int(grp.get("urutan") or idx),
                "units": units_grp,
                "durasi_menit": durasi_m,
                "instrumen": ins,
            })
        clean_kp.sort(key=lambda x: x["urutan"])
        cfg["kelompok_pekerjaan"] = clean_kp
        if clean_kp:
            k1_ins = clean_kp[0].get("instrumen") or {}
            if isinstance(k1_ins.get("ia02"), dict):
                cfg["ia02"].update(k1_ins["ia02"])
            if isinstance(k1_ins.get("ia03"), dict):
                cfg["ia03"] = k1_ins["ia03"]
            if isinstance(k1_ins.get("ia04a"), dict):
                cfg["ia04"].update(k1_ins["ia04a"])

    # 4. Fallback Update Akar (ia02, ia03, ia04, ia05, ia06, ia07, ia08)
    if isinstance(payload.get("ia02"), dict):
        for k in ["skenario", "langkah_kerja", "hasil_kerja", "perlengkapan", "peralatan", "durasi_waktu"]:
            if k in payload["ia02"]:
                cfg["ia02"][k] = str(payload["ia02"][k] or "").strip()
        dur_m = ekstrak_menit_durasi(cfg["ia02"].get("durasi_waktu") or "120")
        cfg["ia02"]["durasi_menit"] = dur_m
        if cfg["kelompok_pekerjaan"]:
            k1_ins = cfg["kelompok_pekerjaan"][0].setdefault("instrumen", {})
            k1_ia02 = k1_ins.setdefault("ia02", {})
            k1_ia02.update(cfg["ia02"])
            cfg["kelompok_pekerjaan"][0]["durasi_menit"] = dur_m

    if isinstance(payload.get("ia03"), dict):
        if "panduan" in payload["ia03"]:
            cfg["ia03"]["panduan"] = str(payload["ia03"]["panduan"] or "").strip()
        if isinstance(payload["ia03"].get("questions"), list):
            clean_q3 = []
            for idx, q in enumerate(payload["ia03"]["questions"], start=1):
                if not isinstance(q, dict):
                    continue
                pert = str(q.get("pertanyaan") or "").strip()
                if not pert:
                    continue
                kuk_list = q.get("kuk") if isinstance(q.get("kuk"), list) else pisahkan_kuk(q.get("kuk") or q.get("elemen_kuk"))
                clean_q3.append({
                    "order": idx,
                    "unit_kode": str(q.get("unit_kode") or "").strip(),
                    "kuk": kuk_list,
                    "elemen_kuk": "; ".join(kuk_list) if kuk_list else str(q.get("elemen_kuk") or "").strip(),
                    "dimensi": str(q.get("dimensi") or "TS").strip().upper(),
                    "pertanyaan": pert,
                    "kunci_jawaban": str(q.get("kunci_jawaban") or "").strip(),
                })
            cfg["ia03"]["questions"] = clean_q3
            if cfg["kelompok_pekerjaan"]:
                cfg["kelompok_pekerjaan"][0].setdefault("instrumen", {})["ia03"] = cfg["ia03"]

    if isinstance(payload.get("ia04"), dict):
        for k in [
            "judul_kegiatan", "judul_proyek", "situasi", "tugas", "tindakan",
            "data_informasi", "hasil", "hal_demonstrasi",
            "waktu_proyek", "waktu_presentasi",
        ]:
            if k in payload["ia04"]:
                cfg["ia04"][k] = str(payload["ia04"][k] or "").strip()
        if isinstance(payload["ia04"].get("questions"), list):
            clean_q4 = []
            for idx, q in enumerate(payload["ia04"]["questions"], start=1):
                if not isinstance(q, dict):
                    continue
                pert = str(q.get("pertanyaan") or "").strip()
                lingkup = str(q.get("lingkup") or "").strip()
                if not pert and not lingkup:
                    continue
                kuk_list = q.get("kuk") if isinstance(q.get("kuk"), list) else pisahkan_kuk(q.get("kuk") or q.get("elemen_kuk"))
                clean_q4.append({
                    "order": idx,
                    "lingkup": lingkup or "-",
                    "unit_kode": str(q.get("unit_kode") or "").strip(),
                    "kuk": kuk_list,
                    "elemen_kuk": "; ".join(kuk_list) if kuk_list else str(q.get("elemen_kuk") or "").strip(),
                    "dimensi": str(q.get("dimensi") or "(TS, TMS)").strip(),
                    "pertanyaan": pert,
                })
            cfg["ia04"]["questions"] = clean_q4
            if cfg["kelompok_pekerjaan"]:
                k1_ins = cfg["kelompok_pekerjaan"][0].setdefault("instrumen", {})
                k1_ins.setdefault("ia04a", {}).update(cfg["ia04"])
                k1_ins.setdefault("ia04b", {})["questions"] = clean_q4

    if isinstance(payload.get("ia05"), dict):
        if "pertanyaan" in payload["ia05"]:
            cfg["ia05"]["pertanyaan"] = str(payload["ia05"]["pertanyaan"] or "").strip()
        if "kunci" in payload["ia05"]:
            cfg["ia05"]["kunci"] = str(payload["ia05"]["kunci"] or "").strip()
        if "jumlah_soal" in payload["ia05"]:
            try:
                jml = max(1, int(payload["ia05"]["jumlah_soal"]))
            except (ValueError, TypeError):
                jml = 10
            cfg["ia05"]["jumlah_soal"] = jml

    if isinstance(payload.get("ia06"), dict):
        if "waktu" in payload["ia06"]:
            cfg["ia06"]["waktu"] = str(payload["ia06"]["waktu"] or "").strip()
        if isinstance(payload["ia06"].get("questions"), list):
            clean_q6 = []
            for idx, q in enumerate(payload["ia06"]["questions"], start=1):
                if not isinstance(q, dict):
                    continue
                pert = str(q.get("pertanyaan") or "").strip()
                kunci = str(q.get("kunci_jawaban") or "").strip()
                clean_q6.append({
                    "order": idx,
                    "pertanyaan": pert,
                    "kunci_jawaban": kunci,
                })
            if clean_q6:
                cfg["ia06"]["questions"] = clean_q6

    if isinstance(payload.get("ia07"), dict):
        if isinstance(payload["ia07"].get("questions"), list):
            clean_q7 = []
            for idx, q in enumerate(payload["ia07"]["questions"], start=1):
                if not isinstance(q, dict):
                    continue
                pert = str(q.get("pertanyaan") or "").strip()
                kunci = str(q.get("kunci_jawaban") or "").strip()
                clean_q7.append({
                    "order": idx,
                    "pertanyaan": pert,
                    "kunci_jawaban": kunci,
                })
            if clean_q7:
                cfg["ia07"]["questions"] = clean_q7

    if isinstance(payload.get("ia08"), dict):
        if isinstance(payload["ia08"].get("bukti_portofolio"), list):
            cfg["ia08"]["bukti_portofolio"] = [
                str(b or "").strip() for b in payload["ia08"]["bukti_portofolio"]
            ]
        if isinstance(payload["ia08"].get("klarifikasi"), list):
            clean_kl = []
            for item in payload["ia08"]["klarifikasi"]:
                if isinstance(item, dict):
                    clean_kl.append({
                        "no_unit": str(item.get("no_unit") or "").strip(),
                        "no_elemen": str(item.get("no_elemen") or "").strip(),
                        "materi": str(item.get("materi") or "").strip(),
                    })
            if clean_kl:
                cfg["ia08"]["klarifikasi"] = clean_kl
        if "bukti_tambahan" in payload["ia08"]:
            cfg["ia08"]["bukti_tambahan"] = str(payload["ia08"]["bukti_tambahan"] or "").strip()

    cfg["schema_muk_version"] = 2
    cfg["diperbarui_pada"] = datetime.now().isoformat(timespec="seconds")
    jalur = _jalur_muk(schema_id)
    jalur.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    # Simpan juga ke multi-versi SQLite
    try:
        db.simpan_versi_muk(
            schema_id=schema_id,
            kode_versi=kode_versi,
            nama_versi=nama_versi,
            data_payload=cfg,
            deskripsi=deskripsi,
            dibuat_oleh=dibuat_oleh,
            is_aktif=is_aktif,
        )
    except Exception:
        pass

    return cfg


def susun_kelompok_pekerjaan_cetak(
    daftar_unit: List[Dict[str, Any]],
    kelompok_pekerjaan_raw: List[Dict[str, Any]],
    nama_skema: str = "Skema Sertifikasi",
) -> Dict[str, Any]:
    """
    Menyusun struktur kelompok pekerjaan siap cetak (untuk FR.MAPA.01, MAPA.02, FR.IA.01, IA.02, IA.03, IA.04A, dan Peta Kelompok)
    beserta informasi validasi cakupan terhadap seluruh unit skema dan instrumen lengkap per kelompok.
    """
    peta_unit = {u["kode_unit"]: u for u in daftar_unit if u.get("kode_unit")}
    total_master = len(peta_unit)

    assigned_codes: List[str] = []
    groups_cetak: List[Dict[str, Any]] = []
    global_no = 1

    for idx, grp in enumerate(kelompok_pekerjaan_raw or [], start=1):
        group_units = []
        lokal_no = 1
        for u_code in (grp.get("units") or []):
            if u_code in peta_unit:
                u_detail = peta_unit[u_code]
                assigned_codes.append(u_code)
                group_units.append({
                    "no": global_no,
                    "no_lokal": lokal_no,
                    "kode_unit": u_code,
                    "judul_unit": u_detail["judul_unit"],
                    "standar_acuan": u_detail.get("standar_acuan", ""),
                    "elemen": u_detail.get("elemen", []),
                    "batasan_variabel": u_detail.get("batasan_variabel", {}),
                    "panduan_penilaian": u_detail.get("panduan_penilaian", {}),
                })
                global_no += 1
                lokal_no += 1
        if group_units:
            nama_grp = grp.get("nama") or f"Kelompok Pekerjaan {idx}"
            judul_units_str = ", ".join(u["judul_unit"] for u in group_units)
            durasi_m = int(grp.get("durasi_menit") or 0)
            if not durasi_m:
                durasi_m = ekstrak_menit_durasi(grp.get("durasi_waktu") or "120 Menit")
            ins = grp.get("instrumen")
            if not isinstance(ins, dict) or not ins:
                ins = default_instrumen_untuk_kelompok(grp, nama_skema)
            groups_cetak.append({
                "id": grp.get("id") or f"kp_{idx}",
                "no_kelompok": len(groups_cetak) + 1,
                "nama": nama_grp,
                "urutan": grp.get("urutan") or idx,
                "rowspan": len(group_units),
                "units": group_units,
                "ringkasan_unit": judul_units_str,
                "durasi_menit": durasi_m,
                "durasi_label": f"{durasi_m} Menit",
                "instrumen": ins,
            })

    unique_assigned = list(dict.fromkeys(assigned_codes))
    unassigned_units = [
        {"kode_unit": k, "judul_unit": u["judul_unit"]}
        for k, u in peta_unit.items()
        if k not in unique_assigned
    ]

    # Jika sama sekali belum ada kelompok yang valid, buat 1 kelompok default berisi seluruh unit
    if not groups_cetak and daftar_unit:
        default_units = []
        for idx_u, u in enumerate(daftar_unit, start=1):
            default_units.append({
                "no": idx_u,
                "no_lokal": idx_u,
                "kode_unit": u["kode_unit"],
                "judul_unit": u["judul_unit"],
                "standar_acuan": u.get("standar_acuan", ""),
                "elemen": u.get("elemen", []),
                "batasan_variabel": u.get("batasan_variabel", {}),
                "panduan_penilaian": u.get("panduan_penilaian", {}),
            })
        judul_units_str = ", ".join(u["judul_unit"] for u in default_units)
        def_grp_dict = {
            "id": "kp_1",
            "nama": "Kelompok Pekerjaan 1 (belum dikelompokkan — draf)",
            "urutan": 1,
            "units": [u["kode_unit"] for u in default_units],
            "durasi_menit": 120,
        }
        def_ins = default_instrumen_untuk_kelompok(def_grp_dict, nama_skema)
        groups_cetak.append({
            "id": "kp_1",
            "no_kelompok": 1,
            "nama": "Kelompok Pekerjaan 1 (belum dikelompokkan — draf)",
            "urutan": 1,
            "rowspan": len(default_units),
            "units": default_units,
            "ringkasan_unit": judul_units_str,
            "durasi_menit": 120,
            "durasi_label": "120 Menit",
            "instrumen": def_ins,
        })
        unique_assigned = [u["kode_unit"] for u in daftar_unit]
        unassigned_units = []

    total_grouped_unique = len(unique_assigned)
    total_unassigned = len(unassigned_units)
    coverage_percent = round((total_grouped_unique / total_master) * 100, 1) if total_master > 0 else 100.0
    is_complete = (total_master > 0 and total_unassigned == 0)

    total_durasi_menit = sum(int(g.get("durasi_menit", 120)) for g in groups_cetak)
    avg_durasi = round(total_durasi_menit / len(groups_cetak)) if groups_cetak else 0
    ringkasan_durasi = f"{total_durasi_menit} Menit ({len(groups_cetak)} kelompok @ {avg_durasi} Menit)"

    return {
        "groups": groups_cetak,
        "total_master": total_master,
        "total_grouped_unique": total_grouped_unique,
        "total_unassigned": total_unassigned,
        "coverage_percent": coverage_percent,
        "is_complete": is_complete,
        "unassigned_units": unassigned_units,
        "total_durasi_menit": total_durasi_menit,
        "ringkasan_durasi": ringkasan_durasi,
    }


def tentukan_dokumen_aktif(doc_mode: str, metode_mapa: str = "observasi") -> List[str]:
    """Menentukan daftar kode dokumen yang dirender berdasarkan doc_mode."""
    mode = (doc_mode or "all").strip().lower()
    if mode == "all":
        return [
            "daftar_periksa",
            "apl01", "apl02", "mapa01",
            "skema_dok", "skkni_dok",
            "peta_kelompok", "mapa02",
            "ak07", "ak04", "ak01",
            "ia01", "ia02", "ia03", "ia04a", "ia04b",
            "ia05a", "ia05b", "ia05c",
            "ia06a", "ia06b", "ia06c",
            "ia07", "ia08",
            "ak02", "ak03", "ak05", "ak06", "va",
        ]
    elif mode == "paket_observasi":
        return [
            "apl01", "apl02", "mapa01", "peta_kelompok", "mapa02",
            "ak07", "ak04", "ak01",
            "ia01", "ia02", "ia03",
            "ia05a", "ia05b", "ia05c",
            "ak02", "ak03", "ak05", "ak06", "va",
        ]
    elif mode == "paket_dit":
        return [
            "apl01", "apl02", "mapa01", "peta_kelompok", "mapa02",
            "ak07", "ak04", "ak01",
            "ia04a", "ia04b",
            "ia05a", "ia05b", "ia05c",
            "ak02", "ak03", "ak05", "ak06", "va",
        ]
    elif mode == "paket_portofolio":
        return [
            "apl01", "apl02", "mapa01", "peta_kelompok", "mapa02",
            "ak07", "ak04", "ak01",
            "ia08",
            "ia05a", "ia05b", "ia05c",
            "ak02", "ak03", "ak05", "ak06", "va",
        ]
    valid_single = {d["kode"] for d in DAFTAR_DOKUMEN_BUKU_KERJA}
    if mode in valid_single:
        return [mode]
    return ["apl01", "apl02"]


def ekstrak_konten_skema_docx(schema_id: str) -> Dict[str, Any]:
    """Membaca isi teks dan tabel dari berkas .docx skema sertifikasi yang diunggah."""
    docx_path = ROOT / "data" / "schema_library" / "docx" / f"{schema_id}.docx"
    doc_meta = schema_library.ambil_skema(schema_id) or {}
    nama_asli = doc_meta.get("nama_asli") or f"{schema_id}.docx"

    hasil: Dict[str, Any] = {
        "ada_berkas": False,
        "nama_asli": nama_asli,
        "judul_dokumen": doc_meta.get("judul_dokumen") or doc_meta.get("nama_skema") or "Skema Sertifikasi",
        "sections": [],
        "tabel_unit": [],
        "penetapan": {},
    }

    if not docx_path.exists():
        return hasil

    try:
        import docx
        doc = docx.Document(docx_path)
        hasil["ada_berkas"] = True

        current_sec: Dict[str, Any] = {"judul": "1. Informasi Umum Skema", "isi": []}
        for para in doc.paragraphs:
            t = para.text.strip()
            if not t:
                continue
            if len(t) < 70 and (t.endswith('.') or t.isupper() or any(t.startswith(f"{i}.") for i in range(1, 25))):
                if current_sec["isi"]:
                    hasil["sections"].append(current_sec)
                current_sec = {"judul": t.rstrip('.'), "isi": []}
            else:
                current_sec["isi"].append(t)
        if current_sec["isi"]:
            hasil["sections"].append(current_sec)

        if len(doc.tables) > 1:
            t1 = doc.tables[1]
            for row in t1.rows[1:]:
                cells = [c.text.strip().replace('\n', ' ') for c in row.cells]
                if len(cells) >= 3 and cells[1]:
                    hasil["tabel_unit"].append({
                        "no": cells[0],
                        "kode_unit": cells[1],
                        "judul_unit": cells[2]
                    })

        if len(doc.tables) > 0:
            t0 = doc.tables[0]
            if len(t0.rows) > 0 and len(t0.rows[0].cells) >= 2:
                hasil["penetapan"]["ditetapkan_header"] = t0.rows[0].cells[0].text.strip()
                hasil["penetapan"]["disahkan_header"] = t0.rows[0].cells[1].text.strip()
            if len(t0.rows) > 2 and len(t0.rows[2].cells) >= 2:
                hasil["penetapan"]["penandatangan_ditetapkan"] = t0.rows[2].cells[0].text.strip()
                hasil["penetapan"]["penandatangan_disahkan"] = t0.rows[2].cells[1].text.strip()
            elif len(t0.rows) > 1 and len(t0.rows[1].cells) >= 2 and t0.rows[1].cells[0].text.strip():
                hasil["penetapan"]["penandatangan_ditetapkan"] = t0.rows[1].cells[0].text.strip()
                hasil["penetapan"]["penandatangan_disahkan"] = t0.rows[1].cells[1].text.strip()
            for r in t0.rows:
                for c in r.cells:
                    t = c.text.strip()
                    if "Ditetapkan" in t and "ditetapkan" not in hasil["penetapan"]:
                        hasil["penetapan"]["ditetapkan"] = t
                    elif "Disahkan" in t and "disahkan" not in hasil["penetapan"]:
                        hasil["penetapan"]["disahkan"] = t
    except Exception as e:
        hasil["galat"] = str(e)

    return hasil


def susun_data_buku_kerja(
    schema_id: str,
    no_skema: str = "",
    nama_asesor: str = "",
    no_met: str = "",
    metode_mapa: str = "",
    kategori_asesi: int = 0,
    nama_tuk: str = "",
    jenis_tuk: str = "",
    nama_penyusun: str = "",
    met_penyusun: str = "",
    nama_validator: str = "",
    met_validator: str = "",
    nama_manajer: str = "",
    tanggal_pelaksanaan: str = "",
    kode_versi: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Menyusun data lengkap skema, unit kompetensi (Elemen + KUK), kelompok pekerjaan,
    dan seluruh instrumen MUK untuk dicetak pada Buku Kerja Asesor V.2023 (18 Dokumen).
    """
    doc = schema_library.ambil_skema(schema_id)
    if not doc:
        return None

    nama_skema = (
        doc.get("judul_skema")
        or doc.get("nama_skema")
        or doc.get("nama_berkas")
        or doc.get("nama_asli")
        or "Skema Sertifikasi"
    ).strip()
    jenis_skema = (doc.get("jenis_skema") or "Okupasi").strip()

    units_raw = doc.get("unit_kompetensi") or doc.get("units") or []
    daftar_unit: List[Dict[str, Any]] = []
    gerbang = status_units.evaluasi_gerbang_skema(schema_id)
    peta_status = gerbang.get("peta_unit") or {}

    for idx, u in enumerate(units_raw):
        kode = u.get("kode_unit") or ""
        judul = u.get("judul_unit") or u.get("judul_skema") or ""

        data_ekstraksi = ambil_json_unit(kode)
        if data_ekstraksi:
            judul = data_ekstraksi.get("judul_unit") or judul
            deskripsi = data_ekstraksi.get("deskripsi_unit") or ""
            raw_elemen = data_ekstraksi.get("elemen_kompetensi") or []
            raw_bv = data_ekstraksi.get("batasan_variabel") or {}
            raw_pp = data_ekstraksi.get("panduan_penilaian") or {}
        else:
            deskripsi = ""
            raw_elemen = []
            raw_bv = {}
            raw_pp = {}

        elemen_list = []
        for e_idx, el in enumerate(raw_elemen):
            e_no = el.get("nomor_elemen") or (e_idx + 1)
            e_nama = (el.get("nama_elemen") or "").strip()

            kuks = []
            kuk_items = []
            for k_idx, k in enumerate(el.get("kuk") or [], start=1):
                k_no = str(k.get("nomor_kuk") or f"{e_no}.{k_idx}").strip()
                k_ur = str(k.get("uraian_kuk") or "").strip()
                teks_kuk = f"{k_no} {k_ur}".strip()
                if teks_kuk:
                    kuks.append(teks_kuk)
                    kuk_items.append({
                        "nomor": k_no,
                        "uraian": k_ur,
                        "teks": teks_kuk,
                    })

            elemen_list.append({
                "nomor": e_no,
                "nama": e_nama,
                "pertanyaan_apl02": format_elemen_apl02(e_nama),
                "kuk": kuks,
                "kuk_items": kuk_items,
            })

        standar_acuan = deteksi_standar_skkni(kode)
        info_st = peta_status.get(kode) or {}
        ringkasan_bv_pp = ringkas_bv_pp_unit(raw_bv, raw_pp)

        daftar_unit.append({
            "nomor_urut": idx + 1,
            "kode_unit": kode,
            "judul_unit": judul,
            "deskripsi_unit": deskripsi,
            "standar_acuan": standar_acuan,
            "elemen": elemen_list,
            "batasan_variabel": raw_bv,
            "panduan_penilaian": raw_pp,
            "ringkasan_bv_pp": ringkasan_bv_pp,
            "status": info_st.get("status", "gagal"),
            "label_status": info_st.get("label", "Gagal"),
            "alasan_status": info_st.get("alasan", ""),
        })

    referensi_skkni = agregasi_referensi_bv_pp_skema(daftar_unit)

    # Muat konfigurasi MUK tersimpan untuk skema ini
    nomor_skema_awal = doc.get("kode_skema") or doc.get("nomor_skema") or doc.get("nomor_dokumen") or ""
    muk_cfg = muat_konfigurasi_muk(schema_id, nama_skema, daftar_unit, nomor_skema=nomor_skema_awal, kode_versi=kode_versi)
    personel = muk_cfg.get("personel") or {}

    nomor_skema_final = no_skema.strip() or personel.get("nomor_skema") or nomor_skema_awal
    nama_asesor_final = nama_asesor.strip() or personel.get("nama_asesor") or ""
    no_met_final = no_met.strip() or personel.get("no_met") or ""
    metode_mapa_final = (metode_mapa.strip() or personel.get("metode_mapa") or "observasi").lower()
    if metode_mapa_final not in ("observasi", "dit", "portofolio"):
        metode_mapa_final = "observasi"

    kat_asesi_final = kategori_asesi if 1 <= kategori_asesi <= 5 else int(personel.get("kategori_asesi") or 1)
    nama_tuk_final = nama_tuk.strip() or personel.get("nama_tuk") or "TUK Sewaktu"
    jenis_tuk_final = (jenis_tuk.strip() or personel.get("jenis_tuk") or "sewaktu").lower()

    penyusun_nama = nama_penyusun.strip() or personel.get("nama_penyusun") or ""
    penyusun_met = met_penyusun.strip() or personel.get("met_penyusun") or ""
    validator_nama = nama_validator.strip() or personel.get("nama_validator") or ""
    validator_met = met_validator.strip() or personel.get("met_validator") or ""
    manajer_nama = nama_manajer.strip() or personel.get("nama_manajer_sertifikasi") or ""
    tgl_pelaksanaan = tanggal_pelaksanaan.strip() or personel.get("tanggal_pelaksanaan") or ""
    tgl_penyusunan = personel.get("tanggal_penyusunan") or tgl_pelaksanaan or ""

    # Susun Kelompok Pekerjaan
    info_kelompok = susun_kelompok_pekerjaan_cetak(
        daftar_unit,
        muk_cfg.get("kelompok_pekerjaan") or [],
        nama_skema=nama_skema,
    )

    # Siapkan instrumen per kelompok pekerjaan
    for grp in info_kelompok.get("groups") or []:
        grp_ins = grp.setdefault("instrumen", {})
        # IA.02 Kelompok
        g_ia02 = grp_ins.setdefault("ia02", {})
        g_ia02_ll = [
            re.sub(r"^[0-9]+[\.\)]\s*", "", ln.strip())
            for ln in re.split(r"\r\n|\r|\n", g_ia02.get("langkah_kerja") or "")
            if ln.strip()
        ]
        g_ia02_pl = [
            re.sub(r"^[-*•]\s*", "", ln.strip())
            for ln in re.split(r"\r\n|\r|\n", g_ia02.get("perlengkapan") or "")
            if ln.strip()
        ]
        g_ia02_alt = [
            re.sub(r"^[-*•]\s*", "", ln.strip())
            for ln in re.split(r"\r\n|\r|\n", g_ia02.get("peralatan") or "")
            if ln.strip()
        ]
        g_ia02["langkah_lines"] = g_ia02_ll
        g_ia02["perlengkapan_lines"] = g_ia02_pl
        g_ia02["peralatan_lines"] = g_ia02_alt
        g_ia02["durasi_waktu"] = g_ia02.get("durasi_waktu") or f"{grp.get('durasi_menit', 120)} Menit"

        # IA.03 Kelompok
        g_ia03 = grp_ins.setdefault("ia03", {})
        g_ia03_q = []
        for idx_q, q in enumerate(g_ia03.get("questions") or [], start=1):
            dim_code = (q.get("dimensi") or "TS").upper()
            kuk_val = q.get("kuk") if isinstance(q.get("kuk"), list) else pisahkan_kuk(q.get("kuk") or q.get("elemen_kuk"))
            g_ia03_q.append({
                "no": idx_q,
                "order": idx_q,
                "unit_kode": q.get("unit_kode") or "",
                "kuk": kuk_val,
                "elemen_kuk": "; ".join(kuk_val) if kuk_val else str(q.get("elemen_kuk") or "-"),
                "dimensi": dim_code,
                "dimensi_label": DIMENSI_KOMPETENSI_LABELS.get(dim_code, dim_code),
                "pertanyaan": q.get("pertanyaan") or "",
                "kunci_jawaban": q.get("kunci_jawaban") or "",
            })
        g_ia03["questions"] = g_ia03_q

        # IA.04A & IA.04B Kelompok
        g_ia04a = grp_ins.setdefault("ia04a", {})
        g_ia04b = grp_ins.setdefault("ia04b", {})
        g_ia04b_q = []
        for idx_q, q in enumerate(g_ia04b.get("questions") or g_ia04a.get("questions") or [], start=1):
            dim_code = (q.get("dimensi") or "(TS, TMS)").strip()
            kuk_val = q.get("kuk") if isinstance(q.get("kuk"), list) else pisahkan_kuk(q.get("kuk") or q.get("elemen_kuk"))
            g_ia04b_q.append({
                "no": idx_q,
                "order": idx_q,
                "lingkup": q.get("lingkup") or "-",
                "unit_kode": q.get("unit_kode") or "",
                "kuk": kuk_val,
                "elemen_kuk": "; ".join(kuk_val) if kuk_val else str(q.get("elemen_kuk") or "-"),
                "dimensi": dim_code,
                "pertanyaan": q.get("pertanyaan") or "",
            })
        g_ia04b["questions"] = g_ia04b_q
        g_ia04a["questions"] = g_ia04b_q

        # IA.01 Kelompok
        g_ia01 = grp_ins.setdefault("ia01", {})
        if "fokus_observasi" not in g_ia01:
            g_ia01["fokus_observasi"] = f"Observasi aktivitas praktik {grp.get('nama')}"

    # Siapkan detail IA.02
    ia02_cfg = muk_cfg.get("ia02") or {}
    langkah_lines = [
        re.sub(r"^[0-9]+[\.\)]\s*", "", ln.strip())
        for ln in re.split(r"\r\n|\r|\n", ia02_cfg.get("langkah_kerja") or "")
        if ln.strip()
    ]
    perlengkapan_lines = [
        re.sub(r"^[-*•]\s*", "", ln.strip())
        for ln in re.split(r"\r\n|\r|\n", ia02_cfg.get("perlengkapan") or "")
        if ln.strip()
    ]
    peralatan_lines = [
        re.sub(r"^[-*•]\s*", "", ln.strip())
        for ln in re.split(r"\r\n|\r|\n", ia02_cfg.get("peralatan") or "")
        if ln.strip()
    ]
    ia02_prepared = {
        **ia02_cfg,
        "langkah_lines": langkah_lines,
        "perlengkapan_lines": perlengkapan_lines,
        "peralatan_lines": peralatan_lines,
    }

    # Siapkan detail IA.03
    ia03_cfg = muk_cfg.get("ia03") or {}
    ia03_questions = []
    for idx_q, q in enumerate(ia03_cfg.get("questions") or [], start=1):
        dim_code = (q.get("dimensi") or "TS").upper()
        ia03_questions.append({
            "no": idx_q,
            "dimensi": dim_code,
            "dimensi_label": DIMENSI_KOMPETENSI_LABELS.get(dim_code, dim_code),
            "pertanyaan": q.get("pertanyaan") or "",
            "kunci_jawaban": q.get("kunci_jawaban") or "",
        })
    ia03_prepared = {
        "panduan": ia03_cfg.get("panduan") or "",
        "questions": ia03_questions,
    }

    # Siapkan detail IA.04A & IA.04B
    ia04_cfg = muk_cfg.get("ia04") or {}
    ia04_prepared = {
        **ia04_cfg,
        "questions": ia04_cfg.get("questions") or [],
    }

    # Siapkan detail IA.05A, 05B, 05C
    ia05_cfg = muk_cfg.get("ia05") or {}
    jumlah_soal = max(1, int(ia05_cfg.get("jumlah_soal") or 10))
    parsed_kunci = parse_kunci_jawaban_ia05(ia05_cfg.get("kunci") or "", jumlah_soal)
    total_soal_kunci = max(jumlah_soal, len(parsed_kunci))
    half_soal = (total_soal_kunci + 1) // 2
    baris_dua_kolom = []
    for r in range(1, half_soal + 1):
        right_no = r + half_soal
        baris_dua_kolom.append({
            "left_no": r,
            "left_ans": parsed_kunci.get(r, ""),
            "right_no": right_no if right_no <= total_soal_kunci else None,
            "right_ans": parsed_kunci.get(right_no, "") if right_no <= total_soal_kunci else "",
        })
    ia05_prepared = {
        "jumlah_soal": total_soal_kunci,
        "pertanyaan": ia05_cfg.get("pertanyaan") or "",
        "kunci_raw": ia05_cfg.get("kunci") or "",
        "parsed_kunci": parsed_kunci,
        "baris_dua_kolom": baris_dua_kolom,
    }

    # Siapkan detail IA.06A, 06B, 06C (Esai)
    ia06_cfg = muk_cfg.get("ia06") or {}
    ia06_questions = ia06_cfg.get("questions") or [
        {"order": i, "pertanyaan": "", "kunci_jawaban": ""} for i in range(1, 6)
    ]
    ia06_prepared = {
        "waktu": ia06_cfg.get("waktu") or "60 Menit",
        "questions": ia06_questions,
    }

    # Siapkan detail IA.07 (DPL - Pertanyaan Lisan)
    ia07_cfg = muk_cfg.get("ia07") or {}
    ia07_questions = ia07_cfg.get("questions") or [
        {"order": i, "pertanyaan": "", "kunci_jawaban": ""} for i in range(1, 4)
    ]
    ia07_prepared = {
        "questions": ia07_questions,
    }

    # Siapkan detail IA.08 (CVP - Ceklis Verifikasi Portofolio)
    ia08_cfg = muk_cfg.get("ia08") or {}
    bukti_porto = ia08_cfg.get("bukti_portofolio") or ["", "", "", ""]
    klarifikasi_list = ia08_cfg.get("klarifikasi") or [
        {"no_unit": "", "no_elemen": "", "materi": ""} for _ in range(6)
    ]
    ia08_prepared = {
        "bukti_portofolio": bukti_porto,
        "klarifikasi": klarifikasi_list,
        "bukti_tambahan": ia08_cfg.get("bukti_tambahan") or "",
    }

    # Bukti persyaratan default untuk APL 01
    persyaratan_dasar = [
        "Fotokopi Ijazah Pendidikan Terakhir",
        "Surat Keterangan Pengalaman Kerja / Magang yang Relevan",
        "Portofolio / Bukti Hasil Pekerjaan yang Relevan",
    ]
    persyaratan_admin = [
        "Fotokopi Kartu Tanda Penduduk (KTP / Identitas Diri)",
        "Pas Foto Formal 3x4 (Background Merah/Biru)",
    ]

    # Pertanyaan standar umpan balik FR.AK.03
    pertanyaan_ak03 = [
        "Saya mendapatkan penjelasan yang cukup memadai mengenai proses asesmen/uji kompetensi",
        "Saya diberikan kesempatan untuk mempelajari standar kompetensi yang akan diujikan dan menilai diri sendiri terhadap pencapaiannya",
        "Asesor memberikan kesempatan untuk mendiskusikan/menegosiasikan metoda, instrumen dan sumber asesmen serta jadwal asesmen",
        "Asesor berusaha menggali seluruh bukti pendukung yang sesuai dengan latar belakang pelatihan dan pengalaman yang saya miliki",
        "Saya sepenuhnya diberikan kesempatan untuk mendemonstrasikan kompetensi yang saya miliki selama asesmen",
        "Saya mendapatkan penjelasan yang memadai mengenai keputusan asesmen",
        "Asesor memberikan umpan balik yang mendukung setelah asesmen serta tindak lanjutnya",
        "Asesor bersama saya mempelajari semua dokumen asesmen serta menandatanganinya",
        "Saya mendapatkan jaminan kerahasiaan hasil asesmen serta penjelasan penanganan dokumen asesmen",
        "Asesor menggunakan keterampilan komunikasi yang efektif selama asesmen",
    ]

    return {
        "schema_id": schema_id,
        "nama_skema": nama_skema,
        "jenis_skema": jenis_skema,
        "nomor_skema": nomor_skema_final,
        "nama_asesor": nama_asesor_final,
        "no_met": no_met_final,
        "nama_tuk": nama_tuk_final,
        "jenis_tuk": jenis_tuk_final,
        "metode_mapa": metode_mapa_final,
        "kategori_asesi": kat_asesi_final,
        "nama_penyusun": penyusun_nama,
        "met_penyusun": penyusun_met,
        "nama_validator": validator_nama,
        "met_validator": validator_met,
        "nama_manajer": manajer_nama,
        "tanggal_pelaksanaan": tgl_pelaksanaan,
        "tanggal_penyusunan": tgl_penyusunan,
        "jumlah_unit": len(daftar_unit),
        "daftar_unit": daftar_unit,
        "referensi_skkni": referensi_skkni,
        "kelompok_pekerjaan": info_kelompok,
        "ia02": ia02_prepared,
        "ia03": ia03_prepared,
        "ia04": ia04_prepared,
        "ia05": ia05_prepared,
        "ia06": ia06_prepared,
        "ia07": ia07_prepared,
        "ia08": ia08_prepared,
        "muk_raw": muk_cfg,
        "persyaratan_dasar": persyaratan_dasar,
        "persyaratan_admin": persyaratan_admin,
        "pertanyaan_ak03": pertanyaan_ak03,
        "daftar_dokumen": DAFTAR_DOKUMEN_BUKU_KERJA,
        "skema_asli": ekstrak_konten_skema_docx(schema_id),
        "dimensi_labels": DIMENSI_KOMPETENSI_LABELS,
        "gerbang": gerbang,
        "daftar_versi_muk": db.daftar_versi_muk_skema(schema_id),
        "versi_aktif": kode_versi or next((v["kode_versi"] for v in db.daftar_versi_muk_skema(schema_id) if v.get("is_aktif")), "v1"),
    }


def ambil_daftar_periksa_rcc(schema_id: str, dok: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Menyusun daftar 27 butir pemeriksaan dokumen mengacu pada 0_Daftar Periksa Kelengkapan Dokumen Upgrading-RCC."""
    nama_skema = ""
    nomor_skema = ""
    if dok:
        nama_skema = dok.get("nama_skema") or dok.get("judul_skema") or ""
        nomor_skema = dok.get("nomor_skema") or ""

    return [
        {
            "id": "daftar_periksa",
            "nomor": "0",
            "kode": "0_Daftar_Periksa",
            "kategori": "Ceklis Master",
            "judul": "Daftar Periksa Kelengkapan Dokumen Pelatihan (Upgrading-RCC)",
            "subjudul": "Master Checklist 25 Dokumen Asesmen BNSP V.2023",
            "tipe": "Ceklis Master",
            "doc_code": "daftar_periksa",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "apl01",
            "nomor": "1",
            "kode": "FR.APL.01",
            "kategori": "A. Pelaksanaan Asesmen",
            "judul": "Permohonan Sertifikasi Kompetensi",
            "subjudul": "Data Pribadi, Pendidikan & Pengalaman Asesi",
            "tipe": "Administrasi",
            "doc_code": "apl01",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "apl02",
            "nomor": "2",
            "kode": "FR.APL.02",
            "kategori": "A. Pelaksanaan Asesmen",
            "judul": "Asesmen Mandiri",
            "subjudul": "Daftar Seluruh Unit, Elemen & KUK dengan Penilaian Mandiri",
            "tipe": "Asesmen Diri",
            "doc_code": "apl02",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "portofolio",
            "nomor": "3",
            "kode": "Portofolio",
            "kategori": "A. Pelaksanaan Asesmen",
            "judul": "Portofolio Asesi (Lampiran Bukti Pendukung)",
            "subjudul": "Berkas Fisik / Dokumen Portofolio Asesi",
            "tipe": "Lampiran Berkas",
            "doc_code": None,
            "orientasi": "portrait",
            "ada_preview": False,
            "keterangan_lampiran": "Bukti dokumen pendukung (ijazah, transkrip nilai, sertifikat pelatihan, surat keterangan kerja) yang dilampirkan oleh asesi pada saat pendaftaran asesmen untuk diverifikasi oleh asesor.",
        },
        {
            "id": "mapa01",
            "nomor": "4",
            "kode": "FR.MAPA.01",
            "kategori": "A. Pelaksanaan Asesmen",
            "judul": "Merencanakan Aktivitas dan Proses Asesmen",
            "subjudul": "Pendekatan Asesmen, Rencana Aktivitas & Konfirmasi",
            "tipe": "Rencana Asesmen",
            "doc_code": "mapa01",
            "orientasi": "landscape",
            "ada_preview": True,
        },
        {
            "id": "skema_dok",
            "nomor": "5a",
            "kode": "Skema",
            "kategori": "A. Pelaksanaan Asesmen",
            "judul": "Dokumen Skema Sertifikasi",
            "subjudul": f"Kemasan Skema: {nama_skema}",
            "tipe": "Dokumen Acuan",
            "doc_code": "skema_dok",
            "orientasi": "portrait",
            "ada_preview": True,
            "keterangan_lampiran": f"Dokumen acuan resmi skema sertifikasi: {nama_skema} ({nomor_skema or 'Nomor sesuai penetapan'}). Memuat aturan kemasan unit kompetensi dan persyaratan dasar pemohon.",
        },
        {
            "id": "skkni_dok",
            "nomor": "5b",
            "kode": "SKKNI",
            "kategori": "A. Pelaksanaan Asesmen",
            "judul": "Standar Kompetensi Kerja (SKKNI)",
            "subjudul": "Standar Acuan Unit Kompetensi Kemnaker",
            "tipe": "Standar Acuan",
            "doc_code": "skkni_dok",
            "orientasi": "portrait",
            "ada_preview": True,
            "keterangan_lampiran": "Standar Kompetensi Kerja Nasional Indonesia (SKKNI) rujukan resmi Kementerian Ketenagakerjaan RI yang mendasari setiap unit kompetensi dalam skema ini.",
        },
        {
            "id": "peta_kelompok",
            "nomor": "5c",
            "kode": "PETA-KP",
            "kategori": "A. Pelaksanaan Asesmen",
            "judul": "Peta Kelompok Pekerjaan",
            "subjudul": "Pengelompokan Unit Kompetensi Asesmen",
            "tipe": "Struktur KP",
            "doc_code": "peta_kelompok",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "mapa02",
            "nomor": "6",
            "kode": "FR.MAPA.02",
            "kategori": "A. Pelaksanaan Asesmen",
            "judul": "Peta Instrumen Asesmen",
            "subjudul": "Matriks Bukti Langsung, Tidak Langsung & Tambahan",
            "tipe": "Matriks Bukti",
            "doc_code": "mapa02",
            "orientasi": "landscape",
            "ada_preview": True,
        },
        {
            "id": "ak07",
            "nomor": "7",
            "kode": "FR.AK.07",
            "kategori": "A. Pelaksanaan Asesmen",
            "judul": "Ceklis Penyesuaian yang Wajar dan Beralasan",
            "subjudul": "Akomodasi Penyesuaian Asesmen",
            "tipe": "Penyesuaian",
            "doc_code": "ak07",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ak04",
            "nomor": "8",
            "kode": "FR.AK.04",
            "kategori": "A. Pelaksanaan Asesmen",
            "judul": "Banding Asesmen",
            "subjudul": "Prosedur Pengajuan Banding Asesi",
            "tipe": "Hak Banding",
            "doc_code": "ak04",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ak01",
            "nomor": "9",
            "kode": "FR.AK.01",
            "kategori": "A. Pelaksanaan Asesmen",
            "judul": "Persetujuan Asesmen dan Kerahasiaan",
            "subjudul": "Kesepakatan Waktu & Kerahasiaan Asesmen",
            "tipe": "Persetujuan",
            "doc_code": "ak01",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ia01",
            "nomor": "10",
            "kode": "FR.IA.01",
            "kategori": "Instrumen Asesmen (IA)",
            "judul": "CL: Ceklis Observasi Aktivitas di Tempat Kerja",
            "subjudul": "Daftar Ceklis Observasi Unjuk Kerja",
            "tipe": "Observasi Langsung",
            "doc_code": "ia01",
            "orientasi": "landscape",
            "ada_preview": True,
        },
        {
            "id": "ia02",
            "nomor": "11",
            "kode": "FR.IA.02",
            "kategori": "Instrumen Asesmen (IA)",
            "judul": "TPD: Tugas Praktik Demonstrasi",
            "subjudul": "Skenario Instruksi Kerja & Praktik Demonstrasi",
            "tipe": "Demonstrasi Praktik",
            "doc_code": "ia02",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ia03",
            "nomor": "12",
            "kode": "FR.IA.03",
            "kategori": "Instrumen Asesmen (IA)",
            "judul": "PMO: Pertanyaan Mendukung Observasi",
            "subjudul": "Tanya Jawab Lisan Klarifikasi Observasi",
            "tipe": "Tanya Jawab Lisan",
            "doc_code": "ia03",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ia04a",
            "nomor": "13a",
            "kode": "FR.IA.04A",
            "kategori": "Instrumen Asesmen (IA)",
            "judul": "DIT: Penjelasan Proyek Singkat / Kasus",
            "subjudul": "Instruksi Proyek Singkat / Studi Kasus Terstruktur",
            "tipe": "Instruksi Proyek",
            "doc_code": "ia04a",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ia04b",
            "nomor": "13b",
            "kode": "FR.IA.04B",
            "kategori": "Instrumen Asesmen (IA)",
            "judul": "DIT: Lembar Penilaian Proyek Singkat",
            "subjudul": "Rubrik Penilaian Hasil Tugas Proyek",
            "tipe": "Rubrik Penilaian",
            "doc_code": "ia04b",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ia05a",
            "nomor": "14a",
            "kode": "FR.IA.05A",
            "kategori": "Instrumen Asesmen (IA)",
            "judul": "DPT: Pertanyaan Pilihan Ganda",
            "subjudul": "Naskah Soal Pilihan Ganda (PG)",
            "tipe": "Lembar Soal PG",
            "doc_code": "ia05a",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ia05b",
            "nomor": "14b",
            "kode": "FR.IA.05B",
            "kategori": "Instrumen Asesmen (IA)",
            "judul": "Kunci Jawaban Pilihan Ganda",
            "subjudul": "Kunci Jawaban PG Khusus Asesor",
            "tipe": "Kunci Jawaban Asesor",
            "doc_code": "ia05b",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ia05c",
            "nomor": "14c",
            "kode": "FR.IA.05C",
            "kategori": "Instrumen Asesmen (IA)",
            "judul": "Lembar Jawaban Asesi Pilihan Ganda",
            "subjudul": "Lembar Kosong Jawaban Asesi PG",
            "tipe": "Lembar Asesi",
            "doc_code": "ia05c",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ia06a",
            "nomor": "15a",
            "kode": "FR.IA.06A",
            "kategori": "Instrumen Asesmen (IA)",
            "judul": "DPT: Pertanyaan Tertulis Esai",
            "subjudul": "Naskah Soal Pertanyaan Tertulis Esai",
            "tipe": "Lembar Soal Esai",
            "doc_code": "ia06a",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ia06b",
            "nomor": "15b",
            "kode": "FR.IA.06B",
            "kategori": "Instrumen Asesmen (IA)",
            "judul": "Kunci Jawaban Pertanyaan Tertulis Esai",
            "subjudul": "Pedoman Jawaban Esai Khusus Asesor",
            "tipe": "Kunci Jawaban Asesor",
            "doc_code": "ia06b",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ia06c",
            "nomor": "15c",
            "kode": "FR.IA.06C",
            "kategori": "Instrumen Asesmen (IA)",
            "judul": "Lembar Jawaban Asesi Pertanyaan Esai",
            "subjudul": "Lembar Format Jawaban Asesi Esai",
            "tipe": "Lembar Asesi",
            "doc_code": "ia06c",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ia07",
            "nomor": "16",
            "kode": "FR.IA.07",
            "kategori": "Instrumen Asesmen (IA)",
            "judul": "DPL: Daftar Pertanyaan Lisan",
            "subjudul": "Tanya Jawab Lisan & Tanggapan Asesi",
            "tipe": "Tanya Jawab Lisan",
            "doc_code": "ia07",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ia08",
            "nomor": "17",
            "kode": "FR.IA.08",
            "kategori": "Instrumen Asesmen (IA)",
            "judul": "CVP: Ceklis Verifikasi Portofolio",
            "subjudul": "Verifikasi Aturan Bukti VATM",
            "tipe": "Verifikasi Portofolio",
            "doc_code": "ia08",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ak02",
            "nomor": "21",
            "kode": "FR.AK.02",
            "kategori": "B. Keputusan & Umpan Balik",
            "judul": "Rekaman Asesmen Kompetensi",
            "subjudul": "Rekapitulasi Nilai & Penetapan Keputusan K/BK",
            "tipe": "Rekap & Keputusan",
            "doc_code": "ak02",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ak03",
            "nomor": "22",
            "kode": "FR.AK.03",
            "kategori": "B. Keputusan & Umpan Balik",
            "judul": "Umpan Balik dan Catatan Asesmen",
            "subjudul": "Catatan Evaluasi & Umpan Balik Asesi",
            "tipe": "Umpan Balik",
            "doc_code": "ak03",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ak05",
            "nomor": "23",
            "kode": "FR.AK.05",
            "kategori": "C. Laporan Asesmen",
            "judul": "Laporan Asesmen",
            "subjudul": "Laporan Resmi Pelaksanaan Asesmen",
            "tipe": "Laporan Resmi",
            "doc_code": "ak05",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "ak06",
            "nomor": "24",
            "kode": "FR.AK.06",
            "kategori": "D. Meninjau & Validasi",
            "judul": "Meninjau Proses Asesmen",
            "subjudul": "Kaji Ulang (Review) Proses Asesmen",
            "tipe": "Kaji Ulang",
            "doc_code": "ak06",
            "orientasi": "portrait",
            "ada_preview": True,
        },
        {
            "id": "va",
            "nomor": "25",
            "kode": "FR.VA",
            "kategori": "D. Meninjau & Validasi",
            "judul": "Memberikan Kontribusi dalam Validasi Asesmen",
            "subjudul": "Pemeriksaan Perangkat oleh Validator Eksternal",
            "tipe": "Validasi Asesmen",
            "doc_code": "va",
            "orientasi": "portrait",
            "ada_preview": True,
        },
    ]

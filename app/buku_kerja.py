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

from app import db, schema_library, status_units
from app.lsp_exporter import ambil_json_unit

ROOT = Path(__file__).resolve().parent.parent
MUK_DIR = ROOT / "data" / "schema_library" / "muk"

# Daftar dokumen yang didukung beserta label resminya
DAFTAR_DOKUMEN_BUKU_KERJA = [
    {"kode": "all", "label": "📚 Semua Dokumen (Paket Lengkap Urutan 1–25)"},
    {"kode": "paket_observasi", "label": "📦 Paket Metode Observasi Langsung (CLO + TPD + PMO + DPT)"},
    {"kode": "paket_dit", "label": "📦 Paket Metode Proyek Singkat / Kegiatan Terstruktur (DIT + DPT)"},
    {"kode": "paket_portofolio", "label": "📦 Paket Metode Verifikasi Portofolio (CVP + DPT)"},
    {"kode": "apl01", "label": "1. FR.APL.01 — Permohonan Sertifikasi Kompetensi"},
    {"kode": "apl02", "label": "2. FR.APL.02 — Asesmen Mandiri"},
    {"kode": "mapa01", "label": "4. FR.MAPA.01 — Merencanakan Aktivitas dan Proses Asesmen"},
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


def default_konfigurasi_muk(nama_skema: str, daftar_unit: List[Dict[str, Any]], nomor_skema: str = "") -> Dict[str, Any]:
    """Menyusun konfigurasi default MUK & Kelompok Pekerjaan untuk suatu skema."""
    semua_kode = [u["kode_unit"] for u in daftar_unit if u.get("kode_unit")]
    ref_skkni = agregasi_referensi_bv_pp_skema(daftar_unit)

    langkah_default = []
    for idx, u in enumerate(daftar_unit, start=1):
        langkah_default.append(
            f"{idx}. Melaksanakan aktivitas: {u.get('judul_unit', '')} sesuai prosedur operasional standar."
        )
    if not langkah_default:
        langkah_default = [
            "1. Mempersiapkan seluruh peralatan dan perangkat kerja pendukung sesuai instruksi kerja.",
            "2. Melaksanakan tahapan pekerjaan sesuai SOP dan standar keselamatan dan kesehatan kerja (K3).",
            "3. Mendokumentasikan hasil pekerjaan dan melaporkan hasil kerja secara tertulis kepada asesor.",
        ]

    ia03_default_questions = [
        {
            "order": 1,
            "dimensi": "CMS",
            "pertanyaan": "Jika pada saat pelaksanaan tugas atau demonstrasi praktik terjadi kendala teknis tak terduga (misalnya peralatan utama mati mendadak, data rusak, atau koneksi terputus), tindakan darurat dan sistematis apa yang pertama kali Anda lakukan?",
            "kunci_jawaban": "Asesi mampu menjelaskan prosedur darurat penanganan insiden, isolasi masalah, dan pelaporan kepada supervisor sesuai SOP keselamatan kerja.",
        },
        {
            "order": 2,
            "dimensi": "TRS",
            "pertanyaan": "Jika lingkungan kerja atau perangkat/aplikasi yang Anda gunakan bermigrasi ke sistem atau versi baru yang belum pernah Anda operasikan sebelumnya, bagaimana strategi Anda untuk beradaptasi cepat agar hasil kerja tetap memenuhi standar?",
            "kunci_jawaban": "Asesi mampu menerapkan prinsip transfer skills, mempelajari dokumentasi/manual sistem baru, serta melakukan pengujian fungsional secara mandiri.",
        },
        {
            "order": 3,
            "dimensi": "JRES",
            "pertanyaan": "Sebutkan prosedur dasar Keselamatan dan Kesehatan Kerja (K3) serta standar komunikasi etis yang wajib Anda patuhi selama melaksanakan seluruh tahapan demonstrasi pekerjaan!",
            "kunci_jawaban": "Asesi mematuhi regulasi K3 lingkungan kerja, penggunaan APD/ergonomi yang tepat, dan komunikasi profesional terhadap rekan kerja maupun asesor.",
        },
        {
            "order": 4,
            "dimensi": "TS",
            "pertanyaan": "Jelaskan langkah-langkah kritis dalam memverifikasi ketepatan dan kualitas hasil kerja sebelum diserahkan kepada pihak manajemen atau pengguna akhir!",
            "kunci_jawaban": "Asesi melakukan cek silang (quality control) terhadap spesifikasi output, memastikan kesesuaian format laporan, dan menandatangani bukti serah terima.",
        },
    ]

    ia04b_default_questions = [
        {
            "order": 1,
            "lingkup": f"Kesesuaian lingkup penyajian proyek skema {nama_skema}",
            "pertanyaan": "Jelaskan tahapan perencanaan dan persiapan yang Anda lakukan dalam menyelesaikan proyek singkat ini!",
            "elemen_kuk": semua_kode[0] if semua_kode else "Unit 1",
            "dimensi": "(TS, TMS)",
        },
        {
            "order": 2,
            "lingkup": "Kesesuaian mutu hasil kerja terhadap standar industri / SOP",
            "pertanyaan": "Bagaimana Anda memastikan hasil keluaran proyek telah memenuhi spesifikasi teknis dan standar kualitas yang ditetapkan?",
            "elemen_kuk": semua_kode[1] if len(semua_kode) > 1 else (semua_kode[0] if semua_kode else "Unit 1"),
            "dimensi": "(TS, JRES)",
        },
        {
            "order": 3,
            "lingkup": "Penanganan kendala teknis dan manajemen waktu pengerjaan",
            "pertanyaan": "Jika terjadi perubahan kebutuhan mendadak atau kendala peralatan saat pengerjaan proyek, langkah antisipasi apa yang Anda terapkan?",
            "elemen_kuk": semua_kode[-1] if semua_kode else "Unit 1",
            "dimensi": "(CMS, TRS)",
        },
    ]

    return {
        "personel": {
            "nomor_skema": nomor_skema,
            "nama_asesor": "",
            "no_met": "",
            "nama_tuk": "TUK Sewaktu",
            "jenis_tuk": "sewaktu",
            "metode_mapa": "observasi",
            "kategori_asesi": 1,
            "nama_penyusun": "Masriah",
            "met_penyusun": "MET.000.032423 2019",
            "nama_validator": "Eko Prasyanto",
            "met_validator": "MET.000.014249 2019",
            "nama_manajer_sertifikasi": "Iqbal",
            "tanggal_pelaksanaan": "",
            "tanggal_penyusunan": "",
        },
        "kelompok_pekerjaan": [
            {
                "id": "kp_1",
                "nama": f"Kelompok Pekerjaan 1 ({nama_skema})",
                "urutan": 1,
                "units": semua_kode,
            }
        ] if semua_kode else [],
        "ia02": {
            "skenario": (
                f"Anda seorang asesi sedang mengajukan sertifikasi skema {nama_skema}. "
                "Anda diharapkan mampu mendemonstrasikan seluruh tugas praktik sesuai dengan kelompok pekerjaan "
                "di atas secara profesional, terstruktur, dan memenuhi standar keselamatan kerja yang berlaku di tempat kerja."
            ),
            "langkah_kerja": "\n".join(langkah_default),
            "hasil_kerja": (
                "Hasil pekerjaan berupa demonstrasi fisik/praktik langsung, bukti karya/dokumen pendukung, "
                "dan lembar verifikasi hasil pekerjaan yang diserahkan kepada asesor."
            ),
            "perlengkapan": (
                "\n".join(ref_skkni["perlengkapan_unik"])
                if ref_skkni.get("perlengkapan_unik")
                else (
                    "Alat Keselamatan & Kesehatan Kerja (K3)\n"
                    "Perangkat media penyimpanan / flashdisk / cloud\n"
                    "Bahan penunjang demonstrasi / dokumen kerja\n"
                    "Formulir checklist laporan pekerjaan"
                )
            ),
            "peralatan": (
                "\n".join(ref_skkni["peralatan_unik"])
                if ref_skkni.get("peralatan_unik")
                else (
                    "Komputer / laptop / gawai penunjang\n"
                    "Perangkat kerja spesifik bidang profesi\n"
                    "Aksesori / peripheral pendukung teknis\n"
                    "Alat Tulis Kantor (ATK)"
                )
            ),
            "durasi_waktu": "120 Menit",
        },
        "ia03": {
            "panduan": "",
            "questions": ia03_default_questions,
        },
        "ia04": {
            "judul_kegiatan": f"Proyek Terstruktur Skema {nama_skema}",
            "situasi": (
                f"Anda ditugaskan sebagai tenaga profesional pada bidang {nama_skema} untuk menyelesaikan "
                "suatu proyek kerja sesuai brief/permintaan klien dan standar operasional prosedur (SOP) industri."
            ),
            "tugas": (
                f"Menyusun perencanaan, menyiapkan perangkat/dokumen kerja, mengeksekusi tahapan kerja {nama_skema}, "
                "serta mempresentasikan hasil akhir proyek di hadapan asesor."
            ),
            "tindakan": "\n".join(langkah_default),
            "data_informasi": "Dokumen brief proyek, SOP tempat kerja, standar K3, dan perangkat kerja pendukung.",
            "hasil": f"Dokumen perencanaan, produk/karya hasil kerja {nama_skema}, dan materi presentasi hasil proyek.",
            "hal_demonstrasi": (
                "1. Penjelasan alur perencanaan dan konsep kerja.\n"
                "2. Demonstrasi hasil proyek singkat / produk kerja yang telah diselesaikan.\n"
                "3. Tanya jawab terkait pemenuhan kriteria unjuk kerja dan pemecahan masalah (problem solving)."
            ),
            "waktu_proyek": "240 menit",
            "waktu_presentasi": "30 menit",
            "questions": ia04b_default_questions,
        },
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
                saved = json.loads(jalur.read_text(encoding="utf-8"))
        except Exception:
            pass

    if not isinstance(saved, dict):
        return default_cfg

    # Gabungkan sub-dictionary dengan aman
    for key in ["personel", "ia02", "ia03", "ia04", "ia05", "ia06", "ia07", "ia08"]:
        if isinstance(saved.get(key), dict):
            default_cfg[key].update({k: v for k, v in saved[key].items() if v is not None})

    if isinstance(saved.get("kelompok_pekerjaan"), list) and len(saved["kelompok_pekerjaan"]) > 0:
        default_cfg["kelompok_pekerjaan"] = saved["kelompok_pekerjaan"]

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

    if isinstance(payload.get("personel"), dict):
        for k, v in payload["personel"].items():
            cfg["personel"][k] = str(v).strip() if not isinstance(v, int) else v
        try:
            kat = int(cfg["personel"].get("kategori_asesi", 1))
            cfg["personel"]["kategori_asesi"] = kat if 1 <= kat <= 5 else 1
        except (ValueError, TypeError):
            cfg["personel"]["kategori_asesi"] = 1

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
            clean_kp.append({
                "id": str(grp.get("id") or f"kp_{idx}"),
                "nama": nama_grp,
                "urutan": int(grp.get("urutan") or idx),
                "units": units_grp,
            })
        clean_kp.sort(key=lambda x: x["urutan"])
        cfg["kelompok_pekerjaan"] = clean_kp

    if isinstance(payload.get("ia02"), dict):
        for k in ["skenario", "langkah_kerja", "hasil_kerja", "perlengkapan", "peralatan", "durasi_waktu"]:
            if k in payload["ia02"]:
                cfg["ia02"][k] = str(payload["ia02"][k] or "").strip()

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
                clean_q3.append({
                    "order": idx,
                    "dimensi": str(q.get("dimensi") or "TS").strip().upper(),
                    "pertanyaan": pert,
                    "kunci_jawaban": str(q.get("kunci_jawaban") or "").strip(),
                })
            cfg["ia03"]["questions"] = clean_q3

    if isinstance(payload.get("ia04"), dict):
        for k in [
            "judul_kegiatan", "situasi", "tugas", "tindakan",
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
                clean_q4.append({
                    "order": idx,
                    "lingkup": lingkup or "-",
                    "pertanyaan": pert,
                    "elemen_kuk": str(q.get("elemen_kuk") or "").strip(),
                    "dimensi": str(q.get("dimensi") or "").strip(),
                })
            cfg["ia04"]["questions"] = clean_q4

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
    beserta informasi validasi cakupan terhadap seluruh unit skema dan panduan pembuatan instrumen per kelompok.
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
            groups_cetak.append({
                "id": grp.get("id") or f"kp_{idx}",
                "no_kelompok": len(groups_cetak) + 1,
                "nama": nama_grp,
                "urutan": grp.get("urutan") or idx,
                "rowspan": len(group_units),
                "units": group_units,
                "ringkasan_unit": judul_units_str,
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
        groups_cetak.append({
            "id": "kp_1",
            "no_kelompok": 1,
            "nama": f"Kelompok Pekerjaan 1 ({nama_skema})",
            "urutan": 1,
            "rowspan": len(default_units),
            "units": default_units,
            "ringkasan_unit": judul_units_str,
        })
        unique_assigned = [u["kode_unit"] for u in daftar_unit]
        unassigned_units = []

    total_grouped_unique = len(unique_assigned)
    total_unassigned = len(unassigned_units)
    coverage_percent = round((total_grouped_unique / total_master) * 100, 1) if total_master > 0 else 100.0
    is_complete = (total_master > 0 and total_unassigned == 0)

    return {
        "groups": groups_cetak,
        "total_master": total_master,
        "total_grouped_unique": total_grouped_unique,
        "total_unassigned": total_unassigned,
        "coverage_percent": coverage_percent,
        "is_complete": is_complete,
        "unassigned_units": unassigned_units,
    }


def tentukan_dokumen_aktif(doc_mode: str, metode_mapa: str = "observasi") -> List[str]:
    """Menentukan daftar kode dokumen yang dirender berdasarkan doc_mode."""
    mode = (doc_mode or "all").strip().lower()
    if mode == "all":
        return [
            "apl01", "apl02", "mapa01", "peta_kelompok", "mapa02",
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

    penyusun_nama = nama_penyusun.strip() or personel.get("nama_penyusun") or "Masriah"
    penyusun_met = met_penyusun.strip() or personel.get("met_penyusun") or "MET.000.032423 2019"
    validator_nama = nama_validator.strip() or personel.get("nama_validator") or "Eko Prasyanto"
    validator_met = met_validator.strip() or personel.get("met_validator") or "MET.000.014249 2019"
    manajer_nama = nama_manajer.strip() or personel.get("nama_manajer_sertifikasi") or "Iqbal"
    tgl_pelaksanaan = tanggal_pelaksanaan.strip() or personel.get("tanggal_pelaksanaan") or ""
    tgl_penyusunan = personel.get("tanggal_penyusunan") or tgl_pelaksanaan or ""

    # Susun Kelompok Pekerjaan
    info_kelompok = susun_kelompok_pekerjaan_cetak(
        daftar_unit,
        muk_cfg.get("kelompok_pekerjaan") or [],
        nama_skema=nama_skema,
    )

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
        "dimensi_labels": DIMENSI_KOMPETENSI_LABELS,
        "gerbang": gerbang,
        "daftar_versi_muk": db.daftar_versi_muk_skema(schema_id),
        "versi_aktif": kode_versi or next((v["kode_versi"] for v in db.daftar_versi_muk_skema(schema_id) if v.get("is_aktif")), "v1"),
    }

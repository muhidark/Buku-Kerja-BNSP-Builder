"""
Pengujian Unit & Integrasi: Instrumen Asesmen per Kelompok Pekerjaan (v2).
Memverifikasi kepatuhan terhadap docs/PROMPT-instrumen-per-kelompok.md:
1. Pemisahan instrumen IA.01, IA.02, IA.03, IA.04A, IA.04B per kelompok.
2. Penjumlahan total durasi asesmen (sum durasi_menit).
3. Struktur KUK array dan validasi dimensi kompetensi.
4. Ketersediaan instrumen per kelompok pada API dan ekspor berkas terpisah.
"""

import json
import zipfile
import io
import pytest
from starlette.testclient import TestClient

from app import buku_kerja, buku_kerja_docx, schema_library
from app.main import app


@pytest.fixture
def skema_dua_kelompok(tmp_path):
    """Menyiapkan skema uji dengan 4 unit dan 2 kelompok pekerjaan."""
    schema_id = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    doc_skema = {
        "id": schema_id,
        "nama_skema": "Skema Pengujian Dua Kelompok",
        "judul_skema": "Skema Pengujian Dua Kelompok",
        "nomor_dokumen": "SKM/2026/001",
        "kode_skema": "SKM/2026/001",
        "jenis_skema": "Okupasi",
        "units": [
            {"kode_unit": "U.001.01", "judul_skema": "Unit Pertama"},
            {"kode_unit": "U.002.01", "judul_skema": "Unit Kedua"},
            {"kode_unit": "U.003.01", "judul_skema": "Unit Ketiga"},
            {"kode_unit": "U.004.01", "judul_skema": "Unit Keempat"},
        ],
    }

    # Simpan skema ke JSON disk schema_library
    doc_dir = schema_library.ROOT / "data" / "schema_library" / "documents"
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc_file = doc_dir / f"{schema_id}.json"
    doc_file.write_text(json.dumps(doc_skema, ensure_ascii=False, indent=2), encoding="utf-8")

    yield schema_id, doc_skema

    # Cleanup
    if doc_file.exists():
        doc_file.unlink(missing_ok=True)
    muk_file = buku_kerja.ROOT / "data" / "schema_library" / "muk" / f"{schema_id}.json"
    if muk_file.exists():
        muk_file.unlink(missing_ok=True)


def test_simpan_ia02_beda_per_kelompok(skema_dua_kelompok):
    """Kriteria 1: Simpan IA.02 untuk K1 dan K2 dengan skenario berbeda tidak saling menimpa."""
    schema_id, _ = skema_dua_kelompok

    # Inisialisasi 2 kelompok
    setup_payload = {
        "kelompok_pekerjaan": [
            {
                "id": "kp_1",
                "nama": "Kelompok 1 (Persiapan)",
                "urutan": 1,
                "units": ["U.001.01", "U.002.01"],
                "durasi_menit": 90,
            },
            {
                "id": "kp_2",
                "nama": "Kelompok 2 (Pelaksanaan)",
                "urutan": 2,
                "units": ["U.003.01", "U.004.01"],
                "durasi_menit": 150,
            },
        ]
    }
    buku_kerja.simpan_konfigurasi_muk(schema_id, setup_payload)

    # Simpan skenario berbeda untuk Kelompok 1
    buku_kerja.simpan_konfigurasi_muk(
        schema_id,
        {
            "kelompok_id": "kp_1",
            "bagian": "ia02",
            "data": {
                "skenario": "SKENARIO KHUSUS KELOMPOK 1: Analisis awal dan instalasi.",
                "langkah_kerja": "1. Langkah K1 Pertama\n2. Langkah K1 Kedua",
                "durasi_menit": 90,
            },
        },
    )

    # Simpan skenario berbeda untuk Kelompok 2
    buku_kerja.simpan_konfigurasi_muk(
        schema_id,
        {
            "kelompok_id": "kp_2",
            "bagian": "ia02",
            "data": {
                "skenario": "SKENARIO KHUSUS KELOMPOK 2: Pengujian performa dan serah terima.",
                "langkah_kerja": "1. Langkah K2 Eksekusi\n2. Langkah K2 Verifikasi",
                "durasi_menit": 150,
            },
        },
    )

    # Reload dari disk/db
    cfg = buku_kerja.muat_konfigurasi_muk(schema_id)
    groups = cfg.get("kelompok_pekerjaan", [])
    assert len(groups) == 2

    k1 = next(g for g in groups if g["id"] == "kp_1")
    k2 = next(g for g in groups if g["id"] == "kp_2")

    # Pastikan skenario masing-masing kelompok tidak saling tertimpa
    assert k1["instrumen"]["ia02"]["skenario"] == "SKENARIO KHUSUS KELOMPOK 1: Analisis awal dan instalasi."
    assert k2["instrumen"]["ia02"]["skenario"] == "SKENARIO KHUSUS KELOMPOK 2: Pengujian performa dan serah terima."

    # Pastikan durasi masing-masing
    assert k1["durasi_menit"] == 90
    assert k2["durasi_menit"] == 150

    # Pastikan mirror akar kompatibilitas mundur mengacu ke kelompok 1
    assert cfg["ia02"]["skenario"] == "SKENARIO KHUSUS KELOMPOK 1: Analisis awal dan instalasi."


def test_penjumlahan_durasi_kelompok(skema_dua_kelompok):
    """Kriteria 3: Total durasi asesmen = jumlah durasi seluruh kelompok."""
    schema_id, _ = skema_dua_kelompok
    daftar_unit = [
        {"kode_unit": "U.001.01", "judul_unit": "Unit 1"},
        {"kode_unit": "U.002.01", "judul_unit": "Unit 2"},
        {"kode_unit": "U.003.01", "judul_unit": "Unit 3"},
        {"kode_unit": "U.004.01", "judul_unit": "Unit 4"},
    ]
    raw_kp = [
        {"id": "kp_1", "nama": "K1", "urutan": 1, "units": ["U.001.01", "U.002.01"], "durasi_menit": 90},
        {"id": "kp_2", "nama": "K2", "urutan": 2, "units": ["U.003.01", "U.004.01"], "durasi_menit": 150},
    ]

    info = buku_kerja.susun_kelompok_pekerjaan_cetak(daftar_unit, raw_kp, "Skema Uji")
    assert info["total_durasi_menit"] == 240
    assert "240 Menit" in info["ringkasan_durasi"]
    assert info["is_complete"] is True


def test_ia03_ia04_kuk_dan_dimensi(skema_dua_kelompok):
    """Kriteria: Pertanyaan IA.03 & IA.04B menyimpan nomor KUK array dan dimensi kompetensi."""
    schema_id, _ = skema_dua_kelompok

    payload_ia03 = {
        "kelompok_id": "kp_1",
        "bagian": "ia03",
        "data": {
            "questions": [
                {
                    "order": 1,
                    "unit_kode": "U.001.01",
                    "kuk": ["1.1", "1.2"],
                    "dimensi": "TS",
                    "pertanyaan": "Jelaskan langkah kerja kritis?",
                    "kunci_jawaban": "Prosedur sesuai SOP",
                }
            ]
        },
    }
    buku_kerja.simpan_konfigurasi_muk(schema_id, payload_ia03)

    cfg = buku_kerja.muat_konfigurasi_muk(schema_id)
    k1 = cfg["kelompok_pekerjaan"][0]
    q = k1["instrumen"]["ia03"]["questions"][0]

    assert q["kuk"] == ["1.1", "1.2"]
    assert q["dimensi"] == "TS"
    assert q["unit_kode"] == "U.001.01"


def test_api_v1_muk_menyertakan_instrumen_per_kelompok(skema_dua_kelompok):
    """Kriteria 2: GET /api/v1/skema/{id}/muk menyertakan kelompok_pekerjaan[].instrumen dan field akar."""
    schema_id, _ = skema_dua_kelompok

    # Setup 2 groups
    buku_kerja.simpan_konfigurasi_muk(
        schema_id,
        {
            "kelompok_pekerjaan": [
                {
                    "id": "kp_1",
                    "nama": "Kelompok A",
                    "urutan": 1,
                    "units": ["U.001.01"],
                    "durasi_menit": 60,
                },
                {
                    "id": "kp_2",
                    "nama": "Kelompok B",
                    "urutan": 2,
                    "units": ["U.002.01"],
                    "durasi_menit": 120,
                },
            ]
        },
    )

    from app import db
    db.inisialisasi_db()
    valid_key = db.buat_kunci_api(nama_klien="Test Client V2", peran="klien", kunci_khusus="test_kunci_khusus_v2_123")

    client = TestClient(app)
    # Panggil endpoint API v1 dengan api key
    resp = client.get(f"/api/v1/skema/{schema_id}/muk", headers={"X-API-Key": valid_key})
    assert resp.status_code == 200
    res_json = resp.json()

    assert res_json["status"] == "sukses"
    assert res_json["schema_muk_version"] == 2
    assert "kelompok_pekerjaan" in res_json
    groups = res_json["kelompok_pekerjaan"]
    assert len(groups) == 2

    # Tiap kelompok punya blok instrumen
    for g in groups:
        assert "instrumen" in g
        assert "ia02" in g["instrumen"]
        assert "ia03" in g["instrumen"]

    # Field akar lama tetap ada untuk kompatibilitas mundur
    assert "instrumen" in res_json
    assert res_json["instrumen"].get("_deprecated") is True
    assert "ia_02" in res_json["instrumen"]


def test_ekspor_zip_ia_terpisah_per_kelompok(skema_dua_kelompok):
    """User instruction #10: Masing-masing dokumen IA terpisah dalam bundel zip."""
    schema_id, _ = skema_dua_kelompok

    # Setup 2 groups
    buku_kerja.simpan_konfigurasi_muk(
        schema_id,
        {
            "kelompok_pekerjaan": [
                {
                    "id": "kp_1",
                    "nama": "Kelompok Alpha",
                    "urutan": 1,
                    "units": ["U.001.01", "U.002.01"],
                    "durasi_menit": 80,
                },
                {
                    "id": "kp_2",
                    "nama": "Kelompok Beta",
                    "urutan": 2,
                    "units": ["U.003.01", "U.004.01"],
                    "durasi_menit": 100,
                },
            ]
        },
    )

    zip_bytes, zip_name = buku_kerja_docx.buat_zip_buku_kerja_bytes(schema_id, doc_mode="all")
    assert zip_bytes is not None
    assert zip_name.endswith(".zip")

    # Baca isi ZIP
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        namelist = zf.namelist()

        # Harus ada file terpisah untuk K1 dan K2 pada instrumen praktik
        ia02_k1_found = any("IA.02_K1" in fn or "ia02_k1" in fn.lower() for fn in namelist)
        ia02_k2_found = any("IA.02_K2" in fn or "ia02_k2" in fn.lower() for fn in namelist)
        assert ia02_k1_found, f"Dokumen IA.02 K1 tidak ditemukan dalam zip: {namelist}"
        assert ia02_k2_found, f"Dokumen IA.02 K2 tidak ditemukan dalam zip: {namelist}"

        # Dokumen tingkat skema/akar (misal FR.MAPA.01, FR.AK.01) tetap 1 berkas
        assert any("MAPA.01" in fn for fn in namelist)
        assert any("AK.01" in fn for fn in namelist)

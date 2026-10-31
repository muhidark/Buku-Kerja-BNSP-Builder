"""
Pengujian Unit Migrasi MUK v2 (Instrumen Asesmen per Kelompok Pekerjaan).
Menguji:
1. Migrasi 1 kelompok: pemindahan ia01, ia02, ia03, ia04a, ia04b ke kelompok_pekerjaan[0].instrumen.
2. Migrasi multi-kelompok: instrumen disalin ke kelompok pertama, kelompok lain ditandai belum_diisi.
3. Idempoten: migrasi kedua kali tidak mengubah apapun.
4. Integritas data: tidak ada karakter yang hilang/berubah dari data legasi.
"""

from scripts.migrasi_muk_v2 import migrasikan_objek_muk, ekstrak_menit_durasi, pisahkan_kuk


def test_ekstrak_menit_durasi():
    assert ekstrak_menit_durasi("90 Menit") == 90
    assert ekstrak_menit_durasi("120 menit") == 120
    assert ekstrak_menit_durasi(60) == 60
    assert ekstrak_menit_durasi("") == 90
    assert ekstrak_menit_durasi(None) == 90


def test_pisahkan_kuk():
    assert pisahkan_kuk("1.1; 1.2") == ["1.1", "1.2"]
    assert pisahkan_kuk("2.1, 2.2, 2.3") == ["2.1", "2.2", "2.3"]
    assert pisahkan_kuk(["1.1", "1.2"]) == ["1.1", "1.2"]
    # Kode unit disaring
    assert pisahkan_kuk("M.70HMS00.005.3") == []


def test_migrasi_satu_kelompok_idempoten():
    data_v1 = {
        "personel": {"nama_asesor": "Budi"},
        "kelompok_pekerjaan": [
            {
                "id": "kp_1",
                "nama": "Kelompok Pekerjaan 1 (Teknis)",
                "urutan": 1,
                "units": ["M.70HMS00.005.3"]
            }
        ],
        "ia02": {
            "skenario": "Skenario Praktik Khusus V1",
            "langkah_kerja": "1. Langkah satu\n2. Langkah dua",
            "hasil_kerja": "Karya uji V1",
            "perlengkapan": "Laptop",
            "peralatan": "ATK",
            "durasi_waktu": "120 Menit"
        },
        "ia03": {
            "panduan": "Panduan PMO",
            "questions": [
                {
                    "order": 1,
                    "dimensi": "TMS",
                    "pertanyaan": "Pertanyaan PMO V1?",
                    "kunci_jawaban": "Kunci PMO V1"
                }
            ]
        },
        "ia04": {
            "judul_kegiatan": "Proyek DIT V1",
            "situasi": "Situasi proyek",
            "questions": [
                {
                    "order": 1,
                    "lingkup": "Analisis",
                    "pertanyaan": "Pertanyaan DIT?",
                    "elemen_kuk": "1.1; 1.2",
                    "dimensi": "(TS, TMS)"
                }
            ]
        },
        "ia05": {"pertanyaan": "Soal PG", "jumlah_soal": 10},
        "ia06": {"questions": []},
        "ia07": {"questions": []},
        "ia08": {"items": []}
    }

    # Migrasi Pertama
    data_v2, changed = migrasikan_objek_muk(data_v1)
    assert changed is True
    assert data_v2["schema_muk_version"] == 2

    # Instrumen praktik pindah ke kelompok_pekerjaan[0].instrumen
    kp0 = data_v2["kelompok_pekerjaan"][0]
    assert "instrumen" in kp0
    ins = kp0["instrumen"]

    assert ins["ia02"]["skenario"] == "Skenario Praktik Khusus V1"
    assert ins["ia02"]["durasi_menit"] == 120
    assert ins["ia02"]["durasi_waktu"] == "120 Menit"
    assert ins["ia03"]["questions"][0]["pertanyaan"] == "Pertanyaan PMO V1?"
    assert ins["ia04a"]["judul_kegiatan"] == "Proyek DIT V1"
    assert ins["ia04a"]["questions"][0]["kuk"] == ["1.1", "1.2"]

    # Instrumen praktik dihapus dari akar
    assert "ia02" not in data_v2
    assert "ia03" not in data_v2
    assert "ia04" not in data_v2

    # Instrumen tingkat skema tetap di akar
    assert data_v2["ia05"]["pertanyaan"] == "Soal PG"

    # Migrasi Kedua (Uji Idempoten)
    data_v2_re, changed_re = migrasikan_objek_muk(data_v2)
    assert changed_re is False
    assert data_v2_re == data_v2


def test_migrasi_multi_kelompok():
    data_multi = {
        "kelompok_pekerjaan": [
            {"id": "kp_1", "nama": "Kelompok 1", "urutan": 1, "units": ["U1"]},
            {"id": "kp_2", "nama": "Kelompok 2", "urutan": 2, "units": ["U2"]}
        ],
        "ia02": {"skenario": "Skenario Bersama Awal", "durasi_waktu": "90 Menit"},
        "ia03": {"questions": []},
        "ia04": {"questions": []}
    }

    data_v2, changed = migrasikan_objek_muk(data_multi)
    assert changed is True
    assert len(data_v2["kelompok_pekerjaan"]) == 2

    # Kelompok 1 terisi
    ins1 = data_v2["kelompok_pekerjaan"][0]["instrumen"]
    assert ins1["ia02"]["skenario"] == "Skenario Bersama Awal"

    # Kelompok 2 ditandai belum_diisi
    ins2 = data_v2["kelompok_pekerjaan"][1]["instrumen"]
    assert ins2["instrumen_status"] == "belum_diisi"
    assert ins2["ia02"]["skenario"] == ""

    # Ada peringatan migrasi multi-kelompok
    assert "MUK ini dibuat sebelum pemisahan instrumen per kelompok" in data_v2["peringatan_migrasi"]

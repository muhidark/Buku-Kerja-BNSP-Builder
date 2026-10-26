"""
Pengujian multi-versi paket MUK dan penanda versi aktif (Langkah 5.2 / T-03).

Memastikan:
1. Simpan dua versi berurutan dengan is_aktif=True menghasilkan tepat SATU baris aktif (versi terakhir).
2. Nilai is_aktif bernilai biner (0/1), bukan string tanggal/timestamp ISO.
3. Nilai diperbarui_pada berformat timestamp ISO yang valid.
4. Versi non-aktif memiliki is_aktif = 0.
5. Idempotensi pemulihan versi aktif: jika versi baru diaktifkan, versi sebelumnya otomatis dinonaktifkan.
6. Tidak ada kondisi dua versi berstatus aktif secara bersamaan pada satu skema.
"""

import json
import re
import pytest
from app import db


@pytest.fixture
def skema_uji():
    """ID skema khusus pengujian yang dibersihkan sebelum dan sesudah uji."""
    sid = "uji_skema_versi_muk_fase5"
    with db._ambil_koneksi() as conn:
        conn.execute("DELETE FROM muk_versi WHERE schema_id = ?", (sid,))
        conn.commit()
    yield sid
    with db._ambil_koneksi() as conn:
        conn.execute("DELETE FROM muk_versi WHERE schema_id = ?", (sid,))
        conn.commit()


def test_simpan_dua_versi_hanya_satu_aktif(skema_uji):
    """Simpan dua versi secara berurutan; tepat satu versi yang aktif."""
    db.simpan_versi_muk(
        schema_id=skema_uji,
        kode_versi="v1",
        nama_versi="Versi Paket 1",
        data_payload={"catatan": "paket satu"},
        is_aktif=True,
    )
    daftar1 = db.daftar_versi_muk_skema(skema_uji)
    assert len(daftar1) == 1
    assert daftar1[0]["kode_versi"] == "v1"
    assert int(daftar1[0]["is_aktif"]) == 1

    # Simpan versi kedua dengan is_aktif=True
    db.simpan_versi_muk(
        schema_id=skema_uji,
        kode_versi="v2",
        nama_versi="Versi Paket 2",
        data_payload={"catatan": "paket dua"},
        is_aktif=True,
    )
    daftar2 = db.daftar_versi_muk_skema(skema_uji)
    assert len(daftar2) == 2

    aktif = [v for v in daftar2 if int(v["is_aktif"]) == 1]
    non_aktif = [v for v in daftar2 if int(v["is_aktif"]) == 0]

    # Harus tepat 1 versi aktif
    assert len(aktif) == 1, f"Harus tepat 1 versi aktif, ditemukan: {len(aktif)}"
    assert aktif[0]["kode_versi"] == "v2"
    assert len(non_aktif) == 1
    assert non_aktif[0]["kode_versi"] == "v1"


def test_kolom_is_aktif_berisi_biner_bukan_timestamp(skema_uji):
    """Memastikan nilai is_aktif adalah biner 0/1 dan diperbarui_pada adalah ISO timestamp."""
    db.simpan_versi_muk(
        schema_id=skema_uji,
        kode_versi="v_test_a",
        nama_versi="Versi Uji A",
        data_payload={"test": 1},
        is_aktif=False,
    )
    db.simpan_versi_muk(
        schema_id=skema_uji,
        kode_versi="v_test_b",
        nama_versi="Versi Uji B",
        data_payload={"test": 2},
        is_aktif=True,
    )

    daftar = db.daftar_versi_muk_skema(skema_uji)
    for v in daftar:
        # Nilai is_aktif harus bernilai 0 atau 1
        assert str(v["is_aktif"]) in ("0", "1"), f"is_aktif bukan biner: {v['is_aktif']!r}"
        # Nilai diperbarui_pada harus berformat ISO timestamp
        assert re.match(r"^\d{4}-\d{2}-\d{2}T", str(v["diperbarui_pada"])), (
            f"diperbarui_pada bukan timestamp ISO: {v['diperbarui_pada']!r}"
        )


def test_ambil_versi_muk_spesifik(skema_uji):
    """Pengambilan data versi spesifik mengembalikan payload yang tepat."""
    payload = {"kunci": "nilai_khusus", "angka": 42}
    db.simpan_versi_muk(
        schema_id=skema_uji,
        kode_versi="v_spesifik",
        nama_versi="Versi Spesifik",
        data_payload=payload,
        is_aktif=True,
    )

    ambil = db.ambil_versi_muk(skema_uji, "v_spesifik")
    assert ambil is not None
    assert ambil["kode_versi"] == "v_spesifik"
    assert json.loads(ambil["data_json"]) == payload
    assert int(ambil["is_aktif"]) == 1


def test_pemulihan_migrasi_baris_tertukar(skema_uji):
    """Fungsi perbaikan _perbaiki_penanda_aktif_muk membetulkan baris yang tertukar secara idempoten."""
    with db._ambil_koneksi() as conn:
        conn.execute("DELETE FROM muk_versi WHERE schema_id = ?", (skema_uji,))
        # Simulasikan bug lama: is_aktif diisi timestamp dan diperbarui_pada diisi '1'
        conn.execute(
            """INSERT INTO muk_versi
               (schema_id, kode_versi, nama_versi, deskripsi, data_json,
                dibuat_oleh, diperbarui_pada, is_aktif)
               VALUES (?, 'v_lama', 'Versi Cacat', '', '{}', NULL, '1', '2026-10-26T12:00:00+00:00')""",
            (skema_uji,),
        )
        conn.commit()

        # Jalankan fungsi pemulihan
        diperbaiki = db._perbaiki_penanda_aktif_muk(conn)
        assert diperbaiki >= 1

        # Cek baris setelah pemulihan
        cur = conn.cursor()
        cur.execute(
            "SELECT is_aktif, diperbarui_pada FROM muk_versi WHERE schema_id = ? AND kode_versi = 'v_lama'",
            (skema_uji,),
        )
        row = cur.fetchone()
        assert row is not None
        is_aktif, diperbarui = row
        assert str(is_aktif) in ("0", "1")
        assert "2026" in str(diperbarui)

        # Pemanggilan ulang (idempoten) tidak boleh merusak lagi
        diperbaiki_kedua = db._perbaiki_penanda_aktif_muk(conn)
        assert diperbaiki_kedua == 0

"""
Pengujian fitur Cetak Buku Kerja Asesor V.2023 (18 Dokumen BNSP & Manajemen MUK/Kelompok Pekerjaan).
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.main import app
from app.buku_kerja import (
    _jalur_muk,
    deteksi_standar_skkni,
    format_elemen_apl02,
    muat_konfigurasi_muk,
    parse_kunci_jawaban_ia05,
    simpan_konfigurasi_muk,
    susun_data_buku_kerja,
    susun_kelompok_pekerjaan_cetak,
    tentukan_dokumen_aktif,
)
from app import schema_library


class TestBukuKerja(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def _ambil_skema_siap(self):
        """Ambil skema yang tidak memiliki unit Gagal agar dapat dicetak."""
        for d in schema_library.daftar_skema():
            data = susun_data_buku_kerja(d["id"])
            if data and not (data.get("gerbang") or {}).get("ada_gagal"):
                return d
        docs = schema_library.daftar_skema()
        return docs[0] if docs else None

    def test_deteksi_standar_skkni(self):
        self.assertEqual(deteksi_standar_skkni("J.63OPR00.009.2"), "SKKNI 2018-056")
        self.assertEqual(deteksi_standar_skkni("M.70MKT00.012.1"), "SKKNI 2022-124")
        self.assertEqual(deteksi_standar_skkni("J.59MTM01.001.1"), "SKKNI 2018-107")
        self.assertEqual(deteksi_standar_skkni("M.73ADV00.001.1"), "SKKNI 2023-101")
        self.assertEqual(deteksi_standar_skkni("UNKNOWN.CODE", "Standar LSP"), "Standar LSP")

    def test_format_elemen_apl02(self):
        self.assertEqual(
            format_elemen_apl02("Menggunakan perangkat komputer."),
            "Dapatkah Saya menggunakan perangkat komputer?",
        )
        self.assertEqual(
            format_elemen_apl02("Dapatkah Saya menyusun laporan"),
            "Dapatkah Saya menyusun laporan?",
        )

    def test_parse_kunci_jawaban_ia05(self):
        raw = "1. B\n2: C\n3 - A\n4 D\nE"
        parsed = parse_kunci_jawaban_ia05(raw, 5)
        self.assertEqual(parsed[1], "B")
        self.assertEqual(parsed[2], "C")
        self.assertEqual(parsed[3], "A")
        self.assertEqual(parsed[4], "D")

    def test_tentukan_dokumen_aktif(self):
        all_docs = tentukan_dokumen_aktif("all")
        self.assertEqual(len(all_docs), 26)
        self.assertIn("mapa01", all_docs)
        self.assertIn("ia01", all_docs)
        self.assertIn("ia06a", all_docs)
        self.assertIn("ia06b", all_docs)
        self.assertIn("ia06c", all_docs)
        self.assertIn("ia07", all_docs)
        self.assertIn("ia08", all_docs)
        self.assertIn("ak06", all_docs)
        self.assertIn("va", all_docs)

        obs_docs = tentukan_dokumen_aktif("paket_observasi")
        self.assertIn("ia01", obs_docs)
        self.assertIn("ia02", obs_docs)
        self.assertIn("ia03", obs_docs)
        self.assertNotIn("ia04a", obs_docs)

        dit_docs = tentukan_dokumen_aktif("paket_dit")
        self.assertIn("ia04a", dit_docs)
        self.assertIn("ia04b", dit_docs)
        self.assertNotIn("ia01", dit_docs)

        porto_docs = tentukan_dokumen_aktif("paket_portofolio")
        self.assertIn("ia08", porto_docs)
        self.assertIn("va", porto_docs)

    def test_susun_kelompok_pekerjaan_cetak(self):
        units = [
            {"kode_unit": "U.01", "judul_unit": "Unit Satu", "elemen": []},
            {"kode_unit": "U.02", "judul_unit": "Unit Dua", "elemen": []},
        ]
        # Sebagian unit saja (50%)
        kp_partial = [{"id": "kp_1", "nama": "KP 1", "urutan": 1, "units": ["U.01"]}]
        res_partial = susun_kelompok_pekerjaan_cetak(units, kp_partial)
        self.assertFalse(res_partial["is_complete"])
        self.assertEqual(res_partial["coverage_percent"], 50.0)
        self.assertEqual(res_partial["total_unassigned"], 1)

        # Seluruh unit (100%)
        kp_full = [{"id": "kp_1", "nama": "KP 1", "urutan": 1, "units": ["U.01", "U.02"]}]
        res_full = susun_kelompok_pekerjaan_cetak(units, kp_full)
        self.assertTrue(res_full["is_complete"])
        self.assertEqual(res_full["coverage_percent"], 100.0)
        self.assertEqual(res_full["total_unassigned"], 0)

    def test_susun_data_buku_kerja(self):
        first_doc = self._ambil_skema_siap()
        if not first_doc:
            self.skipTest("Tidak ada skema terdaftar.")

        schema_id = first_doc["id"]
        data = susun_data_buku_kerja(
            schema_id=schema_id,
            no_skema="SKM-TEST-001",
            nama_asesor="Asesor Uji",
            no_met="MET.000.12345",
            metode_mapa="dit",
            kategori_asesi=3,
        )

        self.assertIsNotNone(data)
        self.assertEqual(data["schema_id"], schema_id)
        self.assertEqual(data["nomor_skema"], "SKM-TEST-001")
        self.assertEqual(data["nama_asesor"], "Asesor Uji")
        self.assertEqual(data["no_met"], "MET.000.12345")
        self.assertEqual(data["metode_mapa"], "dit")
        self.assertEqual(data["kategori_asesi"], 3)
        self.assertEqual(len(data["daftar_unit"]), first_doc.get("jumlah_unit", 0))
        self.assertTrue(data["kelompok_pekerjaan"]["is_complete"])
        self.assertGreaterEqual(len(data["ia03"]["questions"]), 4)
        self.assertGreaterEqual(len(data["ia04"]["questions"]), 1)

    def test_endpoint_cetak_apl_lengkap_18_dokumen(self):
        doc = self._ambil_skema_siap()
        if not doc:
            self.skipTest("Tidak ada skema terdaftar.")

        schema_id = doc["id"]
        resp = self.client.get(
            f"/skema/{schema_id}/cetak-apl",
            params={
                "doc": "all",
                "no_skema": "SKM-2024-TEST",
                "nama_asesor": "Budi Santoso",
                "no_met": "MET.000.9999",
                "metode_mapa": "observasi",
                "kategori_asesi": 1,
            },
        )
        self.assertEqual(resp.status_code, 200)
        teks = resp.text
        for judul_wajib in [
            "FR.APL.01. PERMOHONAN SERTIFIKASI KOMPETENSI",
            "FR.APL.02. ASESMEN MANDIRI",
            "FR.MAPA.01.",
            "PETA KELOMPOK PEKERJAAN SKEMA SERTIFIKASI",
            "FR.MAPA.02.",
            "FR.AK.07.",
            "FR.AK.04.",
            "FR.AK.01.",
            "FR.IA.01.",
            "FR.IA.02.",
            "FR.IA.03.",
            "FR.IA.04A.",
            "FR.IA.04B.",
            "FR.IA.05A.",
            "FR.IA.05.B.",
            "FR.IA.05.C.",
            "FR.IA.06A.DPT",
            "FR.IA.06.B.",
            "FR.IA.06.C.",
            "FR.IA.07.DPL",
            "FR.IA.08.CVP",
            "FR.AK.02.",
            "FR.AK.03.",
            "FR.AK.05.",
            "FR.AK.06.",
            "FR.VA MEMBERIKAN KONTRIBUSI DALAM VALIDASI ASESMEN",
        ]:
            self.assertIn(judul_wajib, teks)
        self.assertIn("SKM-2024-TEST", teks)
        self.assertIn("Budi Santoso", teks)
        self.assertIn("MET.000.9999", teks)

    def test_endpoint_muk_get_dan_post(self):
        doc = self._ambil_skema_siap()
        if not doc:
            self.skipTest("Tidak ada skema terdaftar.")

        schema_id = doc["id"]
        jalur = _jalur_muk(schema_id)
        cadangan = jalur.read_text(encoding="utf-8") if jalur.exists() else None

        try:
            get_resp = self.client.get(f"/skema/{schema_id}/muk")
            self.assertEqual(get_resp.status_code, 200)
            self.assertIn("Paket Materi Uji Kompetensi (MUK)", get_resp.text)
            csrf = get_resp.cookies.get("skkni_csrf", "")

            payload = {
                "personel": {
                    "nomor_skema": "SKM/UJI/2026",
                    "metode_mapa": "dit",
                    "kategori_asesi": 2,
                    "nama_asesor": "Dr. Hendra",
                    "no_met": "MET.000.8888",
                    "nama_penyusun": "Penyusun Uji",
                    "met_penyusun": "MET.PENYUSUN.01",
                    "nama_validator": "Validator Uji",
                    "met_validator": "MET.VALIDATOR.01",
                    "nama_manajer_sertifikasi": "Manajer Uji",
                },
                "ia05": {
                    "jumlah_soal": 4,
                    "pertanyaan": "1. Soal pertama?\na. Ya\nb. Tidak",
                    "kunci": "1. A\n2. B\n3. C\n4. D",
                },
            }

            post_resp = self.client.post(
                f"/skema/{schema_id}/muk",
                data={
                    "csrf_token": csrf,
                    "muk_json": json.dumps(payload),
                },
                follow_redirects=False,
            )
            self.assertEqual(post_resp.status_code, 303)

            cetak_resp = self.client.get(f"/skema/{schema_id}/cetak-apl?doc=ia05b")
            self.assertEqual(cetak_resp.status_code, 200)
            self.assertIn("Penyusun Uji", cetak_resp.text)
            self.assertIn("Validator Uji", cetak_resp.text)
            self.assertIn("SKM/UJI/2026", cetak_resp.text)
        finally:
            if cadangan is not None:
                jalur.write_text(cadangan, encoding="utf-8")
            elif jalur.exists():
                jalur.unlink()

    def test_endpoint_api_buku_kerja(self):
        doc = self._ambil_skema_siap()
        if not doc:
            self.skipTest("Tidak ada skema terdaftar.")

        schema_id = doc["id"]
        api_resp = self.client.get(
            f"/api/skema/{schema_id}/buku-kerja",
            params={
                "no_skema": "SKM-2024-TEST",
                "nama_asesor": "Budi Santoso",
                "no_met": "MET.000.9999",
            },
        )
        self.assertEqual(api_resp.status_code, 200)
        res_json = api_resp.json()
        self.assertEqual(res_json["nomor_skema"], "SKM-2024-TEST")
        self.assertEqual(res_json["nama_asesor"], "Budi Santoso")


if __name__ == "__main__":
    unittest.main()

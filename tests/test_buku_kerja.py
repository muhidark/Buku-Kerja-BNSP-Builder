"""
Pengujian fitur Cetak Buku Kerja Asesor V.2023 (FR.APL.01 & FR.APL.02).
"""

import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.buku_kerja import susun_data_buku_kerja, deteksi_standar_skkni
from app import schema_library


class TestBukuKerja(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_deteksi_standar_skkni(self):
        self.assertEqual(deteksi_standar_skkni("J.63OPR00.009.2"), "SKKNI 2018-056")
        self.assertEqual(deteksi_standar_skkni("M.70MKT00.012.1"), "SKKNI 2022-124")
        self.assertEqual(deteksi_standar_skkni("J.59MTM01.001.1"), "SKKNI 2018-107")
        self.assertEqual(deteksi_standar_skkni("M.73ADV00.001.1"), "SKKNI 2023-101")
        self.assertEqual(deteksi_standar_skkni("UNKNOWN.CODE", "Standar LSP"), "Standar LSP")

    def test_susun_data_buku_kerja(self):
        docs = schema_library.daftar_skema()
        if not docs:
            self.skipTest("Tidak ada skema terdaftar.")
        
        first_doc = docs[0]
        schema_id = first_doc["id"]
        
        data = susun_data_buku_kerja(
            schema_id=schema_id,
            no_skema="SKM-TEST-001",
            nama_asesor="Asesor Uji",
            no_met="MET.000.12345"
        )
        
        self.assertIsNotNone(data)
        self.assertEqual(data["schema_id"], schema_id)
        self.assertEqual(data["nomor_skema"], "SKM-TEST-001")
        self.assertEqual(data["nama_asesor"], "Asesor Uji")
        self.assertEqual(data["no_met"], "MET.000.12345")
        self.assertEqual(len(data["daftar_unit"]), first_doc.get("jumlah_unit", 0))
        self.assertGreaterEqual(len(data["persyaratan_dasar"]), 1)

    def test_endpoint_cetak_apl(self):
        docs = schema_library.daftar_skema()
        if not docs:
            self.skipTest("Tidak ada skema terdaftar.")
        
        schema_id = docs[0]["id"]
        
        resp = self.client.get(
            f"/skema/{schema_id}/cetak-apl",
            params={
                "doc": "all",
                "no_skema": "SKM-2024-TEST",
                "nama_asesor": "Budi Santoso",
                "no_met": "MET.000.9999"
            }
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("FR.APL.01. PERMOHONAN SERTIFIKASI KOMPETENSI", resp.text)
        self.assertIn("FR.APL.02. ASESMEN MANDIRI", resp.text)
        self.assertIn("SKM-2024-TEST", resp.text)
        self.assertIn("Budi Santoso", resp.text)
        self.assertIn("MET.000.9999", resp.text)

    def test_endpoint_api_buku_kerja(self):
        docs = schema_library.daftar_skema()
        if not docs:
            self.skipTest("Tidak ada skema terdaftar.")
        
        schema_id = docs[0]["id"]
        
        api_resp = self.client.get(
            f"/api/skema/{schema_id}/buku-kerja",
            params={
                "no_skema": "SKM-2024-TEST",
                "nama_asesor": "Budi Santoso",
                "no_met": "MET.000.9999"
            }
        )
        self.assertEqual(api_resp.status_code, 200)
        res_json = api_resp.json()
        self.assertEqual(res_json["nomor_skema"], "SKM-2024-TEST")
        self.assertEqual(res_json["nama_asesor"], "Budi Santoso")


if __name__ == "__main__":
    unittest.main()

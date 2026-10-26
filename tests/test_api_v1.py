"""
SKKNI Extractor - Pengujian Otomatis REST API Eksternal v1 (Fase 4).
"""

import unittest
from fastapi.testclient import TestClient

from app import db, schema_library
from app.main import app


class TestApiV1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.inisialisasi_db()
        cls.client = TestClient(app)
        cls.valid_key = "skkni_live_secret_key_bnsp2023"
        # Buat key admin khusus untuk tes endpoint /keys
        cls.admin_key = db.buat_kunci_api(
            nama_klien="Admin Test Suite",
            peran="admin",
            kunci_khusus="skkni_test_admin_key_999",
        )

    def test_01_tolak_tanpa_kunci_api(self):
        """Memastikan permintaan tanpa API Key ditolak dengan status 401."""
        res = self.client.get("/api/v1/status")
        self.assertEqual(res.status_code, 401)
        self.assertIn("detail", res.json())

    def test_02_tolak_kunci_api_salah(self):
        """Memastikan API Key palsu/salah ditolak dengan status 401."""
        res = self.client.get(
            "/api/v1/status",
            headers={"X-API-Key": "kunci_tidak_valid_xyz"},
        )
        self.assertEqual(res.status_code, 401)

    def test_03_status_dan_ping_dengan_header_x_api_key(self):
        """Memastikan otentikasi X-API-Key berhasil dan mengembalikan status online."""
        res = self.client.get(
            "/api/v1/status",
            headers={"X-API-Key": self.valid_key},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "online")
        self.assertIn("versi", data)
        self.assertEqual(data["klien"]["nama_klien"], "WordPress LSP Plugin / Client Default")
        self.assertIn("muk_sync_v2023", data["fitur"])

    def test_04_status_dengan_bearer_token(self):
        """Memastikan otentikasi Authorization: Bearer <key> didukung."""
        res = self.client.get(
            "/api/v1/ping",
            headers={"Authorization": f"Bearer {self.valid_key}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "online")

    def test_05_katalog_skkni(self):
        """Memastikan endpoint /api/v1/skkni mengembalikan katalog dokumen SKKNI."""
        res = self.client.get(
            "/api/v1/skkni",
            headers={"X-API-Key": self.valid_key},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "sukses")
        self.assertIn("total", data)
        self.assertIn("data", data)
        self.assertIsInstance(data["data"], list)

    def test_06_katalog_skema(self):
        """Memastikan endpoint /api/v1/skema mengembalikan daftar skema."""
        res = self.client.get(
            "/api/v1/skema",
            headers={"X-API-Key": self.valid_key},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "sukses")
        self.assertIn("data", data)
        self.assertIsInstance(data["data"], list)

    def test_07_sinkronisasi_muk_skema(self):
        """Memastikan endpoint /api/v1/skema/{id}/muk mengembalikan data MUK terpadu."""
        daftar = schema_library.daftar_skema()
        if not daftar:
            self.skipTest("Belum ada skema terdaftar.")

        schema_id = daftar[0]["id"]
        res = self.client.get(
            f"/api/v1/skema/{schema_id}/muk",
            headers={"X-API-Key": self.valid_key},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "sukses")
        self.assertEqual(data["skema"]["id"], schema_id)
        self.assertIn("kelompok_pekerjaan", data)
        self.assertIn("instrumen", data)
        self.assertIn("ia_01", data["instrumen"])
        self.assertIn("ia_02", data["instrumen"])
        self.assertIn("referensi_bv_pp", data)

    def test_08_render_dokumen_html(self):
        """Memastikan endpoint /api/v1/documents/render menghasilkan HTML Buku Kerja."""
        daftar = schema_library.daftar_skema()
        if not daftar:
            self.skipTest("Belum ada skema terdaftar.")

        schema_id = daftar[0]["id"]
        payload = {
            "schema_id": schema_id,
            "format": "html",
            "form_code": "FR.IA.02",
        }
        res = self.client.post(
            "/api/v1/documents/render",
            json=payload,
            headers={"X-API-Key": self.valid_key},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "sukses")
        self.assertIn("html", data)
        self.assertIn("<!DOCTYPE html>", data["html"])

    def test_09_render_dokumen_docx(self):
        """Memastikan endpoint /api/v1/documents/render format docx menghasilkan file Word valid."""
        daftar = schema_library.daftar_skema()
        if not daftar:
            self.skipTest("Belum ada skema terdaftar.")

        schema_id = daftar[0]["id"]
        payload = {
            "schema_id": schema_id,
            "format": "docx",
            "form_code": "FR.IA.02",
        }
        res = self.client.post(
            "/api/v1/documents/render",
            json=payload,
            headers={"X-API-Key": self.valid_key},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/vnd.openxmlformats-officedocument.wordprocessingml.document", res.headers.get("content-type", ""))
        self.assertTrue(len(res.content) > 1000)

    def test_10_manajemen_kunci_api(self):
        """Memastikan pembatasan endpoint manajemen kunci API (hanya admin)."""
        # Klien biasa tidak boleh mengakses /keys
        res_tolak = self.client.get(
            "/api/v1/keys",
            headers={"X-API-Key": self.valid_key},
        )
        self.assertEqual(res_tolak.status_code, 403)

        # Admin boleh melihat daftar keys
        res_admin = self.client.get(
            "/api/v1/keys",
            headers={"X-API-Key": self.admin_key},
        )
        self.assertEqual(res_admin.status_code, 200)
        data = res_admin.json()
        self.assertEqual(data["status"], "sukses")
        self.assertTrue(len(data["data"]) >= 2)

        # Admin membuat kunci baru
        res_buat = self.client.post(
            "/api/v1/keys",
            json={"nama_klien": "SIMLSP Integration", "peran": "klien"},
            headers={"X-API-Key": self.admin_key},
        )
        self.assertEqual(res_buat.status_code, 200)
        kunci_baru = res_buat.json()["kunci"]

        # Gunakan kunci baru untuk ping
        res_ping = self.client.get(
            "/api/v1/status",
            headers={"X-API-Key": kunci_baru},
        )
        self.assertEqual(res_ping.status_code, 200)
        self.assertEqual(res_ping.json()["klien"]["nama_klien"], "SIMLSP Integration")


if __name__ == "__main__":
    unittest.main()

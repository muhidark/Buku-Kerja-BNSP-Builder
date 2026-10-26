"""
Pengujian fitur Fase 1: SQLite Multi-User / RBAC & Multi-Versi MUK.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.main import app
from app import db, schema_library
from app.buku_kerja import muat_konfigurasi_muk, simpan_konfigurasi_muk, susun_data_buku_kerja


class TestFase1MultiUserDanMultiVersi(unittest.TestCase):

    def setUp(self):
        db.inisialisasi_db()
        self.client = TestClient(app)

    def test_pengguna_bawaan_dan_autentikasi(self):
        # 1. Admin login valid
        adm = db.autentikasi("admin", "admin123")
        self.assertIsNotNone(adm)
        self.assertEqual(adm["peran"], "admin")

        # 2. Asesor login valid
        asr = db.autentikasi("asesor", "asesor123")
        self.assertIsNotNone(asr)
        self.assertEqual(asr["peran"], "asesor")

        # 3. Kata sandi salah
        gagal = db.autentikasi("admin", "salahpassword")
        self.assertIsNone(gagal)

    def test_sesi_pengguna(self):
        adm = db.autentikasi("admin", "admin123")
        self.assertIsNotNone(adm)
        token = db.buat_sesi(adm["id"], durasi_detik=3600)
        self.assertTrue(len(token) > 20)

        # Ambil pengguna dari sesi
        pengguna = db.ambil_pengguna_dari_sesi(token)
        self.assertIsNotNone(pengguna)
        self.assertEqual(pengguna["username"], "admin")

        # Hapus sesi (logout)
        db.hapus_sesi(token)
        self.assertIsNone(db.ambil_pengguna_dari_sesi(token))

    def test_regulasi_skkni_kemnaker(self):
        db.simpan_status_regulasi(
            kode_skkni="2018-045",
            status_regulasi="dicabut",
            nomor_kepmen="Kepmenaker No. 45 Tahun 2018",
            judul_skkni="Digital Marketing",
            kepmen_pengganti="Kepmenaker No. 124 Tahun 2022",
            catatan="Telah digantikan regulasi baru",
        )
        peta = db.ambil_peta_regulasi()
        self.assertIn("2018-045", peta)
        self.assertEqual(peta["2018-045"]["status_regulasi"], "dicabut")
        self.assertEqual(peta["2018-045"]["kepmen_pengganti"], "Kepmenaker No. 124 Tahun 2022")

    def test_multi_versi_paket_muk(self):
        docs = schema_library.daftar_skema()
        if not docs:
            self.skipTest("Tidak ada skema terdaftar.")
        schema_id = docs[0]["id"]

        # Simpan Paket Versi A
        payload_v1 = {
            "personel": {"nama_asesor": "Asesor Versi 1"},
            "ia02": {"durasi_waktu": "120 Menit"},
        }
        simpan_konfigurasi_muk(
            schema_id=schema_id,
            payload=payload_v1,
            kode_versi="v1",
            nama_versi="Paket MUK Versi A",
            is_aktif=True,
        )

        # Simpan Paket Versi B
        payload_v2 = {
            "personel": {"nama_asesor": "Asesor Versi 2"},
            "ia02": {"durasi_waktu": "180 Menit"},
        }
        simpan_konfigurasi_muk(
            schema_id=schema_id,
            payload=payload_v2,
            kode_versi="v2",
            nama_versi="Paket MUK Versi B",
            is_aktif=False,
        )

        # Muat versi spesifik
        cfg_v1 = muat_konfigurasi_muk(schema_id, kode_versi="v1")
        self.assertEqual(cfg_v1["personel"]["nama_asesor"], "Asesor Versi 1")
        self.assertEqual(cfg_v1["ia02"]["durasi_waktu"], "120 Menit")

        cfg_v2 = muat_konfigurasi_muk(schema_id, kode_versi="v2")
        self.assertEqual(cfg_v2["personel"]["nama_asesor"], "Asesor Versi 2")
        self.assertEqual(cfg_v2["ia02"]["durasi_waktu"], "180 Menit")

        # Cek daftar versi skema
        daftar_v = db.daftar_versi_muk_skema(schema_id)
        kode_set = {v["kode_versi"] for v in daftar_v}
        self.assertIn("v1", kode_set)
        self.assertIn("v2", kode_set)

    def test_flow_web_login_dan_logout(self):
        # 1. Buka halaman login
        resp_get = self.client.get("/login")
        self.assertEqual(resp_get.status_code, 200)
        self.assertIn("Masuk Akun", resp_get.text)
        csrf = resp_get.cookies.get("skkni_csrf", "")

        # 2. Login gagal
        resp_fail = self.client.post(
            "/login",
            data={"csrf_token": csrf, "username": "admin", "password": "salahpassword"},
            follow_redirects=False,
        )
        self.assertEqual(resp_fail.status_code, 303)
        self.assertIn("/login", resp_fail.headers["location"])

        # 3. Login sukses
        resp_ok = self.client.post(
            "/login",
            data={"csrf_token": csrf, "username": "admin", "password": "admin123"},
            follow_redirects=False,
        )
        self.assertEqual(resp_ok.status_code, 303)
        session_cookie = resp_ok.cookies.get("skkni_session")
        self.assertIsNotNone(session_cookie)

        # 4. Akses dashboard dengan cookie sesi
        resp_dash = self.client.get("/", cookies={"skkni_session": session_cookie})
        self.assertEqual(resp_dash.status_code, 200)
        self.assertIn("Administrator Kurator Master", resp_dash.text)

        # 5. Logout
        resp_out = self.client.post(
            "/logout",
            data={"csrf_token": csrf},
            cookies={"skkni_csrf": csrf, "skkni_session": session_cookie},
            follow_redirects=False,
        )
        self.assertEqual(resp_out.status_code, 303)


if __name__ == "__main__":
    unittest.main()

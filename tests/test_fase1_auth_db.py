"""
Pengujian fitur Fase 1: SQLite Multi-User / RBAC & Multi-Versi MUK.

Diperbarui pada langkah 1.3: aplikasi tidak lagi membuat akun dengan kata sandi
publik (admin/admin123, asesor/asesor123). Test membuat akunnya sendiri dengan
kata sandi yang diketahui agar pengujian login tetap sah.
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

SANDI_UJI = 'Sandi-Uji-Fase1-9x'
PENGGUNA_UJI = {
    'admin': ('uji_login_admin', 'Pengguna Uji Admin'),
    'asesor': ('uji_login_asesor', 'Pengguna Uji Asesor'),
}


def pastikan_pengguna_uji(peran: str) -> str:
    """Membuat (sekali) akun uji dengan kata sandi yang diketahui."""
    username, nama = PENGGUNA_UJI[peran]
    ada = {p['username'] for p in db.daftar_pengguna()}
    if username not in ada:
        db.tambah_pengguna(
            username=username,
            kata_sandi=SANDI_UJI,
            nama_lengkap=nama,
            peran=peran,
            email=f'{username}@uji.local',
        )
    else:
        # Pastikan kata sandi tetap seperti yang diharapkan walau test lain
        # pernah mengubahnya.
        pengguna = db.autentikasi(username, SANDI_UJI)
        if not pengguna:
            with db._ambil_koneksi() as conn:
                baris = conn.execute(
                    'SELECT id FROM pengguna WHERE username = ?', (username,)
                ).fetchone()
                db.ubah_kata_sandi(baris['id'], SANDI_UJI)
    return username


class TestFase1MultiUserDanMultiVersi(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        for peran in PENGGUNA_UJI:
            pastikan_pengguna_uji(peran)

    def setUp(self):
        db.inisialisasi_db()
        self.client = TestClient(app)

    def test_tidak_ada_akun_berkata_sandi_publik(self):
        """Akun tidak boleh dibuat otomatis dengan kata sandi yang tercetak di UI."""
        for username, sandi_publik in db.KREDENSIAL_BAWAAN_LAMA:
            hasil = db.autentikasi(username, sandi_publik)
            if hasil is None:
                continue  # akun tidak ada / sandinya sudah diganti -> aman
            self.assertTrue(
                hasil.get('must_change_password'),
                f"Akun '{username}' masih memakai kata sandi publik tanpa penanda wajib ganti.",
            )

    def test_autentikasi_dan_peran(self):
        for peran, (username, _) in PENGGUNA_UJI.items():
            pengguna = db.autentikasi(username, SANDI_UJI)
            self.assertIsNotNone(pengguna, f'login {username} gagal')
            self.assertEqual(pengguna['peran'], peran)

        # Kata sandi salah
        self.assertIsNone(db.autentikasi(PENGGUNA_UJI['admin'][0], 'salahpassword'))
        # Pengguna tidak ada
        self.assertIsNone(db.autentikasi('tidak_ada_pengguna_ini', SANDI_UJI))

    def test_sesi_pengguna(self):
        adm = db.autentikasi(PENGGUNA_UJI['admin'][0], SANDI_UJI)
        self.assertIsNotNone(adm)
        assert adm is not None
        token = db.buat_sesi(adm['id'], durasi_detik=3600)
        self.assertTrue(len(token) > 20)

        pengguna = db.ambil_pengguna_dari_sesi(token)
        self.assertIsNotNone(pengguna)
        assert pengguna is not None
        self.assertEqual(pengguna['username'], PENGGUNA_UJI['admin'][0])
        self.assertIn('must_change_password', pengguna)

        db.hapus_sesi(token)
        self.assertIsNone(db.ambil_pengguna_dari_sesi(token))

    def test_regulasi_skkni_kemnaker(self):
        db.simpan_status_regulasi(
            kode_skkni='2018-045',
            status_regulasi='dicabut',
            nomor_kepmen='Kepmenaker No. 45 Tahun 2018',
            judul_skkni='Digital Marketing',
            kepmen_pengganti='Kepmenaker No. 124 Tahun 2022',
            catatan='Telah digantikan regulasi baru',
        )
        peta = db.ambil_peta_regulasi()
        self.assertIn('2018-045', peta)
        self.assertEqual(peta['2018-045']['status_regulasi'], 'dicabut')
        self.assertEqual(peta['2018-045']['kepmen_pengganti'], 'Kepmenaker No. 124 Tahun 2022')

    def test_multi_versi_paket_muk(self):
        docs = schema_library.daftar_skema()
        if not docs:
            self.skipTest('Tidak ada skema terdaftar.')
        schema_id = docs[0]['id']

        payload_v1 = {
            'personel': {'nama_asesor': 'Asesor Versi 1'},
            'ia02': {'durasi_waktu': '120 Menit'},
        }
        simpan_konfigurasi_muk(
            schema_id=schema_id,
            payload=payload_v1,
            kode_versi='v1',
            nama_versi='Paket MUK Versi A',
            is_aktif=True,
        )

        payload_v2 = {
            'personel': {'nama_asesor': 'Asesor Versi 2'},
            'ia02': {'durasi_waktu': '180 Menit'},
        }
        simpan_konfigurasi_muk(
            schema_id=schema_id,
            payload=payload_v2,
            kode_versi='v2',
            nama_versi='Paket MUK Versi B',
            is_aktif=False,
        )

        cfg_v1 = muat_konfigurasi_muk(schema_id, kode_versi='v1')
        self.assertEqual(cfg_v1['personel']['nama_asesor'], 'Asesor Versi 1')
        self.assertEqual(cfg_v1['ia02']['durasi_waktu'], '120 Menit')

        cfg_v2 = muat_konfigurasi_muk(schema_id, kode_versi='v2')
        self.assertEqual(cfg_v2['personel']['nama_asesor'], 'Asesor Versi 2')
        self.assertEqual(cfg_v2['ia02']['durasi_waktu'], '180 Menit')

        daftar_v = db.daftar_versi_muk_skema(schema_id)
        kode_set = {v['kode_versi'] for v in daftar_v}
        self.assertIn('v1', kode_set)
        self.assertIn('v2', kode_set)

    def test_hanya_satu_versi_muk_aktif(self):
        """Penanda versi aktif harus berbentuk 0/1, bukan timestamp (temuan T-03)."""
        docs = schema_library.daftar_skema()
        if not docs:
            self.skipTest('Tidak ada skema terdaftar.')
        schema_id = docs[0]['id']

        simpan_konfigurasi_muk(schema_id, {'personel': {'nama_asesor': 'Aktif A'}},
                               kode_versi='va', nama_versi='Versi A', is_aktif=True)
        simpan_konfigurasi_muk(schema_id, {'personel': {'nama_asesor': 'Aktif B'}},
                               kode_versi='vb', nama_versi='Versi B', is_aktif=True)

        daftar = [v for v in db.daftar_versi_muk_skema(schema_id) if v['kode_versi'] in ('va', 'vb')]
        aktif = [v for v in daftar if v['is_aktif'] in (1, '1', True)]
        self.assertEqual(len(aktif), 1, f'harus tepat satu versi aktif, ditemukan: {aktif}')
        self.assertEqual(aktif[0]['kode_versi'], 'vb')

        for v in daftar:
            self.assertIn(str(v['is_aktif']), ('0', '1'),
                          f"is_aktif berisi nilai bukan biner: {v['is_aktif']!r}")
            self.assertRegex(str(v['diperbarui_pada']), r'^\d{4}-\d{2}-\d{2}T',
                             f"diperbarui_pada bukan timestamp: {v['diperbarui_pada']!r}")

        # Bersihkan versi uji agar tidak menumpuk di data/app.db setiap run.
        with db._ambil_koneksi() as conn:
            conn.execute("DELETE FROM muk_versi WHERE schema_id = ? AND kode_versi IN ('va','vb')",
                         (schema_id,))
            conn.commit()

    def test_migrasi_membetulkan_baris_penanda_tertukar(self):
        """Baris lama yang is_aktif/diperbarui_pada tertukar harus dibalik pasti."""
        schema_id = 'uji_migrasi_penanda_muk'
        with db._ambil_koneksi() as conn:
            conn.execute('DELETE FROM muk_versi WHERE schema_id = ?', (schema_id,))
            # Tiruan baris cacat versi lama: nilai penanda masuk ke
            # diperbarui_pada, timestamp masuk ke is_aktif.
            conn.execute(
                """INSERT INTO muk_versi
                   (schema_id, kode_versi, nama_versi, deskripsi, data_json,
                    dibuat_oleh, diperbarui_pada, is_aktif)
                   VALUES (?, 'v1', 'Versi 1', '', '{}', NULL, '1', '2026-10-26T12:31:09+00:00')""",
                (schema_id,),
            )
            conn.execute(
                """INSERT INTO muk_versi
                   (schema_id, kode_versi, nama_versi, deskripsi, data_json,
                    dibuat_oleh, diperbarui_pada, is_aktif)
                   VALUES (?, 'v2', 'Versi 2', '', '{}', NULL, '0', 0)""",
                (schema_id,),
            )
            conn.commit()

        db.inisialisasi_db()

        with db._ambil_koneksi() as conn:
            rows = {
                r['kode_versi']: dict(r)
                for r in conn.execute(
                    'SELECT kode_versi, is_aktif, diperbarui_pada FROM muk_versi WHERE schema_id = ?',
                    (schema_id,),
                )
            }

        self.assertEqual(str(rows['v1']['is_aktif']), '1', rows['v1'])
        self.assertEqual(str(rows['v2']['is_aktif']), '0', rows['v2'])
        self.assertRegex(str(rows['v1']['diperbarui_pada']), r'^\d{4}-\d{2}-\d{2}T',
                         'timestamp asli harus dikembalikan ke diperbarui_pada')
        self.assertRegex(str(rows['v2']['diperbarui_pada']), r'^\d{4}-\d{2}-\d{2}T',
                         'timestamp yang tertimpa harus diganti timestamp baru')

        # idempoten: jalankan lagi tidak boleh mengubah apa pun
        db.inisialisasi_db()
        with db._ambil_koneksi() as conn:
            ulang = {
                r['kode_versi']: dict(r)
                for r in conn.execute(
                    'SELECT kode_versi, is_aktif, diperbarui_pada FROM muk_versi WHERE schema_id = ?',
                    (schema_id,),
                )
            }
        self.assertEqual(ulang['v1'], rows['v1'])
        self.assertEqual(ulang['v2'], rows['v2'])

        with db._ambil_koneksi() as conn:
            conn.execute('DELETE FROM muk_versi WHERE schema_id = ?', (schema_id,))
            conn.commit()

    def test_flow_web_login_dan_logout(self):
        username = PENGGUNA_UJI['admin'][0]

        resp_get = self.client.get('/login')
        self.assertEqual(resp_get.status_code, 200)
        self.assertIn('Masuk Akun', resp_get.text)
        csrf = resp_get.cookies.get('skkni_csrf') or ''

        # Tidak boleh ada kredensial yang dicetak di halaman login
        self.assertNotIn('admin123', resp_get.text)
        self.assertNotIn('asesor123', resp_get.text)

        resp_fail = self.client.post(
            '/login',
            data={'csrf_token': csrf, 'username': username, 'password': 'salahpassword'},
            follow_redirects=False,
        )
        self.assertEqual(resp_fail.status_code, 303)
        self.assertIn('/login', resp_fail.headers['location'])

        resp_ok = self.client.post(
            '/login',
            data={'csrf_token': csrf, 'username': username, 'password': SANDI_UJI},
            follow_redirects=False,
        )
        self.assertEqual(resp_ok.status_code, 303)
        session_cookie = resp_ok.cookies.get('skkni_session') or ''
        self.assertIsNotNone(session_cookie)

        resp_dash = self.client.get('/', cookies={'skkni_session': session_cookie})
        self.assertEqual(resp_dash.status_code, 200)
        self.assertIn(PENGGUNA_UJI['admin'][1], resp_dash.text)

        resp_out = self.client.post(
            '/logout',
            data={'csrf_token': csrf},
            cookies={'skkni_csrf': csrf, 'skkni_session': session_cookie},
            follow_redirects=False,
        )
        self.assertEqual(resp_out.status_code, 303)

    def test_login_mengembalikan_ke_halaman_yang_ditolak(self):
        """Setelah diarahkan ke /login?next=..., login harus kembali ke halaman itu."""
        username = PENGGUNA_UJI['asesor'][0]
        halaman = self.client.get('/login?next=/skema')
        csrf = halaman.cookies.get('skkni_csrf') or ''
        self.assertIn('name="next" value="/skema"', halaman.text)

        r = self.client.post(
            '/login',
            data={'csrf_token': csrf, 'username': username, 'password': SANDI_UJI,
                  'next': '/skema'},
            follow_redirects=False,
        )
        self.assertEqual(r.status_code, 303)
        self.assertTrue(r.headers['location'].startswith('/skema'),
                        f"tujuan salah: {r.headers['location']!r}")

    def test_next_tidak_boleh_open_redirect(self):
        halaman = self.client.get('/login?next=https://jahat.example/')
        self.assertNotIn('jahat.example', halaman.text)
        self.assertNotIn('name="next"', halaman.text)


if __name__ == '__main__':
    unittest.main()

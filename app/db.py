"""
SKKNI Extractor - Database Manager (SQLite) (Fase 1).

Menyediakan:
1. Inisialisasi basis data SQLite lokal di data/app.db
2. Manajemen Pengguna & RBAC:
   - admin: Kurator Master (kelola SKKNI, koreksi master, status regulasi Kemnaker)
   - asesor: Penyusun / Asesor (kelola skema & instrumen MUK)
3. Manajemen Sesi Pengguna berbasis token cookie HttpOnly
4. Multi-Versi Paket MUK per Skema (misal: Paket Versi A, Paket Versi B)
5. Katalog Status Regulasi SKKNI Kemnaker (Berlaku / Dicabut)
"""

import hashlib
import hmac
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from app.logging_config import ambil_logger

ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "data"
DB_PATH = DB_DIR / "app.db"

#: Nama akun admin yang dibuat otomatis pada basis data kosong.
ADMIN_PERTAMA = "admin"

#: Kredensial yang PERNAH dicetak di halaman login versi 1.0.0.
#: Konstanta ini hanya dipakai untuk MENDETEKSI akun lama yang masih memakai
#: kata sandi publik tersebut, lalu memaksanya mengganti sandi. Tidak dipakai
#: untuk membuat akun. Hapus entri di sini setelah semua pemasangan
#: dimigrasikan (lihat docs/KEAMANAN.md).
KREDENSIAL_BAWAAN_LAMA: Tuple[Tuple[str, str], ...] = (
    ("admin", "admin123"),
    ("asesor", "asesor123"),
)

#: Kunci API yang pernah dibuat otomatis dan tercantum di panduan publik.
#: Kunci ini dicabut saat migrasi; pembuatan kunci baru hanya lewat
#: tools/kunci_api.py atau endpoint admin.
KUNCI_API_BAWAAN_LAMA: Tuple[str, ...] = ("skkni_live_secret_key_bnsp2023",)


def _log_aman():
    """Logger aplikasi untuk peristiwa keamanan (tanpa isi rahasia)."""
    return ambil_logger("db")


def _kolom_tabel(conn: sqlite3.Connection, tabel: str) -> set:
    """Nama kolom yang ada pada sebuah tabel (PRAGMA table_info).

    `tabel` hanya boleh berasal dari konstanta di modul ini; nilainya tidak
    dapat diparameterkan pada PRAGMA, jadi jangan pernah diisi dari input pengguna.
    """
    return {baris["name"] for baris in conn.execute(f"PRAGMA table_info({tabel})")}


def _tambah_kolom(conn: sqlite3.Connection, tabel: str, kolom: str, definisi: str) -> bool:
    """Menambahkan kolom bila belum ada (idempoten, aman dijalankan berulang)."""
    if kolom in _kolom_tabel(conn, tabel):
        return False
    conn.execute(f"ALTER TABLE {tabel} ADD COLUMN {kolom} {definisi}")
    return True


@contextmanager
def _ambil_koneksi() -> Generator[sqlite3.Connection, None, None]:
    """Membuka koneksi SQLite dengan pengaturan aman untuk akses bersamaan.

    WAL + busy_timeout mencegah galat "database is locked" ketika job ekstraksi
    (2 worker) menulis sementara halaman web membaca basis data. timeout=5 juga
    membuat sqlite3 menunggu kunci alih-alih langsung menyerah.
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def hash_kata_sandi(kata_sandi: str, garam: Optional[str] = None) -> Tuple[str, str]:
    """Menghasilkan hash kata sandi PBKDF2-HMAC-SHA256 aman dan garam (salt)."""
    if not garam:
        garam = secrets.token_hex(16)
    kunci = hashlib.pbkdf2_hmac(
        "sha256",
        kata_sandi.encode("utf-8"),
        garam.encode("utf-8"),
        100_000,
    )
    return kunci.hex(), garam


def verifikasi_kata_sandi(kata_sandi: str, hash_disimpan: str, garam: str) -> bool:
    """Verifikasi kata sandi terhadap hash dan garam yang tersimpan."""
    hash_uji, _ = hash_kata_sandi(kata_sandi, garam)
    return hmac.compare_digest(hash_disimpan, hash_uji)


def inisialisasi_db() -> None:
    """Membuat tabel-tabel SQLite bila belum ada dan akun admin bawaan."""
    with _ambil_koneksi() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS pengguna (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            nama_lengkap TEXT NOT NULL,
            email TEXT,
            peran TEXT NOT NULL CHECK(peran IN ('admin', 'asesor')),
            hash_kata_sandi TEXT NOT NULL,
            garam TEXT NOT NULL,
            no_met TEXT,
            dibuat_pada TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sesi (
            token TEXT PRIMARY KEY,
            pengguna_id INTEGER NOT NULL REFERENCES pengguna(id) ON DELETE CASCADE,
            dibuat_pada TEXT NOT NULL,
            kedaluwarsa_pada TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS regulasi_skkni (
            kode_skkni TEXT PRIMARY KEY,
            nomor_kepmen TEXT,
            judul_skkni TEXT,
            status_regulasi TEXT NOT NULL DEFAULT 'berlaku' CHECK(status_regulasi IN ('berlaku', 'dicabut')),
            kepmen_pengganti TEXT,
            catatan TEXT,
            diperbarui_pada TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS muk_versi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schema_id TEXT NOT NULL,
            kode_versi TEXT NOT NULL,
            nama_versi TEXT NOT NULL,
            deskripsi TEXT,
            data_json TEXT NOT NULL,
            dibuat_oleh INTEGER REFERENCES pengguna(id) ON DELETE SET NULL,
            diperbarui_pada TEXT NOT NULL,
            is_aktif INTEGER NOT NULL DEFAULT 1,
            UNIQUE(schema_id, kode_versi)
        );

        CREATE TABLE IF NOT EXISTS kunci_api (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kunci TEXT UNIQUE NOT NULL,
            nama_klien TEXT NOT NULL,
            peran TEXT NOT NULL DEFAULT 'klien',
            aktif INTEGER NOT NULL DEFAULT 1,
            dibuat_pada TEXT NOT NULL,
            terakhir_digunakan TEXT
        );
        """)

        sekarang = datetime.now(timezone.utc).isoformat()

        # ---------------------------------------------------------- migrasi kolom
        # Idempoten: aman dijalankan setiap start, tidak mengubah apa pun bila
        # kolom sudah ada. Kerangka migrasi bernomor (PRAGMA user_version)
        # menyusul pada langkah 4.3.
        _tambah_kolom(conn, "pengguna", "must_change_password", "INTEGER NOT NULL DEFAULT 0")
        _tambah_kolom(conn, "kunci_api", "kunci_hash", "TEXT")
        _tambah_kolom(conn, "kunci_api", "prefix", "TEXT")
        _tambah_kolom(conn, "kunci_api", "kedaluwarsa", "TEXT")

        # ------------------------------------------- akun pertama (sandi acak)
        cur = conn.execute("SELECT COUNT(*) AS total FROM pengguna")
        if cur.fetchone()["total"] == 0:
            sandi_awal = secrets.token_urlsafe(12)
            h_admin, s_admin = hash_kata_sandi(sandi_awal)
            conn.execute(
                """INSERT INTO pengguna
                   (username, nama_lengkap, email, peran, hash_kata_sandi, garam, no_met, dibuat_pada, must_change_password)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (ADMIN_PERTAMA, "Administrator Kurator Master", "admin@lsp.local", "admin",
                 h_admin, s_admin, "", sekarang),
            )
            conn.commit()
            # Kata sandi hanya ditampilkan di konsol, TIDAK ditulis ke berkas log
            # (berkas log bertahan lama dan mudah tersalin).
            print(
                "\n" + "=" * 74 + "\n"
                "AKUN ADMIN PERTAMA DIBUAT (basis data masih kosong)\n"
                f"  username : {ADMIN_PERTAMA}\n"
                f"  sandi    : {sandi_awal}\n"
                "Kata sandi ini hanya ditampilkan sekarang. Setelah masuk, Anda wajib\n"
                "menggantinya lewat halaman Ganti Kata Sandi.\n"
                + "=" * 74 + "\n",
                flush=True,
            )
            _log_aman().warning(
                "Akun '%s' dibuat dengan kata sandi acak (ditampilkan sekali di konsol).",
                ADMIN_PERTAMA,
            )

        # ------------------------------- akun lama yang masih memakai sandi publik
        for username, sandi_publik in KREDENSIAL_BAWAAN_LAMA:
            baris = conn.execute(
                "SELECT id, hash_kata_sandi, garam, must_change_password FROM pengguna WHERE username = ?",
                (username,),
            ).fetchone()
            if not baris or baris["must_change_password"]:
                continue
            if verifikasi_kata_sandi(sandi_publik, baris["hash_kata_sandi"], baris["garam"]):
                conn.execute(
                    "UPDATE pengguna SET must_change_password = 1 WHERE id = ?", (baris["id"],)
                )
                conn.commit()
                _log_aman().warning(
                    "Akun '%s' masih memakai kata sandi bawaan yang dulu dicetak di halaman "
                    "login; akun ditandai wajib ganti sandi.", username,
                )

        # -------------------------------------- cabut kunci API bawaan yang publik
        for kunci_lama in KUNCI_API_BAWAAN_LAMA:
            cur_cabut = conn.execute(
                "UPDATE kunci_api SET aktif = 0 WHERE kunci = ? AND aktif = 1", (kunci_lama,)
            )
            if cur_cabut.rowcount:
                conn.commit()
                _log_aman().warning(
                    "Kunci API bawaan yang pernah tercantum di panduan publik telah dicabut. "
                    "Buat kunci baru lewat: python -m tools.kunci_api buat --nama <klien>"
                )


# ==============================================================================
# Layanan Pengguna & Otentikasi
# ==============================================================================

def autentikasi(username: str, kata_sandi: str) -> Optional[Dict[str, Any]]:
    """Memverifikasi username dan kata sandi. Mengembalikan dict pengguna atau None."""
    with _ambil_koneksi() as conn:
        row = conn.execute("SELECT * FROM pengguna WHERE username = ?", (username.strip(),)).fetchone()
        if not row:
            return None
        if verifikasi_kata_sandi(kata_sandi, row["hash_kata_sandi"], row["garam"]):
            return {
                "id": row["id"],
                "username": row["username"],
                "nama_lengkap": row["nama_lengkap"],
                "email": row["email"],
                "peran": row["peran"],
                "no_met": row["no_met"],
                "must_change_password": bool(row["must_change_password"]),
            }
        return None


def ubah_kata_sandi(pengguna_id: int, kata_sandi_baru: str) -> None:
    """Mengganti kata sandi pengguna dan melepas penanda wajib ganti sandi."""
    if len(kata_sandi_baru or "") < 8:
        raise ValueError("Kata sandi baru minimal 8 karakter.")
    h, s = hash_kata_sandi(kata_sandi_baru)
    with _ambil_koneksi() as conn:
        cur = conn.execute(
            "UPDATE pengguna SET hash_kata_sandi = ?, garam = ?, must_change_password = 0 WHERE id = ?",
            (h, s, pengguna_id),
        )
        conn.commit()
        if not cur.rowcount:
            raise ValueError("Pengguna tidak ditemukan.")


def buat_sesi(pengguna_id: int, durasi_detik: int = 60 * 60 * 24 * 7) -> str:
    """Membuat token sesi baru dan menyimpannya di basis data."""
    token = secrets.token_urlsafe(36)
    sekarang = datetime.now(timezone.utc)
    kedaluwarsa = datetime.fromtimestamp(sekarang.timestamp() + durasi_detik, tz=timezone.utc)
    with _ambil_koneksi() as conn:
        conn.execute(
            "INSERT INTO sesi (token, pengguna_id, dibuat_pada, kedaluwarsa_pada) VALUES (?, ?, ?, ?)",
            (token, pengguna_id, sekarang.isoformat(), kedaluwarsa.isoformat()),
        )
        conn.commit()
    return token


def ambil_pengguna_dari_sesi(token: str) -> Optional[Dict[str, Any]]:
    """Mengambil data pengguna aktif berdasarkan token sesi yang valid."""
    if not token:
        return None
    with _ambil_koneksi() as conn:
        row = conn.execute(
            """SELECT p.id, p.username, p.nama_lengkap, p.email, p.peran, p.no_met,
                      p.must_change_password, s.kedaluwarsa_pada
               FROM sesi s
               JOIN pengguna p ON s.pengguna_id = p.id
               WHERE s.token = ?""",
            (token,),
        ).fetchone()
        if not row:
            return None
        # Periksa masa berlaku
        try:
            exp = datetime.fromisoformat(row["kedaluwarsa_pada"])
            if datetime.now(timezone.utc) > exp:
                hapus_sesi(token)
                return None
        except Exception:
            pass
        return {
            "id": row["id"],
            "username": row["username"],
            "nama_lengkap": row["nama_lengkap"],
            "email": row["email"],
            "peran": row["peran"],
            "no_met": row["no_met"],
            "must_change_password": bool(row["must_change_password"]),
        }


def hapus_sesi(token: str) -> None:
    """Menghapus sesi pengguna (logout)."""
    with _ambil_koneksi() as conn:
        conn.execute("DELETE FROM sesi WHERE token = ?", (token,))
        conn.commit()


def hapus_semua_sesi_pengguna(pengguna_id: int) -> int:
    """Menghapus seluruh sesi milik satu pengguna (dipakai test agar tidak menumpuk)."""
    with _ambil_koneksi() as conn:
        cur = conn.execute("DELETE FROM sesi WHERE pengguna_id = ?", (pengguna_id,))
        conn.commit()
        return cur.rowcount


def daftar_pengguna() -> List[Dict[str, Any]]:
    with _ambil_koneksi() as conn:
        rows = conn.execute("SELECT id, username, nama_lengkap, email, peran, no_met, dibuat_pada FROM pengguna ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]


def tambah_pengguna(username: str, kata_sandi: str, nama_lengkap: str, peran: str = "asesor", email: str = "", no_met: str = "") -> int:
    h, s = hash_kata_sandi(kata_sandi)
    sekarang = datetime.now(timezone.utc).isoformat()
    with _ambil_koneksi() as conn:
        cur = conn.execute(
            """INSERT INTO pengguna
               (username, nama_lengkap, email, peran, hash_kata_sandi, garam, no_met, dibuat_pada)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (username.strip(), nama_lengkap.strip(), email.strip(), peran.strip(), h, s, no_met.strip(), sekarang),
        )
        conn.commit()
        return cur.lastrowid


# ==============================================================================
# Regulasi SKKNI Kemnaker (Berlaku / Dicabut)
# ==============================================================================

def simpan_status_regulasi(kode_skkni: str, status_regulasi: str, nomor_kepmen: str = "", judul_skkni: str = "", kepmen_pengganti: str = "", catatan: str = "") -> None:
    sekarang = datetime.now(timezone.utc).isoformat()
    with _ambil_koneksi() as conn:
        conn.execute(
            """INSERT INTO regulasi_skkni
               (kode_skkni, nomor_kepmen, judul_skkni, status_regulasi, kepmen_pengganti, catatan, diperbarui_pada)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(kode_skkni) DO UPDATE SET
               nomor_kepmen = excluded.nomor_kepmen,
               judul_skkni = excluded.judul_skkni,
               status_regulasi = excluded.status_regulasi,
               kepmen_pengganti = excluded.kepmen_pengganti,
               catatan = excluded.catatan,
               diperbarui_pada = excluded.diperbarui_pada""",
            (kode_skkni.strip(), nomor_kepmen.strip(), judul_skkni.strip(), status_regulasi.strip(), kepmen_pengganti.strip(), catatan.strip(), sekarang),
        )
        conn.commit()


def ambil_peta_regulasi() -> Dict[str, Dict[str, Any]]:
    with _ambil_koneksi() as conn:
        rows = conn.execute("SELECT * FROM regulasi_skkni").fetchall()
        return {r["kode_skkni"]: dict(r) for r in rows}


# ==============================================================================
# Multi-Versi Paket MUK per Skema
# ==============================================================================

def daftar_versi_muk_skema(schema_id: str) -> List[Dict[str, Any]]:
    with _ambil_koneksi() as conn:
        rows = conn.execute(
            """SELECT v.id, v.schema_id, v.kode_versi, v.nama_versi, v.deskripsi, v.diperbarui_pada, v.is_aktif, p.nama_lengkap AS pembuat
               FROM muk_versi v
               LEFT JOIN pengguna p ON v.dibuat_oleh = p.id
               WHERE v.schema_id = ?
               ORDER BY v.id ASC""",
            (schema_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def ambil_versi_muk(schema_id: str, kode_versi: str) -> Optional[Dict[str, Any]]:
    with _ambil_koneksi() as conn:
        row = conn.execute(
            "SELECT * FROM muk_versi WHERE schema_id = ? AND kode_versi = ?",
            (schema_id, kode_versi),
        ).fetchone()
        if not row:
            return None
        res = dict(row)
        try:
            res["payload"] = json.loads(res["data_json"])
        except Exception:
            res["payload"] = {}
        return res


def simpan_versi_muk(schema_id: str, kode_versi: str, nama_versi: str, data_payload: Dict[str, Any], deskripsi: str = "", dibuat_oleh: Optional[int] = None, is_aktif: bool = True) -> int:
    sekarang = datetime.now(timezone.utc).isoformat()
    raw_json = json.dumps(data_payload, ensure_ascii=False, indent=2)
    with _ambil_koneksi() as conn:
        if is_aktif:
            # Setel versi lain menjadi non-aktif untuk skema ini
            conn.execute("UPDATE muk_versi SET is_aktif = 0 WHERE schema_id = ?", (schema_id,))
        cur = conn.execute(
            """INSERT INTO muk_versi
               (schema_id, kode_versi, nama_versi, deskripsi, data_json, dibuat_oleh, diperbarui_pada, is_aktif)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(schema_id, kode_versi) DO UPDATE SET
               nama_versi = excluded.nama_versi,
               deskripsi = excluded.deskripsi,
               data_json = excluded.data_json,
               diperbarui_pada = excluded.diperbarui_pada,
               is_aktif = excluded.is_aktif""",
            (schema_id, kode_versi.strip(), nama_versi.strip(), deskripsi.strip(), raw_json, dibuat_oleh, 1 if is_aktif else 0, sekarang),
        )
        conn.commit()
        return cur.lastrowid


# ==============================================================================
# Manajemen Kunci API Eksternal (Fase 4)
# ==============================================================================

def validasi_kunci_api(kunci: str) -> Optional[Dict[str, Any]]:
    """Memvalidasi kunci API eksternal dan mencatat timestamp terakhir digunakan."""
    if not kunci or not kunci.strip():
        return None
    sekarang = datetime.now(timezone.utc).isoformat()
    with _ambil_koneksi() as conn:
        row = conn.execute(
            "SELECT id, kunci, nama_klien, peran, aktif FROM kunci_api WHERE kunci = ? AND aktif = 1",
            (kunci.strip(),),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE kunci_api SET terakhir_digunakan = ? WHERE id = ?",
            (sekarang, row["id"]),
        )
        conn.commit()
        return dict(row)


def buat_kunci_api(nama_klien: str, peran: str = "klien", kunci_khusus: Optional[str] = None) -> str:
    """Membuat kunci API baru untuk integrasi eksternal (idempotent bila kunci_khusus telah ada)."""
    kunci = kunci_khusus.strip() if kunci_khusus else f"skkni_live_{secrets.token_urlsafe(24)}"
    sekarang = datetime.now(timezone.utc).isoformat()
    with _ambil_koneksi() as conn:
        conn.execute(
            """INSERT INTO kunci_api (kunci, nama_klien, peran, aktif, dibuat_pada)
               VALUES (?, ?, ?, 1, ?)
               ON CONFLICT(kunci) DO UPDATE SET
               nama_klien = excluded.nama_klien,
               peran = excluded.peran,
               aktif = 1""",
            (kunci, nama_klien.strip(), peran.strip(), sekarang),
        )
        conn.commit()
        return kunci


def daftar_kunci_api() -> List[Dict[str, Any]]:
    """Mengembalikan daftar seluruh kunci API terdaftar."""
    with _ambil_koneksi() as conn:
        rows = conn.execute(
            "SELECT id, kunci, nama_klien, peran, aktif, dibuat_pada, terakhir_digunakan FROM kunci_api ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def ubah_status_kunci_api(kunci: str, aktif: bool) -> bool:
    """Mengaktifkan atau menonaktifkan kunci API (berdasarkan nilai kunci)."""
    with _ambil_koneksi() as conn:
        cur = conn.execute(
            "UPDATE kunci_api SET aktif = ? WHERE kunci = ?",
            (1 if aktif else 0, kunci.strip()),
        )
        conn.commit()
        return cur.rowcount > 0


def ubah_status_kunci_api_id(kunci_id: int, aktif: bool) -> bool:
    """Mengaktifkan atau menonaktifkan kunci API berdasarkan id baris.

    Dipakai setelah kunci disimpan sebagai hash: nilai aslinya tidak lagi
    tersedia, sehingga pencabutan harus memakai id.
    """
    with _ambil_koneksi() as conn:
        cur = conn.execute(
            "UPDATE kunci_api SET aktif = ? WHERE id = ?",
            (1 if aktif else 0, int(kunci_id)),
        )
        conn.commit()
        return cur.rowcount > 0


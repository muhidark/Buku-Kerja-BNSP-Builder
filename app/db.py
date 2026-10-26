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

ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "data"
DB_PATH = DB_DIR / "app.db"


@contextmanager
def _ambil_koneksi() -> Generator[sqlite3.Connection, None, None]:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
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
        """)

        # Buat akun admin dan asesor default bila tabel pengguna masih kosong
        cur = conn.execute("SELECT COUNT(*) AS total FROM pengguna")
        if cur.fetchone()["total"] == 0:
            sekarang = datetime.now(timezone.utc).isoformat()
            # Akun Admin Master: admin / admin123
            h_admin, s_admin = hash_kata_sandi("admin123")
            conn.execute(
                """INSERT INTO pengguna
                   (username, nama_lengkap, email, peran, hash_kata_sandi, garam, no_met, dibuat_pada)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("admin", "Administrator Kurator Master", "admin@lsp.local", "admin", h_admin, s_admin, "", sekarang),
            )
            # Akun Asesor Bawaan: asesor / asesor123
            h_asesor, s_asesor = hash_kata_sandi("asesor123")
            conn.execute(
                """INSERT INTO pengguna
                   (username, nama_lengkap, email, peran, hash_kata_sandi, garam, no_met, dibuat_pada)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("asesor", "Asesor Kompetensi", "asesor@lsp.local", "asesor", h_asesor, s_asesor, "MET.000.032423 2019", sekarang),
            )
            conn.commit()


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
            }
        return None


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
            """SELECT p.id, p.username, p.nama_lengkap, p.email, p.peran, p.no_met, s.kedaluwarsa_pada
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
        }


def hapus_sesi(token: str) -> None:
    """Menghapus sesi pengguna (logout)."""
    with _ambil_koneksi() as conn:
        conn.execute("DELETE FROM sesi WHERE token = ?", (token,))
        conn.commit()


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

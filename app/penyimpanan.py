"""Operasi berkas yang sebelumnya disalin di beberapa modul (temuan T-19).

Ada dua salinan `_tulis_json_atomik` (library, schema_library), empat salinan
`siapkan_direktori`, dan dua salinan `_sha256`. Perbedaan kecil di antaranya
berbahaya: satu versi melakukan `fsync` dan yang lain tidak, sehingga jaminan
"berkas tidak pernah setengah tertulis" hanya berlaku di sebagian jalur.

Semua penulisan di sini memakai pola tulis-ke-berkas-sementara lalu `os.replace`
(atomik pada sistem berkas yang sama) dan `fsync` sebelum penggantian.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Optional

BAGIAN_BACA = 1024 * 1024  # 1 MB per potong untuk hashing berkas besar


def pastikan_direktori(daftar: Iterable[Path]) -> None:
    """Membuat direktori yang belum ada (idempoten)."""
    for d in daftar:
        Path(d).mkdir(parents=True, exist_ok=True)


def tulis_json_atomik(path: Path, data: Any) -> None:
    """Menulis JSON secara atomik: pembaca tidak pernah melihat berkas separuh."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, sementara = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(sementara, path)
    except BaseException:
        # Jangan tinggalkan berkas sementara bila penulisan gagal.
        try:
            os.unlink(sementara)
        except OSError:
            pass
        raise


def tulis_teks_atomik(path: Path, teks: str) -> None:
    """Menulis teks biasa secara atomik."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, sementara = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(teks)
            f.flush()
            os.fsync(f.fileno())
        os.replace(sementara, path)
    except BaseException:
        try:
            os.unlink(sementara)
        except OSError:
            pass
        raise


def baca_json(path: Path) -> Optional[Any]:
    """Membaca JSON; mengembalikan None bila berkas hilang atau rusak."""
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return None


def sha256_berkas(path: Path, batas: Optional[int] = None) -> str:
    """SHA-256 isi berkas, dibaca bertahap agar PDF besar tidak masuk memori."""
    h = hashlib.sha256()
    sisa = batas
    with open(path, 'rb') as f:
        while True:
            ukuran = BAGIAN_BACA if sisa is None else min(BAGIAN_BACA, sisa)
            if ukuran <= 0:
                break
            potong = f.read(ukuran)
            if not potong:
                break
            h.update(potong)
            if sisa is not None:
                sisa -= len(potong)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

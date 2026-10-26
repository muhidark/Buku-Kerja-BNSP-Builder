"""Pencadangan harian otomatis (perbaikan T-31 / langkah 4.3).

`tools/backup.py` sudah bisa membuat arsip ZIP ber-manifest, tetapi tidak
pernah dipanggil otomatis sehingga cadangan hanya ada bila seseorang ingat
menjalankan perintahnya.

Aturan yang dipakai:
- cadangan dibuat paling banyak SEKALI per hari (berdasarkan tanggal di nama
  berkas), dijalankan di latar belakang agar start aplikasi tidak tertahan;
- tujuh arsip terbaru disimpan, sisanya dihapus;
- bila pembuatan gagal, aplikasi tetap berjalan dan kegagalan dicatat di log —
  pencadangan tidak boleh menghalangi pemakaian.

Dapat dimatikan dengan variabel lingkungan `SKKNI_TANPA_CADANGAN=1`
(mis. saat menjalankan test atau saat data sedang dipulihkan).
"""

from __future__ import annotations

import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional

from app.logging_config import ambil_logger

logger = ambil_logger('cadangan')

ROOT = Path(__file__).resolve().parent.parent
DIR_CADANGAN = ROOT / 'backups'
SIMPAN_MAKSIMUM = 7
POLA_GLOB = 'backup_skkni_*.zip'


def _tanggal_hari_ini() -> str:
    return datetime.now().strftime('%Y%m%d')


def daftar_cadangan(direktori: Optional[Path] = None) -> list[Path]:
    """Arsip cadangan yang ada, terbaru lebih dulu."""
    d = Path(direktori) if direktori else DIR_CADANGAN
    if not d.is_dir():
        return []
    berkas = [p for p in d.glob(POLA_GLOB) if p.is_file()]
    return sorted(berkas, key=lambda p: p.stat().st_mtime, reverse=True)


def sudah_hari_ini(direktori: Optional[Path] = None) -> bool:
    """True bila sudah ada cadangan bertanggal hari ini."""
    cap = _tanggal_hari_ini()
    return any(cap in p.name for p in daftar_cadangan(direktori))


def terakhir(direktori: Optional[Path] = None) -> Optional[Dict[str, str]]:
    """Ringkasan cadangan terakhir untuk ditampilkan di dashboard."""
    berkas = daftar_cadangan(direktori)
    if not berkas:
        return None
    p = berkas[0]
    return {
        'nama': p.name,
        'waktu': datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec='seconds'),
        'ukuran_kb': str(max(1, p.stat().st_size // 1024)),
    }


def putar(direktori: Optional[Path] = None, simpan: int = SIMPAN_MAKSIMUM) -> int:
    """Menghapus arsip lama sehingga hanya `simpan` terbaru yang tersisa."""
    berkas = daftar_cadangan(direktori)
    dihapus = 0
    for p in berkas[simpan:]:
        try:
            p.unlink()
            dihapus += 1
        except OSError as e:
            logger.warning('Gagal menghapus cadangan lama %s: %s', p.name, e)
    return dihapus


def buat_sekarang(direktori: Optional[Path] = None,
                  pembuat: Optional[Callable[[Path], object]] = None) -> Optional[Path]:
    """Membuat satu arsip cadangan. Mengembalikan path arsip atau None."""
    d = Path(direktori) if direktori else DIR_CADANGAN
    d.mkdir(parents=True, exist_ok=True)
    try:
        if pembuat is None:
            from tools.backup import buat_backup
            arsip, _manifest = buat_backup(d)
        else:
            hasil = pembuat(d)
            arsip = hasil[0] if isinstance(hasil, tuple) else hasil
        logger.info('Cadangan harian dibuat: %s', Path(arsip).name)
        putar(d)
        return Path(arsip)
    except Exception as e:  # noqa: BLE001 — pencadangan tidak boleh mematikan aplikasi
        logger.warning('Pencadangan harian gagal: %s: %s', type(e).__name__, e)
        return None


def jalankan_harian(direktori: Optional[Path] = None,
                    pembuat: Optional[Callable[[Path], object]] = None,
                    latar: bool = True) -> Optional[threading.Thread | Path]:
    """Menjalankan pencadangan bila hari ini belum ada.

    `latar=True` menjalankannya di thread terpisah (dipakai saat start
    aplikasi). Mengembalikan thread, path arsip, atau None bila dilewati.
    """
    if os.environ.get('SKKNI_TANPA_CADANGAN') == '1':
        return None
    if sudah_hari_ini(direktori):
        return None

    if not latar:
        return buat_sekarang(direktori, pembuat)

    t = threading.Thread(target=buat_sekarang, args=(direktori, pembuat),
                         name='cadangan-harian', daemon=True)
    t.start()
    return t

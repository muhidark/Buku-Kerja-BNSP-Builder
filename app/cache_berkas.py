"""Cache kecil untuk pembacaan JSON yang diulang pada satu permintaan.

Halaman skema menghitung status setiap unit (T-18): fungsi seperti
`status_unit`, `peta_kelengkapan`, dan `muat_json_mesin` membaca berkas JSON
yang sama berkali-kali dalam satu render, sehingga jumlah pembacaan tumbuh
mengikuti jumlah unit x jumlah pemeriksaan (pola N+1).

Cache ini menyimpan hasil parse dengan kunci (path, mtime_ns, ukuran):
- Berkas yang berubah otomatis dianggap basi karena mtime/ukurannya berubah.
- Tidak ada masa berlaku waktu: perubahan berkas selalu terdeteksi.
- Nilai yang dikembalikan adalah SALINAN, sehingga pemanggil tidak bisa
  merusak isi cache tanpa sengaja.

Batasan yang disadari: cache hidup di memori proses. Aplikasi ini berjalan
sebagai satu proses uvicorn; bila nanti dijalankan multi-worker, setiap worker
punya cache sendiri (tetap benar, hanya tidak saling berbagi).
"""

from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

#: path (str) -> ((mtime_ns, ukuran), data)
_ISI: Dict[str, Tuple[Tuple[int, int], Any]] = {}
_LOCK = threading.Lock()
_STATISTIK = {'hit': 0, 'miss': 0, 'gagal': 0}

#: Batas jumlah entri agar tidak tumbuh tanpa batas pada pemakaian panjang.
BATAS_ENTRI = 512


def baca_json(path: str | Path) -> Optional[Any]:
    """Membaca JSON dengan cache. Mengembalikan None bila berkas tidak ada/rusak."""
    p = Path(path)
    try:
        st = p.stat()
    except OSError:
        return None

    kunci = str(p)
    jari = (st.st_mtime_ns, st.st_size)

    with _LOCK:
        entri = _ISI.get(kunci)
        if entri is not None and entri[0] == jari:
            _STATISTIK['hit'] += 1
            return copy.deepcopy(entri[1])

    try:
        data = json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        with _LOCK:
            _STATISTIK['gagal'] += 1
        return None

    with _LOCK:
        if len(_ISI) >= BATAS_ENTRI:
            _ISI.clear()
        _ISI[kunci] = (jari, data)
        _STATISTIK['miss'] += 1
    return copy.deepcopy(data)


def statistik() -> Dict[str, int]:
    """Hitungan pemakaian cache (untuk pengujian dan pemantauan)."""
    with _LOCK:
        hasil = dict(_STATISTIK)
    hasil['entri'] = len(_ISI)
    return hasil


def bersihkan() -> None:
    """Mengosongkan cache (dipakai pengujian)."""
    with _LOCK:
        _ISI.clear()
        for k in _STATISTIK:
            _STATISTIK[k] = 0

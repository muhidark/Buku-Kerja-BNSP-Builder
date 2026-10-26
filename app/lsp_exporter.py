"""
SKKNI Extractor - Modul Integrasi & Ekspor ke Plugin LSP WordPress.

Menyediakan konversi hasil ekstraksi unit dan skema menjadi:
1. Format JSON standar LSP (skkni_data array).
2. Format teks Smart Paste (kompatibel langsung dengan regex parser WordPress).
"""

import json
from pathlib import Path

from app import koreksi

ROOT = Path(__file__).resolve().parent.parent


def unit_ke_lsp_dict(data: dict) -> dict:
    """Konversi hasil ekstraksi unit JSON menjadi struktur dict plugin LSP."""
    kode = data.get('kode_unit') or ''
    judul = data.get('judul_unit') or ''
    deskripsi = data.get('deskripsi_unit') or ''

    elemen_list = []
    for idx, e in enumerate(data.get('elemen_kompetensi') or []):
        try:
            e_no = int(e.get('nomor_elemen') or (idx + 1))
        except (ValueError, TypeError):
            e_no = idx + 1

        e_nama = e.get('nama_elemen') or ''
        kuks = []
        for k in e.get('kuk') or []:
            k_no = str(k.get('nomor_kuk') or '').strip()
            k_ur = str(k.get('uraian_kuk') or '').strip()
            kuks.append(f"{k_no} {k_ur}".strip())

        elemen_list.append({
            'nomor': e_no,
            'nama': e_nama,
            'kuk': kuks
        })

    return {
        'kode_unit': kode,
        'judul_unit': judul,
        'deskripsi_unit': deskripsi,
        'elemen': elemen_list
    }


def unit_ke_smart_paste_text(data: dict) -> str:
    """Konversi hasil ekstraksi unit menjadi format teks untuk Smart Paste modal."""
    baris = []
    baris.append(f"KODE UNIT: {data.get('kode_unit') or ''}")
    judul = (data.get('judul_unit') or '').strip()
    if judul:
        baris.append(f"JUDUL UNIT: {judul}")

    deskripsi = (data.get('deskripsi_unit') or '').strip()
    if deskripsi:
        baris.append(f"DESKRIPSI UNIT: {deskripsi}")

    for idx, e in enumerate(data.get('elemen_kompetensi') or []):
        try:
            e_no = int(e.get('nomor_elemen') or (idx + 1))
        except (ValueError, TypeError):
            e_no = idx + 1
        e_nama = (e.get('nama_elemen') or '').strip()
        baris.append(f"{e_no}. {e_nama}")

        for k in e.get('kuk') or []:
            k_no = str(k.get('nomor_kuk') or '').strip()
            k_ur = str(k.get('uraian_kuk') or '').strip()
            baris.append(f"{k_no} {k_ur}".strip())

    return '\n'.join(baris)


def ambil_json_unit(kode_unit: str) -> dict | None:
    """Cari berkas JSON unit ekstraksi dan terapkan koreksi manual bila ada."""
    hasil_final = koreksi.ambil_unit_final(kode_unit)
    if hasil_final is not None:
        return hasil_final

    # Fallback pencarian di seluruh data/json (kecuali folder koreksi)
    for p in (ROOT / 'data' / 'json').rglob(f'{kode_unit}.json'):
        if p.is_file() and 'koreksi' not in p.parts:
            try:
                data_mesin = json.loads(p.read_text(encoding='utf-8'))
                return koreksi.terapkan_koreksi_ke_data(data_mesin, kode_unit)
            except Exception:
                continue
    return None


def skema_ke_lsp_data(skema_doc: dict) -> tuple[list[dict], str]:
    """
    Ekstrak seluruh unit yang sudah ada JSON-nya pada skema menjadi:
    - List dict struktur LSP JSON
    - String gabungan teks Smart Paste
    """
    units = skema_doc.get('units') or []
    lsp_list = []
    text_blocks = []

    for u in units:
        kode = u['kode_unit']
        data = ambil_json_unit(kode)
        if not data:
            continue
        lsp_dict = unit_ke_lsp_dict(data)
        lsp_list.append(lsp_dict)
        text_blocks.append(unit_ke_smart_paste_text(data))

    return lsp_list, '\n\n'.join(text_blocks)

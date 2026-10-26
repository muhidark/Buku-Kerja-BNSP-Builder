"""
SKKNI Extractor - Generator DOCX multi-unit (Fase 3C)

Menggabungkan beberapa unit kompetensi (dari SKKNI berbeda) ke dalam satu
dokumen Word, memakai kembali format dari `app/docx_generator.py`.

Setiap unit:
- dimulai pada halaman baru (page_break_before, tanpa paragraf kosong),
- memakai abstractNum + dua numId sendiri sehingga penomoran Batasan Variabel
  dan Panduan Penilaian dimulai dari 1 dan tidak berlanjut dari unit lain.

Contoh spesifikasi:
    {"units": [
        {"kode": "J.63OPR00.009.2", "skkni": "2018-056"},
        {"kode": "J.59MTM00.011.1", "skkni": "2018-107"},
        {"kode": "M.70MKT00.014.1", "skkni": "2022-124"}
    ]}
"""

import json
from app import penyimpanan
from pathlib import Path

from app import koreksi
from app.docx_generator import dokumen_baru, tambah_unit

DEFAULT_JSON_DIR = Path(__file__).resolve().parent.parent / 'data' / 'json' / 'cross_skkni'


def _muat_unit(item: dict, json_dir: Path) -> dict:
    """Ambil JSON unit berdasarkan kode (dan terapkan koreksi manual bila ada)."""
    kode = item['kode']
    if item.get('json'):
        path = Path(item['json'])
    else:
        path = json_dir / f'{kode}.json'
    if path.exists():
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return koreksi.terapkan_koreksi_ke_data(data, kode) or data
    unit_kor = koreksi.ambil_unit_final(kode)
    if unit_kor is not None:
        return unit_kor
    raise FileNotFoundError(f'JSON unit {kode} tidak ditemukan: {path}')


def generate_multi_docx(units: list[dict] | dict, output_path: str,
                        json_dir: str | Path = DEFAULT_JSON_DIR) -> dict:
    """
    Buat satu DOCX berisi beberapa unit sesuai urutan spesifikasi.

    Returns:
        dict: path, urutan kode, meta numbering tiap unit, total elemen/KUK
    """
    if isinstance(units, dict):
        units = units.get('units', [])

    json_dir = Path(json_dir)
    doc = dokumen_baru()
    metas = []
    total_elemen = total_kuk = 0

    for i, item in enumerate(units):
        unit = _muat_unit(item, json_dir)
        meta = tambah_unit(doc, unit, page_break_before=(i > 0))
        meta['skkni'] = item.get('skkni')
        meta['judul_unit'] = unit['judul_unit']
        meta['jumlah_elemen'] = len(unit['elemen_kompetensi'])
        meta['jumlah_kuk'] = sum(len(e['kuk']) for e in unit['elemen_kompetensi'])
        metas.append(meta)
        total_elemen += meta['jumlah_elemen']
        total_kuk += meta['jumlah_kuk']

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)

    return {
        'docx_path': str(output_path),
        'jumlah_unit': len(metas),
        'urutan_kode': [m['kode_unit'] for m in metas],
        'total_elemen': total_elemen,
        'total_kuk': total_kuk,
        'unit': metas,
    }


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print('Penggunaan: python -m app.multi_docx_generator <spec.json> [output.docx]')
        sys.exit(1)

    spec = penyimpanan.baca_json(Path(sys.argv[1]))
    if spec is None:
        print('Berkas spesifikasi tidak dapat dibaca sebagai JSON.')
        sys.exit(1)
    out = sys.argv[2] if len(sys.argv) > 2 else 'output/multi_unit_test.docx'
    info = generate_multi_docx(spec, out)
    print(f"DOCX: {info['docx_path']}")
    print(f"Unit: {info['jumlah_unit']} -> {', '.join(info['urutan_kode'])}")
    print(f"Elemen: {info['total_elemen']} | KUK: {info['total_kuk']}")

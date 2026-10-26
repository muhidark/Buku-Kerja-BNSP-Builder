"""Ekspor satu skema (hasil parsing DOCX) menjadi SATU berkas JSON untuk plugin LSP.

Alur: schema JSON (units: kode_unit) -> cari JSON ekstraksi tiap unit -> gabung
menjadi array `skkni_data` siap unggah ke halaman LSP Core > Migrasi SKKNI.

Pemakaian:
    source .venv/bin/activate
    python -m tools.ekspor_skema_lsp data/json/schema_content_creator.json
    python -m tools.ekspor_skema_lsp <schema.json> --out output/lsp/nama.json

Keluar dengan kode 1 bila ada unit yang belum punya JSON ekstraksi, agar tidak
diam-diam menghasilkan berkas tidak lengkap.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import lsp_exporter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('schema', help='Berkas JSON hasil parsing skema (punya kunci "units")')
    parser.add_argument('--out', help='Berkas keluaran (default: output/lsp/<nama-schema>.json)')
    parser.add_argument('--ringkas', action='store_true', help='Hanya cetak ringkasan, tanpa menulis berkas')
    args = parser.parse_args()

    schema_path = Path(args.schema)
    if not schema_path.is_absolute():
        schema_path = (ROOT / schema_path).resolve()

    if not schema_path.is_file():
        print(f'GAGAL: berkas skema tidak ditemukan: {schema_path}')
        return 2

    try:
        schema_doc = json.loads(schema_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        print(f'GAGAL: JSON skema tidak valid: {exc}')
        return 2

    units = schema_doc.get('units') or []
    if not units:
        print('GAGAL: skema tidak punya daftar unit ("units" kosong).')
        return 2

    lsp_list, _smart_paste = lsp_exporter.skema_ke_lsp_data(schema_doc)

    ditemukan = {u['kode_unit'] for u in lsp_list}
    semua_kode = [u.get('kode_unit', '') for u in units]
    hilang = [k for k in semua_kode if k not in ditemukan]

    n_elemen = sum(len(u['elemen']) for u in lsp_list)
    n_kuk = sum(len(e['kuk']) for u in lsp_list for e in u['elemen'])

    print(f'Skema      : {schema_path.name}')
    print(f'Unit skema : {len(semua_kode)}')
    print(f'Unit siap  : {len(lsp_list)}  (elemen {n_elemen}, KUK {n_kuk})')
    if hilang:
        print(f'Unit belum ada JSON ekstraksi: {len(hilang)}')
        for kode in hilang:
            print(f'  - {kode}')

    if args.ringkas:
        return 1 if hilang else 0

    out_path = Path(args.out) if args.out else ROOT / 'output' / 'lsp' / (schema_path.stem + '.lsp.json')
    if not out_path.is_absolute():
        out_path = (ROOT / out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not lsp_list:
        print('GAGAL: tidak ada unit yang bisa diekspor.')
        return 1

    out_path.write_text(json.dumps(lsp_list, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'Berkas     : {out_path}')
    print(f'Ukuran     : {out_path.stat().st_size:,} byte')

    if hilang:
        print('\nPERINGATAN: berkas ini belum memuat seluruh unit skema.')
        print('Lengkapi ekstraksi unit di atas, lalu jalankan ulang perintah ini.')
        return 1

    print('\nLengkap. Unggah berkas ini di: LSP Core > Migrasi SKKNI (pilih skema yang sama).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

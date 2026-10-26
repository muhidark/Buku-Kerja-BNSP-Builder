"""
Pengujian mesin identifikasi unit kompetensi SKKNI.
Menggunakan PDF: SKKNI 2023-101.pdf.pdf (Bidang Periklanan)
"""

import sys
import json
from pathlib import Path

# Tambahkan root proyek ke path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.extractor import identify_units, save_results, print_summary


def main():
    pdf_path = project_root / 'data' / 'pdf' / 'SKKNI 2023-101.pdf.pdf'
    output_path = project_root / 'data' / 'json' / 'hasil_identifikasi.json'
    
    if not pdf_path.exists():
        print(f"ERROR: File PDF tidak ditemukan: {pdf_path}")
        sys.exit(1)
    
    print("=" * 100)
    print("PENGUJIAN MESIN IDENTIFIKASI UNIT KOMPETENSI SKKNI")
    print("=" * 100)
    print()
    
    # Jalankan identifikasi
    units = identify_units(str(pdf_path))
    
    # Simpan hasil
    result = save_results(str(pdf_path), units, str(output_path))
    
    # Cetak ringkasan
    print_summary(result)
    
    print()
    print("=" * 100)
    print(f"Hasil JSON disimpan ke: {output_path}")
    print("=" * 100)
    
    # Verifikasi dasar
    print()
    print("VERIFIKASI:")
    print(f"  - Total unit ditemukan: {len(units)}")
    
    titles_missing = [u for u in units if u['status'] == 'title_missing']
    print(f"  - Unit tanpa judul  : {len(titles_missing)}")
    
    if titles_missing:
        print("  Unit tanpa judul:")
        for u in titles_missing:
            print(f"    - {u['code']} (halaman {u['start_page']})")
    
    # Cek duplikasi kode
    codes = [u['code'] for u in units]
    duplicates = [c for c in codes if codes.count(c) > 1]
    if duplicates:
        print(f"  - PERINGATAN: Ada duplikasi kode: {set(duplicates)}")
    else:
        print(f"  - Tidak ada duplikasi kode ✓")
    
    # Tampilkan 5 unit pertama sebagai sampel
    print()
    print("SAMPEL 5 UNIT PERTAMA (detail dari JSON):")
    with open(output_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    for u in data['units'][:5]:
        print(f"  {u['code']} | hal {u['start_page']}-{u['end_page']} | {u['title']}")




def test_extractor():
    assert main() == 0


if __name__ == '__main__':
    main()

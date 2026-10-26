"""
Pengujian parser unit kompetensi (Fase 2A).
Mengekstrak unit M.73ADV00.001.1 dari SKKNI 2023-101.pdf.pdf
"""

import sys
import json
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.unit_parser import parse_unit, save_unit_json, print_unit_summary


def main():
    pdf_path = project_root / 'data' / 'pdf' / 'SKKNI 2023-101.pdf.pdf'
    output_path = project_root / 'data' / 'json' / 'test_unit_001.json'
    
    # Ambil rentang halaman dari hasil Fase 1
    fase1_path = project_root / 'data' / 'json' / 'hasil_identifikasi.json'
    
    if not fase1_path.exists():
        print(f"ERROR: Hasil Fase 1 tidak ditemukan: {fase1_path}")
        print("Jalankan tests/test_extractor.py terlebih dahulu.")
        sys.exit(1)
    
    with open(fase1_path, 'r', encoding='utf-8') as f:
        fase1_data = json.load(f)
    
    # Cari unit M.73ADV00.001.1
    target_code = 'M.73ADV00.001.1'
    target_unit = None
    for u in fase1_data['units']:
        if u['code'] == target_code:
            target_unit = u
            break
    
    if not target_unit:
        print(f"ERROR: Unit {target_code} tidak ditemukan di hasil Fase 1")
        sys.exit(1)
    
    start_page = target_unit['start_page']
    end_page = target_unit['end_page']
    
    print("=" * 100)
    print("PENGUJIAN PARSER UNIT KOMPETENSI (FASE 2A)")
    print("=" * 100)
    print(f"\nFile PDF       : {pdf_path.name}")
    print(f"Kode Unit      : {target_code}")
    print(f"Judul (Fase 1) : {target_unit['title']}")
    print(f"Rentang Halaman: {start_page} - {end_page} (indeks PDF 0-based)")
    print()
    print("-" * 100)
    
    # Parse unit
    unit_data = parse_unit(str(pdf_path), target_code, start_page, end_page)
    
    # Simpan hasil
    save_unit_json(unit_data, str(output_path))
    
    # Cetak ringkasan
    print_unit_summary(unit_data)
    
    print()
    print("-" * 100)
    print(f"\nHasil disimpan ke: {output_path}")
    
    # Verifikasi detail
    print("\n" + "=" * 100)
    print("VERIFIKASI DETAIL")
    print("=" * 100)
    
    # Cek identitas
    print(f"\nIdentitas:")
    print(f"  Kode unit cocok     : {'✓' if unit_data['kode_unit'] == target_code else '✗'}")
    print(f"  Judul ditemukan     : {'✓' if unit_data['judul_unit'] else '✗'}")
    print(f"  Deskripsi ditemukan : {'✓' if unit_data['deskripsi_unit'] else '✗'}")
    
    # Cek elemen
    print(f"\nElemen Kompetensi:")
    for elem in unit_data['elemen_kompetensi']:
        print(f"  {elem['nomor_elemen']}. {elem['nama_elemen']}")
        print(f"     Jumlah KUK: {len(elem['kuk'])}")
    
    # Cek total KUK
    total_kuk = sum(len(e['kuk']) for e in unit_data['elemen_kompetensi'])
    print(f"\nTotal KUK: {total_kuk}")
    
    # Tampilkan semua KUK lengkap
    print("\n" + "-" * 100)
    print("DAFTAR LENGKAP KUK:")
    print("-" * 100)
    for elem in unit_data['elemen_kompetensi']:
        print(f"\nElemen {elem['nomor_elemen']}: {elem['nama_elemen']}")
        for kuk in elem['kuk']:
            print(f"  {kuk['nomor_kuk']} [hal {kuk['halaman_pdf']}]:")
            print(f"    {kuk['uraian_kuk']}")


if __name__ == '__main__':
    main()

"""
SKKNI Extractor - Mesin Identifikasi Unit Kompetensi

Modul ini mengidentifikasi unit kompetensi dari dokumen PDF SKKNI:
- Mendeteksi kode unit dengan regex
- Membedakan halaman uraian unit vs halaman daftar
- Mengekstrak judul unit
- Menentukan halaman awal dan akhir setiap unit
"""

import re
import json
from pathlib import Path
from typing import Optional

try:
    import pymupdf as fitz
except ImportError:
    import fitz


# Pola kode unit SKKNI:
# 1. Format modern: huruf.2-digit-huruf(2-3).2-digit.3-digit.1-digit (e.g. J.63OPR00.009.2)
# 2. Format lama (2004-2010): 3-huruf.2-huruf.2-digit.3-digit.2-digit (e.g. TIK.MM01.001.01)
UNIT_CODE_PATTERN = re.compile(r'(?:[A-Z]\.\d{2}[A-Z]{2,3}\d{2}\.\d{3}\.\d|[A-Z]{3}\.[A-Z]{2}\d{2}\.\d{3}\.\d{2})')


def is_unit_description_page(text: str) -> tuple[bool, Optional[str]]:
    """
    Cek apakah sebuah halaman adalah halaman uraian unit (bukan daftar).
    
    Ciri halaman uraian unit:
    - Hanya memuat 1 kode unit
    - Memiliki label "KODE UNIT" diikuti kode
    
    Returns:
        (bool, kode_unit atau None)
    """
    matches = UNIT_CODE_PATTERN.findall(text)
    
    # Halaman dengan banyak kode = daftar, bukan uraian
    if len(matches) != 1:
        return False, None
    
    # Konfirmasi ada label "KODE UNIT" di dekat kode tersebut
    if re.search(r'KODE\s+UNIT', text):
        return True, matches[0]
    
    return False, None


def extract_unit_title(text: str) -> Optional[str]:
    """
    Ekstrak judul unit dari teks halaman uraian unit.
    
    Pola: "JUDUL UNIT" diikuti ":" lalu judul di baris berikutnya.
    Judul bisa multi-baris, berakhir sebelum "DESKRIPSI UNIT".
    """
    # Cari pola JUDUL UNIT : <judul>. Label dibuat toleran karena sebagian
    # PDF salah ketik (mis. "JUDUL UNI" pada SKKNI 2018-107).
    match = re.search(
        r'JUDUL\s+UNI(?:T)?\s*:\s*\n?(.+?)(?=\n\s*DESKRIPSI\s+UNIT)',
        text,
        re.DOTALL | re.IGNORECASE
    )
    
    if not match:
        return None
    
    title_raw = match.group(1)
    # Bersihkan: ganti newline+spasi berlebih dengan spasi tunggal
    title = re.sub(r'\s+', ' ', title_raw).strip()
    
    return title if title else None


def identify_units(pdf_path: str) -> list[dict]:
    """
    Identifikasi semua unit kompetensi dalam PDF SKKNI.
    
    Returns:
        List of dict dengan keys:
        - code: kode unit
        - title: judul unit (atau None jika tidak ditemukan)
        - start_page: indeks halaman awal (0-based)
        - end_page: indeks halaman akhir (0-based, inklusif)
        - status: 'ok' | 'title_missing'
    """
    doc = fitz.open(pdf_path)
    page_count = doc.page_count
    
    # Kumpulkan semua halaman uraian unit
    unit_pages = []  # list of (page_index, code, title)
    
    for page_idx in range(page_count):
        text = doc[page_idx].get_text()
        is_desc, code = is_unit_description_page(text)
        
        if is_desc and code:
            title = extract_unit_title(text)
            unit_pages.append({
                'page_index': page_idx,
                'code': code,
                'title': title,
                'status': 'ok' if title else 'title_missing'
            })
    
    doc.close()
    
    # Hitung halaman akhir: halaman sebelum unit berikutnya, atau halaman terakhir
    units = []
    for i, unit in enumerate(unit_pages):
        if i + 1 < len(unit_pages):
            end_page = unit_pages[i + 1]['page_index'] - 1
        else:
            end_page = page_count - 1
        
        units.append({
            'code': unit['code'],
            'title': unit['title'],
            'start_page': unit['page_index'],
            'end_page': end_page,
            'status': unit['status']
        })
    
    return units


def save_results(pdf_path: str, units: list[dict], output_path: str) -> dict:
    """
    Simpan hasil identifikasi ke JSON dan kembalikan ringkasan.
    """
    doc = fitz.open(pdf_path)
    page_count = doc.page_count
    doc.close()
    
    result = {
        'source_file': Path(pdf_path).name,
        'pdf_page_count': page_count,
        'total_units_found': len(units),
        'units': units
    }
    
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    return result


def print_summary(result: dict) -> None:
    """Cetak ringkasan hasil identifikasi."""
    print(f"File PDF       : {result['source_file']}")
    print(f"Jumlah halaman : {result['pdf_page_count']}")
    print(f"Unit ditemukan : {result['total_units_found']}")
    print()
    print(f"{'No':<4} {'Kode Unit':<20} {'Halaman':<10} {'Status':<15} Judul")
    print("-" * 100)
    
    for i, unit in enumerate(result['units'], 1):
        pages = f"{unit['start_page']}-{unit['end_page']}"
        title = unit['title'] or '[JUDUL TIDAK DITEMUKAN]'
        # Potong judul jika terlalu panjang
        if len(title) > 50:
            title = title[:47] + '...'
        print(f"{i:<4} {unit['code']:<20} {pages:<10} {unit['status']:<15} {title}")


if __name__ == '__main__':
    # Jalankan langsung untuk pengujian cepat
    import sys
    
    if len(sys.argv) < 2:
        print("Penggunaan: python extractor.py <path_pdf> [path_output_json]")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else 'data/json/hasil_identifikasi.json'
    
    units = identify_units(pdf_path)
    result = save_results(pdf_path, units, output_path)
    print_summary(result)
    print(f"\nHasil disimpan ke: {output_path}")

"""
SKKNI Extractor - Pencocokan unit skema ke PDF SKKNI (Fase 3D)

Mencocokkan kode unit dari dokumen skema dengan indeks unit pada PDF SKKNI
secara PERSIS (bukan kemiripan judul).
"""

from pathlib import Path

from app.extractor import identify_units


def indeks_pdf(pdf_paths: list[str | Path]) -> dict:
    """
    Bangun indeks kode unit -> lokasi PDF/halaman.

    Returns:
        dict: {
          'index': {kode: [entri, ...]},
          'dokumen': {nama_pdf: jumlah_unit},
          'galat': [{'pdf':..., 'pesan':...}]
        }
    """
    index: dict[str, list[dict]] = {}
    dokumen = {}
    galat = []

    for path in pdf_paths:
        path = Path(path)
        try:
            units = identify_units(str(path))
        except Exception as e:  # file rusak / bukan PDF
            galat.append({'pdf': path.name, 'pesan': f'{type(e).__name__}: {e}'})
            continue

        dokumen[path.name] = len(units)
        for u in units:
            index.setdefault(u['code'], []).append({
                'pdf': path.name,
                'start_page': u['start_page'],
                'end_page': u['end_page'],
                'judul_pdf': u.get('title'),
                'status_identifikasi': u.get('status'),
            })

    return {'index': index, 'dokumen': dokumen, 'galat': galat}


def cocokkan(units_skema: list[dict], pdf_paths: list[str | Path],
             indeks: dict | None = None) -> dict:
    """
    Cocokkan daftar unit skema ke PDF.

    Returns:
        dict: units[], tidak_ditemukan[], konflik[], statistik
    """
    idx = indeks or indeks_pdf(pdf_paths)
    index = idx['index']

    hasil = []
    tidak_ditemukan = []
    konflik = []

    for u in units_skema:
        kode = u['kode_unit']
        kandidat = index.get(kode, [])

        entri = {
            'nomor_urut': u.get('nomor_urut'),
            'kode_unit': kode,
            'judul_skema': u.get('judul_skema', ''),
            'jumlah_kandidat': len(kandidat),
            'status': 'ditemukan',
            'pdf': None, 'start_page': None, 'end_page': None,
            'judul_pdf': None,
            'catatan': list(u.get('catatan', [])),
        }

        if not kandidat:
            entri['status'] = 'tidak_ditemukan'
            tidak_ditemukan.append(kode)
            entri['catatan'].append('kode tidak ditemukan pada PDF SKKNI yang tersedia')
        elif len(kandidat) > 1:
            entri['status'] = 'konflik'
            konflik.append({'kode_unit': kode, 'kandidat': kandidat})
            entri['catatan'].append('kode ditemukan di lebih dari satu dokumen; verifikasi manual')
            # tetap catat kandidat pertama untuk audit, tidak dipakai otomatis
            entri.update({k: kandidat[0][k] for k in
                          ('pdf', 'start_page', 'end_page', 'judul_pdf')})
        else:
            entri.update({k: kandidat[0][k] for k in
                          ('pdf', 'start_page', 'end_page', 'judul_pdf')})

        hasil.append(entri)

    return {
        'units': hasil,
        'tidak_ditemukan': tidak_ditemukan,
        'konflik': konflik,
        'statistik': {
            'jumlah_skema': len(units_skema),
            'ditemukan': sum(1 for x in hasil if x['status'] == 'ditemukan'),
            'tidak_ditemukan': len(tidak_ditemukan),
            'konflik': len(konflik),
            'dokumen': idx['dokumen'],
            'galat_pdf': idx['galat'],
        },
    }


if __name__ == '__main__':
    import json
    import sys

    skema_path = sys.argv[1] if len(sys.argv) > 1 else 'data/json/schema_content_creator.json'
    pdfs = sys.argv[2:] or [
        'data/pdf/SKKNI 2018-056.pdf.pdf',
        'data/pdf/SKKNI 2018-107.pdf.pdf',
        'data/pdf/SKKNI 2022-124.pdf.pdf',
    ]
    skema = json.loads(Path(skema_path).read_text(encoding='utf-8'))
    hasil = cocokkan(skema['units'], pdfs)
    for x in hasil['units']:
        lokasi = f"{x['pdf']} hal {x['start_page']}-{x['end_page']}" if x['pdf'] else '-'
        print(f"{x['nomor_urut']:2}. {x['kode_unit']:<20} {x['status']:<15} {lokasi}")
    print('statistik:', hasil['statistik'])

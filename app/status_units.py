"""
Sumber kebenaran tunggal untuk status kesiapan unit kompetensi (Fase 4F).

Tiga status resmi:
- ``siap``  ("Siap dipakai", hijau)    -> Boleh masuk dokumen.
- ``perlu`` ("Perlu diperiksa", amber) -> Ditahan sampai dikoreksi/diverifikasi.
- ``gagal`` ("Gagal", merah)           -> Tidak boleh masuk dokumen.
"""

from __future__ import annotations

from pathlib import Path
from app import koreksi, library, schema_library

LABEL_STATUS = {
    'siap': 'Siap dipakai',
    'perlu': 'Perlu diperiksa',
    'gagal': 'Gagal',
}

WARNA_STATUS = {
    'siap': 'green',
    'perlu': 'amber',
    'gagal': 'red',
}


def _bersihkan_catatan(daftar_catatan: list[str] | None) -> str:
    if not daftar_catatan:
        return ''
    kalimat: list[str] = []
    for item in daftar_catatan:
        teks = str(item or '').strip()
        if not teks:
            continue
        teks = (
            teks.replace('valid_struktur', 'struktur lengkap')
            .replace('perlu_verifikasi', 'perlu diperiksa')
            .replace('gagal_ekstraksi', 'gagal diekstrak')
            .replace('tidak_dapat_dibandingkan', 'belum dapat dibandingkan otomatis')
            .replace('valid_kelengkapan', 'kelengkapan KUK sesuai')
        )
        if teks not in kalimat:
            kalimat.append(teks)
    return '; '.join(kalimat)


def _indeks_unit_skkni() -> dict[str, dict]:
    """Bangun peta kode_unit -> info dokumen SKKNI & kelengkapan KUK dari perpustakaan."""
    peta: dict[str, dict] = {}
    try:
        for d in library.daftar_dokumen():
            doc_id = d.get('id')
            nama_asli = d.get('nama_asli') or ''
            nama_internal = Path(d.get('nama_internal') or '').name
            kel_map = ((d.get('validasi_kelengkapan') or {}).get('unit') or {})
            ver_map = d.get('verifikasi_manual') or {}
            for u in d.get('units') or []:
                kode = (u.get('kode_unit') or '').strip()
                if not kode or kode in peta:
                    continue
                h0 = u.get('halaman_pdf_0based')
                h1 = u.get('halaman_akhir_0based')
                hal_awal = u.get('halaman_tampil') or (h0 + 1 if isinstance(h0, int) else None)
                hal_akhir = (h1 + 1) if isinstance(h1, int) else None
                peta[kode] = {
                    'skkni_id': doc_id,
                    'nama_skkni': nama_asli,
                    'nama_internal': nama_internal,
                    'halaman_awal': hal_awal,
                    'halaman_akhir': hal_akhir,
                    'judul_unit': u.get('judul_unit'),
                    'validasi_kelengkapan': kel_map.get(kode),
                    'verifikasi_manual_skkni': ver_map.get(kode),
                }
    except Exception:
        pass
    return peta


def cari_info_halaman_pdf(
    kode_unit: str,
    data_unit: dict | None = None,
    hasil_cocok: dict | None = None,
    indeks_skkni: dict[str, dict] | None = None,
) -> dict:
    """Temukan nomor halaman PDF (1-based) dan ``skkni_id`` untuk kode unit."""
    hal_awal = None
    hal_akhir = None
    skkni_id = None
    nama_skkni = None

    if hasil_cocok and isinstance(hasil_cocok, dict):
        if isinstance(hasil_cocok.get('halaman_awal'), int):
            hal_awal = hasil_cocok['halaman_awal']
        elif isinstance(hasil_cocok.get('start_page'), int):
            hal_awal = hasil_cocok['start_page'] + 1
        if isinstance(hasil_cocok.get('halaman_akhir'), int):
            hal_akhir = hasil_cocok['halaman_akhir']
        elif isinstance(hasil_cocok.get('end_page'), int):
            hal_akhir = hasil_cocok['end_page'] + 1
        skkni_id = hasil_cocok.get('skkni_id')
        nama_skkni = hasil_cocok.get('nama_skkni') or hasil_cocok.get('pdf')

    if data_unit and isinstance(data_unit, dict):
        if hal_awal is None:
            h0 = data_unit.get('halaman_awal_0based')
            if isinstance(h0, int):
                hal_awal = h0 + 1
            elif isinstance(data_unit.get('halaman_awal'), int):
                hal_awal = data_unit.get('halaman_awal')
        if hal_akhir is None:
            h1 = data_unit.get('halaman_akhir_0based')
            if isinstance(h1, int):
                hal_akhir = h1 + 1
            elif isinstance(data_unit.get('halaman_akhir'), int):
                hal_akhir = data_unit.get('halaman_akhir')

    peta = indeks_skkni if indeks_skkni is not None else _indeks_unit_skkni()
    entri = peta.get((kode_unit or '').strip()) or {}
    if not skkni_id:
        skkni_id = entri.get('skkni_id')
    if not nama_skkni:
        nama_skkni = entri.get('nama_skkni')
    if hal_awal is None:
        hal_awal = entri.get('halaman_awal')
    if hal_akhir is None:
        hal_akhir = entri.get('halaman_akhir')

    return {
        'halaman_awal': hal_awal,
        'halaman_akhir': hal_akhir,
        'skkni_id': skkni_id,
        'nama_skkni': nama_skkni,
    }


def status_unit(
    kode_unit: str,
    data: dict | None = None,
    info_koreksi: dict | None = None,
    verifikasi_manual: dict | bool | None = None,
    hasil_cocok: dict | None = None,
    wajib_json: bool = True,
    indeks_skkni: dict[str, dict] | None = None,
) -> dict:
    """Hitung status 3-tingkat (``siap``, ``perlu``, ``gagal``) untuk satu unit."""
    kode = (kode_unit or '').strip()
    peta_skkni = indeks_skkni if indeks_skkni is not None else _indeks_unit_skkni()
    entri_skkni = peta_skkni.get(kode) or {}

    if data is None and kode:
        data = koreksi.ambil_unit_final(kode)

    if info_koreksi is None and kode:
        info_koreksi = (data or {}).get('_koreksi') or koreksi.status_koreksi(kode)

    if verifikasi_manual is None and entri_skkni.get('verifikasi_manual_skkni'):
        verifikasi_manual = entri_skkni['verifikasi_manual_skkni']

    ada_koreksi = bool((info_koreksi or {}).get('ada_koreksi'))
    konflik_koreksi = bool((info_koreksi or {}).get('konflik'))
    dikoreksi_pada = (info_koreksi or {}).get('dikoreksi_pada')
    oleh_koreksi = (info_koreksi or {}).get('oleh')

    elemen = (data or {}).get('elemen_kompetensi') or []
    elemen_count = len(elemen)
    kuk_count = sum(len(el.get('kuk') or []) for el in elemen)

    info_pdf = cari_info_halaman_pdf(kode, data, hasil_cocok, indeks_skkni=peta_skkni)
    judul = (
        (data or {}).get('judul_unit')
        or (hasil_cocok or {}).get('judul_pdf')
        or (hasil_cocok or {}).get('judul_skkni')
        or (hasil_cocok or {}).get('judul_skema')
        or entri_skkni.get('judul_unit')
        or ''
    )

    def _bungkus(
        st: str,
        alasan: str,
        sumber: str,
    ) -> dict:
        return {
            'kode_unit': kode,
            'judul_unit': judul,
            'status': st,
            'label': LABEL_STATUS[st],
            'warna': WARNA_STATUS[st],
            'boleh_dokumen': st == 'siap',
            'alasan': alasan,
            'sumber': sumber,
            'ada_koreksi': ada_koreksi,
            'konflik_koreksi': konflik_koreksi,
            'dikoreksi_pada': dikoreksi_pada,
            'oleh_koreksi': oleh_koreksi,
            'elemen_count': elemen_count,
            'kuk_count': kuk_count,
            'halaman_awal': info_pdf['halaman_awal'],
            'halaman_akhir': info_pdf['halaman_akhir'],
            'skkni_id': info_pdf['skkni_id'],
            'nama_skkni': info_pdf['nama_skkni'],
        }

    # 1. Periksa koreksi manual terlebih dahulu
    if ada_koreksi:
        if konflik_koreksi:
            return _bungkus(
                'perlu',
                'Hasil mesin berubah sejak dikoreksi — pilih pertahankan koreksi atau pakai hasil mesin baru',
                'konflik_koreksi',
            )
        if elemen_count > 0 and kuk_count > 0:
            return _bungkus(
                'siap',
                'Dikoreksi manual',
                'koreksi_manual',
            )
        return _bungkus(
            'gagal',
            'Koreksi manual belum memiliki elemen atau KUK',
            'koreksi_manual',
        )

    # 2. Periksa status pencocokan skema bila ada
    st_cocok = (hasil_cocok or {}).get('status')
    if st_cocok in ('belum_ditemukan', 'tidak_ditemukan') and data is None:
        return _bungkus(
            'gagal',
            'Kode unit tidak ditemukan pada PDF SKKNI di perpustakaan',
            'belum_ditemukan',
        )
    if st_cocok == 'konflik':
        return _bungkus(
            'perlu',
            'Kode unit ditemukan di lebih dari satu PDF SKKNI',
            'konflik_skkni',
        )

    # 3. Belum ada berkas ekstraksi
    if data is None:
        if wajib_json:
            return _bungkus(
                'gagal',
                'Unit belum diekstrak dari PDF SKKNI',
                'belum_diekstrak',
            )
        return _bungkus(
            'perlu',
            'Belum diekstrak ke JSON',
            'belum_diekstrak',
        )

    # 4. Evaluasi hasil ekstraksi mesin
    val = data.get('validasi') or {}
    kel = data.get('validasi_kelengkapan') or entri_skkni.get('validasi_kelengkapan') or {}
    st_val = val.get('status') or ''
    st_kel = kel.get('status') or ''
    kuk_hilang = kel.get('kuk_hilang') or []

    if elemen_count == 0 or kuk_count == 0 or st_val == 'gagal_ekstraksi':
        catatan_gagal = _bersihkan_catatan(val.get('catatan'))
        alasan_gagal = 'Elemen dan KUK tidak terbaca dari PDF'
        if catatan_gagal:
            alasan_gagal = f'Elemen dan KUK tidak terbaca dari PDF ({catatan_gagal})'
        return _bungkus('gagal', alasan_gagal, 'hasil_mesin')

    if kuk_hilang:
        daftar_hilang = ', '.join(str(x) for x in kuk_hilang)
        return _bungkus(
            'perlu',
            f'Nomor KUK terlewat/hilang: {daftar_hilang}',
            'hasil_mesin',
        )

    if verifikasi_manual:
        return _bungkus(
            'siap',
            'Terverifikasi manual',
            'verifikasi_manual',
        )

    if st_val == 'valid_struktur' and st_kel in ('valid_kelengkapan', ''):
        return _bungkus(
            'siap',
            'KUK lengkap & tervalidasi',
            'hasil_mesin',
        )

    catatan_gabung = _bersihkan_catatan(
        (val.get('catatan') or []) + (kel.get('catatan') or [])
    )
    if not catatan_gabung:
        if st_val == 'perlu_verifikasi':
            catatan_gabung = 'Bagian Batasan Variabel atau Panduan Penilaian perlu diperiksa terhadap PDF'
        elif st_kel == 'tidak_dapat_dibandingkan':
            catatan_gabung = 'Tata letak tabel di PDF memerlukan pemeriksaan kelengkapan KUK'
        else:
            catatan_gabung = 'Perlu pemeriksaan kesesuaian dengan PDF SKKNI'

    return _bungkus('perlu', catatan_gabung, 'hasil_mesin')


def evaluasi_gerbang_skema(
    schema_id: str,
    kode_terpilih: list[str] | None = None,
) -> dict:
    """Evaluasi kesiapan seluruh (atau sebagian) unit dalam skema untuk Gerbang Dokumen."""
    skema = schema_library.ambil_skema(schema_id)
    if not skema:
        raise ValueError(f'Skema tidak ditemukan: {schema_id}')

    unit_skema = skema.get('units') or skema.get('unit_kompetensi') or []
    pencocokan_raw = (skema.get('hasil_pencocokan') or {}).get('units') or {}
    if isinstance(pencocokan_raw, dict):
        peta_cocok = pencocokan_raw
    else:
        peta_cocok = {
            u.get('kode_unit'): u
            for u in pencocokan_raw
            if isinstance(u, dict) and u.get('kode_unit')
        }
    verifikasi_map = skema.get('verifikasi_manual') or {}
    indeks_skkni = _indeks_unit_skkni()

    if kode_terpilih is not None:
        set_pilih = {k.strip() for k in kode_terpilih if k and k.strip()}
        daftar_target = [u for u in unit_skema if u.get('kode_unit') in set_pilih]
    else:
        daftar_target = list(unit_skema)

    daftar_unit: list[dict] = []
    penahan: list[dict] = []
    peta_unit: dict[str, dict] = {}
    ringkasan = {'total': len(daftar_target), 'siap': 0, 'perlu': 0, 'gagal': 0}

    for idx, item in enumerate(daftar_target, start=1):
        kode = (item.get('kode_unit') or '').strip()
        if not kode:
            continue
        cocok = peta_cocok.get(kode)
        ver_manual = verifikasi_map.get(kode)
        st = status_unit(
            kode,
            verifikasi_manual=ver_manual,
            hasil_cocok=cocok,
            wajib_json=True,
            indeks_skkni=indeks_skkni,
        )
        if not st.get('judul_unit'):
            st['judul_unit'] = item.get('judul_skema') or item.get('judul_unit') or ''
        st['no'] = item.get('nomor_urut') or item.get('no') or idx

        ringkasan[st['status']] = ringkasan.get(st['status'], 0) + 1
        daftar_unit.append(st)
        peta_unit[kode] = st
        if st['status'] in ('perlu', 'gagal'):
            penahan.append(st)

    siap_semua = (
        len(daftar_unit) > 0
        and ringkasan['gagal'] == 0
        and ringkasan['perlu'] == 0
    )

    return {
        'schema_id': schema_id,
        'judul_skema': skema.get('nama_skema') or skema.get('judul_skema') or skema.get('nama_asli') or '',
        'siap_semua': siap_semua,
        'ada_gagal': ringkasan['gagal'] > 0,
        'ada_perlu': ringkasan['perlu'] > 0,
        'ringkasan': ringkasan,
        'penahan': penahan,
        'daftar_unit': daftar_unit,
        'peta_unit': peta_unit,
    }

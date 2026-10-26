"""
Pengelolaan koreksi manual unit kompetensi per unit (Fase 4F).

Koreksi disimpan terpisah di ``data/json/koreksi/{kode_unit}.json``
tanpa menimpa berkas ekstraksi mesin di ``browser_extraction/``,
``schema_content_creator/``, atau ``cross_skkni/``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from app import cache_berkas

ROOT = Path(__file__).resolve().parent.parent
JSON_DIR = ROOT / 'data' / 'json'
KOREKSI_DIR = JSON_DIR / 'koreksi'

SUMBER_MESIN_DIRS = [
    JSON_DIR / 'browser_extraction',
    JSON_DIR / 'schema_content_creator',
    JSON_DIR / 'cross_skkni',
]

_POLA_KODE_AMAN = re.compile(r'^[A-Za-z0-9._-]+$')


def _validasi_kode_unit(kode_unit: str) -> str:
    kode = (kode_unit or '').strip()
    if not kode or not _POLA_KODE_AMAN.match(kode) or '..' in kode:
        raise ValueError(f'Kode unit tidak sah: {kode_unit!r}')
    return kode


def path_koreksi(kode_unit: str) -> Path:
    """Kembalikan path berkas koreksi untuk kode unit."""
    kode = _validasi_kode_unit(kode_unit)
    KOREKSI_DIR.mkdir(parents=True, exist_ok=True)
    return KOREKSI_DIR / f'{kode}.json'


def cari_berkas_mesin(kode_unit: str) -> Path | None:
    """Cari berkas JSON hasil ekstraksi mesin untuk kode unit."""
    kode = _validasi_kode_unit(kode_unit)
    for folder in SUMBER_MESIN_DIRS:
        jalur = folder / f'{kode}.json'
        if jalur.is_file():
            return jalur
    return None


def muat_json_mesin(kode_unit: str) -> dict | None:
    """Muat dict JSON hasil mesin asli tanpa campuran koreksi."""
    jalur = cari_berkas_mesin(kode_unit)
    if not jalur:
        return None
    return cache_berkas.baca_json(jalur)


def hitung_hash_berkas(jalur: Path | None) -> str:
    """Hitung SHA-256 dari berkas hasil mesin (kosong bila belum ada berkas)."""
    if not jalur or not jalur.is_file():
        return ''
    return hashlib.sha256(jalur.read_bytes()).hexdigest()


def hitung_hash_mesin(kode_unit: str) -> str:
    """Hitung SHA-256 dari berkas hasil ekstraksi mesin untuk ``kode_unit``."""
    return hitung_hash_berkas(cari_berkas_mesin(kode_unit))


def normalisasi_elemen_koreksi(elemen_input: list[dict]) -> list[dict]:
    """Normalisasi daftar elemen ke struktur simpan ``koreksi/{kode}.json``.

    Format keluaran:
    [
      {
        "nomor": 1,
        "nama": "...",
        "kuk": [
          {"nomor": "1.1", "uraian": "..."}
        ]
      }
    ]
    Catatan: Tidak memangkas karakter isi ``nama`` / ``uraian`` selain
    normalisasi newline ``\\r\\n`` -> ``\\n`` agar tidak ada karakter hilang.
    """
    hasil: list[dict] = []
    for idx, el in enumerate(elemen_input or [], start=1):
        if not isinstance(el, dict):
            continue
        no_raw = el.get('nomor', el.get('nomor_elemen', idx))
        try:
            nomor = int(no_raw)
        except (ValueError, TypeError):
            nomor = idx

        nama = el.get('nama')
        if nama is None:
            nama = el.get('nama_elemen', '')
        nama = str(nama).replace('\r\n', '\n').replace('\r', '\n')

        daftar_kuk: list[dict] = []
        for k_idx, k in enumerate(el.get('kuk') or [], start=1):
            if not isinstance(k, dict):
                continue
            no_kuk = k.get('nomor')
            if no_kuk is None:
                no_kuk = k.get('nomor_kuk', f'{nomor}.{k_idx}')
            no_kuk_str = str(no_kuk).strip() or f'{nomor}.{k_idx}'

            uraian = k.get('uraian')
            if uraian is None:
                uraian = k.get('uraian_kuk', '')
            uraian_str = str(uraian).replace('\r\n', '\n').replace('\r', '\n')

            daftar_kuk.append({
                'nomor': no_kuk_str,
                'uraian': uraian_str,
            })

        hasil.append({
            'nomor': nomor,
            'nama': nama,
            'kuk': daftar_kuk,
        })
    return hasil


def konversi_ke_elemen_kompetensi(elemen_koreksi: list[dict]) -> list[dict]:
    """Ubah struktur elemen dari berkas koreksi ke ``elemen_kompetensi`` standar."""
    hasil: list[dict] = []
    for idx, el in enumerate(elemen_koreksi or [], start=1):
        nomor = el.get('nomor', el.get('nomor_elemen', idx))
        try:
            nomor = int(nomor)
        except (ValueError, TypeError):
            nomor = idx
        nama = el.get('nama') if 'nama' in el else el.get('nama_elemen', '')
        kuk_list: list[dict] = []
        for k_idx, k in enumerate(el.get('kuk') or [], start=1):
            no_kuk = k.get('nomor') if 'nomor' in k else k.get('nomor_kuk', f'{nomor}.{k_idx}')
            uraian = k.get('uraian') if 'uraian' in k else k.get('uraian_kuk', '')
            kuk_list.append({
                'nomor_kuk': str(no_kuk),
                'uraian_kuk': str(uraian),
            })
        hasil.append({
            'nomor_elemen': nomor,
            'nama_elemen': str(nama),
            'kuk': kuk_list,
        })
    return hasil


def ambil_koreksi(kode_unit: str) -> dict | None:
    """Baca berkas koreksi untuk ``kode_unit`` bila ada."""
    try:
        jalur = path_koreksi(kode_unit)
    except ValueError:
        return None
    if not jalur.is_file():
        return None
    return cache_berkas.baca_json(jalur)


def status_koreksi(kode_unit: str, koreksi_data: dict | None = None) -> dict:
    """Periksa status koreksi & apakah ada konflik dengan hasil mesin saat ini.

    Kembalikan dict:
    {
      "ada_koreksi": bool,
      "konflik": bool,
      "dikoreksi_pada": str | None,
      "oleh": str | None,
      "hash_hasil_mesin": str,
      "hash_mesin_sekarang": str,
      "koreksi": dict | None
    }
    """
    if koreksi_data is None:
        koreksi_data = ambil_koreksi(kode_unit)
    hash_sekarang = hitung_hash_mesin(kode_unit)
    if not koreksi_data:
        return {
            'ada_koreksi': False,
            'konflik': False,
            'dikoreksi_pada': None,
            'oleh': None,
            'hash_hasil_mesin': '',
            'hash_mesin_sekarang': hash_sekarang,
            'koreksi': None,
        }
    hash_tersimpan = str(koreksi_data.get('hash_hasil_mesin') or '')
    konflik = bool(hash_sekarang != hash_tersimpan)
    return {
        'ada_koreksi': True,
        'konflik': konflik,
        'dikoreksi_pada': koreksi_data.get('dikoreksi_pada'),
        'oleh': koreksi_data.get('oleh') or 'pengguna_lokal',
        'hash_hasil_mesin': hash_tersimpan,
        'hash_mesin_sekarang': hash_sekarang,
        'koreksi': koreksi_data,
    }


def simpan_koreksi(
    kode_unit: str,
    elemen: list[dict],
    oleh: str = 'muhadi',
    judul_unit: str | None = None,
) -> dict:
    """Simpan koreksi manual ke ``data/json/koreksi/{kode_unit}.json`` secara atomik."""
    kode = _validasi_kode_unit(kode_unit)
    elemen_norm = normalisasi_elemen_koreksi(elemen)
    if not elemen_norm:
        raise ValueError('Koreksi harus memiliki minimal 1 elemen kompetensi.')
    total_kuk = sum(len(el.get('kuk') or []) for el in elemen_norm)
    if total_kuk == 0:
        raise ValueError('Koreksi harus memiliki minimal 1 Kriteria Unjuk Kerja (KUK).')

    hash_mesin = hitung_hash_mesin(kode)
    payload: dict = {
        'kode_unit': kode,
        'dikoreksi_pada': datetime.now().isoformat(timespec='seconds'),
        'oleh': (oleh or 'muhadi').strip() or 'muhadi',
        'hash_hasil_mesin': hash_mesin,
        'elemen': elemen_norm,
    }
    if judul_unit is not None:
        payload['judul_unit'] = str(judul_unit).replace('\r\n', '\n').replace('\r', '\n')

    jalur = path_koreksi(kode)
    tmp = jalur.with_suffix(f'.json.tmp.{os.getpid()}')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, jalur)
    return payload


def hapus_koreksi(kode_unit: str) -> bool:
    """Hapus berkas koreksi untuk mengembalikan unit ke hasil ekstraksi mesin."""
    jalur = path_koreksi(kode_unit)
    if jalur.is_file():
        jalur.unlink()
        return True
    return False


def pertahankan_koreksi(kode_unit: str) -> dict | None:
    """Selesaikan konflik dengan memperbarui ``hash_hasil_mesin`` ke hash mesin terbaru."""
    kode = _validasi_kode_unit(kode_unit)
    data = ambil_koreksi(kode)
    if not data:
        return None
    data['hash_hasil_mesin'] = hitung_hash_mesin(kode)
    data['dikoreksi_pada'] = datetime.now().isoformat(timespec='seconds')
    jalur = path_koreksi(kode)
    tmp = jalur.with_suffix(f'.json.tmp.{os.getpid()}')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, jalur)
    return data


def bandingkan_mesin_dan_koreksi(elemen_mesin: list[dict], elemen_koreksi: list[dict]) -> list[dict]:
    """Susun perbandingan berdampingan antara teks hasil mesin dan teks koreksi."""
    mesin_norm = normalisasi_elemen_koreksi(elemen_mesin or [])
    kor_norm = normalisasi_elemen_koreksi(elemen_koreksi or [])

    peta_mesin_el = {el['nomor']: el for el in mesin_norm}
    peta_kor_el = {el['nomor']: el for el in kor_norm}
    semua_no_el = sorted(set(peta_mesin_el.keys()) | set(peta_kor_el.keys()))

    daftar_perbandingan: list[dict] = []
    for no_el in semua_no_el:
        el_m = peta_mesin_el.get(no_el, {'nomor': no_el, 'nama': '', 'kuk': []})
        el_k = peta_kor_el.get(no_el, {'nomor': no_el, 'nama': '', 'kuk': []})

        nama_berubah = (el_m.get('nama') or '') != (el_k.get('nama') or '')

        peta_m_kuk = {k['nomor']: k['uraian'] for k in (el_m.get('kuk') or [])}
        peta_k_kuk = {k['nomor']: k['uraian'] for k in (el_k.get('kuk') or [])}

        urutan_kuk: list[str] = []
        for k in (el_k.get('kuk') or []):
            if k['nomor'] not in urutan_kuk:
                urutan_kuk.append(k['nomor'])
        for k in (el_m.get('kuk') or []):
            if k['nomor'] not in urutan_kuk:
                urutan_kuk.append(k['nomor'])

        kuk_diff: list[dict] = []
        for no_k in urutan_kuk:
            u_m = peta_m_kuk.get(no_k, '')
            u_k = peta_k_kuk.get(no_k, '')
            kuk_diff.append({
                'nomor': no_k,
                'uraian_mesin': u_m,
                'uraian_koreksi': u_k,
                'berubah': u_m != u_k,
            })

        daftar_perbandingan.append({
            'nomor': no_el,
            'nama_mesin': el_m.get('nama') or '',
            'nama_koreksi': el_k.get('nama') or '',
            'nama_berubah': nama_berubah,
            'kuk': kuk_diff,
            'ada_perubahan': nama_berubah or any(item['berubah'] for item in kuk_diff),
        })

    return daftar_perbandingan


def terapkan_koreksi_ke_data(data_mesin: dict | None, kode_unit: str | None = None) -> dict | None:
    """Gabungkan data mesin dengan koreksi manual bila ada.

    Aturan penggabungan:
    - Teks koreksi menggantikan ``elemen_kompetensi`` pada data yang dikembalikan.
    - Elemen asli mesin tetap disimpan di ``_elemen_mesin`` untuk keperluan audit/perbandingan.
    - Metadata koreksi dan status konflik disimpan di ``_koreksi``.
    """
    kode = kode_unit or (data_mesin or {}).get('kode_unit')
    if not kode:
        return data_mesin

    info = status_koreksi(kode)
    if not info['ada_koreksi']:
        if data_mesin is None:
            return None
        hasil = copy.deepcopy(data_mesin)
        hasil['_koreksi'] = info
        return hasil

    kor = info['koreksi'] or {}
    elemen_baru = konversi_ke_elemen_kompetensi(kor.get('elemen') or [])

    if data_mesin is None:
        hasil = {
            'kode_unit': kode,
            'judul_unit': kor.get('judul_unit') or '',
            'elemen_kompetensi': elemen_baru,
            '_elemen_mesin': [],
            'batasan_variabel': {},
            'panduan_penilaian': {},
            'validasi': {
                'status': 'valid_struktur',
                'catatan': ['Dikoreksi manual oleh pengguna.'],
            },
            'validasi_kelengkapan': {
                'status': 'valid_kelengkapan',
                'kuk_hilang': [],
                'catatan': ['Dikoreksi manual oleh pengguna.'],
            },
        }
    else:
        hasil = copy.deepcopy(data_mesin)
        hasil['_elemen_mesin'] = copy.deepcopy(hasil.get('elemen_kompetensi') or [])
        if kor.get('judul_unit'):
            hasil['judul_unit'] = kor['judul_unit']
        hasil['elemen_kompetensi'] = elemen_baru

    perbandingan = bandingkan_mesin_dan_koreksi(
        hasil.get('_elemen_mesin') or [],
        kor.get('elemen') or [],
    )
    jumlah_kuk_diubah = sum(
        1 for el in perbandingan for k in el['kuk'] if k['berubah']
    )
    jumlah_el_diubah = sum(1 for el in perbandingan if el['nama_berubah'])

    hasil['_koreksi'] = {
        **info,
        'perbandingan': perbandingan,
        'jumlah_kuk_diubah': jumlah_kuk_diubah,
        'jumlah_elemen_diubah': jumlah_el_diubah,
    }
    return hasil


def ambil_unit_final(kode_unit: str) -> dict | None:
    """Ambil dict unit kompetensi siap pakai (hasil mesin + koreksi manual bila ada)."""
    try:
        kode = _validasi_kode_unit(kode_unit)
    except ValueError:
        return None
    mesin = muat_json_mesin(kode)
    return terapkan_koreksi_ke_data(mesin, kode)

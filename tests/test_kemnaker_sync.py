"""
Pengujian Modul Integrasi & Sinkronisasi Regulasi Kemnaker RI.

Memastikan:
1. Ekstraksi nomor dan tahun dari berbagai format penomoran dan nama berkas.
2. Format catatan Kepmenaker pengganti (misal: '2018-107' -> 'Kepmenaker No. 107 Tahun 2018').
3. Pencarian regulasi ke katalog lokal / API Kemnaker RI.
4. Pembaruan otomatis status regulasi lokal (dicabut / berlaku) ke basis data SQLite.
5. Deteksi kode unit format lama (pola 2004-2010 seperti TIK.MM01.001.01).
"""

import pytest
from app import db, library
from app.extractor import UNIT_CODE_PATTERN
from app.services import kemnaker_sync


def test_ekstrak_nomor_tahun():
    """Menguji ekstraksi nomor dan tahun dari input angka maupun pola nama berkas."""
    # 1. Dari nomor dan tahun langsung
    no, th = kemnaker_sync.ekstrak_nomor_tahun_dari_teks_atau_nama("056", "2018", "")
    assert no == "56"
    assert th == "2018"

    # 2. Dari nama berkas format TAHUN-NOMOR
    no, th = kemnaker_sync.ekstrak_nomor_tahun_dari_teks_atau_nama(None, None, "SKKNI 2007-115.pdf.pdf")
    assert no == "115"
    assert th == "2007"

    # 3. Dari nama berkas format NOMOR_TAHUN
    no, th = kemnaker_sync.ekstrak_nomor_tahun_dari_teks_atau_nama(None, None, "SKKNI_107_2018.pdf")
    assert no == "107"
    assert th == "2018"


def test_format_pengganti():
    """Menguji pemformatan catatan pengganti dari Kemnaker."""
    hasil = kemnaker_sync._format_pengganti("2018-107")
    assert "Kepmenaker No. 107 Tahun 2018" in hasil
    assert "SKKNI 2018-107" in hasil

    # String kosong atau catatan bebas
    assert kemnaker_sync._format_pengganti(None) == ""
    assert kemnaker_sync._format_pengganti("Belum ada") == "Belum ada"


def test_cari_regulasi_kemnaker():
    """Menguji pencarian regulasi spesifik (misal 115 tahun 2007 harus dicabut)."""
    info = kemnaker_sync.cari_regulasi_kemnaker("115", "2007", nama_berkas="SKKNI 2007-115.pdf")
    assert info is not None
    assert info["ditemukan"] is True
    assert info["status_regulasi"] == "dicabut"
    assert "107" in info["kepmen_pengganti"]
    assert "2018" in info["kepmen_pengganti"]


def test_dukungan_kode_unit_format_lama():
    """Menguji regex kode unit agar mengenali baik format modern maupun format lama (2004-2010)."""
    # Format modern
    assert UNIT_CODE_PATTERN.match("J.63OPR00.005.2") is not None
    assert UNIT_CODE_PATTERN.match("M.70MKT00.012.1") is not None

    # Format lama (misal SKKNI 2007-115 Multimedia)
    assert UNIT_CODE_PATTERN.match("TIK.MM01.001.01") is not None
    assert UNIT_CODE_PATTERN.match("TIK.MM02.045.01") is not None
    assert UNIT_CODE_PATTERN.match("TIK.MM03.007.01") is not None


def test_sinkronkan_dokumen_ke_db():
    """Menguji penyimpanan hasil sinkronisasi ke database regulasi_skkni."""
    # Pastikan fungsi sinkronisasi berjalan tanpa melempar pengecualian
    hasil = kemnaker_sync.sinkronkan_dokumen_tunggal("966c970af6c646779eadb22d09354da3")
    assert hasil["sukses"] is True
    assert hasil["status_regulasi"] == "dicabut"

    peta = db.ambil_peta_regulasi()
    assert "2007-115" in peta
    assert peta["2007-115"]["status_regulasi"] == "dicabut"
    assert "107" in peta["2007-115"]["kepmen_pengganti"]

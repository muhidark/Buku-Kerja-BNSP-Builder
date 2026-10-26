# Status Kebenaran Sistem (Single Source of Truth)
## Sistem Pembuatan Dokumen Buku Kerja Asesor V.2023

Dokumen ini adalah **sumber kebenaran tunggal** (*single source of truth*) mengenai status implementasi fitur, keamanan, arsitektur, dan pengujian dalam repositori `skkni-extractor`. Seluruh dokumen lain (seperti `README.md` dan `RENCANA_PENGEMBANGAN_BUKU_KERJA.md`) merujuk ke status resmi pada dokumen ini.

---

## 1. Matriks Status Fase & Rujukan Commit

| Fase | Deskripsi & Cakupan | Status | Commit Rujukan | Temuan Ditutup |
| :---: | :--- | :---: | :--- | :--- |
| **Fase 0** | **Persiapan & Baseline**<br/>• Pangkas dependensi tak terpakai & pin versi seragam.<br/>• Pembuatan cabang kerja `audit-fixes` dan cadangan data awal. | **Selesai** | `a5f6cd7` | T-20 |
| **Fase 1** | **Keamanan & Kontrol Akses (RBAC)**<br/>• WAL mode & busy timeout SQLite (30 detik).<br/>• Penegakan otentikasi & otorisasi di seluruh 13 endpoint POST.<br/>• Hentikan kredensial bawaan; kata sandi acak di konsol & wajib ganti sandi.<br/>• Penyimpanan kunci API sebagai hash SHA-256.<br/>• Pengerasan HTTP: Security headers (CSP, nosniff, DENY) & batas login (rate limit). | **Selesai** | `c8412d4`<br/>`3b6abf4`<br/>`c453f34`<br/>`7590ca4`<br/>`bdfb8a1` | T-01, T-02, T-06, T-21, T-22 |
| **Fase 2** | **Bug Fungsional**<br/>• Perbaikan penanda versi MUK tertukar (`is_aktif` biner 0/1 & ISO timestamp) & migrasi data lama.<br/>• Pendaftaran skema keamanan OpenAPI (Swagger UI memiliki tombol Authorize). | **Selesai** | `1c446e7`<br/>`58d13a2` | T-03, T-04 |
| **Fase 3** | **Antarmuka & Pengalaman Pengguna (UI/UX)**<br/>• Peningkatan kontras teks (≥ 4.5:1 WCAG AA) & target klik minimal 32 px.<br/>• Refaktor 1.400+ gaya inline ke kelas CSS semantik.<br/>• Penanda perubahan belum disimpan (*unsaved changes*) & dialog peringatan sebelum tutup tab.<br/>• Indikator loading/proses saat unggah, simpan, dan unduh berkas.<br/>• Aksesibilitas (label form ber-`for`, peran tab ARIA, menu ponsel responsif, ikon SVG).<br/>• Hierarki visual satu aksi utama per halaman. | **Selesai** | `76e01a7`<br/>`7fe7b6a`<br/>`5cac8b9`<br/>`a5e61c2`<br/>`a8e19d1`<br/>`d946b4e` | T-07, T-08, T-09, T-10, T-11, T-12, T-13, T-26, T-27 |
| **Fase 4** | **Keandalan & Struktur Kode**<br/>• Hentikan efek samping pada request GET; identifikasi/validasi jadi aksi eksplisit.<br/>• Cache pembacaan JSON berbasis mtime untuk mengatasi pola pembacaan N+1.<br/>• Migrasi struktur basis data idempoten (`PRAGMA user_version`) & pencadangan harian otomatis (rotasi 7 arsip).<br/>• Pecah `app/main.py` menjadi router per domain di `app/routes/`, satukan helper `app/paths.py`, `app/penyimpanan.py`, dan `app/web_common.py`. | **Selesai** | `563f134`<br/>`4cb7f96`<br/>`f480ed3`<br/>`e4d01e3` | T-17, T-18, T-19, T-25, T-30, T-31 |
| **Fase 5** | **Pengujian & CI (Quality Assurance)**<br/>• Migrasi test suite runner ke `pytest` dan penambahan wrapper test di seluruh skrip.<br/>• Isolasi data uji melalui fixture `conftest.py` dan proteksi checksum basis data kerja.<br/>• Test versi MUK mandiri (`test_versi_muk.py`), test otorisasi (`test_otorisasi.py`), dan OpenAPI (`test_openapi.py`).<br/>• Konfigurasi Linter (Ruff, Black) di `pyproject.toml`, workflow CI GitHub Actions, dan pre-commit hooks. | **Selesai** | `edbae99` | T-05, T-14, T-32 |
| **Fase 6** | **Dokumentasi & Verifikasi Akhir**<br/>• Satu sumber kebenaran status (`docs/STATUS.md`) dan indeks dokumentasi (`docs/README.md`).<br/>• Pembaruan dan perbaikan panduan alur pengujian (`docs/PANDUAN_ALUR_PENGUJIAN.md`) ke 15 butir ceklis.<br/>• Pelaksanaan 12 butir uji checklist penerimaan akhir (`docs/HASIL_VERIFIKASI_AKHIR_2026-10-27.md`). | **Selesai** | *(commit ini)* | T-15, T-16, T-23, T-24, T-28, T-34 |

---

## 2. Status Fitur Utama Aplikasi

* **Pracetak A4 & Desain Responsif**: 100% Sesuai Standar BNSP 2023. Menggunakan `@page` portrait (210 mm) dan landscape (297 mm) untuk formulir yang sesuai (MAPA.01, Peta Kelompok, MAPA.02, IA.01).
* **Ekspor DOCX / ZIP**: 100% Sesuai. Menghasilkan 25 formulir resmi BNSP terpisah dan 1 dokumen gabungan lengkap (00_Buku_Kerja_Lengkap_Gabungan.docx) dengan rotasi orientasi dinamis di dalam dokumen Word.
* **Autentikasi & RBAC**: Sesi HttpOnly berbasis token aman, double-submit CSRF, kontrol peran Admin (Kurator Master) vs Asesor (Penyusun MUK).
* **Basis Data**: SQLite dengan mode WAL (`journal_mode=WAL`), `busy_timeout=30000`, skema termigrasi, dan pencadangan harian otomatis.
* **REST API**: `/api/v1` terlindungi API Key (hash SHA-256), Swagger UI interaktif dengan tombol `Authorize`.

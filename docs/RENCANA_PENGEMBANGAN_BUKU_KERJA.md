# Rencana Pengembangan Sistem Pembuatan Dokumen Buku Kerja Asesor & MUK (Standar BNSP V.2023)

**Dokumen Acuan untuk:**
1. **Tim Tenaga Ahli Sertifikasi / Master Asesor** (Validasi aturan bisnis, alur dokumen BNSP, dan kelengkapan instrumen MUK)
2. **Tim Web Programmer** (Validasi arsitektur teknis, struktur database, integrasi template, dan pengembangan REST API)

---

## 0. Ringkasan Status Pelaksanaan (Update Terbaru)

| Tahap / Modul | Status | Catatan Implementasi |
| :--- | :---: | :--- |
| **Pra-Fase (Fase 4F): Kualitas Data & Gerbang Dokumen** | **SELESAI (100%)** | Hapus KUK palsu, status 3-tingkat (`Siap dipakai`, `Perlu diperiksa`, `Gagal`), Gerbang Dokumen HTTP 409, Editor Koreksi Per-Unit berdampingan PDF + Deteksi Konflik SHA-256 (`docs/CATATAN_PERBAIKAN_FASE_4F.md`). |
| **Fase 2: Modul Kelompok Pekerjaan & Bank Instrumen MUK** | **SELESAI (100%)** | Penyimpanan JSON per skema (`data/schema_library/muk/{schema_id}.json`), UI kelola di `/skema/{schema_id}/muk`, auto-default `IA.02`, `IA.03`, `IA.04`, `IA.05`, `IA.06`, `IA.07`, `IA.08`, kalkulasi cakupan unit Kelompok Pekerjaan. |
| **Fase 3: Konversi Template Dokumen Buku Kerja ke Jinja2** | **SELESAI (100%)** | 25 parsial Jinja2 di `app/templates/buku_kerja/` (`APL.01–02`, `MAPA.01` [Obs/DIT/Port], `Peta Kelompok`, `MAPA.02`, `AK.01–07`, `IA.01–08`, dan `FR.VA` Form Kosongan) + mode cetak satuan & paket metode. |
| **Fase 3B: Instrumen Lanjutan (`IA.06–08` & `FR.VA`)** | **SELESAI (100%)** | `FR.IA.06A/B/C` (Esai), `IA.07` (Lisan), `IA.08` (Ceklis Verifikasi Portofolio), dan `FR.VA` (Form Kosongan Validasi Asesmen). `IA.09` & `IA.10` dilewati sesuai arahan. |
| **Fase 3C: Asisten Referensi BV/PP & Ekspor `.docx` Buku Kerja** | **BELUM** | Menampilkan referensi Batasan Variabel & Panduan Penilaian di editor MUK + unduh bundel `.docx`/`.zip` untuk Buku Kerja. |
| **Fase 1: Multi-User (Login/RBAC SQLite) & Katalog SKKNI Terpusat** | **BELUM** | Pemisahan role `Admin/Kurator Master` (verifikasi SKKNI & status berlaku/dicabut Kemnaker) vs `User/LSP/Asesor` (ruang kerja skema & MUK terpisah). |
| **Fase 4: REST API Eksternal (`/api/v1/...`) dengan API Key** | **BELUM** | Endpoint sinkronisasi otomatis ke plugin WordPress / LMS eksternal menggunakan `X-API-Key`. |

---

## 1. Latar Belakang & Tujuan Proyek

Saat ini terdapat dua sistem yang sebelumnya berjalan secara terpisah:
1. **SKKNI Extractor (Python / FastAPI):** Berfungsi mengekstrak dokumen PDF SKKNI dan DOCX Skema Sertifikasi menjadi data JSON terstruktur (Unit Kompetensi, Elemen Kompetensi, Kriteria Unjuk Kerja/KUK, Batasan Variabel, dan Panduan Penilaian).
2. **Plugin WordPress (`lsp-certification-management`):** Berfungsi mengelola pendaftaran asesi, penjadwalan kegiatan, bank instrumen MUK, serta pencetakan 18+ formulir sertifikasi BNSP.

**Tujuan Pengembangan:**
Menggabungkan kemampuan **Generator Dokumen Sertifikasi & Bank Instrumen MUK** dari plugin WordPress langsung ke dalam aplikasi **SKKNI Extractor**, namun dalam **versi ramping (Tanpa Sistem Pendaftaran Peserta)**.

Output akhirnya adalah **Dokumen Master / Blanko Siap Cetak (Ready-to-Print)** untuk seluruh perangkat asesmen (APL, MAPA, AK, IA) yang akan diisi secara manual oleh peserta (asesi) dan asesor di lapangan, sementara data skema, unit kompetensi, elemen, KUK, serta identitas asesor langsung terisi otomatis dari aplikasi.

---

## 2. Bagian A — Untuk Ditinjau oleh Tenaga Ahli Sertifikasi (Asesor / Komite Skema)

> **PENTING:** Mohon Tenaga Ahli memeriksa apakah pemetaan dokumen, aturan pengisian otomatis vs manual, serta struktur instrumen di bawah ini sudah sesuai dengan pedoman BNSP V.2023 dan SOP LSP.

### 2.1. Konsep Dokumen "Template Siap Cetak" (Tanpa Data Pendaftaran Asesi)
Karena aplikasi ini tidak memproses pendaftaran peserta secara online:
- **Bagian yang Terisi Otomatis oleh Sistem:**
  - Judul Skema, Nomor Skema, dan Jenis Kemasan (KKNI / Okupasi / Klaster).
  - Daftar Unit Kompetensi (Kode Unit, Judul Unit, dan Standar Acuan SKKNI).
  - Rincian Elemen Kompetensi dan Kriteria Unjuk Kerja (KUK) secara lengkap pada `FR.APL.02` (dengan konversi kalimat tanya aktif *"Dapatkah Saya ...?"*) dan `FR.IA.01`.
  - Pengelompokan Unit berdasarkan **Kelompok Pekerjaan** pada `Peta Kelompok Pekerjaan`, `FR.IA.01`, `FR.IA.02`, dan `FR.IA.03`.
  - Identitas **Asesor Penguji** (Nama & No. Reg. MET), **Tim Penyusun**, **Validator**, dan **Manajer Sertifikasi** (diinput melalui halaman `/skema/{schema_id}/muk`).
- **Bagian yang Dikosongkan (Blanko untuk Diisi Manual / Tulis Tangan):**
  - Identitas Asesi (Nama lengkap, NIK, tempat/tgl lahir, alamat, pekerjaan, tanda tangan).
  - Kotak pencapaian/asesmen mandiri (`☐ K` / `☐ BK` pada `FR.APL.02`, serta `☐ Ya` / `☐ Tidak` pada `FR.IA.01` & `FR.IA.03`).
  - Kolom bukti relevan, tanggapan asesi, umpan balik, catatan asesor, dan rekomendasi akhir.

### 2.2. Daftar Dokumen & Status Konversi Saat Ini
Mengacu pada paket dokumen acuan (contoh: *Skema Videografer*) dan template yang sudah dikonversi ke `app/templates/buku_kerja/`:

| No | Kode Dokumen | Nama Dokumen | File Template Jinja2 | Status |
| :--- | :--- | :--- | :--- | :---: |
| 1 | **Cover & Ceklis** | Cover & Daftar Periksa Kelengkapan Dokumen | *(Dilewati sesuai arahan)* | Dilewati |
| 2 | **FR.APL.01** | Permohonan Sertifikasi Kompetensi | `cetak_apl.html` | **Selesai** |
| 3 | **FR.APL.02** | Asesmen Mandiri (*"Dapatkah Saya ...?"*) | `cetak_apl.html` | **Selesai** |
| 4 | **FR.MAPA.01 (Obs)** | Merencanakan Aktivitas & Proses Asesmen *(Observasi Langsung)* | `_form_mapa01.html` | **Selesai** |
| 5 | **FR.MAPA.01 (DIT)** | Merencanakan Aktivitas & Proses Asesmen *(DIT / Kegiatan Terstruktur)* | `_form_mapa01.html` | **Selesai** |
| 6 | **FR.MAPA.01 (Port)** | Merencanakan Aktivitas & Proses Asesmen *(Verifikasi Portofolio)* | `_form_mapa01.html` | **Selesai** |
| 7 | **Peta Kelompok** | Peta Kelompok Pekerjaan & Daftar Unit | `_form_peta_kelompok.html` | **Selesai** |
| 8 | **FR.MAPA.02** | Peta Instrumen Asesmen | `_form_mapa02.html` | **Selesai** |
| 9 | **FR.AK.01** | Persetujuan Asesmen dan Kerahasiaan | `_form_ak01.html` | **Selesai** |
| 10 | **FR.AK.02** | Rekaman Asesmen Kompetensi | `_form_ak02.html` | **Selesai** |
| 11 | **FR.AK.03** | Umpan Balik dan Catatan Asesmen | `_form_ak03.html` | **Selesai** |
| 12 | **FR.AK.04** | Banding Asesmen | `_form_ak04.html` | **Selesai** |
| 13 | **FR.AK.05** | Laporan Asesmen | `_form_ak05.html` | **Selesai** |
| 14 | **FR.AK.06** | Meninjau Proses Asesmen | `_form_ak06.html` | **Selesai** |
| 15 | **FR.AK.07** | Ceklis Penyesuaian yang Wajar dan Beralasan | `_form_ak07.html` | **Selesai** |
| 16 | **FR.IA.01** | CL - Ceklis Observasi Aktivitas Praktik | `_form_ia01.html` | **Selesai** |
| 17 | **FR.IA.02** | TPD - Tugas Praktik Demonstrasi | `_form_ia02.html` | **Selesai** |
| 18 | **FR.IA.03** | PMO - Pertanyaan Mendukung Observasi | `_form_ia03.html` | **Selesai** |
| 19 | **FR.IA.04A & 04B** | DIT - Penjelasan Proyek Singkat (STAR) & Lembar Penilaian | `_form_ia04a.html`, `_form_ia04b.html` | **Selesai** |
| 20 | **FR.IA.05A, B, C** | DPT - Soal Pilihan Ganda, Kunci Jawaban, & Lembar Jawaban | `_form_ia05a.html` s/d `05c.html` | **Selesai** |
| 21 | **FR.IA.06A, B, C** | DPT - Soal Esai, Kunci Jawaban Esai, & Lembar Jawaban Esai | `_form_ia06a.html` s/d `06c.html` | **Selesai** |
| 22 | **FR.IA.07** | DPL - Daftar Pertanyaan Lisan | `_form_ia07.html` | **Selesai** |
| 23 | **FR.IA.08** | CVP - Ceklis Verifikasi Portofolio | `_form_ia08.html` | **Selesai** |
| 24 | **FR.IA.09 & 10** | PW (Wawancara) & VPK (Verifikasi Pihak Ketiga) | *(Tidak dibuat sesuai arahan)* | Dilewati |
| 25 | **FR.VA** | Memberikan Kontribusi dalam Validasi Asesmen (Form Kosongan) | `_form_va.html` | **Selesai** |

---

## 3. Bagian B — Laporan Teknis untuk Web Programmer

### 3.1. Apa yang Sudah Selesai Dikerjakan & Diuji
1. **Perbaikan Kualitas Data & Gerbang Dokumen (`Fase 4F` — Detail di `docs/CATATAN_PERBAIKAN_FASE_4F.md`):**
   - `app/unit_parser.py`: Menghapus pembuatan KUK palsu (*placeholder*) saat teks kriteria tidak terbaca.
   - `app/status_units.py` & `app/templates/_status_badge.html`: Penilaian otomatis 3-tingkat (`Siap dipakai`, `Perlu diperiksa`, `Gagal`) yang seragam di seluruh halaman.
   - `app/main.py`: Gerbang Dokumen (*Document Gate*) yang memblokir unduhan DOCX dan pencetakan Buku Kerja (`HTTP 409`) apabila skema masih memiliki unit berstatus `Gagal`.
   - `app/koreksi.py` & `app/templates/unit_koreksi.html`: Editor koreksi per-unit berdampingan dengan PDF SKKNI asli, disimpan terpisah di `data/json/koreksi/{kode_unit}.json` dengan pelacak sidik jari `hash_hasil_mesin` (SHA-256) untuk mendeteksi konflik ekstraksi ulang.
2. **Modul Kelompok Pekerjaan & Bank Instrumen MUK (`Fase 2`):**
   - `app/buku_kerja.py`: Penyimpanan dan pemuatan konfigurasi MUK per skema di `data/schema_library/muk/{schema_id}.json`.
   - `app/templates/skema_muk.html` (`GET/POST /skema/{schema_id}/muk`): Antarmuka terpadu untuk mengelola Personel & TUK, Kelompok Pekerjaan (dengan indikator persentase cakupan unit), serta instrumen `FR.IA.02`, `FR.IA.03`, `FR.IA.04`, dan `FR.IA.05`.
   - Fungsi generator otomatis (`buat_default_ia02`, `buat_default_ia03`, `buat_default_ia04`, `buat_default_ia05`) jika pengguna belum mengisi instrumen secara manual.
3. **Konversi 18 Dokumen Buku Kerja BNSP ke Jinja2 (`Fase 3`):**
   - 19 file parsial Jinja2 di `app/templates/buku_kerja/` yang diintegrasikan ke dalam `app/templates/cetak_apl.html`.
   - Mendukung pencetakan dokumen satuan, **Paket per Metode (`Observasi`, `DIT`, `Portofolio`)**, maupun **Paket Lengkap (`all`)**, termasuk pengaturan orientasi halaman *Portrait* & *Landscape* otomatis untuk `FR.MAPA.01`.
   - Seluruh pengujian otomatis (`tests/test_buku_kerja.py`, `tests/test_gerbang_dokumen.py`, `tests/test_koreksi.py`, `tests/test_koreksi_konflik.py`, `tests/test_web.py`) lulus 100%.

---

## 4. Bagian C —Apa yang Belum Dikerjakan & Rencana Pengembangan Berikutnya

Berikut adalah daftar pekerjaan yang belum dieksekusi beserta urutan prioritas pengerjaan berikutnya:

### Prioritas 1 — Peningkatan Kualitas Penyusunan MUK & Ekspor Dokumen (Jangka Pendek)
1. **Panel Referensi Otomatis Batasan Variabel (BV) & Panduan Penilaian (PP) di Editor MUK (`/skema/{schema_id}/muk`):**
   - Menampilkan hasil ekstraksi **Batasan Variabel** (konteks, peralatan, perlengkapan) dan **Panduan Penilaian** (pengetahuan, keterampilan, aspek kritis) dari JSON SKKNI langsung di samping form `FR.IA.02`, `FR.IA.03`, dan `FR.IA.04` agar penyusun MUK tinggal menyalin/mengklik ke dalam instrumen.
2. **Pengembangan Instrumen Tambahan (`FR.IA.06` s/d `FR.IA.11` & `FR.VA`):**
   - Menyusun struktur JSON, form editor di `/skema/{schema_id}/muk`, dan template cetak Jinja2 untuk:
     - `FR.IA.06` (Pertanyaan Tertulis Esai: Soal, Kunci Jawaban, Lembar Jawaban)
     - `FR.IA.07` (Pertanyaan Lisan)
     - `FR.IA.08` (Ceklis Verifikasi Portofolio — penting untuk melengkapi paket metode Portofolio)
     - `FR.IA.09` (Pertanyaan Wawancara)
     - `FR.IA.10` (Klarifikasi Bukti Pihak Ketiga) & `FR.IA.11` (Ceklis Reviu Produk)
     - `FR.VA` (Memberikan Kontribusi dalam Validasi Asesmen — menunggu hasil konsultasi dengan Master Asesor).
3. **Ekspor Buku Kerja ke Format Microsoft Word (`.docx`) / Paket `.zip` Terstruktur:**
   - Menambahkan generator `.docx` untuk formulir Buku Kerja sehingga pengguna dapat mengunduh bundel `.zip` bernomor urut (`01. FR.APL.01.docx`, `02. FR.APL.02.docx`, dst.) seperti pada folder contoh *01 Videografer*.

### Prioritas 2 — Katalog SKKNI Terpusat & Sistem Multi-User Komersial (Fase 1 Arsitektur SaaS)
1. **Migrasi Metadata ke SQLite (`data/app.db`) & Autentikasi Multi-User (RBAC):**
   - **Role `Admin / Kurator Master`:** Mengunggah PDF SKKNI, melakukan koreksi unit hingga berstatus `Siap dipakai`, serta memberi label status regulasi Kemnaker (`Berlaku` / `Dicabut` beserta tautan referensi Kepmenaker).
   - **Role `User / LSP / Asesor`:** Menggunakan unit kompetensi dari **Katalog SKKNI Terpusat** secara instan (*Read-Only* terhadap Master SKKNI) untuk merakit Skema Sertifikasi dan Paket MUK di ruang kerjanya masing-masing tanpa saling menimpa.
2. **Multi-Versi Paket MUK per Skema:**
   - Memungkinkan satu skema memiliki beberapa versi paket soal/instrumen (misal: *Paket MUK Versi A*, *Paket MUK Versi B*).

### Prioritas 3 — REST API Eksternal (`/api/v1/...`) dengan API Key (Fase 4 Integrasi)
1. **Endpoint Terproteksi `X-API-Key`:**
   - `GET /api/v1/skkni` & `GET /api/v1/skkni/{kode_unit}` — Mengambil data unit, elemen, KUK, BV, dan PP yang sudah terverifikasi.
   - `GET /api/v1/skema` & `GET /api/v1/skema/{id}/muk` — Sinkronisasi langsung daftar unit, kelompok pekerjaan, dan instrumen MUK ke plugin WordPress (`lsp-certification-management`) tanpa *Smart Paste* manual.
   - `POST /api/v1/documents/render` — Render HTML/dokumen Buku Kerja dari aplikasi eksternal.

# Catatan Rilis — SKKNI Extractor v1.0.0

**Versi Resmi**: 1.0.0  
**Tanggal Rilis**: Oktober 2026  
**Status Audit**: Fase 5A (Remediasi 5A.1)  

---

## 1. Ikhtisar Aplikasi

**SKKNI Extractor** adalah aplikasi desktop-web lokal untuk mengekstrak unit-unit kompetensi dari dokumen PDF Standar Kompetensi Kerja Nasional Indonesia (SKKNI) menjadi data JSON terstruktur, memvalidasinya, dan mengompilasinya menjadi dokumen Microsoft Word (`.docx`) berstandar resmi (multi-unit berdasarkan skema sertifikasi).

Aplikasi beroperasi secara **100% lokal dan deterministik** berbasis analisis geometris koordinat bounding-box PyMuPDF tanpa ketergantungan pada kecerdasan buatan (AI), LLM, Ollama, atau layanan komputasi awan (*cloud*).

---

## 2. Fitur Utama pada Versi 1.0.0

### A. Ekstraksi dan Pemrosesan PDF SKKNI
- **Identifikasi Unit Otomatis**: Mendeteksi kode unit, judul unit, dan rentang halaman dari dokumen SKKNI dengan berbagai format layout (2018-056, 2018-107, 2022-124, 2023-101, dsb.).
- **Deteksi Kolom Dinamis**: Menentukan batas kolom tabel Elemen Kompetensi dan Kriteria Unjuk Kerja (KUK) secara adaptif berdasarkan celah sebaran koordinat horizontal (`x0`, `x1`).
- **Parsing Pohon Rekursif**: Mem-parsing Batasan Variabel dan Panduan Penilaian menjadi struktur pohon bertingkat (`1` $\rightarrow$ `1.1` $\rightarrow$ `1.1.1`) dengan penanganan pemenggalan baris, subbutir berhuruf besar, dan lanjutan antar-halaman.
- **Validasi Kelengkapan KUK**: Memvalidasi integritas penomoran urutan KUK secara mandiri.

### B. Manajemen Skema Sertifikasi dan Kompilasi Multi-Unit
- **Pembacaan Dokumen Skema (.docx)**: Membaca tabel kemasan/paket unit kompetensi pada dokumen skema.
- **Pencocokan Cerdas**: Memetakan kode unit skema ke repositori PDF SKKNI lokal dan menandai konflik sumber secara akurat.
- **Generator Dokumen Word Standar Resmi**:
  - Ukuran kertas F4 (21,5 × 33,0 cm) dengan tipografi Bookman Old Style 11 pt.
  - Implementasi XML *Word Multilevel Numbering* terisolasi per unit sehingga penomoran selalu dimulai ulang dari 1 di setiap unit.
  - *Hanging indent* adaptif untuk memastikan jarak nomor ke teks konsisten dan rapi.
  - Tabel dengan pengulangan header otomatis (`tblHeader`) dan baris tidak terpotong sembarangan (`cantSplit`).

### C. Antarmuka Web Lokal & Manajemen Pekerjaan
- **Backend Ringan & Cepat**: Dibangun di atas FastAPI + Uvicorn + template Jinja2 murni lokal (tanpa CDN eksternal).
- **Background Extraction Job Manager**: Ekstraksi berjalan di thread latar belakang (maks. 2 worker paralel) dengan pemantauan progres real-time dan pemulihan status saat restart server.
- **Preview Interaktif**: Menampilkan preview elemen, KUK, batasan variabel, dan panduan penilaian sebelum diekspor.
- **Keamanan Berlapis**: Proteksi token CSRF (double-submit cookie), pencegahan path traversal pada unduhan dokumen, dan validasi format unggahan (maks. 50 MB untuk PDF, 20 MB untuk DOCX).

### D. Utilitas Pencadangan & Pemulihan (Fase 5A.1)
- **`tools/backup.py`**: Mencadangkan seluruh data dan metadata ke arsip ZIP ber-timestamp lengkap dengan manifest SHA-256.
- **`tools/restore.py`**: Pemulihan data dengan mode simulasi (*dry-run*), verifikasi hash SHA-256 dua arah, isolasi staging, proteksi path traversal, dan proteksi ZIP bomb.
- **Sistem Logging Terstruktur**: Modul logging Python standar dengan rotasi berkas otomatis (maks. 10 MB, 5 file retensi) di direktori `logs/`.
- **Single Source of Truth Versi**: Seluruh komponen API dan UI terhubung ke satu konstanta versi tunggal di `app/version.py`.

---

## 3. Hasil Pengujian & Jaminan Mutu (Quality Assurance)

- **Pengujian Regresi**: Seluruh 20 rangkaian pengujian unit dan integrasi (Fase 1 s.d. 4F) lulus 100%.
- **Pengujian Audit QA Fase 4F**:
  - Verifikasi teks dua arah (PDF $\leftrightarrow$ JSON $\leftrightarrow$ DOCX): 183 potongan teks semantik diperiksa dan 100% cocok.
  - Temuan Critical: 0.
  - Temuan Major: 0.
- **Pengujian Negatif**: 8 kasus mutasi kesalahan struktur (KUK hilang, KUK duplikat, elemen hilang, mutasi teks, pergeseran bagian BV/PP) terbukti berhasil dideteksi oleh validator.
- **Integritas Data Pengguna**: Seluruh data sumber pengguna terbukti utuh 100% tanpa perubahan hash SHA-256.

---

## 4. Keterbatasan yang Diketahui

1. Dokumen PDF hasil pindai murni (*scanned image*) tanpa lapisan teks (*text layer*) tidak didukung; memerlukan proses OCR sebelum diproses oleh aplikasi.
2. Jarak spasi penomoran Word level 2 dan level 3 mengikuti standar *hanging indent* 0,75 cm yang menghasilkan tampilan rapat (±0,1 cm) sesuai dokumen referensi resmi.
3. Aplikasi dirancang untuk penggunaan lokal di lingkungan jaringan aman (`127.0.0.1`), bukan untuk disajikan langsung ke internet publik tanpa reverse-proxy / autentikasi tambahan.

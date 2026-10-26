# Panduan Pencadangan dan Pemulihan Data (Backup & Restore)

Dokumen ini menjelaskan prosedur pencadangan (*backup*) dan pemulihan (*restore*) data aplikasi **SKKNI Extractor** menggunakan utilitas bawaan pada direktori `tools/`.

---

## 1. Komponen yang Dicadangkan

Proses backup mencakup seluruh data produksi aplikasi:
- Dokumen PDF SKKNI perpustakaan (`data/library/` dan `data/pdf/`).
- Dokumen skema sertifikasi DOCX (`data/schema_library/` dan `data/skema/`).
- Metadata dokumen perpustakaan dan skema (format JSON).
- Hasil ekstraksi unit kompetensi (format JSON di `data/json/`).
- Riwayat pekerjaan ekstraksi (format JSON di `data/jobs/`).
- Metadata dan berkas kompilasi dokumen Word hasil generator (`data/web_documents/` dan `output/web_documents/`).

Berkas yang **otomatis dikecualikan** demi efisiensi dan keamanan:
- Virtual environment (`.venv/`)
- Cache Python (`__pycache__/`, `*.pyc`)
- Berkas sementara (`*.tmp`, `tmp/`)
- Berkas log (`logs/`)
- Berkas arsip backup itu sendiri (`backups/`)
- Berkas kontrol versi (`.git/`)

---

## 2. Cara Membuat Backup (`tools/backup.py`)

Pastikan virtual environment telah aktif:
```bash
source .venv/bin/activate
```

### A. Backup ke Lokasi Default
Secara default, arsip akan disimpan di direktori `backups/` di root proyek:
```bash
python tools/backup.py
```

### B. Backup ke Direktori Tertentu
Gunakan opsi `--outdir` (atau `-o`) untuk menentukan lokasi penyimpanan lain:
```bash
python tools/backup.py --outdir /media/backup/skkni_backups
```

### Karakteristik Berkas Backup
- Format: Arsip ZIP terkompresi dengan penamaan ber-timestamp: `backup_skkni_YYYYMMDD_HHMMSS.zip`.
- Manifest Integritas: Di dalam root ZIP disertakan berkas `manifest.json` yang memuat daftar seluruh berkas, ukuran, waktu pembuatan, versi aplikasi, dan hash SHA-256 masing-masing berkas.
- Uji Integritas Otomatis: Skrip secara otomatis memvalidasi integritas arsip (`testzip()`) sebelum proses backup dinyatakan selesai.

---

## 3. Cara Memulihkan Data (`tools/restore.py`)

Utilitas `tools/restore.py` dilengkapi dengan fitur keselamatan:
- **Dry-Run**: Memeriksa isi arsip dan potensi konflik tanpa mengubah berkas.
- **Validasi Keamanan**: Menolak path traversal (`..`), path absolut (`/`), symlink berbahaya, dan rasio kompresi ekstrem (ZIP bomb).
- **Verifikasi Dua Arah**: Memverifikasi kesesuaian hash SHA-256 setiap berkas hasil ekstraksi terhadap manifest.
- **Ekstraksi Atomik**: Mengekstrak ke direktori staging sementara terlebih dahulu untuk mencegah data terpulihkan sebagian jika proses terhenti.
- **Proteksi Pekerjaan Aktif**: Menolak pemulihan ke direktori produksi jika masih ada pekerjaan ekstraksi yang berstatus `berjalan` atau `menunggu`.

### A. Uji Coba Pemulihan (Dry-Run)
Sebelum memulihkan data, disarankan untuk menjalankan simulasi dry-run:
```bash
python tools/restore.py backups/backup_skkni_20261023_214849.zip --dry-run
```
Perintah ini akan menampilkan total berkas, jumlah berkas baru, dan jumlah berkas yang berkonflik.

### B. Pemulihan ke Direktori Terisolasi (Rekomendasi Uji)
Anda dapat memulihkan isi backup ke folder uji terpisah untuk memeriksa datanya secara aman:
```bash
python tools/restore.py backups/backup_skkni_20261023_214849.zip --target-dir /tmp/skkni_restore_test
```

### C. Pemulihan ke Direktori Produksi
Jika memulihkan ke direktori proyek aktif dan terdapat berkas yang sudah ada sebelumnya:
```bash
python tools/restore.py backups/backup_skkni_20261023_214849.zip --force
```

> **PERINGATAN**:
> 1. Gunakan opsi `--force` hanya jika Anda yakin ingin menimpa data yang ada dengan data dari arsip cadangan.
> 2. Pastikan server web tidak sedang menjalankan proses ekstraksi saat melakukan pemulihan.

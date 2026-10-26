# Panduan Instalasi — SKKNI Extractor v1.0.0

Dokumen ini menjelaskan langkah-langkah instalasi dan konfigurasi lingkungan untuk menjalankan aplikasi **SKKNI Extractor**.

---

## 1. Persyaratan Sistem

- **Sistem Operasi**: Linux (direkomendasikan Ubuntu 22.04 LTS atau lebih baru).
- **Python**: Versi 3.10, 3.11, atau 3.12/3.14.
- **Ruang Disk Bebas**: Minimal 1 GB (untuk penyimpanan PDF SKKNI, ekstraksi JSON, dan berkas Word DOCX).
- **Memori RAM**: Minimal 2 GB (direkomendasikan 4 GB untuk pemrosesan paralel).
- **Perangkat Lunak Tambahan (Opsional)**:
  - LibreOffice (`flatpak` atau `apt`) jika ingin menguji rendering visual dokumen Word ke PDF secara otomatis.

---

## 2. Pemasangan Virtual Environment dan Dependensi

Buka terminal pada direktori proyek `~/Projects/skkni-extractor`:

```bash
cd ~/Projects/skkni-extractor

# 1. Buat virtual environment (bila belum ada)
python3 -m venv .venv

# 2. Aktifkan virtual environment
source .venv/bin/activate

# 3. Perbarui pip dan pasang dependensi
pip install --upgrade pip
pip install -r requirements.txt
```

Daftar pustaka utama dalam `requirements.txt`:
- `fastapi` & `uvicorn` (backend web server lokal)
- `jinja2` (template antarmuka web)
- `pymupdf` (ekstraksi teks dan analisis koordinat PDF)
- `python-docx` (pembuatan dokumen Microsoft Word)
- `httpx` (pengujian API lokal)

---

## 3. Menjalankan Aplikasi

Aplikasi dapat dijalankan menggunakan skrip peluncur bawaan:

```bash
./run.sh
```

Skrip `run.sh` akan:
1. Memvalidasi keberadaan virtual environment `.venv`.
2. Memverifikasi modul wajib (`fastapi`, `uvicorn`, `jinja2`, `pymupdf`, `docx`).
3. Menjalankan server Uvicorn pada alamat lokal `http://127.0.0.1:8000`.

Jika ingin mengubah port bawaan (default: 8000), jalankan dengan variabel lingkungan `PORT`:
```bash
PORT=8080 ./run.sh
```

---

## 4. Mengakses Dashboard Aplikasi

Setelah server aktif, buka peramban web (browser) dan akses:

```
http://127.0.0.1:8000
```

Tampilan Dashboard akan memuat informasi versi aplikasi (`v1.0.0`), ringkasan statistik dokumen SKKNI, skema sertifikasi, dan dokumen Word yang telah dihasilkan.

---

## 5. Menghentikan Aplikasi

Untuk menghentikan server lokal:
- Pada terminal tempat `./run.sh` berjalan, tekan kombinasi tombol `Ctrl + C`.
- Jika dijalankan di latar belakang (daemon/background task), hentikan melalui PID proses:
  ```bash
  pkill -f "uvicorn app.main:app"
  ```

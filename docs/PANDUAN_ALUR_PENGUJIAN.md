# Panduan Alur Pengujian Aplikasi (Testing Workflow)
## Sistem Pembuatan Dokumen Buku Kerja Asesor BNSP V.2023

Dokumen ini memuat skenario dan langkah kerja terstruktur untuk menguji seluruh fungsi sistem secara menyeluruh (*End-to-End Testing*), mencakup antarmuka web (GUI), tata letak pracetak A4, ekspor berkas Word/ZIP, integrasi REST API, hingga pengujian otomatis di terminal.

---

## 1. Peta Alur Pengujian (Workflow Diagram)

```mermaid
flowchart TD
    Start(["Mulai Pengujian"]) --> Step1["Tahap 1: Pengujian Otentikasi & RBAC<br/>(Login Asesor vs Admin)"]
    Step1 --> Step2["Tahap 2: Katalog SKKNI & Kurasi Regulasi<br/>(Status Berlaku / Dicabut)"]
    Step2 --> Step3["Tahap 3: Kelola Skema & Kelompok Pekerjaan<br/>(Pemetaan Unit ke Kelompok)"]
    Step3 --> Step4["Tahap 4: Asisten MUK & Multi-Versi<br/>(Tarik BV/PP ke IA.02, IA.03, IA.06)"]
    Step4 --> Step5["Tahap 5: Pracetak A4 Buku Kerja<br/>(Verifikasi Portrait vs Landscape)"]
    Step5 --> Step6["Tahap 6: Ekspor Dokumen Word (.docx) & .ZIP<br/>(01_FR.APL.01 s/d 25_FR.VA)"]
    Step6 --> Step7["Tahap 7: Uji REST API v1 (Swagger UI)<br/>(Endpoint /api/v1/... dengan API Key)"]
    Step7 --> Step8["Tahap 8: Otomasi Unit Tests<br/>(python -m unittest discover tests)"]
    Step8 --> Finish(["Pengujian Selesai (100% Lulus)"])
```

---

## 2. Matriks Akun Uji Coba

| Peran | Username | Password | Deskripsi Tugas |
| :--- | :--- | :--- | :--- |
| **Kurator Master (Admin)** | `admin` | `admin123` | Mengelola dokumen SKKNI, kurasi status regulasi Kemnaker, manajemen API Key. |
| **Penyusun Skema / Asesor** | `asesor` | `asesor123` | Mengelola skema sertifikasi, kelompok pekerjaan, instrumen MUK, cetak & ekspor dokumen. |
| **API Client Eksternal** | *API Key* | `skkni_live_secret_key_bnsp2023` | Sinkronisasi MUK ke plugin WordPress LSP atau SIMLSP. |

---

## 3. Langkah Kerja Pengujian Terinci

### Tahap 1: Pengujian Otentikasi & Hak Akses (RBAC)
1. **Buka Aplikasi**: Akses [http://127.0.0.1:8000/](http://127.0.0.1:8000/).
2. **Uji Login Asesor**:
   - Klik tombol **"Masuk"** di pojok kanan atas (atau buka `/login`).
   - Masukkan `asesor` / `asesor123`.
   - **Hasil yang Diharapkan**: Berhasil masuk, di pojok kanan atas muncul nama *"Asesor Kompetensi"* dengan badge hijau `ASESOR` dan tombol *"Keluar"*.
3. **Uji Pembatasan Hak Asesor**:
   - Buka salah satu dokumen SKKNI di `/skkni/skkni_2019_109_broadcasting`.
   - **Hasil yang Diharapkan**: Form kurasi regulasi tidak muncul (hanya dapat melihat data).
4. **Uji Ganti Akun Admin**:
   - Klik tombol *"Keluar"* (Logout).
   - Masuk kembali menggunakan `admin` / `admin123`.
   - **Hasil yang Diharapkan**: Header menampilkan badge kuning `ADMIN`.

---

### Tahap 2: Katalog SKKNI & Kurasi Regulasi Kemnaker
1. **Buka Menu Dokumen SKKNI**: Akses [http://127.0.0.1:8000/skkni](http://127.0.0.1:8000/skkni).
   - **Hasil yang Diharapkan**: Kolom *"Status Kemnaker"* tampil dengan badge hijau `✓ Berlaku` atau merah `⛔ Dicabut`.
2. **Uji Kurasi Status Regulasi (Khusus Admin)**:
   - Klik salah satu SKKNI (misal: *Broadcasting TV*).
   - Gulir ke panel bawah **"Kurasi Status Regulasi SKKNI"**.
   - Pilih opsi **"⛔ Dicabut / Digantikan"**, isi nomor Kepmenaker pengganti (misal: `KEP.999/MEN/2026`), lalu klik tombol **"Simpan Perubahan Regulasi"**.
   - **Hasil yang Diharapkan**: Notifikasi hijau sukses muncul, dan status langsung berubah menjadi `⛔ Dicabut` beserta rujukan Kepmen pengganti.

---

### Tahap 3: Pengelompokan Pekerjaan & Multi-Versi MUK
1. **Buka Skema Sertifikasi**: Akses [http://127.0.0.1:8000/skema](http://127.0.0.1:8000/skema).
2. **Buka Editor MUK**: Klik tombol **"Kelola Buku Kerja MUK"** pada skema yang tersedia (misal *Social Media Marketing*).
3. **Uji Fitur Multi-Versi**:
   - Perhatikan kotak dropdown **"Versi MUK:"** di bagian atas.
   - Pilihan varian paket MUK (misal *Versi 1 - Draf Awal MUK*) aktif dari database SQLite.
4. **Uji Kelompok Pekerjaan**:
   - Pastikan setiap unit kompetensi terpetakan ke kelompok kerja (misal: *Kelompok 1: Pengelolaan Konten & Media Sosial*).
   - Indikator cakupan unit menampilkan `100% (Semua unit telah terpetakan)`.
5. **Uji Asisten BV & PP (Generator 1-Klik)**:
   - Klik tombol **"Tarik dari Batasan Variabel SKKNI"** pada instrumen `FR.IA.02`. Daftar peralatan dan perlengkapan otomatis terisi dari SKKNI.
   - Klik tombol **"Tarik dari Aspek Kritis & Sikap SKKNI"** pada instrumen `FR.IA.03` / `FR.IA.06` / `FR.IA.07`. Draf pertanyaan dan kunci jawaban otomatis terisi.
6. **Simpan Konfigurasi MUK**: Klik tombol **"Simpan Seluruh Konfigurasi MUK"**.
   - **Hasil yang Diharapkan**: Notifikasi tersimpan muncul dan data tersimpan aman di SQLite `muk_versi` serta file JSON.

---

### Tahap 4: Pracetak Buku Kerja & Ukuran Kertas A4 (BNSP V.2023)
1. **Buka Halaman Cetak Buku Kerja**:
   - Dari editor MUK, klik tombol **"Cetak Buku Kerja (HTML)"** atau langsung buka:
     [http://127.0.0.1:8000/skema/ad086999cce24093ae152b7bb4f51240/cetak-apl?doc=all](http://127.0.0.1:8000/skema/ad086999cce24093ae152b7bb4f51240/cetak-apl?doc=all)
2. **Verifikasi Orientasi Layar**:
   - Formulir teks (`FR.APL.01`, `FR.APL.02`, `FR.AK.01`) tampil tegak sebagai **A4 Portrait (210 mm)**.
   - Formulir tabel lebar (`FR.MAPA.01`, `Peta Kelompok Pekerjaan`, `FR.MAPA.02`, `FR.IA.01`) otomatis **melebar utuh sebagai A4 Landscape (297 mm)**.
3. **Uji Filter Mode Dokumen & Metode**:
   - Ubah dropdown dokumen ke **"Observasi Langsung (CLO + TPD + PMO)"** atau **"FR.MAPA.01"**.
   - **Hasil yang Diharapkan**: Halaman otomatis menyaring dan hanya menampilkan paket formulir yang dipilih.
4. **Uji Fitur Cetak Browser (`Ctrl + P`)**:
   - Tekan `Ctrl + P` pada keyboard.
   - Periksa print preview: Browser otomatis memilih layout A4 dan menyesuaikan lembar landscape tanpa memotong kolom tabel.

---

### Tahap 5: Ekspor Berkas Word (.docx) & Arsip .ZIP
1. **Uji Ekspor Word (.docx)**:
   - Pada bar atas halaman cetak, klik tombol hijau **"Unduh .DOCX"**.
   - Buka berkas `.docx` yang terunduh di Microsoft Word atau LibreOffice.
   - **Hasil yang Diharapkan**: Dokumen rapi, tabel bergaris presisi, dan halaman otomatis berpindah orientasi (Landscape saat MAPA/IA.01 dan Portrait saat formulir teks).
2. **Uji Ekspor Bundel .ZIP**:
   - Klik tombol ungu **"Unduh .ZIP"**.
   - Ekstrak berkas `.zip`.
   - **Hasil yang Diharapkan**: Berisi berkas-berkas Word satuan bernomor urut resmi:
     - `01_FR.APL.01_Permohonan_Sertifikasi_Kompetensi.docx`
     - `02_FR.APL.02_Asesmen_Mandiri.docx`
     - `04_FR.MAPA.01_Merencanakan_Aktivitas_dan_Proses_Asesmen.docx` *(Landscape)*
     - `05c_Peta_Kelompok_Pekerjaan.docx` *(Landscape)*
     - `06_FR.MAPA.02_Peta_Instrumen_Asesmen.docx` *(Landscape)*
     - `10_FR.IA.01_CL_Ceklis_Observasi_Aktivitas.docx` *(Landscape)*
     - `11_FR.IA.02` s/d `25_FR.VA.docx` (termasuk formulir kosongan `FR.VA`).
     - `00_Buku_Kerja_Lengkap_Gabungan.docx`.

---

### Tahap 6: Pengujian REST API v1 Terintegrasi (Swagger UI)
1. **Buka Swagger UI**: Akses [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).
2. **Otentikasi Kunci API**:
   - Klik tombol **"Authorize"** di pojok kanan atas Swagger UI.
   - Pada field `ApiKeyAuth (apiKey)` atau `BearerAuth (http)`, masukkan kunci default:
     ```text
     skkni_live_secret_key_bnsp2023
     ```
   - Klik **Authorize** lalu **Close**.
3. **Uji Coba Endpoint**:
   - **`GET /api/v1/status`**: Klik *Try it out* -> *Execute*. Response mengembalikan status `200 OK` dengan informasi klien *"WordPress LSP Plugin"*.
   - **`GET /api/v1/skkni`**: Response mengembalikan daftar dokumen SKKNI beserta status regulasi Kemnaker.
   - **`GET /api/v1/skema/{schema_id}/muk`**: Masukkan ID skema `ad086999cce24093ae152b7bb4f51240` -> Response mengembalikan JSON siap sinkronisasi untuk WordPress LSP (Kelompok Pekerjaan, Instrumen IA.01–11, dan referensi BV/PP).
   - **`POST /api/v1/documents/render`**: Kirim payload JSON untuk merender formulir ke HTML atau DOCX dari aplikasi eksternal.

---

### Tahap 7: Otomasi Pengujian Sistem (Unit Testing di Terminal)
Jalankan perintah berikut di terminal proyek:

```bash
cd /home/muhadi/Projects/skkni-extractor
.venv/bin/python -m unittest discover tests
```

**Kriteria Keberhasilan**:
- Seluruh 26 unit test (mencakup auth, SQLite, multi-versi MUK, REST API v1, template cetak, dan generator docx) lulus 100%:
  ```text
  Ran 26 tests in ~5.6s
  OK
  ```

---

## 4. Lembar Ceklis Pengujian Mandiri (Testing Checklist)

| No | Modul / Fitur | Status Uji | Catatan / Hasil |
| :---: | :--- | :---: | :--- |
| 1 | Login Asesor (`asesor` / `asesor123`) | [ ] Lulus | Hak akses terbatas ke skema & MUK |
| 2 | Login Admin (`admin` / `admin123`) | [ ] Lulus | Akses penuh termasuk kurasi regulasi SKKNI |
| 3 | Perubahan status regulasi SKKNI Kemnaker | [ ] Lulus | Badge Berlaku / Dicabut terupdate |
| 4 | Pemetaan unit ke Kelompok Pekerjaan | [ ] Lulus | Indikator cakupan unit 100% |
| 5 | Asisten BV & PP generator 1-klik | [ ] Lulus | Alat, bahan, dan pertanyaan terisi otomatis |
| 6 | Penyimpanan Multi-Versi Paket MUK | [ ] Lulus | Tersimpan terpisah di SQLite `muk_versi` |
| 7 | Tampilan layar A4 Portrait (210mm) | [ ] Lulus | APL.01, APL.02, AK, IA.02 s/d VA |
| 8 | Tampilan layar A4 Landscape (297mm) | [ ] Lulus | MAPA.01, Peta Kelompok, MAPA.02, IA.01 |
| 9 | Cetak Browser (`Ctrl + P`) A4 Otomatis | [ ] Lulus | Halaman tabel tidak terpotong |
| 10 | Unduh berkas Word (.docx) & .ZIP urut | [ ] Lulus | Berkas 01 s/d 25 tersusun rapi |
| 11 | REST API v1 & Swagger UI di `/docs` | [ ] Lulus | Autentikasi `X-API-Key` terverifikasi |
| 12 | Seluruh 26 Unit Tests di Terminal | [ ] Lulus | `OK` tanpa error |

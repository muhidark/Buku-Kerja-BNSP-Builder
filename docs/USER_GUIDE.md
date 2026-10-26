# Panduan Pengguna — SKKNI Extractor v1.0.0

Aplikasi **SKKNI Extractor** digunakan untuk mengelola dokumen PDF SKKNI, memadukan dokumen skema sertifikasi, mengekstrak unit kompetensi menjadi JSON terstruktur, dan menghasilkan dokumen Microsoft Word (`.docx`) berstandar resmi.

---

## Alur Kerja Utama

```
1. Upload PDF SKKNI
       │
       ▼
2. Identifikasi Unit Otomatis
       │
       ▼
3. Upload Dokumen Skema (.docx)
       │
       ▼
4. Pencocokan Unit Kompetensi
       │
       ▼
5. Ekstraksi Unit (Background Job)
       │
       ▼
6. Validasi Struktur & Kelengkapan KUK
       │
       ▼
7. Preview & Verifikasi Hasil
       │
       ▼
8. Generate Dokumen Word (.docx) & Unduh
```

---

## 1. Mengelola Dokumen SKKNI (`/skkni`)

1. Akses menu **Dokumen SKKNI** pada navigasi atas.
2. **Unggah PDF**:
   - Klik area unggah atau pilih berkas PDF SKKNI (maksimal 50 MB).
   - Sistem akan memverifikasi integritas berkas PDF dan menghitung hash SHA-256. Berkas duplikat akan otomatis ditolak untuk mencegah redundansi.
3. **Identifikasi Unit Otomatis**:
   - Setelah berkas diunggah, aplikasi secara otomatis memindai daftar isi dan isi PDF untuk mengidentifikasi kode unit, judul unit, serta rentang halaman (0-based index).
4. Klik pada baris dokumen untuk melihat daftar unit kompetensi yang terdeteksi di dalam dokumen tersebut.

---

## 2. Mengelola Skema Sertifikasi (`/skema`)

1. Akses menu **Skema Sertifikasi**.
2. **Unggah Skema (.docx)**:
   - Pilih berkas dokumen skema sertifikasi Microsoft Word (maksimal 20 MB).
   - Sistem membaca tabel kemasan/paket kompetensi pada dokumen skema untuk mengekstrak nomor urut, kode unit, dan judul skema.
3. **Pencocokan Kode Unit**:
   - Aplikasi mencocokkan setiap kode unit di dokumen skema ke repositori PDF SKKNI yang tersedia.
   - Status pencocokan:
     - `ditemukan`: Unit ditemukan secara persis di salah satu PDF SKKNI.
     - `belum_ditemukan`: Unit belum memiliki PDF SKKNI sumber di perpustakaan.
     - `konflik`: Unit ditemukan di lebih dari satu dokumen PDF SKKNI.

---

## 3. Ekstraksi Unit Kompetensi

1. Buka halaman detail skema yang ingin diproses (`/skema/{id}`).
2. Anda dapat mengekstrak:
   - **Satu unit tertentu**: Klik tombol *Ekstrak* pada baris unit yang diinginkan.
   - **Seluruh unit sekaligus**: Klik tombol *Ekstrak Semua Unit*.
3. Sistem akan memulai **Background Extraction Job** (dikelola oleh *Job Manager* dengan batas 2 worker paralel).
4. Pengguna diarahkan ke halaman pemantauan progres (`/job/{job_id}`). Anda dapat melihat progres per unit secara langsung tanpa memblokir server.
5. Saat server dijalankan ulang, status pekerjaan lama akan dipulihkan secara aman.

---

## 4. Validasi dan Preview Hasil Ekstraksi (`/unit`)

1. Pada halaman detail skema atau menu **Unit Kompetensi**, klik tombol *Preview* pada unit yang telah diekstrak.
2. Halaman preview menampilkan:
   - Metadata unit (Kode, Judul, Deskripsi Unit).
   - Tabel Elemen Kompetensi dan Kriteria Unjuk Kerja (KUK).
   - Batasan Variabel (struktur pohon bernomor lengkap).
   - Panduan Penilaian (aspek kritis, kondisi pengujian, dsb.).
3. **Status Validasi**:
   - `valid_struktur`: Struktur tabel, elemen, dan penomoran pohon konsisten.
   - `valid_kelengkapan`: Nomor KUK terbukti lengkap dan berurutan sesuai sumber PDF.
   - `perlu_verifikasi`: Terdapat anomali pemformatan pada PDF sumber yang memerlukan pemeriksaan visual.

---

## 5. Pembuatan dan Pengunduhan Dokumen Word (`/hasil`)

1. Buka halaman detail skema (`/skema/{id}`).
2. Pada panel **Buat Dokumen Word**:
   - Pilih unit-unit yang ingin disertakan ke dalam dokumen kompilasi.
   - Bila terdapat unit dengan status *perlu_verifikasi*, centang persetujuan eksplisit untuk menyertakannya sebagai *draft*.
   - Klik **Buat Dokumen Word**.
3. Sistem mengompilasi unit-unit tersebut menjadi satu berkas Word (`.docx`):
   - Format kertas F4 (21,5 × 33,0 cm), margin resmi.
   - Tipografi Bookman Old Style 11 pt dengan spasi rapi.
   - XML *Word Multilevel Numbering* yang terisolasi per unit sehingga penomoran selalu dimulai ulang dari 1 di setiap unit.
   - *Hanging indent* adaptif agar jarak nomor ke teks konsisten dan tidak melompat.
4. Akses menu **Hasil Ekstraksi** (`/hasil`) untuk melihat riwayat dokumen yang telah dibuat.
5. Klik **Unduh Berkas (.docx)** untuk menyimpan berkas Word ke komputer Anda.

# Catatan Perbaikan Teknis (Fase 4F) — SKKNI Extractor & Pembuat Buku Kerja

**Tanggal Penyelesaian:** 26 Oktober 2026  
**Status:** Selesai Diperbaiki & Lulus Uji Otomatis 100%  
**Referensi Commit Git:**
- Baseline sebelum perbaikan: `dbec53b` (*"Baseline awal sebelum implementasi perbaikan Fase 4F"*)
- Implementasi Fase 4F: `d7a0527` (*"Implementasi Fase 4F: Gerbang Dokumen, status 3-tingkat terpadu, editor koreksi per-unit, dan deteksi konflik"*)

---

## 1. Daftar Temuan Bug yang Telah Diselesaikan

Seluruh **5 temuan bug & celah kualitas data** dari audit sebelumnya telah diselesaikan secara tuntas:

| No | Temuan Bug Sebelumnya | Penyebab Akar Masalah | Solusi yang Diterapkan | Status |
| :-: | :--- | :--- | :--- | :-: |
| **1** | **Satu unit memiliki 3 status berbeda di 3 halaman** (mis. hijau *Terdeteksi* di `/skkni`, hijau *Cocok* di `/skema`, padahal isi JSON `0 elemen / gagal_ekstraksi`) | Masing-masing halaman menghitung lencana status sendiri-sendiri tanpa memeriksa isi elemen/KUK aktual di disk. | Dibuat satu sumber kebenaran tunggal di `app/status_units.py` dengan fungsi `status_unit()` dan partial `app/templates/_status_badge.html` yang dipakai seragam di halaman SKKNI, Skema, dan Pratinjau Unit. | **Selesai** |
| **2** | **Jebakan KUK Palsu (*Fake Placeholder*) pada Cetak Buku Kerja** | Di `app/buku_kerja.py`, bila unit gagal diekstrak (`elemen_list` kosong), kode menyuntikkan KUK palsu `"1.1 Menerapkan prosedur kerja sesuai standar yang berlaku."` | Blok *fallback* KUK palsu dihapus total dari `susun_data_buku_kerja()`. Jika ada unit berstatus `Gagal`, endpoint `/skema/{id}/cetak-apl` menolak pencetakan dengan **HTTP 409**. | **Selesai** |
| **3** | **Tidak ada Gerbang Dokumen (*Document Gate*) yang menahan unit gagal** | Pengguna masih bisa memaksa pembuatan dokumen meskipun ada unit dengan 0 elemen/KUK. | `evaluasi_gerbang_skema()` dan `document_service.buat_dokumen()` kini memblokir pembuatan dokumen di UI (tombol `disabled` + Dialog C3 daftar unit penahan) sekaligus di sisi server (**HTTP 409**, bahkan jika `draft=True` saat ada unit `Gagal`). | **Selesai** |
| **4** | **Tidak ada cara memperbaiki teks KUK/Elemen yang salah baca dari PDF** | "Verifikasi manual" hanya berupa tombol centang tanpa kemampuan menyunting teks KUK yang terpotong/meleset. | Dibuat modul `app/koreksi.py` dan halaman editor `app/templates/unit_koreksi.html` (`GET/POST /skema/{id}/unit/{kode}/koreksi`) dengan tautan langsung ke halaman PDF sumber (`/skkni/{doc_id}/pdf#page=X`). | **Selesai** |
| **5** | **Risiko kehilangan koreksi atau konflik diam-diam saat PDF diekstrak ulang** | Jika koreksi disimpan menimpa berkas mesin, ekstraksi ulang akan menghapus koreksi; sebaliknya jika tidak dicek, perubahan mesin tidak terdeteksi. | Koreksi disimpan terpisah di `data/json/koreksi/{kode_unit}.json` beserta `hash_hasil_mesin` (SHA-256 berkas mesin). Jika berkas mesin berubah karena ekstraksi ulang, sistem otomatis menandai **Konflik Koreksi** dan menampilkan perbandingan berdampingan (**Teks Mesin vs Teks Koreksi**). | **Selesai** |

---

## 2. Arsitektur Teknis & Berkas yang Ditambahkan / Diubah

### A. Modul Backend Baru
1. **`app/status_units.py`**
   - Menyediakan 3 status resmi yang mudah dipahami pengguna:
     - `siap` (**`● Siap dipakai`**, hijau) — Boleh masuk dokumen.
     - `perlu` (**`● Perlu diperiksa`**, kuning/amber) — Ditahan sampai dikoreksi atau diverifikasi manual.
     - `gagal` (**`● Gagal`**, merah) — Tidak boleh masuk dokumen (0 elemen/KUK atau belum diekstrak).
   - Fungsi utama:
     - `status_unit(kode_unit, ...)`: Mengevaluasi satu unit dengan urutan prioritas: (1) Koreksi manual & cek konflik hash, (2) Status pencocokan skema, (3) Ketersediaan berkas JSON, (4) Validasi struktur & kelengkapan KUK.
     - `evaluasi_gerbang_skema(schema_id, kode_terpilih)`: Mengevaluasi seluruh unit dalam skema dan menghasilkan ringkasan `{total, siap, perlu, gagal}` beserta daftar `penahan`.

2. **`app/koreksi.py`**
   - Menyimpan koreksi manual secara atomik (`tmp` + `os.replace`) di `data/json/koreksi/{kode_unit}.json` **tanpa pernah mengubah** berkas asli di `data/json/browser_extraction/`, `schema_content_creator/`, atau `cross_skkni/`.
   - Struktur berkas `data/json/koreksi/{kode_unit}.json`:
     ```json
     {
       "kode_unit": "J.63OPR00.005.2",
       "dikoreksi_pada": "2026-10-26T13:31:20",
       "oleh": "muhadi",
       "hash_hasil_mesin": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
       "judul_unit": "Mengoperasikan Piranti Lunak Pengolah Kata Tingkat Maju",
       "elemen": [
         {
           "nomor": 1,
           "nama": "Mengidentifikasi perangkat lunak...",
           "kuk": [
             {
               "nomor": "1.1",
               "uraian": "Perangkat lunak diidentifikasi sesuai spesifikasi teknis."
             }
           ]
         }
       ]
     }
     ```
   - Fungsi utama:
     - `ambil_unit_final(kode_unit)`: Menggabungkan JSON mesin dengan koreksi manual (menyimpan elemen asli mesin di `_elemen_mesin` dan metadata perbandingan di `_koreksi`).
     - `simpan_koreksi(kode_unit, elemen, oleh, judul_unit)`: Menyimpan koreksi tanpa memangkas karakter isi (`\r\n` dinormalisasi ke `\n`).
     - `hapus_koreksi(kode_unit)`: Menghapus koreksi dan mengembalikan unit ke hasil mesin.
     - `pertahankan_koreksi(kode_unit)`: Menyelesaikan konflik dengan memperbarui `hash_hasil_mesin` ke SHA-256 berkas mesin terbaru.
     - `bandingkan_mesin_dan_koreksi(elemen_mesin, elemen_koreksi)`: Menyusun diff per elemen dan per KUK untuk tampilan audit berdampingan.

### B. Integrasi ke Modul Eksportir & Generator Dokumen
- **`app/lsp_exporter.py`**: `ambil_json_unit()` kini memanggil `koreksi.ambil_unit_final()` sehingga fitur **Salin JSON LSP** dan **Salin Teks Smart Paste** otomatis memakai teks yang sudah dikoreksi.
- **`app/multi_docx_generator.py`**: `_muat_unit()` menerapkan `koreksi.terapkan_koreksi_ke_data()` sehingga dokumen `.docx` yang diunduh memuat teks KUK hasil koreksi.
- **`app/buku_kerja.py`**: `susun_data_buku_kerja()` memakai `ambil_json_unit()` (termasuk koreksi) dan menyertakan objek `gerbang`.
- **`app/services/document_service.py`**: `validasi()` dan `buat_dokumen()` mengenali koreksi aktif sebagai penyelesaian masalah struktur/kelengkapan, mendeteksi `konflik_koreksi`, dan menolak paksaan pembuatan dokumen bila masih ada unit `Gagal`.

### C. Endpoint / Rute Baru di `app/main.py`
| Metode | Path Rute | Fungsi Handler | Keterangan |
| :--- | :--- | :--- | :--- |
| `GET` | `/skkni/{doc_id}/pdf` | `buka_pdf_skkni()` | Menyajikan berkas PDF SKKNI secara `inline` agar tautan `#page=N` langsung membuka halaman ke-`N` di tab browser. |
| `GET` | `/skema/{schema_id}/unit/{kode_unit}/koreksi` | `halaman_koreksi_unit()` | Menampilkan halaman editor koreksi KUK & elemen beserta tabel perbandingan mesin vs koreksi. |
| `POST` | `/skema/{schema_id}/unit/{kode_unit}/koreksi` | `simpan_koreksi_unit()` | Menyimpan koreksi manual atau menyelesaikan konflik (`aksi=pertahankan`). Dilindungi token CSRF. |
| `POST` | `/skema/{schema_id}/unit/{kode_unit}/koreksi/kembalikan` | `kembalikan_koreksi_unit()` | Menghapus berkas koreksi dan mengembalikan unit ke hasil ekstraksi mesin. Dilindungi token CSRF. |
| `GET` | `/api/unit/{kode_unit}/status` | `api_status_unit()` | Mengembalikan JSON status 3-tingkat untuk satu unit kompetensi. |

---

## 3. Cara Menjalankan Pengujian Otomatis (Untuk Teknisi Programmer)

Programmer dapat menjalankan perintah berikut dari direktori root proyek (`/home/muhadi/Projects/skkni-extractor`):

```bash
# 1. Uji Gerbang Dokumen & Konsistensi Status 3-Tingkat (27 pemeriksaan)
PYTHONPATH=. .venv/bin/python tests/test_gerbang_dokumen.py

# 2. Uji Editor Koreksi Per-Unit, Presisi Karakter, & Ekspor (23 pemeriksaan)
PYTHONPATH=. .venv/bin/python tests/test_koreksi.py

# 3. Uji Audit Riwayat & Deteksi Konflik Ekstraksi Ulang (16 pemeriksaan)
PYTHONPATH=. .venv/bin/python tests/test_koreksi_konflik.py

# 4. Uji Regresi Web & Fase 1-4E (62 + 40 + 41 + 4 pemeriksaan)
PYTHONPATH=. .venv/bin/python tests/test_web.py
PYTHONPATH=. .venv/bin/python tests/test_document_service.py
PYTHONPATH=. .venv/bin/python tests/test_document_download.py
PYTHONPATH=. .venv/bin/python tests/test_buku_kerja.py
```

---

## 4. Apa Langkah Berikutnya? (Peta Jalan Pengembangan Selanjutnya)

Setelah fondasi kualitas data & koreksi manual (**Fase 4F**) ini selesai dan stabil, langkah pengembangan berikutnya sesuai dokumen rencana besar (`docs/RENCANA_PENGEMBANGAN_BUKU_KERJA.md`) adalah:

1. **Tahap 2 — Penyempurnaan Template Cetak `FR.APL.01` & `FR.APL.02` Siap Print (100% Kosong untuk Peserta)**
   - Memastikan tata letak cetak (`@media print` & ekspor `.docx`) untuk **FR.APL.01** dan **FR.APL.02** sesuai persis dengan contoh dokumen acuan LSP (murni template siap print untuk diisi peserta secara manual, sedangkan Nama Asesor, No. MET, Nomor Skema, serta tabel Elemen & KUK terisi otomatis dari aplikasi).
2. **Tahap 3 — Generator Buku Kerja Asesor & Dokumen Asesmen (`FR.MAPA`, `FR.AK`, `FR.IA`)**
   - Menambahkan generator template dokumen asesmen lanjutan yang menarik Elemen & KUK yang sudah tervalidasi/dikoreksi:
     - **Kelompok Administrasi & Keputusan (`FR.AK`):** `FR.AK.01` (Persetujuan Asesmen), `FR.AK.02` (Rekaman Asesmen Kompetensi — otomatis memuat daftar Judul Unit skema), `FR.AK.03` (Umpan Balik), `FR.AK.04` (Banding).
     - **Kelompok Perencanaan (`FR.MAPA.01` & `FR.MAPA.02`).**
     - **Kelompok Instrumen Asesmen (`FR.IA`):** `FR.IA.01` (Ceklis Observasi Aktivitas di Tempat Kerja — otomatis menarik tabel Elemen & KUK), `FR.IA.02` (Tugas Praktik Demonstrasi), `FR.IA.03` (Pertanyaan untuk Mendukung Observasi).
3. **Tahap 4 — Fitur *One-Click ZIP Bundle* per Skema**
   - Tombol **"Unduh Paket Lengkap Skema (.ZIP)"** yang langsung menghasilkan struktur folder bernomor (`01. FR.APL.01...`, `02. FR.APL.02...`, `03. FR.MAPA.01...`, dst.) siap cetak untuk satu skema penuh.
4. **Tahap 5 — Penerapan Mode *Read-Only Publik + Login Admin* (Saat Aplikasi Dibuka untuk Banyak Pengguna)**
   - Mengunci rute pengubahan data (Unggah PDF/Skema, Ekstrak, Koreksi Manual, Hapus) dengan sesi login Admin LSP, sementara Asesor/Staf tetap dapat membuka halaman skema, mengisi Nama Asesor & No. MET mereka sendiri, lalu mengunduh/mencetak paket Buku Kerja tanpa risiko merusak database SKKNI & Skema.

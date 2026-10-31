# PROMPT UNTUK DEVELOPER — Instrumen per Kelompok Pekerjaan

> Cara pakai: kirim seluruh isi dokumen ini (mulai dari bagian "Peran" di bawah) ke developer /
> agen coding Anda. Minta dia **menjawab dengan rencana dulu, belum menulis kode**. Setelah rencananya
> disetujui, baru implementasi bertahap.

---

## Peran

Anda bekerja pada aplikasi **Buku Kerja Builder** (FastAPI + Jinja2 + penyimpanan JSON + SQLite,
repo `skkni-extractor`). Tugas Anda: mengubah struktur data dan UI agar instrumen asesmen
**FR.IA.01, FR.IA.02, FR.IA.03 disimpan per Kelompok Pekerjaan**, bukan satu set untuk seluruh
skema. **FR.IA.04A/04B (DIT) dan FR.IA.05–IA.08 tetap di level MUK** — DIT adalah satu kasus
berbasis analisis data, bukan per kelompok.

Sebelum menulis kode, bacalah dulu: `app/buku_kerja.py`, `app/routes/skema.py`,
`app/templates/buku_kerja/_form_ia0*.html`, dan `app/schema_library.py`.

---

## Masalah yang harus diperbaiki

Saat ini konfigurasi MUK disimpan seperti ini (akar objek MUK):

```json
{
  "personel": { "...": "..." },
  "kelompok_pekerjaan": [
    { "id": "kp_1", "nama": "Kelompok Pekerjaan 1 (...)", "urutan": 1,
      "units": ["M.70HMS00.005.3", "M.70HMS00.025.3"] },
    { "id": "kp_2", "nama": "Kelompok Pekerjaan 2 (...)", "urutan": 2,
      "units": ["M.70HMS00.026.1"] }
  ],
  "ia02": { "skenario": "...", "langkah_kerja": "...", "perlengkapan": "...", "peralatan": "...", "durasi_waktu": "120 Menit" },
  "ia03": { "panduan": "", "questions": [ ... ] },
  "ia04": { "judul_kegiatan": "...", "situasi": "...", "questions": [ ... ] },
  "ia05": { ... }, "ia06": { ... }, "ia07": { ... }, "ia08": { ... }
}
```

Akibatnya, untuk skema dengan 2–3 kelompok:

1. **Satu skenario TPD (IA.02) dipakai untuk semua kelompok.** Padahal tiap kelompok adalah satu
   kesatuan pekerjaan yang berbeda, sehingga seharusnya punya skenario, langkah kerja, keluaran
   (`hasil_kerja`), perlengkapan, peralatan, dan durasi sendiri.
2. **Durasi tidak bisa dijumlahkan per kelompok.** `durasi_waktu` hanya satu nilai, sementara total
   waktu asesmen = jumlah durasi seluruh kelompok.
3. **Pertanyaan IA.03 tidak bisa menempel ke kelompoknya** sehingga menjadi generik, dan
   `elemen_kuk` diisi kode unit (mis. `M.70HMS00.005.3`) padahal semestinya nomor KUK (`1.1`).
4. Teks default di `buku_kerja.py` membuktikan masalah ini: *"Anda diharapkan mampu mendemonstrasikan
   **seluruh** tugas praktik sesuai dengan kelompok pekerjaan di atas…"* — satu skenario untuk semua
   kelompok.

Fungsi `susun_kelompok_pekerjaan_cetak()` sudah menyusun kelompok untuk keperluan cetak
(MAPA.01, MAPA.02, IA.01, IA.02, IA.03, IA.04A, IA.04B, Peta Kelompok), tetapi datanya tetap
diambil dari objek tunggal di akar MUK.

---

## Aturan domain yang wajib dipenuhi (jangan diubah tanpa persetujuan)

- **1 kelompok pekerjaan = 1 pekerjaan utuh**: masukan → proses → keluaran, punya deliverable.
- **1 kelompok = 1 set instrumen praktik**: satu skenario IA.02, satu set pertanyaan IA.03, satu
  rangkaian indikator IA.01. **DIT (IA.04A/04B) tidak per kelompok**: satu kasus per skema, wajib
  menyertakan paket data yang dianalisis peserta (brief, keluhan, analitik, hasil uji).
- **Durasi total asesmen = jumlah durasi tiap kelompok.** Nilai per kelompok harus dijumlahkan dan
  ditampilkan sebagai total.
- **IA.05 / IA.06 / IA.07 / IA.08 tetap di level MUK** (tertulis, lisan, ceklis portofolio bersifat
  satu paket per skema/asesi). Jangan dipindah.
- **Penempatan dimensi kompetensi harus divalidasi**:
  - instrumen praktik (IA.01, IA.02, IA.04A, IA.04B): **TS, TMS, JRES**
- IA.03 (PMO) ikut praktik, tetapi isinya bertumpu **TRS, CMS** (situasi berbeda / fungsi gagal), dan
  tidak boleh menanyakan ulang apa yang sudah terlihat dipraktikkan
  - instrumen tanya jawab (IA.05, IA.06, IA.07): **TRS, CMS**
  - satu pertanyaan boleh punya lebih dari satu dimensi (`"(TS, TMS)"`).

---

## Perubahan data model yang diminta

Target struktur (versi skema MUK = 2):

```json
{
  "schema_muk_version": 2,
  "personel": { "...": "..." },
  "kelompok_pekerjaan": [
    {
      "id": "kp_1",
      "nama": "Kelompok Pekerjaan 1 (...)",
      "urutan": 1,
      "units": ["M.70HMS00.005.3", "M.70HMS00.025.3"],
      "instrumen": {
        "ia01": { "indikator": [ { "order": 1, "indikator": "...", "kuk": "1.1" } ] },
        "ia02": {
          "skenario": "", "langkah_kerja": "", "hasil_kerja": "",
          "perlengkapan": "", "peralatan": "",
          "durasi_menit": 90,
          "langkah": [ { "order": 1, "kode": "K1-1", "uraian": "", "menit": 10, "kuk": ["1.1"] } ]
        },
        "ia03": { "panduan": "", "questions": [ { "order": 1, "dimensi": "TRS", "pertanyaan": "", "kunci_jawaban": "", "kuk": ["2.1"] } ] }
      }
    }
  ],

  "ia04a": {
    "judul_kegiatan": "", "situasi": "", "tugas": "", "tindakan": "",
    "data_informasi": "", "hasil": "", "hal_demonstrasi": "",
    "waktu_proyek": "", "waktu_presentasi": "",
    "peta_unit": ["M.70HMS00.005.3"],
    "paket_data": [
      { "nama": "Brief klien", "jenis": "dokumen", "wajib": true },
      { "nama": "Keluhan pengguna verbatim", "jenis": "data", "wajib": true },
      { "nama": "Data analitik / funnel", "jenis": "data", "wajib": true }
    ],
    "questions": [ { "order": 1, "lingkup": "", "pertanyaan": "", "kuk": ["1.1","1.2"], "dimensi": "(TS, TMS)" } ]
  },
  "ia04b": { "questions": [ { "order": 1, "kriteria": "", "kuk": ["1.1"], "pencapaian": "" } ] },

  "ia05": { ... }, "ia06": { ... }, "ia07": { ... }, "ia08": { ... }
}
```

Ketentuan:

- **Jangan mengganti nama field di dalam `ia02`/`ia03`/`ia04`** (`skenario`, `langkah_kerja`,
  `hasil_kerja`, `perlengkapan`, `peralatan`, `judul_kegiatan`, `situasi`, `tugas`, `tindakan`,
  `data_informasi`, `hasil`, `hal_demonstrasi`, `waktu_proyek`, `waktu_presentasi`, `questions`,
  `lingkup`, `pertanyaan`, `elemen_kuk`, `dimensi`). Yang berubah hanya **lokasinya** (pindah ke
  `kelompok_pekerjaan[i].instrumen`) dan penambahan field baru.
- `durasi_waktu` (string "120 Menit") tetap dipertahankan untuk kompatibilitas cetak, tetapi
  tambahkan `durasi_menit` (integer) agar bisa dijumlahkan.
- `elemen_kuk` tetap ada (kompatibilitas), tetapi tambahkan `kuk` berupa **array nomor KUK**.
  Isi `elemen_kuk` dengan gabungan nomor KUK (`"1.1; 1.2"`), **bukan kode unit**.

---

## Migrasi data lama (wajib idempoten)

Ada **dua tempat penyimpanan** yang harus ikut dimigrasi — jangan hanya salah satu:

1. berkas `data/schema_library/muk/<schema_id>.json`
2. tabel SQLite `muk_versi`, kolom `data_json` (versi MUK tersimpan)

Aturan migrasi:

- Jika `schema_muk_version` belum ada atau < 2:
  - **1 kelompok**: salin `ia02`, `ia03`, `ia04` dari akar ke `kelompok_pekerjaan[0].instrumen`
    (`ia04` → `ia04a`, plus `ia04b` bila ada). Hapus dari akar **hanya setelah** salinan terverifikasi.
  - **lebih dari 1 kelompok**: salin ke kelompok pertama, tandai kelompok lain
    `instrumen_status: "belum_diisi"`, dan tambahkan peringatan di UI:
    *"MUK ini dibuat sebelum pemisahan instrumen per kelompok — periksa tiap kelompok."*
  - Migrasi harus aman dijalankan berulang (idempoten), mencatat log, dan **membuat backup**
    (`tools/backup.py`) sebelum menulis.
- Bacaan lama (tanpa `instrumen`) harus tetap bisa dibuka: sediakan fungsi pembaca kompatibel yang
  mengembalikan struktur baru dengan fallback ke akar.

---

## API dan route

- `POST /skema/{schema_id}/simpan-muk-bagian` — terima payload baru per kelompok, mis.
  `{ "kelompok_id": "kp_1", "bagian": "ia02", "data": { ... } }` untuk IA.01/IA.02/IA.03. DIT
  (IA.04A/04B) disimpan tanpa `kelompok_id` karena satu kasus per skema. Pertahankan dukungan payload lama
  (tanpa `kelompok_id`) → diarahkan ke kelompok pertama.
- `POST /skema/{schema_id}/simpan-kelompok-kerja` — tetap, tetapi saat kelompok dihapus/ditambah,
  instrumen di dalamnya ikut dipindah/dihapus dengan konfirmasi.
- `GET /api/v1/skema/{schema_id}/muk` — tambahkan blok `kelompok_pekerjaan[].instrumen`. Jangan hapus
  field akar pada respons ini (klien lama masih memakainya); beri tanda `deprecated: true`.
  Jika perlu bentuk murni baru, sediakan `/api/v2/skema/{schema_id}/muk`.
- **Temuan sampingan yang harus dibereskan:** `app/routes/skema.py` mendefinisikan
  `POST /skema/{schema_id}/simpan-muk-bagian` **dua kali** (sekitar baris 401 dan 567). Handler kedua
  tidak pernah terpanggil. Satukan jadi satu.

---

## UI

- Halaman MUK: **tab per kelompok pekerjaan** (nama kelompok + jumlah unit). Di dalam tiap tab:
  IA.01, IA.02, IA.03. DIT (IA.04A/04B) tetap satu panel di level MUK, dengan kolom **paket data**
  (daftar berkas yang dianalisis peserta).
- Panel ringkasan di atas: total durasi (jumlah `durasi_menit` semua kelompok), jumlah pertanyaan,
  dan status kelengkapan per kelompok.
- Tombol **"Salin instrumen dari kelompok lain"** — wajib konfirmasi, dan hanya menyalin field yang
  dipilih (bukan seluruh blok).
- Pertahankan penanda *unsaved changes* dan indikator loading yang sudah ada.
- Jangan mengubah tata letak/typography form cetak.

---

## Validasi yang harus ditambahkan

1. `sum(durasi_menit)` semua kelompok tampil sebagai total; kalau kosong, tampilkan peringatan.
2. Setiap pertanyaan IA.03 (per kelompok) dan IA.04A (level MUK) harus punya minimal satu nomor KUK
   yang valid; kalau masih berisi kode unit → tandai **peringatan** (bukan error keras).
   IA.04A wajib punya minimal satu entri `paket_data` bertanda `wajib: true` — DIT tanpa data
   yang dianalisis bukan DIT.
3. Dimensi wajib diisi; instrumen praktik memakai TS/TMS/JRES, instrumen tanya jawab TRS/CMS.
   Dimensi di luar aturan → peringatan.
4. Unit yang belum masuk kelompok mana pun tetap dilaporkan (`unassigned_units`) seperti sekarang.
5. Kelompok default otomatis (fallback di `susun_kelompok_pekerjaan_cetak`) harus diberi label
   jelas di dokumen: *"Kelompok Pekerjaan 1 (belum dikelompokkan — draf)"*.

---

## Cetak / ekspor

- **FR.IA.02 dicetak sebagai SATU berkas untuk seluruh skema**, bukan satu berkas per kelompok:
  tabel pengelompokan pekerjaan di depan, lalu tiap kelompok mendapat blok skenario/langkah/
  keluaran/perlengkapan/durasi sendiri di dalam berkas yang sama.
- IA.01 dan IA.03 mengikuti pola berkas yang sama: satu dokumen, blok per kelompok di dalamnya.
- `page_break_before` di awal tiap blok kelompok (bukan `page_break_after` di akhir, agar tidak
  muncul halaman kosong).
- Halaman ringkasan: daftar kelompok + durasi masing-masing + total.
- Ekspor ZIP: satu nama berkas per instrumen (mis. `IA02_TPD_<slug>.docx`), bukan per kelompok.

---

## Kriteria selesai (harus dibuktikan, bukan diklaim)

Buat fixture uji dengan **satu skema 2 kelompok** (mis. 2 unit + 2 unit), lalu:

1. Simpan IA.02 untuk kelompok 1 dan kelompok 2 dengan skenario berbeda → setelah reload, keduanya
   tetap berbeda (tidak saling menimpa).
2. `GET /api/v1/skema/{id}/muk` menampilkan instrumen di dalam tiap kelompok, dan masih menyertakan
   field akar yang lama.
3. Cetak PDF: kelompok 1 dan 2 masing-masing punya skenario sendiri, total durasi = jumlah keduanya,
   tidak ada halaman kosong, tidak ada tabel terpotong.
4. Migrasi MUK lama (1 kelompok, tanpa `schema_muk_version`) → data pindah ke kelompok 1, isi tidak
   berubah satu karakter pun, dan migrasi kedua kali tidak mengubah apa pun (idempoten).
5. Semua test yang ada (`pytest`) tetap lulus; tambahkan test baru: `test_instrumen_per_kelompok.py`,
   `test_migrasi_muk_v2.py`.
6. `ruff` dan `black` bersih.

---

## Cara kerja yang saya minta

1. **Balas dulu dengan rencana** (tanpa kode): daftar berkas yang akan diubah, bentuk payload baru,
   dan urutan langkah migrasi. Tunggu persetujuan saya.
2. Implementasi bertahap: (a) migrasi + pembaca kompatibel, (b) simpan per kelompok, (c) UI tab,
   (d) cetak, (e) validasi. Setiap tahap: jalankan `pytest`, tunjukkan hasilnya.
3. Jangan menyentuh data asli tanpa backup. Gunakan salinan database untuk pengujian.
4. Jangan menggabungkan semuanya dalam satu commit besar; pisahkan per tahap.
5. Kalau ada keputusan desain yang ambigu, **bertanya** — jangan mengarang field baru tanpa
   menyebutkannya di ringkasan perubahan.

---

## Lampiran A — Pemetaan metode → instrumen (MAPA.02)

Metode diambil dari `personel.metode_mapa`. Yang **dicetak** hanya instrumen yang sesuai metode:

| Metode | Instrumen yang dicetak |
|---|---|
| `observasi` | FR.IA.01 CL, FR.IA.02 TPD, FR.IA.03 PMO, FR.IA.05 DPT, FR.IA.07 DPL *(opsional)* |
| `dit` | FR.IA.03 PMO, FR.IA.04A, FR.IA.04B, FR.IA.05 DPT, FR.IA.07 DPL *(opsional)* |
| `portofolio` | FR.IA.08 CVP, FR.IA.09 PW, FR.IA.05 DPT |

**Potensi asesi** (`personel.kategori_asesi`): `1` untuk `observasi` dan `dit`, `3` untuk `portofolio`.
Nilai ini harus mengikuti metode yang dipilih. Arti 1–5 mengikuti legenda MAPA.02:
1 = pelatihan/pendidikan dengan kurikulum & fasilitas praktik telusur standar; 2 = pelatihan/pendidikan
belum berbasis kompetensi; 3 = pekerja berpengalaman dari tempat kerja yang telusur standar;
4 = pekerja berpengalaman dari tempat kerja yang belum berbasis kompetensi; 5 = otodidak.

**DIT tidak memakai kelompok pekerjaan.** Semua unit diperlakukan sebagai satu kelompok, dan DIT tidak
wajib mengujikan seluruh unit — cukup unit yang paling penting dan mewakili pekerjaan skema
(prioritas kemampuan berpikir). Jangan menambahkan tabel pengelompokan pada FR.IA.04A/04B.

### Tiga ketidaksesuaian yang harus diperbaiki di kode

1. `app/templates/buku_kerja/_form_mapa02.html` baris ~29: IA.03 hanya `aktif` untuk `observasi`.
   Untuk `dit` IA.03 juga harus aktif (PMO tetap dipakai pada DIT).
2. Baris ~34: IA.07 (`DPL - Daftar Pertanyaan Lisan`) masih `aktif: False` sehingga tidak pernah bisa
   dipilih padahal statusnya opsional. Jadikan pilihan yang bisa diaktifkan pengguna.
3. **FR.IA.09 PW - Pertanyaan Wawancara belum ada sama sekali**: tidak ada `_form_ia09.html`, dan data
   MUK hanya menyimpan `ia01`–`ia08`. Untuk metode `portofolio`, instrumen ini wajib ada —
   tambahkan template, field data `ia09` (pola sama dengan `ia07`: `questions[]` berisi
   `pertanyaan` + `kunci_jawaban`), dan ikutkan dalam ekspor DOCX/ZIP.

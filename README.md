# SKKNI Extractor

Aplikasi untuk mengekstrak unit kompetensi dari dokumen PDF SKKNI (Standar Kompetensi Kerja Nasional Indonesia) menjadi JSON terstruktur.

## Status Pengembangan

Status lengkap, matriks fase, commit rujukan, dan riwayat temuan audit tercatat resmi di **[docs/STATUS.md](file:///home/muhadi/Projects/skkni-extractor/docs/STATUS.md)**. Indeks dokumentasi lengkap dapat dilihat di **[docs/README.md](file:///home/muhadi/Projects/skkni-extractor/docs/README.md)**.

| Fase | Isi Fitur Utama | Status |
| :--- | :--- | :---: |
| 1 s/d 2C | Identifikasi unit, parser elemen/KUK, Batasan Variabel & Panduan Penilaian | Selesai |
| 3A s/d 3D | Generator DOCX multi-unit & integrasi skema sertifikasi | Selesai |
| 4A s/d 4E | Backend FastAPI, perpustakaan PDF & skema, job background, unduh DOCX | Selesai |
| 4F | Database SQLite, editor koreksi manual unit, deteksi konflik, gerbang dokumen | Selesai |
| Buku Kerja | 25 Formulir BNSP V.2023, pracetak A4 (Portrait/Landscape), ekspor ZIP/DOCX | Selesai |
| Audit Fixes | Pengerasan RBAC/keamanan, fix multi-versi MUK, penyempurnaan UI/UX, refaktor router, runner test pytest & CI | Selesai |

## Teknologi

- Python 3
- PyMuPDF (`pymupdf`) untuk ekstraksi PDF
- Tanpa AI, Ollama, atau layanan cloud

## Struktur proyek

```
skkni-extractor/
├── app/
│   ├── __init__.py
│   ├── extractor.py          # Fase 1: identifikasi unit
│   ├── section_parser.py     # Fase 2B: kolom dinamis + bagian bernomor
│   ├── unit_parser.py        # Fase 2A/2B: parser unit lengkap
│   ├── docx_generator.py     # Fase 3A/3C: generator DOCX (satu unit)
│   ├── multi_docx_generator.py  # Fase 3C: gabungan beberapa unit
│   ├── schema_parser.py      # Fase 3D: baca daftar unit dari DOCX skema
│   ├── unit_matcher.py       # Fase 3D: cocokkan kode ke PDF SKKNI
│   └── schema_pipeline.py    # Fase 3D: orkestrasi skema → DOCX + laporan
├── data/
│   ├── pdf/                  # PDF SKKNI masukan
│   └── json/                 # hasil ekstraksi
├── tests/
│   ├── baseline/             # baseline hasil Fase 1 & 2A untuk uji regresi
│   ├── test_extractor.py     # Fase 1
│   ├── test_unit_parser.py   # Fase 2A
│   ├── test_unit_complete.py # Fase 2B (lengkap)
│   ├── test_unit_numbering.py# Fase 2C (metadata penomoran)
│   ├── test_docx_generator.py# Fase 3A (validasi DOCX + render PDF)
│   ├── test_cross_skkni.py   # Fase 3B (4 SKKNI + laporan)
│   ├── test_multi_docx.py    # Fase 3C (3 unit dalam satu dokumen)
│   ├── test_schema_parser.py # Fase 3D (baca dokumen skema)
│   ├── test_unit_matcher.py  # Fase 3D (pencocokan kode → PDF)
│   └── test_schema_to_docx.py# Fase 3D (10 unit → DOCX + regresi)
├── output/
│   ├── cross_skkni/          # DOCX/PDF + laporan_pengujian.json (Fase 3B)
├── requirements.txt
└── README.md
```

## Cara menjalankan

```bash
cd ~/Projects/skkni-extractor
source .venv/bin/activate

python tests/test_extractor.py        # Fase 1
python tests/test_unit_parser.py      # Fase 2A
python tests/test_unit_complete.py    # Fase 2B (regresi + validasi penuh)
python tests/test_unit_numbering.py   # Fase 2C (metadata penomoran + regresi)
python tests/test_docx_generator.py   # Fase 3A (DOCX + numbering + render PDF)
python tests/test_cross_skkni.py      # Fase 3B (4 SKKNI, ~2 menit)
python tests/test_multi_docx.py       # Fase 3C (multi-unit + spasi numbering)
python tests/test_schema_parser.py    # Fase 3D (dokumen skema)
python tests/test_unit_matcher.py     # Fase 3D (pencocokan PDF)
python tests/test_schema_to_docx.py   # Fase 3D (pipeline 10 unit, ~5 menit)
python tests/test_web.py              # Fase 4A/4B (halaman, API, aset, regresi)
python tests/test_skkni_library.py    # Fase 4B (unggah, duplikat, pencarian, keamanan)
python tests/test_kuk_completeness.py # Fase 4B (validator nomor KUK)
python tests/test_schema_library.py   # Fase 4C (unggah DOCX skema, keamanan)
python tests/test_schema_matching.py  # Fase 4C (pencocokan unit, periksa ulang)
python tests/test_web_extraction.py   # Fase 4D (job manager, preview, JSON)
python tests/test_document_service.py # Fase 4E (validasi + isi DOCX)
python tests/test_document_download.py# Fase 4E (API unduh, traversal, CSRF)

# pipeline lengkap
python -m app.schema_pipeline

# generate DOCX satu unit
python -m app.docx_generator data/json/test_unit_001_complete.json \
       "output/M.73ADV00.001.1.docx"

# parser manual
python -m app.unit_parser "data/pdf/SKKNI 2023-101.pdf.pdf" M.73ADV00.001.1 21 24
```

## Cara kerja parser

1. Rentang halaman unit diambil dari hasil Fase 1 (`hasil_identifikasi.json`), indeks 0-based.
2. Identitas unit diekstrak lewat label resmi `KODE UNIT`, `JUDUL UNIT`, `DESKRIPSI UNIT`.
3. Batas kolom tabel **dideteksi dinamis**:
   - celah terbesar pada sebaran `x0` blok isi tabel menentukan dua kolom,
   - batas = titik tengah antara `x1` maksimum kolom kiri dan `x0` minimum kolom kanan,
   - hasilnya divalidasi terhadap koordinat header `ELEMEN KOMPETENSI` / `KRITERIA UNJUK KERJA`.
4. KUK diparse per nomor (`X.Y`); baris lanjutan digabung dengan satu spasi; nomor tidak diubah.
5. `BATASAN VARIABEL` dan `PANDUAN PENILAIAN` diparse sebagai outline bernomor rekursif
   (kedalaman ditentukan dari jumlah bagian nomor: `1` → `1.1` → `1.2.1`).
6. Setiap node menyimpan `nomor`, `level`, `parent_nomor`, `is_numbered`, `judul`, `teks`,
   `halaman_pdf`, `halaman_akhir`, `bbox`, `teks_mentah`.
7. Validasi otomatis menghasilkan status `valid_struktur` / `perlu_verifikasi` / `gagal_ekstraksi`.

## Metadata penomoran (Fase 2C)

Setiap node di `batasan_variabel` dan `panduan_penilaian` memuat:

| Field | Arti |
|---|---|
| `nomor` | nomor lengkap apa adanya dari PDF, mis. `2.1.3`; `null` untuk paragraf tanpa nomor |
| `level` | tingkat penomoran (1, 2, 3, …); paragraf tanpa nomor = level induk + 1 |
| `parent_nomor` | nomor induk; `null` bila node berada di akar |
| `is_numbered` | `true` untuk bagian bernomor, `false` untuk paragraf biasa seperti `(Tidak ada.)` |
| `teks` | isi tanpa nomor (nomor tidak digabung permanen ke teks) |
| `halaman_pdf` | indeks halaman PDF 0-based |

Tambahan:

- Nomor asli disimpan di `teks_mentah` untuk audit; nomor tidak dibuat ulang atau dikoreksi.
- `penomoran` pada tiap bagian: `grup`, `mulai_dari`, `jumlah_level_maks`,
  `jumlah_node_bernomor`, `jumlah_paragraf_tanpa_nomor`, `nomor_akar`, `mulai_dari_satu`.
- `batasan_variabel` dan `panduan_penilaian` adalah dua kelompok terpisah, masing-masing mulai `1`.
- Penomoran selalu dimulai ulang per unit (tidak ada state antar-unit).
- Level di atas 3 dipertahankan apa adanya dan ditandai
  `perlu penentuan format Word Multilevel Numbering`.
- Nomor yang tidak berurutan ditandai pada `catatan` validasi, tidak diperbaiki otomatis.
- `penomoran.rencana_word_multilevel` menyimpan indentasi acuan Fase 3:
  level 1 (0,75 cm / hanging −0,75), level 2 (1,49 / −0,75), level 3 (2,23 / −0,75).

## Generator DOCX (Fase 3A)

`app/docx_generator.py` mengubah JSON satu unit menjadi `.docx`:

| Aspek | Nilai |
|---|---|
| Font | Bookman Old Style 11 pt |
| Spasi | after 6 pt, line 1,15 |
| Halaman | 21,5 × 33,0 cm (F4), margin atas/kanan 2,54 cm, bawah 5,08 cm, kiri 3,0 cm |
| Tabel | 2 kolom × 4524 twip, border 0,5 pt, header tebal, `tblHeader` + `cantSplit` |
| KUK | nomor eksplisit dari JSON (`1.1` + tab + uraian, hanging indent 0,75 cm) |
| BV / PP | Word Multilevel Numbering (`abstractNum` + `num` terpisah per kelompok) |

Penomoran:

- Satu `abstractNum` 3 level (`%1.`, `%1.%2.`, `%1.%2.%3.`), dua `w:num` (BV dan PP)
  masing-masing dengan `startOverride=1` di semua level → tiap kelompok mulai dari 1.
- Indentasi paragraf: level 1 = 425 twip (0,75 cm), level 2 = 845 (1,49 cm),
  level 3 = 1264 (2,23 cm); hanging 425 twip.
- Paragraf tanpa nomor tidak diberi `numPr`; indentasi mengikuti `parent_nomor`.
- Nomor yang ditampilkan diverifikasi dengan menyimulasikan counter Word per `numId`
  dan mencocokkannya dengan `nomor` JSON, bukan hanya memeriksa adanya `numPr`.

## Perbedaan tata letak PDF yang ditangani (Fase 3B)

Empat SKKNI yang diuji memakai layout berbeda; parser/ generator menanganinya tanpa
mengubah hasil unit yang sudah berjalan:

| Perbedaan | Contoh | Penanganan |
|---|---|---|
| Nomor halaman 85–90 pt dari tepi bawah | 2018-056, 2018-107, 2022-124 | deteksi nomor halaman diperlebar |
| Blok tabel muncul **setelah** Batasan Variabel dalam urutan PyMuPDF | 2018-107 | batas tabel ditentukan dari posisi (halaman, y), bukan urutan |
| Satu blok memuat sel Elemen **dan** sel KUK | 2018-107 | blok dipecah per baris menurut kolom |
| Nomor berdiri sendiri di baris, teks di baris berikutnya | 2022-124 (Batasan/Panduan) | nomor "menunggu teks" lalu dipasangkan |
| Baris lanjutan berhuruf besar (judul UU terpotong) | 2018-107 | digabung bila kalimat belum selesai & lebih menjorok |
| Level penomoran >3 | (sebelum perbaikan) | dipertahankan; generator membuat level tambahan + ditandai |
| Urutan blok tidak visual | 2018-107 | identitas (judul/deskripsi) dibaca dari teks berurut posisi (y, x), bukan urutan stream PyMuPDF; batas deskripsi berhenti pada label struktural pertama |
| Satu blok PDF berisi kalimat yang terpecah jadi banyak baris | 2018-056 PP 2.1 | semua baris setelah baris pertama dalam blok digabung ke paragraf yang sama |
| Subbutir dilanjutkan baris berhuruf besar yang lebih menjorok | 2018-056, 2018-107 | digabung bila level >= 2 dan kalimat belum selesai |
| Kalimat terpotong antar halaman | 2018-056 PP | lanjutan paragraf tanpa nomor digabung bila kalimat belum selesai |

## Multi-unit (Fase 3C)

`app/multi_docx_generator.py` menggabungkan beberapa unit dari SKKNI berbeda
ke satu dokumen, memakai ulang `dokumen_baru()` + `tambah_unit()`:

```python
from app.multi_docx_generator import generate_multi_docx
generate_multi_docx({'units': [
    {'kode': 'J.63OPR00.009.2', 'skkni': '2018-056'},
    {'kode': 'J.59MTM00.011.1', 'skkni': '2018-107'},
]}, 'output/multi.docx')
```

- Urutan unit mengikuti spesifikasi.
- Unit ke-2 dan seterusnya dimulai dengan `page_break_before` pada paragraf
  KODE UNIT (tanpa paragraf kosong tambahan).
- Setiap unit memperoleh `abstractNum` + dua `numId` sendiri, sehingga Batasan
  Variabel dan Panduan Penilaian selalu mulai dari 1.

### Spasi nomor–teks

`hitung_hanging()` membuat hanging indent adaptif per level: lebar nomor
terpanjang pada level itu + 0,25 cm, dibatasi agar nomor tidak masuk margin.
Left indent (posisi teks & baris lanjutan) tetap 0,75/1,49/2,23 cm.
Hasil render: jarak nomor–teks 6,0–6,4 pt di semua level (level 3 tidak lagi
melompat ke tab default).

## Dokumen Word dari browser (Fase 4E)

- `app/services/document_service.py` — validasi unit, generate DOCX lewat
  `multi_docx_generator`, metadata atomik di `data/web_documents/<id>.json`,
  berkas di `output/web_documents/<id>.docx`.
- `app/api/documents.py` — `POST /api/documents/generate`, `GET /api/documents`,
  `GET /api/documents/{id}`, `GET /api/documents/{id}/download`.
- Halaman: `GET /hasil` (riwayat), `GET /hasil/{id}` (detail), `POST /hasil/generate`
  (form dari detail skema), panel **Buat Dokumen Word** di detail skema.

Status: `siap_ditinjau` (semua unit lolos struktur + kelengkapan),
`draft_perlu_verifikasi` (dibuat setelah persetujuan eksplisit), `gagal`.
Tanpa persetujuan, dokumen dengan unit bermasalah ditolak (409).

## Ekstraksi dari browser (Fase 4D)

- `app/jobs.py` — job manager: thread latar belakang (maks. 2 job paralel),
  status `menunggu`/`berjalan`/`selesai`/`selesai_sebagian`/`gagal`/`terputus`,
  progres per unit, disimpan atomik di `data/jobs/<id>.json`.
- Alur: detail skema → `POST /skema/{id}/ekstrak` (satu unit / semua) →
  `parse_unit` + `section_parser` → validator KUK independen →
  `data/json/browser_extraction/<kode>.json` → `GET /job/{id}` → preview.
- Halaman: `GET /job/{id}` (progres + polling), `GET /skema/{id}/unit/{kode}`
  (preview elemen/KUK/BV/PP), API `GET /api/jobs/{id}`.
- Saat aplikasi dimulai, job yang tertinggal ditandai `terputus` (tidak menggantung).

## Perpustakaan skema (Fase 4C)

- `app/schema_library.py` — unggah DOCX, validasi ZIP/struktur/makro, metadata atomik,
  pembacaan unit lewat `schema_parser.py`, pencocokan lewat `unit_matcher.py`.
- `app/api/skema.py` — `GET /api/skema`, `GET /api/skema/{id}`.
- Halaman: `GET /skema`, `POST /skema/upload`, `GET /skema/{id}`,
  `POST /skema/{id}/periksa-ulang`, `POST /skema/{id}/verifikasi`.

Berkas di `data/schema_library/docx/<id>.docx`, metadata di
`data/schema_library/documents/<id>.json`.

Sumber pencocokan = semua PDF di `data/pdf/` **dan** PDF unggahan pada perpustakaan
SKKNI. Status pencocokan: `ditemukan`, `belum_ditemukan`, `konflik`
(+ penanda `judul_berbeda`). Status berlapis per unit: `diekstrak`, `valid struktur`,
`valid kelengkapan`, `manual` — tidak ada yang otomatis "manual".

## Perpustakaan SKKNI (Fase 4B)

- `app/library.py` — unggah, validasi PDF, SHA-256, metadata JSON atomik.
- `app/kuk_completeness_validator.py` — validasi nomor KUK independen.
- `app/api/skkni.py` — `GET /api/skkni`, `GET /api/skkni/{id}`.
- `app/api/security.py` — token CSRF double-submit cookie.

Berkas disimpan di `data/library/pdf/<id>.pdf`; metadata di
`data/library/documents/<id>.json`. PDF di `data/pdf/` didaftarkan otomatis
sebagai dokumen `proyek` tanpa disalin.

Aturan unggah: hanya PDF (signature + `%%EOF` + dapat dibuka + tidak terenkripsi),
maksimum 50 MB, duplikat SHA-256 ditolak, nama asli hanya metadata, nama internal
berupa UUID heksadesimal.

Status validasi kelengkapan: `valid_kelengkapan`, `perlu_verifikasi`,
`tidak_dapat_dibandingkan` (unit belum punya JSON). Status `terverifikasi_manual`
hanya diberikan lewat tombol eksplisit di halaman detail.

## Aplikasi web lokal (Fase 4A)

```
./run.sh            # http://127.0.0.1:8000
```

Halaman: `/` dashboard, `/skkni`, `/skema`, `/unit`, `/ekstraksi`, `/hasil`.
API: `/api/health`, `/api/dashboard`, `/api/system/status`.

- `app/main.py` — aplikasi FastAPI, rute halaman, penanganan galat tanpa traceback.
- `app/api/system.py` — status aplikasi dan modul.
- `app/api/dashboard.py` — ringkasan dashboard.
- `app/web_data.py` — lapisan baca-saja ke berkas proyek (tanpa data dummy).
- `app/templates/` — base + 6 halaman Jinja2.
- `app/static/` — CSS dan JavaScript lokal, tanpa CDN.

Server hanya mendengarkan `127.0.0.1`, tanpa CORS bebas, tanpa unggah berkas,
tanpa eksekusi perintah dari browser. Folder `data/` dan `output/` dibaca
apa adanya; bila kosong, angka tampil 0 dan halaman menampilkan pesan kosong.

## Skema sertifikasi → DOCX (Fase 3D)

`app/schema_pipeline.py` menjalankan alur lengkap:

1. `schema_parser.baca_skema()` — membaca DOCX skema, mengambil tabel pada
   bagian **Kemasan / Paket Kompetensi** (bukan daftar di bagian lain),
   menyimpan kode, judul, nomor urut, dan lokasi baris tabel.
2. `unit_matcher.cocokkan()` — mencocokkan kode **persis** ke indeks unit tiap
   PDF SKKNI; menandai kode tidak ditemukan dan konflik antar dokumen.
3. `unit_parser.parse_unit()` — ekstraksi tiap unit (JSON terpisah untuk audit):
   `data/json/schema_content_creator/<kode>.json`.
4. Validasi 15 butir per unit; duplikasi teks yang terbukti ada di PDF
   dikategorikan `peringatan_format_sumber`, bukan kegagalan.
5. `multi_docx_generator` — satu DOCX; nama final hanya bila 10/10 unit lengkap,
   jika tidak memakai akhiran `DRAFT_BELUM_LENGKAP`.

Hasil: `output/SKKNI Content Creator - 10 Unit Kompetensi.docx` +
`output/laporan_content_creator.json`.

## Klasifikasi peringatan (Fase 3B.2)

`validasi` memisahkan dua hal:

| Field | Arti |
|---|---|
| `catatan` | masalah struktur/ekstraksi; memengaruhi `status` |
| `peringatan_format_sumber` | kondisi yang memang ada di PDF sumber (mis. KUK tanpa titik), **tidak** mengubah teks dan **tidak** menggagalkan status |

Setiap peringatan berbentuk `{kategori, nomor_kuk, halaman_pdf, pesan}` dengan
`kategori = "peringatan_format_sumber"`, sehingga tetap tersedia untuk audit.

## Keterbatasan

- `valid_struktur` hanya berarti lolos pemeriksaan otomatis, **bukan** bukti teks identik 100% dengan PDF.
- Kesamaan jumlah bagian tidak menjamin isi benar; gunakan `teks_mentah` + `halaman_pdf` untuk audit manual.
- Untuk PDF dengan layout tabel berbeda (mis. garis kolom tidak sejajar teks), batas kolom dapat
  berkeyakinan rendah dan hasilnya ditandai `perlu_verifikasi`.
- DOCX: jarak antara nomor level 2/3 dan teks rapat (±0,1 cm). Ini konsekuensi hanging 0,75 cm
  yang ditetapkan spesifikasi; render dokumen referensi menunjukkan jarak yang sama.
- DOCX: `tblHeader` sudah dipasang, tetapi tabel unit uji masih muat di satu halaman sehingga
  pengulangan header belum terbukti secara visual.
- DOCX: python-docx tidak menghitung nomor tampilan; verifikasi memakai simulasi counter +
  pengecekan posisi/nomor pada PDF hasil render LibreOffice. Word dapat merender sedikit berbeda.
- DOCX: indentasi memakai `w:ind` tanpa `leftChars`/`firstLineChars`; atribut char-unit membuat
  LibreOffice mengabaikan indentasi twips.

# Keamanan Aplikasi — Catatan Operasional

Dokumen ini menjelaskan cara aplikasi menangani akun, kata sandi, dan kunci API
**setelah** perbaikan keamanan pada cabang `audit-fixes`. Isinya menerangkan apa
yang sudah ditegakkan, apa yang masih terbuka, dan apa yang harus dilakukan
operator saat memasang aplikasi.

---

## 1. Akun dan Kata Sandi

### Akun pertama
Saat basis data (`data/app.db`) masih kosong, aplikasi membuat **satu** akun
`admin` dengan kata sandi acak. Kata sandi itu:

- ditampilkan **sekali** di konsol saat `./run.sh` dijalankan;
- **tidak** ditulis ke `logs/skkni_extractor.log` (berkas log bertahan lama);
- **tidak** dicetak di halaman login atau di dokumentasi mana pun.

Saat masuk pertama kali, akun ini membawa penanda `must_change_password`.
Selama penanda itu menyala, **semua tindakan pengubahan data ditahan** dan
pengguna diarahkan ke `/akun/ganti-sandi`. Halaman baca tetap bisa dibuka.

### Akun lama dari versi 1.0.0
Versi lama membuat `admin` / `asesor` dengan kata sandi yang tercetak di halaman
login. Pada setiap start, aplikasi memeriksa apakah sebuah akun masih memakai
kata sandi publik tersebut; bila ya, akun ditandai wajib ganti sandi dan
perilakunya sama seperti di atas.

Daftar kata sandi lama yang diperiksa ada di `app/db.py` pada konstanta
`KREDENSIAL_BAWAAN_LAMA`. **Hapus konstanta itu setelah semua pemasangan
dimigrasikan**, karena keberadaannya hanya berguna untuk mendeteksi akun lama.

### Kebijakan kata sandi
- Minimal 8 karakter (`db.ubah_kata_sandi`).
- Harus berbeda dari kata sandi saat ini.
- Disimpan sebagai PBKDF2-HMAC-SHA256, 100.000 iterasi, garam acak per akun.
- Mengganti kata sandi menghapus **semua** sesi lain milik akun tersebut.

### Peran
| Peran | Boleh |
| :--- | :--- |
| `admin` | Semua tindakan: unggah SKKNI, unggah skema, kurasi regulasi Kemnaker, koreksi unit. |
| `asesor` | Semua tindakan kerja: simpan MUK, ekstrak, verifikasi manual, cetak, buat dokumen. **Tidak** boleh unggah atau mengoreksi master data. |

Satu aturan akses untuk seluruh aplikasi ada di `app/api/auth_guard.py`
(`wajib_login(peran)`). Jangan menulis pemeriksaan sesi/peran sendiri di route
baru — pasang dependency itu.

Tanpa sesi: halaman HTML diarahkan ke `/login?next=...`, jalur `/api/*` dibalas
`403` JSON. Peran salah selalu `403`.

---

## 2. Kunci API Eksternal

Kunci API **tidak dibuat otomatis** dan tidak lagi tercantum di dokumentasi.
Kunci yang dulu publik sudah dicabut saat migrasi (`KUNCI_API_BAWAAN_LAMA` di
`app/db.py`) dan dibalas `401`.

```bash
.venv/bin/python -m tools.kunci_api buat --nama "WordPress LSP" --peran klien
.venv/bin/python -m tools.kunci_api daftar
.venv/bin/python -m tools.kunci_api cabut 3
```

Nilai kunci lengkap hanya ditampilkan sekali saat dibuat. Setelah itu aplikasi
hanya menyimpan hash SHA-256 dan 12 karakter awal sebagai `prefix` untuk
ditampilkan di daftar.

---

## 3. Header Keamanan dan Swagger

Setiap respons membawa `X-Content-Type-Options`, `X-Frame-Options`,
`Referrer-Policy`, serta `Content-Security-Policy`. CSP dipasang sebagai
`default-src 'self'` dengan `'unsafe-inline'` untuk gaya dan skrip, karena
template masih memuat gaya dan skrip inline. Artinya CSP di sini mencegah
pemuatan kode dari domain luar, **bukan** mencegah injeksi inline. Setelah gaya
inline dipindahkan ke kelas CSS (langkah 3.3), `'unsafe-inline'` dapat dicabut.

Dokumentasi API (`/docs`, `/redoc`, `/openapi.json`) terbuka saat `APP_ENV`
bukan `produksi`. Setel `APP_ENV=produksi` bila aplikasi dipakai di jaringan
LSP agar ketiganya dibalas `404`.

---

## 4. Yang Masih Terbuka (jujur, belum dikerjakan)

Perbaikan ini menutup tindakan **pengubahan** data, bukan pembacaan:

1. **Halaman baca masih publik.** Siapa pun yang bisa menjangkau port aplikasi
   dapat membuka `/skkni`, `/skema`, dan mengunduh dokumen. Penguncian baca
   menyeluruh adalah tahap 5 peta jalan (`docs/RENCANA_PENGEMBANGAN_BUKU_KERJA.md`).
2. **Batas percobaan login belum ada.** Brute force belum dihambat; dikerjakan
   pada langkah 1.5.
3. **Cookie sesi belum memakai `Secure`.** Aplikasi berjalan di
   `http://127.0.0.1`, sehingga `Secure` akan membuat cookie tidak terkirim.
   Setel `Secure` bila nanti dipasang di belakang HTTPS.
4. **Token CSRF belum diikat ke sesi.** Masih pola double-submit cookie.
5. **Belum ada audit trail siapa mengubah apa** selain kolom `oleh`/`dibuat_oleh`
   pada koreksi dan versi MUK.

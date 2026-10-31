"""
SKKNI Extractor - Migrasi Konfigurasi MUK ke Versi 2 (Instrumen per Kelompok Pekerjaan).

Aturan Migrasi:
1. Memindahkan FR.IA.01, IA.02, IA.03, IA.04A, IA.04B dari akar MUK ke `kelompok_pekerjaan[i].instrumen`.
2. Menyimpan `schema_muk_version = 2`.
3. Menambahkan `durasi_menit` (integer) pada IA.02 tanpa menghapus `durasi_waktu`.
4. Menyediakan array `kuk` pada pertanyaan IA.03 dan IA.04A/B.
5. Idempoten: aman dijalankan berulang kali tanpa merusak atau mengubah data yang sudah v2.
6. Berjalan pada berkas `data/schema_library/muk/*.json` dan tabel SQLite `muk_versi`.
"""

import copy
import json
import logging
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
MUK_DIR = ROOT / 'data' / 'schema_library' / 'muk'

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('migrasi_muk_v2')


def ekstrak_menit_durasi(durasi_val: Any, default_menit: int = 90) -> int:
    """Mengubah string '90 Menit' atau int ke integer menit."""
    if isinstance(durasi_val, (int, float)):
        return int(durasi_val) if durasi_val > 0 else default_menit
    s = str(durasi_val or '').strip()
    m = re.search(r'(\d+)', s)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return default_menit


def pisahkan_kuk(elemen_kuk_val: Any) -> List[str]:
    """Mengekstrak array nomor KUK (mis. '1.1; 1.2' -> ['1.1', '1.2'])."""
    if isinstance(elemen_kuk_val, list):
        return [str(x).strip() for x in elemen_kuk_val if str(x).strip()]
    raw = str(elemen_kuk_val or '').strip()
    if not raw or raw == '-':
        return []
    # Jika berisi kode unit (misal M.70HMS00.005.3), abaikan atau pisahkan
    parts = re.split(r'[,;|\s]+', raw)
    hasil = []
    for p in parts:
        p_clean = p.strip()
        if p_clean and re.match(r'^\d+(\.\d+)?(-(\d+\.)?\d+)?$', p_clean):
            hasil.append(p_clean)
        elif p_clean and not p_clean.startswith(('J.', 'M.', 'SKKNI')):
            hasil.append(p_clean)
    return hasil or ([raw] if raw and not raw.startswith(('J.', 'M.')) else [])


def migrasikan_objek_muk(muk_dict: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """
    Mengubah dict konfigurasi MUK dari v1 (instrumen di akar) ke v2 (instrumen di kelompok_pekerjaan).
    Mengembalikan (muk_hasil, apakah_diubah).
    Idempoten: Jika `schema_muk_version` >= 2, fungsi tidak mengubah apa pun.
    """
    if not isinstance(muk_dict, dict):
        return muk_dict, False

    versi_sekarang = muk_dict.get('schema_muk_version', 1)
    try:
        versi_sekarang = int(versi_sekarang)
    except (ValueError, TypeError):
        versi_sekarang = 1

    if versi_sekarang >= 2:
        return muk_dict, False

    baru = copy.deepcopy(muk_dict)
    kelompok_list = baru.get('kelompok_pekerjaan') or []

    # Jika sama sekali belum ada kelompok_pekerjaan, buat kelompok default
    if not kelompok_list:
        kelompok_list = [{
            'id': 'kp_1',
            'nama': 'Kelompok Pekerjaan 1 (belum dikelompokkan — draf)',
            'urutan': 1,
            'units': []
        }]
        baru['kelompok_pekerjaan'] = kelompok_list

    # Ambil instrumen lama dari akar
    akar_ia02 = baru.get('ia02') or {}
    akar_ia03 = baru.get('ia03') or {}
    akar_ia04 = baru.get('ia04') or {}
    akar_ia01 = baru.get('ia01') or {}
    akar_ia04b = baru.get('ia04b') or {}

    # Konversi format IA.02
    durasi_str = str(akar_ia02.get('durasi_waktu') or '90 Menit').strip()
    durasi_int = ekstrak_menit_durasi(durasi_str, default_menit=90)
    langkah_raw = akar_ia02.get('langkah_kerja') or ''
    langkah_list = []
    if isinstance(akar_ia02.get('langkah'), list):
        langkah_list = akar_ia02['langkah']
    else:
        for idx_l, line in enumerate(str(langkah_raw).split('\n'), start=1):
            line_s = line.strip()
            if line_s:
                # buang nomor awalan mis. '1. '
                clean_l = re.sub(r'^\d+[\.\)]\s*', '', line_s)
                langkah_list.append({
                    'order': idx_l,
                    'kode': f'K1-{idx_l}',
                    'uraian': clean_l,
                    'menit': max(10, durasi_int // max(1, len(str(langkah_raw).split('\n')))),
                    'kuk': []
                })

    instrumen_ia02 = {
        'skenario': str(akar_ia02.get('skenario') or '').strip(),
        'langkah_kerja': str(akar_ia02.get('langkah_kerja') or '').strip(),
        'hasil_kerja': str(akar_ia02.get('hasil_kerja') or '').strip(),
        'perlengkapan': str(akar_ia02.get('perlengkapan') or '').strip(),
        'peralatan': str(akar_ia02.get('peralatan') or '').strip(),
        'durasi_menit': durasi_int,
        'durasi_waktu': durasi_str,
        'langkah': langkah_list,
    }

    # Konversi format IA.03
    q3_list = []
    for idx_q, q in enumerate(akar_ia03.get('questions') or [], start=1):
        if not isinstance(q, dict):
            continue
        dim = str(q.get('dimensi') or 'TS').strip().upper()
        # Instrumen praktik: TS, TMS, JRES
        if dim not in ('TS', 'TMS', 'JRES', 'CMS', 'TRS'):
            dim = 'TS'
        raw_kuk = q.get('kuk') or q.get('elemen_kuk') or []
        kuk_arr = pisahkan_kuk(raw_kuk)
        q3_list.append({
            'order': int(q.get('order') or idx_q),
            'dimensi': dim,
            'pertanyaan': str(q.get('pertanyaan') or '').strip(),
            'kunci_jawaban': str(q.get('kunci_jawaban') or '').strip(),
            'kuk': kuk_arr,
            'elemen_kuk': '; '.join(kuk_arr) if kuk_arr else str(q.get('elemen_kuk') or '').strip(),
        })

    instrumen_ia03 = {
        'panduan': str(akar_ia03.get('panduan') or '').strip(),
        'questions': q3_list,
    }

    # Konversi format IA.04A
    q4_list = []
    for idx_q, q in enumerate(akar_ia04.get('questions') or [], start=1):
        if not isinstance(q, dict):
            continue
        raw_kuk = q.get('kuk') or q.get('elemen_kuk') or []
        kuk_arr = pisahkan_kuk(raw_kuk)
        dim = str(q.get('dimensi') or '(TS, TMS)').strip()
        q4_list.append({
            'order': int(q.get('order') or idx_q),
            'lingkup': str(q.get('lingkup') or '-').strip(),
            'pertanyaan': str(q.get('pertanyaan') or '').strip(),
            'kuk': kuk_arr,
            'elemen_kuk': '; '.join(kuk_arr) if kuk_arr else str(q.get('elemen_kuk') or '').strip(),
            'dimensi': dim,
        })

    instrumen_ia04a = {
        'judul_kegiatan': str(akar_ia04.get('judul_kegiatan') or '').strip(),
        'situasi': str(akar_ia04.get('situasi') or '').strip(),
        'tugas': str(akar_ia04.get('tugas') or '').strip(),
        'tindakan': str(akar_ia04.get('tindakan') or '').strip(),
        'data_informasi': str(akar_ia04.get('data_informasi') or '').strip(),
        'hasil': str(akar_ia04.get('hasil') or '').strip(),
        'hal_demonstrasi': str(akar_ia04.get('hal_demonstrasi') or '').strip(),
        'waktu_proyek': str(akar_ia04.get('waktu_proyek') or '').strip(),
        'waktu_presentasi': str(akar_ia04.get('waktu_presentasi') or '').strip(),
        'questions': q4_list,
    }

    # IA.04B & IA.01
    instrumen_ia04b = copy.deepcopy(akar_ia04b if isinstance(akar_ia04b, dict) else {'questions': []})
    instrumen_ia01 = copy.deepcopy(akar_ia01 if isinstance(akar_ia01, dict) else {'indikator': []})

    instrumen_gabungan_k1 = {
        'ia01': instrumen_ia01,
        'ia02': instrumen_ia02,
        'ia03': instrumen_ia03,
        'ia04a': instrumen_ia04a,
        'ia04b': instrumen_ia04b,
        'instrumen_status': 'lengkap' if (instrumen_ia02['skenario'] or q3_list or q4_list) else 'draf'
    }

    jumlah_kelompok = len(kelompok_list)

    for i, grp in enumerate(kelompok_list):
        if not isinstance(grp, dict):
            continue
        if i == 0:
            # Salin ke kelompok pertama
            grp['instrumen'] = copy.deepcopy(instrumen_gabungan_k1)
        else:
            # Kelompok lain jika lebih dari 1 kelompok
            grp_exist = grp.get('instrumen')
            if not isinstance(grp_exist, dict) or not grp_exist:
                grp['instrumen'] = {
                    'ia01': {'indikator': []},
                    'ia02': {
                        'skenario': '', 'langkah_kerja': '', 'hasil_kerja': '',
                        'perlengkapan': '', 'peralatan': '', 'durasi_menit': 90, 'durasi_waktu': '90 Menit', 'langkah': []
                    },
                    'ia03': {'panduan': '', 'questions': []},
                    'ia04a': {
                        'judul_kegiatan': '', 'situasi': '', 'tugas': '', 'tindakan': '',
                        'data_informasi': '', 'hasil': '', 'hal_demonstrasi': '',
                        'waktu_proyek': '', 'waktu_presentasi': '', 'questions': []
                    },
                    'ia04b': {'questions': []},
                    'instrumen_status': 'belum_diisi'
                }

    if jumlah_kelompok > 1:
        baru['peringatan_migrasi'] = 'MUK ini dibuat sebelum pemisahan instrumen per kelompok — periksa tiap kelompok.'

    # Verifikasi bahwa kelompok_pekerjaan[0].instrumen sudah terisi dengan benar
    verifikasi_ok = bool(
        kelompok_list[0].get('instrumen')
        and 'ia02' in kelompok_list[0]['instrumen']
        and 'ia03' in kelompok_list[0]['instrumen']
        and 'ia04a' in kelompok_list[0]['instrumen']
    )

    if verifikasi_ok:
        # Hapus instrumen praktik dari akar hanya setelah salinan terverifikasi
        baru.pop('ia02', None)
        baru.pop('ia03', None)
        baru.pop('ia04', None)
        baru.pop('ia04a', None)
        baru.pop('ia04b', None)
        baru.pop('ia01', None)

    baru['schema_muk_version'] = 2
    baru['diperbarui_pada'] = datetime.now(timezone.utc).isoformat()

    return baru, True


def jalankan_migrasi(buat_backup_pertama: bool = True) -> Dict[str, Any]:
    """Menjalankan migrasi MUK v2 untuk semua file disk dan tabel SQLite."""
    if buat_backup_pertama:
        try:
            logger.info("Membuat backup sebelum migrasi...")
            subprocess.run([sys.executable, str(ROOT / 'tools' / 'backup.py')], check=True, cwd=str(ROOT))
        except Exception as e:
            logger.warning("Gagal membuat backup otomatis via tools/backup.py: %s. Melanjutkan dengan salinan lokal...", e)

    hasil = {
        'berkas_diproses': 0,
        'berkas_dimigrasi': 0,
        'db_baris_diproses': 0,
        'db_baris_dimigrasi': 0,
        'daftar_skema_dimigrasi': [],
    }

    # 1. Migrasi Berkas JSON di data/schema_library/muk/
    if MUK_DIR.exists():
        for json_file in sorted(MUK_DIR.glob('*.json')):
            hasil['berkas_diproses'] += 1
            try:
                raw_data = json.loads(json_file.read_text(encoding='utf-8'))
                migrated_data, changed = migrasikan_objek_muk(raw_data)
                if changed:
                    # Simpan file migrasi secara atomik
                    tmp_file = json_file.with_suffix('.json.tmp')
                    tmp_file.write_text(json.dumps(migrated_data, indent=2, ensure_ascii=False), encoding='utf-8')
                    tmp_file.replace(json_file)
                    hasil['berkas_dimigrasi'] += 1
                    hasil['daftar_skema_dimigrasi'].append(json_file.stem)
                    logger.info("Berkas MUK %s berhasil dimigrasikan ke v2.", json_file.name)
            except Exception as e:
                logger.error("Gagal memigrasikan berkas %s: %s", json_file.name, e)

    # 2. Migrasi Tabel SQLite `muk_versi`
    try:
        from app import db
        with db._ambil_koneksi() as conn:
            rows = conn.execute("SELECT id, schema_id, kode_versi, data_json FROM muk_versi").fetchall()
            for r in rows:
                hasil['db_baris_diproses'] += 1
                try:
                    payload = json.loads(r['data_json'])
                    migrated_data, changed = migrasikan_objek_muk(payload)
                    if changed:
                        new_json = json.dumps(migrated_data, ensure_ascii=False)
                        sekarang = datetime.now(timezone.utc).isoformat()
                        conn.execute(
                            "UPDATE muk_versi SET data_json = ?, diperbarui_pada = ? WHERE id = ?",
                            (new_json, sekarang, r['id']),
                        )
                        hasil['db_baris_dimigrasi'] += 1
                        logger.info("Baris muk_versi ID %s (skema: %s) berhasil dimigrasikan ke v2.", r['id'], r['schema_id'])
                except Exception as e:
                    logger.error("Gagal memigrasikan baris muk_versi ID %s: %s", r['id'], e)
            conn.commit()
    except Exception as e:
        logger.error("Gagal mengakses database untuk migrasi muk_versi: %s", e)

    logger.info("=== RINGKASAN MIGRASI MUK V2 ===")
    logger.info("Berkas dimigrasikan: %s / %s", hasil['berkas_dimigrasi'], hasil['berkas_diproses'])
    logger.info("Baris DB dimigrasikan: %s / %s", hasil['db_baris_dimigrasi'], hasil['db_baris_diproses'])
    return hasil


if __name__ == '__main__':
    jalankan_migrasi(buat_backup_pertama=False)

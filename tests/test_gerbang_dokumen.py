"""
Pengujian Gerbang Pembuatan Dokumen & Konsistensi Status 3-Tingkat (Fase 4F - Langkah 1).

Menguji 3 kasus utama:
1. Semua unit berstatus ``siap`` -> dokumen diizinkan dibuat.
2. Ada unit berstatus ``gagal`` (0 elemen/KUK) -> tombol Buat Dokumen nonaktif,
   kode unit gagal dicantumkan, dan paksaan lewat POST/API ditolak di server (409).
3. Ada unit berstatus ``perlu`` -> ditahan dengan alasan tertulis, dan paksaan
   pembuatan dokumen final tanpa koreksi/persetujuan ditolak di server (409).
"""

import json
import re
import shutil
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from fastapi.testclient import TestClient
from app import koreksi, library, schema_library as sl, status_units
from app.main import app
from app.services import document_service as ds

DOC_UJI = project_root / 'output' / 'web_documents' / '_uji_gerbang'
META_UJI = project_root / 'data' / 'web_documents' / '_uji_gerbang'

lulus, gagal = [], []


def cek(nama: str, kondisi: bool, detail: str = '') -> None:
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}" + (f" — {detail}" if detail and not kondisi else ''))


def ambil_csrf(client: TestClient) -> str:
    r = client.get('/skema')
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    return m.group(1) if m else ''


def main() -> int:
    print('=' * 100)
    print('PENGUJIAN GERBANG DOKUMEN & STATUS 3-TINGKAT — FASE 4F')
    print('=' * 100)

    sid = next((d['id'] for d in sl.daftar_skema()
                if d.get('nama_skema') == 'SOCIAL MEDIA MARKETING'), None)
    if not sid:
        print('ERROR: Skema SOCIAL MEDIA MARKETING tidak ditemukan.')
        return 1

    for d in (DOC_UJI, META_UJI):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
    ds.DOC_DIR = DOC_UJI
    ds.META_DIR = META_UJI

    client = TestClient(app)
    token = ambil_csrf(client)

    skema_asli = sl.ambil_skema(sid)
    unit_gagal_path = project_root / 'data' / 'json' / 'browser_extraction' / 'J.63OPR00.004.2.json'
    isi_unit_asli = unit_gagal_path.read_text(encoding='utf-8')

    try:
        # Pastikankoreksi bersih sebelum uji
        for u in skema_asli.get('units') or []:
            koreksi.hapus_koreksi(u['kode_unit'])

        # ------------------------------------------------------------------
        # KASUS 3 (Kondisi Bawaan Skema): Ada unit 'perlu' (J.63OPR00.005.2)
        # ------------------------------------------------------------------
        print('\n1. KASUS UNIT PERLU DIPERIKSA (MENAHAN PEMBUATAN DOKUMEN FINAL)')
        gerbang_perlu = status_units.evaluasi_gerbang_skema(sid)
        cek('siap_semua bernilai False saat ada unit perlu', gerbang_perlu['siap_semua'] is False)
        cek('ada_perlu bernilai True', gerbang_perlu['ada_perlu'] is True)
        cek('ada_gagal bernilai False', gerbang_perlu['ada_gagal'] is False)
        cek('ringkasan mencatat 3 siap dan 1 perlu',
            gerbang_perlu['ringkasan'] == {'total': 4, 'siap': 3, 'perlu': 1, 'gagal': 0},
            str(gerbang_perlu['ringkasan']))

        penahan = gerbang_perlu['penahan']
        cek('unit penahan adalah J.63OPR00.005.2',
            len(penahan) == 1 and penahan[0]['kode_unit'] == 'J.63OPR00.005.2',
            str(penahan))
        cek('alasan tertulis tersedia dan manusiawi',
            bool(penahan[0].get('alasan')) and 'perlu_verifikasi' not in penahan[0]['alasan'],
            penahan[0].get('alasan', ''))

        # Halaman detail skema menampilkan alasan penahan & tautan koreksi
        r_skema = client.get(f'/skema/{sid}')
        cek('halaman skema HTTP 200', r_skema.status_code == 200)
        cek('halaman skema menampilkan kode unit penahan', 'J.63OPR00.005.2' in r_skema.text)
        cek('halaman skema menampilkan lencana Perlu diperiksa', 'Perlu diperiksa' in r_skema.text)
        cek('halaman skema menampilkan tombol Koreksi', f'/skema/{sid}/unit/J.63OPR00.005.2/koreksi' in r_skema.text)

        # Paksa lewat API tanpa persetujuan draft -> ditolak 409 di server
        r_api_perlu = client.post(
            '/api/documents/generate',
            json={'schema_id': sid, 'semua_unit': True, 'draft': False, 'csrf_token': token},
            headers={'x-csrf-token': token},
        )
        cek('API menolak pembuatan dokumen final saat ada unit perlu (HTTP 409)',
            r_api_perlu.status_code == 409, str(r_api_perlu.status_code))

        # Paksa lewat POST form /hasil/generate tanpa draft -> ditolak (redirect galat)
        r_post_perlu = client.post(
            '/hasil/generate',
            data={'schema_id': sid, 'csrf_token': token},
            follow_redirects=False,
        )
        cek('POST /hasil/generate menolak dokumen final saat ada unit perlu',
            r_post_perlu.status_code == 303 and 'tipe=galat' in r_post_perlu.headers.get('location', ''),
            r_post_perlu.headers.get('location', ''))

        # ------------------------------------------------------------------
        # KASUS 1: Semua unit berstatus 'siap'
        # ------------------------------------------------------------------
        print('\n2. KASUS SEMUA UNIT SIAP DIPAKAI')
        # Koreksi unit J.63OPR00.005.2 agar semua 4 unit menjadi 'siap'
        data_005 = koreksi.muat_json_mesin('J.63OPR00.005.2')
        koreksi.simpan_koreksi('J.63OPR00.005.2', data_005['elemen_kompetensi'], oleh='penguji')

        gerbang_siap = status_units.evaluasi_gerbang_skema(sid)
        cek('siap_semua bernilai True setelah unit perlu dikoreksi', gerbang_siap['siap_semua'] is True)
        cek('ringkasan mencatat 4 siap, 0 perlu, 0 gagal',
            gerbang_siap['ringkasan'] == {'total': 4, 'siap': 4, 'perlu': 0, 'gagal': 0},
            str(gerbang_siap['ringkasan']))
        cek('daftar penahan kosong', gerbang_siap['penahan'] == [])

        r_api_siap = client.post(
            '/api/documents/generate',
            json={'schema_id': sid, 'semua_unit': True, 'draft': False, 'csrf_token': token},
            headers={'x-csrf-token': token},
        )
        cek('API mengizinkan pembuatan dokumen final saat semua unit siap (HTTP 200)',
            r_api_siap.status_code == 200, str(r_api_siap.status_code))
        cek('status dokumen adalah siap_ditinjau',
            r_api_siap.json().get('status') == 'siap_ditinjau',
            str(r_api_siap.json().get('status')))

        koreksi.hapus_koreksi('J.63OPR00.005.2')

        # ------------------------------------------------------------------
        # KASUS 2: Ada unit berstatus 'gagal' (0 elemen / 0 KUK)
        # ------------------------------------------------------------------
        print('\n3. KASUS ADA UNIT GAGAL (0 ELEMEN / 0 KUK)')
        data_rusak = json.loads(isi_unit_asli)
        data_rusak['elemen_kompetensi'] = []
        data_rusak['validasi'] = {'status': 'gagal_ekstraksi', 'catatan': ['Elemen tidak terbaca']}
        unit_gagal_path.write_text(json.dumps(data_rusak, ensure_ascii=False, indent=2), encoding='utf-8')

        gerbang_gagal = status_units.evaluasi_gerbang_skema(sid)
        cek('siap_semua bernilai False saat ada unit gagal', gerbang_gagal['siap_semua'] is False)
        cek('ada_gagal bernilai True', gerbang_gagal['ada_gagal'] is True)
        cek('unit J.63OPR00.004.2 berstatus gagal',
            gerbang_gagal['peta_unit']['J.63OPR00.004.2']['status'] == 'gagal',
            str(gerbang_gagal['peta_unit']['J.63OPR00.004.2']))

        r_skema_gagal = client.get(f'/skema/{sid}')
        cek('tombol Buat Dokumen Word memiliki atribut disabled di HTML',
            'disabled title="Tidak dapat membuat dokumen karena masih ada unit berstatus Gagal"' in r_skema_gagal.text)
        cek('kode unit gagal J.63OPR00.004.2 dicantumkan di peringatan gerbang',
            '<code>J.63OPR00.004.2</code> (Gagal)' in r_skema_gagal.text)

        # Paksa lewat API bahkan dengan draft=True -> tetap ditolak 409 di server!
        r_api_gagal = client.post(
            '/api/documents/generate',
            json={'schema_id': sid, 'semua_unit': True, 'draft': True, 'csrf_token': token},
            headers={'x-csrf-token': token},
        )
        cek('API menolak paksaan generate saat ada unit gagal meskipun draft=True (HTTP 409)',
            r_api_gagal.status_code == 409, str(r_api_gagal.status_code))

        # Paksa lewat POST /hasil/generate bahkan dengan draft=1 -> tetap ditolak di server!
        r_post_gagal = client.post(
            '/hasil/generate',
            data={'schema_id': sid, 'draft': '1', 'csrf_token': token},
            follow_redirects=False,
        )
        cek('POST /hasil/generate menolak paksaan saat ada unit gagal meskipun draft=1',
            r_post_gagal.status_code == 303 and 'tipe=galat' in r_post_gagal.headers.get('location', ''),
            r_post_gagal.headers.get('location', ''))

        # Paksa lewat GET /skema/{id}/cetak-apl -> ditolak 409 di server!
        r_cetak_gagal = client.get(f'/skema/{sid}/cetak-apl')
        cek('GET /skema/{id}/cetak-apl menolak cetak saat ada unit gagal (HTTP 409)',
            r_cetak_gagal.status_code == 409, str(r_cetak_gagal.status_code))

        # ------------------------------------------------------------------
        # KONSISTENSI STATUS DI 3 HALAMAN + API STATUS UNIT
        # ------------------------------------------------------------------
        print('\n4. KONSISTENSI STATUS DI SEMUA HALAMAN')
        r_api_st = client.get('/api/unit/J.63OPR00.004.2/status')
        cek('/api/unit/J.63OPR00.004.2/status mengembalikan gagal',
            r_api_st.status_code == 200 and r_api_st.json().get('status') == 'gagal',
            str(r_api_st.json()))

        r_prev = client.get(f'/skema/{sid}/unit/J.63OPR00.004.2')
        cek('halaman pratinjau unit menampilkan lencana Gagal yang sama',
            r_prev.status_code == 200 and '● Gagal' in r_prev.text)

    finally:
        unit_gagal_path.write_text(isi_unit_asli, encoding='utf-8')
        for u in skema_asli.get('units') or []:
            koreksi.hapus_koreksi(u['kode_unit'])
        ds.DOC_DIR = project_root / 'output' / 'web_documents'
        ds.META_DIR = project_root / 'data' / 'web_documents'
        for d in (DOC_UJI, META_UJI):
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)

    print('\n' + '=' * 100)
    print(f'HASIL: {len(lulus)} lulus, {len(gagal)} gagal')
    if gagal:
        for g in gagal:
            print(f'  - {g}')
    print('=' * 100)
    return 0 if not gagal else 1


if __name__ == '__main__':
    sys.exit(main())

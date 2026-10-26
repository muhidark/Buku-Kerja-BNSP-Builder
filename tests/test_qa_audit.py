"""
Pengujian audit QA dan pengujian negatif (Fase 4F).

Memastikan: (a) data nyata lolos tanpa temuan palsu, (b) tujuh mutasi yang
disengaja benar-benar terdeteksi, (c) audit DOCX menangkap KUK yang hilang.
Data produksi tidak diubah: semua mutasi dilakukan pada salinan di memori/temp.
"""

import copy
import json
import shutil
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from docx import Document

from app import qa_audit as qa
from app.services import document_service as ds

lulus, gagal = [], []


def cek(nama, kondisi, detail=''):
    (lulus if kondisi else gagal).append(nama)
    print(f"  [{'PASS' if kondisi else 'FAIL'}] {nama}" + (f" — {detail}" if detail and not kondisi else ''))


def jenis(temuan) -> set:
    return {t['jenis'] for t in temuan}


def main():
    print("=" * 100)
    print("PENGUJIAN AUDIT QA — FASE 4F")
    print("=" * 100)

    units = qa.unit_uji()
    if len(units) != 4:
        print(f'ERROR: unit uji tidak lengkap ({len(units)}).')
        return 1

    peta_pdf = {p.name: p for p in (project_root / 'data' / 'pdf').glob('*.pdf')}
    for d in qa.library.daftar_dokumen():
        internal = d.get('nama_internal')
        if internal and (project_root / internal).exists():
            peta_pdf[Path(internal).name] = project_root / internal

    # ---------------------------------------------------------- 1 data nyata
    print("\n1. DATA NYATA TANPA TEMUAN PALSU")
    kode = units[0]['kode_unit']
    pdf = peta_pdf[units[0]['pdf']]
    data_asli = json.loads(units[0]['json'].read_text(encoding='utf-8'))
    hasil = qa.audit_pdf_json(kode, pdf, units[0]['mulai'], units[0]['akhir'], data_asli)
    cek('audit unit bersih tanpa temuan', not hasil['temuan'], str(jenis(hasil['temuan'])))
    cek('jumlah KUK PDF = JSON',
        len(hasil['kuk_pdf']) == len(hasil['kuk_json']) > 0,
        f"{len(hasil['kuk_pdf'])} vs {len(hasil['kuk_json'])}")
    cek('elemen PDF = JSON',
        sorted(hasil['elemen_pdf']) == sorted(
            int(e['nomor_elemen']) for e in data_asli['elemen_kompetensi']))

    # ------------------------------------------------- 2..8 mutasi negatif
    print("\n2. KUK DIHAPUS DARI JSON")
    d1 = copy.deepcopy(data_asli)
    d1['elemen_kompetensi'][0]['kuk'].pop()
    t1 = qa.audit_pdf_json(kode, pdf, units[0]['mulai'], units[0]['akhir'], d1)['temuan']
    cek('KUK hilang terdeteksi', 'kuk_hilang' in jenis(t1), str(jenis(t1)))
    cek('KUK hilang berkategori Critical',
        any(x['keparahan'] == 'Critical' for x in t1 if x['jenis'] == 'kuk_hilang'))

    print("\n3. KUK DIDUPLIKASI")
    d2 = copy.deepcopy(data_asli)
    d2['elemen_kompetensi'][0]['kuk'].append(copy.deepcopy(d2['elemen_kompetensi'][0]['kuk'][0]))
    t2 = qa.audit_pdf_json(kode, pdf, units[0]['mulai'], units[0]['akhir'], d2)['temuan']
    cek('duplikat KUK JSON terdeteksi', 'kuk_duplikat_json' in jenis(t2), str(jenis(t2)))

    print("\n4. NOMOR KUK DIUBAH")
    d3 = copy.deepcopy(data_asli)
    asli_nomor = d3['elemen_kompetensi'][0]['kuk'][0]['nomor_kuk']
    d3['elemen_kompetensi'][0]['kuk'][0]['nomor_kuk'] = '9.9'
    t3 = qa.audit_pdf_json(kode, pdf, units[0]['mulai'], units[0]['akhir'], d3)['temuan']
    cek('nomor KUK berubah terdeteksi',
        {'kuk_hilang', 'kuk_tanpa_bukti'} & jenis(t3), str(jenis(t3)))
    cek('nomor asli dilaporkan hilang',
        any(x['jenis'] == 'kuk_hilang' and asli_nomor in x['pesan'] for x in t3))

    print("\n5. ELEMEN DIHILANGKAN")
    d4 = copy.deepcopy(data_asli)
    d4['elemen_kompetensi'].pop()
    t4 = qa.audit_pdf_json(kode, pdf, units[0]['mulai'], units[0]['akhir'], d4)['temuan']
    cek('jumlah elemen berbeda terdeteksi', 'jumlah_elemen' in jenis(t4), str(jenis(t4)))

    print("\n6. URAIAN KUK DIPOTONG")
    d5 = copy.deepcopy(data_asli)
    d5['elemen_kompetensi'][0]['kuk'][0]['uraian_kuk'] = 'Teks yang dipotong'
    t5 = qa.audit_pdf_json(kode, pdf, units[0]['mulai'], units[0]['akhir'], d5)['temuan']
    cek('uraian terpotong terdeteksi', 'teks_tidak_ada_di_pdf' in jenis(t5), str(jenis(t5)))

    print("\n7. PARAGRAF BV DIPINDAH KE PP")
    d6 = copy.deepcopy(data_asli)
    bv_nodes = qa.flatten_nodes(d6['batasan_variabel']['sections'])
    pp_nodes = qa.flatten_nodes(d6['panduan_penilaian']['sections'])
    pindah = bv_nodes[0]
    d6['panduan_penilaian']['sections'].insert(0, {
        'nomor': pindah['nomor'], 'level': pindah['level'], 'teks': pindah['teks'],
        'is_numbered': True, 'children': []})
    d6['batasan_variabel']['sections'] = d6['batasan_variabel']['sections'][1:]
    t6 = qa.audit_pdf_json(kode, pdf, units[0]['mulai'], units[0]['akhir'], d6)['temuan']
    cek('paragraf salah bagian terdeteksi',
        {'pp_salah_bagian', 'bv_salah_bagian', 'teks_tidak_ada_di_pdf'} & jenis(t6),
        str(jenis(t6)))

    print("\n8. SUBBAGIAN PP DIHILANGKAN")
    d7 = copy.deepcopy(data_asli)
    if pp_nodes:
        d7['panduan_penilaian']['sections'] = d7['panduan_penilaian']['sections'][:-1]
    t7 = qa.audit_pdf_json(kode, pdf, units[0]['mulai'], units[0]['akhir'], d7)['temuan']
    cek('teks PDF tanpa pasangan JSON terdeteksi',
        'teks_pdf_tidak_masuk_json' in jenis(t7), str(jenis(t7)))

    # ------------------------------------------------------ 9 audit DOCX
    print("\n9. AUDIT DOCX (FILE NYATA)")
    docs = ds.daftar_dokumen()
    meta = next((d for d in docs if d.get('status') == 'siap_ditinjau' and d['jumlah_unit'] == 4), None)
    if not meta:
        meta = next((d for d in docs if d['jumlah_unit'] == 4), None)
    cek('dokumen Word 4 unit tersedia', meta is not None)
    if meta:
        ad = qa.audit_docx(meta)
        cek('audit DOCX tanpa temuan', not ad['temuan'], str([t['jenis'] for t in ad['temuan']]))
        cek('183 teks dibandingkan', ad['teks_diperiksa'] == 183, str(ad['teks_diperiksa']))
        cek('semua teks cocok', ad['teks_cocok'] == ad['teks_diperiksa'])
        cek('8 numId untuk 4 unit', ad['num_id'] == 8, str(ad['num_id']))

        # mutasi: hapus satu baris tabel KUK
        tmp_dir = project_root / 'output' / 'qa' / '_uji_docx'
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        asal = project_root / meta['berkas_docx']
        salinan = tmp_dir / asal.name
        shutil.copy(asal, salinan)
        doc = Document(str(salinan))
        tbl = doc.tables[0]
        tbl._tbl.remove(tbl.rows[-1]._tr)
        doc.save(str(salinan))

        dir_asli = ds.DOC_DIR
        ds.DOC_DIR = tmp_dir
        try:
            meta_uji = dict(meta, berkas_docx=str(salinan.relative_to(project_root)))
            ad2 = qa.audit_docx(meta_uji)
        finally:
            ds.DOC_DIR = dir_asli
        cek('KUK hilang pada DOCX terdeteksi', 'kuk_berbeda' in jenis(ad2['temuan']),
            str(jenis(ad2['temuan'])))
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # --------------------------------------------------- 10 laporan lengkap
    print("\n10. LAPORAN QA")
    lap = qa.jalankan_audit(meta)
    j, h = qa.simpan_laporan(lap)
    cek('laporan JSON tersimpan', j.exists() and j.stat().st_size > 500)
    cek('laporan HTML tersimpan', h.exists() and 'Laporan QA' in h.read_text(encoding='utf-8'))
    isi = json.loads(j.read_text(encoding='utf-8'))
    cek('ringkasan berisi hitungan temuan', 'critical' in isi['ringkasan'])
    cek('setiap unit punya status', all(u.get('status') for u in isi['unit']))
    cek('empat unit diaudit', isi['ringkasan']['unit_diaudit'] == 4)
    cek('tidak ada Critical pada data nyata', isi['ringkasan']['critical'] == 0,
        str([t for t in isi['temuan'] if t['keparahan'] == 'Critical'][:2]))

    print("\n" + "=" * 100)
    print(f"HASIL: {len(lulus)} lulus, {len(gagal)} gagal")
    if gagal:
        for g in gagal:
            print(f"  - {g}")
    print("=" * 100)
    return 0 if not gagal else 1




def test_qa_audit():
    assert main() == 0


if __name__ == '__main__':
    sys.exit(main())

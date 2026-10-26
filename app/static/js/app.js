/* SKKNI Extractor - perilaku antarmuka (Fase 4A) */
(function () {
  'use strict';

  /* Filter tabel di sisi klien: hanya menyembunyikan baris, tidak mengubah data. */
  function pasangFilter(input) {
    var tabel = document.querySelector('table[data-table="' + input.dataset.filter + '"]');
    if (!tabel) return;
    var baris = Array.prototype.slice.call(tabel.tBodies[0].rows);

    input.addEventListener('input', function () {
      var kata = input.value.trim().toLowerCase();
      var tampil = 0;
      baris.forEach(function (tr) {
        var cocok = !kata || tr.textContent.toLowerCase().indexOf(kata) !== -1;
        tr.hidden = !cocok;
        if (cocok) tampil++;
      });
      var kosong = tabel.parentNode.querySelector('.filter-kosong');
      if (!tampil && kata) {
        if (!kosong) {
          kosong = document.createElement('p');
          kosong.className = 'empty filter-kosong';
          kosong.textContent = 'Tidak ada baris yang cocok dengan pencarian.';
          tabel.parentNode.insertBefore(kosong, tabel.nextSibling);
        }
      } else if (kosong) {
        kosong.remove();
      }
    });
  }

  document.querySelectorAll('input[data-filter]').forEach(pasangFilter);


  /* --------------------------------------------------------------------
     Indikator proses (langkah 3.5, temuan T-09).
     Sebelumnya tidak ada umpan balik sama sekali: pengguna menekan tombol
     dua kali karena peramban tampak hang saat membuat 25 formulir Word.
     -------------------------------------------------------------------- */
  var overlay = null;

  function pastikanOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.className = 'proses-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-live', 'assertive');
    overlay.innerHTML =
      '<div class="proses-kotak">' +
      '  <div class="proses-lingkar" aria-hidden="true"></div>' +
      '  <span class="proses-teks">Memproses…</span>' +
      '  <span class="proses-sub">Mohon tunggu, jangan tutup halaman ini.</span>' +
      '</div>';
    document.body.appendChild(overlay);
    return overlay;
  }

  function tampilkanProses(teks, sub) {
    var ov = pastikanOverlay();
    ov.querySelector('.proses-teks').textContent = teks || 'Memproses…';
    var el = ov.querySelector('.proses-sub');
    el.textContent = sub || 'Mohon tunggu, jangan tutup halaman ini.';
    ov.classList.add('is-tampil');
  }

  function sembunyikanProses() {
    if (overlay) overlay.classList.remove('is-tampil');
  }

  /* Dipakai juga oleh halaman MUK saat menyimpan satu bagian. */
  window.tampilkanProses = tampilkanProses;
  window.sembunyikanProses = sembunyikanProses;

  var JEDA_MINIMUM = 400;   // agar indikator tidak berkedip untuk operasi cepat

  function matikanForm(form) {
    form.querySelectorAll('button, input[type="submit"]').forEach(function (b) {
      b.disabled = true;
      if (b.tagName === 'BUTTON' && !b.dataset.labelAsli) {
        b.dataset.labelAsli = b.textContent;
        b.textContent = 'Memproses…';
      }
    });
  }

  document.querySelectorAll('form').forEach(function (form) {
    if ((form.getAttribute('method') || 'get').toLowerCase() !== 'post') return;
    form.addEventListener('submit', function () {
      matikanForm(form);
      tampilkanProses(form.dataset.proses || 'Memproses…');
    });
  });

  /* Tautan yang memicu pembuatan berkas: beri tanda dan cegah klik ganda.
     Hanya tautan yang membuka di tab yang sama; pratinjau target=_blank
     selesai dalam hitungan milidetik dan tidak perlu indikator. */
  document.querySelectorAll('a[href*="/unduh-"]').forEach(function (a) {
    if (a.target === '_blank') return;
    a.addEventListener('click', function () {
      if (a.dataset.sedangUnduh === '1') { a.preventDefault(); return; }
      a.dataset.sedangUnduh = '1';
      tampilkanProses(
        a.dataset.proses || 'Menyiapkan berkas…',
        'Paket lengkap butuh sekitar 6 detik. Jangan tutup halaman ini.'
      );
      setTimeout(function () {
        a.dataset.sedangUnduh = '0';
        sembunyikanProses();
      }, 12000);
    });
  });

  /* Jaring pengaman: bila pengguna kembali ke halaman ini (mis. setelah
     unduhan selesai), indikator dimatikan. */
  window.addEventListener('focus', sembunyikanProses);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') sembunyikanProses();
  });

  /* Tandai item navigasi aktif bila server tidak menentukannya. */
  var jalur = window.location.pathname.replace(/\/$/, '') || '/';
  document.querySelectorAll('.nav-item').forEach(function (a) {
    var target = a.getAttribute('href').replace(/\/$/, '') || '/';
    a.classList.toggle('is-active', target === jalur);
  });
})();

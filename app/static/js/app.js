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

  /* Tandai item navigasi aktif bila server tidak menentukannya. */
  var jalur = window.location.pathname.replace(/\/$/, '') || '/';
  document.querySelectorAll('.nav-item').forEach(function (a) {
    var target = a.getAttribute('href').replace(/\/$/, '') || '/';
    a.classList.toggle('is-active', target === jalur);
  });
})();

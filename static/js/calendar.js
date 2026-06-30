(function () {
  'use strict';

  var grid = document.getElementById('calendar-grid');
  var agenda = document.getElementById('calendar-agenda');
  var filtersForm = document.getElementById('calendar-filters');

  if (!grid) return;

  var selectedDate = null;

  function attachDayClickHandlers() {
    document.querySelectorAll('.calendar-day-cell').forEach(function (cell) {
      cell.addEventListener('click', function (e) {
        if (e.target.closest('.calendar-event-item')) return;
        var date = cell.getAttribute('data-date');
        if (!date) return;

        if (selectedDate === date) {
          // Toggle off — show all sections
          selectedDate = null;
          document.querySelectorAll('.calendar-day-cell.selected').forEach(function (c) {
            c.classList.remove('selected');
          });
          document.querySelectorAll('.agenda-day-section').forEach(function (s) {
            s.classList.remove('agenda-hidden');
          });
        } else {
          // Show only this day
          selectedDate = date;
          document.querySelectorAll('.calendar-day-cell.selected').forEach(function (c) {
            c.classList.remove('selected');
          });
          cell.classList.add('selected');
          document.querySelectorAll('.agenda-day-section').forEach(function (s) {
            var isTarget = s.getAttribute('data-date') === date;
            s.classList.toggle('agenda-hidden', !isTarget);
          });
          // Scroll agenda section into view
          var target = document.querySelector('.agenda-day-section[data-date="' + date + '"]');
          if (target) {
            target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }
        }
      });
    });
  }

  function updateNavButtons() {
    var navBtns = document.querySelectorAll('.calendar-nav-btn');
    var urlParams = new URLSearchParams(window.location.search);
    var year = urlParams.get('year') || '';
    var month = urlParams.get('month') || '';
    if (year && month && navBtns.length >= 2) {
      var y = parseInt(year, 10);
      var m = parseInt(month, 10);
      var prevM = m === 1 ? 12 : m - 1;
      var prevY = m === 1 ? y - 1 : y;
      var nextM = m === 12 ? 1 : m + 1;
      var nextY = m === 12 ? y + 1 : y;
      navBtns[0].setAttribute('data-year', prevY);
      navBtns[0].setAttribute('data-month', prevM);
      navBtns[1].setAttribute('data-year', nextY);
      navBtns[1].setAttribute('data-month', nextM);
    }
  }

  document.querySelectorAll('.calendar-nav-btn').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      var year = btn.getAttribute('data-year');
      var month = btn.getAttribute('data-month');
      var params = new URLSearchParams();
      if (filtersForm) {
        var formData = new FormData(filtersForm);
        formData.forEach(function (value, key) {
          if (value) params.set(key, value);
        });
      }
      params.set('year', year);
      params.set('month', month);
      fetch('/events/calendar?' + params.toString(), { headers: { 'Accept': 'text/html' } })
        .then(function (r) { return r.text(); })
        .then(function (html) {
          var parser = new DOMParser();
          var doc = parser.parseFromString(html, 'text/html');
          var newGrid = doc.getElementById('calendar-grid');
          var newAgenda = doc.getElementById('calendar-agenda');
          var newNav = doc.querySelector('.calendar-nav');
          if (newGrid) grid.innerHTML = newGrid.innerHTML;
          if (newAgenda && agenda) agenda.outerHTML = newAgenda.outerHTML;
          agenda = document.getElementById('calendar-agenda');
          if (newNav) {
            var oldNav = document.querySelector('.calendar-nav');
            if (oldNav) oldNav.innerHTML = newNav.innerHTML;
          }
          selectedDate = null;
          history.pushState({ year: year, month: month }, '', '/events/calendar?' + params.toString());
          attachDayClickHandlers();
          updateNavButtons();
        })
        .catch(function (err) { console.error('Calendar nav error:', err); });
    });
  });

  attachDayClickHandlers();

  // ── Export toggle ──
  var exportBtn = document.getElementById('export-toggle-btn');
  var exportPanel = document.getElementById('export-panel');
  if (exportBtn && exportPanel) {
    exportBtn.addEventListener('click', function () {
      exportPanel.classList.toggle('hidden');
    });
  }

  // ── Clipboard copy ──
  var clipBtn = document.getElementById('clip-copy-btn');
  var exportDateFrom = document.getElementById('export-date-from');
  var exportDateTo = document.getElementById('export-date-to');
  var csvDateFrom = document.getElementById('csv-date-from');
  var csvDateTo = document.getElementById('csv-date-to');
  var csvForm = document.getElementById('csv-export-form');

  if (csvForm && exportDateFrom && exportDateTo && csvDateFrom && csvDateTo) {
    csvForm.addEventListener('submit', function () {
      csvDateFrom.value = exportDateFrom.value;
      csvDateTo.value = exportDateTo.value;
    });
  }

  if (clipBtn && exportDateFrom && exportDateTo) {
    clipBtn.addEventListener('click', function () {
      var orig = clipBtn.textContent;
      var params = new URLSearchParams();
      params.set('date_from', exportDateFrom.value);
      params.set('date_to', exportDateTo.value);
      if (filtersForm) {
        var formData = new FormData(filtersForm);
        formData.forEach(function (value, key) {
          if (value) params.set(key, value);
        });
      }
      fetch('/api/events/export-text?' + params.toString())
        .then(function (r) { return r.text(); })
        .then(function (text) {
          return navigator.clipboard.writeText(text).then(function () {
            clipBtn.textContent = '\u2713 ' + clipBtn.getAttribute('data-copied');
            clipBtn.disabled = true;
            setTimeout(function () {
              clipBtn.textContent = orig;
              clipBtn.disabled = false;
            }, 2000);
          });
        })
        .catch(function () {
          clipBtn.textContent = 'Error';
          setTimeout(function () { clipBtn.textContent = orig; }, 2000);
        });
    });
  }
})();
(function () {
  'use strict';

  var grid = document.getElementById('calendar-grid');
  var detailPanel = document.getElementById('calendar-day-detail');
  var filtersForm = document.getElementById('calendar-filters');

  if (!grid) return;

  function attachDayClickHandlers() {
    document.querySelectorAll('.calendar-day-cell').forEach(function (cell) {
      cell.addEventListener('click', function (e) {
        if (e.target.closest('.calendar-event-item')) return;
        var date = cell.getAttribute('data-date');
        if (!date) return;
        var params = new URLSearchParams();
        if (filtersForm) {
          var formData = new FormData(filtersForm);
          formData.forEach(function (value, key) {
            if (value) params.set(key, value);
          });
        }
        fetch('/api/events/calendar-day?' + params.toString() + '&date_str=' + encodeURIComponent(date))
          .then(function (r) { return r.text(); })
          .then(function (html) {
            if (detailPanel) {
              detailPanel.innerHTML = html;
              detailPanel.classList.remove('hidden');
            }
          })
          .catch(function (err) { console.error('Day detail error:', err); });
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
          var newDetail = doc.getElementById('calendar-day-detail');
          var newNav = doc.querySelector('.calendar-nav');
          if (newGrid) grid.innerHTML = newGrid.innerHTML;
          if (newDetail && detailPanel) detailPanel.outerHTML = newDetail.outerHTML;
          if (newNav) {
            var oldNav = document.querySelector('.calendar-nav');
            if (oldNav) oldNav.innerHTML = newNav.innerHTML;
          }
          history.pushState({ year: year, month: month }, '', '/events/calendar?' + params.toString());
          attachDayClickHandlers();
          updateNavButtons();
        })
        .catch(function (err) { console.error('Calendar nav error:', err); });
    });
  });

  document.addEventListener('click', function (e) {
    if (detailPanel && !detailPanel.classList.contains('hidden')) {
      if (!detailPanel.contains(e.target) && !e.target.closest('.calendar-day-cell')) {
        detailPanel.classList.add('hidden');
      }
    }
  });

  attachDayClickHandlers();
})();
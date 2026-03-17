(function () {
  'use strict';

  // ── Constants ──────────────────────────────────────────────────────────────
  var LS_KEY = 'promanager_player_columns';
  var DEFAULT_COLS = ['Team', 'Email', 'Active', 'Actions'];
  var ALL_COLS = [
    'Team', 'Email', 'Phone', 'Date of birth', 'Active',
    'Shirt number', 'Position', 'Injured until', 'Absent by default',
    'Priority', 'Actions'
  ];

  var cfg = window.PLAYERS_CONFIG || {};

  // ── localStorage helpers ───────────────────────────────────────────────────
  function loadVisibleCols() {
    try {
      var raw = localStorage.getItem(LS_KEY);
      if (!raw) return DEFAULT_COLS.slice();
      var parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return DEFAULT_COLS.slice();
      var valid = parsed.filter(function (c) { return ALL_COLS.indexOf(c) !== -1; });
      return valid.length ? valid : DEFAULT_COLS.slice();
    } catch (e) {
      return DEFAULT_COLS.slice();
    }
  }

  function saveVisibleCols(cols) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(cols)); } catch (e) {}
  }

  // ── Column visibility ──────────────────────────────────────────────────────
  function applyColumnVisibility(visibleCols) {
    ALL_COLS.forEach(function (col) {
      var show = visibleCols.indexOf(col) !== -1;
      document.querySelectorAll('#players-table [data-col="' + col + '"]').forEach(function (el) {
        el.style.display = show ? '' : 'none';
      });
    });
  }

  function initColumnsPopover() {
    var btn = document.getElementById('columns-btn');
    var popover = document.getElementById('columns-popover');
    if (!btn || !popover) return;

    var visibleCols = loadVisibleCols();

    popover.querySelectorAll('.col-toggle').forEach(function (cb) {
      cb.checked = visibleCols.indexOf(cb.dataset.col) !== -1;
    });
    applyColumnVisibility(visibleCols);

    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      popover.style.display = popover.style.display === 'none' ? 'block' : 'none';
    });

    popover.addEventListener('change', function (e) {
      if (!e.target.classList.contains('col-toggle')) return;
      var col = e.target.dataset.col;
      if (e.target.checked) {
        if (visibleCols.indexOf(col) === -1) visibleCols.push(col);
      } else {
        visibleCols = visibleCols.filter(function (c) { return c !== col; });
      }
      saveVisibleCols(visibleCols);
      applyColumnVisibility(visibleCols);
    });

    document.addEventListener('click', function (e) {
      if (!popover.contains(e.target) && e.target !== btn) {
        popover.style.display = 'none';
      }
    });
  }

  // ── CSRF ───────────────────────────────────────────────────────────────────
  function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
  }

  // ── Banner (safe DOM — no innerHTML with user data) ────────────────────────
  function showBanner(type, message, errors) {
    var banner = document.getElementById('bulk-banner');
    if (!banner) return;

    while (banner.firstChild) banner.removeChild(banner.firstChild);

    var bg = type === 'error' ? '#fde8e8'
           : type === 'success' ? '#d4edda'
           : '#fff3cd';
    banner.style.cssText = 'display:block;padding:.75rem 1rem;border-radius:.35rem;background:' + bg + ';position:relative;';
    banner.appendChild(document.createTextNode(message));

    if (errors && errors.length) {
      var details = document.createElement('details');
      details.style.marginTop = '.5rem';
      var summary = document.createElement('summary');
      summary.textContent = errors.length + ' error(s)';
      details.appendChild(summary);
      var ul = document.createElement('ul');
      ul.style.cssText = 'margin:.25rem 0 0 1rem;';
      errors.forEach(function (err) {
        var li = document.createElement('li');
        li.textContent = 'Player ' + err.id + ': ' + err.message;
        ul.appendChild(li);
      });
      details.appendChild(ul);
      banner.appendChild(details);
    }

    var closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.textContent = '×';
    closeBtn.style.cssText = 'position:absolute;top:.5rem;right:.75rem;background:none;border:none;cursor:pointer;font-size:1rem;line-height:1;';
    closeBtn.addEventListener('click', function () { banner.style.display = 'none'; });
    banner.appendChild(closeBtn);
  }

  // ── Edit mode ──────────────────────────────────────────────────────────────
  var pendingChanges = {};

  function enterEditMode() {
    document.getElementById('edit-btn').style.display = 'none';
    document.getElementById('save-btn').style.display = '';
    document.getElementById('cancel-btn').style.display = '';
    document.querySelectorAll('#players-table tbody tr').forEach(function (row) {
      row.querySelectorAll('td[data-field]').forEach(function (cell) {
        cell.querySelector('.cell-view').style.display = 'none';
        var input = cell.querySelector('.cell-input');
        if (input) input.style.display = '';
      });
    });
  }

  function exitEditMode(discard) {
    document.getElementById('edit-btn').style.display = '';
    document.getElementById('save-btn').style.display = 'none';
    document.getElementById('cancel-btn').style.display = 'none';

    document.querySelectorAll('#players-table tbody tr').forEach(function (row) {
      row.querySelectorAll('td[data-field]').forEach(function (cell) {
        cell.querySelector('.cell-view').style.display = '';
        var input = cell.querySelector('.cell-input');
        if (input) {
          input.style.display = 'none';
          if (discard) {
            var orig = cell.dataset.value;
            if (input.type === 'checkbox') {
              input.checked = orig === 'true';
            } else {
              input.value = orig;
            }
            cell.style.backgroundColor = '';
          }
        }
      });
      var errSpan = row.querySelector('.row-error');
      if (errSpan) errSpan.remove();
    });
    if (discard) pendingChanges = {};
  }

  function trackCellChange(cell, input) {
    var pid = cell.closest('tr').dataset.playerId;
    var field = cell.dataset.field;
    var orig = cell.dataset.value;

    function onChange() {
      var newVal = input.type === 'checkbox'
        ? (input.checked ? 'true' : 'false')
        : input.value;
      var changed = newVal !== orig;
      cell.style.backgroundColor = changed ? '#fff9c4' : '';

      if (!pendingChanges[pid]) pendingChanges[pid] = {};
      if (changed) {
        pendingChanges[pid][field] = input.type === 'checkbox' ? input.checked : input.value;
      } else {
        delete pendingChanges[pid][field];
        if (Object.keys(pendingChanges[pid]).length === 0) delete pendingChanges[pid];
      }

      var saveBtn = document.getElementById('save-btn');
      if (saveBtn) saveBtn.disabled = Object.keys(pendingChanges).length === 0;
    }

    input.addEventListener('change', onChange);
    input.addEventListener('input', onChange);
  }

  function initEditMode() {
    var editBtn = document.getElementById('edit-btn');
    var saveBtn = document.getElementById('save-btn');
    var cancelBtn = document.getElementById('cancel-btn');
    if (!editBtn) return;

    editBtn.addEventListener('click', enterEditMode);
    cancelBtn.addEventListener('click', function () { exitEditMode(true); });

    document.querySelectorAll('#players-table tbody tr').forEach(function (row) {
      row.querySelectorAll('td[data-field]').forEach(function (cell) {
        var input = cell.querySelector('.cell-input');
        if (input) trackCellChange(cell, input);
      });
    });

    saveBtn.addEventListener('click', function () {
      if (Object.keys(pendingChanges).length === 0) return;
      doSave();
    });
  }

  function doSave() {
    var players = Object.keys(pendingChanges).map(function (pid) {
      return Object.assign({ id: parseInt(pid, 10) }, pendingChanges[pid]);
    });
    var body = { players: players };
    if (cfg.seasonId) body.season_id = cfg.seasonId;
    if (cfg.teamId) body.team_id = cfg.teamId;

    fetch('/players/bulk-update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
      body: JSON.stringify(body),
    })
    .then(function (r) {
      if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || r.statusText); });
      return r.json();
    })
    .then(function (data) {
      data.saved.forEach(function (pid) {
        var row = document.querySelector('#players-table tr[data-player-id="' + pid + '"]');
        if (!row) return;
        row.querySelectorAll('td[data-field]').forEach(function (cell) {
          cell.style.backgroundColor = '';
          var input = cell.querySelector('.cell-input');
          if (input) {
            var newVal = input.type === 'checkbox'
              ? (input.checked ? 'true' : 'false')
              : input.value;
            cell.dataset.value = newVal;
            var view = cell.querySelector('.cell-view');
            if (view && input.type !== 'checkbox') {
              view.textContent = input.value || '—';
            }
          }
        });
        delete pendingChanges[pid];
      });

      data.errors.forEach(function (err) {
        var row = document.querySelector('#players-table tr[data-player-id="' + err.id + '"]');
        if (!row) return;
        row.querySelectorAll('td[data-field]').forEach(function (cell) {
          cell.style.backgroundColor = '#fde8e8';
        });
        var existing = row.querySelector('.row-error');
        if (existing) existing.remove();
        var span = document.createElement('span');
        span.className = 'row-error';
        span.style.cssText = 'color:#c00;font-size:.8rem;margin-left:.5rem;';
        span.textContent = err.message;
        row.querySelector('td:last-child').appendChild(span);
      });

      var saveBtn = document.getElementById('save-btn');
      if (saveBtn) saveBtn.disabled = Object.keys(pendingChanges).length === 0;
      if (data.errors.length === 0) exitEditMode(false);
    })
    .catch(function (err) {
      showBanner('error', (err && err.message) || 'Save failed — network error. Please try again.', null);
    });
  }

  // ── Row selection & bulk toolbar ───────────────────────────────────────────
  function getCheckedRows() {
    return Array.from(document.querySelectorAll('#players-table .row-check:checked'));
  }

  function updateToolbar() {
    var checked = getCheckedRows();
    var toolbar = document.getElementById('bulk-toolbar');
    var countEl = document.getElementById('bulk-count');
    if (!toolbar) return;
    toolbar.style.display = checked.length > 0 ? 'flex' : 'none';
    if (countEl) countEl.textContent = checked.length + ' row' + (checked.length !== 1 ? 's' : '') + ' selected';
  }

  function initBulkToolbar() {
    var selectAll = document.getElementById('select-all');
    if (!selectAll) return;

    selectAll.addEventListener('change', function () {
      document.querySelectorAll('#players-table .row-check').forEach(function (cb) {
        cb.checked = selectAll.checked;
      });
      updateToolbar();
    });

    document.querySelectorAll('#players-table .row-check').forEach(function (cb) {
      cb.addEventListener('change', function () {
        updateToolbar();
        var all = document.querySelectorAll('#players-table .row-check');
        var allChecked = Array.from(all).every(function (c) { return c.checked; });
        selectAll.checked = allChecked;
        selectAll.indeterminate = !allChecked && Array.from(all).some(function (c) { return c.checked; });
      });
    });

    var clearBtn = document.getElementById('clear-selection-btn');
    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        document.querySelectorAll('#players-table .row-check').forEach(function (cb) { cb.checked = false; });
        selectAll.checked = false;
        selectAll.indeterminate = false;
        updateToolbar();
      });
    }

    var setActiveBtn = document.getElementById('set-active-btn');
    var setInactiveBtn = document.getElementById('set-inactive-btn');
    if (setActiveBtn) setActiveBtn.addEventListener('click', function () { bulkSetActive(true); });
    if (setInactiveBtn) setInactiveBtn.addEventListener('click', function () { bulkSetActive(false); });

    // Assign to team dropdown
    var assignBtn = document.getElementById('assign-btn');
    var assignSelect = document.getElementById('assign-team-select');
    if (assignBtn && assignSelect) {
      assignBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        if (assignBtn.disabled) return;
        assignSelect.style.display = assignSelect.style.display === 'none' ? 'block' : 'none';
      });
      assignSelect.addEventListener('change', function () {
        var teamId = parseInt(assignSelect.value, 10);
        if (!teamId) return;
        assignSelect.value = '';
        assignSelect.style.display = 'none';
        bulkAssign(teamId);
      });
      document.addEventListener('click', function (e) {
        if (e.target !== assignBtn && e.target !== assignSelect) {
          assignSelect.style.display = 'none';
        }
      });
    }

    // Age filter
    var ageToggle = document.getElementById('age-filter-toggle');
    var agePanel = document.getElementById('age-filter-panel');
    if (ageToggle && agePanel) {
      ageToggle.addEventListener('click', function () {
        agePanel.style.display = agePanel.style.display === 'none' ? 'flex' : 'none';
      });
    }
    var ageAfter = document.getElementById('age-after');
    var ageBefore = document.getElementById('age-before');
    if (ageAfter) ageAfter.addEventListener('input', applyAgeFilter);
    if (ageBefore) ageBefore.addEventListener('input', applyAgeFilter);
  }

  function applyAgeFilter() {
    var ageAfter = document.getElementById('age-after');
    var ageBefore = document.getElementById('age-before');
    var after = ageAfter && ageAfter.value ? new Date(ageAfter.value) : null;
    var before = ageBefore && ageBefore.value ? new Date(ageBefore.value) : null;
    if (!after && !before) {
      document.querySelectorAll('#players-table .row-check').forEach(function (cb) { cb.checked = false; });
      var selectAll = document.getElementById('select-all');
      if (selectAll) { selectAll.checked = false; selectAll.indeterminate = false; }
      updateToolbar();
      return;
    }

    document.querySelectorAll('#players-table tbody tr').forEach(function (row) {
      var cb = row.querySelector('.row-check');
      if (!cb) return;
      var dob = row.dataset.dob;
      if (!dob) { cb.checked = false; return; }
      var d = new Date(dob);
      cb.checked = (!after || d >= after) && (!before || d <= before);
    });

    var selectAll = document.getElementById('select-all');
    if (selectAll) selectAll.indeterminate = true;
    updateToolbar();
  }

  function bulkSetActive(isActive) {
    var ids = getCheckedRows().map(function (cb) {
      return parseInt(cb.closest('tr').dataset.playerId, 10);
    });
    if (!ids.length) return;

    fetch('/players/bulk-update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
      body: JSON.stringify({ players: ids.map(function (id) { return { id: id, is_active: isActive }; }) }),
    })
    .then(function (r) {
      if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || r.statusText); });
      return r.json();
    })
    .then(function (data) {
      var msg = data.saved.length + ' player(s) updated.';
      showBanner(
        data.errors.length ? 'warning' : 'success',
        data.errors.length ? msg + ' ' + data.errors.length + ' failed.' : msg,
        data.errors.length ? data.errors : null
      );
      if (data.saved.length) setTimeout(function () { location.reload(); }, 800);
    })
    .catch(function (err) { showBanner('error', (err && err.message) || 'Network error. Please try again.', null); });
  }

  function bulkAssign(teamId) {
    var ids = getCheckedRows().map(function (cb) {
      return parseInt(cb.closest('tr').dataset.playerId, 10);
    });
    if (!ids.length || !cfg.seasonId) return;

    fetch('/players/bulk-assign', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
      body: JSON.stringify({ player_ids: ids, team_id: teamId, season_id: cfg.seasonId }),
    })
    .then(function (r) {
      if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || r.statusText); });
      return r.json();
    })
    .then(function (data) {
      var msg = data.assigned + ' assigned, ' + data.skipped + ' skipped.';
      showBanner(
        data.errors.length ? 'warning' : 'success',
        msg,
        data.errors.length ? data.errors : null
      );
      if (data.assigned > 0) setTimeout(function () { location.reload(); }, 800);
    })
    .catch(function (err) { showBanner('error', (err && err.message) || 'Network error. Please try again.', null); });
  }

  // ── Boot ───────────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    initColumnsPopover();
    initEditMode();
    initBulkToolbar();
  });

})();

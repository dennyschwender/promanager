(function () {
  'use strict';

  // ── Constants ──────────────────────────────────────────────────────────────
  var LS_KEY = 'promanager_player_columns_v2';
  var LS_ORDER_KEY = 'promanager_player_col_order';
  var _params = new URLSearchParams(window.location.search);
  var HAS_TEAM_FILTER = !!(_params.get('season_id') && _params.get('team_id'));
  var LS_ORDER_KEY = 'promanager_player_col_order';
  var DEFAULT_COLS = ['Team', 'Email', 'Active', 'Has User', 'Actions'];
  var ALL_COLS = ['Team', 'Email', 'Phone', 'Date of birth', 'Active', 'Has User', 'Role', 'Shirt number', 'Position', 'Status', 'Injured until', 'Absent by default', 'Priority', 'Actions'];
  // Columns that only contain meaningful data when a season is selected
  var PT_COLS = ['Role', 'Shirt number', 'Position', 'Status', 'Injured until', 'Absent by default', 'Priority'];

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
      // Force-hide season-specific columns when no season is selected
      if (!cfg.seasonId && PT_COLS.indexOf(col) !== -1) show = false;
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
      if (!cfg.seasonId && PT_COLS.indexOf(cb.dataset.col) !== -1) {
        cb.disabled = true;
        cb.checked = false;
        cb.parentElement.title = window.I18N.select_season_hint;
        cb.parentElement.style.opacity = '0.45';
      }
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
      summary.textContent = window.I18N.errors_count.replace('%{count}', errors.length);
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
    var table = document.getElementById('players-table');
    table.classList.add('edit-mode');
    if (HAS_TEAM_FILTER) table.classList.add('team-filtered');
    if (!HAS_TEAM_FILTER) table.classList.add('pt-hidden');
    document.getElementById('edit-btn').style.display = 'none';
    var notice = document.getElementById('pt-edit-notice');
    if (notice) notice.style.display = HAS_TEAM_FILTER ? 'none' : '';
    document.getElementById('save-btn').style.display = '';
    document.getElementById('cancel-btn').style.display = '';
    document.querySelectorAll('#players-table tbody tr').forEach(function (row) {
      row.querySelectorAll('td[data-field]').forEach(function (cell) {
        var input = cell.querySelector('.cell-input');
        if (input && !input.disabled) {
          cell.querySelector('.cell-view').style.display = 'none';
          input.style.display = '';
        }
        // disabled pt-fields: leave cell-view visible so stacked values remain readable
      });
    });
  }

  function exitEditMode(discard) {
    var table = document.getElementById('players-table');
    table.classList.remove('edit-mode');
    table.classList.remove('pt-hidden');
    table.classList.remove('team-filtered');
    var notice = document.getElementById('pt-edit-notice');
    if (notice) notice.style.display = 'none';
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

      // Status → Injured until coupling
      var statusSel = row.querySelector('td[data-field="membership_status"] select.cell-input');
      var injuredIn = row.querySelector('.injured-until-input');
      if (statusSel && injuredIn) {
        statusSel.addEventListener('change', function () {
          var isInjured = statusSel.value === 'injured';
          injuredIn.disabled = !isInjured;
          injuredIn.style.display = isInjured ? '' : 'none';
          var view = injuredIn.closest('td') && injuredIn.closest('td').querySelector('.cell-view');
          if (view) view.style.display = isInjured ? 'none' : '';
          if (!isInjured) injuredIn.value = '';
        });
      }
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
      showBanner('error', (err && err.message) || window.I18N.save_failed, null);
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

    var hasInactive = false, hasActive = false, hasNotArchived = false, hasArchived = false;
    checked.forEach(function (cb) {
      var row = cb.closest('tr');
      var isActive = row.dataset.isActive === 'true';
      var isArchived = !!row.dataset.archivedAt;
      if (!isArchived && !isActive) hasInactive = true;
      if (!isArchived && isActive)  hasActive   = true;
      if (!isArchived)              hasNotArchived = true;
      if (isArchived)               hasArchived  = true;
    });

    var activateBtn   = document.getElementById('bulk-activate-btn');
    var deactivateBtn = document.getElementById('bulk-deactivate-btn');
    var archiveBtn    = document.getElementById('bulk-archive-btn');
    var unarchiveBtn  = document.getElementById('bulk-unarchive-btn');
    if (activateBtn)   activateBtn.style.display   = hasInactive    ? '' : 'none';
    if (deactivateBtn) deactivateBtn.style.display = hasActive      ? '' : 'none';
    if (archiveBtn)    archiveBtn.style.display    = hasNotArchived ? '' : 'none';
    if (unarchiveBtn)  unarchiveBtn.style.display  = hasArchived    ? '' : 'none';

    // "Create User" button — only for players without a linked user
    var createUserBtn = document.getElementById('bulk-create-user-btn');
    var createUserIds = document.getElementById('bulk-create-user-ids');
    if (createUserBtn && createUserIds) {
      var noUserIds = checked
        .filter(function (cb) { return cb.dataset.hasUser !== 'true'; })
        .map(function (cb) { return cb.closest('tr').dataset.playerId; })
        .filter(Boolean);
      createUserIds.value = noUserIds.join(',');
      createUserBtn.style.display = noUserIds.length > 0 ? '' : 'none';
    }
  }

  function bulkPost(url, ids, resultKey, reloadOnCount) {
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
      body: JSON.stringify({ player_ids: ids }),
    })
    .then(function (r) { return r.ok ? r.json() : r.json().then(function (e) { throw new Error(e.detail || 'Error'); }); })
    .then(function (data) {
      var count = data[resultKey] || 0;
      showBanner(data.errors && data.errors.length ? 'warning' : 'success',
        count + ' ' + resultKey + ', ' + (data.skipped || 0) + ' skipped.', null);
      if (count > 0) setTimeout(function () { location.reload(); }, 800);
    })
    .catch(function (err) { showBanner('error', (err && err.message) || window.I18N.network_error, null); });
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

    var bulkActivateBtn = document.getElementById('bulk-activate-btn');
    if (bulkActivateBtn) {
      bulkActivateBtn.addEventListener('click', function () {
        var ids = getCheckedRows()
          .map(function (cb) { return cb.closest('tr'); })
          .filter(function (row) { return row.dataset.isActive === 'false' && !row.dataset.archivedAt; })
          .map(function (row) { return parseInt(row.dataset.playerId, 10); });
        if (ids.length) bulkPost('/players/bulk-activate', ids, 'activated', true);
      });
    }

    var bulkDeactivateBtn = document.getElementById('bulk-deactivate-btn');
    if (bulkDeactivateBtn) {
      bulkDeactivateBtn.addEventListener('click', function () {
        var ids = getCheckedRows()
          .map(function (cb) { return cb.closest('tr'); })
          .filter(function (row) { return row.dataset.isActive === 'true' && !row.dataset.archivedAt; })
          .map(function (row) { return parseInt(row.dataset.playerId, 10); });
        if (ids.length) bulkPost('/players/bulk-deactivate', ids, 'deactivated', true);
      });
    }

    var bulkUnarchiveBtn = document.getElementById('bulk-unarchive-btn');
    if (bulkUnarchiveBtn) {
      bulkUnarchiveBtn.addEventListener('click', function () {
        var ids = getCheckedRows()
          .map(function (cb) { return cb.closest('tr'); })
          .filter(function (row) { return !!row.dataset.archivedAt; })
          .map(function (row) { return parseInt(row.dataset.playerId, 10); });
        if (ids.length) bulkPost('/players/bulk-unarchive', ids, 'unarchived', true);
      });
    }

    // Assign to team+season picker
    var allPickers = [];

    function closeAllPickers() {
      allPickers.forEach(function (p) { p.style.display = 'none'; });
    }

    function initPicker(btnId, pickerId, teamSelId, seasonSelId, confirmBtnId, onConfirm) {
      var btn        = document.getElementById(btnId);
      var picker     = document.getElementById(pickerId);
      var teamSel    = document.getElementById(teamSelId);
      var seasonSel  = document.getElementById(seasonSelId);
      var confirmBtn = document.getElementById(confirmBtnId);
      if (!btn || !picker || !teamSel || !seasonSel || !confirmBtn) return;
      allPickers.push(picker);

      (cfg.teams || []).forEach(function (id, i) {
        var opt = document.createElement('option');
        opt.value = id; opt.textContent = (cfg.teamNames || [])[i] || id;
        teamSel.appendChild(opt);
      });
      (cfg.seasons || []).forEach(function (id, i) {
        var opt = document.createElement('option');
        opt.value = id; opt.textContent = (cfg.seasonNames || [])[i] || id;
        seasonSel.appendChild(opt);
      });

      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var open = picker.style.display === 'flex';
        closeAllPickers();
        if (!open) { picker.style.display = 'flex'; teamSel.value = ''; seasonSel.value = ''; }
      });

      confirmBtn.addEventListener('click', function () {
        var teamId   = parseInt(teamSel.value,   10);
        var seasonId = parseInt(seasonSel.value, 10);
        if (!teamId || !seasonId) { showBanner('error', 'Please select both a team and a season.', null); return; }
        picker.style.display = 'none';
        onConfirm(teamId, seasonId);
      });

    }

    document.addEventListener('click', function (e) {
      var insideAny = allPickers.some(function (p) { return p.contains(e.target); });
      var isBtn = e.target.closest('#assign-btn, #remove-from-team-btn');
      if (!insideAny && !isBtn) closeAllPickers();
    });

    initPicker('assign-btn', 'assign-picker', 'assign-team-select', 'assign-season-select', 'assign-confirm-btn',
      function (teamId, seasonId) { bulkAssign(teamId, seasonId); }
    );

    initPicker('remove-from-team-btn', 'remove-picker', 'remove-team-select', 'remove-season-select', 'remove-confirm-btn',
      function (teamId, seasonId) {
        var ids = getCheckedRows().map(function (cb) { return parseInt(cb.closest('tr').dataset.playerId, 10); });
        if (!ids.length) return;
        fetch('/players/bulk-remove', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
          body: JSON.stringify({ player_ids: ids, team_id: teamId, season_id: seasonId }),
        })
          .then(function (r) { return r.ok ? r.json() : r.json().then(function (e) { throw new Error(e.detail || 'Error'); }); })
          .then(function (data) {
            showBanner('success', window.I18N.removed_count.replace('%{removed}', data.removed).replace('%{skipped}', data.skipped), null);
            if (data.removed > 0) setTimeout(function () { location.reload(); }, 800);
          })
          .catch(function (err) { showBanner('error', (err && err.message) || window.I18N.network_error, null); });
      }
    );

    var bulkArchiveBtn = document.getElementById('bulk-archive-btn');
    if (bulkArchiveBtn) {
      bulkArchiveBtn.addEventListener('click', function () {
        var rows = getCheckedRows()
          .map(function (cb) { return cb.closest('tr'); })
          .filter(function (row) { return !row.dataset.archivedAt; });
        if (!rows.length) return;
        openArchiveDialog(
          rows.map(function (row) {
            return {
              id: parseInt(row.dataset.playerId, 10),
              name: (row.querySelector('td:nth-child(2) a') || {}).textContent || window.I18N.player_fallback,
              dob: row.dataset.dob || '',
            };
          })
        );
      });
    }

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
      var msg = window.I18N.updated_count.replace('%{count}', data.saved.length);
      showBanner(
        data.errors.length ? 'warning' : 'success',
        data.errors.length ? msg + ' ' + data.errors.length + ' failed.' : msg,
        data.errors.length ? data.errors : null
      );
      if (data.saved.length) setTimeout(function () { location.reload(); }, 800);
    })
    .catch(function (err) { showBanner('error', (err && err.message) || window.I18N.network_error, null); });
  }

  function bulkAssign(teamId, seasonId) {
    var ids = getCheckedRows().map(function (cb) {
      return parseInt(cb.closest('tr').dataset.playerId, 10);
    });
    if (!ids.length || !teamId || !seasonId) return;

    fetch('/players/bulk-assign', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
      body: JSON.stringify({ player_ids: ids, team_id: teamId, season_id: seasonId }),
    })
    .then(function (r) {
      if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || r.statusText); });
      return r.json();
    })
    .then(function (data) {
      var msg = window.I18N.assigned_count.replace('%{count}', data.assigned).replace('%{skipped}', data.skipped || 0);
      showBanner(
        data.errors.length ? 'warning' : 'success',
        msg,
        data.errors.length ? data.errors : null
      );
      if (data.assigned > 0) setTimeout(function () { location.reload(); }, 800);
    })
    .catch(function (err) { showBanner('error', (err && err.message) || window.I18N.network_error, null); });
  }

  // ── Action dropdowns ───────────────────────────────────────────────────────
  function closeAllDropdowns() {
    document.querySelectorAll('.action-dropdown-menu.open').forEach(function (m) {
      m.classList.remove('open');
      m.classList.remove('open-up');
    });
    document.querySelectorAll('.table-responsive.dropdown-open').forEach(function (w) {
      w.classList.remove('dropdown-open');
    });
  }
  function initActionDropdowns() {
    document.addEventListener('click', function (e) {
      var toggle = e.target.closest('.action-dropdown-toggle');
      if (toggle) {
        e.stopPropagation();
        var menu = toggle.nextElementSibling;
        var isOpen = menu.classList.contains('open');
        closeAllDropdowns();
        if (!isOpen) {
          var rect = toggle.getBoundingClientRect();
          var spaceBelow = window.innerHeight - rect.bottom;
          menu.classList.add('open');
          if (spaceBelow < 120) menu.classList.add('open-up');
          var wrapper = toggle.closest('.table-responsive');
          if (wrapper) wrapper.classList.add('dropdown-open');
        }
        return;
      }
      closeAllDropdowns();
    });
  }

  // ── Column reordering ─────────────────────────────────────────────────────
  function loadColOrder() {
    try {
      var raw = localStorage.getItem(LS_ORDER_KEY);
      if (!raw) return ALL_COLS.slice();
      var parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return ALL_COLS.slice();
      var valid = parsed.filter(function (c) { return ALL_COLS.indexOf(c) !== -1; });
      ALL_COLS.forEach(function (c) { if (valid.indexOf(c) === -1) valid.push(c); });
      return valid;
    } catch (e) { return ALL_COLS.slice(); }
  }

  function saveColOrder(order) {
    try { localStorage.setItem(LS_ORDER_KEY, JSON.stringify(order)); } catch (e) {}
  }

  function applyColOrder(order) {
    var table = document.getElementById('players-table');
    if (!table) return;
    ALL_COLS.length = 0;
    order.forEach(function (c) { ALL_COLS.push(c); });
    var headerRow = table.querySelector('thead tr');
    var thMap = {};
    headerRow.querySelectorAll('th[data-col]').forEach(function (th) { thMap[th.dataset.col] = th; });
    headerRow.querySelectorAll('th[data-col]').forEach(function (th) { th.remove(); });
    order.forEach(function (col) { if (thMap[col]) headerRow.appendChild(thMap[col]); });
    table.querySelectorAll('tbody tr').forEach(function (row) {
      var tdMap = {};
      row.querySelectorAll('td[data-col]').forEach(function (td) { tdMap[td.dataset.col] = td; });
      row.querySelectorAll('td[data-col]').forEach(function (td) { td.remove(); });
      order.forEach(function (col) { if (tdMap[col]) row.appendChild(tdMap[col]); });
    });
  }

  function initColReorder() {
    var table = document.getElementById('players-table');
    if (!table) return;
    applyColOrder(loadColOrder());
    var dragSrcCol = null;
    var headerRow = table.querySelector('thead tr');
    headerRow.querySelectorAll('th[data-col]').forEach(function (th) {
      th.draggable = true;
      th.style.cursor = 'grab';
      th.addEventListener('dragstart', function (e) {
        dragSrcCol = th.dataset.col;
        th.classList.add('col-dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', dragSrcCol);
      });
      th.addEventListener('dragend', function () {
        th.classList.remove('col-dragging');
        headerRow.querySelectorAll('th[data-col]').forEach(function (h) { h.classList.remove('col-drag-over'); });
      });
      th.addEventListener('dragover', function (e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        headerRow.querySelectorAll('th[data-col]').forEach(function (h) { h.classList.remove('col-drag-over'); });
        th.classList.add('col-drag-over');
      });
      th.addEventListener('dragleave', function () { th.classList.remove('col-drag-over'); });
      th.addEventListener('drop', function (e) {
        e.preventDefault();
        th.classList.remove('col-drag-over');
        var targetCol = th.dataset.col;
        if (!dragSrcCol || dragSrcCol === targetCol) return;
        var currentOrder = ALL_COLS.slice();
        var srcIdx = currentOrder.indexOf(dragSrcCol);
        var tgtIdx = currentOrder.indexOf(targetCol);
        if (srcIdx === -1 || tgtIdx === -1) return;
        currentOrder.splice(srcIdx, 1);
        currentOrder.splice(tgtIdx, 0, dragSrcCol);
        saveColOrder(currentOrder);
        applyColOrder(currentOrder);
        initColReorder();
      });
    });
  }

  // ── Advanced filter ───────────────────────────────────────────────────────
  var ADV_FILTER_FIELDS = [
    { key: 'name',          label: window.I18N.filter_name,       type: 'text' },
    { key: 'email',         label: window.I18N.filter_email,      type: 'text' },
    { key: 'phone',         label: window.I18N.filter_phone,      type: 'text' },
    { key: 'date_of_birth', label: window.I18N.filter_dob,        type: 'daterange' },
    { key: 'is_active',     label: window.I18N.filter_active,     type: 'boolean', boolLabels: [window.I18N.bool_active, window.I18N.bool_inactive] },
    { key: 'shirt_number',  label: window.I18N.filter_shirt,      type: 'number' },
    { key: 'position',      label: window.I18N.filter_position,   type: 'text' },
    { key: 'priority',      label: window.I18N.filter_priority,   type: 'number' },
    { key: 'has_membership', label: window.I18N.filter_membership, type: 'boolean', boolLabels: [window.I18N.bool_yes, window.I18N.bool_no] },
  ];
  var ADV_TEXT_OPS = [
    { value: 'contains',     label: window.I18N.op_contains },
    { value: 'not_contains', label: window.I18N.op_not_contains },
    { value: 'equals',       label: window.I18N.op_equals },
    { value: 'starts_with',  label: window.I18N.op_starts_with },
    { value: 'is_empty',     label: window.I18N.op_empty },
    { value: 'is_not_empty', label: window.I18N.op_not_empty },
  ];
  var ADV_NUM_OPS = [
    { value: 'eq',           label: '=' },
    { value: 'neq',          label: '≠' },
    { value: 'lt',           label: '<' },
    { value: 'gt',           label: '>' },
    { value: 'is_empty',     label: window.I18N.op_empty },
    { value: 'is_not_empty', label: window.I18N.op_not_empty },
  ];

  function getRowValue(row, fieldKey) {
    function valOf(sel) { var el = row.querySelector(sel); return el ? (el.dataset.value || '') : ''; }
    switch (fieldKey) {
      case 'name': {
        var nameParts = [];
        var tds = Array.from(row.querySelectorAll('td'));
        for (var i = 0; i < tds.length; i++) {
          if (!tds[i].dataset.col && tds[i].querySelector('a')) nameParts.push(tds[i].textContent.trim());
        }
        return nameParts.join(' ').toLowerCase();
      }
      case 'email':         return valOf('td[data-col="Email"]');
      case 'phone':         return valOf('td[data-col="Phone"]');
      case 'date_of_birth': return valOf('td[data-col="Date of birth"]');
      case 'is_active':     return valOf('td[data-col="Active"]');
      case 'shirt_number':  return valOf('td[data-col="Shirt number"]');
      case 'position':      return valOf('td[data-col="Position"]');
      case 'priority':      return valOf('td[data-col="Priority"]');
      case 'has_membership': {
        var td = row.querySelector('td[data-col="Team"]');
        return td ? (parseInt(td.dataset.value || '0', 10) > 0 ? 'true' : 'false') : 'false';
      }
      default: return '';
    }
  }

  function testTextOp(rowVal, op, filterVal) {
    var rv = rowVal.toLowerCase(), fv = filterVal.toLowerCase().trim();
    switch (op) {
      case 'contains':     return rv.indexOf(fv) !== -1;
      case 'not_contains': return rv.indexOf(fv) === -1;
      case 'equals':       return rv === fv;
      case 'starts_with':  return rv.indexOf(fv) === 0;
      case 'is_empty':     return rv === '' || rv === '\u2014';
      case 'is_not_empty': return rv !== '' && rv !== '\u2014';
      default: return true;
    }
  }

  function testNumOp(rowVal, op, filterVal) {
    if (op === 'is_empty')     return rowVal === '';
    if (op === 'is_not_empty') return rowVal !== '';
    var rv = parseFloat(rowVal), fv = parseFloat(filterVal);
    if (isNaN(rv) || isNaN(fv)) return false;
    switch (op) {
      case 'eq':  return rv === fv;
      case 'neq': return rv !== fv;
      case 'lt':  return rv < fv;
      case 'gt':  return rv > fv;
      default: return true;
    }
  }

  function rowMatchesCondition(row, c) {
    var def = null;
    for (var i = 0; i < ADV_FILTER_FIELDS.length; i++) {
      if (ADV_FILTER_FIELDS[i].key === c.field) { def = ADV_FILTER_FIELDS[i]; break; }
    }
    if (!def) return true;
    var rowVal = getRowValue(row, c.field);
    if (def.type === 'boolean')   return c.boolVal === 'any' || rowVal === c.boolVal;
    if (def.type === 'daterange') {
      if (!c.dateFrom && !c.dateTo) return true;
      if (!rowVal) return false;
      if (c.dateFrom && rowVal < c.dateFrom) return false;
      if (c.dateTo   && rowVal > c.dateTo)   return false;
      return true;
    }
    if (def.type === 'text')   return testTextOp(rowVal, c.op, c.value || '');
    if (def.type === 'number') return testNumOp(rowVal, c.op, c.value || '');
    return true;
  }

  function readConditions() {
    var conditions = [];
    document.querySelectorAll('#adv-filter-rows .adv-filter-row').forEach(function (rowEl) {
      var fieldKey = rowEl.querySelector('.adv-field-sel').value;
      var def = null;
      for (var i = 0; i < ADV_FILTER_FIELDS.length; i++) {
        if (ADV_FILTER_FIELDS[i].key === fieldKey) { def = ADV_FILTER_FIELDS[i]; break; }
      }
      if (!def) return;
      var c = { field: fieldKey };
      if (def.type === 'boolean') {
        var bs = rowEl.querySelector('.adv-bool-sel');
        c.boolVal = bs ? bs.value : 'any';
      } else if (def.type === 'daterange') {
        c.dateFrom = (rowEl.querySelector('.adv-date-from') || {}).value || '';
        c.dateTo   = (rowEl.querySelector('.adv-date-to')   || {}).value || '';
      } else {
        c.op    = (rowEl.querySelector('.adv-op-sel')    || {}).value || '';
        c.value = (rowEl.querySelector('.adv-val-input') || {}).value || '';
      }
      conditions.push(c);
    });
    return conditions;
  }

  function applyAdvFilter() {
    var conditions = readConditions();
    var logic = (document.getElementById('adv-filter-logic') || {}).value || 'and';
    var statusEl = document.getElementById('adv-filter-status');
    var searchEl = document.getElementById('player-search');
    var search = searchEl ? searchEl.value.trim().toLowerCase() : '';
    var total = 0, visible = 0;
    document.querySelectorAll('#players-table tbody tr').forEach(function (row) {
      total++;
      var show = conditions.length === 0 ? true
        : logic === 'and'
          ? conditions.every(function (c) { return rowMatchesCondition(row, c); })
          : conditions.some(function  (c) { return rowMatchesCondition(row, c); });
      if (show && search) show = (row.dataset.search || '').indexOf(search) !== -1;
      row.style.display = show ? '' : 'none';
      if (show) visible++;
    });
    if (statusEl) statusEl.textContent = conditions.length > 0 ? 'Showing ' + visible + ' of ' + total + ' players' : '';
  }
  window.playerSearchApply = applyAdvFilter;

  function buildValueArea(def, container) {
    container.querySelectorAll('.adv-op-sel,.adv-val-input,.adv-bool-sel,.adv-date-from,.adv-date-to,.adv-date-sep').forEach(function (el) { el.remove(); });
    function mk(tag, attrs, style) {
      var el = document.createElement(tag);
      Object.keys(attrs || {}).forEach(function (k) {
        if (k === 'textContent') el.textContent = attrs[k];
        else el[k] = attrs[k];
      });
      if (style) el.style.cssText = style;
      return el;
    }
    var inputStyle = 'width:auto;padding:.2rem .4rem;font-size:.85rem;';
    if (def.type === 'boolean') {
      var sel = mk('select', { className: 'adv-bool-sel sel-inline' });
      var trueLabel  = (def.boolLabels && def.boolLabels[0]) || window.I18N.bool_yes;
      var falseLabel = (def.boolLabels && def.boolLabels[1]) || window.I18N.bool_no;
      [['any', window.I18N.bool_any],['true', trueLabel],['false', falseLabel]].forEach(function (o) {
        sel.appendChild(mk('option', { value: o[0], textContent: o[1] }));
      });
      sel.addEventListener('change', applyAdvFilter);
      container.appendChild(sel);
      return;
    }
    if (def.type === 'daterange') {
      var fromIn = mk('input', { type: 'date', className: 'adv-date-from' }, inputStyle);
      var sep    = mk('span',  { className: 'adv-date-sep', textContent: '\u2192' }, 'margin:0 .3rem;');
      var toIn   = mk('input', { type: 'date', className: 'adv-date-to'   }, inputStyle);
      fromIn.addEventListener('input', applyAdvFilter);
      toIn.addEventListener('input',   applyAdvFilter);
      container.appendChild(fromIn); container.appendChild(sep); container.appendChild(toIn);
      return;
    }
    var ops = def.type === 'number' ? ADV_NUM_OPS : ADV_TEXT_OPS;
    var opSel = mk('select', { className: 'adv-op-sel sel-inline' });
    ops.forEach(function (o) { opSel.appendChild(mk('option', { value: o.value, textContent: o.label })); });
    var noValOps = ['is_empty', 'is_not_empty'];
    var valIn = mk('input', {
      type: def.type === 'number' ? 'number' : 'text',
      className: 'adv-val-input',
      placeholder: 'value'
    }, 'width:130px;padding:.2rem .4rem;font-size:.85rem;');
    opSel.addEventListener('change', function () {
      valIn.style.display = noValOps.indexOf(opSel.value) !== -1 ? 'none' : '';
      applyAdvFilter();
    });
    valIn.addEventListener('input', applyAdvFilter);
    container.appendChild(opSel);
    container.appendChild(valIn);
  }

  function addFilterRow(container) {
    var rowEl = document.createElement('div');
    rowEl.className = 'adv-filter-row';
    var fieldSel = document.createElement('select');
    fieldSel.className = 'adv-field-sel';
    fieldSel.classList.add('sel-inline');
    ADV_FILTER_FIELDS.forEach(function (f) {
      var o = document.createElement('option');
      o.value = f.key;
      o.textContent = f.label;
      fieldSel.appendChild(o);
    });
    var valWrap = document.createElement('span');
    valWrap.className = 'adv-val-wrap';
    valWrap.style.cssText = 'display:inline-flex;align-items:center;gap:.3rem;flex-wrap:wrap;';
    function onFieldChange() {
      var def = null;
      for (var i = 0; i < ADV_FILTER_FIELDS.length; i++) {
        if (ADV_FILTER_FIELDS[i].key === fieldSel.value) { def = ADV_FILTER_FIELDS[i]; break; }
      }
      if (def) buildValueArea(def, valWrap);
      applyAdvFilter();
    }
    fieldSel.addEventListener('change', onFieldChange);
    var removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.textContent = '\u2715';
    removeBtn.title = window.I18N.remove_btn;
    removeBtn.style.cssText = 'background:none;border:none;cursor:pointer;color:var(--tp-muted,#6c757d);font-size:.9rem;padding:.1rem .3rem;line-height:1;';
    removeBtn.addEventListener('click', function () { rowEl.remove(); applyAdvFilter(); });
    rowEl.appendChild(fieldSel);
    rowEl.appendChild(valWrap);
    rowEl.appendChild(removeBtn);
    container.appendChild(rowEl);
    onFieldChange();
  }

  function clearFilterRows(container) {
    while (container.firstChild) container.removeChild(container.firstChild);
  }

  function initAdvFilter() {
    var toggleBtn = document.getElementById('adv-filter-btn');
    var panel     = document.getElementById('adv-filter-panel');
    var addBtn    = document.getElementById('adv-filter-add');
    var clearBtn  = document.getElementById('adv-filter-clear');
    var logicSel  = document.getElementById('adv-filter-logic');
    var rowsCont  = document.getElementById('adv-filter-rows');
    if (!toggleBtn || !panel) return;
    toggleBtn.addEventListener('click', function () {
      var open = panel.style.display !== 'none';
      panel.style.display = open ? 'none' : '';
      toggleBtn.textContent = open ? 'Filter \u25be' : 'Filter \u25b4';
    });
    if (addBtn)   addBtn.addEventListener('click', function () { addFilterRow(rowsCont); });
    if (clearBtn) clearBtn.addEventListener('click', function () { clearFilterRows(rowsCont); applyAdvFilter(); });
    if (logicSel) logicSel.addEventListener('change', applyAdvFilter);
    addFilterRow(rowsCont);
  }

  // ── Archive dialog ────────────────────────────────────────────────────────
  function openArchiveDialog(players) {
    var dialog = document.getElementById('archive-dialog');
    var list   = document.getElementById('archive-dialog-list');
    if (!dialog || !list) return;
    // Clear existing items safely
    while (list.firstChild) { list.removeChild(list.firstChild); }
    players.forEach(function (p) {
      var li = document.createElement('li');
      li.textContent = p.name.trim() + (p.dob ? '  (' + p.dob + ')' : '');
      list.appendChild(li);
    });
    dialog._pendingIds = players.map(function (p) { return p.id; });
    dialog.showModal();
  }

  var archiveDialog  = document.getElementById('archive-dialog');
  var archiveConfirm = document.getElementById('archive-dialog-confirm');
  var archiveCancel  = document.getElementById('archive-dialog-cancel');
  if (archiveCancel && archiveDialog) {
    archiveCancel.addEventListener('click', function () { archiveDialog.close(); });
  }
  if (archiveConfirm && archiveDialog) {
    archiveConfirm.addEventListener('click', function () {
      var ids = archiveDialog._pendingIds || [];
      archiveDialog.close();
      if (!ids.length) return;
      bulkPost('/players/bulk-archive', ids, 'archived', true);
    });
  }

  // ── Per-row delegated handlers ─────────────────────────────────────────────
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.row-archive-btn');
    if (!btn) return;
    openArchiveDialog([{
      id: parseInt(btn.dataset.id, 10),
      name: btn.dataset.name || window.I18N.player_fallback,
      dob:  btn.dataset.dob  || '',
    }]);
  });

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.row-activate-btn');
    if (!btn) return;
    bulkPost('/players/bulk-activate', [parseInt(btn.dataset.id, 10)], 'activated', true);
  });

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.row-deactivate-btn');
    if (!btn) return;
    bulkPost('/players/bulk-deactivate', [parseInt(btn.dataset.id, 10)], 'deactivated', true);
  });

  // ── Boot ───────────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    initColumnsPopover();
    initColReorder();
    initAdvFilter();
    initEditMode();
    initBulkToolbar();
    initActionDropdowns();
  });

})();

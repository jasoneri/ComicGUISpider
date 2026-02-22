(() => {
  let bridge = null;
  let modal = null;
  let activeBookKey = "";
  let pendingTimer = null;
  const episodesCache = new Map();
  const downloadedEpCache = new Set();

  const listEl = document.getElementById("episodeList");
  const titleEl = document.getElementById("episodeTitle");
  const countEl = document.getElementById("epCount");
  const btnGroup = document.getElementById("handleBtnGroup");
  const epsNumInput = document.getElementById("EpsNumInput");

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function setLoadingState(loading) {
    btnGroup.querySelectorAll("button, input").forEach(el => el.disabled = loading);
  }

  function showBtnGroup(visible) {
    btnGroup.classList.toggle("d-none", !visible);
  }

  function clearPendingTimer() {
    if (pendingTimer) {
      clearTimeout(pendingTimer);
      pendingTimer = null;
    }
  }

  function updateCount() {
    const checked = listEl.querySelectorAll('input[type="checkbox"]:checked').length;
    const total = listEl.querySelectorAll('input[type="checkbox"]').length;
    countEl.textContent = `${checked}/${total} selected`;
  }

  function renderLoading() {
    showBtnGroup(false);
    listEl.innerHTML = `
      <div class="d-flex align-items-center gap-2 py-3">
        <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
        <span>Loading episodes...</span>
      </div>`;
    updateCount();
  }

  function renderError(message) {
    showBtnGroup(false);
    listEl.innerHTML = `<div class="alert alert-danger mb-0" role="alert">${escapeHtml(message)}</div>`;
    updateCount();
  }

  function toggleAllEpisodes() {
    const checkboxes = listEl.querySelectorAll('input[type="checkbox"]');
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);
    checkboxes.forEach(cb => cb.checked = !allChecked);
    updateCount();
  }

  function selectRange(fromEnd) {
    const checkboxes = listEl.querySelectorAll('input[type="checkbox"]');
    const total = checkboxes.length;
    if (total === 0) return;
    const parsed = parseInt(epsNumInput.value, 10);
    const n = Math.max(1, Math.min(Number.isFinite(parsed) ? parsed : 1, total));
    epsNumInput.value = String(n);
    checkboxes.forEach(cb => cb.checked = false);
    const start = fromEnd ? total - n : 0;
    const end = fromEnd ? total : n;
    for (let i = start; i < end; i++) checkboxes[i].checked = true;
    updateCount();
  }

  function renderEpisodes(bookKey, episodes) {
    if (!Array.isArray(episodes) || episodes.length === 0) {
      showBtnGroup(false);
      listEl.innerHTML = '<p class="text-muted mb-0">No episodes found.</p>';
      updateCount();
      return;
    }
    let html = '<div class="episodes-grid">';
    for (let i = 0; i < episodes.length; i++) {
      const ep = episodes[i];
      const epIdx = Number(ep.idx);
      const epName = escapeHtml(ep.name || `Episode ${epIdx}`);
      const checkboxId = `ep${bookKey}-${epIdx}`;
      html += `
        <input class="btn-check" type="checkbox" id="${checkboxId}" autocomplete="off">
        <label class="btn btn-outline-primary" for="${checkboxId}">${epName}</label>`;
    }
    html += '</div>';
    listEl.innerHTML = html;
    showBtnGroup(true);
    updateCount();

    document.querySelectorAll(`label[for^="ep${bookKey}-"]`).forEach(label => {
      if (downloadedEpCache.has(label.getAttribute('for'))) {
        label.classList.add('episode-container-downloaded');
      }
    });
  }

  function ensureModal() {
    if (!modal) {
      modal = new bootstrap.Modal(document.getElementById("episodeModal"));
    }
    return modal;
  }

  // event delegation: card click → read data-* attributes
  document.addEventListener("click", (e) => {
    const card = e.target.closest(".normal-book-card[data-book-key]");
    if (!card) return;
    if (e.target.closest("a")) return;
    const bookKey = card.dataset.bookKey;
    const title = card.dataset.bookTitle || `Book ${bookKey}`;
    window.onBookClick(bookKey, title);
  });

  document.addEventListener("DOMContentLoaded", () => {
    listEl.addEventListener("change", updateCount);
    document.getElementById("toggleAllEpBtn").addEventListener("click", toggleAllEpisodes);
    document.getElementById("beginBtn").addEventListener("click", () => selectRange(false));
    document.getElementById("lastBtn").addEventListener("click", () => selectRange(true));
    if (window.qt && window.qt.webChannelTransport) {
      new QWebChannel(window.qt.webChannelTransport, (channel) => {
        bridge = channel.objects.bridge || null;
      });
    }
  });

  window.onBookClick = function (bookKey, title) {
    activeBookKey = String(bookKey);
    titleEl.textContent = title || `Book ${bookKey}`;

    if (episodesCache.has(bookKey)) {
      setLoadingState(false);
      renderEpisodes(bookKey, episodesCache.get(bookKey));
      ensureModal().show();
      return;
    }

    setLoadingState(true);
    renderLoading();
    ensureModal().show();

    clearPendingTimer();
    pendingTimer = setTimeout(() => {
      if (activeBookKey === String(bookKey)) {
        window.showEpisodeError("Episode loading timeout (8s). Please retry.");
      }
    }, 8000);

    if (!bridge || typeof bridge.fetchEpisodes !== "function") {
      window.showEpisodeError("QWebChannel bridge not ready.");
      return;
    }

    bridge.fetchEpisodes(String(bookKey));
  };

  window.updateEpisodes = function (bookKey, episodesJson) {
    if (String(bookKey) !== activeBookKey) {
      return;
    }

    clearPendingTimer();
    setLoadingState(false);

    try {
      const episodes = typeof episodesJson === "string" ? JSON.parse(episodesJson) : episodesJson;
      episodesCache.set(bookKey, episodes);
      renderEpisodes(bookKey, episodes);
    } catch (err) {
      window.showEpisodeError(`Episode parse error: ${err}`);
    }
  };

  window.showEpisodeError = function (message) {
    clearPendingTimer();
    setLoadingState(false);
    renderError(message || "Episode request failed.");
  };

  window.markDownloadedEpisodes = function (epIds) {
    epIds.forEach(id => {
      downloadedEpCache.add(id);
      const label = document.querySelector(`label[for="${id}"]`);
      if (label) label.classList.add('episode-container-downloaded');
    });
  };

  // --- Card Status Badge ---

  window.renderCardBadgeDl = function(bookKey, dlMax) {
    const row = document.getElementById(`status-row-${bookKey}`);
    if (!row) return;
    row.querySelectorAll('.badge-dl').forEach(el => el.remove());
    const span = document.createElement('span');
    span.className = 'badge bg-secondary bg-opacity-75 badge-dl status-badge-fade';
    span.textContent = `DL: ${dlMax}`;
    row.prepend(span);
  };

  window.renderCardBadgeLatest = function(bookKey, latestEpName) {
    const row = document.getElementById(`status-row-${bookKey}`);
    if (!row) return;
    row.querySelectorAll('.badge-latest').forEach(el => el.remove());
    const span = document.createElement('span');
    const dlBadge = row.querySelector('.badge-dl');
    const dlText = dlBadge ? dlBadge.textContent.replace('DL: ', '') : '';
    const hasUpdate = dlText && dlText !== latestEpName;
    span.className = hasUpdate
        ? 'badge bg-danger badge-latest status-badge-fade'
        : 'badge bg-success badge-latest status-badge-fade';
    span.textContent = hasUpdate ? `NEW: ${latestEpName}` : `Latest \u2713`;
    row.appendChild(span);
  };

  // --- Scan Toast ---

  let _scanToastInstance = null;

  window.showScanNotification = function(message) {
    const el = document.getElementById('scanToast');
    if (!el) return;
    document.getElementById('scanToastBody').textContent = message;
    if (!_scanToastInstance) _scanToastInstance = new bootstrap.Toast(el, { autohide: false });
    _scanToastInstance.show();
  };

  window.hideScanNotification = function() {
    if (_scanToastInstance) _scanToastInstance.hide();
  };
})();

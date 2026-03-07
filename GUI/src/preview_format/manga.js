(() => {
  class MangaPreviewApp {
    constructor() {
      this.bridge = null;
      this.modal = null;
      this.activeBookKey = "";
      this.pendingTimer = null;
      this.scanToastInstance = null;
      this.episodesCache = new Map();
      this.downloadedEpCache = new Set();

      this.listEl = document.getElementById("episodeList");
      this.titleEl = document.getElementById("episodeTitle");
      this.countEl = document.getElementById("epCount");
      this.btnGroup = document.getElementById("handleBtnGroup");
      this.epsNumInput = document.getElementById("EpsNumInput");
    }

    init() {
      this.exposeWindowApi();
      this.bindDocumentEvents();
      document.addEventListener("DOMContentLoaded", () => this.onDomReady());
    }

    exposeWindowApi() {
      window.onBookClick = (bookKey, title) => this.onBookClick(bookKey, title);
      window.updateEpisodes = (bookKey, episodesJson) => this.updateEpisodes(bookKey, episodesJson);
      window.showEpisodeError = (message) => this.showEpisodeError(message);
      window.showEpisodeFetchError = (bookKey, code) => this.showEpisodeFetchError(bookKey, code);
      window.markDownloadedEpisodes = (epIds) => this.markDownloadedEpisodes(epIds);
      window.renderCardBadgeDl = (bookKey, dlMax) => this.renderCardBadgeDl(bookKey, dlMax);
      window.renderCardBadgeLatest = (bookKey, latestEpName) => this.renderCardBadgeLatest(bookKey, latestEpName);
      window.showScanNotification = (message) => this.showScanNotification(message);
      window.hideScanNotification = () => this.hideScanNotification();
      window.updateFavoriteState = (key, isFavorited) => this.updateFavoriteState(key, isFavorited);
      window.initFavoriteStates = (keys) => this.initFavoriteStates(keys);
    }

    bindDocumentEvents() {
      document.addEventListener("click", (event) => this.onCardClick(event));
      document.addEventListener("click", (event) => this.onFavoriteClick(event), true);
      document.addEventListener("keydown", (event) => this.onFavoriteKeydown(event), true);
    }

    onDomReady() {
      this.initBridge();
      this.listEl.addEventListener("change", () => this.updateCount());
      document.getElementById("toggleAllEpBtn").addEventListener("click", () => this.toggleAllEpisodes());
      document.getElementById("beginBtn").addEventListener("click", () => this.selectRange(false));
      document.getElementById("lastBtn").addEventListener("click", () => this.selectRange(true));
      const clearEpBtn = document.getElementById("clearEpBtn");
      if (clearEpBtn) {
        clearEpBtn.addEventListener("click", () => this.clearEpisodes());
      }
      this.initDragSelect();
    }

    initBridge() {
      if (window.qt && window.qt.webChannelTransport) {
        new QWebChannel(window.qt.webChannelTransport, (channel) => {
          this.bridge = channel.objects.bridge || null;
        });
      }
    }

    onCardClick(event) {
      const card = event.target.closest(".normal-book-card[data-book-key]");
      if (!card || event.target.closest("a")) {
        return;
      }
      const bookKey = card.dataset.bookKey;
      const title = card.dataset.bookTitle || `Book ${bookKey}`;
      this.onBookClick(bookKey, title);
    }

    onFavoriteClick(event) {
      if (!event.target || !event.target.matches(".card-favorite-btn")) {
        return;
      }
      event.stopPropagation();
      event.preventDefault();
      const key = event.target.dataset.bookKey;
      if (this.bridge && typeof this.bridge.toggleFavorite === "function") {
        this.bridge.toggleFavorite(String(key));
      }
    }

    onFavoriteKeydown(event) {
      if (!event.target || !event.target.matches(".card-favorite-btn")) {
        return;
      }
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        event.target.click();
      }
    }

    escapeHtml(text) {
      return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    getEpisodeCheckboxes() {
      return this.listEl.querySelectorAll('input[type="checkbox"]');
    }

    setLoadingState(loading) {
      this.btnGroup.querySelectorAll("button, input").forEach((element) => {
        element.disabled = loading;
      });
    }

    showBtnGroup(visible) {
      this.btnGroup.classList.toggle("d-none", !visible);
    }

    clearPendingTimer() {
      if (this.pendingTimer) {
        clearTimeout(this.pendingTimer);
        this.pendingTimer = null;
      }
    }

    updateCount() {
      const checkboxes = this.getEpisodeCheckboxes();
      const checked = Array.from(checkboxes).filter((checkbox) => checkbox.checked).length;
      this.countEl.textContent = `${checked}/${checkboxes.length} selected`;
    }

    renderLoading() {
      this.showBtnGroup(false);
      this.listEl.innerHTML = `
      <div class="d-flex align-items-center gap-2 py-3">
        <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
        <span>Loading episodes...</span>
      </div>`;
      this.updateCount();
    }

    renderError(message) {
      this.showBtnGroup(false);
      this.listEl.innerHTML = `<div class="alert alert-danger mb-0" role="alert">${this.escapeHtml(message)}</div>`;
      this.updateCount();
    }

    buildEpisodeErrorMessage(code) {
      const retryHint = "请关闭弹窗后再次点击卡片重试。";
      switch (code) {
        case "timeout":
          return `章节加载超时（8 秒）。${retryHint}`;
        case "bridge_not_ready":
          return `预览通道尚未就绪。${retryHint}`;
        case "parse_error":
          return `章节数据解析失败。${retryHint}`;
        case "fetch_failed":
        default:
          return `章节加载失败。${retryHint}`;
      }
    }

    toggleAllEpisodes() {
      const checkboxes = this.getEpisodeCheckboxes();
      const allChecked = Array.from(checkboxes).every((checkbox) => checkbox.checked);
      checkboxes.forEach((checkbox) => {
        checkbox.checked = !allChecked;
      });
      this.updateCount();
    }

    selectRange(fromEnd) {
      const checkboxes = this.getEpisodeCheckboxes();
      const total = checkboxes.length;
      if (total === 0) {
        return;
      }
      const parsed = parseInt(this.epsNumInput.value, 10);
      const count = Math.max(1, Math.min(Number.isFinite(parsed) ? parsed : 1, total));
      this.epsNumInput.value = String(count);
      checkboxes.forEach((checkbox) => {
        checkbox.checked = false;
      });
      const start = fromEnd ? total - count : 0;
      const end = fromEnd ? total : count;
      for (let index = start; index < end; index += 1) {
        checkboxes[index].checked = true;
      }
      this.updateCount();
    }

    clearEpisodes() {
      this.listEl.querySelectorAll('input.btn-check[type="checkbox"]').forEach((checkbox) => {
        if (checkbox.checked) {
          checkbox.checked = false;
        }
      });
      this.updateCount();
    }

    initDragSelect() {
      let dragging = false;
      let wasDragging = false;
      let startX = 0;
      let startY = 0;

      const style = document.createElement("style");
      style.textContent = `
      #dragSelOverlay { position:fixed; pointer-events:none; z-index:9999; display:none;
        box-sizing:border-box; border:2px dashed #0d6efd; background:rgba(13,110,253,0.08); }
      body.drag-selecting *, body.drag-selecting {
        user-select:none !important; -webkit-user-select:none !important; cursor:crosshair !important; }
    `;
      document.head.appendChild(style);

      const overlay = document.createElement("div");
      overlay.id = "dragSelOverlay";
      document.body.appendChild(overlay);

      const updateOverlay = (x1, y1, x2, y2) => {
        overlay.style.left = `${Math.min(x1, x2)}px`;
        overlay.style.top = `${Math.min(y1, y2)}px`;
        overlay.style.width = `${Math.abs(x2 - x1)}px`;
        overlay.style.height = `${Math.abs(y2 - y1)}px`;
      };

      const intersects = (a, b) => {
        return !(a.right < b.left || a.left > b.right || a.bottom < b.top || a.top > b.bottom);
      };

      document.addEventListener(
        "click",
        (event) => {
          if (!wasDragging) {
            return;
          }
          wasDragging = false;
          event.preventDefault();
          event.stopPropagation();
        },
        true
      );

      document.addEventListener("mousedown", (event) => {
        if (event.button !== 0 || event.target.closest("input, a, button, select, textarea")) {
          return;
        }
        if (!this.listEl.contains(event.target)) {
          return;
        }
        startX = event.clientX;
        startY = event.clientY;
        dragging = false;
        wasDragging = false;
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp, { once: true });
      });

      const onMove = (event) => {
        const deltaX = event.clientX - startX;
        const deltaY = event.clientY - startY;
        if (!dragging && (Math.abs(deltaX) > 5 || Math.abs(deltaY) > 5)) {
          dragging = true;
          document.body.classList.add("drag-selecting");
          overlay.style.display = "block";
        }
        if (!dragging) {
          return;
        }
        updateOverlay(startX, startY, event.clientX, event.clientY);
      };

      const onUp = (event) => {
        document.removeEventListener("mousemove", onMove);
        document.body.classList.remove("drag-selecting");
        overlay.style.display = "none";
        if (!dragging) {
          return;
        }
        dragging = false;
        wasDragging = true;

        const selectRect = {
          left: Math.min(startX, event.clientX),
          top: Math.min(startY, event.clientY),
          right: Math.max(startX, event.clientX),
          bottom: Math.max(startY, event.clientY),
        };
        if (selectRect.right - selectRect.left < 5 && selectRect.bottom - selectRect.top < 5) {
          return;
        }

        this.listEl.querySelectorAll("label.btn").forEach((label) => {
          const rect = label.getBoundingClientRect();
          if (!intersects(selectRect, rect)) {
            return;
          }
          const checkbox = document.getElementById(label.htmlFor);
          if (checkbox && checkbox.classList.contains("btn-check") && !checkbox.checked) {
            checkbox.checked = true;
          }
        });
        this.updateCount();
      };
    }

    renderEpisodes(bookKey, episodes) {
      if (!Array.isArray(episodes) || episodes.length === 0) {
        this.showBtnGroup(false);
        this.listEl.innerHTML = '<p class="text-muted mb-0">No episodes found.</p>';
        this.updateCount();
        return;
      }

      let html = '<div class="episodes-grid">';
      for (let index = 0; index < episodes.length; index += 1) {
        const episode = episodes[index];
        const episodeIndex = Number(episode.idx);
        const episodeName = this.escapeHtml(episode.name || `Episode ${episodeIndex}`);
        const checkboxId = `ep${bookKey}-${episodeIndex}`;
        html += `
        <input class="btn-check" type="checkbox" id="${checkboxId}" autocomplete="off">
        <label class="btn btn-outline-primary" for="${checkboxId}">${episodeName}</label>`;
      }
      html += "</div>";
      this.listEl.innerHTML = html;
      this.showBtnGroup(true);
      this.updateCount();

      document.querySelectorAll(`label[for^="ep${bookKey}-"]`).forEach((label) => {
        if (this.downloadedEpCache.has(label.getAttribute("for"))) {
          label.classList.add("episode-container-downloaded");
        }
      });
    }

    ensureModal() {
      if (!this.modal) {
        this.modal = new bootstrap.Modal(document.getElementById("episodeModal"));
      }
      return this.modal;
    }

    onBookClick(bookKey, title) {
      this.activeBookKey = String(bookKey);
      this.titleEl.textContent = title || `Book ${bookKey}`;

      if (this.episodesCache.has(bookKey)) {
        this.setLoadingState(false);
        this.renderEpisodes(bookKey, this.episodesCache.get(bookKey));
        this.ensureModal().show();
        return;
      }

      this.setLoadingState(true);
      this.renderLoading();
      this.ensureModal().show();

      this.clearPendingTimer();
      this.pendingTimer = setTimeout(() => {
        if (this.activeBookKey === String(bookKey)) {
          this.showEpisodeError(this.buildEpisodeErrorMessage("timeout"));
        }
      }, 8000);

      if (!this.bridge || typeof this.bridge.fetchEpisodes !== "function") {
        this.showEpisodeError(this.buildEpisodeErrorMessage("bridge_not_ready"));
        return;
      }

      this.bridge.fetchEpisodes(String(bookKey));
    }

    updateEpisodes(bookKey, episodesJson) {
      if (String(bookKey) !== this.activeBookKey) {
        return;
      }

      this.clearPendingTimer();
      this.setLoadingState(false);

      try {
        const episodes = typeof episodesJson === "string" ? JSON.parse(episodesJson) : episodesJson;
        this.episodesCache.set(bookKey, episodes);
        this.renderEpisodes(bookKey, episodes);
      } catch (error) {
        this.showEpisodeError(this.buildEpisodeErrorMessage("parse_error"));
      }
    }

    showEpisodeError(message) {
      this.clearPendingTimer();
      this.setLoadingState(false);
      this.renderError(message || this.buildEpisodeErrorMessage("fetch_failed"));
    }

    showEpisodeFetchError(bookKey, code = "fetch_failed") {
      if (String(bookKey) !== this.activeBookKey) {
        return;
      }
      this.showEpisodeError(this.buildEpisodeErrorMessage(code));
    }

    markDownloadedEpisodes(epIds) {
      epIds.forEach((id) => {
        this.downloadedEpCache.add(id);
        const label = document.querySelector(`label[for="${id}"]`);
        if (label) {
          label.classList.add("episode-container-downloaded");
        }
      });
    }

    renderCardBadgeDl(bookKey, dlMax) {
      const row = document.getElementById(`status-row-${bookKey}`);
      if (!row) {
        return;
      }
      row.querySelectorAll(".badge-dl").forEach((element) => element.remove());
      const span = document.createElement("span");
      span.className = "badge bg-secondary bg-opacity-75 badge-dl status-badge-fade";
      span.textContent = `DL: ${dlMax}`;
      row.prepend(span);
    }

    renderCardBadgeLatest(bookKey, latestEpName) {
      const row = document.getElementById(`status-row-${bookKey}`);
      if (!row) {
        return;
      }
      row.querySelectorAll(".badge-latest").forEach((element) => element.remove());
      const span = document.createElement("span");
      const dlBadge = row.querySelector(".badge-dl");
      const dlText = dlBadge ? dlBadge.textContent.replace("DL: ", "") : "";
      const hasUpdate = dlText && dlText !== latestEpName;
      span.className = hasUpdate
        ? "badge bg-danger badge-latest status-badge-fade"
        : "badge bg-success badge-latest status-badge-fade";
      span.textContent = hasUpdate ? `NEW: ${latestEpName}` : "Latest \u2713";
      row.appendChild(span);
    }

    showScanNotification(message) {
      const toast = document.getElementById("scanToast");
      if (!toast) {
        return;
      }
      document.getElementById("scanToastBody").textContent = message;
      if (!this.scanToastInstance) {
        this.scanToastInstance = new bootstrap.Toast(toast, { autohide: false });
      }
      this.scanToastInstance.show();
    }

    hideScanNotification() {
      if (this.scanToastInstance) {
        this.scanToastInstance.hide();
      }
    }

    updateFavoriteState(key, isFavorited) {
      const button = document.querySelector(`.card-favorite-btn[data-book-key="${key}"]`);
      if (!button) {
        return;
      }
      button.textContent = isFavorited ? "★" : "☆";
      button.classList.toggle("is-favorited", isFavorited);
      button.setAttribute("aria-pressed", isFavorited);
    }

    initFavoriteStates(keys) {
      document.querySelectorAll(".card-favorite-btn").forEach((button) => {
        this.updateFavoriteState(button.dataset.bookKey, false);
      });
      if (Array.isArray(keys)) {
        keys.forEach((key) => this.updateFavoriteState(key, true));
      }
    }
  }

  new MangaPreviewApp().init();
})();

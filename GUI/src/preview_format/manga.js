(() => {
  class MangaPreviewApp {
    constructor() {
      this.bridge = null;
      this.bridgeInitPromise = null;
      this.qwebchannelPromise = null;
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
      this.scrollBottomBtn = document.getElementById("scrollBottomBtn");
      this.filterInput = document.getElementById("episodeFilterInput");
      this.modalEl = document.getElementById("episodeModal");
      this.modalBodyEl = this.modalEl ? this.modalEl.querySelector(".modal-body") : null;
    }

    init() {
      this.exposeWindowApi();
      this.bindDocumentEvents();
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => this.onDomReady(), { once: true });
        return;
      }
      this.onDomReady();
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
      void this.initBridge();
      this.listEl.addEventListener("change", () => this.updateCount());
      if (this.filterInput) {
        this.filterInput.addEventListener("input", () => this.applyEpisodeFilter());
      }
      document.getElementById("toggleAllEpBtn").addEventListener("click", () => this.toggleAllEpisodes());
      document.getElementById("beginBtn").addEventListener("click", () => this.selectRange(false));
      document.getElementById("lastBtn").addEventListener("click", () => {
        this.selectRange(true);
        this.scrollEpisodesToBottom();
      });
      const clearEpBtn = document.getElementById("clearEpBtn");
      if (clearEpBtn) {
        clearEpBtn.addEventListener("click", () => this.clearEpisodes());
      }
      if (this.scrollBottomBtn) {
        this.scrollBottomBtn.addEventListener("click", () => this.scrollEpisodesToBottom());
      }
      this.ensureModal();
      this.ensureScanToast();
      this.initDragSelect();
    }

    isQtBridgeAvailable() {
      return Boolean(window.qt && window.qt.webChannelTransport);
    }

    isStandalonePreviewMode() {
      return !this.isQtBridgeAvailable();
    }

    async ensureQWebChannel() {
      if (!this.isQtBridgeAvailable()) {
        return false;
      }
      if (typeof window.QWebChannel === "function") {
        return true;
      }
      if (!this.qwebchannelPromise) {
        this.qwebchannelPromise = new Promise((resolve) => {
          const script = document.createElement("script");
          script.src = "qrc:///qtwebchannel/qwebchannel.js";
          script.onload = () => resolve(typeof window.QWebChannel === "function");
          script.onerror = () => resolve(false);
          document.head.appendChild(script);
        });
      }
      return this.qwebchannelPromise;
    }

    async initBridge() {
      if (this.bridge) {
        return this.bridge;
      }
      if (!this.isQtBridgeAvailable()) {
        return null;
      }
      if (!this.bridgeInitPromise) {
        this.bridgeInitPromise = (async () => {
          const loaded = await this.ensureQWebChannel();
          if (!loaded || typeof window.QWebChannel !== "function") {
            return null;
          }
          return new Promise((resolve) => {
            new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
              this.bridge = channel.objects.bridge || null;
              resolve(this.bridge);
            });
          });
        })();
      }
      return this.bridgeInitPromise;
    }

    async waitForBridge() {
      const bridge = await this.initBridge();
      if (bridge && typeof bridge.fetchEpisodes === "function") {
        return bridge;
      }
      for (let attempts = 0; attempts < 20; attempts += 1) {
        if (this.bridge && typeof this.bridge.fetchEpisodes === "function") {
          return this.bridge;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 50));
      }
      return null;
    }

    ensureModal() {
      if (this.modal) {
        return this.modal;
      }
      if (!this.modalEl) {
        return null;
      }

      if (!(window.bootstrap && typeof window.bootstrap.Modal === "function")) {
        return null;
      }

      const modal = new window.bootstrap.Modal(this.modalEl);
      this.modal = {
        show: () => modal.show(),
        hide: () => modal.hide(),
        isOpen: () => this.modalEl.classList.contains("show"),
      };
      return this.modal;
    }

    ensureScanToast() {
      if (this.scanToastInstance) {
        return this.scanToastInstance;
      }
      const toast = document.getElementById("scanToast");
      if (!toast) {
        return null;
      }

      if (window.bootstrap && typeof window.bootstrap.Toast === "function") {
        const instance = new window.bootstrap.Toast(toast, { autohide: false });
        this.scanToastInstance = {
          show: () => {
            toast.hidden = false;
            instance.show();
          },
          hide: () => {
            instance.hide();
            toast.hidden = true;
          },
        };
        return this.scanToastInstance;
      }

      this.scanToastInstance = {
        show: () => {
          toast.hidden = false;
          window.requestAnimationFrame(() => toast.classList.add("show"));
        },
        hide: () => {
          toast.classList.remove("show");
          toast.hidden = true;
        },
      };
      return this.scanToastInstance;
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

    getFavoriteButton(target) {
      return target instanceof Element ? target.closest(".card-favorite-btn[data-book-key]") : null;
    }

    async toggleFavorite(button) {
      if (!button) {
        return;
      }
      const key = button.dataset.bookKey;
      const bridge = this.bridge || await this.waitForBridge();
      if (bridge && typeof bridge.toggleFavorite === "function") {
        bridge.toggleFavorite(String(key));
      }
    }

    async onFavoriteClick(event) {
      const button = this.getFavoriteButton(event.target);
      if (!button) {
        return;
      }
      event.stopPropagation();
      event.preventDefault();
      await this.toggleFavorite(button);
    }

    onFavoriteKeydown(event) {
      const button = this.getFavoriteButton(event.target);
      if (!button) {
        return;
      }
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        button.click();
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
      if (this.btnGroup) {
        this.btnGroup.querySelectorAll("button, input").forEach((element) => {
          element.disabled = loading;
        });
      }
      if (this.filterInput) {
        this.filterInput.disabled = loading;
      }
    }

    showBtnGroup(visible) {
      if (this.btnGroup) {
        this.btnGroup.classList.toggle("d-none", !visible);
      }
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

    scrollEpisodesToBottom() {
      const scrollContainer = this.modalBodyEl || (this.listEl ? this.listEl.closest(".modal-body") : null);
      if (!scrollContainer) {
        return;
      }
      scrollContainer.scrollTo({
        top: scrollContainer.scrollHeight,
        behavior: "smooth",
      });
    }

    renderLoading() {
      this.showBtnGroup(false);
      if (this.filterInput) {
        this.filterInput.value = "";
        this.filterInput.disabled = true;
      }
      this.listEl.innerHTML = `
      <div class="d-flex align-items-center gap-2 py-3">
        <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
        <span>Loading episodes...</span>
      </div>`;
      this.updateCount();
    }

    renderError(message) {
      this.showBtnGroup(false);
      if (this.filterInput) {
        this.filterInput.value = "";
        this.filterInput.disabled = true;
      }
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

    applyEpisodeFilter() {
      if (!this.filterInput) {
        return;
      }
      const keyword = this.filterInput.value.trim().toLowerCase();
      const items = this.listEl.querySelectorAll("[data-episode-item]");
      let visibleCount = 0;

      items.forEach((item) => {
        const matched = !keyword || (item.dataset.episodeText || "").includes(keyword);
        item.hidden = !matched;
        if (matched) {
          visibleCount += 1;
        }
      });

      const emptyState = this.listEl.querySelector("#episodeEmptyState");
      if (emptyState) {
        emptyState.hidden = visibleCount !== 0;
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
      this.listEl.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
        checkbox.checked = false;
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
      #dragSelOverlay {
        position: fixed;
        pointer-events: none;
        z-index: 9999;
        display: none;
        box-sizing: border-box;
        border: 2px dashed var(--bs-primary);
        border-radius: 18px;
        background: rgba(var(--bs-primary-rgb), 0.12);
      }
      body.drag-selecting,
      body.drag-selecting * {
        user-select: none !important;
        -webkit-user-select: none !important;
        cursor: crosshair !important;
      }`;
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

        this.listEl.querySelectorAll("label[data-episode-chip]").forEach((label) => {
          const rect = label.getBoundingClientRect();
          if (!intersects(selectRect, rect)) {
            return;
          }
          const checkbox = document.getElementById(label.htmlFor);
          if (checkbox && !checkbox.checked) {
            checkbox.checked = true;
          }
        });
        this.updateCount();
      };
    }

    renderEpisodes(bookKey, episodes) {
      if (!Array.isArray(episodes) || episodes.length === 0) {
        this.showBtnGroup(false);
        if (this.filterInput) {
          this.filterInput.value = "";
          this.filterInput.disabled = true;
        }
        this.listEl.innerHTML = '<p class="text-muted mb-0">No episodes found.</p>';
        this.updateCount();
        return;
      }

      if (this.filterInput) {
        this.filterInput.value = "";
        this.filterInput.disabled = false;
      }

      let html = '<div class="episodes-grid">';

      for (let index = 0; index < episodes.length; index += 1) {
        const episode = episodes[index];
        const episodeIndex = Number.isFinite(Number(episode.idx)) ? Number(episode.idx) : index + 1;
        const rawName = String(episode.name || `Episode ${episodeIndex}`);
        const episodeName = this.escapeHtml(rawName);
        const checkboxId = `ep${bookKey}-${episodeIndex}`;
        const searchText = this.escapeHtml(`${episodeIndex} ${rawName}`.toLowerCase());
        html += `
        <div class="episode-item-wrap" data-episode-item data-episode-text="${searchText}">
          <input class="episode-item-input" type="checkbox" id="${checkboxId}" autocomplete="off">
          <label data-episode-chip class="episode-item" for="${checkboxId}" title="${episodeName}">
            <span class="episode-item-text">
              <span class="episode-item-index">${episodeIndex}</span>${episodeName}
            </span>
          </label>
        </div>`;
      }

      html += "</div>";

      this.listEl.innerHTML = html;
      this.showBtnGroup(true);
      this.updateCount();

      this.listEl.querySelectorAll(`label[for^="ep${bookKey}-"]`).forEach((label) => {
        if (this.downloadedEpCache.has(label.getAttribute("for"))) {
          label.classList.add("episode-container-downloaded");
        }
      });
    }

    getStandaloneEpisodes(bookKey, title) {
      if (!this.isStandalonePreviewMode()) {
        return null;
      }
      const dataset = window.__MANGA_PREVIEW_BROWSER_DATA__;
      if (dataset && Array.isArray(dataset[String(bookKey)])) {
        return dataset[String(bookKey)];
      }
      return this.generateStandaloneEpisodes(bookKey, title);
    }

    generateStandaloneEpisodes(bookKey, title) {
      const seedText = `${bookKey}:${title || ""}`;
      const seed = Array.from(seedText).reduce((sum, char) => sum + char.charCodeAt(0), 0);
      const total = 42 + (seed % 84);
      const topics = [
        "序章", "相遇", "分歧", "夜色试炼", "推进线", "高压对峙", "回收节点", "隐藏支线", "后日谈", "特别篇",
      ];
      return Array.from({ length: total }, (_, index) => {
        const idx = index + 1;
        const topic = topics[(seed + index) % topics.length];
        const arc = Math.floor(index / topics.length) + 1;
        const suffix = arc > 1 ? ` / 篇章 ${arc}` : "";
        return {
          idx,
          name: `第${idx}话 ${topic}${suffix}`,
        };
      });
    }

    async onBookClick(bookKey, title) {
      const cacheKey = String(bookKey);
      const modal = this.ensureModal();
      if (!modal) {
        return;
      }
      this.activeBookKey = cacheKey;
      this.titleEl.textContent = title || `Book ${bookKey}`;

      if (this.episodesCache.has(cacheKey)) {
        this.setLoadingState(false);
        this.renderEpisodes(cacheKey, this.episodesCache.get(cacheKey));
        modal.show();
        return;
      }

      const standaloneEpisodes = this.getStandaloneEpisodes(cacheKey, title);
      if (standaloneEpisodes) {
        this.episodesCache.set(cacheKey, standaloneEpisodes);
        this.setLoadingState(false);
        this.renderEpisodes(cacheKey, standaloneEpisodes);
        modal.show();
        return;
      }

      this.setLoadingState(true);
      this.renderLoading();
      modal.show();

      this.clearPendingTimer();
      this.pendingTimer = setTimeout(() => {
        if (this.activeBookKey === cacheKey) {
          this.showEpisodeError(this.buildEpisodeErrorMessage("timeout"));
        }
      }, 8000);

      const bridge = await this.waitForBridge();
      if (cacheKey !== this.activeBookKey) {
        return;
      }

      if (!bridge || typeof bridge.fetchEpisodes !== "function") {
        this.showEpisodeError(this.buildEpisodeErrorMessage("bridge_not_ready"));
        return;
      }

      bridge.fetchEpisodes(cacheKey);
    }

    updateEpisodes(bookKey, episodesJson) {
      const cacheKey = String(bookKey);
      if (cacheKey !== this.activeBookKey) {
        return;
      }

      this.clearPendingTimer();
      this.setLoadingState(false);

      try {
        const episodes = typeof episodesJson === "string" ? JSON.parse(episodesJson) : episodesJson;
        this.episodesCache.set(cacheKey, episodes);
        this.renderEpisodes(cacheKey, episodes);
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
      span.className = "book-card-badge book-card-badge-muted badge-dl status-badge-fade";
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
        ? "book-card-badge book-card-badge-danger badge-latest status-badge-fade"
        : "book-card-badge book-card-badge-success badge-latest status-badge-fade";
      span.textContent = hasUpdate ? `NEW: ${latestEpName}` : "Latest \u2713";
      row.appendChild(span);
    }

    showScanNotification(message) {
      const toast = this.ensureScanToast();
      if (!toast) {
        return;
      }
      document.getElementById("scanToastBody").textContent = message;
      toast.show();
    }

    hideScanNotification() {
      const toast = this.ensureScanToast();
      if (toast) {
        toast.hide();
      }
    }

    updateFavoriteState(key, isFavorited) {
      const button = document.querySelector(`.card-favorite-btn[data-book-key="${key}"]`);
      if (!button) {
        return;
      }
      const input = button.querySelector(".card-favorite-input");
      if (input) {
        input.checked = isFavorited;
      }
      button.classList.toggle("is-favorited", isFavorited);
      button.setAttribute("aria-pressed", String(isFavorited));
    }

    initFavoriteStates(keys) {
      const buttons = Array.from(document.querySelectorAll(".card-favorite-btn"));
      buttons.forEach((button) => {
        button.classList.add("is-syncing");
        this.updateFavoriteState(button.dataset.bookKey, false);
      });
      if (Array.isArray(keys)) {
        keys.forEach((key) => this.updateFavoriteState(key, true));
      }
      window.requestAnimationFrame(() => {
        buttons.forEach((button) => button.classList.remove("is-syncing"));
      });
    }
  }

  new MangaPreviewApp().init();
})();

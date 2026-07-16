(() => {
  const previewUi = window.previewUi;
  if (!previewUi) {
    throw new Error('previewUi is not ready');
  }
  const previewCommandBus = window.previewCommandBus;
  if (!previewCommandBus) {
    throw new Error('previewCommandBus is not ready');
  }

  const {
    escapeHtml,
    createDialogController,
    createToastController,
    createQtBridgeClient,
  } = previewUi;

  function requireElement(id) {
    const element = document.getElementById(id);
    if (!(element instanceof HTMLElement)) {
      throw new Error(`preview template is missing required element: #${id}`);
    }
    return element;
  }

  class EpisodePreviewBase {
    constructor() {
      this.bridgeClient = createQtBridgeClient();
      this.modal = null;
      this.activeBookKey = '';
      this.pendingTimer = null;
      this.scanToastInstance = null;
      this.episodesCache = new Map();
      this.bookMetaCache = new Map();

      this.listEl = requireElement('episodeList');
      this.titleEl = requireElement('episodeTitle');
      this.countEl = requireElement('epCount');
      this.btnGroup = requireElement('handleBtnGroup');
      this.epsNumInput = requireElement('EpsNumInput');
      this.scrollBottomBtn = document.getElementById('scrollBottomBtn');
      this.filterInput = document.getElementById('episodeFilterInput');
      this.modalEl = requireElement('episodeModal');
      this.bookMetaEl = requireElement('episodeBookMeta');
      this.bulkBarEl = requireElement('episodeBulkSelectBar');
      this.modalBodyEl = this.modalEl.querySelector('.preview-dialog__body');
      if (!(this.modalBodyEl instanceof HTMLElement)) {
        throw new Error('preview template is missing .preview-dialog__body');
      }
    }

    registerCommandHandlers() {
      previewCommandBus.register('manga.episodes.loaded', ({ bookKey, episodes, bookMeta }) => {
        this.updateEpisodes(bookKey, episodes, bookMeta);
      });
      previewCommandBus.register('preview.books.downloaded', ({ bookIds }) => {
        if (window.previewRuntime) {
          window.previewRuntime.markDownloaded(bookIds, []);
        }
      });
      previewCommandBus.register('manga.episodes.error', ({ bookKey, code, message }) => {
        this.showEpisodeFetchError(bookKey, code, message);
      });
      previewCommandBus.register('preview.scan.show', ({ message }) => {
        this.showScanNotification(message);
      });
      previewCommandBus.register('preview.scan.hide', () => {
        this.hideScanNotification();
      });
      previewCommandBus.register('manga.badge.dl', ({ bookKey, dlMax }) => {
        this.renderCardBadgeDl(bookKey, dlMax);
      });
      previewCommandBus.register('manga.badge.latest', ({ bookKey, latestEpName }) => {
        this.renderCardBadgeLatest(bookKey, latestEpName);
      });
      previewCommandBus.register('manga.dl_scan.result', ({ badges }) => {
        this.applyDlScanResult(badges);
      });
    }

    bindBaseDocumentEvents() {
      document.addEventListener('click', (event) => this.onCardClick(event));
    }

    onDomReadyBase() {
      void this.bridgeClient.init();
      this.bindEpisodeListEvents();
      if (this.filterInput) {
        this.filterInput.addEventListener('input', () => this.applyEpisodeFilter());
      }
      requireElement('toggleAllEpBtn').addEventListener('click', () => this.toggleAllEpisodes());
      requireElement('beginBtn').addEventListener('click', () => this.selectRange(false));
      requireElement('lastBtn').addEventListener('click', () => {
        this.selectRange(true);
        this.scrollEpisodesToBottom();
      });
      requireElement('clearEpBtn').addEventListener('click', () => this.clearEpisodes());
      if (this.scrollBottomBtn instanceof HTMLElement) {
        this.scrollBottomBtn.addEventListener('click', () => this.scrollEpisodesToBottom());
      }
      this.ensureModal();
      this.modalEl.addEventListener('preview-dialog:show', () => { this.bulkBarEl.hidden = false; });
      this.modalEl.addEventListener('preview-dialog:hide', () => { this.bulkBarEl.hidden = true; });
      this.ensureScanToast();
      this.initEpisodeDragSelect();
      window.collectPreviewSubmitPayload = () => this.collectSubmitPayload();
      window.updateEpisodes = (bookKey, episodes) => this.preloadEpisodes(bookKey, episodes);
    }

    initEpisodeDragSelect() {
      if (this.listEl.__cgsEpisodeDragSelectBound) {
        return;
      }
      let dragging = false;
      let wasDragging = false;
      let startX = 0;
      let startY = 0;

      let overlay = document.getElementById('dragSelOverlay');
      if (!(overlay instanceof HTMLElement)) {
        overlay = document.createElement('div');
        overlay.id = 'dragSelOverlay';
        document.body.appendChild(overlay);
      }
      overlay.style.display = 'none';

      const updateOverlay = (x1, y1, x2, y2) => {
        overlay.style.left = `${Math.min(x1, x2)}px`;
        overlay.style.top = `${Math.min(y1, y2)}px`;
        overlay.style.width = `${Math.abs(x2 - x1)}px`;
        overlay.style.height = `${Math.abs(y2 - y1)}px`;
      };

      const intersects = (a, b) => !(a.right < b.left || a.left > b.right || a.bottom < b.top || a.top > b.bottom);

      document.addEventListener(
        'click',
        (event) => {
          if (!wasDragging) {
            return;
          }
          wasDragging = false;
          if (!this.listEl.contains(event.target)) {
            return;
          }
          event.preventDefault();
          event.stopPropagation();
        },
        true
      );

      document.addEventListener('mousedown', (event) => {
        if (event.button !== 0 || event.target.closest('input, a, button, select, textarea')) {
          return;
        }
        if (!this.listEl.contains(event.target)) {
          return;
        }
        startX = event.clientX;
        startY = event.clientY;
        dragging = false;
        wasDragging = false;
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp, { once: true });
      });

      const onMove = (event) => {
        const deltaX = event.clientX - startX;
        const deltaY = event.clientY - startY;
        if (!dragging && (Math.abs(deltaX) > 5 || Math.abs(deltaY) > 5)) {
          dragging = true;
          document.body.classList.add('drag-selecting');
          overlay.style.display = 'block';
        }
        if (!dragging) {
          return;
        }
        updateOverlay(startX, startY, event.clientX, event.clientY);
      };

      const onUp = (event) => {
        document.removeEventListener('mousemove', onMove);
        document.body.classList.remove('drag-selecting');
        overlay.style.display = 'none';
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

        this.listEl.querySelectorAll('label[data-episode-chip]').forEach((label) => {
          if (!intersects(selectRect, label.getBoundingClientRect())) {
            return;
          }
          const checkbox = document.getElementById(label.htmlFor);
          if (checkbox && !checkbox.checked) {
            checkbox.checked = true;
          }
        });
        this.updateCount();
      };

      this.listEl.__cgsEpisodeDragSelectBound = true;
    }

    ensureModal() {
      if (!this.modal) {
        this.modal = createDialogController(this.modalEl);
      }
      return this.modal;
    }

    ensureScanToast() {
      if (!this.scanToastInstance) {
        this.scanToastInstance = createToastController(requireElement('scanToast'));
      }
      return this.scanToastInstance;
    }

    bindEpisodeListEvents() {
      this.listEl.addEventListener('click', (event) => this.onEpisodeListClick(event));
      this.listEl.addEventListener('change', (event) => this.onEpisodeListChange(event));
    }

    onEpisodeListClick(event) {
      const target = event.target instanceof Element ? event.target : null;
      const label = target ? target.closest('label[data-episode-chip]') : null;
      if (!label || !this.listEl.contains(label)) {
        return;
      }
      const checkboxId = label.getAttribute('for');
      const checkbox = checkboxId ? document.getElementById(checkboxId) : null;
      if (!(checkbox instanceof HTMLInputElement) || checkbox.type !== 'checkbox') {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      checkbox.checked = !checkbox.checked;
      checkbox.dispatchEvent(new Event('change', { bubbles: true }));
    }

    onEpisodeListChange(event) {
      const target = event.target;
      if (!(target instanceof HTMLInputElement) || target.type !== 'checkbox' || !this.listEl.contains(target)) {
        return;
      }
      event.stopPropagation();
      this.updateCount();
    }

    async waitForBridge(methodName = 'fetchEpisodes') {
      return this.bridgeClient.waitFor(methodName);
    }

    beforeOpenBook(_bookKey, _title) {}

    getImmediateEpisodes(bookKey, _title) {
      return this.episodesCache.get(String(bookKey)) || null;
    }

    preloadEpisodes(bookKey, episodes, bookMeta = null) {
      const cacheKey = String(bookKey);
      if (!Array.isArray(episodes)) {
        throw new TypeError('episodes payload must be an array');
      }
      this.episodesCache.set(cacheKey, episodes);
      this.bookMetaCache.set(cacheKey, bookMeta && typeof bookMeta === 'object' ? bookMeta : {});
      if (cacheKey === this.activeBookKey) {
        this.clearPendingTimer();
        this.setLoadingState(false);
        this.renderEpisodes(cacheKey, episodes);
        this.renderBookMeta(this.bookMetaCache.get(cacheKey));
      }
    }

    requestEpisodes(bridge, bookKey) {
      bridge.fetchEpisodes(bookKey);
    }

    async onBookClick(bookKey, title) {
      const cacheKey = String(bookKey);
      const modal = this.ensureModal();
      this.beforeOpenBook(cacheKey, title);
      this.activeBookKey = cacheKey;
      this.titleEl.textContent = title || `Book ${bookKey}`;
      this.renderBookMeta(this.bookMetaCache.get(cacheKey));

      const readyEpisodes = this.getImmediateEpisodes(cacheKey, title);
      if (readyEpisodes) {
        this.setLoadingState(false);
        this.renderEpisodes(cacheKey, readyEpisodes);
        modal.show();
        return;
      }

      this.setLoadingState(true);
      this.renderLoading();
      modal.show();
      this.clearPendingTimer();
      this.pendingTimer = setTimeout(() => {
        if (this.activeBookKey === cacheKey) {
          this.showEpisodeError(this.buildEpisodeErrorMessage('timeout'));
        }
      }, 8000);

      const bridge = await this.waitForBridge('fetchEpisodes');
      if (cacheKey !== this.activeBookKey) {
        return;
      }
      if (!bridge || typeof bridge.fetchEpisodes !== 'function') {
        this.clearPendingTimer();
        this.showEpisodeError(this.buildEpisodeErrorMessage('bridge_not_ready'));
        return;
      }
      this.requestEpisodes(bridge, cacheKey);
    }

    renderBookMeta(meta) {
      const data = meta && typeof meta === 'object' ? meta : {};
      const stats = [
        ['更新', data.updatedAt], ['上架', data.publicDate], ['观看', data.views],
        ['点赞', data.likes], ['页数', data.pages], ['状态', data.status],
        ['类型', data.btype], ['作者', data.artist],
      ].filter(([, value]) => value !== null && value !== undefined && String(value).trim());
      const tags = Array.isArray(data.tags) ? data.tags.filter(Boolean) : [];
      const aliases = Array.isArray(data.otherNames) ? data.otherNames.filter(Boolean) : [];
      const description = String(data.description || '').trim();
      if (!stats.length && !tags.length && !aliases.length && !description) {
        this.bookMetaEl.hidden = true;
        this.bookMetaEl.replaceChildren();
        return;
      }

      const statsHtml = stats.length
        ? `<div class="preview-book-meta__stats">${stats.map(([label, value], index) => `${index ? '<span class="preview-book-meta__stat-sep" aria-hidden="true">·</span>' : ''}<span class="preview-book-meta__stat"><span class="preview-book-meta__stat-label">${escapeHtml(label)}</span> ${escapeHtml(String(value))}</span>`).join('')}</div>`
        : '';
      const aliasesHtml = aliases.length
        ? `<div class="preview-book-meta__aliases">${escapeHtml(aliases.join(' · '))}</div>`
        : '';
      const descriptionBlock = description
        ? `<div class="preview-book-meta__desc-body"><p class="preview-book-meta__description">${escapeHtml(description.slice(0, 120))}${description.length > 120 ? '…' : ''}</p>${description.length > 120 ? '<button type="button" class="preview-book-meta__toggle">展开</button>' : ''}</div>`
        : '';
      const descColHtml = (descriptionBlock || aliasesHtml)
        ? `<div class="preview-book-meta__desc-col">${descriptionBlock}${aliasesHtml}</div>`
        : '';
      const tagsColHtml = tags.length
        ? `<div class="preview-book-meta__tags-col"><div class="preview-book-meta__tags">${tags.map((tag) => `<span class="preview-book-meta__tag">${escapeHtml(String(tag))}</span>`).join('')}</div></div>`
        : '';
      let mainHtml = '';
      if (descColHtml && tagsColHtml) {
        mainHtml = `<div class="preview-book-meta__main">${descColHtml}${tagsColHtml}</div>`;
      } else if (descColHtml) {
        mainHtml = `<div class="preview-book-meta__main preview-book-meta__main--solo">${descColHtml}</div>`;
      } else if (tagsColHtml) {
        mainHtml = `<div class="preview-book-meta__main preview-book-meta__main--solo">${tagsColHtml}</div>`;
      }

      this.bookMetaEl.innerHTML = `${statsHtml}${mainHtml}`;
      const paragraph = this.bookMetaEl.querySelector('.preview-book-meta__description');
      const toggle = this.bookMetaEl.querySelector('.preview-book-meta__toggle');
      if (paragraph && toggle) {
        toggle.setAttribute('aria-expanded', 'false');
        toggle.addEventListener('click', () => {
          const expanded = paragraph.classList.toggle('is-expanded');
          paragraph.textContent = expanded ? description : `${description.slice(0, 120)}…`;
          toggle.textContent = expanded ? '收起' : '展开';
          toggle.setAttribute('aria-expanded', String(expanded));
        });
      }
      this.bookMetaEl.hidden = false;
    }

    onCardClick(event) {
      const target = event.target instanceof Element ? event.target : null;
      const card = target ? target.closest('.normal-book-card[data-book-key]') : null;
      if (!card || target.closest('a')) {
        return;
      }
      const bookKey = card.dataset.bookKey;
      if (document.body.classList.contains('subscribe-select-mode')) {
        const checkbox = card.querySelector('.preview-checkbox > .preview-checkbox-input');
        if (checkbox instanceof HTMLInputElement) {
          event.preventDefault();
          checkbox.checked = !checkbox.checked;
          checkbox.dispatchEvent(new Event('change', { bubbles: true }));
        }
        return;
      }
      const title = card.dataset.bookTitle || `Book ${bookKey}`;
      this.onBookClick(bookKey, title);
    }

    getEpisodeCheckboxes() {
      return this.listEl.querySelectorAll('input[type="checkbox"]');
    }

    setLoadingState(loading) {
      this.btnGroup.querySelectorAll('button, input').forEach((element) => {
        element.disabled = loading;
      });
      if (this.filterInput) {
        this.filterInput.disabled = loading;
      }
    }

    showBtnGroup(visible) {
      this.btnGroup.classList.toggle('is-hidden', !visible);
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
      const reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      this.modalBodyEl.scrollTo({
        top: this.modalBodyEl.scrollHeight,
        behavior: reducedMotion ? 'auto' : 'smooth',
      });
    }

    collectSubmitPayload() {
      if (!window.previewRuntime || typeof window.previewRuntime.collectSubmitPayload !== 'function') {
        throw new Error('previewRuntime.collectSubmitPayload is not ready');
      }
      return window.previewRuntime.collectSubmitPayload();
    }

    renderLoading() {
      this.showBtnGroup(false);
      if (this.filterInput) {
        this.filterInput.value = '';
        this.filterInput.disabled = true;
      }
      this.listEl.innerHTML = `
      <div class="preview-state preview-state--loading">
        <span class="preview-spinner" aria-hidden="true"></span>
        <span>Loading episodes...</span>
      </div>`;
      this.updateCount();
    }

    renderError(message) {
      this.showBtnGroup(false);
      if (this.filterInput) {
        this.filterInput.value = '';
        this.filterInput.disabled = true;
      }
      this.listEl.innerHTML = `<div class="preview-state preview-state--error" role="alert">${escapeHtml(message)}</div>`;
      this.updateCount();
    }

    buildEpisodeErrorMessage(code) {
      const retryHint = '请关闭弹窗后再次点击卡片重试。';
      switch (code) {
        case 'timeout':
          return `章节加载超时（8 秒）。${retryHint}`;
        case 'bridge_not_ready':
          return `预览通道尚未就绪。${retryHint}`;
        case 'parse_error':
          return `章节数据解析失败。${retryHint}`;
        case 'fetch_failed':
        default:
          return `章节加载失败。${retryHint}`;
      }
    }

    applyEpisodeFilter() {
      if (!this.filterInput) {
        return;
      }
      const keyword = this.filterInput.value.trim().toLowerCase();
      let visibleCount = 0;
      this.listEl.querySelectorAll('[data-episode-item]').forEach((item) => {
        const matched = !keyword || (item.dataset.episodeText || '').includes(keyword);
        item.hidden = !matched;
        if (matched) {
          visibleCount += 1;
        }
      });
      const emptyState = this.listEl.querySelector('#episodeEmptyState');
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

    renderEpisodes(bookKey, episodes) {
      if (!Array.isArray(episodes) || episodes.length === 0) {
        this.showBtnGroup(false);
        if (this.filterInput) {
          this.filterInput.value = '';
          this.filterInput.disabled = true;
        }
        this.listEl.innerHTML = '<p class="preview-empty-state">No episodes found.</p>';
        this.updateCount();
        return;
      }

      if (this.filterInput) {
        this.filterInput.value = '';
        this.filterInput.disabled = false;
      }

      let html = '<div class="episodes-grid">';
      const descriptors = [];
      for (let index = 0; index < episodes.length; index += 1) {
        const episode = episodes[index];
        const episodeIndex = Number.isFinite(Number(episode.idx)) ? Number(episode.idx) : index + 1;
        const rawName = String(episode.name || `Episode ${episodeIndex}`);
        const episodeName = escapeHtml(rawName);
        const checkboxId = `ep${bookKey}-${episodeIndex}`;
        const searchText = escapeHtml(`${episodeIndex} ${rawName}`.toLowerCase());
        const isDled = Boolean(episode.downloaded);
        const inputCls = isDled ? 'episode-item-input episode-container-downloaded' : 'episode-item-input';
        const labelCls = isDled ? 'episode-item episode-container-downloaded' : 'episode-item';
        descriptors.push({
          id: checkboxId,
          kind: 'episode',
          checkboxId,
          parentId: String(bookKey),
          downloaded: isDled,
        });
        html += `
        <div class="episode-item-wrap" data-episode-item data-episode-text="${searchText}">
          <input class="${inputCls}" type="checkbox" id="${checkboxId}" autocomplete="off">
          <label data-episode-chip class="${labelCls}" for="${checkboxId}" title="${episodeName}">
            <span class="episode-item-text">
              <span class="episode-item-index">${episodeIndex}</span>${episodeName}
            </span>
          </label>
        </div>`;
      }
      html += '</div>';

      this.listEl.innerHTML = html;
      if (window.previewRuntime && typeof window.previewRuntime.registerItems === 'function') {
        window.previewRuntime.registerItems(descriptors);
      }
      if (window.previewRuntime && typeof window.previewRuntime.refresh === 'function') {
        window.previewRuntime.refresh(this.listEl);
      }
      this.showBtnGroup(true);
      this.updateCount();
      this.afterRenderEpisodes(bookKey);
    }

    afterRenderEpisodes(_bookKey) {}

    updateEpisodes(bookKey, episodes, bookMeta = null) {
      const cacheKey = String(bookKey);
      if (cacheKey !== this.activeBookKey) {
        return;
      }

      this.clearPendingTimer();
      this.setLoadingState(false);

      try {
        if (!Array.isArray(episodes)) {
          throw new TypeError('episodes payload must be an array');
        }
        this.preloadEpisodes(cacheKey, episodes, bookMeta);
      } catch (_error) {
        this.showEpisodeError(this.buildEpisodeErrorMessage('parse_error'));
      }
    }

    showEpisodeError(message) {
      this.clearPendingTimer();
      this.setLoadingState(false);
      this.renderError(message || this.buildEpisodeErrorMessage('fetch_failed'));
    }

    showEpisodeFetchError(bookKey, code = 'fetch_failed', message = '') {
      if (String(bookKey) !== this.activeBookKey) {
        return;
      }
      this.clearPendingTimer();
      this.showEpisodeError(message || this.buildEpisodeErrorMessage(code));
    }

    applyDlScanResult(badges) {
      if (!Array.isArray(badges)) {
        return;
      }
      badges.forEach((badge) => {
        if (!badge || typeof badge !== 'object') {
          return;
        }
        this.renderCardBadgeDl(badge.bookKey, badge.dlMax);
        if (badge.latestEpName) {
          this.renderCardBadgeLatest(badge.bookKey, badge.latestEpName);
        }
      });
    }

    renderCardBadgeDl(bookKey, dlMax) {
      const row = document.getElementById(`status-row-${bookKey}`);
      if (!row) {
        return;
      }
      row.querySelectorAll('.badge-dl').forEach((element) => element.remove());
      const span = document.createElement('span');
      span.className = 'book-card-badge book-card-badge-muted badge-dl status-badge-fade';
      span.textContent = `DL: ${dlMax}`;
      span.title = span.textContent;
      row.prepend(span);
    }

    renderCardBadgeLatest(bookKey, latestEpName) {
      const row = document.getElementById(`status-row-${bookKey}`);
      if (!row) {
        return;
      }
      row.querySelectorAll('.badge-latest').forEach((element) => element.remove());
      const dlBadge = row.querySelector('.badge-dl');
      if (!dlBadge) {
        return;
      }
      const span = document.createElement('span');
      const dlText = dlBadge.textContent.replace('DL: ', '');
      const hasUpdate = dlText !== latestEpName;
      span.className = hasUpdate
        ? 'book-card-badge book-card-badge-danger badge-latest status-badge-fade'
        : 'book-card-badge book-card-badge-success badge-latest status-badge-fade';
      span.textContent = hasUpdate ? `NEW: ${latestEpName}` : '\u2713';
      span.title = span.textContent;
      row.appendChild(span);
    }

    showScanNotification(message) {
      requireElement('scanToastBody').textContent = message;
      this.ensureScanToast().show();
    }

    hideScanNotification() {
      this.ensureScanToast().hide();
    }

  }

  previewUi.EpisodePreviewBase = EpisodePreviewBase;
})();

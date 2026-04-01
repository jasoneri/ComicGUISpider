(() => {
  const previewUi = window.previewUi;
  const EpisodePreviewBase = previewUi && previewUi.EpisodePreviewBase;
  if (!previewUi || !EpisodePreviewBase) {
    throw new Error('preview episode base is not ready');
  }

  const esc = previewUi.escapeHtml;

  function getRuntime() {
    if (!window.previewRuntime) {
      throw new Error('previewRuntime is not ready');
    }
    return window.previewRuntime;
  }

  function updateProgressBar() {
    const bar = document.getElementById('progress-bar');
    const track = bar ? bar.parentElement : null;
    if (!bar) {
      return;
    }
    const max = window.CLIP_MAX_TASKS || 0;
    const count = document.querySelectorAll('.singal-task').length;
    if (max <= 0) {
      bar.style.width = '0';
      bar.textContent = '0%';
      bar.classList.remove('is-complete');
      if (track) {
        track.setAttribute('aria-valuenow', '0');
      }
      return;
    }
    if (count >= max) {
      bar.style.width = '100%';
      bar.classList.add('is-complete');
      bar.textContent = '100% Completed';
      if (track) {
        track.setAttribute('aria-valuenow', '100');
      }
      return;
    }
    const pct = Math.round((count / max) * 100);
    bar.style.width = `${pct}%`;
    bar.classList.remove('is-complete');
    bar.textContent = `${pct}%`;
    if (track) {
      track.setAttribute('aria-valuenow', String(pct));
    }
  }

  function buildBadgeGroups(options) {
    const bottom = [];
    const top = [];
    const pagesIcon = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="currentColor" d="m19 1l-5 5v11l5-4.5zm2 4v13.5c-1.1-.35-2.3-.5-3.5-.5c-1.7 0-4.15.65-5.5 1.5V6c-1.45-1.1-3.55-1.5-5.5-1.5S2.45 4.9 1 6v14.65c0 .25.25.5.5.5c.1 0 .15-.05.25-.05C3.1 20.45 5.05 20 6.5 20c1.95 0 4.05.4 5.5 1.5c1.35-.85 3.8-1.5 5.5-1.5c1.65 0 3.35.3 4.75 1.05c.1.05.15.05.25.05c.25 0 .5-.25.5-.5V6c-.6-.45-1.25-.75-2-1M10 18.41C8.75 18.09 7.5 18 6.5 18c-1.06 0-2.32.19-3.5.5V7.13c.91-.4 2.14-.63 3.5-.63s2.59.23 3.5.63z" /></svg>';
    const likesIcon = '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48"><path fill="currentColor" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="4" d="M15 8C8.925 8 4 12.925 4 19c0 11 13 21 20 23.326C31 40 44 30 44 19c0-6.075-4.925-11-11-11c-3.72 0-7.01 1.847-9 4.674A10.99 10.99 0 0 0 15 8" /></svg>';
    if (options.likes) {
      bottom.push(`<span class="demo-badge demo-badge-likes">${likesIcon}<span class="demo-badge-label">${esc(options.likes)}</span></span>`);
    }
    if (options.pages) {
      bottom.push(`<span class="demo-badge demo-badge-pages">${pagesIcon}<span class="demo-badge-label">${esc(options.pages)}</span></span>`);
    }
    if (options.lang) {
      const text = esc(options.lang);
      top.push(`<span class="demo-badge demo-badge-light demo-badge-lang" title="${text}">${text}</span>`);
    }
    if (options.btype) {
      const text = esc(options.btype);
      top.push(`<span class="demo-badge demo-badge-light" title="${text}">${text}</span>`);
    }
    let html = '';
    if (bottom.length) {
      html += `<div class="demo-badge-group demo-badge-group-bottom">${bottom.join('')}</div>`;
    }
    if (top.length) {
      html += `<div class="demo-badge-group demo-badge-group-top">${top.join('')}</div>`;
    }
    return html;
  }

  function buildMetaBadges(metaBadges) {
    if (!metaBadges || !metaBadges.length) {
      return '';
    }
    const lines = metaBadges.map((badge) => (
      `<span class="demo-badge demo-badge-manga-meta" title="${esc(badge)}"><span class="demo-badge-label">${esc(badge)}</span></span>`
    ));
    return `<div class="demo-badge-group demo-badge-group-bottom">${lines.join('\n')}</div>`;
  }

  function bookCardHtml(idx, imgSrc, title, url, options = {}) {
    const safeIdx = esc(idx);
    const safeTitle = esc(title);
    const safeUrl = esc(url);
    const safeImg = esc(imgSrc);
    const isDownloaded = options.flag === 'downloaded';
    const lockedAttr = isDownloaded ? ' data-preview-locked="true"' : '';
    const disabledAttr = isDownloaded ? ' disabled aria-disabled="true"' : '';
    const cardStateClass = isDownloaded ? ' preview-card-state-downloaded' : '';
    const mediaStateClass = isDownloaded ? ' container-downloaded' : '';
    const imageStateClass = isDownloaded ? ' img-downloaded' : '';
    const badges = buildBadgeGroups(options);
    const extraInfo = options.extra_info ? `\n          <div class="card-extra-info">${options.extra_info}</div>` : '';
    return `<div class="singal-task preview-card${cardStateClass}">
        <div class="preview-checkbox preview-card-check">
          <input class="preview-checkbox-input" type="checkbox" name="img" id="${safeIdx}"${lockedAttr}${disabledAttr}>
          <label class="preview-checkbox-label" for="${safeIdx}">
            <span class="preview-checkbox-toggle" aria-hidden="true"><span class="preview-checkbox-tick"></span></span>
            <div class="preview-checkbox-media${mediaStateClass}">
              <img src="${safeImg}" title="${safeTitle}" alt="${safeTitle}" class="preview-card-image${imageStateClass}"/>
              ${badges}
            </div>
          </label>
        </div>
        <div class="preview-title">
          <a href="${safeUrl}" title="${safeTitle}" class="preview-title-link">
            <p class="preview-title-clamp">${safeTitle}</p>
          </a>${extraInfo}
        </div>
      </div>`;
  }

  function bookWithEpsCardHtml(idx, imgSrc, title, url, options = {}) {
    const safeIdx = esc(idx);
    const safeTitle = esc(title);
    const safeImg = esc(imgSrc);
    const metaBadgesHtml = buildMetaBadges(options.meta_badges);
    let metaHtml = '';
    if (options.meta && options.meta.length) {
      metaHtml = options.meta.map((meta) => (
        `<p class="book-card-meta-item" title="${esc(meta)}">${esc(meta)}</p>`
      )).join('\n');
    }
    const extraInfo = options.extra_info ? `\n          <div class="card-extra-info">${options.extra_info}</div>` : '';
    return `<article class="preview-manga-card singal-task">
      <div class="book-card normal-book-card" data-book-key="${safeIdx}" data-book-title="${safeTitle}" role="button" aria-label="${safeTitle}">
        <div class="book-card-media">
          <img src="${safeImg}" class="book-card-cover" alt="${safeTitle}" title="${safeTitle}" onerror="this.onerror=null;this.src='../GUI/src/preview_format/placeholder.svg';">
          ${metaBadgesHtml}
        </div>
        <div class="book-card-body">
          <h3 class="book-card-title" title="${safeTitle}">${safeTitle}</h3>
          ${metaHtml}${extraInfo}
        </div>
        <div id="status-row-${safeIdx}" class="book-card-status" aria-live="polite"></div>
      </div>
    </article>`;
  }

  class FixPreviewApp extends EpisodePreviewBase {
    constructor() {
      super();
      this.savedSelections = new Map();
      this._activeGroupIdx = null;
    }

    init() {
      this.registerCommandHandlers();
      this.registerWindowApi();
      getRuntime().setExtraCheckedIdsResolver(() => this.getAllSelectedEpisodeIds());
      this.bindDocumentEvents();
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => this.onDomReady(), { once: true });
        return;
      }
      this.onDomReady();
    }

    registerWindowApi() {
      window.addBookCard = (idx, imgSrc, title, url, options) => this.addBookCard(idx, imgSrc, title, url, options);
      window.addBookWithEpsCard = (idx, imgSrc, title, url, options) => this.addBookWithEpsCard(idx, imgSrc, title, url, options);
      window.addFixGroup = (groupIdx, keyword) => this.addFixGroup(groupIdx, keyword);
      window.finishTasks = () => document.documentElement.outerHTML;
      window.checkDoneTasks = () => document.querySelectorAll('.singal-task').length;
      window.selectAllEpisodes = (bookKey) => this.selectAllEpisodes(bookKey);
    }

    bindDocumentEvents() {
      this.bindBaseDocumentEvents();
      document.addEventListener('click', (event) => this.onGroupToggleClick(event));
    }

    onDomReady() {
      this.onDomReadyBase();
      this.modalEl.addEventListener('preview-dialog:show', () => this.syncBulkToolbarPresentation({ modalOpen: true }));
      this.modalEl.addEventListener('preview-dialog:hide', () => this.syncBulkToolbarPresentation({ modalOpen: false }));
      this.syncBulkToolbarPresentation();
      updateProgressBar();
    }

    getUpperTarget(groupIdx) {
      if (groupIdx != null) {
        const group = document.querySelector(`.fix-group[data-group-idx="${groupIdx}"]`);
        return group ? group.querySelector('.fix-group-upper') : null;
      }
      return document.getElementById('bookCardsUpper');
    }

    getLowerTarget(groupIdx) {
      if (groupIdx != null) {
        const group = document.querySelector(`.fix-group[data-group-idx="${groupIdx}"]`);
        return group ? group.querySelector('.fix-group-lower') : null;
      }
      return document.getElementById('bookCardsLower');
    }

    addBookCard(idx, imgSrc, title, url, options = {}) {
      const groupIdx = options._groupIdx ?? this._activeGroupIdx;
      const target = this.getUpperTarget(groupIdx);
      if (!target) {
        return;
      }
      target.insertAdjacentHTML('beforeend', bookCardHtml(idx, imgSrc, title, url, options));
      const runtime = getRuntime();
      runtime.registerItems([{
        id: String(idx),
        kind: 'book',
        checkboxId: String(idx),
        scope: 'fix',
        groupIdx: groupIdx != null ? String(groupIdx) : undefined,
        locked: options.flag === 'downloaded',
        downloaded: options.flag === 'downloaded',
      }]);
      runtime.refresh(target.lastElementChild);
      updateProgressBar();
    }

    addBookWithEpsCard(idx, imgSrc, title, url, options = {}) {
      const groupIdx = options._groupIdx ?? this._activeGroupIdx;
      const target = this.getLowerTarget(groupIdx);
      if (!target) {
        return;
      }
      target.insertAdjacentHTML('beforeend', bookWithEpsCardHtml(idx, imgSrc, title, url, options));
      updateProgressBar();
    }

    addFixGroup(groupIdx, keyword) {
      const groupStack = document.getElementById('fixGroupStack');
      const fragments = document.getElementById('fixFragmentSections');
      const content = groupStack || document.getElementById('fixContent');
      if (!content) {
        return;
      }
      if (groupStack) {
        groupStack.hidden = false;
      }
      if (fragments) {
        fragments.hidden = true;
      }
      const safeKeyword = esc(keyword);
      const html = `<div class="fix-group" data-group-idx="${groupIdx}" data-group-keyword="${safeKeyword}">
        <div class="fix-group-header">
          <h2 class="fix-group-title">
            <span class="fix-group-index">${groupIdx}</span>
            <span class="fix-group-keyword">${safeKeyword}</span>
          </h2>
          <button type="button" class="preview-action-button preview-action-button--primary" data-group-toggle="${groupIdx}">全选切换</button>
        </div>
        <section class="fix-group-upper book-grid" data-empty-label="该分组上半区暂无内容"></section>
        <section class="fix-group-lower book-grid" data-empty-label="该分组下半区暂无内容"></section>
      </div>`;
      content.insertAdjacentHTML('beforeend', html);
      this._activeGroupIdx = groupIdx;
      this.syncBulkToolbarPresentation();
    }

    syncBulkToolbarPresentation(options = {}) {
      const bulkSelect = window.previewBulkSelect;
      if (!bulkSelect) {
        return;
      }
      const host = document.getElementById('previewBulkSelectHost');
      const fragments = document.getElementById('fixFragmentSections');
      const modalOpen = options.modalOpen ?? this.ensureModal().isOpen();
      const activeHost = !modalOpen && host && fragments && !fragments.hidden && !host.closest('[hidden]') ? host : null;
      bulkSelect.setHost(activeHost);
      bulkSelect.setHidden(modalOpen);
      bulkSelect.refresh();
    }

    onGroupToggleClick(event) {
      const button = event.target instanceof Element ? event.target.closest('[data-group-toggle]') : null;
      if (!button) {
        return;
      }
      const groupIdx = button.getAttribute('data-group-toggle');
      if (groupIdx) {
        this.toggleGroupSelection(groupIdx);
      }
    }

    beforeOpenBook() {
      this._saveCurrentEpisodeSelections();
    }

    afterRenderEpisodes(bookKey) {
      this._restoreEpisodeSelections(bookKey);
    }

    _saveCurrentEpisodeSelections() {
      if (!this.activeBookKey) {
        return;
      }
      const checked = new Set();
      this.getEpisodeCheckboxes().forEach((checkbox) => {
        if (checkbox.checked) {
          checked.add(checkbox.id);
        }
      });
      if (checked.size) {
        this.savedSelections.set(this.activeBookKey, checked);
        return;
      }
      this.savedSelections.delete(this.activeBookKey);
    }

    _restoreEpisodeSelections(bookKey) {
      const saved = this.savedSelections.get(bookKey);
      if (!saved) {
        return;
      }
      this.getEpisodeCheckboxes().forEach((checkbox) => {
        checkbox.checked = saved.has(checkbox.id);
      });
      this.updateCount();
    }

    selectAllEpisodes(bookKey) {
      const key = String(bookKey);
      const cached = this.episodesCache.get(key);
      if (!cached || !cached.length) {
        return;
      }
      const ids = new Set();
      for (let index = 0; index < cached.length; index += 1) {
        const episodeIndex = Number.isFinite(Number(cached[index].idx)) ? Number(cached[index].idx) : index + 1;
        ids.add(`ep${key}-${episodeIndex}`);
      }
      this.savedSelections.set(key, ids);
      if (key === this.activeBookKey) {
        this.getEpisodeCheckboxes().forEach((checkbox) => {
          checkbox.checked = ids.has(checkbox.id);
        });
        this.updateCount();
      }
    }

    getAllSelectedEpisodeIds() {
      this._saveCurrentEpisodeSelections();
      const all = [];
      this.savedSelections.forEach((ids) => ids.forEach((id) => all.push(id)));
      return all;
    }

    toggleGroupSelection(groupIdx) {
      const runtime = getRuntime();
      const ids = runtime.getItemIds({ kind: 'book', scope: 'fix', selectableOnly: true, requireCheckbox: true })
        .filter((id) => runtime.resolveItem(id)?.groupIdx === String(groupIdx));
      if (!ids.length) {
        return;
      }
      runtime.toggleAll(ids);
      runtime.refresh();
    }
  }

  new FixPreviewApp().init();
})();

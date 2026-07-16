(() => {
  const OVERLAY_ID = 'previewPagingOverlay';
  const DEFAULT_TEXT = 'paging..';

  function requireCommandBus() {
    const bus = window.previewCommandBus;
    if (!bus || typeof bus.register !== 'function') {
      throw new Error('previewCommandBus is not ready for preview.paging');
    }
    return bus;
  }

  function ensureOverlay() {
    let overlay = document.getElementById(OVERLAY_ID);
    if (overlay instanceof HTMLElement) {
      return overlay;
    }
    overlay = document.createElement('div');
    overlay.id = OVERLAY_ID;
    overlay.className = 'preview-paging-overlay';
    overlay.hidden = true;
    overlay.setAttribute('aria-busy', 'true');
    overlay.setAttribute('aria-live', 'polite');
    overlay.innerHTML = [
      '<div class="preview-paging-loader" role="status">',
      `  <span class="loader-text">${DEFAULT_TEXT}</span>`,
      '  <span class="load" aria-hidden="true"></span>',
      '</div>',
    ].join('');
    document.body.appendChild(overlay);
    return overlay;
  }

  function showPagingOverlay(payload) {
    const overlay = ensureOverlay();
    const textNode = overlay.querySelector('.loader-text');
    const label = payload && payload.text != null && String(payload.text).trim()
      ? String(payload.text).trim()
      : DEFAULT_TEXT;
    if (textNode) {
      textNode.textContent = label;
    }
    overlay.hidden = false;
  }

  function hidePagingOverlay() {
    const overlay = document.getElementById(OVERLAY_ID);
    if (overlay instanceof HTMLElement) {
      overlay.hidden = true;
    }
  }

  function registerHandlers() {
    const bus = requireCommandBus();
    bus.register('preview.paging.show', (payload) => {
      showPagingOverlay(payload || {});
    });
    bus.register('preview.paging.hide', () => {
      hidePagingOverlay();
    });
  }

  registerHandlers();
  window.previewPaging = {
    show: showPagingOverlay,
    hide: hidePagingOverlay,
  };
})();

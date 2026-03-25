(() => {
  const BAR_ID = 'previewBulkSelectBar';
  const DRAG_OVERLAY_ID = 'dragSelOverlay';

  function getRuntime() {
    if (!window.previewRuntime) {
      throw new Error('previewRuntime is not ready');
    }
    return window.previewRuntime;
  }

  function getBookIds(options = {}) {
    return getRuntime().getItemIds({
      kind: 'book',
      requireCheckbox: true,
      ...options,
    });
  }

  function clampSelectCount(total, inputEl) {
    const parsed = parseInt(inputEl.value, 10);
    const value = Number.isFinite(parsed) ? parsed : 1;
    const clamped = Math.max(1, Math.min(value, total > 0 ? total : 1));
    inputEl.value = String(clamped);
    return clamped;
  }

  function getToolbarControl(toolbar, selector) {
    const element = toolbar.querySelector(selector);
    if (!(element instanceof HTMLElement)) {
      throw new Error(`preview bulk select is missing required element: ${selector}`);
    }
    return element;
  }

  function ensureToolbar() {
    const toolbar = document.getElementById(BAR_ID);
    if (!(toolbar instanceof HTMLElement)) {
      throw new Error('preview bulk select toolbar is missing from the formal template');
    }
    getToolbarControl(toolbar, '#bulkClearBtn');
    getToolbarControl(toolbar, '#bulkToggleAllBtn');
    getToolbarControl(toolbar, '#bulkFirstBtn');
    getToolbarControl(toolbar, '#bulkLastBtn');
    getToolbarControl(toolbar, '#bulkSelectCountInput');
    getToolbarControl(toolbar, '#bulkSelectedCount');
    return toolbar;
  }

  function syncPageSpacing(toolbar, basePaddingBottom, presentation) {
    if (presentation.hidden || presentation.inline) {
      document.body.style.paddingBottom = basePaddingBottom ? `${basePaddingBottom}px` : '';
      return;
    }
    const spacing = Math.ceil(toolbar.getBoundingClientRect().height) + 12;
    const applied = Math.max(basePaddingBottom, spacing);
    document.body.style.paddingBottom = `${applied}px`;
  }

  function syncToolbarPresentation(toolbar, basePaddingBottom, state) {
    const host = state.host instanceof HTMLElement && !state.host.closest('[hidden]') ? state.host : null;
    const inline = Boolean(host);
    const parent = host || document.body;
    if (toolbar.parentElement !== parent) {
      parent.appendChild(toolbar);
    }
    toolbar.hidden = state.hidden;
    toolbar.setAttribute('aria-hidden', String(state.hidden));
    toolbar.classList.toggle('preview-bulk-select--inline', inline);
    toolbar.classList.toggle('preview-bulk-select--floating', !inline);
    syncPageSpacing(toolbar, basePaddingBottom, {
      hidden: state.hidden,
      inline,
    });
  }

  function scrollPageToBottom() {
    const scrollTarget = Math.max(
      document.documentElement?.scrollHeight || 0,
      document.body?.scrollHeight || 0
    );
    window.scrollTo({
      top: scrollTarget,
      behavior: 'smooth',
    });
  }

  function mount() {
    const toolbar = ensureToolbar();
    const toggleAllBtn = getToolbarControl(toolbar, '#bulkToggleAllBtn');
    const firstBtn = getToolbarControl(toolbar, '#bulkFirstBtn');
    const lastBtn = getToolbarControl(toolbar, '#bulkLastBtn');
    const clearBtn = getToolbarControl(toolbar, '#bulkClearBtn');
    const countInput = getToolbarControl(toolbar, '#bulkSelectCountInput');
    const countBadge = getToolbarControl(toolbar, '#bulkSelectedCount');
    const presentation = {
      host: null,
      hidden: false,
    };
    const basePaddingBottom = parseFloat(window.getComputedStyle(document.body).paddingBottom) || 0;

    function syncPresentation() {
      syncToolbarPresentation(toolbar, basePaddingBottom, presentation);
    }

    function refresh() {
      syncPresentation();
      const runtime = getRuntime();
      const bookIds = getBookIds();
      const selectableIds = getBookIds({ selectableOnly: true });
      const checked = runtime.getCheckedIds({ kind: 'book' }).length;
      countBadge.textContent = `${checked}/${bookIds.length} selected`;

      const disabled = selectableIds.length === 0;
      toggleAllBtn.disabled = disabled;
      firstBtn.disabled = disabled;
      lastBtn.disabled = disabled;
      countInput.disabled = disabled;
    }

    if (!toolbar.__cgsBulkSelectBound) {
      clearBtn.addEventListener('click', () => {
        const runtime = getRuntime();
        runtime.clearChecked(getBookIds());
        refresh();
      });
      toggleAllBtn.addEventListener('click', () => {
        const runtime = getRuntime();
        const selectableIds = getBookIds({ selectableOnly: true });
        runtime.toggleAll(selectableIds);
        refresh();
      });
      firstBtn.addEventListener('click', () => {
        const runtime = getRuntime();
        const selectableIds = getBookIds({ selectableOnly: true });
        const total = selectableIds.length;
        if (total === 0) {
          return;
        }
        const count = clampSelectCount(total, countInput);
        runtime.clearChecked(getBookIds());
        runtime.selectRange(selectableIds, { fromEnd: false, count });
        refresh();
      });
      lastBtn.addEventListener('click', () => {
        const runtime = getRuntime();
        const selectableIds = getBookIds({ selectableOnly: true });
        const total = selectableIds.length;
        if (total === 0) {
          return;
        }
        const count = clampSelectCount(total, countInput);
        runtime.clearChecked(getBookIds());
        runtime.selectRange(selectableIds, { fromEnd: true, count });
        refresh();
        scrollPageToBottom();
      });
      countInput.addEventListener('blur', () => {
        clampSelectCount(getBookIds({ selectableOnly: true }).length, countInput);
      });
      countInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          clampSelectCount(getBookIds({ selectableOnly: true }).length, countInput);
        }
      });
      document.addEventListener('change', (event) => {
        if (event.target instanceof HTMLInputElement && event.target.type === 'checkbox' && event.target.id) {
          refresh();
        }
      });
      document.addEventListener('preview-runtime:refresh', refresh);

      let resizeRafId = 0;
      window.addEventListener('resize', () => {
        if (resizeRafId) {
          return;
        }
        resizeRafId = window.requestAnimationFrame(() => {
          resizeRafId = 0;
          syncPresentation();
        });
      });
      initDragSelect(refresh);
      toolbar.__cgsBulkSelectBound = true;
    }

    window.previewBulkSelect = {
      refresh,
      setHost(hostEl) {
        presentation.host = hostEl instanceof HTMLElement ? hostEl : null;
      },
      setHidden(hidden) {
        presentation.hidden = Boolean(hidden);
      },
    };

    refresh();
  }

  function initDragSelect(onSelectionChanged) {
    if (document.body.__cgsDragSelectBound) {
      return;
    }
    let dragging = false;
    let wasDragging = false;
    let startX = 0;
    let startY = 0;

    let overlay = document.getElementById(DRAG_OVERLAY_ID);
    if (!(overlay instanceof HTMLElement)) {
      overlay = document.createElement('div');
      overlay.id = DRAG_OVERLAY_ID;
      document.body.appendChild(overlay);
    }
    overlay.style.display = 'none';

    function updateOverlay(x1, y1, x2, y2) {
      overlay.style.left = `${Math.min(x1, x2)}px`;
      overlay.style.top = `${Math.min(y1, y2)}px`;
      overlay.style.width = `${Math.abs(x2 - x1)}px`;
      overlay.style.height = `${Math.abs(y2 - y1)}px`;
    }

    function intersects(a, b) {
      return !(a.right < b.left || a.left > b.right || a.bottom < b.top || a.top > b.bottom);
    }

    document.addEventListener('click', (event) => {
      if (!wasDragging) {
        return;
      }
      wasDragging = false;
      event.preventDefault();
      event.stopPropagation();
    }, true);

    document.addEventListener('mousedown', (event) => {
      if (event.button !== 0) {
        return;
      }
      if (event.target.closest('input, a, button, select, textarea')) {
        return;
      }
      startX = event.clientX;
      startY = event.clientY;
      dragging = false;
      wasDragging = false;
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp, { once: true });
    });

    function onMove(event) {
      const dx = event.clientX - startX;
      const dy = event.clientY - startY;
      if (!dragging && (Math.abs(dx) > 5 || Math.abs(dy) > 5)) {
        dragging = true;
        document.body.classList.add('drag-selecting');
        overlay.style.display = 'block';
      }
      if (!dragging) {
        return;
      }
      updateOverlay(startX, startY, event.clientX, event.clientY);
    }

    function onUp(event) {
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

      const runtime = getRuntime();
      getBookIds({ selectableOnly: true }).forEach((id) => {
        const targets = runtime.resolveDomTargets(id);
        const hitTarget = targets.card || targets.label || targets.checkbox;
        if (!hitTarget) {
          return;
        }
        if (intersects(selectRect, hitTarget.getBoundingClientRect())) {
          runtime.setChecked(id, true);
        }
      });
      onSelectionChanged();
    }

    document.body.__cgsDragSelectBound = true;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();

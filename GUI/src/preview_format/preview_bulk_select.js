(() => {
  const BAR_ID = "previewBulkSelectBar";
  const STYLE_ID = "previewBulkSelectStyle";
  const CHECKBOX_SELECTOR = '.singal-task input.form-check-input[name="img"][id]';

  function getBookCheckboxes() {
    return Array.from(document.querySelectorAll(CHECKBOX_SELECTOR));
  }

  function clampSelectCount(total, inputEl) {
    const parsed = parseInt(inputEl.value, 10);
    const value = Number.isFinite(parsed) ? parsed : 1;
    const clamped = Math.max(1, Math.min(value, total > 0 ? total : 1));
    inputEl.value = String(clamped);
    return clamped;
  }

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      #${BAR_ID} {
        position: fixed;
        left: 2rem;
        bottom: 0;
        backdrop-filter: blur(0.8px);
        z-index: 1040;
      }
      #${BAR_ID} .bulk-toolbar-inner {
        max-width: 880px;
        margin: 0 auto;
        padding: .5rem .75rem;
      }
      #${BAR_ID} .bulk-toolbar-row {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        margin: -.25rem 0 0 -.5rem;
      }
      #${BAR_ID} .bulk-toolbar-row > * {
        margin: .25rem 0 0 .5rem;
      }
    `;
    document.head.appendChild(style);
  }

  function applyBottomSafeSpacing(toolbar, basePaddingBottom) {
    const spacing = Math.ceil(toolbar.getBoundingClientRect().height) + 12;
    const applied = Math.max(basePaddingBottom, spacing);
    document.body.style.paddingBottom = `${applied}px`;
  }

  function mount() {
    if (document.getElementById(BAR_ID)) return;
    ensureStyle();

    const toolbar = document.createElement("div");
    toolbar.id = BAR_ID;
    toolbar.innerHTML = `
      <div class="bulk-toolbar-inner">
        <div class="bulk-toolbar-row">
          <div class="input-group input-group-sm" style="width: auto;">
            <button id="bulkClearBtn" type="button" class="btn btn-outline-secondary" title="清空选择">
              <svg xmlns="http://www.w3.org/2000/svg" width="20px" height="20px" viewBox="0 0 1024 1024">
                <path fill="currentColor" d="m899.1 869.6l-53-305.6H864c14.4 0 26-11.6 26-26V346c0-14.4-11.6-26-26-26H618V138c0-14.4-11.6-26-26-26H432c-14.4 0-26 11.6-26 26v182H160c-14.4 0-26 11.6-26 26v192c0 14.4 11.6 26 26 26h17.9l-53 305.6c-.3 1.5-.4 3-.4 4.4c0 14.4 11.6 26 26 26h723c1.5 0 3-.1 4.4-.4c14.2-2.4 23.7-15.9 21.2-30M204 390h272V182h72v208h272v104H204zm468 440V674c0-4.4-3.6-8-8-8h-48c-4.4 0-8 3.6-8 8v156H416V674c0-4.4-3.6-8-8-8h-48c-4.4 0-8 3.6-8 8v156H202.8l45.1-260H776l45.1 260z" />
              </svg>
            </button>
            <button class="btn btn-outline-secondary" type="button" id="bulkToggleAllBtn">All</button>
            <button class="btn btn-outline-secondary" type="button" id="bulkFirstBtn">First~</button>
            <input
              type="number"
              class="form-control text-center"
              id="bulkSelectCountInput"
              value="1"
              min="1"
              step="1"
              inputmode="numeric"
              aria-label="Number of books to select"
              style="max-width: 72px;"
            >
            <button class="btn btn-outline-secondary" type="button" id="bulkLastBtn">~Last</button>
          </div>
          <span class="badge text-bg-primary" id="bulkSelectedCount">0/0 selected</span>
        </div>
      </div>
    `;
    toolbar.querySelector('#bulkClearBtn').addEventListener('click', () => {
      getBookCheckboxes().forEach(cb => {
        if (cb.checked) {
          cb.checked = false;
          cb.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });
    });
    document.body.appendChild(toolbar);

    const toggleAllBtn = document.getElementById("bulkToggleAllBtn");
    const firstBtn = document.getElementById("bulkFirstBtn");
    const lastBtn = document.getElementById("bulkLastBtn");
    const countInput = document.getElementById("bulkSelectCountInput");
    const countBadge = document.getElementById("bulkSelectedCount");
    const basePaddingBottom = parseFloat(window.getComputedStyle(document.body).paddingBottom) || 0;

    function updateCount() {
      const checkboxes = getBookCheckboxes();
      const total = checkboxes.length;
      const checked = checkboxes.filter(cb => cb.checked).length;
      countBadge.textContent = `${checked}/${total} selected`;

      const disabled = total === 0;
      toggleAllBtn.disabled = disabled;
      firstBtn.disabled = disabled;
      lastBtn.disabled = disabled;
      countInput.disabled = disabled;
    }

    function toggleAll() {
      const checkboxes = getBookCheckboxes();
      if (checkboxes.length === 0) return;
      const allChecked = checkboxes.every(cb => cb.checked);
      checkboxes.forEach(cb => {
        cb.checked = !allChecked;
      });
      updateCount();
    }

    function selectRange(fromEnd) {
      const checkboxes = getBookCheckboxes();
      const total = checkboxes.length;
      if (total === 0) return;

      const n = clampSelectCount(total, countInput);
      checkboxes.forEach(cb => {
        cb.checked = false;
      });

      const start = fromEnd ? total - n : 0;
      const end = fromEnd ? total : n;
      for (let i = start; i < end; i += 1) {
        checkboxes[i].checked = true;
      }
      updateCount();
    }

    toggleAllBtn.addEventListener("click", toggleAll);
    firstBtn.addEventListener("click", () => selectRange(false));
    lastBtn.addEventListener("click", () => selectRange(true));

    countInput.addEventListener("blur", () => {
      clampSelectCount(getBookCheckboxes().length, countInput);
    });
    countInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        clampSelectCount(getBookCheckboxes().length, countInput);
      }
    });

    document.addEventListener("change", (event) => {
      if (event.target && event.target.matches(CHECKBOX_SELECTOR)) {
        updateCount();
      }
    });

    let resizeRafId = 0;
    const scheduleSpacingUpdate = () => {
      if (resizeRafId) return;
      resizeRafId = window.requestAnimationFrame(() => {
        resizeRafId = 0;
        applyBottomSafeSpacing(toolbar, basePaddingBottom);
      });
    };

    applyBottomSafeSpacing(toolbar, basePaddingBottom);
    window.addEventListener("resize", scheduleSpacingUpdate);
    updateCount();

    initDragSelect();
  }

  // ── 拖拽框选 ──────────────────────────────────────────────────────
  function initDragSelect() {
    let dragging = false;
    let wasDragging = false;
    let startX = 0, startY = 0;

    const s = document.createElement('style');
    s.textContent = `
      #dragSelOverlay {
        position: fixed; pointer-events: none; z-index: 9999;
        display: none; box-sizing: border-box;
        border: 2px dashed #0d6efd;
        background: rgba(13,110,253,0.08);
      }
      body.drag-selecting, body.drag-selecting * {
        user-select: none !important;
        -webkit-user-select: none !important;
        cursor: crosshair !important;
      }
    `;
    document.head.appendChild(s);

    const overlay = document.createElement('div');
    overlay.id = 'dragSelOverlay';
    document.body.appendChild(overlay);

    function updateOverlay(x1, y1, x2, y2) {
      overlay.style.left   = Math.min(x1, x2) + 'px';
      overlay.style.top    = Math.min(y1, y2) + 'px';
      overlay.style.width  = Math.abs(x2 - x1) + 'px';
      overlay.style.height = Math.abs(y2 - y1) + 'px';
    }

    function intersects(a, b) {
      return !(a.right < b.left || a.left > b.right ||
              a.bottom < b.top || a.top > b.bottom);
    }

    document.addEventListener('click', (e) => {
      if (!wasDragging) return;
      wasDragging = false;
      e.preventDefault();
      e.stopPropagation();
    }, true);

    document.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return;
      if (e.target.closest('input, a, button, select, textarea')) return;
      startX = e.clientX;
      startY = e.clientY;
      dragging = false;
      wasDragging = false;
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp, { once: true });
    });

    function onMove(e) {
      const dx = e.clientX - startX, dy = e.clientY - startY;
      if (!dragging && (Math.abs(dx) > 5 || Math.abs(dy) > 5)) {
        dragging = true;
        document.body.classList.add('drag-selecting');
        overlay.style.display = 'block';
      }
      if (!dragging) return;
      updateOverlay(startX, startY, e.clientX, e.clientY);
    }

    function onUp(e) {
      document.removeEventListener('mousemove', onMove);
      document.body.classList.remove('drag-selecting');
      overlay.style.display = 'none';
      if (!dragging) return;

      dragging = false;
      wasDragging = true; // 触发上面 click 捕获压制

      const selR = {
        left:   Math.min(startX, e.clientX),
        top:    Math.min(startY, e.clientY),
        right:  Math.max(startX, e.clientX),
        bottom: Math.max(startY, e.clientY),
      };
      if (selR.right - selR.left < 5 && selR.bottom - selR.top < 5) return;

      document.querySelectorAll('.singal-task').forEach(task => {
        const r = task.getBoundingClientRect();
        if (intersects(selR, r)) {
          const cb = task.querySelector('input.form-check-input[name="img"]');
          if (cb && !cb.checked) {
            cb.checked = true;
            cb.dispatchEvent(new Event('change', { bubbles: true }));
          }
        }
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();

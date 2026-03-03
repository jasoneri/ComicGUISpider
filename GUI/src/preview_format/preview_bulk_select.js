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
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();

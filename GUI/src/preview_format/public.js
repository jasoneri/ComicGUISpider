(() => {
  const DIALOG_OPEN_CLASS = 'is-open';
  const DIALOG_SHOW_EVENT = 'preview-dialog:show';
  const DIALOG_HIDE_EVENT = 'preview-dialog:hide';
  const TOAST_VISIBLE_CLASS = 'is-visible';
  const ESCAPE_MAP = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'};

  function reflowPreviewBadges() {
    document.querySelectorAll('.demo-badge-group').forEach((group) => {
      if (!group.children.length) {
        group.remove();
      }
    });
  }

  window.get_curr_hml = function() {
    return document.documentElement.outerHTML;
  };

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ESCAPE_MAP[char]);
  }

  function toggleBodyDialogState() {
    document.body.classList.toggle(
      'preview-dialog-open',
      Boolean(document.querySelector(`.preview-dialog.${DIALOG_OPEN_CLASS}`))
    );
  }

  function emitDialogEvent(dialogEl, name) {
    dialogEl.dispatchEvent(new CustomEvent(name, { bubbles: true }));
  }

  const FOCUSABLE_SELECTORS = [
    'a[href]', 'button:not([disabled])', 'input:not([disabled])',
    'select:not([disabled])', 'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])', '[data-preview-dialog-close]',
  ].join(',');

  function getFocusableEls(root) {
    return Array.from(root.querySelectorAll(FOCUSABLE_SELECTORS)).filter(
      (el) => !el.closest('[hidden]') && el.offsetParent !== null
    );
  }

  function createDialogController(dialogEl) {
    if (!(dialogEl instanceof HTMLElement)) {
      return null;
    }
    if (dialogEl.__previewDialogController) {
      return dialogEl.__previewDialogController;
    }

    const panel = dialogEl.querySelector('.preview-dialog__panel');
    const closeButtons = dialogEl.querySelectorAll('[data-preview-dialog-close]');
    let openerEl = null;

    const setHidden = (hidden, eventName = null) => {
      dialogEl.hidden = hidden;
      dialogEl.setAttribute('aria-hidden', String(hidden));
      dialogEl.classList.toggle(DIALOG_OPEN_CLASS, !hidden);
      toggleBodyDialogState();
      if (eventName) {
        emitDialogEvent(dialogEl, eventName);
      }
    };

    const trapFocus = (event) => {
      const focusable = getFocusableEls(dialogEl);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey) {
        if (document.activeElement === first) { event.preventDefault(); last.focus(); }
      } else {
        if (document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };

    const onKeyDown = (event) => {
      if (event.key === 'Tab') trapFocus(event);
      if (event.key === 'Escape' && !dialogEl.hasAttribute('data-preview-static')) controller.hide();
    };

    closeButtons.forEach((button) => {
      button.addEventListener('click', () => controller.hide());
    });

    dialogEl.addEventListener('click', (event) => {
      if (event.target === dialogEl && !dialogEl.hasAttribute('data-preview-static')) {
        controller.hide();
      }
    });

    if (panel instanceof HTMLElement) {
      panel.addEventListener('click', (event) => event.stopPropagation());
    }

    const controller = {
      show(opener = null) {
        if (!dialogEl.hidden) {
          return;
        }
        openerEl = opener instanceof HTMLElement ? opener : document.activeElement;
        dialogEl.hidden = false;
        dialogEl.setAttribute('aria-hidden', 'false');
        dialogEl.addEventListener('keydown', onKeyDown);
        window.requestAnimationFrame(() => {
          dialogEl.classList.add(DIALOG_OPEN_CLASS);
          toggleBodyDialogState();
          emitDialogEvent(dialogEl, DIALOG_SHOW_EVENT);
          const first = getFocusableEls(dialogEl)[0];
          if (first) first.focus();
        });
      },
      hide() {
        if (dialogEl.hidden) {
          return;
        }
        dialogEl.removeEventListener('keydown', onKeyDown);
        const activeEl = document.activeElement;
        if (activeEl instanceof HTMLElement && dialogEl.contains(activeEl)) {
          activeEl.blur();
        }
        setHidden(true, DIALOG_HIDE_EVENT);
        if (openerEl && typeof openerEl.focus === 'function') {
          openerEl.focus();
          openerEl = null;
        }
      },
      isOpen() {
        return dialogEl.classList.contains(DIALOG_OPEN_CLASS) && !dialogEl.hidden;
      },
    };

    dialogEl.__previewDialogController = controller;
    setHidden(dialogEl.hidden);
    return controller;
  }

  function createToastController(toastEl) {
    if (!(toastEl instanceof HTMLElement)) {
      return null;
    }
    if (toastEl.__previewToastController) {
      return toastEl.__previewToastController;
    }

    toastEl.querySelectorAll('[data-preview-toast-close]').forEach((button) => {
      button.addEventListener('click', () => controller.hide());
    });

    const controller = {
      show() {
        toastEl.hidden = false;
        toastEl.classList.add(TOAST_VISIBLE_CLASS);
      },
      hide() {
        toastEl.classList.remove(TOAST_VISIBLE_CLASS);
        toastEl.hidden = true;
      },
      isOpen() {
        return toastEl.classList.contains(TOAST_VISIBLE_CLASS) && !toastEl.hidden;
      },
    };

    toastEl.__previewToastController = controller;
    if (toastEl.hidden) {
      controller.hide();
    }
    return controller;
  }

  function createQtBridgeClient({ objectName = 'bridge' } = {}) {
    let bridge = null;
    let bridgeInitPromise = null;
    let qwebchannelPromise = null;

    function isAvailable() {
      return Boolean(window.qt && window.qt.webChannelTransport);
    }

    async function ensureQWebChannel() {
      if (!isAvailable()) {
        return false;
      }
      if (typeof window.QWebChannel === 'function') {
        return true;
      }
      if (!qwebchannelPromise) {
        qwebchannelPromise = new Promise((resolve) => {
          const script = document.createElement('script');
          script.src = 'qrc:///qtwebchannel/qwebchannel.js';
          script.onload = () => resolve(typeof window.QWebChannel === 'function');
          script.onerror = () => resolve(false);
          document.head.appendChild(script);
        });
      }
      return qwebchannelPromise;
    }

    async function init() {
      if (bridge) {
        return bridge;
      }
      if (!isAvailable()) {
        return null;
      }
      if (!bridgeInitPromise) {
        bridgeInitPromise = (async () => {
          const loaded = await ensureQWebChannel();
          if (!loaded || typeof window.QWebChannel !== 'function') {
            return null;
          }
          return new Promise((resolve) => {
            new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
              bridge = channel.objects[objectName] || null;
              resolve(bridge);
            });
          });
        })();
      }
      return bridgeInitPromise;
    }

    async function waitFor(methodName, attempts = 20, delayMs = 50) {
      const candidate = await init();
      if (candidate && typeof candidate[methodName] === 'function') {
        return candidate;
      }
      for (let attempt = 0; attempt < attempts; attempt += 1) {
        if (bridge && typeof bridge[methodName] === 'function') {
          return bridge;
        }
        await new Promise((resolve) => window.setTimeout(resolve, delayMs));
      }
      return null;
    }

    return {
      isAvailable,
      init,
      waitFor,
      get bridge() {
        return bridge;
      },
    };
  }

  window.reflowPreviewBadges = reflowPreviewBadges;
  window.previewUi = {
    escapeHtml,
    createDialogController,
    createToastController,
    createQtBridgeClient,
  };
  window.scanChecked = function() {
    if (window.previewRuntime && typeof window.previewRuntime.scanChecked === 'function') {
      return window.previewRuntime.scanChecked();
    }
    return Array.from(document.querySelectorAll('input[type="checkbox"][id]'))
      .filter((checkbox) => checkbox.checked && !checkbox.disabled)
      .map((checkbox) => checkbox.id);
  };
  window.previewCommandBus = (() => {
    const handlers = new Map();
    const pending = [];
    let latestSessionId = -1;

    function tryDispatch(command) {
      const { type, sid, payload } = command;
      if (sid < latestSessionId) {
        return true;
      }
      latestSessionId = sid;
      const handler = handlers.get(type);
      if (!handler) {
        return false;
      }
      handler(payload ?? {}, command);
      return true;
    }

    function flushPending() {
      let i = 0;
      while (i < pending.length) {
        if (tryDispatch(pending[i])) {
          pending.splice(i, 1);
        } else {
          i += 1;
        }
      }
    }

    return {
      register(type, handler) {
        handlers.set(type, handler);
        if (pending.length) {
          flushPending();
        }
        return () => {
          if (handlers.get(type) === handler) {
            handlers.delete(type);
          }
        };
      },
      dispatch(command) {
        const { type, sid } = command;
        if (!Number.isFinite(sid) || sid < latestSessionId) {
          return false;
        }
        latestSessionId = sid;
        const handler = handlers.get(type);
        if (!handler) {
          pending.push(command);
          return false;
        }
        handler(command.payload ?? {}, command);
        return true;
      },
    };
  })();

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', reflowPreviewBadges, { once: true });
  } else {
    reflowPreviewBadges();
  }
})();

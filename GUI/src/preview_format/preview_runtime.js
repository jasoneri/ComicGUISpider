(() => {
  const CHECKBOX_SELECTOR = 'input[type="checkbox"][id]';
  const registry = new Map();
  const order = [];
  const lockSet = new Set();
  let extraCheckedIdsResolver = null;

  function normalizeIds(ids) {
    const seen = new Set();
    return (Array.isArray(ids) ? ids : [ids])
      .filter((id) => id !== null && id !== undefined && id !== '')
      .map((id) => String(id))
      .filter((id) => {
        if (seen.has(id)) {
          return false;
        }
        seen.add(id);
        return true;
      });
  }

  function isPreviewCheckbox(node) {
    return node instanceof HTMLInputElement && node.type === 'checkbox' && Boolean(node.id);
  }

  function escapeSelector(value) {
    if (window.CSS && typeof window.CSS.escape === 'function') {
      return window.CSS.escape(String(value));
    }
    return String(value).replace(/["\\]/g, '\\$&');
  }

  function normalizeKind(kind) {
    return kind === 'episode' ? 'episode' : 'book';
  }

  function normalizeDescriptor(raw) {
    if (!raw || raw.id === null || raw.id === undefined || raw.id === '') {
      throw new Error('previewRuntime.registerItem requires descriptor.id');
    }
    return {
      id: String(raw.id),
      kind: normalizeKind(raw.kind),
      checkboxId: raw.checkboxId === null || raw.checkboxId === undefined || raw.checkboxId === ''
        ? null
        : String(raw.checkboxId),
      parentId: raw.parentId === null || raw.parentId === undefined || raw.parentId === ''
        ? null
        : String(raw.parentId),
      scope: raw.scope ? String(raw.scope) : 'preview',
      locked: Boolean(raw.locked),
      downloaded: Boolean(raw.downloaded),
      groupIdx: raw.groupIdx === null || raw.groupIdx === undefined || raw.groupIdx === ''
        ? null
        : String(raw.groupIdx),
      meta: raw.meta && typeof raw.meta === 'object' ? { ...raw.meta } : {},
      dom: raw.dom && typeof raw.dom === 'object' ? { ...raw.dom } : {},
    };
  }

  function inferScope(checkbox) {
    if (checkbox.closest('.ags-group')) {
      return 'ags';
    }
    if (checkbox.closest('.book') || checkbox.closest('.book_with_eps')) {
      return 'clip';
    }
    return 'preview';
  }

  function inferParentId(checkbox) {
    const name = String(checkbox.name || '');
    if (name.startsWith('episode-')) {
      return name.slice('episode-'.length) || null;
    }
    if (checkbox.id.startsWith('ep')) {
      const raw = checkbox.id.slice(2);
      const dashIndex = raw.indexOf('-');
      if (dashIndex > 0) {
        return raw.slice(0, dashIndex);
      }
    }
    return null;
  }

  function inferDescriptorFromCheckbox(checkbox) {
    const id = String(checkbox.id);
    const name = String(checkbox.name || '');
    const group = checkbox.closest('.ags-group');
    return {
      id,
      kind: name.startsWith('episode-') || id.startsWith('ep') ? 'episode' : 'book',
      checkboxId: id,
      parentId: inferParentId(checkbox),
      scope: inferScope(checkbox),
      locked: checkbox.dataset.previewLocked === 'true' || checkbox.disabled,
      downloaded: false,
      groupIdx: group ? group.dataset.groupIdx || null : null,
    };
  }

  function getDescriptor(id) {
    return registry.get(String(id)) || null;
  }

  function getCheckboxForDescriptor(descriptor) {
    if (!descriptor || !descriptor.checkboxId) {
      return null;
    }
    const checkbox = document.getElementById(descriptor.checkboxId);
    return isPreviewCheckbox(checkbox) ? checkbox : null;
  }

  function findCardTarget(checkbox, label) {
    return checkbox?.closest('.preview-card, .book, .book_with_eps, .episode-item-wrap, .singal-task, article, [data-preview-item]')
      || label?.closest('.preview-card, .book, .book_with_eps, .episode-item-wrap, .singal-task, article, [data-preview-item]')
      || null;
  }

  function resolveDomTargetsByDescriptor(descriptor) {
    if (!descriptor) {
      return {
        checkbox: null,
        label: null,
        card: null,
        container: null,
        img: null,
      };
    }

    const explicit = descriptor.dom || {};
    const checkbox = explicit.checkbox || getCheckboxForDescriptor(descriptor);
    const label = explicit.label
      || (descriptor.checkboxId
        ? document.querySelector(`label[for="${escapeSelector(descriptor.checkboxId)}"]`)
        : null);
    const card = explicit.card || findCardTarget(checkbox, label);
    const container = explicit.container
      || label?.querySelector('.preview-checkbox-media')
      || card?.querySelector('.preview-checkbox-media')
      || null;
    const img = explicit.img
      || label?.querySelector('img')
      || card?.querySelector('img')
      || null;

    return {
      checkbox: isPreviewCheckbox(checkbox) ? checkbox : null,
      label: label instanceof Element ? label : null,
      card: card instanceof Element ? card : null,
      container: container instanceof Element ? container : null,
      img: img instanceof Element ? img : null,
    };
  }

  function itemTouchesRoot(root, targets) {
    if (!root || root === document) {
      return true;
    }
    return [targets.checkbox, targets.label, targets.card, targets.container, targets.img].some(
      (node) => node instanceof Node && root.contains(node)
    );
  }

  function dispatchCheckboxChange(checkbox) {
    checkbox.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function applyDownloadedPresentation(descriptor, domTargets) {
    if (!descriptor || !descriptor.downloaded) {
      return;
    }
    if (descriptor.kind === 'book') {
      if (domTargets.card) {
        domTargets.card.classList.add('preview-card-state-downloaded');
      }
      if (domTargets.container) {
        domTargets.container.classList.add('container-downloaded');
      }
      if (domTargets.img) {
        domTargets.img.classList.add('img-downloaded');
      }
      return;
    }
    if (domTargets.label) {
      domTargets.label.classList.add('episode-container-downloaded');
    }
    if (domTargets.checkbox) {
      domTargets.checkbox.classList.add('episode-container-downloaded');
    }
  }

  function applyLockState(id, options = {}) {
    const descriptor = getDescriptor(id);
    if (!descriptor) {
      return false;
    }
    const { checkbox, label } = resolveDomTargetsByDescriptor(descriptor);
    lockSet.add(descriptor.id);
    descriptor.locked = true;
    registry.set(descriptor.id, descriptor);

    if (!checkbox) {
      return true;
    }

    const dispatchChange = options.dispatchChange !== false;
    const wasChecked = checkbox.checked;

    checkbox.dataset.previewLocked = 'true';
    checkbox.disabled = true;
    checkbox.setAttribute('aria-disabled', 'true');
    if (label) {
      label.setAttribute('aria-disabled', 'true');
    }

    if (wasChecked) {
      checkbox.checked = false;
      if (dispatchChange) {
        dispatchCheckboxChange(checkbox);
      }
    }
    return true;
  }

  function registerItem(rawDescriptor) {
    const incoming = normalizeDescriptor(rawDescriptor);
    const existing = getDescriptor(incoming.id);
    const merged = existing
      ? {
          ...existing,
          ...incoming,
          meta: { ...(existing.meta || {}), ...(incoming.meta || {}) },
          dom: { ...(existing.dom || {}), ...(incoming.dom || {}) },
        }
      : incoming;

    if (!existing) {
      order.push(merged.id);
    }
    registry.set(merged.id, merged);

    if (merged.locked || merged.downloaded || lockSet.has(merged.id)) {
      applyLockState(merged.id, { dispatchChange: false });
    }
    return registry.get(merged.id);
  }

  function registerItems(descriptors) {
    return (Array.isArray(descriptors) ? descriptors : []).map((descriptor) => registerItem(descriptor));
  }

  function autoRegisterCheckboxes(root = document) {
    const targetRoot = root instanceof Element || root === document ? root : document;
    targetRoot.querySelectorAll(CHECKBOX_SELECTOR).forEach((checkbox) => {
      if (!registry.has(String(checkbox.id))) {
        registerItem(inferDescriptorFromCheckbox(checkbox));
      }
    });
  }

  function refresh(root = document) {
    const targetRoot = root instanceof Element || root === document ? root : document;
    autoRegisterCheckboxes(targetRoot);

    order.forEach((id) => {
      const descriptor = getDescriptor(id);
      if (!descriptor) {
        return;
      }
      const targets = resolveDomTargetsByDescriptor(descriptor);
      if (!itemTouchesRoot(targetRoot, targets)) {
        return;
      }
      if (descriptor.locked || descriptor.downloaded || lockSet.has(id)) {
        applyLockState(id, { dispatchChange: false });
      }
      applyDownloadedPresentation(descriptor, targets);
    });

    if (typeof window.reflowPreviewBadges === 'function') {
      window.reflowPreviewBadges();
    }
    document.dispatchEvent(new CustomEvent('preview-runtime:refresh', { detail: { root: targetRoot } }));
    return registry.size;
  }

  function resolveItem(id) {
    return getDescriptor(id);
  }

  function resolveDomTargets(id) {
    return resolveDomTargetsByDescriptor(getDescriptor(id));
  }

  function isLocked(id) {
    return lockSet.has(String(id));
  }

  function isSelectable(id) {
    const descriptor = getDescriptor(id);
    if (!descriptor) {
      return false;
    }
    const { checkbox } = resolveDomTargetsByDescriptor(descriptor);
    return Boolean(checkbox) && !checkbox.disabled && !isLocked(descriptor.id);
  }

  function getItemIds(options = {}) {
    const kind = options.kind ? normalizeKind(options.kind) : null;
    const parentId = options.parentId === undefined || options.parentId === null
      ? options.parentId
      : String(options.parentId);
    const scope = options.scope ? String(options.scope) : null;
    const selectableOnly = Boolean(options.selectableOnly);
    const checkedOnly = Boolean(options.checkedOnly);
    const requireCheckbox = Boolean(options.requireCheckbox || selectableOnly || checkedOnly);

    return order.filter((id) => {
      const descriptor = getDescriptor(id);
      if (!descriptor) {
        return false;
      }
      if (kind && descriptor.kind !== kind) {
        return false;
      }
      if (scope && descriptor.scope !== scope) {
        return false;
      }
      if (parentId !== undefined && descriptor.parentId !== parentId) {
        return false;
      }

      const { checkbox } = resolveDomTargetsByDescriptor(descriptor);
      if (requireCheckbox && !checkbox) {
        return false;
      }
      if (selectableOnly && !isSelectable(id)) {
        return false;
      }
      if (checkedOnly && !(checkbox && checkbox.checked && !checkbox.disabled && !isLocked(id))) {
        return false;
      }
      return true;
    });
  }

  function getCheckedIds(options = {}) {
    return getItemIds({ ...options, checkedOnly: true });
  }

  function setChecked(ids, checked) {
    let changed = 0;
    normalizeIds(ids).forEach((id) => {
      const descriptor = getDescriptor(id);
      if (!descriptor) {
        return;
      }
      const { checkbox } = resolveDomTargetsByDescriptor(descriptor);
      if (!checkbox) {
        return;
      }

      const nextChecked = Boolean(checked);
      if (nextChecked && !isSelectable(id)) {
        return;
      }
      if (checkbox.checked === nextChecked) {
        return;
      }

      checkbox.checked = nextChecked;
      dispatchCheckboxChange(checkbox);
      changed += 1;
    });
    return changed;
  }

  function clearChecked(ids) {
    const targetIds = ids === undefined
      ? getItemIds({ requireCheckbox: true, checkedOnly: true })
      : normalizeIds(ids);
    return setChecked(targetIds, false);
  }

  function setExtraCheckedIdsResolver(resolver) {
    extraCheckedIdsResolver = typeof resolver === 'function' ? resolver : null;
  }

  function toggleAll(ids) {
    const targetIds = normalizeIds(ids).filter((id) => isSelectable(id));
    if (targetIds.length === 0) {
      return 0;
    }
    const allChecked = targetIds.every((id) => {
      const { checkbox } = resolveDomTargetsByDescriptor(getDescriptor(id));
      return Boolean(checkbox && checkbox.checked);
    });
    return setChecked(targetIds, !allChecked);
  }

  function selectRange(ids, options = {}) {
    const targetIds = normalizeIds(ids).filter((id) => isSelectable(id));
    const total = targetIds.length;
    if (total === 0) {
      return 0;
    }

    const parsed = parseInt(options.count, 10);
    const count = Math.max(1, Math.min(Number.isFinite(parsed) ? parsed : 1, total));
    const fromEnd = Boolean(options.fromEnd);
    clearChecked(targetIds);
    const selectedIds = fromEnd
      ? targetIds.slice(total - count)
      : targetIds.slice(0, count);
    return setChecked(selectedIds, true);
  }

  function lock(ids) {
    normalizeIds(ids).forEach((id) => {
      const descriptor = getDescriptor(id);
      if (!descriptor) {
        return;
      }
      descriptor.locked = true;
      registry.set(descriptor.id, descriptor);
      applyLockState(descriptor.id);
    });
    refresh();
  }

  function markDownloaded(bookIds, episodeIds = []) {
    const normalizedBooks = normalizeIds(bookIds);
    const normalizedEpisodes = normalizeIds(episodeIds);
    const missingBooks = [];
    const missingEpisodes = [];
    const targets = [];

    normalizedBooks.forEach((id) => {
      const descriptor = getDescriptor(id);
      const domTargets = resolveDomTargetsByDescriptor(descriptor);
      if (!descriptor || descriptor.kind !== 'book' || !domTargets.checkbox || !domTargets.label) {
        missingBooks.push(id);
        return;
      }
      targets.push({ descriptor, domTargets });
    });

    normalizedEpisodes.forEach((id) => {
      const descriptor = getDescriptor(id);
      const domTargets = resolveDomTargetsByDescriptor(descriptor);
      if (!descriptor || descriptor.kind !== 'episode' || !domTargets.checkbox || !domTargets.label) {
        missingEpisodes.push(id);
        return;
      }
      targets.push({ descriptor, domTargets });
    });

    if (missingBooks.length || missingEpisodes.length) {
      throw new Error(
        `markDownload target mismatch: books=${missingBooks.join(',') || '<none>'}, `
        + `episodes=${missingEpisodes.join(',') || '<none>'}`
      );
    }

    targets.forEach(({ descriptor, domTargets }) => {
      descriptor.downloaded = true;
      registry.set(descriptor.id, descriptor);
      applyLockState(descriptor.id);
      applyDownloadedPresentation(descriptor, domTargets);
    });

    refresh();
    return document.documentElement.outerHTML;
  }

  function scanChecked() {
    const checkedIds = getCheckedIds();
    if (!extraCheckedIdsResolver) {
      return checkedIds;
    }
    const extraIds = extraCheckedIdsResolver();
    return normalizeIds(checkedIds.concat(Array.isArray(extraIds) ? extraIds : [extraIds]));
  }

  function collectSubmitPayload() {
    const episodeIds = scanChecked().filter((id) => String(id).startsWith('ep'));
    return {
      action: 'submit-download',
      bookIds: getCheckedIds({ kind: 'book' }),
      episodeIds,
    };
  }

  window.previewRuntime = {
    registerItem,
    registerItems,
    refresh,
    getItemIds,
    getCheckedIds,
    setChecked,
    clearChecked,
    setExtraCheckedIdsResolver,
    toggleAll,
    selectRange,
    lock,
    isLocked,
    isSelectable,
    resolveItem,
    resolveDomTargets,
    markDownloaded,
    scanChecked,
    collectSubmitPayload,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => refresh(), { once: true });
  } else {
    refresh();
  }
})();

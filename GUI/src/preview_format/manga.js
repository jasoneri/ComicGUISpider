(() => {
  const EpisodePreviewBase = window.previewUi && window.previewUi.EpisodePreviewBase;
  if (!EpisodePreviewBase) {
    throw new Error('preview episode base is not ready');
  }

  class MangaPreviewApp extends EpisodePreviewBase {
    init() {
      this.registerBaseWindowApi();
      this.bindBaseDocumentEvents();
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => this.onDomReady(), { once: true });
        return;
      }
      this.onDomReady();
    }

    onDomReady() {
      this.onDomReadyBase();
      this.initDragSelect();
    }

    isStandalonePreviewMode() {
      return !this.bridgeClient.isAvailable();
    }

    initDragSelect() {
      let dragging = false;
      let wasDragging = false;
      let startX = 0;
      let startY = 0;

      const style = document.createElement('style');
      style.textContent = `
      #dragSelOverlay {
        position: fixed;
        pointer-events: none;
        z-index: 9999;
        display: none;
        box-sizing: border-box;
        border: 2px dashed var(--preview-accent);
        border-radius: 18px;
        background: rgba(var(--preview-accent-rgb), 0.12);
      }
      body.drag-selecting,
      body.drag-selecting * {
        user-select: none !important;
        -webkit-user-select: none !important;
        cursor: crosshair !important;
      }`;
      document.head.appendChild(style);

      const overlay = document.createElement('div');
      overlay.id = 'dragSelOverlay';
      document.body.appendChild(overlay);

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
    }

    getImmediateEpisodes(bookKey, title) {
      const cached = super.getImmediateEpisodes(bookKey, title);
      if (cached) {
        return cached;
      }
      if (!this.isStandalonePreviewMode()) {
        return null;
      }
      const cacheKey = String(bookKey);
      const dataset = window.__MANGA_PREVIEW_BROWSER_DATA__;
      const episodes = dataset && Array.isArray(dataset[cacheKey])
        ? dataset[cacheKey]
        : this.generateStandaloneEpisodes(cacheKey, title);
      this.episodesCache.set(cacheKey, episodes);
      return episodes;
    }

    generateStandaloneEpisodes(bookKey, title) {
      const seedText = `${bookKey}:${title || ''}`;
      const seed = Array.from(seedText).reduce((sum, char) => sum + char.charCodeAt(0), 0);
      const total = 42 + (seed % 84);
      const topics = [
        '序章', '相遇', '分歧', '夜色试炼', '推进线', '高压对峙', '回收节点', '隐藏支线', '后日谈', '特别篇',
      ];
      return Array.from({ length: total }, (_, index) => {
        const idx = index + 1;
        const topic = topics[(seed + index) % topics.length];
        const arc = Math.floor(index / topics.length) + 1;
        const suffix = arc > 1 ? ` / 篇章 ${arc}` : '';
        return {
          idx,
          name: `第${idx}话 ${topic}${suffix}`,
        };
      });
    }
  }

  new MangaPreviewApp().init();
})();

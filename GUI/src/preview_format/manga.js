(() => {
  const EpisodePreviewBase = window.previewUi && window.previewUi.EpisodePreviewBase;
  const previewCommandBus = window.previewCommandBus;
  if (!EpisodePreviewBase) {
    throw new Error('preview episode base is not ready');
  }
  if (!previewCommandBus) {
    throw new Error('previewCommandBus is not ready');
  }

  class MangaPreviewApp extends EpisodePreviewBase {
    init() {
      this.initFavoriteFeature();
      this.registerCommandHandlers();
      this.bindBaseDocumentEvents();
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => this.onDomReady(), { once: true });
        return;
      }
      this.onDomReady();
    }

    initFavoriteFeature() {
      if (typeof MangaFavoriteFeature === 'function') {
        this.favoriteFeature = new MangaFavoriteFeature(this.bridgeClient);
        this.favoriteFeature.init();
      }
    }

    registerCommandHandlers() {
      super.registerCommandHandlers();
      previewCommandBus.register('manga.favorite.state', ({ bookKey, isFavorited }) => {
        if (this.favoriteFeature) {
          this.favoriteFeature.updateFavoriteState(bookKey, Boolean(isFavorited));
        }
      });
      previewCommandBus.register('manga.favorites.sync', ({ bookKeys }) => {
        if (this.favoriteFeature) {
          this.favoriteFeature.initFavoriteStates(Array.isArray(bookKeys) ? bookKeys : []);
        }
      });
    }

    onDomReady() {
      this.onDomReadyBase();
    }

    isStandalonePreviewMode() {
      return !this.bridgeClient.isAvailable();
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

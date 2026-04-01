(() => {
  "use strict";

  class MangaFavoriteFeature {
    constructor(bridgeClient) {
      this.bridgeClient = bridgeClient;
      this._eventHandlers = {
        onFavoriteClick: null,
        onFavoriteKeydown: null,
      };
    }

    init() {
      this._eventHandlers.onFavoriteClick = (event) => this.onFavoriteClick(event);
      this._eventHandlers.onFavoriteKeydown = (event) => this.onFavoriteKeydown(event);

      document.addEventListener('click', this._eventHandlers.onFavoriteClick, true);
      document.addEventListener('keydown', this._eventHandlers.onFavoriteKeydown, true);
    }

    destroy() {
      if (this._eventHandlers.onFavoriteClick) {
        document.removeEventListener('click', this._eventHandlers.onFavoriteClick, true);
      }
      if (this._eventHandlers.onFavoriteKeydown) {
        document.removeEventListener('keydown', this._eventHandlers.onFavoriteKeydown, true);
      }
    }

    getFavoriteButton(target) {
      return target instanceof Element ? target.closest('.card-favorite-btn[data-book-key]') : null;
    }

    async toggleFavorite(button) {
      if (!button) {
        return;
      }
      const key = String(button.dataset.bookKey || '');
      const bridge = this.bridgeClient.bridge || await this.bridgeClient.waitFor('toggleFavorite');
      if (bridge && typeof bridge.toggleFavorite === 'function') {
        bridge.toggleFavorite(key);
      }
    }

    async onFavoriteClick(event) {
      const button = this.getFavoriteButton(event.target);
      if (!button) {
        return;
      }
      event.stopPropagation();
      event.preventDefault();
      await this.toggleFavorite(button);
    }

    onFavoriteKeydown(event) {
      const button = this.getFavoriteButton(event.target);
      if (!button) {
        return;
      }
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        button.click();
      }
    }

    updateFavoriteState(key, isFavorited) {
      const button = document.querySelector(`.card-favorite-btn[data-book-key="${key}"]`);
      if (!button) {
        return;
      }
      const input = button.querySelector('.card-favorite-input');
      if (input) {
        input.checked = isFavorited;
      }
      button.classList.toggle('is-favorited', isFavorited);
      button.setAttribute('aria-pressed', String(isFavorited));
    }

    initFavoriteStates(keys) {
      const buttons = Array.from(document.querySelectorAll('.card-favorite-btn'));
      buttons.forEach((button) => {
        button.classList.add('is-syncing');
        this.updateFavoriteState(button.dataset.bookKey, false);
      });
      if (Array.isArray(keys)) {
        keys.forEach((key) => this.updateFavoriteState(key, true));
      }
      window.requestAnimationFrame(() => {
        buttons.forEach((button) => button.classList.remove('is-syncing'));
      });
    }
  }

  window.MangaFavoriteFeature = MangaFavoriteFeature;
})();

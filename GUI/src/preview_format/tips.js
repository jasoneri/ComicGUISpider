// tip_downloaded.js - 下载状态标记系统
(() => {
  const MARK_RETRY_DELAY_MS = 100;
  const MAX_MARK_ATTEMPTS = 40;

  // 动态注入样式
  const style = document.createElement('style');
  style.textContent = `
        .img-downloaded {
            filter: grayscale(100%) !important;
            opacity: 0.6 !important;
            transition: all 0.3s ease;
        }
        .container-downloaded {
            background-color: lightsalmon !important;
        }
        .episode-downloaded {
            filter: grayscale(100%) !important;
            opacity: 0.6 !important;
            transition: all 0.3s ease;
        }
        .episode-container-downloaded {
            background-color: lightsalmon !important;
            opacity: 1 !important;
        }
  `;
  document.head.appendChild(style);

  // 存储下载状态的回调函数
  window.downloadStatusCallbacks = [];

  // 注册下载状态回调
  window.registerDownloadCallback = function(callback) {
    window.downloadStatusCallbacks.push(callback);
  };

  function normalizeIds(ids) {
    return (Array.isArray(ids) ? ids : [])
      .filter((id) => id !== null && id !== undefined && id !== '')
      .map((id) => String(id));
  }

  function getBookLabel(id) {
    return document.querySelector(`label[for="${id}"]`);
  }

  function getBookCheckbox(id) {
    return document.getElementById(id);
  }

  function getEpisodeCheckbox(id) {
    return document.getElementById(id);
  }

  function getEpisodeLabel(id) {
    return document.querySelector(`label[for="${id}"]`);
  }

  function disableSelection(checkbox, label) {
    if (!checkbox) {
      return;
    }
    checkbox.checked = false;
    checkbox.disabled = true;
    checkbox.setAttribute("aria-disabled", "true");
    if (label) {
      label.setAttribute("aria-disabled", "true");
    }
  }

  function hasPendingTargets(bookIds, episodeIds) {
    return bookIds.some((id) => !getBookLabel(id) || !getBookCheckbox(id))
      || episodeIds.some((id) => !getEpisodeCheckbox(id) || !getEpisodeLabel(id));
  }

  // Python端调用的重试函数
  window.tryMarkDownload = function(downloadedIdxes, downloadedEpisodeIdxes = []) {
    const bookIds = normalizeIds(downloadedIdxes);
    const episodeIds = normalizeIds(downloadedEpisodeIdxes);
    let attempts = 0;

    function tryMark() {
      attempts++;

      if (typeof window.markDownload !== 'function') {
        if (attempts < MAX_MARK_ATTEMPTS) {
          setTimeout(tryMark, MARK_RETRY_DELAY_MS);
          return false;
        }
        throw new Error(`markDownload is not ready after ${MAX_MARK_ATTEMPTS} attempts`);
      }

      if (hasPendingTargets(bookIds, episodeIds)) {
        if (attempts < MAX_MARK_ATTEMPTS) {
          setTimeout(tryMark, MARK_RETRY_DELAY_MS);
          return false;
        }
        throw new Error(
          `markDownload targets missing after ${MAX_MARK_ATTEMPTS} attempts: `
          + `books=${bookIds.join(',') || '<none>'}, episodes=${episodeIds.join(',') || '<none>'}`
        );
      }

      window.markDownload(bookIds, episodeIds);
      return true;
    }

    tryMark();
    return document.documentElement.outerHTML;
  };

  // 标记下载状态的主函数
  window.markDownload = function(downloadedIdxes, downloadedEpisodeIdxes = []) {
    const bookIds = normalizeIds(downloadedIdxes);
    const episodeIds = normalizeIds(downloadedEpisodeIdxes);
    const missingBooks = [];
    const missingEpisodes = [];

    bookIds.forEach((id) => {
      const label = getBookLabel(id);
      const checkbox = getBookCheckbox(id);
      if (!label || !checkbox) {
        missingBooks.push(id);
        return;
      }
      disableSelection(checkbox, label);
      const card = checkbox.closest('.preview-card-shell');
      if (card) {card.classList.add('preview-card-state-downloaded');}
      const container = label.querySelector('.preview-checkbox-media');
      if (container) {container.classList.add('container-downloaded');}
      const img = label.querySelector('img');
      if (img) {img.classList.add('img-downloaded');}
    });

    // 处理episodes的下载状态（基于bid值）
    episodeIds.forEach((id) => {
      const episodeElement = getEpisodeCheckbox(id);
      const label = getEpisodeLabel(id);
      if (!episodeElement || !label) {
        missingEpisodes.push(id);
        return;
      }
      disableSelection(episodeElement, label);
      label.classList.add('episode-container-downloaded');
      episodeElement.classList.add('episode-container-downloaded');
    });

    if (missingBooks.length || missingEpisodes.length) {
      throw new Error(
        `markDownload target mismatch: books=${missingBooks.join(',') || '<none>'}, `
        + `episodes=${missingEpisodes.join(',') || '<none>'}`
      );
    }

    // 执行所有注册的回调函数
    let firstError = null;
    window.downloadStatusCallbacks.forEach((callback) => {
      try {
        callback(bookIds, episodeIds);
      } catch (error) {
        console.error('downloadStatus callback failed', error);
        if (!firstError) {
          firstError = error;
        }
      }
    });
    if (firstError) {
      throw firstError;
    }
  };
})();

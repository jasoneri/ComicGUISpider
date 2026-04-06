(() => {
  const MARK_RETRY_DELAY_MS = 100;
  const MAX_MARK_ATTEMPTS = 40;

  function normalizeIds(ids) {
    return (Array.isArray(ids) ? ids : [])
      .filter((id) => id !== null && id !== undefined && id !== '')
      .map((id) => String(id));
  }

  function getRuntime() {
    if (!window.previewRuntime) {
      throw new Error('previewRuntime is not ready');
    }
    return window.previewRuntime;
  }

  function hasPendingTargets(runtime, bookIds, episodeIds) {
    return [...bookIds, ...episodeIds].some((id) => {
      const item = runtime.resolveItem(id);
      if (!item) {
        return true;
      }
      const { checkbox, label } = runtime.resolveDomTargets(id);
      return !checkbox || !label;
    });
  }

  window.tryMarkDownload = function(downloadedIdxes, downloadedEpisodeIdxes = []) {
    const bookIds = normalizeIds(downloadedIdxes);
    const episodeIds = normalizeIds(downloadedEpisodeIdxes);
    let attempts = 0;

    function tryMark() {
      attempts += 1;

      if (!window.previewRuntime) {
        if (attempts < MAX_MARK_ATTEMPTS) {
          setTimeout(tryMark, MARK_RETRY_DELAY_MS);
          return false;
        }
        throw new Error(`previewRuntime is not ready after ${MAX_MARK_ATTEMPTS} attempts`);
      }

      const runtime = getRuntime();
      if (hasPendingTargets(runtime, bookIds, episodeIds)) {
        if (attempts < MAX_MARK_ATTEMPTS) {
          setTimeout(tryMark, MARK_RETRY_DELAY_MS);
          return false;
        }
        throw new Error(
          `markDownload targets missing after ${MAX_MARK_ATTEMPTS} attempts: `
          + `books=${bookIds.join(',') || '<none>'}, episodes=${episodeIds.join(',') || '<none>'}`
        );
      }

      runtime.markDownloaded(bookIds, episodeIds);
      return true;
    }

    tryMark();
    return document.documentElement.outerHTML;
  };

  window.markDownload = function(downloadedIdxes, downloadedEpisodeIdxes = []) {
    const runtime = getRuntime();
    const bookIds = normalizeIds(downloadedIdxes);
    const episodeIds = normalizeIds(downloadedEpisodeIdxes);
    return runtime.markDownloaded(bookIds, episodeIds);
  };
})();

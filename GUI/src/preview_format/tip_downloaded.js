// tip_downloaded.js - 下载状态标记系统
(() => {
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

  // Python端调用的重试函数
  window.tryMarkDownloadStatus = function(downloadedUrls, downloadedEpisodeBids = []) {
    let attempts = 0;
    const maxAttempts = 10;

    function tryMark() {
      attempts++;
      if (window.markDownloadStatus) {
        window.markDownloadStatus(downloadedUrls, downloadedEpisodeBids);
        return true;
      } else {
        if (attempts < maxAttempts) {
          setTimeout(tryMark, 100);
        } else {
          console.error(`Failed to find markDownloadStatus after ${maxAttempts} attempts`);
        }
        return false;
      }
    }

    tryMark();
    return document.documentElement.outerHTML;
  };

  // 标记下载状态的主函数
  window.markDownloadStatus = function(downloadedUrls, downloadedEpisodeBids = []) {
    // 处理普通任务的下载状态
    downloadedUrls.forEach(url => {
      const urlElement = document.querySelector(`a[href="${url}"]`);
      if (urlElement) {
        urlElement.classList.add('downloaded');
        const container = urlElement.closest('.singal-task');
        if (container) {
          const formCheck = container.querySelector('.form-check');
          formCheck ? formCheck.classList.add('container-downloaded') : container.classList.add('container-downloaded');
          const img = container.querySelector('img');
          if (img) img.classList.add('img-downloaded');
        }
      } 
    });

    // 处理episodes的下载状态（基于bid值）
    downloadedEpisodeBids.forEach(bid => {
      const episodeElement = document.querySelector(`input[class="btn-check"][value="${bid}"]`);
      const label = document.querySelector(`label[for="${episodeElement.id}"]`);
      label.classList.add('episode-container-downloaded');
      episodeElement.classList.add('episode-container-downloaded');
    });

    // 执行所有注册的回调函数
    window.downloadStatusCallbacks.forEach(callback => {
      try {
        callback(downloadedUrls, downloadedEpisodeBids);
      } catch (e) {
      }
    });
  };
})();

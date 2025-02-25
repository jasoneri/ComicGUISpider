// task-panel.js
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
  `;
  document.head.appendChild(style);
  
  function highlightDownloads() {
    document.querySelectorAll('a.downloaded').forEach(url_a => {
      const container = url_a.closest('.singal-task');
      const formCheck = container.querySelector('.form-check');
      formCheck ?  formCheck.classList.add('container-downloaded') : container.classList.add('container-downloaded');
      container.querySelector('img').classList.add('img-downloaded');
    });
  }

  document.addEventListener('DOMContentLoaded', highlightDownloads);
  const observer = new MutationObserver((mutations) => {
    mutations.forEach(mutation => {
      if (mutation.addedNodes.length) {
        highlightDownloads();
      }
    });
  });
  observer.observe(document.body, {
    childList: true,
    subtree: true
  });
})();

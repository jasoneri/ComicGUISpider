(() => {
  const TOAST_ID = "cgsTaskAddedToast";
  const TOAST_TITLE_CLASS = "cgs-task-toast-title";
  const TOAST_SUBTITLE_CLASS = "cgs-task-toast-subtitle";
  const TOAST_SUBTITLE = "在主界面任务栏查看详细进度";
  let removeTimer = null;

  function removeToast() {
    const toast = document.getElementById(TOAST_ID);
    if (toast) {
      toast.remove();
    }
    if (removeTimer) {
      clearTimeout(removeTimer);
      removeTimer = null;
    }
  }

  window.showTaskAddedToast = function (title) {
    removeToast();
    const toast = document.createElement("div");
    const titleEl = document.createElement("div");
    const subtitleEl = document.createElement("div");

    toast.id = TOAST_ID;
    titleEl.className = TOAST_TITLE_CLASS;
    subtitleEl.className = TOAST_SUBTITLE_CLASS;
    titleEl.textContent = `“${title}”已加入任务列表`;
    subtitleEl.textContent = TOAST_SUBTITLE;

    toast.appendChild(titleEl);
    toast.appendChild(subtitleEl);
    document.body.appendChild(toast);

    removeTimer = window.setTimeout(removeToast, 4000);
  };
})();

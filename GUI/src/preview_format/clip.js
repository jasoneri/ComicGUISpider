// clip.js - 动态注入模式
(() => {
  let taskCount = 0;

  // 获取maxTasks值
  function getMaxTasks() {
    return window.CLIP_MAX_TASKS || 0;
  }

  // Selected对象定义
  class Selected {
    constructor(taskId, episodeBid = null, episodeName = null, episodeIdx = null) {
      this.taskId = taskId;
      this.episodeBid = episodeBid;
      this.episodeName = episodeName;
      this.episodeIdx = episodeIdx;
      this.isEpisode = episodeBid !== null;
    }
    get uniqueId() {
      return this.isEpisode ? `${this.taskId}-${this.episodeIdx}` : `${this.taskId}`;
    }
    get checkboxName() {
      return this.isEpisode ? `episode-${this.taskId}` : 'img';
    }
    get checkboxValue() {
      return this.isEpisode ? this.episodeBid : '';
    }
  }

  window.addEL = function(idx, url, img_src, title, author, pages, tags, episodes) {
    let selectedObjects = [];
    if (episodes && episodes.length > 0) {
      for (let i = 0; i < episodes.length; i++) {
        const ep = episodes[i];
        selectedObjects.push(new Selected(idx, ep.bid, ep.ep, ep.idx));
      }
    } else {
      selectedObjects.push(new Selected(idx));
    }
    if (!window.selectedObjectsMap) {
      window.selectedObjectsMap = new Map();
    }
    window.selectedObjectsMap.set(idx, selectedObjects);

    // 3. 生成HTML片段，支持两种页面结构：带分话的 `book_with_eps` 和 普通 `book`
    const parentElement = document.querySelector('.container-fluid');
    const progressBar = document.getElementById('progress-bar');

    if (episodes && episodes.length > 0) {
      // 生成 book_with_eps 结构（带 episodes grid）
      let html = `
      <div class="book_with_eps">
        <div class="col-11 singal-task">
          <div class="thumbnail-container"><label class="form-check-label" for="${idx}" style="height: 100%">
            <img src="${img_src}" title="${title}" alt="${title}" class="img-thumbnail">
          </label></div>
          <ul style="margin: 15px;">
            <li class="text-truncate"><a href="${url}"><span class="title">${title}</span></a></li>
            <li><span class="author">${author}</span></li>
            <li><span class="pages">${pages}pages</span></li>
            <li>`;

      if (Array.isArray(tags)) {
        for (let i = 0; i < tags.length; i++) {
          html += `<span class="tag">${tags[i]}</span> `;
        }
      }

      html += `</li></ul>
        </div>
        <div class="episodes-container">
          <div class="episodes-grid">
            <button type="button" class="btn btn-outline-primary btn-sm" onclick="toggleAllEpisodes(${idx})">全选切换</button>`;

      // 生成每个 episode 的 input+label
      for (let i = 0; i < selectedObjects.length; i++) {
        const s = selectedObjects[i];
        // 保持 id 格式为 `${idx}-${episodeIdx}`，value 为 episodeBid，label 文本为 episodeName
        html += `
            <input class="btn-check" type="checkbox" name="${s.checkboxName}" value="${s.checkboxValue}" id="${s.uniqueId}" checked autocomplete="off">
            <label class="btn btn-outline-primary" for="${s.uniqueId}" style="height: 85%;">${s.episodeName}</label>`;
      }

      html += `
          </div>
        </div>
      </div>`;

      parentElement.insertAdjacentHTML('beforeend', html);
    } else {
      // 生成 book 结构（单个作品，无分话）
      const selected = selectedObjects[0];
      let html = `
      <div class="book">
        <div class="col-11 singal-task">
          <div class="thumbnail-container"><label class="form-check-label" for="${idx}" style="height: 100%">
            <img src="${img_src}" title="${title}" alt="${title}" class="img-thumbnail">
          </label></div>
          <ul style="list-style:none">
            <li class="text-truncate"><a href="${url}"><span class="title">${title}</span></a></li>
            <li><span class="author">${author}</span></li>
            <li><span class="pages">${pages}pages</span></li>
            <li>`;

      if (Array.isArray(tags)) {
        for (let i = 0; i < tags.length; i++) {
          html += `<span class="tag">${tags[i]}</span> `;
        }
      }

      html += `</li></ul>
        </div>
        <label class="right-checkbox">
          <input class="form-check-input" type="checkbox" name="${selected.checkboxName}" value="${selected.checkboxValue}" id="${selected.uniqueId}" checked>
        </label>
      </div>`;

      parentElement.insertAdjacentHTML('beforeend', html);
    }

    taskCount++;
    const currentMaxTasks = getMaxTasks();
    if (taskCount >= currentMaxTasks) {
      progressBar.style.width = `100%`;
      progressBar.setAttribute('aria-valuenow', "100");
      progressBar.className = "progress-bar bg-success"
      progressBar.innerText = "100% Completed"
    } else {
      const progressPercent = Math.round((taskCount / currentMaxTasks) * 100);
      progressBar.style.width = `${progressPercent}%`;
      progressBar.setAttribute('aria-valuenow', String(progressPercent));
    }
  };

  // 暴露其他函数到全局作用域
  window.toggleAllEpisodes = function(taskIdx) {
    const episodeCheckboxes = document.querySelectorAll(`input[name="episode-${taskIdx}"]`);
    const allChecked = Array.from(episodeCheckboxes).every(cb => cb.checked);
    episodeCheckboxes.forEach(cb => cb.checked = !allChecked);
  };

  window.checkDoneTasks = function() {
    const El = document.querySelectorAll(".book, .book_with_eps");
    return El.length;
  };

  window.finishTasks = function() {
    var modal = bootstrap.Modal.getInstance(document.getElementById('myModal'));
    if (modal) {
      modal.hide();
    }
    return document.documentElement.outerHTML;
  };

})();

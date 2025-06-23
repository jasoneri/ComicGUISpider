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

    // 3. 生成HTML片段
    const htmlString1 = `
      <div class="list-group-item"><div class="row g-1">
        <div class="col-11 singal-task">
            <div class="thumbnail-container"><label class="form-check-label" for="${idx}" style="height: 100%">
                <img src="${img_src}" title="${title}" alt="${title}" class="img-thumbnail">
            </label></div>
            <ul style="list-style:none">
                <li class="text-truncate"><a href="${url}"><span class="title">${title}</span></a></li>
                <li><span class="author">${author}</span></li>
                <li><span class="pages">${pages}pages</span></li>`;

    let tags_html = `<li>`;
    for (let i = 0; i < tags.length; i++) {
      tags_html += `<span class="tag">${tags[i]}</span> `;
    }
    tags_html += `</li></ul>
            </div>`;

    let episodes_html = '';
    let endingTags = '';

    if (episodes && episodes.length > 0) {
      // 有episodes：生成episodes选择界面，与col-11同级
      episodes_html = `
        <div class="col-12">
          <div class="episodes-section">
            <div class="episodes-list row" id="episodes-${idx}">
              <div class="col-auto">
                <button type="button" class="btn btn-outline-primary btn-sm" style="height: 85%;" onclick="toggleAllEpisodes(${idx})">全选切换</button>
              </div>`;

      for (let i = 0; i < selectedObjects.length; i++) {
        const selected = selectedObjects[i];
        episodes_html += `
              <div class="col-auto">
                <input class="btn-check" type="checkbox" name="${selected.checkboxName}" value="${selected.checkboxValue}"
                    id="${selected.uniqueId}" checked autocomplete="off">
                <label class="btn btn-outline-primary" for="${selected.uniqueId}" style="height: 85%;">${selected.episodeName}</label>
              </div>`;
      }
      episodes_html += `
            </div>
          </div>
        </div>`;

      // 有episodes时不需要主input
      endingTags = `
        <div class="col-1"></div>
    </div></div>`;
    } else {
      // 没episodes：生成主选择框
      const selected = selectedObjects[0];
      endingTags = `
        <div class="col-1"><div class="checkbox checkbox-div"><label style="width: 50%;height: 95%;float: right;">
            <input class="form-check-input" type="checkbox"
                   name="${selected.checkboxName}"
                   value="${selected.checkboxValue}"
                   id="${selected.uniqueId}" checked>
        </label></div></div>
    </div></div>`;
    }

    const parentElement = document.querySelector(".list-group");
    const progressBar = document.getElementById('progress-bar');

    parentElement.insertAdjacentHTML('beforeend', htmlString1 + tags_html + episodes_html + endingTags);

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
    const El = document.querySelectorAll(".list-group-item");
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

// task-panel.js
(() => {
  // 动态注入样式
  const style = document.createElement('style');
  style.textContent = `
        /* 分界线样式 */
        #panelDivider {
            margin: 1rem 0;
            border-width: 2px;
            border-color: #0d6efd;
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        #panelDivider.visible {
            opacity: 1;
        }
        #taskPanel {
            max-height: 300px;
            overflow-y: auto;
            transition: all 0.3s ease;
            margin-bottom: 15px;
            box-shadow: 0 -2px 5px rgba(0,0,0,0.1); /* 投影增强层次 */
            direction: rtl;  /* 滚动条左侧 */
        }
        #taskContainer {
            direction: ltr;
        }
        /* 滚动条样式 */
        #taskPanel::-webkit-scrollbar {
            width: 8px;
            background: #f1f1f1;
        }
        #taskPanel::-webkit-scrollbar-thumb {
            background: #888;
            border-radius: 4px;
        }
        #taskPanel::-webkit-scrollbar-thumb:hover {
            background: #555;
        }
        @supports (scrollbar-width: thin) {
            #taskPanel {
                scrollbar-width: thin;
                scrollbar-color: #888 #f1f1f1;
            }
        }
        /* 进度条完成 */
        .completed .progress-bar {
            background-color: #198754 !important;
        }
        /* 任务项样式 */
        .task-item {
            padding: 12px;
            border-bottom: 1px solid #dee2e6;
        }
        .task-progress {
            height: 20px;
            margin-top: 8px;
        }
        .task-count {
            font-family: monospace;
            font-size: 0.85em;
            color: #6c757d;
        }
    `;
  document.head.appendChild(style);

  // 初始化任务面板
  window.initTaskPanel = function () {
    // function initTaskPanel() {
    // 创建容器
    const container = document.createElement('div');
    container.innerHTML = `
            <button class="btn btn-primary w-100 mb-2" 
                    type="button" 
                    data-bs-toggle="collapse" 
                    data-bs-target="#taskPanel"
                    aria-expanded="true">
                Hide tasks(<span id="taskCounter">0</span>)
            </button>
            <div class="collapse show" id="taskPanel">
                <div class="card card-body pb-2" id="taskContainer"></div>
            </div>
        `;
    // 插入分隔线
    const divider = document.createElement('hr');
    divider.id = 'panelDivider';
    document.body.insertAdjacentElement('afterbegin', container);
    container.insertAdjacentElement('afterend', divider);
    // 事件监听
    const taskPanel = document.getElementById('taskPanel');
    const counterBtn = container.querySelector('button');
    if (taskPanel.classList.contains('show')) {
      divider.classList.add('visible');
      requestAnimationFrame(autoScroll);
    }
    taskPanel.addEventListener('shown.bs.collapse', () => {
      counterBtn.innerHTML = `Hide tasks (<span id="taskCounter">${taskCounter()}</span>)`;
      divider.classList.add('visible');
      autoScroll(); // 展开时自动滚动
    });
    taskPanel.addEventListener('hidden.bs.collapse', () => {
      counterBtn.innerHTML = `Show tasks (<span id="taskCounter">${taskCounter()}</span>)`;
      divider.classList.remove('visible');
    });
    window.scrollTo({top: 0, behavior: 'smooth'});
  }

  // 自动滚动优化
  function autoScroll() {
    const panel = document.getElementById('taskPanel');
    panel.scrollTo({
      top: panel.scrollHeight,
      behavior: 'smooth'
    });
  }

  // 添加任务
  window.addTask = function (uuid, title, task_count, title_url) {
    const container = document.getElementById('taskContainer');
    // if (document.getElementById(uuid)) return;
    const initialProgress = 0;
    const task = document.createElement('div');
    task.className = 'task-item';
    task.id = `task-${uuid}`;
    task.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <a href="${title_url}">
                    <span class="fw-bold">${title}</span></a>
                <small class="task-count">page: ${task_count}</small>
            </div>
            <div class="progress task-progress">
                <div class="progress-bar" 
                    role="progressbar" 
                    style="width: ${initialProgress}%" 
                    aria-valuenow="${initialProgress}" 
                    aria-valuemin="0" 
                    aria-valuemax="100">
                    ${initialProgress}%
                </div>
            </div>
        `;

    container.appendChild(task);
    updateCounter();
    // 自动滚动逻辑
    const panel = document.getElementById('taskPanel');
    if (panel.classList.contains('show')) {
      requestAnimationFrame(autoScroll);
    }
  }
  // 更新子任务进度
  window.updateTaskProgress = function (uuid, progress) {
    const task = document.getElementById(`task-${uuid}`);
    if (!task) return;

    const progressBar = task.querySelector('.progress-bar');
    // const progressText = task.querySelector('small');
    progressBar.style.width = `${progress}%`;
    progressBar.textContent = `${progress}%`;
    progressBar.ariaValuenow = progress;
    if (progress >= 100) {
      task.classList.add('completed');
      progressBar.textContent = '100% Completed';
    }
  }

  // 更新计数器
  function taskCounter() {
    return document.querySelectorAll('#taskContainer > .task-item').length;
  }

  function updateCounter() {
    document.querySelectorAll('#taskCounter').forEach(el => {
      el.textContent = taskCounter();
    });
  }

  // 初始化
  // document.addEventListener('DOMContentLoaded', initTaskPanel);
})();

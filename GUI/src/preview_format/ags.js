(() => {
  let bookCount = 0;
  // todo[0] badge可不止一个，我自己手动做，ai别碰！
  const BADGE_ICON = '<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="M4 3.75A1.75 1.75 0 0 1 5.75 2h8.5A1.75 1.75 0 0 1 16 3.75v12.5a.75.75 0 0 1-1.18.616L10 13.607l-4.82 3.259A.75.75 0 0 1 4 16.25V3.75Z"/></svg>';
  const ESCAPE_MAP = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  };

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ESCAPE_MAP[char]);
  }

  function buildBadgeGroups(options) {
    const bottomBadges = [];
    const topBadges = [];

    if (options.likes) {
      bottomBadges.push(
        `<span class="demo-badge demo-badge-likes">${BADGE_ICON}<span class="demo-badge-label">${escapeHtml(options.likes)}</span></span>`
      );
    }
    if (options.pages) {
      bottomBadges.push(
        `<span class="demo-badge demo-badge-pages">${BADGE_ICON}<span class="demo-badge-label">p${escapeHtml(options.pages)}</span></span>`
      );
    }
    if (options.lang) {
      const text = escapeHtml(options.lang);
      topBadges.push(`<span class="demo-badge demo-badge-light demo-badge-lang" title="${text}">${text}</span>`);
    }
    if (options.btype) {
      const text = escapeHtml(options.btype);
      topBadges.push(`<span class="demo-badge demo-badge-light demo-badge-btype" title="${text}">${text}</span>`);
    }

    let html = '';
    if (bottomBadges.length) {
      html += `<div class="demo-badge-group demo-badge-group-bottom">${bottomBadges.join('')}</div>`;
    }
    if (topBadges.length) {
      html += `<div class="demo-badge-group demo-badge-group-top">${topBadges.join('')}</div>`;
    }
    return html;
  }

  window.addAgsEL = function(idx, img_src, title, url, options = {}) {
    const isDownloaded = options.flag === 'downloaded';
    const disabledAttr = isDownloaded ? ' disabled aria-disabled="true"' : '';
    const labelDisabledAttr = isDownloaded ? ' aria-disabled="true"' : '';
    const cardStateClass = isDownloaded ? ' preview-card-state-downloaded' : '';
    const mediaStateClass = isDownloaded ? ' container-downloaded' : '';
    const imageStateClass = isDownloaded ? ' img-downloaded' : '';
    const safeIdx = escapeHtml(idx);
    const safeTitle = escapeHtml(title);
    const safeUrl = escapeHtml(url);
    const safeImgSrc = escapeHtml(img_src);
    const badgesHtml = buildBadgeGroups(options);

    return `
      <div class="col-md-3 singal-task preview-card-shell${cardStateClass}">
        <div class="form-check preview-card-check">
          <input class="form-check-input preview-checkbox-input" type="checkbox" name="img" id="${safeIdx}"${disabledAttr}>
          <label class="form-check-label preview-checkbox-label" for="${safeIdx}"${labelDisabledAttr}>
            <span class="preview-checkbox-toggle" aria-hidden="true"><span class="preview-checkbox-tick"></span></span>
            <div class="preview-checkbox-media${mediaStateClass}">
              <img src="${safeImgSrc}" title="${safeTitle}" alt="${safeTitle}" class="img-thumbnail preview-card-image${imageStateClass}"/>
              ${badgesHtml}
            </div>
          </label>
        </div>
        <div class="preview-title-shell">
          <a href="${safeUrl}" title="${safeTitle}" class="preview-title-link">
            <p class="preview-title-clamp">${safeTitle}</p>
          </a>
        </div>
      </div>`;
  };

  window.addAgsGroup = function(groupIdx, books) {
    if (!books || books.length === 0) {
      console.warn(`Group ${groupIdx} has no books`);
      return;
    }

    const searchKeyword = books[0].search_keyword || `Group ${groupIdx}`;
    const safeSearchKeyword = escapeHtml(searchKeyword);

    let booksHtml = '';
    for (let i = 0; i < books.length; i++) {
      const book = books[i];
      const options = {
        pages: book.pages,
        likes: book.likes,
        lang: book.lang,
        btype: book.btype,
        flag: book.flag
      };
      booksHtml += window.addAgsEL(book.idx, book.img_src, book.title, book.url, options);
    }

    // todo[0] group 需要可折叠
    const groupHtml = `
      <div class="ags-group card mb-4" data-group-idx="${groupIdx}" data-group-keyword="${safeSearchKeyword}">
        <div class="card-header d-flex justify-content-between align-items-center">
          <h5 class="mb-0">
            <span class="badge bg-primary me-2">${groupIdx}</span>
            ${safeSearchKeyword}
            <span class="badge bg-secondary ms-2">${books.length} results</span>
          </h5>
          <button type="button" class="btn btn-sm btn-outline-primary" onclick="toggleGroupSelection(${groupIdx})">
            全选切换
          </button>
        </div>
          <div class="row">
            ${booksHtml}
          </div>
      </div>`;

    const mainContainer = document.querySelector('.list-group');
    if (mainContainer) {
      mainContainer.insertAdjacentHTML('beforeend', groupHtml);
      bookCount += books.length;
      if (typeof window.reflowPreviewBadges === 'function') {
        window.reflowPreviewBadges();
      }
    }
  };

  window.toggleGroupSelection = function(groupIdx) {
    const groupElement = document.querySelector(`.ags-group[data-group-idx="${groupIdx}"]`);
    if (!groupElement) return;

    const checkboxes = Array.from(
      groupElement.querySelectorAll('input[type="checkbox"][name="img"]')
    ).filter((checkbox) => !checkbox.disabled);
    if (checkboxes.length === 0) {
      return;
    }
    const allChecked = checkboxes.every(cb => cb.checked);

    checkboxes.forEach(cb => {
      cb.checked = !allChecked;
    });
  };

  window.checkDoneTasks = function() {
    const books = document.querySelectorAll('.singal-task');
    return books.length;
  };

  window.finishTasks = function() {
    return document.documentElement.outerHTML;
  };

})();

(() => {
  let bookCount = 0;

  window.addAgsEL = function(idx, img_src, title, url, options = {}) {
    const { pages, likes, lang, btype, flag } = options;

    const abbreviated_title = title.length > 18 ? title.substring(0, 18) + "..." : title;

    let badgesHtml = '';
    if (pages) {
      badgesHtml += `<span class="badge bg-info badge-left-bottom">p${pages}</span><br>`;
    }
    if (likes) {
      badgesHtml += `<span class="badge bg-danger badge-left-bottom">♥️${likes}</span><br>`;
    }
    if (lang) {
      badgesHtml += `<span class="badge rounded-pill bg-light text-dark badge-right-top badge-lang">${lang}</span>`;
    }
    if (btype) {
      badgesHtml += `<span class="badge bg-light text-dark badge-right-top badge-btype">${btype}</span>`;
    }

    const container_cls = flag ? ` container-${flag}` : "";
    const img_cls = flag ? ` img-${flag}` : "";

    const maxWidth = 170;
    return `
      <div class="col-md-3 singal-task" style="max-width:${maxWidth}px">
        <div class="form-check${container_cls}">
          <input class="form-check-input" type="checkbox" name="img" id="${idx}">
          <label class="form-check-label" for="${idx}">
            <div style="position: relative; display: inline-block;">
              <img src="${img_src}" title="${title}" alt="${title}" class="img-thumbnail${img_cls}"/>
              ${badgesHtml}
            </div>
          </label>
        </div>
        <a href="${url}"><p>[${idx}]、${abbreviated_title}</p></a></div>
`;
  };

  window.addAgsGroup = function(groupIdx, books) {
    if (!books || books.length === 0) {
      console.warn(`Group ${groupIdx} has no books`);
      return;
    }

    const searchKeyword = books[0].search_keyword || `Group ${groupIdx}`;

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
      <div class="ags-group card mb-4" data-group-idx="${groupIdx}" data-group-keyword="${searchKeyword}">
        <div class="card-header d-flex justify-content-between align-items-center">
          <h5 class="mb-0">
            <span class="badge bg-primary me-2">${groupIdx}</span>
            ${searchKeyword}
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
    }
  };

  window.toggleGroupSelection = function(groupIdx) {
    const groupElement = document.querySelector(`.ags-group[data-group-idx="${groupIdx}"]`);
    if (!groupElement) return;

    const checkboxes = groupElement.querySelectorAll('input[type="checkbox"][name="img"]');
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);

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

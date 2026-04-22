// ==UserScript==
// @name         cbg
// @namespace    tag:jsoneri:cbg
// @version      0.1
// @description  油猴脚本，右下角设置透明背景角色图(火狐无法用)
// @author       jsoneri
// @match        *://*/*
// @exclude      *://challenges.cloudflare.com/*
// @grant        GM_getResourceURL
// @grant        GM_addStyle
{resource-placehold}
// ==/UserScript==

(function () {
  'use strict';

  const CONFIG = {
    width: 400,
    height: 600,
    right: -20,
    bottom: 0,
    opacity: 0.75,
    zIndex: 9999,
  };

  const STYLE_ID = 'tm-random-png-style';
  const BOX_ID = 'tm-random-png-bg';
  let lastIndex = -1;
  let lastUrl = location.href;

  function getResourceNames() {
    const meta = GM_info.scriptMetaStr || '';
    return [...meta.matchAll(/@resource\s+(\S+)/g)].map(m => m[1]);
  }

  const IMAGELIST = getResourceNames().map(name => GM_getResourceURL(name));

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    GM_addStyle(`
      #${BOX_ID} {
        position: fixed !important;
        right: ${CONFIG.right}px !important;
        bottom: ${CONFIG.bottom}px !important;
        background-size: contain !important;
        background-position: center !important;
        background-repeat: no-repeat !important;
        opacity: ${CONFIG.opacity} !important;
        z-index: ${CONFIG.zIndex} !important;
        pointer-events: none !important;
      }
    `);
  }

  function ensureBox() {
    let box = document.getElementById(BOX_ID);
    if (!box && document.body) {
      box = document.createElement('div');
      box.id = BOX_ID;
      document.body.appendChild(box);
    }
    return box;
  }

  function getRandomImage() {
    if (!IMAGELIST.length) return '';
    if (IMAGELIST.length === 1) return IMAGELIST[0];
    let index;
    do {
      index = Math.floor(Math.random() * IMAGELIST.length);
    } while (index === lastIndex);
    lastIndex = index;
    return IMAGELIST[index];
  }

  function updateImage() {
    const box = ensureBox();
    if (!box) return;

    const imgUrl = getRandomImage();
    if (!imgUrl) return;

    const img = new Image();

    img.onload = function () {
      const naturalWidth = img.naturalWidth || img.width;
      const naturalHeight = img.naturalHeight || img.height;
      if (!naturalWidth || !naturalHeight) return;

      const scale = Math.min(
        CONFIG.width / naturalWidth,
        CONFIG.height / naturalHeight
      );

      const boxWidth = Math.round(naturalWidth * scale);
      const boxHeight = Math.round(naturalHeight * scale);

      box.style.width = `${boxWidth}px`;
      box.style.height = `${boxHeight}px`;
      box.style.backgroundImage = `url("${imgUrl}")`;

      console.log('[随机PNG背景] 已切换:', imgUrl, {
        naturalWidth, naturalHeight, boxWidth, boxHeight
      });
    };

    img.onerror = function () {
      console.error('[随机PNG背景] 图片加载失败:', imgUrl);
    };

    img.src = imgUrl;
  }

  function init() {
    injectStyle();
    ensureBox();
    updateImage();
  }

  function checkUrlChange() {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      updateImage();
    }
  }

  const rawPushState = history.pushState;
  history.pushState = function () {
    const ret = rawPushState.apply(this, arguments);
    setTimeout(checkUrlChange, 50);
    return ret;
  };

  const rawReplaceState = history.replaceState;
  history.replaceState = function () {
    const ret = rawReplaceState.apply(this, arguments);
    setTimeout(checkUrlChange, 50);
    return ret;
  };

  window.addEventListener('popstate', checkUrlChange);
  window.addEventListener('hashchange', checkUrlChange);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
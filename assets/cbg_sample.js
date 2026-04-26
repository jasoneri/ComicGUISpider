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

  const STYLE_ID = 'tm-cbg-style';
  const BOX_ID = 'tm-cbg-box';
  let initialized = false;

  function getResourceNames() {
    const meta = (typeof GM_info !== 'undefined' && GM_info.scriptMetaStr) || '';
    return [...meta.matchAll(/@resource\s+(\S+)/g)].map(m => m[1]);
  }

  const IMAGELIST = getResourceNames()
    .map(name => {
      try {
        return GM_getResourceURL(name);
      } catch {
        return '';
      }
    })
    .filter(Boolean);

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
        user-select: none !important;
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

  function pickImage() {
    if (!IMAGELIST.length) return '';
    const index = Math.floor(Math.random() * IMAGELIST.length);
    return IMAGELIST[index];
  }

  function renderOnce() {
    if (initialized) return;
    if (!document.body) return;
    const imgUrl = pickImage();
    if (!imgUrl) return;

    injectStyle();

    const box = ensureBox();
    if (!box) return;

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
      console.error('[cbg] 图片加载失败:', imgUrl);
    };

    img.src = imgUrl;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderOnce, { once: true });
  } else {
    renderOnce();
  }
})();
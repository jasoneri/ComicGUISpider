/**
 * 发布页工具条部件（pubilsh_helper.html 专属）。
 *
 * 设计要点：
 *   - 图标在此统一维护，HTML 不再内联 SVG；
 *   - 候选发布页下拉挂在「发布页」标签上（点标签展开），只在
 *     data-publish-candidates 不少于 2 个时生成（单数不显示），选中后回填
 *     `.publish-url-input`，保存仍走既有 save-btn。
 *
 * 由页面以 `<script src="../GUI/src/preview_format/widget/publish_bar.js">` 引入。
 */
(() => {
	"use strict";

	const ICONS = {
		cancel:
			'<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">' +
			'<line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>',
		link:
			'<svg width="1em" height="1em" viewBox="0 0 640 640">' +
			'<path d="M0 0h640v640H0z" fill="none" />' +
			'<path fill="currentColor" d="M384 64c-17.7 0-32 14.3-32 32s14.3 32 32 32h82.7L265.3 329.4c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0L512 173.3V256c0 17.7 14.3 32 32 32s32-14.3 32-32V96c0-17.7-14.3-32-32-32zm-240 96c-44.2 0-80 35.8-80 80v256c0 44.2 35.8 80 80 80h256c44.2 0 80-35.8 80-80v-80c0-17.7-14.3-32-32-32s-32 14.3-32 32v80c0 8.8-7.2 16-16 16H144c-8.8 0-16-7.2-16-16V240c0-8.8 7.2-16 16-16h80c17.7 0 32-14.3 32-32s-14.3-32-32-32z" />' +
			'</svg>',
		save:
			'<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">' +
			'<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path>' +
			'<polyline points="17 21 17 13 7 13 7 21"></polyline>' +
			'<polyline points="7 3 7 8 15 8"></polyline></svg>',
		// 下拉指示箭头，旋转 180° 表示展开。
		chevron:
			'<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 48 48">' +
			'<path d="M0 0h48v48H0z" fill="none" />' +
			'<path fill="#2196F3" d="M43 17.1L39.9 14L24 29.9L8.1 14L5 17.1L24 36z" />' +
			'</svg>',
		check:
			'<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24">' +
			'<path d="M0 0h24v24H0z" fill="none" />' +
			'<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5">' +
			'<path stroke-width="5.5" d="M3 12h5V6h4v12h4v-6h5" opacity=".2" />' +
			'<path d="M3 12h5V6h4v12h4v-6h5" />' +
			'</g>' +
			'</svg>',
	};

	/** HTML 里的静态按钮，图标由 JS 注入；空按钮直接替换，带文字的按钮前置插入。 */
	const ICON_TARGETS = {
		".inner-cancel-btn": { icon: ICONS.cancel },
		".link-btn": { icon: ICONS.link },
		".save-btn": { icon: ICONS.save },
		".btn1": { icon: ICONS.check, prepend: true },
	};

	const injectIcons = () => {
		Object.entries(ICON_TARGETS).forEach(([selector, { icon, prepend }]) => {
			const el = document.querySelector(selector);
			if (!el) return;
			if (prepend) {
				// 前置模式幂等：已存在 svg 就跳过，避免重复堆积。
				if (!el.querySelector("svg")) el.insertAdjacentHTML("afterbegin", icon);
			} else {
				el.innerHTML = icon;
			}
		});
	};

	/** 从发布页工具条读取候选；解析失败或缺省返回空数组。 */
	const readCandidates = (bar) => {
		const raw = bar.getAttribute("data-publish-candidates");
		if (!raw) return [];
		try {
			const parsed = JSON.parse(raw);
			return Array.isArray(parsed)
				? parsed.filter((url) => typeof url === "string" && url.trim())
				: [];
		} catch {
			return [];
		}
	};

	/** 候选下拉：仅当候选数 >= 2 时把「发布页」标签改造成触发器，否则什么都不渲染。 */
	const buildCandidateDropdown = () => {
		const bar = document.querySelector(".btn-group-bar.publish-bar");
		const label = document.querySelector(".btn-label.disable");
		const input = document.querySelector(".publish-url-input");
		if (!bar || !label || !input) return;

		const candidates = readCandidates(bar);
		if (candidates.length < 2) return;

		const panel = document.createElement("div");
		panel.className = "pub-candidate-panel";
		panel.setAttribute("role", "listbox");
		panel.hidden = true;
		// 挂到 body 顶层并 fixed 定位：工具条的 backdrop-filter 会形成层叠上下文，
		// 留在 bar 内部会被后续 DOM（底部主操作栏/图片容器）盖住，弹层永远在最上。
		document.body.appendChild(panel);

		function markSelected(url) {
			[...panel.children].forEach((item) => {
				item.classList.toggle("selected", item.dataset.url === url);
			});
		}

		function closePanel() {
			panel.hidden = true;
			label.classList.remove("open");
			label.setAttribute("aria-expanded", "false");
		}

		candidates.forEach((url) => {
			const item = document.createElement("button");
			item.type = "button";
			item.className = "pub-candidate-item";
			item.setAttribute("role", "option");
			item.dataset.url = url;
			item.textContent = url;
			item.title = url;
			item.addEventListener("click", (event) => {
				event.stopPropagation();
				input.value = url;
				markSelected(url);
				closePanel();
				input.focus();
			});
			panel.appendChild(item);
		});

		markSelected(input.value.trim());

		// 标签改造为下拉触发器：可点、带箭头、保留原有样式类。
		label.classList.add("has-dropdown");
		label.setAttribute("role", "button");
		label.setAttribute("tabindex", "0");
		label.setAttribute("aria-haspopup", "listbox");
		label.setAttribute("aria-expanded", "false");
		label.title = "选择预设发布页";
		label.insertAdjacentHTML("beforeend", ICONS.chevron);

		const positionPanel = () => {
			const rect = label.getBoundingClientRect();
			const pad = 6;

			// 下方的有效边界不是视口底边，而是「下一张卡片」的顶边——
			// 发布栏正下方就是主操作栏（输入域名/输入检测），下拉压住它等于
			// 把主交互控件全遮住，这是本页最差的展开方向。
			const nextBlockBelow = (node) => {
				let cur = node;
				while (cur) {
					const sib = cur.nextElementSibling;
					if (sib && sib.getBoundingClientRect().top > rect.bottom) return sib;
					cur = cur.parentElement;
				}
				return null;
			};
			let floor = window.innerHeight;
			const card = label.closest(".btn-group-bar.publish-bar");
			const nextCard = card ? nextBlockBelow(card) : null;
			if (nextCard) floor = Math.min(floor, nextCard.getBoundingClientRect().top);

			const roomBelow = floor - rect.bottom - pad;
			const roomAbove = rect.top - pad;

			panel.style.maxHeight = "";
			const naturalHeight = panel.offsetHeight;
			// 下方放得下就照常朝下；否则哪边宽裕朝哪边。
			const openBelow = naturalHeight <= roomBelow || roomBelow >= roomAbove;
			const room = openBelow ? roomBelow : roomAbove;
			panel.style.maxHeight = Math.max(12, Math.min(220, room)) + "px";

			const left = Math.min(Math.max(rect.left, 12), window.innerWidth - panel.offsetWidth - 12);
			panel.style.left = left + "px";
			panel.style.top = openBelow
				? rect.bottom + pad + "px"
				: rect.top - pad - panel.offsetHeight + "px";
		};

		const openPanel = () => {
			panel.hidden = false;
			positionPanel();
			label.classList.add("open");
			label.setAttribute("aria-expanded", "true");
		};

		const togglePanel = (event) => {
			event.stopPropagation();
			if (panel.hidden) openPanel();
			else closePanel();
		};

		label.addEventListener("click", togglePanel);
		label.addEventListener("keydown", (event) => {
			if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
				event.preventDefault();
				togglePanel(event);
			}
		});

		document.addEventListener("click", (event) => {
			if (!panel.hidden && !panel.contains(event.target) && !label.contains(event.target)) closePanel();
		});

		document.addEventListener("keydown", (event) => {
			if (event.key === "Escape" && !panel.hidden) closePanel();
		});

		// 滚动/缩放会使用 fixed 定位的浮层错位，直接收起。
		window.addEventListener("resize", closePanel);
		window.addEventListener("scroll", closePanel, true);
	};

	const init = () => {
		injectIcons();
		buildCandidateDropdown();
	};

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();

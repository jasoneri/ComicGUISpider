(() => {
	const TOAST_STACK_ID = "cgsTaskAddedToastStack";
	const TOAST_CLASS = "cgs-task-toast";
	const TOAST_EXIT_CLASS = "is-leaving";
	const TOAST_TITLE_CLASS = "cgs-task-toast-title line-clamp-2";
	const TOAST_SUBTITLE_CLASS = "cgs-task-toast-subtitle";
	const TOAST_SUBTITLE = "已入队, 主界面任务栏查看进度";
	const MAX_TOASTS = 4;
	const TOAST_LIFETIME_MS = 3000;
	const EXIT_DURATION_MS = 240;
	const toastTimers = new WeakMap();

	function ensureToastStack() {
		let stack = document.getElementById(TOAST_STACK_ID);
		if (stack) {
			return stack;
		}

		stack = document.createElement("div");
		stack.id = TOAST_STACK_ID;
		stack.setAttribute("aria-live", "polite");
		stack.setAttribute("aria-label", "Task notifications");
		document.body.appendChild(stack);
		return stack;
	}

	function cleanupToastStack() {
		const stack = document.getElementById(TOAST_STACK_ID);
		if (stack && stack.childElementCount === 0) {
			stack.remove();
		}
	}

	function clearToastTimers(toast) {
		const timers = toastTimers.get(toast);
		if (!timers) {
			return;
		}

		if (timers.removeTimer) {
			clearTimeout(timers.removeTimer);
		}
		if (timers.disposeTimer) {
			clearTimeout(timers.disposeTimer);
		}

		toastTimers.delete(toast);
	}

	function disposeToast(toast) {
		clearToastTimers(toast);
		if (toast && toast.isConnected) {
			toast.remove();
		}
		cleanupToastStack();
	}

	function removeToast(toast, immediate = false) {
		if (!toast) {
			return;
		}
		const timers = toastTimers.get(toast) || {};
		if (timers.removeTimer) {
			clearTimeout(timers.removeTimer);
			timers.removeTimer = null;
		}
		if (timers.disposeTimer) {
			clearTimeout(timers.disposeTimer);
			timers.disposeTimer = null;
		}

		if (immediate) {
			toastTimers.set(toast, timers);
			disposeToast(toast);
			return;
		}

		if (toast.classList.contains(TOAST_EXIT_CLASS)) {
			toastTimers.set(toast, timers);
			return;
		}

		toast.classList.add(TOAST_EXIT_CLASS);
		timers.disposeTimer = window.setTimeout(() => disposeToast(toast), EXIT_DURATION_MS);
		toastTimers.set(toast, timers);
	}

	function scheduleToastRemoval(toast) {
		const timers = toastTimers.get(toast) || {};
		timers.removeTimer = window.setTimeout(() => removeToast(toast), TOAST_LIFETIME_MS);
		toastTimers.set(toast, timers);
	}

	function trimOverflow(stack) {
		while (stack.childElementCount > MAX_TOASTS) {
			removeToast(stack.lastElementChild, true);
		}
	}
	window.showTaskAddedToast = function (title) {
		const stack = ensureToastStack();
		const toast = document.createElement("article");
		const titleEl = document.createElement("div");
		const subtitleEl = document.createElement("div");
		toast.className = TOAST_CLASS;
		toast.setAttribute("role", "status");
		toast.setAttribute("aria-live", "polite");
		titleEl.className = TOAST_TITLE_CLASS;
		subtitleEl.className = TOAST_SUBTITLE_CLASS;
		titleEl.textContent = `${title}`;
		subtitleEl.textContent = TOAST_SUBTITLE;
		toast.appendChild(titleEl);
		toast.appendChild(subtitleEl);
		stack.prepend(toast);
		trimOverflow(stack);
		scheduleToastRemoval(toast);
	};
})();
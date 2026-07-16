(() => {
	// Two lanes (do not merge):
	//   1) request queue  — every showTaskAddedToast only enqueues
	//   2) display pipeline — mounts/exits ONE card per beat
	// Visual: Sonner absolute stack (lift/scale/transition).
	// https://emilkowal.ski/ui/building-a-toast-component

	const TOAST_STACK_ID = "cgsTaskAddedToastStack";
	const TOAST_CLASS = "cgs-task-toast";
	const TOAST_SUBTITLE = "已入队, 主界面任务栏查看进度";

	const MAX_VISIBLE = 4;
	const MAX_QUEUE_SIZE = 40;
	/** How long a card stays once it is on stage (idle, no backlog). */
	const TOAST_LIFETIME_MS = 3200;
	/** Shortest readable hold when backlog is draining. */
	const MIN_HOLD_MS = 1100;
	/**
	 * One shared cadence for enter AND exit.
	 * 0→4 fill must use this beat — not a faster "fill burst" (that reads as
	 * ultra-stack, which is the opposite of continuous single-item motion).
	 */
	const STACK_BEAT_MS = 480;
	const EXIT_ANIM_MS = 400;
	/** Drop request if it sat in queue this long (wall-clock from enqueue). */
	const MAX_QUEUE_AGE_MS = 16000;
	const GAP_PX = 14;
	const WIDTH_PX = 356;

	/** @type {{ id: number, title: string, enqueuedAt: number, mountedAt: number, el: HTMLElement, removeTimer: number|null, disposeTimer: number|null, exitAt: number, leaving: boolean }[]} */
	const onStage = [];
	/** @type {{ title: string, enqueuedAt: number }[]} */
	const requestQueue = [];

	let nextId = 1;
	let expanded = false;
	let hoverBound = false;
	/** Next free moment on the global exit timeline. */
	let nextExitAt = 0;
	/** Next free moment for a new enter (prevents multi-mount same tick). */
	let nextEnterAt = 0;
	let enterPumpTimer = null;

	function ensureToastStack() {
		let stack = document.getElementById(TOAST_STACK_ID);
		if (stack) {
			return stack;
		}
		stack = document.createElement("div");
		stack.id = TOAST_STACK_ID;
		stack.setAttribute("aria-live", "polite");
		stack.setAttribute("aria-label", "Task notifications");
		stack.style.setProperty("--width", `${WIDTH_PX}px`);
		stack.style.setProperty("--gap", `${GAP_PX}px`);
		stack.style.setProperty("--offset-top", "18px");
		stack.style.setProperty("--offset-right", "18px");
		document.body.appendChild(stack);
		bindStackHover(stack);
		return stack;
	}

	function bindStackHover(stack) {
		if (hoverBound) {
			return;
		}
		hoverBound = true;
		stack.addEventListener("mouseenter", () => {
			expanded = true;
			layoutStack();
		});
		stack.addEventListener("mouseleave", () => {
			expanded = false;
			layoutStack();
		});
	}

	function cleanupToastStack() {
		const stack = document.getElementById(TOAST_STACK_ID);
		if (stack && onStage.length === 0 && requestQueue.length === 0) {
			stack.remove();
			hoverBound = false;
			expanded = false;
			nextExitAt = 0;
			nextEnterAt = 0;
		}
	}

	function livingOnStage() {
		return onStage.filter((item) => !item.leaving);
	}

	function pruneRequestQueue(now = Date.now()) {
		while (requestQueue.length > 0 && now - requestQueue[0].enqueuedAt > MAX_QUEUE_AGE_MS) {
			requestQueue.shift();
		}
		while (requestQueue.length > MAX_QUEUE_SIZE) {
			requestQueue.shift();
		}
	}

	function clearItemTimers(item) {
		if (item.removeTimer) {
			clearTimeout(item.removeTimer);
			item.removeTimer = null;
		}
		if (item.disposeTimer) {
			clearTimeout(item.disposeTimer);
			item.disposeTimer = null;
		}
	}

	function measureFrontHeight() {
		const living = livingOnStage();
		if (living.length === 0 || !living[0].el) {
			return 72;
		}
		const front = living[0].el;
		const previousHeight = front.style.height;
		front.style.height = "auto";
		const height = front.getBoundingClientRect().height || 72;
		front.style.height = previousHeight;
		return height;
	}

	function layoutStack() {
		const stack = ensureToastStack();
		const living = livingOnStage();
		const frontHeight = measureFrontHeight();
		stack.style.setProperty("--front-toast-height", `${frontHeight}px`);
		stack.dataset.expanded = expanded ? "true" : "false";
		stack.dataset.count = String(living.length);

		const heights = living.map((item) => {
			if (!item.el) {
				return frontHeight;
			}
			if (expanded || item === living[0]) {
				const previous = item.el.style.height;
				item.el.style.height = "auto";
				const measured = item.el.getBoundingClientRect().height || frontHeight;
				item.el.style.height = previous;
				return measured;
			}
			return frontHeight;
		});

		if (expanded) {
			const totalHeight = heights.reduce(
				(sum, height, index) => sum + height + (index > 0 ? GAP_PX : 0),
				0,
			);
			stack.style.setProperty("--hover-height", `${Math.max(totalHeight, frontHeight) + 24}px`);
		} else {
			stack.style.setProperty(
				"--hover-height",
				`${frontHeight + Math.max(0, living.length - 1) * 12 + 20}px`,
			);
		}

		let offsetBefore = 0;
		living.forEach((item, index) => {
			const el = item.el;
			if (!el) {
				return;
			}
			const isFront = index === 0;
			el.dataset.front = isFront ? "true" : "false";
			el.dataset.expanded = expanded ? "true" : "false";
			el.dataset.visible = index < MAX_VISIBLE ? "true" : "false";
			el.dataset.index = String(index);
			el.style.setProperty("--toasts-before", String(index));
			el.style.setProperty("--z-index", String(living.length - index));
			el.style.setProperty("--offset", `${offsetBefore}px`);
			el.style.setProperty("--initial-height", `${heights[index]}px`);
			if (!item.leaving) {
				el.style.height = expanded || isFront ? `${heights[index]}px` : `${frontHeight}px`;
			}
			offsetBefore += heights[index] + GAP_PX;
		});

		onStage.forEach((item) => {
			if (item.leaving && item.el) {
				item.el.dataset.removed = "true";
			}
		});
	}

	/**
	 * Place this card on the global exit timeline so no two living cards
	 * share an exit beat (prevents batch-wave leave).
	 */
	function scheduleExit(item) {
		const now = Date.now();
		const underPressure = requestQueue.length > 0;
		const holdMs = underPressure ? MIN_HOLD_MS : TOAST_LIFETIME_MS;
		const preferred = now + holdMs;
		const exitAt = Math.max(preferred, nextExitAt || 0, now);
		nextExitAt = exitAt + STACK_BEAT_MS;

		clearItemTimers(item);
		item.exitAt = exitAt;
		item.removeTimer = window.setTimeout(() => beginExit(item), Math.max(0, exitAt - now));
	}

	/**
	 * When backlog first appears, compress existing long holds into one-by-one
	 * exit beats (oldest first). Never delay an already-sooner exit.
	 */
	function compressExitCadence() {
		const living = livingOnStage().slice().reverse(); // oldest first (stage is newest-first)
		if (living.length === 0) {
			return;
		}
		const now = Date.now();
		let exitAt = now + STACK_BEAT_MS;
		for (const item of living) {
			const minHold = (item.mountedAt || now) + MIN_HOLD_MS;
			let assigned = Math.max(exitAt, minHold, now);
			if (typeof item.exitAt === "number" && item.exitAt >= now) {
				assigned = Math.min(assigned, item.exitAt);
			}
			clearItemTimers(item);
			item.exitAt = assigned;
			item.removeTimer = window.setTimeout(
				() => beginExit(item),
				Math.max(0, assigned - now),
			);
			exitAt = assigned + STACK_BEAT_MS;
		}
		nextExitAt = exitAt;
	}

	function beginExit(item) {
		if (!item || item.leaving) {
			return;
		}
		const wasFront = livingOnStage()[0] === item;
		item.leaving = true;
		clearItemTimers(item);
		if (item.el) {
			item.el.dataset.removed = "true";
			item.el.dataset.front = wasFront ? "true" : "false";
		}
		// Free the stage slot at exit-start so the next enter can overlap motion.
		layoutStack();
		scheduleEnterPump(0);

		item.disposeTimer = window.setTimeout(() => {
			if (item.el && item.el.isConnected) {
				item.el.remove();
			}
			const index = onStage.indexOf(item);
			if (index >= 0) {
				onStage.splice(index, 1);
			}
			layoutStack();
			scheduleEnterPump(0);
			cleanupToastStack();
		}, EXIT_ANIM_MS);
	}

	function createToastElement(title) {
		const toast = document.createElement("article");
		const titleEl = document.createElement("div");
		const subtitleEl = document.createElement("div");
		toast.className = TOAST_CLASS;
		toast.setAttribute("role", "status");
		toast.setAttribute("aria-live", "polite");
		toast.dataset.mounted = "false";
		toast.dataset.expanded = "false";
		toast.dataset.front = "false";
		toast.dataset.visible = "true";
		toast.dataset.removed = "false";
		titleEl.className = "cgs-task-toast-title";
		subtitleEl.className = "cgs-task-toast-subtitle";
		titleEl.textContent = String(title ?? "");
		subtitleEl.textContent = TOAST_SUBTITLE;
		toast.appendChild(titleEl);
		toast.appendChild(subtitleEl);
		return toast;
	}

	/** Mount exactly one request onto the stage. */
	function mountOne(request) {
		const stack = ensureToastStack();
		const item = {
			id: nextId++,
			title: request.title,
			enqueuedAt: request.enqueuedAt,
			mountedAt: Date.now(),
			el: createToastElement(request.title),
			removeTimer: null,
			disposeTimer: null,
			exitAt: 0,
			leaving: false,
		};
		onStage.unshift(item);
		stack.prepend(item.el);
		layoutStack();

		requestAnimationFrame(() => {
			requestAnimationFrame(() => {
				if (item.el && !item.leaving) {
					item.el.dataset.mounted = "true";
					layoutStack();
				}
			});
		});

		scheduleExit(item);
		return item;
	}

	/**
	 * Display pipeline: at most ONE enter per STACK_BEAT.
	 * Fill 0→4 and drain both use the same beat (no fast-fill exception).
	 */
	function pumpEnter() {
		enterPumpTimer = null;
		pruneRequestQueue();
		const now = Date.now();
		if (livingOnStage().length >= MAX_VISIBLE || requestQueue.length === 0) {
			cleanupToastStack();
			return;
		}
		if (now < nextEnterAt) {
			scheduleEnterPump(nextEnterAt - now);
			return;
		}

		const request = requestQueue.shift();
		if (!request) {
			return;
		}
		if (now - request.enqueuedAt > MAX_QUEUE_AGE_MS) {
			scheduleEnterPump(0);
			return;
		}

		mountOne(request);
		// Always advance enter timeline by full stack beat — even on first fill.
		nextEnterAt = Date.now() + STACK_BEAT_MS;

		if (livingOnStage().length < MAX_VISIBLE && requestQueue.length > 0) {
			scheduleEnterPump(STACK_BEAT_MS);
		}
	}

	function scheduleEnterPump(delayMs) {
		const waitMs = Math.max(0, delayMs);
		if (enterPumpTimer !== null) {
			// Already scheduled; only pull earlier if needed.
			return;
		}
		enterPumpTimer = window.setTimeout(pumpEnter, waitMs);
	}

	/**
	 * Public API: request lane only. Never mounts here.
	 * Caller burst vs stagger is irrelevant — pipeline owns all pacing.
	 */
	window.showTaskAddedToast = function (title) {
		const stageEmpty = livingOnStage().length === 0;
		const queueWasEmpty = requestQueue.length === 0;
		const stageFull = livingOnStage().length >= MAX_VISIBLE;

		pruneRequestQueue();
		requestQueue.push({
			title: String(title ?? ""),
			enqueuedAt: Date.now(),
		});
		pruneRequestQueue();

		// Overflow while stage full → compress long holds into single-exit beats.
		if (stageFull && queueWasEmpty && requestQueue.length > 0) {
			compressExitCadence();
		}

		// Cold start: allow first card immediately, then STACK_BEAT between each.
		// Do NOT reset nextEnterAt when stage already has cards (preserves cadence).
		if (stageEmpty && queueWasEmpty) {
			nextEnterAt = 0;
		}
		scheduleEnterPump(Math.max(0, nextEnterAt - Date.now()));
	};
})();

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useData } from 'vitepress'

const WIDGET_ORIGIN = 'https://notice.101114105.xyz'
const WIDGET_BOARD = 'cgs'
const TIP_URL = `${WIDGET_ORIGIN}/v1/boards/${WIDGET_BOARD}/tip`
const PANEL_URL = `${WIDGET_ORIGIN}/boards/${WIDGET_BOARD}/timeline/?embed=1&panel=1`
// 已读只记「最新一条的 id」：/tip 结构上只返回最新公告，条幅不可能展示旧条目，
// 存集合是多余的。但值带版本位——将来要加字段时才有干净的迁移路径
const READ_KEY = `notice:read:${WIDGET_BOARD}`
const READ_VERSION = 1
const MARQUEE_SPEED = 60 // px/s，约 4.6 汉字/秒：能读完，又明显在动
const MARQUEE_GAP = 48 // 两段之间的留白，px

interface Tip {
  id: string
  tip: string
  link_label: string
  link_url: string
}

type Mode = 'hidden' | 'bar' | 'dot' | 'panel'

const { isDark } = useData()

const tip = shallowRef<Tip | null>(null)
const mode = ref<Mode>('hidden')
const shift = ref(0) // 一次循环的位移量；0 表示静止（仅 reduced-motion）
const copies = ref(1) // 跑马灯段数，铺满可视区才不会露白
const panel = ref({ width: 360, height: 520 })

const viewportEl = ref<HTMLElement | null>(null)
const segEls = ref<HTMLElement[]>([])
const iframeEl = ref<HTMLIFrameElement | null>(null)

const scrolling = computed(() => shift.value > 0)
const trackStyle = computed(() =>
  scrolling.value
    ? { '--nb-shift': `${shift.value}px`, '--nb-dur': `${shift.value / MARQUEE_SPEED}s` }
    : undefined,
)
const fullText = computed(() =>
  tip.value ? [tip.value.tip, tip.value.link_label].filter(Boolean).join(' · ') : '',
)

function readMark(): string {
  try {
    const raw = window.localStorage.getItem(READ_KEY)
    if (!raw) return ''
    const state = JSON.parse(raw) as { v?: number; id?: string }
    // 版本不认识就当未读。降级方向只能是「多提示一次」，绝不能是「吞掉公告」
    return state.v === READ_VERSION && typeof state.id === 'string' ? state.id : ''
  } catch (err) {
    // 隐私模式禁用 localStorage、或值被外部写坏：都降级为每次提示，但不能无声
    console.warn('[notice] 已读状态读取失败，公告将重复展示', err)
    return ''
  }
}

function markRead(id: string): void {
  try {
    window.localStorage.setItem(READ_KEY, JSON.stringify({ v: READ_VERSION, id }))
  } catch (err) {
    console.warn('[notice] 已读状态写入失败，下次仍会展示', err)
  }
}

function measure(): void {
  const vp = viewportEl.value
  const seg = segEls.value[0]
  if (!vp || !seg) return
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    // 前庭功能障碍用户会因持续位移眩晕，这里必须让步：静止 + 省略号
    shift.value = 0
    copies.value = 1
    return
  }
  const step = seg.scrollWidth + MARQUEE_GAP
  shift.value = step
  // 无论文字长短都滚：位移到 step 时，剩余段落仍须盖满可视区，否则循环会露白
  copies.value = Math.ceil((vp.clientWidth + MARQUEE_GAP) / step) + 1
}

let resizeObserver: ResizeObserver | null = null

watch([mode, fullText], async () => {
  resizeObserver?.disconnect()
  resizeObserver = null
  if (mode.value !== 'bar') return
  await nextTick()
  measure()
  const vp = viewportEl.value
  if (!vp) return
  resizeObserver = new ResizeObserver(measure)
  resizeObserver.observe(vp)
})

async function loadTip(): Promise<void> {
  const res = await fetch(TIP_URL, { headers: { accept: 'application/json' } })
  if (res.status === 204) return // 该 board 尚无公告
  if (!res.ok) throw new Error(`tip ${res.status} ${res.statusText}`)
  const data = (await res.json()) as Tip
  tip.value = data
  mode.value = readMark() === data.id ? 'dot' : 'bar'
}

function activate(current: Tip): void {
  markRead(current.id)
  if (!current.link_url) {
    mode.value = 'panel'
    return
  }
  // 宏任务里再撤条幅：Vue 的 DOM patch 走微任务，同步改 mode 会在浏览器
  // 处理 <a target="_blank"> 默认跳转前把节点摘掉，跳转可能被吞
  window.setTimeout(() => {
    mode.value = 'dot'
  }, 0)
}

function dismiss(current: Tip): void {
  markRead(current.id)
  mode.value = 'dot'
}

function syncTheme(): void {
  iframeEl.value?.contentWindow?.postMessage(
    { type: 'notice-widget.theme', theme: isDark.value ? 'dark' : 'light' },
    WIDGET_ORIGIN,
  )
}

function onMessage(event: MessageEvent): void {
  if (event.origin !== WIDGET_ORIGIN) return
  const data = event.data
  if (!data || typeof data !== 'object') return
  if (data.type === 'notice-widget.expand') {
    panel.value = { width: data.width ?? 360, height: data.height ?? 520 }
  } else if (data.type === 'notice-widget.collapse') {
    mode.value = 'dot'
  }
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && mode.value === 'panel') mode.value = 'dot'
}

watch(isDark, syncTheme)

onMounted(() => {
  window.addEventListener('message', onMessage)
  window.addEventListener('keydown', onKeydown)
  loadTip().catch((err) => console.error('[notice] 公告拉取失败', err))
})

onBeforeUnmount(() => {
  window.removeEventListener('message', onMessage)
  window.removeEventListener('keydown', onKeydown)
  resizeObserver?.disconnect()
})
</script>

<template>
  <div v-if="tip" class="nb">
    <!-- 未读：右下角固定宽度的横向滚动公告条 -->
    <div v-if="mode === 'bar'" class="nb-bar">
      <component
        :is="tip.link_url ? 'a' : 'button'"
        class="nb-bar__main"
        :href="tip.link_url || undefined"
        :target="tip.link_url ? '_blank' : undefined"
        :rel="tip.link_url ? 'noopener noreferrer' : undefined"
        :type="tip.link_url ? undefined : 'button'"
        :title="fullText"
        @click="activate(tip)"
      >
        <svg
          class="nb-ico"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <path d="m3 11 18-5v12L3 14v-3z" />
          <path d="M11.6 16.8a3 3 0 1 1-5.8-1.6" />
        </svg>
        <span ref="viewportEl" class="nb-vp">
          <span class="nb-track" :class="{ 'is-scroll': scrolling }" :style="trackStyle">
            <span
              v-for="n in copies"
              :key="n"
              ref="segEls"
              class="nb-seg"
              :aria-hidden="n === 1 ? undefined : 'true'"
            >
              <span>{{ tip.tip }}</span>
              <span v-if="tip.link_label" class="nb-seg__cta">{{ tip.link_label }}</span>
            </span>
          </span>
        </span>
      </component>
      <button
        class="nb-bar__x"
        type="button"
        aria-label="不再提示这条公告"
        title="不再提示"
        @click="dismiss(tip)"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          aria-hidden="true"
        >
          <path d="M18 6 6 18M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- 已读：低调的重开入口，hover 才提亮 -->
    <button
      v-else-if="mode === 'dot'"
      class="nb-dot"
      type="button"
      aria-label="查看公告"
      title="查看公告"
      @click="mode = 'panel'"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path d="m3 11 18-5v12L3 14v-3z" />
        <path d="M11.6 16.8a3 3 0 1 1-5.8-1.6" />
      </svg>
    </button>

    <!-- 展开：公告时间线浮窗 -->
    <iframe
      v-else-if="mode === 'panel'"
      ref="iframeEl"
      class="nb-panel"
      :src="PANEL_URL"
      :style="{ width: panel.width + 'px', height: panel.height + 'px' }"
      title="CGS 公告"
      scrolling="no"
      @load="syncTheme"
    />
  </div>
</template>

<style scoped>
.nb {
  position: fixed;
  right: 24px;
  bottom: 24px;
  /* < --vp-z-index-backdrop(50)，移动端侧栏遮罩仍能盖住 */
  z-index: 40;
}

/* ---------- 未读：滚动公告条 ---------- */
.nb-bar {
  display: flex;
  align-items: stretch;
  width: 320px;
  height: 44px;
  overflow: hidden;
  border: 1px solid var(--vp-c-divider);
  border-radius: 22px;
  background: var(--vp-c-bg-elv);
  box-shadow: var(--vp-shadow-3);
  animation: nb-in 0.28s cubic-bezier(0.25, 0.46, 0.45, 0.94) backwards;
}
.nb-bar__main {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 0 0 0 14px;
  border: 0;
  background: none;
  color: var(--vp-c-text-1);
  font: inherit;
  text-align: left;
  text-decoration: none;
  cursor: pointer;
  transition: background-color 0.2s ease;
}
.nb-bar__main:hover {
  background: var(--vp-c-default-soft);
}
.nb-ico {
  flex: none;
  width: 16px;
  height: 16px;
  color: var(--vp-c-brand-1);
}
.nb-vp {
  flex: 1;
  min-width: 0;
  height: 22px;
  overflow: hidden;
}
.nb-track {
  display: flex;
  align-items: center;
  gap: 48px;
  height: 100%;
}
.nb-seg {
  flex: none;
  max-width: 100%;
  overflow: hidden;
  font-size: 13px;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.nb-track.is-scroll {
  will-change: transform;
  animation: nb-marquee var(--nb-dur) linear infinite;
}
.nb-track.is-scroll .nb-seg {
  max-width: none;
  overflow: visible;
}
.nb-bar:hover .nb-track.is-scroll,
.nb-bar:focus-within .nb-track.is-scroll {
  animation-play-state: paused;
}
.nb-seg__cta {
  margin-left: 8px;
  color: var(--vp-c-brand-1);
  font-weight: 500;
}
.nb-seg__cta::before {
  content: '· ';
  color: var(--vp-c-text-3);
  font-weight: 400;
}
.nb-bar__x {
  display: grid;
  flex: none;
  place-items: center;
  width: 44px;
  border: 0;
  background: none;
  color: var(--vp-c-text-3);
  cursor: pointer;
  transition: color 0.2s ease, background-color 0.2s ease;
}
.nb-bar__x:hover {
  background: var(--vp-c-default-soft);
  color: var(--vp-c-text-1);
}
.nb-bar__x svg {
  width: 14px;
  height: 14px;
}

/* ---------- 已读：低调入口 ---------- */
.nb-dot {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 50%;
  background: var(--vp-c-bg-elv);
  color: var(--vp-c-text-3);
  box-shadow: var(--vp-shadow-2);
  --nb-dot-rest: 0.5;
  opacity: var(--nb-dot-rest);
  cursor: pointer;
  transition: opacity 0.2s ease, color 0.2s ease, border-color 0.2s ease;
  /* backwards 而非 both：入场动画不能在结束后继续压住 opacity，
     否则静息值与 :hover 全被动画覆盖，小圆点会永远停在不透明 */
  animation: nb-dot-in 0.28s cubic-bezier(0.25, 0.46, 0.45, 0.94) backwards;
}
.nb-dot:hover,
.nb-dot:focus-visible {
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-1);
  opacity: 1;
}
.nb-dot svg {
  width: 16px;
  height: 16px;
}
/* 触屏没有 hover，静息态必须看得见 */
@media (pointer: coarse) {
  .nb-dot {
    width: 44px;
    height: 44px;
    --nb-dot-rest: 0.72;
  }
}

/* ---------- 展开：时间线浮窗 ---------- */
.nb-panel {
  display: block;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 48px);
  border: 0;
  border-radius: 16px;
  background: transparent;
  overflow: hidden;
  transition: width 0.25s cubic-bezier(0.25, 0.46, 0.45, 0.94),
    height 0.25s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

.nb-bar__main:focus-visible,
.nb-bar__x:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: -2px;
}
.nb-dot:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 2px;
}

@keyframes nb-marquee {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(calc(var(--nb-shift) * -1));
  }
}
@keyframes nb-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
@keyframes nb-dot-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: var(--nb-dot-rest);
    transform: none;
  }
}

@media (max-width: 420px) {
  .nb {
    right: 16px;
    bottom: 16px;
  }
  .nb-bar {
    width: calc(100vw - 32px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .nb-bar,
  .nb-dot {
    animation: none;
  }
  .nb-track.is-scroll {
    animation: none;
  }
  .nb-panel {
    transition: none;
  }
}
</style>

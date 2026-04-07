<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  createEmptyMonitorBoardRuntimeData,
  emptyMonitorBoardLiveStatus,
  monitorBoardCopy,
  type MonitorBoardLocale,
  type MonitorBoardRuntimeData,
  monitorBoardSites,
  type MonitorBoardLiveStatus,
  type MonitorBoardStatusMap,
  type MonitorBoardVoteKey,
  type MonitorBoardVotes,
} from './monitorStatusBoardSource'
import {
  fetchMonitorBoardRuntimeData,
  submitMonitorBoardVote,
} from './monitorBoardApi'

const props = withDefaults(defineProps<{
  locale?: MonitorBoardLocale
  resetDate?: string
  statusMap?: MonitorBoardStatusMap
  apiBaseUrl?: string
}>(), {
  locale: 'zh',
})

type ChartShape = {
  areaPath: string
  linePath: string
}

type MonitorBoardLocalStageEntry = {
  action: MonitorBoardVoteKey
  completedAt: string
}

type MonitorBoardLocalStageMap = Partial<Record<string, MonitorBoardLocalStageEntry>>

type MonitorBoardLoadState = 'idle' | 'loading' | 'ready' | 'error'

type MonitorBoardBubbleConfig = {
  key: MonitorBoardVoteKey
  label: string
  color: string
  glow: string
  angleDeg: number
  offsetX: number
  offsetY: number
}

type MonitorBoardVoteVisual = {
  color: string
  glow: string
  angleDeg: number
}

type MonitorBoardGuideBubbleConfig = {
  offsetX: number
  offsetY: number
}

function buildChart(values: number[], width = 112, height = 40, padding = 4): ChartShape {
  if (values.length === 0) {
    const floor = height - padding
    return {
      areaPath: `M ${padding} ${floor} L ${width - padding} ${floor} L ${width - padding} ${floor} L ${padding} ${floor} Z`,
      linePath: `M ${padding} ${floor} L ${width - padding} ${floor}`,
    }
  }

  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const step = (width - padding * 2) / Math.max(values.length - 1, 1)

  const points = values.map((value, index) => {
    const x = padding + step * index
    const normalized = (value - min) / span
    const y = height - padding - normalized * (height - padding * 2)
    return {
      x: Number(x.toFixed(2)),
      y: Number(y.toFixed(2)),
    }
  })

  const linePath = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
    .join(' ')

  const firstPoint = points[0]
  const lastPoint = points[points.length - 1]
  const floor = height - padding
  const areaPath = `${linePath} L ${lastPoint.x} ${floor} L ${firstPoint.x} ${floor} Z`

  return { areaPath, linePath }
}

function cloneStatusMap(statusMap: MonitorBoardStatusMap): Record<string, MonitorBoardLiveStatus> {
  return Object.fromEntries(
    Object.entries(statusMap).map(([siteId, liveStatus]) => [
      siteId,
      {
        uptime: [...liveStatus.uptime],
        votes: { ...liveStatus.votes },
      },
    ]),
  )
}

const text = computed(() => monitorBoardCopy[props.locale])
const guideHint = computed(() => props.locale === 'zh' ? '点击卡片' : 'click card')
const completedToastLabel = computed(() => props.locale === 'zh' ? '已投票' : 'Voted')
const hoverAvatarSrc = '/assets/img/icons/monitor.png'
const bubblePlaceholderSrc = '/assets/img/monitor/speak.svg'
const boardRoot = ref<HTMLElement | null>(null)
const remoteRuntimeData = ref<MonitorBoardRuntimeData | null>(null)
const loadState = ref<MonitorBoardLoadState>('idle')
const loadErrorMessage = ref<string | null>(null)
const localStageMap = ref<MonitorBoardLocalStageMap>({})
const pendingStageMap = ref<MonitorBoardLocalStageMap>({})
const activeCardId = ref<string | null>(null)
const toastMessage = ref<string | null>(null)

const providedRuntimeData = computed<MonitorBoardRuntimeData | null>(() => {
  if (props.resetDate === undefined && props.statusMap === undefined) {
    return null
  }

  return {
    resetDate: props.resetDate ?? createEmptyMonitorBoardRuntimeData().resetDate,
    statusMap: cloneStatusMap(props.statusMap ?? {}),
  }
})

const runtimeData = computed<MonitorBoardRuntimeData>(() => (
  providedRuntimeData.value
  ?? remoteRuntimeData.value
  ?? createEmptyMonitorBoardRuntimeData()
))
const resetDate = computed(() => runtimeData.value.resetDate)
const effectiveStageMap = computed<MonitorBoardLocalStageMap>(() => ({
  ...localStageMap.value,
  ...pendingStageMap.value,
}))
const effectiveApiBaseUrl = computed(() => {
  if (typeof props.apiBaseUrl === 'string' && props.apiBaseUrl.trim() !== '') {
    return props.apiBaseUrl.trim()
  }

  const configuredApiBaseUrl = import.meta.env.VITE_MONITOR_API_BASE_URL
  return typeof configuredApiBaseUrl === 'string' && configuredApiBaseUrl.trim() !== ''
    ? configuredApiBaseUrl.trim()
    : import.meta.env.DEV
      ? LOCAL_MONITOR_API_BASE_URL
      : '/api/monitor'
})
const localStageStorageKey = computed(() => `monitor-board-local-stage:${resetDate.value ?? 'default'}`)
const hasActiveCard = computed(() => activeCardId.value !== null)
const hasPendingSubmission = computed(() => Object.keys(pendingStageMap.value).length > 0)
const summaryStatusLabel = computed(() => {
  if (loadState.value === 'loading') {
    return text.value.syncing
  }
  if (loadState.value === 'error') {
    return text.value.syncFailed
  }
  if (hasPendingSubmission.value) {
    return text.value.submitting
  }
  return null
})
const loadAlertMessage = computed(() => {
  if (loadState.value !== 'error') {
    return null
  }
  return loadErrorMessage.value ?? text.value.retryHint
})

const TOAST_TIMEOUT_MS = 1800
const LOCAL_MONITOR_API_BASE_URL = 'http://127.0.0.1:8787/api/monitor'
const DEFAULT_MONITOR_BUBBLE_RADIUS_PX = 130
const DEFAULT_MONITOR_GUIDE_BUBBLE_RADIUS_PX = 140
const MONITOR_NEUTRAL_BUBBLE_ANGLE_DEG = 30
const MONITOR_GUIDE_BUBBLE_ANGLE_DEG = MONITOR_NEUTRAL_BUBBLE_ANGLE_DEG
const MONITOR_CARD_LAYER = 400
const MONITOR_PREVIEW_LAYER_UNDER = 200
const MONITOR_PREVIEW_LAYER_OVER = 600
const MONITOR_PREVIEW_START_Y_PX = 100
const MONITOR_PREVIEW_APEX_Y_PX = -1
const MONITOR_PREVIEW_REBOUND_Y_PX = 4
const MONITOR_PREVIEW_SETTLE_Y_PX = -1
const MONITOR_PREVIEW_END_Y_PX = 0
const bubbleOrbitRadiusPx = ref(DEFAULT_MONITOR_BUBBLE_RADIUS_PX)
const guideBubbleOrbitRadiusPx = ref(DEFAULT_MONITOR_GUIDE_BUBBLE_RADIUS_PX)

const monitorPreviewMotionStyle = {
  '--monitor-card-layer': `${MONITOR_CARD_LAYER}`,
  '--monitor-preview-layer-under': `${MONITOR_PREVIEW_LAYER_UNDER}`,
  '--monitor-preview-layer-over': `${MONITOR_PREVIEW_LAYER_OVER}`,
  '--monitor-pop-start-y': `${MONITOR_PREVIEW_START_Y_PX}px`,
  '--monitor-pop-apex-y': `${MONITOR_PREVIEW_APEX_Y_PX}px`,
  '--monitor-pop-rebound-y': `${MONITOR_PREVIEW_REBOUND_Y_PX}px`,
  '--monitor-pop-settle-y': `${MONITOR_PREVIEW_SETTLE_Y_PX}px`,
  '--monitor-pop-end-y': `${MONITOR_PREVIEW_END_Y_PX}px`,
} as const

const voteVisualMap: Record<MonitorBoardVoteKey, MonitorBoardVoteVisual> = {
  up: {
    color: '#10b981',
    glow: '0 0 12px rgba(16, 185, 129, 0.52)',
    angleDeg: 180,
  },
  neutral: {
    color: '#f59e0b',
    glow: '0 0 12px rgba(245, 158, 11, 0.42)',
    angleDeg: MONITOR_NEUTRAL_BUBBLE_ANGLE_DEG,
  },
  down: {
    color: '#f43f5e',
    glow: '0 0 12px rgba(244, 63, 94, 0.44)',
    angleDeg: 0,
  },
}

function buildBubbleOrbit(angleDeg: number, radiusPx: number): { offsetX: number, offsetY: number } {
  const radians = angleDeg * Math.PI / 180
  return {
    offsetX: Number((Math.cos(radians) * radiusPx).toFixed(2)),
    offsetY: Number((Math.sin(radians) * radiusPx * -1).toFixed(2)),
  }
}

const bubbleConfigs = computed<MonitorBoardBubbleConfig[]>(() => [
  {
    key: 'up',
    label: text.value.segments.up,
    ...buildBubbleOrbit(voteVisualMap.up.angleDeg, bubbleOrbitRadiusPx.value),
    ...voteVisualMap.up,
  },
  {
    key: 'neutral',
    label: text.value.segments.neutral,
    ...buildBubbleOrbit(voteVisualMap.neutral.angleDeg, bubbleOrbitRadiusPx.value),
    ...voteVisualMap.neutral,
  },
  {
    key: 'down',
    label: text.value.segments.down,
    ...buildBubbleOrbit(voteVisualMap.down.angleDeg, bubbleOrbitRadiusPx.value),
    ...voteVisualMap.down,
  },
])

const guideBubbleConfig = computed<MonitorBoardGuideBubbleConfig>(() => (
  buildBubbleOrbit(MONITOR_GUIDE_BUBBLE_ANGLE_DEG, guideBubbleOrbitRadiusPx.value)
))

let toastTimer: number | null = null

function isMonitorBoardVoteKey(value: unknown): value is MonitorBoardVoteKey {
  return value === 'up' || value === 'neutral' || value === 'down'
}

function readLocalStageMap(storageKey: string): MonitorBoardLocalStageMap {
  if (typeof window === 'undefined') {
    return {}
  }

  const rawValue = window.localStorage.getItem(storageKey)
  if (!rawValue) {
    return {}
  }

  try {
    const parsed = JSON.parse(rawValue) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return {}
    }

    return Object.fromEntries(
      Object.entries(parsed).flatMap(([siteId, stage]) => {
        if (!stage || typeof stage !== 'object') {
          return []
        }

        const action = (stage as { action?: unknown }).action
        const completedAt = (stage as { completedAt?: unknown }).completedAt
        if (!isMonitorBoardVoteKey(action) || typeof completedAt !== 'string') {
          return []
        }

        return [[siteId, { action, completedAt }]]
      }),
    ) as MonitorBoardLocalStageMap
  } catch (error) {
    console.error('Failed to parse monitor board local stage.', error)
    return {}
  }
}

function writeLocalStageMap(storageKey: string, stageMap: MonitorBoardLocalStageMap): void {
  if (typeof window === 'undefined') {
    return
  }

  window.localStorage.setItem(storageKey, JSON.stringify(stageMap))
}

function readOrbitRadiusPx(sizeVariableName: '--monitor-action-width' | '--monitor-guide-width', fallbackRadiusPx: number): number {
  if (!boardRoot.value || typeof window === 'undefined') {
    return fallbackRadiusPx
  }

  const sampleCard = boardRoot.value.querySelector<HTMLElement>('.status-card')
  if (!sampleCard) {
    return fallbackRadiusPx
  }

  const cardStyles = window.getComputedStyle(sampleCard)
  const avatarWidth = Number.parseFloat(cardStyles.getPropertyValue('--monitor-avatar-width'))
  const orbitWidth = Number.parseFloat(cardStyles.getPropertyValue(sizeVariableName))
  const bubbleGap = Number.parseFloat(cardStyles.getPropertyValue('--monitor-bubble-gap'))
  if (![avatarWidth, orbitWidth, bubbleGap].every(Number.isFinite)) {
    return fallbackRadiusPx
  }

  return Number((((avatarWidth + orbitWidth) / 2) + bubbleGap).toFixed(2))
}

function syncBubbleOrbitMetrics(): void {
  bubbleOrbitRadiusPx.value = readOrbitRadiusPx('--monitor-action-width', DEFAULT_MONITOR_BUBBLE_RADIUS_PX)
  guideBubbleOrbitRadiusPx.value = readOrbitRadiusPx('--monitor-guide-width', DEFAULT_MONITOR_GUIDE_BUBBLE_RADIUS_PX)
}

function syncLocalStageMap(): void {
  localStageMap.value = readLocalStageMap(localStageStorageKey.value)
}

function setPendingStage(cardId: string, entry: MonitorBoardLocalStageEntry | null): void {
  if (entry) {
    pendingStageMap.value = {
      ...pendingStageMap.value,
      [cardId]: entry,
    }
    return
  }

  pendingStageMap.value = Object.fromEntries(
    Object.entries(pendingStageMap.value).filter(([entryCardId]) => entryCardId !== cardId),
  ) as MonitorBoardLocalStageMap
}

function commitLocalStage(cardId: string, entry: MonitorBoardLocalStageEntry): void {
  const nextStageMap: MonitorBoardLocalStageMap = {
    ...localStageMap.value,
    [cardId]: entry,
  }

  localStageMap.value = nextStageMap
  writeLocalStageMap(localStageStorageKey.value, nextStageMap)
}

async function hydrateRemoteRuntimeData(): Promise<void> {
  if (providedRuntimeData.value) {
    return
  }

  loadState.value = 'loading'
  loadErrorMessage.value = null

  try {
    remoteRuntimeData.value = await fetchMonitorBoardRuntimeData(effectiveApiBaseUrl.value)
    loadState.value = 'ready'
  } catch (error) {
    loadState.value = 'error'
    loadErrorMessage.value = error instanceof Error ? error.message : text.value.retryHint
    console.error('Failed to fetch monitor board runtime data.', error)
  }
}

function isCardCompleted(cardId: string): boolean {
  return effectiveStageMap.value[cardId] != null
}

function isCardLocked(cardId: string): boolean {
  return activeCardId.value === cardId
}

function isCardDimmed(cardId: string): boolean {
  return activeCardId.value !== null && activeCardId.value !== cardId
}

function getCardElement(cardId: string | null): HTMLElement | null {
  if (!cardId || !boardRoot.value) {
    return null
  }

  return boardRoot.value.querySelector<HTMLElement>(`[data-card-id="${cardId}"]`)
}

function blurCardFocus(cardId: string | null): void {
  const cardElement = getCardElement(cardId)
  if (!cardElement || typeof document === 'undefined') {
    return
  }

  const activeElement = document.activeElement
  if (activeElement instanceof HTMLElement && (activeElement === cardElement || cardElement.contains(activeElement))) {
    activeElement.blur()
  }

  cardElement.blur()
}

function clearActiveCard(): void {
  const previousCardId = activeCardId.value
  activeCardId.value = null
  blurCardFocus(previousCardId)
}

function clearToast(): void {
  toastMessage.value = null
  if (toastTimer !== null && typeof window !== 'undefined') {
    window.clearTimeout(toastTimer)
    toastTimer = null
  }
}

function showToast(message: string): void {
  if (typeof window === 'undefined') {
    return
  }

  toastMessage.value = message
  if (toastTimer !== null) {
    window.clearTimeout(toastTimer)
  }

  toastTimer = window.setTimeout(() => {
    toastMessage.value = null
    toastTimer = null
  }, TOAST_TIMEOUT_MS)
}

function handleCardActivate(cardId: string): void {
  if (isCardCompleted(cardId)) {
    showToast(completedToastLabel.value)
    return
  }

  if (activeCardId.value === cardId) {
    clearActiveCard()
    return
  }

  blurCardFocus(activeCardId.value)
  activeCardId.value = cardId
}

function handleCardClick(cardId: string, event: MouseEvent): void {
  const target = event.target
  if (target instanceof Element && target.closest('a, button')) {
    return
  }

  handleCardActivate(cardId)
}

function handleCardKeydown(cardId: string, event: KeyboardEvent): void {
  if (event.key !== 'Enter' && event.key !== ' ') {
    return
  }

  event.preventDefault()
  handleCardActivate(cardId)
}

function handleBubbleVote(cardId: string, action: MonitorBoardVoteKey): void {
  const stageEntry: MonitorBoardLocalStageEntry = {
    action,
    completedAt: new Date().toISOString(),
  }

  setPendingStage(cardId, stageEntry)
  clearActiveCard()

  void submitMonitorBoardVote({
    siteId: cardId,
    action,
    delta: 1,
  }, effectiveApiBaseUrl.value)
    .then(() => {
      commitLocalStage(cardId, stageEntry)
      showToast(text.value.submitSuccess)
    })
    .catch((error: unknown) => {
      const detail = error instanceof Error ? error.message : text.value.retryHint
      console.error('Failed to submit monitor board vote.', error)
      showToast(`${text.value.submitFailed}: ${detail}`)
    })
    .finally(() => {
      setPendingStage(cardId, null)
    })
}

function handleDocumentPointerDown(event: PointerEvent): void {
  if (!activeCardId.value || !boardRoot.value) {
    return
  }

  const target = event.target
  if (!(target instanceof Node)) {
    return
  }

  const activeCardElement = getCardElement(activeCardId.value)
  if (activeCardElement?.contains(target)) {
    return
  }

  clearActiveCard()
}

function handleDocumentKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    clearActiveCard()
  }
}

onMounted(() => {
  syncLocalStageMap()
  syncBubbleOrbitMetrics()
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  document.addEventListener('keydown', handleDocumentKeydown)
  window.addEventListener('resize', syncBubbleOrbitMetrics)
  void hydrateRemoteRuntimeData()
})

onBeforeUnmount(() => {
  clearToast()
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  document.removeEventListener('keydown', handleDocumentKeydown)
  window.removeEventListener('resize', syncBubbleOrbitMetrics)
})

watch(localStageStorageKey, () => {
  clearActiveCard()
  syncLocalStageMap()
})

const cardsWithCharts = computed(() => monitorBoardSites.map((site) => {
  const liveStatus: MonitorBoardLiveStatus = runtimeData.value.statusMap[site.id] ?? emptyMonitorBoardLiveStatus
  const localStage = effectiveStageMap.value[site.id]
  const effectiveVotes: MonitorBoardVotes = {
    up: liveStatus.votes.up,
    neutral: liveStatus.votes.neutral,
    down: liveStatus.votes.down,
  }

  if (localStage) {
    effectiveVotes[localStage.action] += 1
  }

  const totalVotes = effectiveVotes.up + effectiveVotes.neutral + effectiveVotes.down
  const chart = buildChart(liveStatus.uptime)

  return {
    ...site,
    chart,
    isCompleted: localStage != null,
    completedAction: localStage?.action ?? null,
    completedBorderColor: localStage ? voteVisualMap[localStage.action].color : 'transparent',
    totalVotes,
    segments: (Object.keys(voteVisualMap) as MonitorBoardVoteKey[]).map((key) => ({
      key,
      label: text.value.segments[key],
      value: effectiveVotes[key],
      color: voteVisualMap[key].color,
      glow: voteVisualMap[key].glow,
      percent: totalVotes === 0 ? 0 : (effectiveVotes[key] / totalVotes) * 100,
    })),
  }
}))

</script>

<template>
  <section ref="boardRoot" class="monitor-board">
    <div class="board-shell">
      <header class="board-header">
        <div class="board-copy">
          <h1>
            站点可用<del>监控</del>投票
          </h1>
        </div>

        <div class="board-summary">
          <div class="summary-chip">
            <span>{{ text.resetDate }}</span>
            <strong>{{ resetDate }}</strong>
          </div>
          <div
            v-if="summaryStatusLabel"
            class="summary-chip"
            :class="{
              'is-error': loadState === 'error',
              'is-pending': loadState !== 'error',
            }"
          >
            <strong>{{ summaryStatusLabel }}</strong>
          </div>
        </div>
      </header>

      <p v-if="loadAlertMessage" class="board-alert" role="status">
        {{ loadAlertMessage }}
      </p>

      <div class="card-grid" :class="{ 'has-active-card': hasActiveCard }">
        <article
          v-for="(card, index) in cardsWithCharts"
          :key="card.id"
          class="status-card"
          :class="{
            'is-clickable': !card.isCompleted,
            'is-completed': card.isCompleted,
            'is-locked': isCardLocked(card.id),
            'is-dimmed': isCardDimmed(card.id),
          }"
          :data-card-id="card.id"
          :tabindex="card.isCompleted || isCardDimmed(card.id) ? -1 : 0"
          :aria-disabled="card.isCompleted ? 'true' : undefined"
          :style="[
            monitorPreviewMotionStyle,
            {
              '--monitor-accent': card.accent,
              '--monitor-completed-border': card.completedBorderColor,
              '--monitor-delay': `${index * 120}ms`,
            },
          ]"
          @click="handleCardClick(card.id, $event)"
          @keydown="handleCardKeydown(card.id, $event)"
        >
          <div class="card-monitor-shell">
            <img
              class="card-monitor"
              :src="hoverAvatarSrc"
              alt=""
              aria-hidden="true"
            >
          </div>

          <div class="card-monitor-overlay">
            <div
              class="bubble-guide"
              aria-hidden="true"
              :style="{
                '--guide-offset-x': `${guideBubbleConfig.offsetX}px`,
                '--guide-offset-y': `${guideBubbleConfig.offsetY}px`,
              }"
            >
              <img class="bubble-guide-art" :src="bubblePlaceholderSrc" alt="">
              <span class="bubble-guide-label">{{ guideHint }}</span>
            </div>

            <div class="bubble-action-stack">
              <button
                v-for="(bubble, bubbleIndex) in bubbleConfigs"
                :key="`${card.id}-${bubble.key}`"
                type="button"
                class="bubble-action"
                :style="{
                  '--bubble-color': bubble.color,
                  '--bubble-glow': bubble.glow,
                  '--bubble-delay': `${bubbleIndex * 60}ms`,
                  '--bubble-offset-x': `${bubble.offsetX}px`,
                  '--bubble-offset-y': `${bubble.offsetY}px`,
                }"
                :aria-label="`${card.name} ${bubble.label}`"
                @click.stop="handleBubbleVote(card.id, bubble.key)"
              >
                <img class="bubble-action-art" :src="bubblePlaceholderSrc" alt="">
                <span class="bubble-action-label">{{ bubble.label }}</span>
              </button>
            </div>
          </div>

          <div class="card-layout">
            <a
              class="site-link"
              :href="card.href"
              :aria-label="`${card.name} official site`"
              target="_blank"
              rel="noreferrer"
              @click.stop
            >
              <img class="site-icon" :src="card.avatarSrc" :alt="card.name">
            </a>

            <svg class="sparkline" viewBox="0 0 112 40" preserveAspectRatio="none" aria-hidden="true">
              <defs>
                <linearGradient :id="`fill-${card.id}`" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" :stop-color="card.accent" stop-opacity="0.42" />
                  <stop offset="100%" :stop-color="card.accent" stop-opacity="0" />
                </linearGradient>
              </defs>
              <path class="sparkline-area" :d="card.chart.areaPath" :fill="`url(#fill-${card.id})`" />
              <path class="sparkline-line" :d="card.chart.linePath" />
            </svg>

            <div class="card-bottom">
              <div class="metric-row">
                <div class="segment-list">
                  <span
                    v-for="segment in card.segments"
                    :key="segment.key"
                    class="segment-pill"
                    :title="segment.label"
                  >
                    <span
                      class="segment-dot"
                      :style="{
                        backgroundColor: segment.color,
                        boxShadow: segment.glow,
                      }"
                    />
                    {{ segment.value }}
                  </span>
                </div>

                <div class="total-votes">
                  {{ text.totalVotes }}
                  <strong>{{ card.totalVotes }}</strong>
                </div>
              </div>

              <div class="stacked-bar" :aria-label="text.distribution">
                <span
                  v-for="segment in card.segments"
                  :key="`${card.id}-${segment.key}`"
                  class="stack-segment"
                  :style="{
                    width: `${segment.percent}%`,
                    backgroundColor: segment.color,
                  }"
                />
              </div>
            </div>
          </div>
        </article>
      </div>
    </div>

    <div class="board-toast-stack" aria-live="polite" aria-atomic="true">
      <div v-if="toastMessage" class="board-toast" role="status">
        {{ toastMessage }}
      </div>
    </div>
  </section>
</template>

<style scoped>
.monitor-board {
  --monitor-panel: rgba(12, 12, 14, 0.96);
  --monitor-border: rgba(255, 255, 255, 0.08);
  --monitor-border-strong: rgba(255, 255, 255, 0.14);
  --monitor-copy: rgba(245, 245, 246, 0.96);
  --monitor-muted: rgba(163, 163, 168, 0.78);
  color: var(--monitor-copy);
}

.board-shell {
  position: relative;
  overflow: visible;
  border: 1px solid var(--monitor-border);
  border-radius: 32px;
  padding: 28px;
  background:
    radial-gradient(circle at top right, rgba(255, 255, 255, 0.08), transparent 26%),
    radial-gradient(circle at left center, rgba(88, 28, 135, 0.24), transparent 32%),
    linear-gradient(180deg, rgba(10, 10, 11, 0.98), rgba(5, 5, 5, 0.98));
  box-shadow:
    0 24px 100px rgba(0, 0, 0, 0.48),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.board-shell::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.55), transparent 88%);
  pointer-events: none;
}

.board-header,
.card-grid {
  position: relative;
  z-index: 1;
}

.board-header {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 28px;
}

.board-copy {
  max-width: 680px;
}

.board-copy h1 {
  margin: 0;
  border: 0;
  padding: 0;
  color: #fafafa;
  font-size: clamp(2rem, 4vw, 2.75rem);
  line-height: 1.08;
  letter-spacing: -0.04em;
}

.board-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-self: flex-start;
}

.summary-chip {
  min-width: 124px;
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(14px);
}

.summary-chip span {
  color: rgba(255, 255, 255, 0.56);
  font-size: 0.72rem;
  line-height: 1;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.summary-chip strong {
  font-size: 1rem;
  font-weight: 600;
}

.summary-chip.is-error {
  border-color: rgba(248, 113, 113, 0.34);
  background: rgba(127, 29, 29, 0.24);
}

.summary-chip.is-pending {
  border-color: rgba(96, 165, 250, 0.28);
  background: rgba(30, 41, 59, 0.72);
}

.board-alert {
  position: relative;
  z-index: 1;
  margin: -6px 0 20px;
  padding: 12px 14px;
  border: 1px solid rgba(248, 113, 113, 0.24);
  border-radius: 16px;
  background: rgba(127, 29, 29, 0.18);
  color: rgba(254, 226, 226, 0.94);
  font-size: 0.84rem;
  line-height: 1.4;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.status-card {
  --monitor-avatar-left: 50%;
  --monitor-avatar-bottom: calc(100% - 5px);
  --monitor-avatar-width: 180px;
  --monitor-shell-height: calc(var(--monitor-avatar-width) * 0.605);
  --monitor-card-border-color: var(--monitor-border);
  --monitor-card-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 12px 40px rgba(0, 0, 0, 0.3);
  --monitor-bubble-gap: 12px;
  --monitor-guide-width: 92px;
  --monitor-guide-height: 54px;
  --monitor-action-width: 88px;
  --monitor-action-height: 52px;
  --monitor-action-radius: calc((var(--monitor-avatar-width) + var(--monitor-action-width)) / 2 + var(--monitor-bubble-gap));
  --monitor-action-center-x: 50%;
  --monitor-action-center-y: 50%;
  --monitor-pop-start-scale: 0.88;
  --monitor-pop-peak-scale: 1.03;
  --monitor-pop-rebound-scale: 0.99;
  --monitor-pop-settle-scale: 1.01;
  position: relative;
  overflow: visible;
  border: 1px solid transparent;
  border-radius: 26px;
  padding: 20px 22px;
  background: transparent;
  box-shadow: none;
  animation: card-in 560ms cubic-bezier(0.22, 1, 0.36, 1) both;
  animation-delay: var(--monitor-delay);
  isolation: isolate;
  transition:
    transform 220ms ease,
    opacity 220ms ease,
    filter 220ms ease;
}

.status-card::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: var(--monitor-card-layer);
  border: 1px solid var(--monitor-card-border-color);
  border-radius: inherit;
  background: var(--monitor-panel);
  box-shadow: var(--monitor-card-shadow);
  pointer-events: none;
  transition:
    border-color 220ms ease,
    box-shadow 220ms ease;
}

.status-card.is-clickable {
  cursor: pointer;
}

.status-card.is-completed {
  --monitor-card-border-color: var(--monitor-completed-border);
  cursor: not-allowed;
}

.status-card.is-completed:hover {
  --monitor-card-border-color: var(--monitor-completed-border);
  transform: none;
}

.status-card.is-clickable:focus-visible {
  outline: none;
  --monitor-card-border-color: rgba(255, 255, 255, 0.22);
  --monitor-card-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.08),
    0 0 0 4px rgba(255, 255, 255, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 12px 40px rgba(0, 0, 0, 0.3);
}

.status-card:hover {
  --monitor-card-border-color: var(--monitor-border-strong);
  transform: translateY(-2px);
}

.status-card:is(:hover, :focus-within),
.status-card.is-locked {
  z-index: 3;
}

.status-card.is-locked {
  transform: translateY(-4px);
  --monitor-card-border-color: rgba(255, 255, 255, 0.22);
  --monitor-card-shadow:
    0 24px 72px rgba(0, 0, 0, 0.46),
    0 0 0 1px rgba(255, 255, 255, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

.card-grid.has-active-card .status-card.is-dimmed {
  opacity: 0.28;
  filter: blur(7px) saturate(0.4);
  transform: scale(0.97);
  pointer-events: none;
  user-select: none;
}

.card-monitor-shell,
.card-monitor-overlay {
  position: absolute;
  left: var(--monitor-avatar-left);
  bottom: var(--monitor-avatar-bottom);
  width: var(--monitor-avatar-width);
  aspect-ratio: 516 / 312;
  overflow: visible;
  pointer-events: none;
}

.card-monitor-shell {
  z-index: var(--monitor-preview-layer-under);
  opacity: 0;
  transform: translateX(-50%) translateY(var(--monitor-pop-start-y)) scale(var(--monitor-pop-start-scale));
  transform-origin: bottom center;
  transition:
    opacity 180ms ease,
    transform 260ms ease;
}

.card-monitor-overlay {
  z-index: var(--monitor-preview-layer-over);
  transform: translateX(-50%);
}

.card-monitor {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  pointer-events: none;
  user-select: none;
  object-fit: contain;
  filter: drop-shadow(0 14px 28px rgba(0, 0, 0, 0.34));
}

.status-card:not(.is-completed):not(.is-dimmed):is(:hover, :focus-within) .card-monitor-shell,
.status-card.is-locked .card-monitor-shell {
  opacity: 1;
  animation:
    card-monitor-pop 760ms cubic-bezier(0.16, 1, 0.3, 1) both,
    card-monitor-layer-pop 760ms linear both;
}

.status-card.is-completed .card-monitor {
  filter: grayscale(0.14) saturate(0.82) drop-shadow(0 10px 22px rgba(0, 0, 0, 0.28));
}

.status-card.is-completed:not(.is-dimmed):is(:hover, :focus-within) .card-monitor-shell {
  z-index: var(--monitor-preview-layer-over);
  opacity: 0.72;
  transform: translateX(-50%) translateY(2px) scale(0.94);
}

.bubble-guide {
  position: absolute;
  left: var(--monitor-action-center-x);
  top: var(--monitor-action-center-y);
  z-index: 1;
  display: grid;
  place-items: center;
  width: var(--monitor-guide-width);
  height: var(--monitor-guide-height);
  opacity: 0;
  transform: translate(
    calc(-50% + var(--guide-offset-x)),
    calc(-50% + var(--guide-offset-y) + 14px)
  ) scale(0.92);
  pointer-events: none;
}

.bubble-guide-art,
.bubble-action-art {
  display: block;
  width: 100%;
  height: 100%;
}

.bubble-guide-art {
  filter: drop-shadow(0 16px 22px rgba(0, 0, 0, 0.28));
}

.bubble-guide-label,
.bubble-action-label {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 0.25rem 0.7rem 0.7rem;
  text-align: center;
  letter-spacing: 0.01em;
}

.bubble-guide-label {
  color: rgba(9, 9, 11, 0.92);
  font-size: 0.68rem;
  font-weight: 700;
}

.status-card:not(.is-dimmed):is(:hover, :focus-within):not(.is-locked):not(.is-completed) .bubble-guide {
  animation:
    bubble-guide-in 240ms ease 760ms both,
    bubble-guide-float 1800ms ease-in-out 1040ms infinite;
}

.bubble-action-stack {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
}

.bubble-action {
  --bubble-reveal-offset-y: 12px;
  --bubble-interaction-y: 0px;
  --bubble-scale: 0.88;
  position: absolute;
  left: var(--monitor-action-center-x);
  top: var(--monitor-action-center-y);
  width: var(--monitor-action-width);
  height: var(--monitor-action-height);
  border: 0;
  padding: 0;
  background: transparent;
  opacity: 0;
  transform: translate(
    calc(-50% + var(--bubble-offset-x)),
    calc(-50% + var(--bubble-offset-y) + var(--bubble-reveal-offset-y) + var(--bubble-interaction-y))
  ) scale(var(--bubble-scale));
  cursor: pointer;
  pointer-events: none;
  transition:
    transform 220ms ease,
    opacity 220ms ease;
  transition-delay: var(--bubble-delay);
}

.bubble-action-art {
  filter: drop-shadow(0 14px 24px rgba(0, 0, 0, 0.32));
}

.bubble-action-label {
  color: rgba(10, 10, 11, 0.94);
  font-size: 0.68rem;
  font-weight: 800;
}

.bubble-action:hover,
.bubble-action:focus-visible {
  --bubble-interaction-y: 6px;
  --bubble-scale: 1.04;
}

.bubble-action:focus-visible {
  outline: none;
}

.bubble-action:active {
  --bubble-interaction-y: 8px;
  --bubble-scale: 0.98;
}

.status-card.is-locked:not(.is-completed) .bubble-action {
  opacity: 1;
  --bubble-reveal-offset-y: 0px;
  --bubble-scale: 1;
  pointer-events: auto;
}

.status-card.is-locked:not(.is-completed) .bubble-action-stack {
  pointer-events: auto;
}

.card-layout {
  position: relative;
  z-index: var(--monitor-card-layer);
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr);
  grid-template-rows: 52px minmax(56px, auto);
  align-items: center;
  column-gap: 20px;
  row-gap: 12px;
}

.site-link {
  display: flex;
  grid-row: 1 / span 2;
  width: 104px;
  height: 104px;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  text-decoration: none;
  transition: transform 180ms ease, opacity 180ms ease;
}

.site-link:hover {
  transform: translateY(-1px);
  opacity: 0.92;
}

.site-icon {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.sparkline {
  display: block;
  width: 100%;
  height: 52px;
  min-width: 0;
}

.sparkline-area {
  opacity: 0.96;
}

.sparkline-line {
  fill: none;
  stroke: var(--monitor-accent);
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.card-bottom {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 12px;
}

.metric-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-end;
}

.segment-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  color: rgba(255, 255, 255, 0.7);
  font-size: 0.78rem;
  line-height: 1;
}

.segment-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.segment-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
}

.total-votes {
  color: rgba(255, 255, 255, 0.5);
  font-size: 0.76rem;
  line-height: 1;
}

.total-votes strong {
  margin-left: 6px;
  color: rgba(255, 255, 255, 0.94);
  font-size: 0.88rem;
}

.stacked-bar {
  display: flex;
  height: 14px;
  overflow: hidden;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.05);
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.45);
}

.stack-segment {
  position: relative;
  min-width: 0;
}

.stack-segment::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.22), transparent);
}

.board-toast-stack {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 30;
  display: flex;
  justify-content: flex-end;
  pointer-events: none;
}

.board-toast {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 88px;
  padding: 0.72rem 0.96rem;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 999px;
  background: rgba(9, 9, 11, 0.88);
  color: rgba(250, 250, 250, 0.96);
  font-size: 0.82rem;
  font-weight: 600;
  letter-spacing: 0.01em;
  box-shadow: 0 18px 42px rgba(0, 0, 0, 0.34);
  backdrop-filter: blur(16px);
  animation: toast-in 180ms ease both;
}

@keyframes card-in {
  from {
    opacity: 0;
    transform: translateY(20px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes card-monitor-pop {
  0% {
    opacity: 0;
    transform: translateX(-50%) translateY(var(--monitor-pop-start-y)) scale(var(--monitor-pop-start-scale));
  }

  38% {
    opacity: 1;
    transform: translateX(-50%) translateY(var(--monitor-pop-apex-y)) scale(var(--monitor-pop-peak-scale));
  }

  56% {
    transform: translateX(-50%) translateY(var(--monitor-pop-rebound-y)) scale(var(--monitor-pop-rebound-scale));
  }

  72% {
    transform: translateX(-50%) translateY(var(--monitor-pop-settle-y)) scale(var(--monitor-pop-settle-scale));
  }

  100% {
    opacity: 1;
    transform: translateX(-50%) translateY(var(--monitor-pop-end-y)) scale(1);
  }
}

@keyframes card-monitor-layer-pop {
  0%,
  37.99% {
    z-index: var(--monitor-preview-layer-under);
  }

  38%,
  100% {
    z-index: var(--monitor-preview-layer-over);
  }
}

@keyframes bubble-guide-in {
  from {
    opacity: 0;
    transform: translate(
      calc(-50% + var(--guide-offset-x)),
      calc(-50% + var(--guide-offset-y) + 14px)
    ) scale(0.92);
  }

  to {
    opacity: 1;
    transform: translate(
      calc(-50% + var(--guide-offset-x)),
      calc(-50% + var(--guide-offset-y))
    ) scale(1);
  }
}

@keyframes bubble-guide-float {
  0%,
  100% {
    transform: translate(
      calc(-50% + var(--guide-offset-x)),
      calc(-50% + var(--guide-offset-y))
    ) scale(1);
  }

  50% {
    transform: translate(
      calc(-50% + var(--guide-offset-x)),
      calc(-50% + var(--guide-offset-y) - 4px)
    ) scale(1);
  }
}

@keyframes toast-in {
  from {
    opacity: 0;
    transform: translateY(10px) scale(0.96);
  }

  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@media (max-width: 980px) {
  .card-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .board-shell {
    padding: 22px;
    border-radius: 24px;
  }

  .status-card {
    --monitor-avatar-width: 96px;
    --monitor-bubble-gap: 8px;
    --monitor-guide-width: 84px;
    --monitor-guide-height: 48px;
    --monitor-action-width: 78px;
    --monitor-action-height: 46px;
  }

  .card-layout {
    grid-template-columns: 88px minmax(0, 1fr);
    grid-template-rows: 48px minmax(54px, auto);
    column-gap: 16px;
  }

  .site-link {
    width: 88px;
    height: 88px;
  }

  .sparkline {
    height: 48px;
  }
}

@media (max-width: 540px) {
  .board-shell {
    padding: 18px;
  }

  .status-card {
    --monitor-avatar-width: 84px;
    --monitor-bubble-gap: 6px;
    --monitor-guide-width: 74px;
    --monitor-guide-height: 42px;
    --monitor-action-width: 68px;
    --monitor-action-height: 40px;
    padding: 18px;
  }

  .card-layout {
    grid-template-columns: 72px minmax(0, 1fr);
    grid-template-rows: 42px minmax(52px, auto);
    column-gap: 14px;
    row-gap: 10px;
  }

  .site-link {
    width: 72px;
    height: 72px;
  }

  .sparkline {
    height: 42px;
  }

  .metric-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .board-toast-stack {
    right: 14px;
    bottom: 14px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .status-card {
    animation: none;
  }

  .status-card:hover {
    transform: none;
  }

  .card-monitor-shell {
    transition: opacity 120ms ease;
  }

  .status-card:not(.is-completed):not(.is-dimmed):is(:hover, :focus-within) .card-monitor-shell,
  .status-card.is-locked .card-monitor-shell {
    animation: none;
    z-index: var(--monitor-preview-layer-over);
    opacity: 1;
    transform: translateX(-50%) translateY(var(--monitor-pop-end-y)) scale(1);
  }

  .status-card.is-completed:not(.is-dimmed):is(:hover, :focus-within) .card-monitor-shell {
    animation: none;
    z-index: var(--monitor-preview-layer-over);
    opacity: 0.72;
    transform: translateX(-50%) translateY(2px) scale(0.94);
  }

  .status-card:not(.is-dimmed):is(:hover, :focus-within):not(.is-locked):not(.is-completed) .bubble-guide {
    animation: none;
    opacity: 1;
    transform: translate(
      calc(-50% + var(--guide-offset-x)),
      calc(-50% + var(--guide-offset-y))
    ) scale(1);
  }

  .status-card.is-locked:not(.is-completed) .bubble-action {
    animation: none;
    opacity: 1;
    --bubble-reveal-offset-y: 0px;
    --bubble-scale: 1;
  }

  .board-toast {
    animation: none;
  }
}
</style>

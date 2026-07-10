<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  createEmptyMonitorBoardRuntimeData,
  emptyMonitorBoardLiveStatus,
  getMonitorBoardVoteMatrixKey,
  monitorBoardIsps,
  monitorBoardCopy,
  monitorBoardVoteKeys,
  sumMonitorBoardVoteMatrixByVote,
  needProxySites,
  type MonitorBoardLocale,
  type MonitorBoardRuntimeData,
  monitorBoardSites,
  type MonitorBoardIsp,
  type MonitorBoardIspKey,
  type MonitorBoardLiveStatus,
  type MonitorBoardStatusMap,
  type MonitorBoardUptimes,
  type MonitorBoardVoteMatrix,
  type MonitorBoardVoteKey,
  type MonitorBoardVotes,
} from './monitorStatusBoardSource'
import {
  fetchMonitorBoardRuntimeData,
  MonitorBoardApiError,
  submitMonitorBoardVote,
} from './monitorBoardApi'

const hoverAvatarSrc = new URL('../../../assets/img/icons/monitor.png', import.meta.url).href
const downBubbleSrc = new URL('../../../assets/img/monitor/down.png', import.meta.url).href
const guideBubbleSrc = new URL('../../../assets/img/monitor/guide.webp', import.meta.url).href
const neutralBubbleSrc = new URL('../../../assets/img/monitor/neutral.png', import.meta.url).href
const upBubbleSrc = new URL('../../../assets/img/monitor/up.png', import.meta.url).href

const props = withDefaults(defineProps<{
  locale?: MonitorBoardLocale
  resetDate?: string
  resetStartedAt?: string
  statusMap?: MonitorBoardStatusMap
  apiBaseUrl?: string
}>(), {
  locale: 'zh',
})

type MonitorBoardLocalStageEntry = {
  action: MonitorBoardVoteKey
  state_isp: MonitorBoardIspKey
  completedAt: string
}

type MonitorBoardLocalStageMap = Partial<Record<string, MonitorBoardLocalStageEntry>>

type MonitorBoardPendingIspSelection = {
  cardId: string
  action: MonitorBoardVoteKey
}

type MonitorBoardLoadState = 'idle' | 'loading' | 'ready' | 'error'

type MonitorBoardOrbitPosition = {
  offsetX: number
  offsetY: number
}

type MonitorBoardBubbleConfig = MonitorBoardOrbitPosition & {
  key: MonitorBoardVoteKey
  assetSrc: string
}

type MonitorBoardVoteMeta = {
  assetSrc: string
  color: string
  glow: string
  angleDeg: number
}

type MonitorBoardChartLine = {
  key: MonitorBoardVoteKey
  linePath: string
  color: string
  zIndex: number
}

type MonitorBoardSegment = {
  key: MonitorBoardVoteKey
  value: number
  color: string
  glow: string
  percent: number
}

type MonitorBoardIspSignalCell = {
  key: MonitorBoardVoteKey
  value: number
  color: string
  glow: string
  strength: number
}

type MonitorBoardIspSignalRow = {
  isp: MonitorBoardIsp
  cells: MonitorBoardIspSignalCell[]
}

const MONITOR_VOTE_DISABLED_STORAGE_KEY = 'monitor-board-vote-disabled:v1'
const MONITOR_SELECTED_ISP_STORAGE_KEY = 'monitor-board-selected-isp:v1'
const MONITOR_CHART_MIN_VALUE = 0
const MONITOR_CHART_LAYER_OFFSETS = [20, 40, 60] as const
const MONITOR_CHART_EMA_DECAY = 0.75

function buildChartLinePath(values: number[], chartMax: number, width = 112, height = 40, padding = 4): string {
  const floor = height - padding
  const chartValues = values.length === 0
    ? [MONITOR_CHART_MIN_VALUE, MONITOR_CHART_MIN_VALUE]
    : values.length === 1
      ? [values[0], values[0]]
      : values
  const usableHeight = height - padding * 2
  const span = Math.max(chartMax - MONITOR_CHART_MIN_VALUE, 1)
  const step = (width - padding * 2) / Math.max(chartValues.length - 1, 1)

  const points = chartValues.map((value, index) => {
    const x = padding + step * index
    const normalized = (Math.max(value, MONITOR_CHART_MIN_VALUE) - MONITOR_CHART_MIN_VALUE) / span
    const y = floor - normalized * usableHeight
    return {
      x: Number(x.toFixed(2)),
      y: Number(y.toFixed(2)),
    }
  })

  const linePath = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
    .join(' ')

  return linePath
}

function buildChartLines(cumulativeUptimes: MonitorBoardUptimes): MonitorBoardChartLine[] {
  if (cumulativeUptimes.length < 2) {
    return []
  }

  const cumulativeVotes = cumulativeUptimes.map((sample) => sumMonitorBoardVoteMatrixByVote(sample))
  const len = cumulativeVotes.length - 1
  let prev = cumulativeVotes[0]
  let chartMax = 1
  const emaSamples: MonitorBoardVotes[] = new Array(len)
  let emaUp = 0
  let emaNeutral = 0
  let emaDown = 0

  for (let i = 0; i < len; i++) {
    const curr = cumulativeVotes[i + 1]
    const diffUp = curr.up - prev.up
    const diffNeutral = curr.neutral - prev.neutral
    const diffDown = curr.down - prev.down
    prev = curr

    emaUp = emaUp * MONITOR_CHART_EMA_DECAY + diffUp
    emaNeutral = emaNeutral * MONITOR_CHART_EMA_DECAY + diffNeutral
    emaDown = emaDown * MONITOR_CHART_EMA_DECAY + diffDown

    const sample: MonitorBoardVotes = { up: emaUp, neutral: emaNeutral, down: emaDown }
    emaSamples[i] = sample

    if (emaUp > chartMax) chartMax = emaUp
    if (emaNeutral > chartMax) chartMax = emaNeutral
    if (emaDown > chartMax) chartMax = emaDown
  }

  const latestSample = emaSamples[len - 1]
  const orderedKeys = [...monitorVoteKeys].sort((leftKey, rightKey) => {
    const valueDelta = latestSample[leftKey] - latestSample[rightKey]
    if (valueDelta !== 0) {
      return valueDelta
    }
    return monitorVoteKeys.indexOf(leftKey) - monitorVoteKeys.indexOf(rightKey)
  })

  return orderedKeys.map((key, index) => ({
    key,
    color: monitorVoteMetaMap[key].color,
    linePath: buildChartLinePath(emaSamples.map((sample) => sample[key]), chartMax),
    zIndex: MONITOR_CARD_LAYER + MONITOR_CHART_LAYER_OFFSETS[index],
  }))
}

function cloneStatusMap(statusMap: MonitorBoardStatusMap): Record<string, MonitorBoardLiveStatus> {
  return Object.fromEntries(
    Object.entries(statusMap).map(([siteId, liveStatus]) => [
      siteId,
      {
        uptimes: liveStatus.uptimes.map((sample) => ({ ...sample })),
        votes: { ...liveStatus.votes },
      },
    ]),
  )
}

const text = computed(() => monitorBoardCopy[props.locale])
const completedToastLabel = computed(() => props.locale === 'zh' ? '已投票' : 'Voted')
const boardRoot = ref<HTMLElement | null>(null)
const selectedIsp = ref<MonitorBoardIspKey | null>(null)
const remoteRuntimeData = ref<MonitorBoardRuntimeData | null>(null)
const loadState = ref<MonitorBoardLoadState>('idle')
const loadErrorMessage = ref<string | null>(null)
const localStageMap = ref<MonitorBoardLocalStageMap>({})
const pendingStageMap = ref<MonitorBoardLocalStageMap>({})
const pendingIspSelection = ref<MonitorBoardPendingIspSelection | null>(null)
const voteDisabledDetail = ref<string | null>(null)
const activeCardId = ref<string | null>(null)
const toastMessage = ref<string | null>(null)

const providedRuntimeData = computed<MonitorBoardRuntimeData | null>(() => {
  if (props.resetDate === undefined && props.statusMap === undefined) {
    return null
  }

  return {
    resetDate: props.resetDate ?? createEmptyMonitorBoardRuntimeData().resetDate,
    resetStartedAt: props.resetStartedAt ?? createEmptyMonitorBoardRuntimeData().resetStartedAt,
    statusMap: cloneStatusMap(props.statusMap ?? {}),
  }
})

const runtimeData = computed<MonitorBoardRuntimeData>(() => (
  providedRuntimeData.value
  ?? remoteRuntimeData.value
  ?? createEmptyMonitorBoardRuntimeData()
))
const resetDate = computed(() => runtimeData.value.resetDate)
const resetStartedAt = computed(() => runtimeData.value.resetStartedAt)
const displayStageMap = computed<MonitorBoardLocalStageMap>(() => ({
  ...localStageMap.value,
  ...pendingStageMap.value,
}))
const effectiveApiBaseUrl = computed(() => {
  return typeof props.apiBaseUrl === 'string' && props.apiBaseUrl.trim() !== ''
    ? props.apiBaseUrl.trim()
    : undefined
})
const localStageStorageKey = computed(() => `monitor-board-local-stage:${resetStartedAt.value ?? 'default'}`)
const hasActiveCard = computed(() => activeCardId.value !== null)
const hasIspFocus = computed(() => pendingIspSelection.value !== null)
const hasPendingSubmission = computed(() => Object.keys(pendingStageMap.value).length > 0)
const voteDisabledToastLabel = computed(() => (
  voteDisabledDetail.value ? buildSubmitFailedToast(voteDisabledDetail.value) : null
))
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

const TOAST_TIMEOUT_MS = 2400
const MONITOR_BUBBLE_RADIUS_PX = 120
const MONITOR_NEUTRAL_BUBBLE_ANGLE_DEG = 30
const MONITOR_CARD_LAYER = 400
const MONITOR_CARD_OVERLAY_LAYER = MONITOR_CARD_LAYER + 1
const MONITOR_PREVIEW_LAYER_UNDER = 200
const MONITOR_PREVIEW_LAYER_OVER = 600
const MONITOR_PREVIEW_START_Y_PX = 100
const MONITOR_PREVIEW_APEX_Y_PX = -1
const MONITOR_PREVIEW_REBOUND_Y_PX = 4
const MONITOR_PREVIEW_SETTLE_Y_PX = -1
const MONITOR_PREVIEW_END_Y_PX = 0
const monitorVoteKeys = monitorBoardVoteKeys

const monitorPreviewMotionStyle = {
  '--monitor-card-layer': `${MONITOR_CARD_LAYER}`,
  '--monitor-card-overlay-layer': `${MONITOR_CARD_OVERLAY_LAYER}`,
  '--monitor-preview-layer-under': `${MONITOR_PREVIEW_LAYER_UNDER}`,
  '--monitor-preview-layer-over': `${MONITOR_PREVIEW_LAYER_OVER}`,
  '--monitor-pop-start-y': `${MONITOR_PREVIEW_START_Y_PX}px`,
  '--monitor-pop-apex-y': `${MONITOR_PREVIEW_APEX_Y_PX}px`,
  '--monitor-pop-rebound-y': `${MONITOR_PREVIEW_REBOUND_Y_PX}px`,
  '--monitor-pop-settle-y': `${MONITOR_PREVIEW_SETTLE_Y_PX}px`,
  '--monitor-pop-end-y': `${MONITOR_PREVIEW_END_Y_PX}px`,
} as const

const monitorVoteMetaMap: Record<MonitorBoardVoteKey, MonitorBoardVoteMeta> = {
  up: {
    assetSrc: upBubbleSrc,
    color: '#10b981',
    glow: '0 0 12px rgba(16, 185, 129, 0.52)',
    angleDeg: 180,
  },
  neutral: {
    assetSrc: neutralBubbleSrc,
    color: '#f59e0b',
    glow: '0 0 12px rgba(245, 158, 11, 0.42)',
    angleDeg: MONITOR_NEUTRAL_BUBBLE_ANGLE_DEG,
  },
  down: {
    assetSrc: downBubbleSrc,
    color: '#f43f5e',
    glow: '0 0 12px rgba(244, 63, 94, 0.44)',
    angleDeg: 0,
  },
}

function buildBubbleOrbit(angleDeg: number, radiusPx: number): MonitorBoardOrbitPosition {
  const radians = angleDeg * Math.PI / 180
  return {
    offsetX: Number((Math.cos(radians) * radiusPx).toFixed(2)),
    offsetY: Number((Math.sin(radians) * radiusPx * -1).toFixed(2)),
  }
}

const bubbleConfigs: MonitorBoardBubbleConfig[] = monitorVoteKeys.map((key) => {
  const meta = monitorVoteMetaMap[key]
  return {
    key,
    assetSrc: meta.assetSrc,
    ...buildBubbleOrbit(meta.angleDeg, MONITOR_BUBBLE_RADIUS_PX),
  }
})

const guideBubbleConfig = buildBubbleOrbit(MONITOR_NEUTRAL_BUBBLE_ANGLE_DEG, MONITOR_BUBBLE_RADIUS_PX)

function buildVoteSegments(votes: MonitorBoardVotes): MonitorBoardSegment[] {
  const totalVotes = votes.up + votes.neutral + votes.down
  return monitorVoteKeys.map((key) => {
    const meta = monitorVoteMetaMap[key]
    return {
      key,
      value: votes[key],
      color: meta.color,
      glow: meta.glow,
      percent: totalVotes === 0 ? 0 : (votes[key] / totalVotes) * 100,
    }
  })
}

function buildIspSignalRows(votes: MonitorBoardVoteMatrix): MonitorBoardIspSignalRow[] {
  const maxValue = Math.max(
    1,
    ...monitorBoardIsps.flatMap((isp) => (
      monitorVoteKeys.map((key) => votes[getMonitorBoardVoteMatrixKey(key, isp.id)])
    )),
  )

  return monitorBoardIsps.reduce<MonitorBoardIspSignalRow[]>((rows, isp) => {
    const cells = monitorVoteKeys.map((key) => {
      const meta = monitorVoteMetaMap[key]
      const value = votes[getMonitorBoardVoteMatrixKey(key, isp.id)]
      return {
        key,
        value,
        color: meta.color,
        glow: meta.glow,
        strength: value === 0 ? 0 : Math.max(0.24, value / maxValue),
      }
    })
    const total = cells.reduce((sum, cell) => sum + cell.value, 0)
    if (total > 0) rows.push({ isp, cells })
    return rows
  }, [])
}

let toastTimer: number | null = null

function isMonitorBoardVoteKey(value: unknown): value is MonitorBoardVoteKey {
  return value === 'up' || value === 'neutral' || value === 'down'
}

function isMonitorBoardIspKey(value: unknown): value is MonitorBoardIspKey {
  return value === 'telecom' || value === 'mobile' || value === 'unicom'
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
        const state_isp = (stage as { state_isp?: unknown }).state_isp
        const completedAt = (stage as { completedAt?: unknown }).completedAt
        if (!isMonitorBoardVoteKey(action) || typeof completedAt !== 'string') {
          return []
        }

        return [[siteId, {
          action,
          state_isp: isMonitorBoardIspKey(state_isp) ? state_isp : 'telecom',
          completedAt,
        }]]
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

function readSelectedIsp(storageKey: string): MonitorBoardIspKey | null {
  if (typeof window === 'undefined') {
    return null
  }

  const rawValue = window.localStorage.getItem(storageKey)
  return isMonitorBoardIspKey(rawValue) ? rawValue : null
}

function writeSelectedIsp(storageKey: string, _ispKey: MonitorBoardIspKey): void {
  if (typeof window === 'undefined') {
    return
  }

  window.localStorage.setItem(storageKey, _ispKey)
}

function readVoteDisabledDetail(storageKey: string): string | null {
  if (typeof window === 'undefined') {
    return null
  }

  const detail = window.localStorage.getItem(storageKey)
  return typeof detail === 'string' && detail.trim() !== '' ? detail : null
}

function writeVoteDisabledDetail(storageKey: string, detail: string): void {
  if (typeof window === 'undefined') {
    return
  }

  window.localStorage.setItem(storageKey, detail)
}

function syncLocalStageMap(): void {
  localStageMap.value = readLocalStageMap(localStageStorageKey.value)
}

function syncSelectedIsp(): void {
  selectedIsp.value = readSelectedIsp(MONITOR_SELECTED_ISP_STORAGE_KEY)
}

function syncVoteDisabledDetail(): void {
  voteDisabledDetail.value = readVoteDisabledDetail(MONITOR_VOTE_DISABLED_STORAGE_KEY)
}

function buildSubmitFailedToast(detail: string): string {
  return `${text.value.submitFailed}: ${detail}`
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
  return displayStageMap.value[cardId] != null
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

function submitVote(cardId: string, action: MonitorBoardVoteKey, _stateIsp: MonitorBoardIspKey): void {
  if (voteDisabledToastLabel.value) {
    clearActiveCard()
    showToast(voteDisabledToastLabel.value)
    return
  }

  const stageEntry: MonitorBoardLocalStageEntry = {
    action,
    state_isp: _stateIsp,
    completedAt: new Date().toISOString(),
  }

  setPendingStage(cardId, stageEntry)
  clearActiveCard()

  void submitMonitorBoardVote({
    siteId: cardId,
    action,
    state_isp: _stateIsp,
    delta: 1,
  }, effectiveApiBaseUrl.value)
    .then(() => {
      if (!providedRuntimeData.value) {
        const currentRuntimeData = remoteRuntimeData.value
          ?? createEmptyMonitorBoardRuntimeData(resetDate.value, resetStartedAt.value)
        const currentLiveStatus = currentRuntimeData.statusMap[cardId] ?? emptyMonitorBoardLiveStatus
        const matrixKey = getMonitorBoardVoteMatrixKey(action, _stateIsp)

        remoteRuntimeData.value = {
          resetDate: currentRuntimeData.resetDate,
          resetStartedAt: currentRuntimeData.resetStartedAt,
          statusMap: {
            ...currentRuntimeData.statusMap,
            [cardId]: {
              uptimes: currentLiveStatus.uptimes.map((sample) => ({ ...sample })),
              votes: {
                ...currentLiveStatus.votes,
                [matrixKey]: currentLiveStatus.votes[matrixKey] + 1,
              },
            },
          },
        }
      }

      commitLocalStage(cardId, stageEntry)
      showToast(text.value.submitSuccess)
    })
    .catch((error: unknown) => {
      const detail = error instanceof Error ? error.message : text.value.retryHint
      if (error instanceof MonitorBoardApiError && error.status === 406) {
        voteDisabledDetail.value = detail
        writeVoteDisabledDetail(MONITOR_VOTE_DISABLED_STORAGE_KEY, detail)
      }
      console.error('Failed to submit monitor board vote.', error)
      showToast(buildSubmitFailedToast(detail))
    })
    .finally(() => {
      setPendingStage(cardId, null)
    })
}

function closeIspFocus(): void {
  pendingIspSelection.value = null
}

function handleIspFocusDismiss(): void {
  closeIspFocus()
  clearActiveCard()
}

function handleIspSelect(_ispKey: MonitorBoardIspKey): void {
  const pendingVote = pendingIspSelection.value
  if (!pendingVote) {
    return
  }

  selectedIsp.value = _ispKey
  writeSelectedIsp(MONITOR_SELECTED_ISP_STORAGE_KEY, _ispKey)
  closeIspFocus()
  submitVote(pendingVote.cardId, pendingVote.action, _ispKey)
}

function handleBubbleVote(cardId: string, action: MonitorBoardVoteKey): void {
  if (voteDisabledToastLabel.value) {
    clearActiveCard()
    showToast(voteDisabledToastLabel.value)
    return
  }

  const _selectedIsp = selectedIsp.value
  if (!_selectedIsp) {
    pendingIspSelection.value = { cardId, action }
    return
  }

  submitVote(cardId, action, _selectedIsp)
}

function handleDocumentPointerDown(event: PointerEvent): void {
  if (hasIspFocus.value || !activeCardId.value || !boardRoot.value) {
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
    if (hasIspFocus.value) {
      handleIspFocusDismiss()
      return
    }
    clearActiveCard()
  }
}

onMounted(() => {
  syncLocalStageMap()
  syncSelectedIsp()
  syncVoteDisabledDetail()
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  document.addEventListener('keydown', handleDocumentKeydown)
  void hydrateRemoteRuntimeData()
})

onBeforeUnmount(() => {
  clearToast()
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  document.removeEventListener('keydown', handleDocumentKeydown)
})

watch(localStageStorageKey, () => {
  clearActiveCard()
  syncLocalStageMap()
})

type MonitorBoardCardWithChart = {
  chartLines: MonitorBoardChartLine[]
  isCompleted: boolean
  completedBorderColor: string
  ispSignalRows: MonitorBoardIspSignalRow[]
  needsProxy: boolean
  segments: MonitorBoardSegment[]
} & typeof monitorBoardSites[number]

const cardsWithCharts = computed<MonitorBoardCardWithChart[]>(() => {
  const statusMap = runtimeData.value.statusMap
  const displayStage = displayStageMap.value
  const pendingStage = pendingStageMap.value

  return monitorBoardSites.map((site) => {
    const liveStatus: MonitorBoardLiveStatus = statusMap[site.id] ?? emptyMonitorBoardLiveStatus
    const stagedVote = displayStage[site.id]
    const pendingVote = pendingStage[site.id]
    const effectiveVoteMatrix: MonitorBoardVoteMatrix = { ...liveStatus.votes }

    if (pendingVote) {
      const matrixKey = getMonitorBoardVoteMatrixKey(pendingVote.action, pendingVote.state_isp)
      effectiveVoteMatrix[matrixKey] += 1
    }
    const effectiveVotes = sumMonitorBoardVoteMatrixByVote(effectiveVoteMatrix)

    return {
      ...site,
      chartLines: buildChartLines(liveStatus.uptimes),
      isCompleted: stagedVote != null,
      completedBorderColor: stagedVote ? monitorVoteMetaMap[stagedVote.action].color : 'transparent',
      ispSignalRows: buildIspSignalRows(effectiveVoteMatrix),
      needsProxy: needProxySites.includes(site.id),
      segments: buildVoteSegments(effectiveVotes),
    }
  })
})

</script>

<template>
  <section ref="boardRoot" class="monitor-board" :class="{ 'has-isp-focus': hasIspFocus }">
    <div class="board-shell">
      <header class="board-header">
        <div class="board-copy">
          <h1>{{ text.title }}</h1>
        </div>

        <div class="board-summary">
          <div class="summary-chip">
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
              <img class="bubble-art" :src="guideBubbleSrc" alt="">
            </div>

            <div class="bubble-action-stack">
              <button
                v-for="(bubble, bubbleIndex) in bubbleConfigs"
                :key="`${card.id}-${bubble.key}`"
                type="button"
                class="bubble-action"
                :style="{
                  '--bubble-delay': `${bubbleIndex * 60}ms`,
                  '--bubble-offset-x': `${bubble.offsetX}px`,
                  '--bubble-offset-y': `${bubble.offsetY}px`,
                }"
                :aria-label="`${card.name} ${bubble.key}`"
                @click.stop="handleBubbleVote(card.id, bubble.key)"
              >
                <img class="bubble-art" :src="bubble.assetSrc" alt="">
              </button>
            </div>
          </div>

          <span
            v-if="card.needsProxy"
            class="vpnBadge"
            role="img"
            aria-label="VPN"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 32 32" aria-hidden="true">
              <path d="M0 0h32v32H0z" fill="none" />
              <path fill="currentColor" d="M14 23h-2V9h6a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-4Zm0-7h4v-5h-4Zm14 3L24.32 9H22v14h2V13l3.68 10H30V9h-2zM8 9L6 22L4 9H2l2.52 14h2.96L10 9z" stroke-width="1" stroke="currentColor" />
            </svg>
          </span>

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

            <div class="sparkline-group" aria-hidden="true">
              <svg
                v-for="series in card.chartLines"
                :key="`${card.id}-${series.key}`"
                class="sparkline"
                viewBox="0 0 112 40"
                preserveAspectRatio="none"
                :style="{ zIndex: String(series.zIndex) }"
              >
                <path
                  class="sparkline-line"
                  :d="series.linePath"
                  :style="{ stroke: series.color }"
                />
              </svg>
            </div>

            <div class="card-bottom">
              <div class="metric-row">
                  
                  <div
                    class="isp-broadcast"
                  >
                    <div
                      v-for="row in card.ispSignalRows"
                      :key="`${card.id}-${row.isp.id}`"
                      class="isp-broadcast-row"
                    >
                      <img
                        class="isp-broadcast-icon"
                        :src="row.isp.iconSrc"
                        :alt="row.isp.name"
                      >
                      <div class="isp-broadcast-cells">
                        <template v-for="(cell, cellIndex) in row.cells" :key="`${card.id}-${row.isp.id}-${cell.key}`">
                          <span
                            class="isp-broadcast-value"
                            :style="{
                              color: cell.color,
                              textShadow: cell.glow,
                            }"
                          >{{ cell.value }}</span>
                          <span
                            v-if="cellIndex < row.cells.length - 1"
                            class="isp-broadcast-separator"
                            aria-hidden="true"
                          >/</span>
                        </template>
                      </div>
                  </div>
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

    <div
      v-if="pendingIspSelection"
      class="isp-focus-layer"
      role="dialog"
      aria-modal="true"
      @click.self="handleIspFocusDismiss"
    >
      <div class="isp-focus-panel">
        <button
          v-for="(isp, ispIndex) in monitorBoardIsps"
          :key="isp.id"
          type="button"
          class="isp-focus-option"
          :style="{ '--isp-focus-delay': `${ispIndex * 70}ms` }"
          :aria-label="isp.name"
          @click="handleIspSelect(isp.id)"
        >
          <img class="isp-focus-icon" :src="isp.iconSrc" :alt="isp.name">
        </button>
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
.monitor-board{--monitor-panel:rgba(12,12,14,0.96);--monitor-border:rgba(255,255,255,0.08);--monitor-border-strong:rgba(255,255,255,0.14);--monitor-copy:rgba(245,245,246,0.96);--monitor-muted:rgba(163,163,168,0.78);color:var(--monitor-copy)}
.board-shell{position:relative;overflow:visible;border:1px solid var(--monitor-border);border-radius:32px;padding:28px;background:radial-gradient(circle at top right,rgba(255,255,255,0.08),transparent 26%),radial-gradient(circle at left center,rgba(88,28,135,0.24),transparent 32%),linear-gradient(180deg,rgba(10,10,11,0.98),rgba(5,5,5,0.98));box-shadow:0 24px 100px rgba(0,0,0,0.48),inset 0 1px 0 rgba(255,255,255,0.04);transition:filter 220ms ease,transform 220ms ease}
.board-shell::before{content:'';position:absolute;inset:0;background-image:linear-gradient(rgba(255,255,255,0.03) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.03) 1px,transparent 1px);background-size:44px 44px;mask-image:linear-gradient(180deg,rgba(0,0,0,0.55),transparent 88%);pointer-events:none}
.board-header,.card-grid{position:relative;z-index:1}
.board-header{display:flex;flex-wrap:wrap;justify-content:space-between;gap:24px;margin-bottom:28px}
.board-copy{display:flex;max-width:680px;align-items:center}
.board-copy h1{margin:0;border:0;padding:0;color:#fafafa;font-size:clamp(2rem,4vw,2.75rem);line-height:1.08;letter-spacing:-0.04em}
.board-summary{display:flex;flex-wrap:wrap;gap:12px;align-self:flex-start}
.summary-chip{min-width:124px;display:grid;gap:6px;padding:14px 16px;border:1px solid rgba(255,255,255,0.09);border-radius:18px;background:rgba(255,255,255,0.04);backdrop-filter:blur(14px)}
.summary-chip strong{font-size:1rem;font-weight:600}
.summary-chip.is-error{border-color:rgba(248,113,113,0.34);background:rgba(127,29,29,0.24)}
.summary-chip.is-pending{border-color:rgba(96,165,250,0.28);background:rgba(30,41,59,0.72)}
.board-alert{position:relative;z-index:1;margin:-6px 0 20px;padding:12px 14px;border:1px solid rgba(248,113,113,0.24);border-radius:16px;background:rgba(127,29,29,0.18);color:rgba(254,226,226,0.94);font-size:0.84rem;line-height:1.4}
.card-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
.monitor-board.has-isp-focus .board-shell{filter:blur(18px) saturate(0.52);transform:scale(0.985)}
.isp-focus-layer{position:fixed;inset:0;z-index:1400;display:grid;place-items:center;padding:24px;background:rgba(0,0,0,0.28);backdrop-filter:blur(18px)}
.isp-focus-panel{
  display: flex;
  align-items: center;
  justify-content: center;
  gap: min(2vw,22px);
}
.isp-focus-option{
  position:relative;display:grid;width:10vw;max-width:136px;max-height:136px;place-items:center;border-radius:38px;cursor:pointer;opacity:0;animation:isp-focus-option-in 320ms cubic-bezier(0.22,1,0.36,1) both;
}
.isp-focus-option::before{content:'';position:absolute;inset:0;border:1px solid rgba(255,255,255,0.14);border-radius:inherit;background:rgba(255,255,255,0.06);box-shadow:0 14px 34px rgba(0,0,0,0.34),inset 0 1px 0 rgba(255,255,255,0.08);transition:transform 180ms ease,border-color 180ms ease,background 180ms ease,box-shadow 180ms ease}
.isp-focus-option:hover::before{transform:translateY(-2px) scale(1.02);border-color:rgba(255,255,255,0.22);background:rgba(255,255,255,0.1)}
.isp-focus-option:focus-visible{outline:none}
.isp-focus-option:focus-visible::before{border-color:rgba(255,255,255,0.28);box-shadow:0 0 0 4px rgba(255,255,255,0.08),0 14px 34px rgba(0,0,0,0.34),inset 0 1px 0 rgba(255,255,255,0.08)}
.isp-focus-option:active::before{transform:scale(0.97)}
.isp-focus-icon{
  position:relative;z-index:1;display:block;width:100%;height:100%;padding:10%;object-fit:contain;filter:drop-shadow(0 10px 16px rgba(0,0,0,0.24))
}
.status-card{--monitor-avatar-left:50%;--monitor-avatar-bottom:calc(100% - 5px);--monitor-avatar-width:180px;--monitor-card-border-color:var(--monitor-border);--monitor-card-shadow:inset 0 1px 0 rgba(255,255,255,0.05),0 12px 40px rgba(0,0,0,0.3);--monitor-guide-width:92px;--monitor-guide-height:54px;--monitor-action-width:88px;--monitor-action-height:52px;--monitor-pop-start-scale:0.88;--monitor-pop-peak-scale:1.03;--monitor-pop-rebound-scale:0.99;--monitor-pop-settle-scale:1.01;position:relative;overflow:visible;border:1px solid transparent;border-radius:26px;padding:20px 22px;background:transparent;box-shadow:none;animation:card-in 560ms cubic-bezier(0.22,1,0.36,1) both;animation-delay:var(--monitor-delay);isolation:isolate;transition:transform 220ms ease,opacity 220ms ease,filter 220ms ease}
.status-card::before{content:'';position:absolute;inset:0;z-index:var(--monitor-card-layer);border:1px solid var(--monitor-card-border-color);border-radius:inherit;background:var(--monitor-panel);box-shadow:var(--monitor-card-shadow);pointer-events:none;transition:border-color 220ms ease,box-shadow 220ms ease}
.status-card.is-clickable{cursor:pointer}
.status-card.is-completed{--monitor-card-border-color:var(--monitor-completed-border);cursor:not-allowed}
.status-card.is-completed:hover{--monitor-card-border-color:var(--monitor-completed-border);transform:none}
.status-card.is-clickable:focus-visible{outline:none;--monitor-card-border-color:rgba(255,255,255,0.22);--monitor-card-shadow:0 0 0 1px rgba(255,255,255,0.08),0 0 0 4px rgba(255,255,255,0.08),inset 0 1px 0 rgba(255,255,255,0.05),0 12px 40px rgba(0,0,0,0.3)}
.status-card:hover{--monitor-card-border-color:var(--monitor-border-strong);transform:translateY(-2px)}
.status-card:is(:hover,:focus-within),.status-card.is-locked{z-index:400}
.status-card.is-locked{transform:translateY(-4px);--monitor-card-border-color:rgba(255,255,255,0.22);--monitor-card-shadow:0 24px 72px rgba(0,0,0,0.46),0 0 0 1px rgba(255,255,255,0.08),inset 0 1px 0 rgba(255,255,255,0.06)}
.card-grid.has-active-card .status-card.is-dimmed{opacity:0.28;filter:blur(7px) saturate(0.4);transform:scale(0.97);pointer-events:none;user-select:none}
.status-card:not(.is-completed):not(.is-dimmed):is(:hover,:focus-within) .card-monitor-shell,.status-card.is-locked .card-monitor-shell{opacity:1;animation:card-monitor-pop 1200ms cubic-bezier(0.16,1,0.3,1) both,card-monitor-layer-pop 760ms linear both}
.status-card.is-completed .card-monitor{filter:grayscale(0.14) saturate(0.82) drop-shadow(0 10px 22px rgba(0,0,0,0.28))}
.status-card.is-completed:not(.is-dimmed):is(:hover,:focus-within) .card-monitor-shell{opacity:0.72;transform:translateX(-50%) translateY(2px) scale(0.94)}
.status-card.is-locked:not(.is-completed) .bubble-action{opacity:1;--bubble-reveal-offset-y:0px;--bubble-scale:1;pointer-events:auto}
.status-card.is-locked:not(.is-completed) .bubble-action-stack{pointer-events:auto}
.status-card:not(.is-dimmed):is(:hover,:focus-within):not(.is-locked):not(.is-completed) .bubble-guide{animation:bubble-guide-in 240ms ease 720ms both}
.card-monitor-shell,.card-monitor-overlay{position:absolute;left:var(--monitor-avatar-left);bottom:var(--monitor-avatar-bottom);width:var(--monitor-avatar-width);aspect-ratio:516 / 312;overflow:visible;pointer-events:none}
.card-monitor-shell{z-index:var(--monitor-preview-layer-under);opacity:0;transform:translateX(-50%) translateY(var(--monitor-pop-start-y)) scale(var(--monitor-pop-start-scale));transform-origin:bottom center;transition:opacity 180ms ease,transform 260ms ease}
.card-monitor-overlay{z-index:var(--monitor-preview-layer-over);transform:translateX(-50%)}
.card-monitor{position:absolute;inset:0;display:block;width:100%;height:100%;pointer-events:none;user-select:none;object-fit:contain;filter:drop-shadow(0 14px 28px rgba(0,0,0,0.34))}
.bubble-guide{position:absolute;left:50%;top:50%;z-index:1;display:grid;place-items:center;width:var(--monitor-guide-width);height:var(--monitor-guide-height);opacity:0;transform:translate( calc(-50% + var(--guide-offset-x)),calc(-50% + var(--guide-offset-y) + 14px) ) scale(0.92);pointer-events:none}
.bubble-art{display:block;width:100%;height:100%}
.bubble-guide .bubble-art{filter:drop-shadow(0 16px 22px rgba(0,0,0,0.28))}
.bubble-action-stack{position:absolute;inset:0;z-index:2;pointer-events:none}
.bubble-action{--bubble-reveal-offset-y:12px;--bubble-interaction-y:0px;--bubble-scale:0.88;position:absolute;left:50%;top:50%;width:var(--monitor-action-width);height:var(--monitor-action-height);border:0;padding:0;background:transparent;opacity:0;transform:translate( calc(-50% + var(--bubble-offset-x)),calc(-50% + var(--bubble-offset-y) + var(--bubble-reveal-offset-y) + var(--bubble-interaction-y)) ) scale(var(--bubble-scale));cursor:pointer;pointer-events:none;transition:transform 220ms ease,opacity 220ms ease;transition-delay:var(--bubble-delay)}
.bubble-action .bubble-art{filter:drop-shadow(0 14px 24px rgba(0,0,0,0.32))}
.bubble-action:focus-visible{--bubble-interaction-y:6px;--bubble-scale:1.04}
.bubble-action:focus-visible{outline:none}
.bubble-action:active{--bubble-interaction-y:8px;--bubble-scale:0.98}
.vpnBadge{position:absolute;left:14px;top:14px;z-index:var(--monitor-card-overlay-layer);display:inline-flex;width:2rem;height:2rem;align-items:center;justify-content:center;border:0;padding:0;background:transparent;color:rgba(250,250,250,0.7);font-size:1rem;line-height:1;pointer-events:none}
.vpnBadge svg{display:block;width:1em;height:1em}
.card-layout{position:relative;z-index:var(--monitor-card-layer);display:grid;grid-template-columns:104px minmax(0,1fr);grid-template-rows:52px minmax(56px,auto);align-items:center;column-gap:20px;row-gap:12px}
.site-link{display:flex;grid-row:1 / span 2;width:104px;height:104px;align-items:center;justify-content:center;cursor:pointer;text-decoration:none;transition:transform 180ms ease,opacity 180ms ease}
.site-link:hover{transform:translateY(-1px);opacity:0.92}
.site-icon{display:block;width:100%;height:100%;object-fit:contain}
.sparkline-group{position:relative;display:block;width:100%;height:60px;min-width:0;isolation:isolate}
.sparkline{position:absolute;inset:0;display:block;width:100%;height:100%;min-width:0;pointer-events:none;overflow:visible}
.sparkline-line{fill:none;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round}
.card-bottom{display:flex;min-width:0;flex-direction:column;gap:12px}
.metric-row{display:flex;flex-wrap:wrap;justify-content:space-between;gap:12px;align-items:flex-end}
.isp-broadcast{display:flex;align-items:center;flex-wrap:wrap;gap:8px;min-width:0;max-width:100%}
.isp-broadcast-row{display:inline-flex;flex:0 0 auto;align-items:center;gap:6px;white-space:nowrap}
.isp-broadcast-icon{display:block;width:18px;height:18px;flex:0 0 auto;object-fit:contain;filter:drop-shadow(0 4px 8px rgba(0,0,0,0.24))}
.isp-broadcast-cells{display:inline-flex;align-items:center;gap:4px;min-width:0;white-space:nowrap}
.isp-broadcast-value{font-size:0.72rem;font-weight:700;line-height:1}
.isp-broadcast-separator{color:rgba(255,255,255,0.28);font-size:0.72rem;font-weight:600}
.stacked-bar{display:flex;height:14px;overflow:hidden;border-radius:22px;background:rgba(255,255,255,0.05);box-shadow:inset 0 1px 2px rgba(0,0,0,0.45)}
.stack-segment{position:relative;min-width:0}
.stack-segment::after{content:'';position:absolute;inset:0;background:linear-gradient(180deg,rgba(255,255,255,0.22),transparent)}
.board-toast-stack{position:fixed;right:20px;bottom:20px;z-index:30;display:flex;justify-content:flex-end;pointer-events:none}
.board-toast{display:inline-flex;align-items:center;justify-content:center;min-width:88px;padding:0.72rem 0.96rem;border:1px solid rgba(255,255,255,0.1);border-radius:999px;background:rgba(9,9,11,0.88);color:rgba(250,250,250,0.96);font-size:0.82rem;font-weight:600;letter-spacing:0.01em;box-shadow:0 18px 42px rgba(0,0,0,0.34);backdrop-filter:blur(16px);animation:toast-in 180ms ease both}
@keyframes card-in{from{opacity:0;transform:translateY(20px)}
to{opacity:1;transform:translateY(0)}
}
@keyframes isp-focus-option-in{from{opacity:0;transform:translateY(18px) scale(0.84)}
to{opacity:1;transform:translateY(0) scale(1)}
}
@keyframes card-monitor-pop{0%{opacity:0;transform:translateX(-50%) translateY(var(--monitor-pop-start-y)) scale(var(--monitor-pop-start-scale))}
38%{opacity:1;transform:translateX(-50%) translateY(var(--monitor-pop-apex-y)) scale(var(--monitor-pop-peak-scale))}
56%{transform:translateX(-50%) translateY(var(--monitor-pop-rebound-y)) scale(var(--monitor-pop-rebound-scale))}
72%{transform:translateX(-50%) translateY(var(--monitor-pop-settle-y)) scale(var(--monitor-pop-settle-scale))}
100%{opacity:1;transform:translateX(-50%) translateY(var(--monitor-pop-end-y)) scale(1)}
}
@keyframes card-monitor-layer-pop{0%,37.99%{z-index:var(--monitor-preview-layer-under)}
38%,100%{z-index:var(--monitor-preview-layer-over)}
}
@keyframes bubble-guide-in{from{opacity:0;transform:translate( calc(-50% + var(--guide-offset-x)),calc(-50% + var(--guide-offset-y) + 14px) ) scale(0.92)}
to{opacity:1;transform:translate( calc(-50% + var(--guide-offset-x)),calc(-50% + var(--guide-offset-y)) ) scale(1)}
}
@keyframes toast-in{from{opacity:0;transform:translateY(10px) scale(0.96)}
to{opacity:1;transform:translateY(0) scale(1)}
}
@media (max-width:980px){.card-grid{grid-template-columns:1fr}
}
@media (max-width:768px){.board-shell{padding:22px;border-radius:24px}
.status-card{--monitor-avatar-width:96px;--monitor-guide-width:84px;--monitor-guide-height:48px;--monitor-action-width:78px;--monitor-action-height:46px}
.card-layout{grid-template-columns:88px minmax(0,1fr);grid-template-rows:48px minmax(54px,auto);column-gap:16px}
.site-link{width:88px;height:88px}
.sparkline-group{height:48px}
}
@media (max-width:540px){.board-shell{padding:18px}
.status-card{--monitor-avatar-width:84px;--monitor-guide-width:74px;--monitor-guide-height:42px;--monitor-action-width:68px;--monitor-action-height:40px;padding:18px}
.card-layout{grid-template-columns:72px minmax(0,1fr);grid-template-rows:42px minmax(52px,auto);column-gap:14px;row-gap:10px}
.site-link{width:72px;height:72px}
.sparkline-group{height:42px}
.metric-row{align-items:flex-start;flex-direction:column}
.board-toast-stack{right:14px;bottom:14px}
}
@media (prefers-reduced-motion:reduce){.status-card{animation:none}
.status-card:hover{transform:none}
.monitor-board.has-isp-focus .board-shell{transform:none}
.isp-focus-option{animation:none;opacity:1;transform:none}
.card-monitor-shell{transition:opacity 120ms ease}
.status-card:not(.is-completed):not(.is-dimmed):is(:hover,:focus-within) .card-monitor-shell,.status-card.is-locked .card-monitor-shell{animation:none;z-index:var(--monitor-preview-layer-over);opacity:1;transform:translateX(-50%) translateY(var(--monitor-pop-end-y)) scale(1)}
.status-card.is-completed:not(.is-dimmed):is(:hover,:focus-within) .card-monitor-shell{animation:none;z-index:var(--monitor-preview-layer-over);opacity:0.72;transform:translateX(-50%) translateY(2px) scale(0.94)}
.status-card:not(.is-dimmed):is(:hover,:focus-within):not(.is-locked):not(.is-completed) .bubble-guide{animation:none;opacity:1;transform:translate( calc(-50% + var(--guide-offset-x)),calc(-50% + var(--guide-offset-y)) ) scale(1)}
.status-card.is-locked:not(.is-completed) .bubble-action{animation:none;opacity:1;--bubble-reveal-offset-y:0px;--bubble-scale:1}
.board-toast{animation:none}
}

</style>

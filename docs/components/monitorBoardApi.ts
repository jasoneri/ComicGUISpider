import type {
  MonitorBoardLiveStatus,
  MonitorBoardRuntimeData,
  MonitorBoardUptimes,
  MonitorBoardVoteKey,
  MonitorBoardVotes,
} from './monitorStatusBoardSource'

const DEFAULT_MONITOR_API_BASE_URL = '/api/monitor'

export type MonitorBoardVoteSubmission = {
  siteId: string
  action: MonitorBoardVoteKey
  delta: number
}

export class MonitorBoardApiError extends Error {
  readonly status: number

  constructor(message: string, status = 500) {
    super(message)
    this.name = 'MonitorBoardApiError'
    this.status = status
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isVoteKey(value: unknown): value is MonitorBoardVoteKey {
  return value === 'up' || value === 'neutral' || value === 'down'
}

function readJsonErrorMessage(payload: unknown, fallback: string): string {
  if (!isRecord(payload)) {
    return fallback
  }

  const message = payload.message
  return typeof message === 'string' && message.trim() !== '' ? message : fallback
}

function normalizeVotes(value: unknown): MonitorBoardVotes {
  if (!isRecord(value)) {
    throw new TypeError('Monitor board votes payload must be an object.')
  }

  const up = value.up
  const neutral = value.neutral
  const down = value.down

  if (![up, neutral, down].every((entry) => typeof entry === 'number' && Number.isFinite(entry))) {
    throw new TypeError('Monitor board votes payload must contain finite numeric up/neutral/down fields.')
  }

  return { up, neutral, down }
}

function normalizeUptimes(value: unknown): MonitorBoardUptimes {
  if (!Array.isArray(value)) {
    throw new TypeError('Monitor board uptimes payload must be an array of vote snapshots.')
  }

  return value.map((entry) => normalizeVotes(entry))
}

function normalizeLiveStatus(value: unknown): MonitorBoardLiveStatus {
  if (!isRecord(value)) {
    throw new TypeError('Monitor board live status payload must be an object.')
  }

  return {
    uptimes: normalizeUptimes(value.uptimes),
    votes: normalizeVotes(value.votes),
  }
}

export function normalizeMonitorBoardRuntimeData(value: unknown): MonitorBoardRuntimeData {
  if (!isRecord(value)) {
    throw new TypeError('Monitor board runtime payload must be an object.')
  }

  const resetDate = value.resetDate
  const resetStartedAt = value.resetStartedAt
  if (typeof resetDate !== 'string' || resetDate.trim() === '') {
    throw new TypeError('Monitor board runtime payload requires a non-empty resetDate string.')
  }
  if (typeof resetStartedAt !== 'string' || resetStartedAt.trim() === '') {
    throw new TypeError('Monitor board runtime payload requires a non-empty resetStartedAt string.')
  }

  const statusMap = value.statusMap
  if (!isRecord(statusMap)) {
    throw new TypeError('Monitor board runtime payload requires an object statusMap.')
  }

  return {
    resetDate,
    resetStartedAt,
    statusMap: Object.fromEntries(
      Object.entries(statusMap).map(([siteId, liveStatus]) => [siteId, normalizeLiveStatus(liveStatus)]),
    ),
  }
}

async function parseJsonResponse(response: Response): Promise<unknown> {
  const rawBody = await response.text()
  if (rawBody === '') {
    return null
  }

  try {
    return JSON.parse(rawBody) as unknown
  } catch (error) {
    throw new MonitorBoardApiError(
      `Monitor API returned non-JSON content (status ${response.status}).`,
      response.status || 500,
    )
  }
}

function trimTrailingSlash(value: string): string {
  return value.endsWith('/') ? value.slice(0, -1) : value
}

function normalizeApiBaseUrl(apiBaseUrl: string | undefined): string {
  if (typeof apiBaseUrl !== 'string' || apiBaseUrl.trim() === '') {
    return DEFAULT_MONITOR_API_BASE_URL
  }

  return trimTrailingSlash(apiBaseUrl.trim())
}

export async function fetchMonitorBoardRuntimeData(apiBaseUrl?: string): Promise<MonitorBoardRuntimeData> {
  const response = await fetch(normalizeApiBaseUrl(apiBaseUrl), {
    headers: {
      accept: 'application/json',
    },
  })
  const payload = await parseJsonResponse(response)

  if (!response.ok) {
    throw new MonitorBoardApiError(
      readJsonErrorMessage(payload, `Monitor data request failed with status ${response.status}.`),
      response.status,
    )
  }

  return normalizeMonitorBoardRuntimeData(payload)
}

export async function submitMonitorBoardVote(
  submission: MonitorBoardVoteSubmission,
  apiBaseUrl?: string,
): Promise<void> {
  const { siteId, action, delta } = submission
  if (typeof siteId !== 'string' || siteId.trim() === '') {
    throw new TypeError('Monitor vote submission requires a non-empty siteId string.')
  }
  if (!isVoteKey(action)) {
    throw new TypeError('Monitor vote submission action must be one of up/neutral/down.')
  }
  if (!Number.isInteger(delta) || delta <= 0) {
    throw new TypeError('Monitor vote submission delta must be a positive integer.')
  }

  const response = await fetch(`${normalizeApiBaseUrl(apiBaseUrl)}/vote`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'application/json',
    },
    body: JSON.stringify({
      siteId,
      action,
      delta,
    }),
  })
  const payload = await parseJsonResponse(response)

  if (!response.ok) {
    throw new MonitorBoardApiError(
      readJsonErrorMessage(payload, `Monitor vote request failed with status ${response.status}.`),
      response.status,
    )
  }
}

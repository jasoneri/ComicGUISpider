type DocsUrlEnv = Readonly<Record<string, string | undefined>>

const LOCAL_HTTP_HOSTS = new Set(['127.0.0.1', 'localhost'])

const DEFAULT_ORIGINS = {
  MAIN: 'https://cgs.101114105.xyz',
  IMG: 'https://img-cgs.101114105.xyz',
  RV: 'https://rv.101114105.xyz',
  GHSTAT: 'https://ghstat.101114105.xyz',
} as const

const DEFAULT_MONITOR_API_BASE_URL = 'https://cgs-monitor.101114105.xyz/api/monitor'
const DEFAULT_TIMELINE_API_BASE_URL = 'https://notice.101114105.xyz/v1/boards/cgs'

function join(origin: string, path = ''): string {
  return origin + (path.startsWith('/') ? path : `/${path}`)
}

function trimTrailingSlash(value: string): string {
  return value.endsWith('/') ? value.slice(0, -1) : value
}

function isLocalHttpUrl(url: URL): boolean {
  return url.protocol === 'http:' && LOCAL_HTTP_HOSTS.has(url.hostname)
}

function readEnvValue(env: DocsUrlEnv, key: string): string | null {
  const value = env[key]
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : null
}

function parseAbsoluteUrl(rawValue: string, key: string): URL {
  try {
    return new URL(rawValue)
  } catch (error) {
    throw new Error(`${key} must be an absolute URL.`)
  }
}

function normalizeOrigin(rawValue: string, key: string): string {
  const url = parseAbsoluteUrl(rawValue, key)
  if (url.protocol !== 'https:' && !isLocalHttpUrl(url)) {
    throw new Error(`${key} must use https unless pointing to localhost or 127.0.0.1.`)
  }
  if (url.pathname !== '/' || url.search !== '' || url.hash !== '') {
    throw new Error(`${key} must not include path, query, or hash.`)
  }
  return trimTrailingSlash(url.origin)
}

export function normalizeMonitorApiBaseUrl(rawValue: string, key: string): string {
  const url = parseAbsoluteUrl(rawValue, key)
  if (url.protocol !== 'https:' && !isLocalHttpUrl(url)) {
    throw new Error(`${key} must use https unless pointing to localhost or 127.0.0.1.`)
  }
  if (url.search !== '' || url.hash !== '') {
    throw new Error(`${key} must not include query or hash.`)
  }

  const normalizedPathname = trimTrailingSlash(url.pathname)
  if (normalizedPathname !== '/api/monitor') {
    throw new Error(`${key} must point to /api/monitor.`)
  }

  return `${trimTrailingSlash(url.origin)}${normalizedPathname}`
}

const TIMELINE_BOARD_PATH = /^\/v1\/boards\/[a-z][a-z0-9-]{1,31}$/

export function normalizeTimelineApiBaseUrl(rawValue: string, key: string): string {
  const url = parseAbsoluteUrl(rawValue, key)
  if (url.protocol !== 'https:' && !isLocalHttpUrl(url)) {
    throw new Error(`${key} must use https unless pointing to localhost or 127.0.0.1.`)
  }
  const normalizedPathname = trimTrailingSlash(url.pathname)
  if (url.search !== '' || url.hash !== '' || !TIMELINE_BOARD_PATH.test(normalizedPathname)) {
    throw new Error(`${key} must point to /v1/boards/{board}.`)
  }
  return `${trimTrailingSlash(url.origin)}${normalizedPathname}`
}

export const PLACEHOLDERS = {
  URL_MAIN: '{{URL_MAIN}}',
  URL_IMG: '{{URL_IMG}}',
  URL_RV: '{{URL_RV}}',
  URL_GHSTAT: '{{URL_GHSTAT}}',
  URL_MONITOR_API: '{{URL_MONITOR_API}}',
  URL_TIMELINE_API: '{{URL_TIMELINE_API}}',
} as const

export function createDocsUrlConfig(env: DocsUrlEnv) {
  const ORIGINS = {
    MAIN: normalizeOrigin(readEnvValue(env, 'DOCS_MAIN_ORIGIN') ?? DEFAULT_ORIGINS.MAIN, 'DOCS_MAIN_ORIGIN'),
    IMG: normalizeOrigin(readEnvValue(env, 'DOCS_IMG_ORIGIN') ?? DEFAULT_ORIGINS.IMG, 'DOCS_IMG_ORIGIN'),
    RV: normalizeOrigin(readEnvValue(env, 'DOCS_RV_ORIGIN') ?? DEFAULT_ORIGINS.RV, 'DOCS_RV_ORIGIN'),
    GHSTAT: normalizeOrigin(readEnvValue(env, 'DOCS_GHSTAT_ORIGIN') ?? DEFAULT_ORIGINS.GHSTAT, 'DOCS_GHSTAT_ORIGIN'),
  } as const

  const monitorApiBaseUrl = normalizeMonitorApiBaseUrl(
    readEnvValue(env, 'VITE_MONITOR_API_BASE_URL') ?? DEFAULT_MONITOR_API_BASE_URL,
    'VITE_MONITOR_API_BASE_URL',
  )
  const timelineApiBaseUrl = normalizeTimelineApiBaseUrl(
    readEnvValue(env, 'VITE_TIMELINE_API_BASE_URL') ?? DEFAULT_TIMELINE_API_BASE_URL,
    'VITE_TIMELINE_API_BASE_URL',
  )

  const URLS = {
    main: (path = '/') => join(ORIGINS.MAIN, path),
    img: (path = '/') => join(ORIGINS.IMG, path),
    rv: (path = '/') => join(ORIGINS.RV, path),
    ghstat: (path = '/') => join(ORIGINS.GHSTAT, path),
    monitor: {
      api: monitorApiBaseUrl,
    },
    timeline: {
      api: timelineApiBaseUrl,
    },
    assets: {
      logo: join(ORIGINS.IMG, '/file/1765128492268_cgs_eat.png'),
      rvLogo: join(ORIGINS.IMG, '/file/1766904566021_rv.png'),
    },
    pages: {
      rvFeed: join(ORIGINS.RV, '/contribute/feed'),
      quickStart: join(ORIGINS.MAIN, '/deploy/quick-start'),
      faq: join(ORIGINS.MAIN, '/faq'),
      featScript: join(ORIGINS.MAIN, '/script'),
      timeline: join(ORIGINS.MAIN, '/timeline/'),
    },
  } as const

  const PLACEHOLDER_MAP = {
    [PLACEHOLDERS.URL_MAIN]: ORIGINS.MAIN,
    [PLACEHOLDERS.URL_IMG]: ORIGINS.IMG,
    [PLACEHOLDERS.URL_RV]: ORIGINS.RV,
    [PLACEHOLDERS.URL_GHSTAT]: ORIGINS.GHSTAT,
    [PLACEHOLDERS.URL_MONITOR_API]: monitorApiBaseUrl,
    [PLACEHOLDERS.URL_TIMELINE_API]: timelineApiBaseUrl,
  } as const

  return {
    ORIGINS,
    URLS,
    PLACEHOLDERS,
    PLACEHOLDER_MAP,
    MONITOR_API_BASE_URL: monitorApiBaseUrl,
    TIMELINE_API_BASE_URL: timelineApiBaseUrl,
  } as const
}

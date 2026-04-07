export type MonitorBoardLocale = 'zh' | 'en'

export type MonitorBoardVotes = {
  up: number
  neutral: number
  down: number
}

export type MonitorBoardSite = {
  id: string
  name: string
  href: string
  avatarSrc: string
  accent: string
}

export type MonitorBoardLiveStatus = {
  uptime: number[]
  votes: MonitorBoardVotes
}

export type MonitorBoardStatusMap = Partial<Record<string, MonitorBoardLiveStatus>>

export type MonitorBoardRuntimeData = {
  resetDate: string
  statusMap: Record<string, MonitorBoardLiveStatus>
}

export const monitorBoardSites: MonitorBoardSite[] = [
  {
    id: 'copy-manga',
    name: '拷贝漫画',
    href: 'https://www.2025copy.com/',
    avatarSrc: '/assets/img/icons/website/copy.png',
    accent: '#10b981',
  },
  {
    id: 'mangabz',
    name: 'Māngabz',
    href: 'https://mangabz.com',
    avatarSrc: '/assets/img/icons/website/mangabz.png',
    accent: '#14b8a6',
  },
  {
    id: '18comic',
    name: '18comic',
    href: 'https://18comic.vip/',
    avatarSrc: '/assets/img/icons/website/jm.png',
    accent: '#f59e0b',
  },
  {
    id: 'wnacg',
    name: 'wnacg',
    href: 'https://www.wnacg.com/',
    avatarSrc: '/assets/img/icons/website/wnacg.png',
    accent: '#fb7185',
  },
  {
    id: 'ehentai',
    name: 'E-Hentai',
    href: 'https://exhentai.org/',
    avatarSrc: '/assets/img/icons/website/ehentai.png',
    accent: '#f43f5e',
  },
  {
    id: 'hitomi',
    name: 'Hitomi',
    href: 'https://hitomi.la/',
    avatarSrc: '/assets/img/icons/website/hitomi.png',
    accent: '#8b5cf6',
  },
  {
    id: 'h-comic',
    name: 'H-Comic',
    href: 'https://h-comic.com/',
    avatarSrc: '/assets/img/icons/website/hcomic.png',
    accent: '#ef4444',
  },
]

export const monitorBoardCopy = {
  zh: {
    title: '站点可用投票',
    segments: {
      up: '可用',
      neutral: '观望',
      down: '异常',
    },
    totalVotes: '总票数',
    distribution: '社区反馈分布',
  },
  en: {
    title: 'Availability Vote',
    segments: {
      up: 'up',
      neutral: 'neutral',
      down: 'down',
    },
    totalVotes: 'total votes',
    distribution: 'Community signal distribution',
  },
} as const

const monitorBoardMockStatusMap: Record<string, MonitorBoardLiveStatus> = {
  'copy-manga': {
    uptime: [97, 98, 98, 99, 99, 100, 99, 98, 98, 99, 100, 100, 99, 98, 99, 99, 100, 100, 99, 98, 98, 99, 100, 100, 99, 99, 100, 100],
    votes: { up: 35, neutral: 5, down: 2 },
  },
  mangabz: {
    uptime: [95, 96, 95, 97, 98, 97, 96, 95, 95, 96, 98, 99, 98, 96, 95, 94, 95, 96, 97, 97, 98, 99, 98, 97, 96, 95, 96, 97],
    votes: { up: 22, neutral: 4, down: 1 },
  },
  '18comic': {
    uptime: [82, 84, 86, 88, 85, 83, 79, 81, 87, 86, 89, 91, 84, 82, 80, 83, 85, 87, 89, 86, 84, 83, 88, 90, 91, 87, 85, 84],
    votes: { up: 4, neutral: 4, down: 1 },
  },
  wnacg: {
    uptime: [77, 79, 74, 72, 71, 69, 75, 78, 74, 72, 76, 79, 73, 70, 68, 71, 75, 76, 78, 74, 70, 69, 73, 77, 76, 72, 71, 74],
    votes: { up: 3, neutral: 3, down: 3 },
  },
  ehentai: {
    uptime: [74, 72, 69, 67, 71, 70, 66, 63, 61, 64, 68, 71, 73, 69, 66, 62, 59, 61, 64, 65, 62, 60, 57, 58, 61, 63, 60, 58],
    votes: { up: 1, neutral: 1, down: 3 },
  },
  hitomi: {
    uptime: [89, 90, 91, 90, 92, 91, 89, 88, 90, 91, 93, 94, 92, 90, 89, 88, 89, 91, 92, 93, 91, 90, 88, 87, 89, 90, 91, 92],
    votes: { up: 4, neutral: 1, down: 1 },
  },
  'h-comic': {
    uptime: [86, 84, 83, 85, 88, 87, 84, 81, 80, 82, 85, 87, 86, 84, 83, 82, 81, 83, 84, 86, 85, 84, 82, 80, 81, 83, 84, 85],
    votes: { up: 6, neutral: 3, down: 2 },
  },
}

const monitorBoardMockRuntimeData: MonitorBoardRuntimeData = {
  resetDate: '04/06',
  statusMap: monitorBoardMockStatusMap,
}

export const emptyMonitorBoardLiveStatus: MonitorBoardLiveStatus = {
  uptime: [],
  votes: {
    up: 0,
    neutral: 0,
    down: 0,
  },
}

export function createMockMonitorBoardStatusMap(): Record<string, MonitorBoardLiveStatus> {
  return Object.fromEntries(
    Object.entries(monitorBoardMockStatusMap).map(([siteId, status]) => [
      siteId,
      {
        uptime: [...status.uptime],
        votes: { ...status.votes },
      },
    ]),
  )
}

export function createMockMonitorBoardRuntimeData(): MonitorBoardRuntimeData {
  return {
    resetDate: monitorBoardMockRuntimeData.resetDate,
    statusMap: createMockMonitorBoardStatusMap(),
  }
}

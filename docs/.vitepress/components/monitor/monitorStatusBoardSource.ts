const copySiteAvatarSrc = new URL('../../../assets/img/icons/website/copy.png', import.meta.url).href
const ehentaiSiteAvatarSrc = new URL('../../../assets/img/icons/website/ehentai.png', import.meta.url).href
const hitomiSiteAvatarSrc = new URL('../../../assets/img/icons/website/hitomi.png', import.meta.url).href
const hcomicSiteAvatarSrc = new URL('../../../assets/img/icons/website/hcomic.png', import.meta.url).href
const jmSiteAvatarSrc = new URL('../../../assets/img/icons/website/jm.png', import.meta.url).href
const mangabzSiteAvatarSrc = new URL('../../../assets/img/icons/website/mangabz.png', import.meta.url).href
const wnacgSiteAvatarSrc = new URL('../../../assets/img/icons/website/wnacg.png', import.meta.url).href
const danbooruSiteAvatarSrc = new URL('../../../assets/img/icons/website/danbooru.svg', import.meta.url).href

export type MonitorBoardLocale = 'zh' | 'en'

export type MonitorBoardVotes = {
  up: number
  neutral: number
  down: number
}

export type MonitorBoardVoteKey = keyof MonitorBoardVotes

export type MonitorBoardUptimes = MonitorBoardVotes[]

export type MonitorBoardSite = {
  id: string
  name: string
  href: string
  avatarSrc: string
}

export type MonitorBoardLiveStatus = {
  uptimes: MonitorBoardUptimes
  votes: MonitorBoardVotes
}

export type MonitorBoardStatusMap = Partial<Record<string, MonitorBoardLiveStatus>>

export type MonitorBoardRuntimeData = {
  resetDate: string
  resetStartedAt: string
  statusMap: Record<string, MonitorBoardLiveStatus>
}

export const monitorBoardSites: MonitorBoardSite[] = [
  {
    id: 'copy-manga',
    name: '拷贝漫画',
    href: 'https://www.2026copy.com/',
    avatarSrc: copySiteAvatarSrc,
  },
  {
    id: 'mangabz',
    name: 'Māngabz',
    href: 'https://mangabz.com',
    avatarSrc: mangabzSiteAvatarSrc,
  },
  {
    id: '18comic',
    name: '18comic',
    href: 'https://18comic.vip/',
    avatarSrc: jmSiteAvatarSrc,
  },
  {
    id: 'wnacg',
    name: 'wnacg',
    href: 'https://www.wnacg.com/',
    avatarSrc: wnacgSiteAvatarSrc,
  },
  {
    id: 'ehentai',
    name: 'E-Hentai',
    href: 'https://exhentai.org/',
    avatarSrc: ehentaiSiteAvatarSrc,
  },
  {
    id: 'hitomi',
    name: 'Hitomi',
    href: 'https://hitomi.la/',
    avatarSrc: hitomiSiteAvatarSrc,
  },
  {
    id: 'h-comic',
    name: 'H-Comic',
    href: 'https://h-comic.com/',
    avatarSrc: hcomicSiteAvatarSrc,
  },
  {
    id: 'danbooru',
    name: 'Danbooru',
    href: 'https://danbooru.domain.us',
    avatarSrc: danbooruSiteAvatarSrc,
  },
]

export const monitorBoardCopy = {
  zh: {
    title: '站点状态',
    syncing: '远端同步中',
    syncFailed: '远端同步失败',
    submitting: '提交中',
    submitSuccess: '已提交',
    submitFailed: '提交失败',
    retryHint: '请稍后重试',
    distribution: '社区反馈分布',
  },
  en: {
    title: 'Site Status',
    syncing: 'syncing',
    syncFailed: 'sync failed',
    submitting: 'submitting',
    submitSuccess: 'submitted',
    submitFailed: 'submit failed',
    retryHint: 'retry later',
    distribution: 'Community signal distribution',
  },
} as const

export const emptyMonitorBoardLiveStatus: MonitorBoardLiveStatus = {
  uptimes: [],
  votes: {
    up: 0,
    neutral: 0,
    down: 0,
  },
}

export function createEmptyMonitorBoardRuntimeData(
  resetDate = '---- ~',
  resetStartedAt = 'default',
): MonitorBoardRuntimeData {
  return {
    resetDate,
    resetStartedAt,
    statusMap: {},
  }
}

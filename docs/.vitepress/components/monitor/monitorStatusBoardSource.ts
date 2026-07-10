const copySiteAvatarSrc = new URL('../../../assets/img/icons/website/copy.png', import.meta.url).href
const ehentaiSiteAvatarSrc = new URL('../../../assets/img/icons/website/ehentai.png', import.meta.url).href
const hitomiSiteAvatarSrc = new URL('../../../assets/img/icons/website/hitomi.png', import.meta.url).href
const hcomicSiteAvatarSrc = new URL('../../../assets/img/icons/website/hcomic.png', import.meta.url).href
const jmSiteAvatarSrc = new URL('../../../assets/img/icons/website/jm.png', import.meta.url).href
const mangabzSiteAvatarSrc = new URL('../../../assets/img/icons/website/mangabz.png', import.meta.url).href
const wnacgSiteAvatarSrc = new URL('../../../assets/img/icons/website/wnacg.png', import.meta.url).href
const danbooruSiteAvatarSrc = new URL('../../../assets/img/icons/website/danbooru.svg', import.meta.url).href
const nhentaiSiteAvatarSrc = new URL('../../../assets/img/icons/website/nhentai.svg', import.meta.url).href
const jestfulSiteAvatarSrc = new URL('../../../assets/img/icons/website/jf.svg', import.meta.url).href
const manhuaguiSiteAvatarSrc = new URL('../../../assets/img/icons/website/mhg.png', import.meta.url).href
const dm5SiteAvatarSrc = new URL('../../../assets/img/icons/website/dm5.png', import.meta.url).href
const mobileIspIconSrc = new URL('../../../assets/img/icons/isp/mobile.png', import.meta.url).href
const telecomIspIconSrc = new URL('../../../assets/img/icons/isp/telecom.png', import.meta.url).href
const unicomIspIconSrc = new URL('../../../assets/img/icons/isp/unicom.png', import.meta.url).href

export type MonitorBoardLocale = 'zh' | 'en'

export type MonitorBoardIspKey = 'telecom' | 'mobile' | 'unicom'

export type MonitorBoardVotes = {
  up: number
  neutral: number
  down: number
}

export type MonitorBoardVoteKey = keyof MonitorBoardVotes

export type MonitorBoardVoteMatrixKey = `${MonitorBoardVoteKey}-${MonitorBoardIspKey}`

export type MonitorBoardVoteMatrix = Record<MonitorBoardVoteMatrixKey, number>

export type MonitorBoardUptimes = MonitorBoardVoteMatrix[]

export type MonitorBoardSite = {
  id: string
  name: string
  href: string
  avatarSrc: string
}

export type MonitorBoardIsp = {
  id: MonitorBoardIspKey
  name: string
  iconSrc: string
}

export type MonitorBoardLiveStatus = {
  uptimes: MonitorBoardUptimes
  votes: MonitorBoardVoteMatrix
}

export type MonitorBoardStatusMap = Partial<Record<string, MonitorBoardLiveStatus>>

export type MonitorBoardRuntimeData = {
  resetDate: string
  resetStartedAt: string
  statusMap: Record<string, MonitorBoardLiveStatus>
}

export const needProxySites: readonly string[] = [
  'copy-manga',
  'ehentai',
  'h-comic',
  'nhentai',
  'manhuagui',
]

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
  {
    id: 'nhentai',
    name: 'Nhentai',
    href: 'https://nhentai.net/',
    avatarSrc: nhentaiSiteAvatarSrc,
  },
  {
    id: 'jestful',
    name: 'jestful',
    href: 'https://jestful.net/',
    avatarSrc: jestfulSiteAvatarSrc,
  },
  {
    id: 'manhuagui',
    name: '漫画柜',
    href: 'https://www.manhuagui.com/',
    avatarSrc: manhuaguiSiteAvatarSrc,
  },
  {
    id: 'dm5',
    name: 'dm5',
    href: 'https://tel.dm5.com/',
    avatarSrc: dm5SiteAvatarSrc,
  }
]

export const monitorBoardVoteKeys: MonitorBoardVoteKey[] = ['up', 'neutral', 'down']

export const monitorBoardIspKeys: MonitorBoardIspKey[] = ['telecom', 'mobile', 'unicom']

export const monitorBoardVoteMatrixKeys: MonitorBoardVoteMatrixKey[] = monitorBoardVoteKeys.flatMap((voteKey) => (
  monitorBoardIspKeys.map((ispKey) => `${voteKey}-${ispKey}` as MonitorBoardVoteMatrixKey)
))

export const monitorBoardIsps: MonitorBoardIsp[] = [
  {
    id: 'telecom',
    name: 'Telecom',
    iconSrc: telecomIspIconSrc,
  },
  {
    id: 'mobile',
    name: 'Mobile',
    iconSrc: mobileIspIconSrc,
  },
  {
    id: 'unicom',
    name: 'Unicom',
    iconSrc: unicomIspIconSrc,
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

export function createEmptyMonitorBoardVoteMatrix(): MonitorBoardVoteMatrix {
  return Object.fromEntries(
    monitorBoardVoteMatrixKeys.map((key) => [key, 0]),
  ) as MonitorBoardVoteMatrix
}

export function getMonitorBoardVoteMatrixKey(
  voteKey: MonitorBoardVoteKey,
  ispKey: MonitorBoardIspKey,
): MonitorBoardVoteMatrixKey {
  return `${voteKey}-${ispKey}` as MonitorBoardVoteMatrixKey
}

export function getMonitorBoardVoteMatrixCell(
  votes: MonitorBoardVoteMatrix,
  voteKey: MonitorBoardVoteKey,
  ispKey: MonitorBoardIspKey,
): number {
  return votes[getMonitorBoardVoteMatrixKey(voteKey, ispKey)]
}

export function sumMonitorBoardVoteMatrixByVote(votes: MonitorBoardVoteMatrix): MonitorBoardVotes {
  return Object.fromEntries(
    monitorBoardVoteKeys.map((voteKey) => [
      voteKey,
      monitorBoardIspKeys.reduce((total, ispKey) => (
        total + getMonitorBoardVoteMatrixCell(votes, voteKey, ispKey)
      ), 0),
    ]),
  ) as MonitorBoardVotes
}

export function sumMonitorBoardVoteMatrixTotal(votes: MonitorBoardVoteMatrix): number {
  return monitorBoardVoteMatrixKeys.reduce((total, key) => total + votes[key], 0)
}

export const emptyMonitorBoardLiveStatus: MonitorBoardLiveStatus = {
  uptimes: [],
  votes: createEmptyMonitorBoardVoteMatrix(),
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

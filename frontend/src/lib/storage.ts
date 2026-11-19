/**
 * 本地存储的唯一入口。
 *
 * 为什么集中：此前 6 处 `localStorage.getItem('...')` 散落在 4 个组件里，
 * 键名各写各的（`cs-agent-app`、`cs_sessions`、`bigrobot-theme`…），改名时漏改一处
 * 就是「主题/语言/登录态莫名丢失」。键名现在只在这里定义，改名只改这一张表。
 *
 * 兼容：读取时按 legacy 列表回退，命中后顺手迁移到新键，老用户升级不丢设置。
 *
 * 边界（重要）：**这里只放 UI 态与本地凭据**。任何能从服务端 refetch 恢复的数据
 * （会话、配置、日志）一律不落 localStorage——那是 react-query 的职责。
 */

export const K = {
  /** 管理员令牌（本机引导取回后缓存，避免每页都要手输） */
  token: 'bigrobot-admin-token',
  /** 界面语言 zh | en */
  lang: 'bigrobot-lang',
  /** 亮/暗主题 */
  theme: 'bigrobot-theme',
  /** 访客本机会话列表（未登录访客的会话句柄，服务端不持久化） */
  sessions: 'bigrobot-sessions',
  /** 人设页的角色库草稿 */
  roleLib: 'bigrobot-persona-roles',
  /** 坐席快捷回复模板 */
  canned: 'bigrobot-canned',
} as const

export type StorageKey = (typeof K)[keyof typeof K]

/** 改名/重构前的旧键，读取时回退用。数组顺序 = 优先级。 */
const LEGACY: Record<string, string[]> = {
  [K.token]: ['cs-agent-app'],
  [K.sessions]: ['cs_sessions'],
  [K.lang]: ['zhike-lang'],
  [K.theme]: ['zhike-theme'],
  [K.roleLib]: ['zhike-persona-roles'],
  [K.canned]: ['zhike-canned'],
}

function safe<T>(fn: () => T, fallback: T): T {
  try {
    return fn()
  } catch {
    return fallback
  }
}

/** 读：新键 → 旧键（命中即迁移）→ 默认值。 */
export function read(key: StorageKey, fallback = ''): string {
  return safe(() => {
    const hit = localStorage.getItem(key)
    if (hit !== null) return hit
    for (const legacy of LEGACY[key] ?? []) {
      const old = localStorage.getItem(legacy)
      if (old !== null) {
        localStorage.setItem(key, old)
        localStorage.removeItem(legacy)
        return old
      }
    }
    return fallback
  }, fallback)
}

export function write(key: StorageKey, value: string): void {
  safe(() => localStorage.setItem(key, value), undefined)
}

export function remove(key: StorageKey): void {
  safe(() => localStorage.removeItem(key), undefined)
}

/** 读 JSON；解析失败或类型不符时返回 fallback（本地存储可能被用户手改坏）。 */
export function readJson<T>(key: StorageKey, fallback: T): T {
  return safe(() => {
    const raw = read(key)
    if (!raw) return fallback
    return JSON.parse(raw) as T
  }, fallback)
}

export function writeJson(key: StorageKey, value: unknown): void {
  safe(() => localStorage.setItem(key, JSON.stringify(value)), undefined)
}

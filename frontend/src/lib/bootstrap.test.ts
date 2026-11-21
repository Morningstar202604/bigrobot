/**
 * 启动令牌引导：管理页不能在无令牌时永久卡在 Loading。
 *
 * 真实复现：切换语言后刷新 /dashboard，页面永远显示 "Loading overview…"，
 * 因为 store 里没有 adminToken，请求带不上管理头，401 又被 loading 状态吞掉。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

// 用一个显式的可变对象承载 mock 状态：每个用例前重置，
// 否则前一个用例设进去的令牌会泄漏到下一个，导致「不该发请求」的用例失败。
const mockState = { token: '' }

vi.mock('../store/appStore', () => ({
  useAppStore: {
    getState: () => ({
      get adminToken() {
        return mockState.token
      },
      setAdminToken: (t: string) => {
        mockState.token = t
      },
    }),
  },
}))

describe('bootstrapAdminToken', () => {
  beforeEach(() => {
    vi.resetModules()
    mockState.token = ''
    globalThis.fetch = vi.fn()
  })

  it('无令牌时从本机引导接口取回', async () => {
    ;(globalThis.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => ({ available: true, token: 'boot-token' }),
    })
    const { bootstrapAdminToken } = await import('./queries')
    const { useAppStore } = await import('../store/appStore')
    await bootstrapAdminToken()
    expect(useAppStore.getState().adminToken).toBe('boot-token')
  })

  it('已有有效令牌时只校验一次，不重复引导', async () => {
    ;(globalThis.fetch as any).mockResolvedValue({ ok: true })
    const { bootstrapAdminToken } = await import('./queries')
    const { useAppStore } = await import('../store/appStore')
    useAppStore.getState().setAdminToken('existing')
    const got = await bootstrapAdminToken()
    expect(got).toBe(true)
    expect(globalThis.fetch).toHaveBeenCalledTimes(1)
    expect(useAppStore.getState().adminToken).toBe('existing')
  })

  it('已有令牌失效时清掉并重新引导', async () => {
    ;(globalThis.fetch as any)
      .mockResolvedValueOnce({ ok: false, status: 401 })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ available: true, token: 'new-token' }) })
    const { bootstrapAdminToken } = await import('./queries')
    const { useAppStore } = await import('../store/appStore')
    useAppStore.getState().setAdminToken('stale')
    const got = await bootstrapAdminToken()
    expect(got).toBe(true)
    expect(useAppStore.getState().adminToken).toBe('new-token')
    expect(globalThis.fetch).toHaveBeenCalledTimes(2)
  })

  it('接口不可用时安静返回 false，不抛异常', async () => {
    ;(globalThis.fetch as any).mockRejectedValue(new Error('network down'))
    const { bootstrapAdminToken } = await import('./queries')
    await expect(bootstrapAdminToken()).resolves.toBe(false)
  })

  it('服务端明确不给令牌时返回 false（公网部署）', async () => {
    ;(globalThis.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => ({ available: false, reason: '非回环来源' }),
    })
    const { bootstrapAdminToken } = await import('./queries')
    await expect(bootstrapAdminToken()).resolves.toBe(false)
  })
})

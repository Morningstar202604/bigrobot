import { useState } from 'react'
import { Brain, KeyRound, ShieldAlert } from 'lucide-react'
import { useAdminSchema, useAdminPurge, useAdminMemory, useAdminInjection } from '../lib/queries'
import { usePagination } from '../lib/pagination'
import { EmptyState } from '../ui'
import { Spinner, ErrorBanner } from '../components/Spinner'
import type { MemoryEntry, InjectionLogEntry } from '../types/api'
import { t as tr } from '../lib/t'
import { Check } from 'lucide-react'
import { Pager } from './bits'
import { useFeedback } from '../components/Feedback'
import { useAppStore } from '../store/appStore'

export function DataPanel() {
  // 运行总览与经营图表只在「实例 · 运行总览」维护一份；本页只做存储与数据清理，
  // 避免两个页面重复请求 /api/admin/overview、report、stats，也避免同一组数字出现两次。
  const { data: schema, isLoading: schemaLoading, error, refetch } = useAdminSchema()
  const purge = useAdminPurge()
  const fb = useFeedback()
  const [confirmPurge, setConfirmPurge] = useState(false)
  if (schemaLoading) return <Spinner full label={tr('加载数据…')} />
  if (error) return <div className="p-4"><ErrorBanner message={(error as Error).message} onRetry={() => refetch()} /></div>

  return (
    <>
      {/* 诊断区：DB 版本 / 表容量 / 数据清理（/api/admin/schema + /api/admin/purge） */}
      <div className="grp" style={{ marginTop: 14 }}>
        <div className="grp-head">
          <h3>{tr('存储与维护')}</h3>
          <span className="gh-note">{schema ? tr('schema v{v}', { v: schema.schema_version }) : tr('…')}</span>
        </div>
        <div className="grp-body">
          <div className="flex flex-wrap gap-1.5 mb-3">
            {Object.entries(schema?.tables ?? {}).map(([t, n]) => (
              <span key={t} className="badge muted" title={`${t}: ${n} 行`}>{t} · {n}</span>
            ))}
          </div>
          {confirmPurge ? (
            <div className="flex items-center gap-2 flex-wrap text-xs">
              <span style={{ color: 'var(--danger)' }}>{tr('将清理 180 天前的运营数据（审计链保留），确定？')}</span>
              <button className="btn sm" style={{ background: 'var(--danger)', color: '#fff' }}
                disabled={purge.isPending}
                onClick={() => purge.mutate(180, {
                  onSuccess: (r) => {
                    setConfirmPurge(false)
                    fb.toast.success(tr('已清理 {n} 条', { n: Object.values(r.removed || {}).reduce((a: number, b) => a + Number(b || 0), 0) }))
                  },
                  onError: (e) => fb.toast.error(`${tr('清理失败')}: ${(e as Error).message}`),
                })}>
                {purge.isPending ? tr('清理中…') : tr('确认清理')}
              </button>
              <button className="btn ghost sm" onClick={() => setConfirmPurge(false)}>{tr('取消')}</button>
            </div>
          ) : (
            <button className="btn secondary sm" onClick={() => setConfirmPurge(true)}>{tr('清理 180 天前的运营数据…')}</button>
          )}
        </div>
      </div>

    </>
  )
}


export function MemPanel() {
  const { data: memRes, isLoading } = useAdminMemory()
  const mem: MemoryEntry[] = memRes?.entries ?? []
  // usePagination 必须在任何 return 之前调用：否则"加载中 → 有数据"时
  // hook 数量变化，React 直接抛 #310 并整页白屏（已复现）。
  const pg = usePagination(mem)
  if (isLoading) return <Spinner full label={tr('加载记忆…')} />
  if (!mem.length) return <EmptyState icon={<Brain size={22} />} title={tr('暂无长期记忆')} desc={tr('用户产生偏好或多次对话后会自动沉淀在这里。')} />
  return (
    <>
      <div className="tbl-wrap">
        <table className="dt">
          <thead><tr><th>{tr('用户')}</th><th>Key</th><th>Value</th><th>{tr('更新')}</th></tr></thead>
          <tbody>
            {pg.pageItems.map((m: MemoryEntry, i: number) => (
              <tr key={`${m.visitor_id}-${m.key}-${i}`}>
                <td>{m.visitor_id}</td>
                <td><span className="badge info">{m.key}</span></td>
                <td>{m.value}</td>
                <td className="muted">{m.updated_at?.slice(0, 16)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pg.hasPages && <Pager page={pg.page} maxPage={pg.maxPage} total={pg.total} onChange={pg.setPage} label={tr('长期记忆')} />}
    </>
  )
}

/* ============ 注入日志 ============ */
export function InjPanel() {
  const { data: injRes, isLoading } = useAdminInjection()
  const inj: InjectionLogEntry[] = injRes?.entries ?? []
  // 同 MemPanel：hooks 必须在早退之前
  const pg = usePagination(inj)
  if (isLoading) return <Spinner full label={tr('加载注入日志…')} />
  if (!inj.length) return <EmptyState icon={<ShieldAlert size={22} />} title={tr('暂无注入拦截记录')} desc={tr('护栏被触发后会出现在这里。')} />
  return (
    <>
      <div className="tbl-wrap">
        <table className="dt">
          <thead><tr><th>#</th><th>{tr('用户')}</th><th>{tr('原始输入')}</th><th>{tr('命中')}</th><th>{tr('动作')}</th></tr></thead>
          <tbody>
            {pg.pageItems.map((m: InjectionLogEntry) => (
              <tr key={m.id}>
                <td>{m.id}</td>
                <td>{m.visitor_id}</td>
                <td className="raw" title={m.raw_input}>{m.raw_input}</td>
                <td><span className="badge danger">{m.detected}</span></td>
                <td>{m.action}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pg.hasPages && <Pager page={pg.page} maxPage={pg.maxPage} total={pg.total} onChange={pg.setPage} label={tr('注入日志')} />}
    </>
  )
}


/* ============ 档案（人物/群）：后端 /api/profiles ============ */

export function TokenPanel() {
  const adminToken = useAppStore((s) => s.adminToken)
  const setAdminToken = useAppStore((s) => s.setAdminToken)
  const [copied, setCopied] = useState(false)
  const [state, setState] = useState<'idle' | 'loading' | 'ok' | 'fail'>('idle')
  const [msg, setMsg] = useState('')

  const fetchToken = async () => {
    setState('loading')
    try {
      const r = await fetch('/api/bootstrap/local-token')
      const d = await r.json().catch(() => ({}))
      if (r.ok && d.available && d.token) {
        setAdminToken(d.token)
        setState('ok'); setMsg('已从本机服务获取到令牌')
      } else {
        setState('fail'); setMsg(d.detail || d.reason || `HTTP ${r.status}`)
      }
    } catch (e) {
      setState('fail'); setMsg((e as Error).message)
    }
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(adminToken)
      setCopied(true); setTimeout(() => setCopied(false), 1800)
    } catch { setMsg('复制被浏览器拒绝，请手动选中') }
  }

  return (
    <div className="space-y-4">
      <div className="text-sm text-muted" style={{ lineHeight: 1.8 }}>
        控制台用的是「访问令牌」而不是账号密码。本机打开时自动获取，远程访问才需要手动粘贴。
      </div>

      <div className="card p-4 space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold"><KeyRound size={15} /> {tr('当前令牌')}</div>
        {adminToken ? (
          <>
            <button
              className="w-full text-left font-mono text-xs border border-line-2 rounded-lg p-3 break-all"
              onClick={copy}
              title={tr('点击复制')}
            >
              {copied ? <span className="text-ok"><Check size={12} /> {tr('已复制到剪贴板')}</span> : adminToken}
            </button>
            <div className="flex gap-2">
              <button className="btn sm" onClick={copy}>{copied ? '已复制' : '复制令牌'}</button>
              <button className="btn secondary sm" onClick={fetchToken}>{tr('重新获取')}</button>
              <button className="btn ghost sm" onClick={() => { setAdminToken(''); setMsg('已清除，刷新页面后需重新登录') }}>
                清除
              </button>
            </div>
          </>
        ) : (
          <div className="text-xs text-muted">{tr('本机还没有令牌。点下面的按钮从服务端获取。')}</div>
        )}
        {msg && <div className="text-[11px] text-muted">{msg}</div>}
      </div>

      <div className="card p-4 space-y-2">
        <div className="text-sm font-semibold">{tr('换一台设备访问？')}</div>
        <div className="text-xs text-muted" style={{ lineHeight: 1.8 }}>
          1. 在这台机器上点「复制令牌」；<br />
          2. 在另一台设备打开控制台，粘贴到登录框；<br />
          3. 令牌只存在浏览器本地，不会上传。
        </div>
      </div>

      <div className="card p-4 space-y-2">
        <div className="text-sm font-semibold">{tr('安全说明')}</div>
        <div className="text-xs text-muted" style={{ lineHeight: 1.8 }}>
          本机自动获取只在 <code>127.0.0.1</code> / <code>::1</code> 回环地址生效，公网来源一律 403。
          公网部署建议设 <code>BIGROBOT_LOCAL_TOKEN_BOOTSTRAP=0</code> 彻底关闭该通道。
        </div>
      </div>
    </div>
  )
}

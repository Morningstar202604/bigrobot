import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { MessagesSquare, X, RefreshCw, Headset, Inbox, Search, Download } from 'lucide-react'
import { http, useAdminSessions, useCloseSession, useAccounts, isAuthError } from './lib/queries'
import TokenGate from './components/TokenGate'
import type { AgentMsg, SessionRow } from './types/api'
import { Spinner, ErrorBanner } from './components/Spinner'
import { ESCALATE_REASON, SESSION_STATUS, CHANNEL_LABEL, label } from './lib/labels'
import { EmptyState, PageHead } from './ui'
import { PAGE_SIZE, pageCount } from './lib/paging'
import Markdown from './components/Markdown'
import './pages.css'
import './pages2.css'
import { t } from './lib/t'

// 状态标签只有一份来源：lib/labels 的 SESSION_STATUS。这里只补一个「全部」。
const FILTERS = [
  { key: '', label: t('全部') },
  ...Object.entries(SESSION_STATUS).map(([key, label]) => ({ key, label })),
]

const STATUS_LABELS = SESSION_STATUS

const STATUS_TONE: Record<string, string> = {
  ongoing: 'info',
  pending_agent: 'warn',
  agent_handled: 'ok',
  closed: 'muted',
}

/** 渠道前缀在「渠道」列已经展示，这里只留可辨识的用户标识（如群号/QQ 号）。 */
function visitorLabel(vid?: string | null): string {
  if (!vid) return '-'
  const body = vid.includes(':') ? vid.slice(vid.indexOf(':') + 1) : vid
  return body.slice(0, 24) || '-'
}

function fmtTime(iso?: string | null): string {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
  } catch {
    return iso
  }
}

export default function SessionsCenter() {
  const [status, setStatus] = useState('')
  const [active, setActive] = useState<SessionRow | null>(null)
  const [dialog, setDialog] = useState<AgentMsg[]>([])
  const [loadingDialog, setLoadingDialog] = useState(false)
  const [query, setQuery] = useState('')
  const [appliedQuery, setAppliedQuery] = useState('')
  const [page, setPage] = useState(0)
  const [account, setAccount] = useState('')
  const accounts = useAccounts()
  const sessions = useAdminSessions(status || undefined, appliedQuery || undefined, page, 30, account || undefined)
  const close = useCloseSession()

  const total = sessions.data?.total ?? 0
  const maxPage = pageCount(total, PAGE_SIZE) - 1
  // 筛选后总数变少时把页码拉回最后一页，避免停在空白页。
  // 必须等本页数据回来再夹紧：新 queryKey 的首次渲染 total 还是 0，
  // 此时夹紧会把刚翻到的第 2 页立刻打回第 1 页（已复现）。
  useEffect(() => {
    if (!sessions.data) return
    if (page > maxPage) setPage(maxPage)
  }, [page, maxPage, sessions.data])

  const exportSession = async () => {
    if (!active) return
    try {
      const r = await http.get<{ markdown: string; filename: string }>(
        `/api/sessions/${active.id}/export?fmt=md`)
      const blob = new Blob([r.markdown], { type: 'text/markdown;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = r.filename || `session-${active.id.slice(0, 8)}.md`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      alert((e as Error).message)
    }
  }

  const [pullGroup, setPullGroup] = useState('')
  const [pulling, setPulling] = useState(false)
  const [members, setMembers] = useState<{ user_id: string; nickname: string; role: string }[] | null>(null)
  const [loading, setLoading] = useState('')
  const [transcribing, setTranscribing] = useState<number | null>(null)

  const transcribe = async (mid: number) => {
    if (!active) return
    setTranscribing(mid)
    try {
      const r = await http.post<{ text: string }>(`/api/sessions/${active.id}/messages/${mid}/transcribe`, {})
      alert(`${t('识别结果')}：${r.text}`)
      sessions.refetch()
    } catch (e) {
      alert((e as Error).message)
    } finally {
      setTranscribing(null)
    }
  }
  const [notices, setNotices] = useState<{ notice_id: string; text: string }[] | null>(null)
  const [files, setFiles] = useState<{ file_id: string; name: string; size: number; busid?: number }[] | null>(null)


  const loadNotices = async () => {
    if (!pullGroup.trim()) return
    setLoading('notices'); setFiles(null); setMembers(null)
    try {
      const r = await http.get<{ notices: { notice_id: string; text: string }[] }>(
        `/api/channel/qq/groups/${pullGroup.trim()}/notices`)
      setNotices(r.notices)
    } catch (e) {
      alert((e as Error).message)
    } finally { setLoading('') }
  }

  const loadFiles = async () => {
    if (!pullGroup.trim()) return
    setLoading('files'); setMembers(null)
    try {
      const r = await http.get<{ files: { file_id: string; name: string; size: number; busid?: number }[] }>(
        `/api/channel/qq/groups/${pullGroup.trim()}/files`)
      setFiles(r.files)
    } catch (e) {
      alert((e as Error).message)
    } finally {
      setLoading('')
    }
  }

  const loadMembers = async () => {
    if (!pullGroup.trim()) return
    setLoading('members'); setFiles(null)
    try {
      const r = await http.get<{ count: number; members: { user_id: string; nickname: string; role: string }[] }>(
        `/api/channel/qq/groups/${pullGroup.trim()}/members`)
      setMembers(r.members)
    } catch (e) {
      alert((e as Error).message)
    } finally {
      setLoading('')
    }
  }

  const pullHistory = async () => {
    if (!active || !pullGroup.trim()) return
    setPulling(true)
    try {
      const r = await http.post<{ added: number; skipped: number }>(
        `/api/sessions/${active.id}/history/pull`,
        { group_id: pullGroup.trim(), limit: 50 })
      await open(active)
      alert(`已拉取 ${r.added} 条，跳过重复 ${r.skipped} 条`)
    } catch (e) {
      alert((e as Error).message)
    } finally {
      setPulling(false)
    }
  }

  const open = async (s: SessionRow) => {
    setActive(s)
    setLoadingDialog(true)
    try {
      const d = await http.get<{ messages: AgentMsg[] }>(`/api/sessions/${s.id}/messages`)
      setDialog(d.messages || [])
    } catch {
      setDialog([])
    } finally {
      setLoadingDialog(false)
    }
  }

  const doClose = async () => {
    if (!active) return
    try {
      await close.mutateAsync(active.id)
      setActive({ ...active, status: 'closed' })
      await sessions.refetch()
    } catch {
      /* 错误经 mutation 暴露 */
    }
  }

  const items = sessions.data?.items ?? []

  return (
    <div className="p-4 md:p-6 max-w-[1400px] mx-auto w-full space-y-4 pb-24 md:pb-10">
      <PageHead
        title={t('会话中心')}
        sub={t(appliedQuery ? '会话搜索副标题' : '会话列表副标题', { query: appliedQuery, total: sessions.data?.total ?? '…' })}
        right={
          <>
            {FILTERS.map((f) => (
              <button
                key={f.key}
                onClick={() => { setStatus(f.key); setPage(0) }}
                className={`mod-toggle ${status === f.key ? 'on' : ''}`}
              >
                {t(f.label)}
              </button>
            ))}
            {(accounts.data?.accounts?.length ?? 0) > 0 && (
              <select
                className="input sm"
                aria-label={t('按账号筛选')}
                value={account}
                onChange={(e) => { setAccount(e.target.value); setPage(0) }}
              >
                <option value="">{t('全部账号')}</option>
                {accounts.data!.accounts.map((a) => {
                  const uid = a.id || a.account_id || a.platform_uid || ''
                  return (
                  <option key={`${a.channel}:${uid}`} value={uid}>
                    {a.display_name ? `${a.display_name}（${uid}）` : `${a.channel} · ${uid}`}
                  </option>
                  )
                })}
              </select>
            )}
            <div className="tb-search">
              <Search size={13} />
              <input
                placeholder={t('搜用户 / 会话 / 消息内容')}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') { setAppliedQuery(query.trim()); setPage(0) }
                  if (e.key === 'Escape') { setQuery(''); setAppliedQuery(''); setPage(0) }
                }}
                aria-label={t('搜索会话')}
              />
              {appliedQuery && (
                <button className="tb-search-clear" title={t('清除搜索')} onClick={() => { setQuery(''); setAppliedQuery(''); setPage(0) }}>
                  <X size={11} />
                </button>
              )}
            </div>
            <button className="btn ghost sm whitespace-nowrap" onClick={() => sessions.refetch()} title={t('立即刷新')}>
              <RefreshCw size={13} />
            </button>
          </>
        }
      />

      {sessions.isLoading && <Spinner full label={t('加载会话…')} />}
      {sessions.error && isAuthError(sessions.error) && (
        <TokenGate error={sessions.error} onAuthed={() => sessions.refetch()} />
      )}
      {sessions.error && !isAuthError(sessions.error) && (
        <ErrorBanner message={(sessions.error as Error).message} onRetry={() => sessions.refetch()} />
      )}

      {!sessions.isLoading && items.length === 0 && (
        <EmptyState icon={<Inbox size={22} />} title={t('没有匹配的会话')} desc={t('换一个筛选条件，或去对话页/群里产生一条新会话。')} />
      )}

      {items.length > 0 && (
        <>
        <div className="tbl-wrap">
          <table className="dt">
            <thead>
              <tr>
                <th>{t('开始时间')}</th>
                <th>{t('渠道')}</th>
                <th>{t('用户')}</th>
                <th>{t('状态')}</th>
                <th>{t('消息')}</th>
                <th>{t('首响')}</th>
                <th>{t('升级原因')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id} className="cursor-pointer" onClick={() => open(s)}>
                  <td className="muted">{fmtTime(s.started_at)}</td>
                  <td><span className="badge info">{label(CHANNEL_LABEL, s.channel)}</span></td>
                  <td className="raw" title={s.visitor_id}>{visitorLabel(s.visitor_id)}</td>
                  <td>
                    <span className={`badge ${STATUS_TONE[s.status] || 'muted'}`}>
                      {label(STATUS_LABELS, s.status)}
                    </span>
                  </td>
                  <td>{s.message_count}</td>
                  <td className="muted">
                    {s.first_response_seconds != null
                      ? `${s.first_response_seconds < 60 ? `${s.first_response_seconds}s` : `${Math.round(s.first_response_seconds / 60)}分`}`
                      : '-'}
                  </td>
                  <td className="muted">{label(ESCALATE_REASON, s.escalate_reason, '-')}</td>
                  <td>
                    <button
                      className="btn ghost sm whitespace-nowrap"
                      onClick={(e) => { e.stopPropagation(); open(s) }}
                    >
                      {t('查看')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="pager">
          <span>{t('分页状态', { total, page: page + 1, pages: maxPage + 1 })}</span>
          <button className="btn ghost sm whitespace-nowrap" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>{t('上一页')}</button>
          <button className="btn ghost sm whitespace-nowrap" disabled={page >= maxPage} onClick={() => setPage((p) => Math.min(maxPage, p + 1))}>{t('下一页')}</button>
        </div>
        </>
      )}

      {active && (
        <div className="drawer-mask" onClick={() => setActive(null)}>
          <div className="drawer" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-head">
              <h3 title={active.id}>会话 #{active.id.slice(0, 8)} · {label(CHANNEL_LABEL, active.channel)}</h3>
              <div className="flex gap-2">
                <button className="btn ghost sm whitespace-nowrap" onClick={exportSession} title={t('导出为 Markdown')}>
                  <Download size={13} /> 导出
                </button>
                <Link to="/operator" className="btn ghost sm whitespace-nowrap"><Headset size={13} /> {t('协作台')}</Link>
                {active.status !== 'closed' && (
                  <button className="btn secondary sm" onClick={doClose} disabled={close.isPending}>
                    <X size={13} /> {close.isPending ? '关闭中…' : '关闭会话'}
                  </button>
                )}
                <button className="btn ghost sm whitespace-nowrap" aria-label={t('关闭')} title={t('关闭')} onClick={() => setActive(null)}><X size={14} /></button>
              </div>
            </div>
            <div className="drawer-body space-y-3 max-h-[60vh] overflow-auto">
              <div className="flex flex-col gap-2">
                <input
                  className="tb-search-input w-full"
                  placeholder={t('群号，拉取 QQ 历史')}
                  value={pullGroup}
                  onChange={(e) => setPullGroup(e.target.value)}
                  aria-label={t('群号')}
                />
                <div className="flex flex-wrap gap-2">
                <button className="btn ghost sm whitespace-nowrap" onClick={() => void pullHistory()} disabled={loading !== '' || !pullGroup.trim()}>
                  {pulling ? t('拉取中…') : t('拉取历史')}
                </button>
                <button className="btn ghost sm whitespace-nowrap" onClick={() => void loadMembers()} disabled={loading !== '' || !pullGroup.trim()}>
                  {loading === 'members' ? t('加载中…') : t('成员')}
                </button>
                <button className="btn ghost sm whitespace-nowrap" onClick={() => void loadNotices()} disabled={loading !== '' || !pullGroup.trim()}>
                  {loading === 'notices' ? t('加载中…') : t('公告')}
                </button>
                <button className="btn ghost sm whitespace-nowrap" onClick={() => void loadFiles()} disabled={loading !== '' || !pullGroup.trim()}>
                  {loading === 'files' ? t('加载中…') : t('文件')}
                </button>
                </div>
              </div>
              {notices && (
                <div className="rounded border border-[var(--line,#e5e7eb)] p-2 max-h-40 overflow-auto text-[12px] whitespace-pre-wrap">
                  <div className="text-muted mb-1">{t('群公告')} {notices.length}</div>
                  {notices.map((n) => <div key={n.notice_id}>{n.text}</div>)}
                </div>
              )}
              {files && (
                <div className="rounded border border-[var(--line,#e5e7eb)] p-2 max-h-40 overflow-auto text-[12px]">
                  <div className="text-muted mb-1 flex justify-between items-center">
                    <span>{t('群文件')} {files.length}</span>
                    <label className="btn ghost sm cursor-pointer">
                      {t('上传')}
                      <input type="file" className="hidden" onChange={async (ev) => {
                        const f = ev.target.files?.[0]; if (!f) return
                        const fd = new FormData(); fd.append('file', f)
                        setLoading('upload')
                        try {
                          await http.postForm(`/api/channel/qq/groups/${pullGroup.trim()}/upload`, fd)
                          await loadFiles()
                        } catch (e) { alert((e as Error).message) } finally { setLoading('') }
                      }} />
                    </label>
                  </div>
                  {files.map((f) => (
                    <div key={f.file_id || f.name} className="flex justify-between gap-2 items-center">
                      <span className="truncate">{f.name}</span>
                      <span className="text-muted shrink-0">{(f.size / 1024).toFixed(0)} KB</span>
                      <button
                        className="btn ghost sm shrink-0"
                        onClick={async () => {
                          try {
                            const r = await http.get<{ url: string }>(
                              `/api/channel/qq/groups/${pullGroup.trim()}/files/${f.file_id}/url?busid=${f.busid ?? 0}`)
                            window.open(r.url, '_blank')
                          } catch (e) { alert((e as Error).message) }
                        }}
                      >
                        {t('下载')}
                      </button>
                    </div>
                  ))}
                </div>
              )}
              {members && (
                <div className="rounded border border-[var(--line,#e5e7eb)] p-2 max-h-40 overflow-auto text-[12px]">
                  <div className="text-muted mb-1">{t('群成员')} {members.length}</div>
                  {members.map((m) => (
                    <div key={m.user_id} className="flex justify-between gap-2">
                      <span className="truncate">{m.nickname || m.user_id}</span>
                      <span className="text-muted shrink-0">
                        {m.role === 'owner' ? t('群主') : m.role === 'admin' ? t('管理员') : t('成员')}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {close.error && <ErrorBanner message={(close.error as Error).message} onRetry={() => sessions.refetch()} />}
              {loadingDialog && <Spinner label={t('加载对话…')} />}
              {!loadingDialog && dialog.length === 0 && <div className="empty">{t('该会话暂无消息')}</div>}
              {dialog.map((m, i) => (
                <div key={m.id ?? m.ts ?? i} className={`msg-row ${m.role === 'visitor' ? 'visitor' : m.role === 'operator' ? 'operator' : 'agent'}`}>
                  <div className="msg-body">
                    <div className="bubble">
                      <span className="text-[10px] text-muted mr-2">
                        {m.role === 'visitor' ? '用户' : m.role === 'operator' ? '管理员' : '秘书'}
                        {(m as AgentMsg & { source?: string }).source === 'platform' && ' · QQ 历史'}
                      </span>
                      {m.role === 'visitor' ? m.content : <Markdown text={m.content} />}
                      {Boolean((m as AgentMsg & { refs?: string[] }).refs?.length) && (
                        <button
                          className="btn ghost sm mt-1"
                          disabled={transcribing === m.id}
                          onClick={() => m.id !== undefined && void transcribe(m.id)}
                        >
                          {transcribing === m.id ? t('识别中…') : t('转写')}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
              {active.escalate_reason && (
                <div className="text-xs text-muted">升级原因：{label(ESCALATE_REASON, active.escalate_reason)} · 开始 {fmtTime(active.started_at)}</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

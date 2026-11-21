import { useRef, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Inbox, ClipboardList, Radio, X, Headset, Ticket, RefreshCw,
  StickyNote, Download, Search, MessagesSquare,
} from 'lucide-react'
import {
  http, useOperatorQueues, useAdminSessions, useCloseSession, useAccounts,
  isAuthError,
} from './lib/queries'
import TokenGate from './components/TokenGate'
import { useFeedback } from './components/Feedback'
import Markdown from './components/Markdown'
import { ESCALATE_REASON, SESSION_STATUS, CHANNEL_LABEL, label } from './lib/labels'
import { useWs } from './hooks/useWs'
import { useAppStore, ensureOpId } from './store/appStore'
import { useShell } from './components/ResponsiveShell'
import { Avatar, MsgMeta, ThoughtBlock } from './ui'
import { Spinner, ErrorBanner } from './components/Spinner'
import { PAGE_SIZE, pageCount } from './lib/paging'
import './pages.css'
import './pages2.css'
import { t } from './lib/t'
import { K, readJson, writeJson } from './lib/storage'

/** 快捷回复（Chatwoot canned responses 对标）：常用话术一键插入，本地可编辑 */
const CANNED_DEFAULT = [
  '您好，稍等，我帮您查询一下~',
  '亲，这个问题的标准处理方式是：签收后 7 天内可无理由退货，质量问题 15 天内可换货。',
  '已经为您登记，24 小时内会有专人跟进处理。',
  '感谢您的耐心等待，还有其他可以帮您的吗？',
]

function CannedBar({ onPick }) {
  const [items, setItems] = useState(() => {
    const v = readJson(K.canned, CANNED_DEFAULT)
    return Array.isArray(v) && v.length ? v : CANNED_DEFAULT
  })
  const [editing, setEditing] = useState(false)
  const save = (list) => { setItems(list); writeJson(K.canned, list) }
  return (
    <div className="canned-bar">
      {!editing ? (
        <>
          {items.map((text, i) => (
            <button key={i} className="canned-chip" title={t('点击插入到输入框')} onClick={() => onPick(text)}>
              {text.length > 18 ? text.slice(0, 18) + '…' : text}
            </button>
          ))}
          <button className="canned-edit" onClick={() => setEditing(true)}>{t('编辑')}</button>
        </>
      ) : (
        <div className="canned-editing">
          {items.map((text, i) => (
            <div key={i} className="canned-row">
              <input value={text} onChange={(e) => { const n = [...items]; n[i] = e.target.value; setItems(n) }} />
              <button className="ac-del" onClick={() => save(items.filter((_, j) => j !== i))}>✕</button>
            </div>
          ))}
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="btn secondary sm" onClick={() => setItems([...items, ''])}>{t('+ 加一条')}</button>
            <button className="btn sm" onClick={() => { save(items.filter((text) => text.trim())); setEditing(false) }}>{t('完成')}</button>
          </div>
        </div>
      )}
    </div>
  )
}

/** 内部备注面板（Chatwoot 对标）：只给协作团队看，用户永远看不到 */
function NotesPanel({ sid }) {
  const [notes, setNotes] = useState([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    let dead = false
    http.get(`/api/operator/notes/${sid}`)
      .then((d) => { if (!dead) setNotes(d.notes || []) })
      .catch((e) => { if (!dead) setErr(e.message) })
    return () => { dead = true }
  }, [sid])

  const add = async () => {
    if (!text.trim() || busy) return
    setBusy(true); setErr('')
    try {
      const d = await http.post(`/api/operator/notes/${sid}`, { content: text.trim() })
      setNotes((n) => [d.note, ...n])
      setText('')
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="notes-panel">
      <div className="notes-title"><StickyNote size={13} /> {t('内部备注（用户不可见）')}</div>
      <div className="notes-list">
        {notes.length === 0 && <div className="notes-empty">{t('暂无备注。')}</div>}
        {notes.map((n) => (
          <div key={n.id} className="notes-item">
            <div className="notes-text">{n.content}</div>
            <div className="notes-meta">{(n.operator || '真人')} · {(n.created_at || '').slice(0, 16).replace('T', ' ')}</div>
          </div>
        ))}
      </div>
      {err && <div className="notes-err">{err}</div>}
      <div className="notes-add">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
          placeholder={t('记点内部信息：用户情绪、承诺事项、跟进计划…')}
          maxLength={2000}
        />
        <button className="btn secondary sm" onClick={add} disabled={busy || !text.trim()}>{t('记下')}</button>
      </div>
    </div>
  )
}

function normRole(r) {
  return r === 'agent' ? 'agent' : r === 'operator' ? 'operator' : r === 'system' ? 'system' : 'visitor'
}

function formatTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function fmtDate(iso) {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
    })
  } catch {
    return iso
  }
}

function visitorLabel(vid) {
  if (!vid) return '-'
  const body = vid.includes(':') ? vid.slice(vid.indexOf(':') + 1) : vid
  return body.slice(0, 18) || '-'
}

const STATUS_TONE = {
  ongoing: 'info',
  pending_agent: 'warn',
  agent_handled: 'ok',
  closed: 'muted',
}

const FILTERS = [
  { key: '', label: '全部' },
  ...Object.entries(SESSION_STATUS).map(([key, text]) => ({ key, label: text })),
]

export default function OperatorDesk() {
  const [params] = useSearchParams()
  const [mode, setMode] = useState('all') // all | tickets
  const [status, setStatus] = useState(params.get('status') || '')
  const [query, setQuery] = useState('')
  const [appliedQuery, setAppliedQuery] = useState('')
  const [page, setPage] = useState(0)
  const [account, setAccount] = useState('')
  const [active, setActive] = useState(null)
  const [dialog, setDialog] = useState([])
  const [loadingDialog, setLoadingDialog] = useState(false)
  const [reply, setReply] = useState('')
  const [notesOpen, setNotesOpen] = useState(false)
  const [error, setError] = useState('')
  const opId = useAppStore((s) => s.opId)
  const adminToken = useAppStore((s) => s.adminToken)
  const fb = useFeedback()
  const setDraft = useAppStore((s) => s.setDraft)
  const { mobile } = useShell()
  const bodyRef = useRef(null)
  const footRef = useRef(null)

  const sessionsQ = useAdminSessions(status || undefined, appliedQuery || undefined, page, PAGE_SIZE, account || undefined)
  const accountsQ = useAccounts()
  const queues = useOperatorQueues()
  const close = useCloseSession()

  const total = sessionsQ.data?.total ?? 0
  const maxPage = pageCount(total, PAGE_SIZE) - 1
  const items = sessionsQ.data?.items ?? []

  useEffect(() => {
    if (!sessionsQ.data) return
    if (page > maxPage) setPage(maxPage)
  }, [page, maxPage, sessionsQ.data])

  // 协作回复草稿走 zustand（切页不丢）
  const onReplyChange = (v) => {
    setReply(v)
    setDraft('operator-reply', v)
  }

  // 键盘弹起时把输入区保持在可视范围内（visualViewport）
  useEffect(() => {
    const vv = window.visualViewport
    if (!vv) return
    const onResize = () => {
      if (footRef.current) {
        footRef.current.style.bottom = Math.max(0, vv.offsetTop + vv.height - window.innerHeight) + 'px'
      }
    }
    vv.addEventListener('resize', onResize)
    vv.addEventListener('scroll', onResize)
    return () => {
      vv.removeEventListener('resize', onResize)
      vv.removeEventListener('scroll', onResize)
    }
  }, [])

  // WS 实时接收新会话 / 状态变更（useWs 自动重连）
  const wsUrl = adminToken ? '/ws/operator' : null
  const wsSubs = adminToken ? ['bigrobot-admin', adminToken] : undefined
  const activeRef = useRef(null)
  useEffect(() => { activeRef.current = active }, [active])
  const { state: connState } = useWs(wsUrl, (p) => {
    if (p.type === 'new_pending' || p.type === 'session_updated') {
      sessionsQ.refetch()
      queues.refetch()
    }
    if (p.type === 'visitor_message' && p.session_id === activeRef.current?.id) {
      setDialog((prev) => [...prev, {
        role: 'visitor', content: String(p.content ?? ''), ts: new Date().toISOString(),
      }])
    }
  }, !!adminToken, wsSubs)

  useEffect(() => { ensureOpId() }, [])
  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight
  }, [dialog, active])
  useEffect(() => { setNotesOpen(false) }, [active])

  const openDialog = async (s) => {
    setActive(s)
    setError('')
    setLoadingDialog(true)
    try {
      const d = await http.get(`/api/sessions/${s.id}/messages`)
      setDialog((d.messages || []).map((m) => ({ ...m, role: normRole(m.role) })))
    } catch {
      setDialog([])
    } finally {
      setLoadingDialog(false)
    }
  }

  const take = async (sid) => {
    setError('')
    try {
      await http.post(`/api/sessions/${sid}/op`, { op: 'take', visitor_id: opId })
      const row = sessionsQ.data?.items?.find((x) => x.id === sid)
      await Promise.all([sessionsQ.refetch(), queues.refetch()])
      if (row) await openDialog({ ...row, status: 'agent_handled' })
      else setActive((prev) => prev && prev.id === sid ? { ...prev, status: 'agent_handled' } : prev)
    } catch (e) {
      setError(e.message)
    }
  }

  const doReply = async () => {
    const c = reply.trim()
    if (!c || !active || active.status === 'closed') return
    const tempId = `op-${Date.now()}`
    onReplyChange('')
    setDialog((prev) => [...prev, {
      role: 'operator', content: c, ts: new Date().toISOString(), tempId,
    }])
    try {
      await http.post(`/api/sessions/${active.id}/op`, { op: 'reply', content: c })
      sessionsQ.refetch()
    } catch (e) {
      // 失败必须撤回乐观气泡并把内容回填输入框，否则坐席以为已经发出去了
      setDialog((prev) => prev.filter((m) => m.tempId !== tempId))
      onReplyChange(c)
      setError(`发送失败：${e.message || '请重试'}`)
    }
  }

  const closeSess = async () => {
    if (!active) return
    setError('')
    try {
      await close.mutateAsync(active.id)
      setActive(null)
      setDialog([])
      await sessionsQ.refetch()
    } catch (e) {
      setError(e.message)
    }
  }

  const exportSession = async () => {
    if (!active) return
    try {
      const r = await http.get(`/api/sessions/${active.id}/export?fmt=md`)
      const blob = new Blob([r.markdown], { type: 'text/markdown;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = r.filename || `session-${active.id.slice(0, 8)}.md`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      fb.toast.error(e.message || '导出失败')
    }
  }

  const setStatusFilter = (key) => { setStatus(key); setPage(0) }
  const applyQuery = () => { setAppliedQuery(query.trim()); setPage(0) }
  const clearQuery = () => { setQuery(''); setAppliedQuery(''); setPage(0) }

  const tickets = queues.data?.tickets ?? []
  const pendingCount = queues.data?.sessions?.length ?? 0
  const isMobile = mobile

  return (
    <div className={`op-app ${isMobile ? 'op-app-mobile' : ''} ${isMobile && active ? 'show-dialog' : ''}`}
      style={isMobile ? undefined : { height: 'calc(100dvh - 170px)', minHeight: 420 }}>
      <section className="op-pane op-left">
        <div className={`op-left-head ${isMobile ? 'op-left-head-mobile' : ''}`}>
          <div className="op-conn">
            <Radio size={14} />
            <span>
              {connState === 'online' ? '实时通道在线' : connState === 'connecting' ? '连接中…' : '已断开，重连中'}
            </span>
            {pendingCount > 0 && <span className="badge warn" style={{ marginLeft: 'auto' }}>待接管 {pendingCount}</span>}
            <span className={`dot ${connState === 'online' ? 'online' : connState === 'connecting' ? 'connecting' : 'offline'}`} style={{ marginLeft: pendingCount > 0 ? 6 : 'auto' }} />
          </div>
          <div className="op-tabs">
            <button className={`op-tab ${mode === 'all' ? 'on' : ''}`} onClick={() => { setMode('all'); setPage(0) }}>
              <Inbox size={13} style={{ verticalAlign: '-2px', marginRight: 4 }} />
              会话（{total}）
            </button>
            <button className={`op-tab ${mode === 'tickets' ? 'on' : ''}`} onClick={() => setMode('tickets')}>
              <ClipboardList size={13} style={{ verticalAlign: '-2px', marginRight: 4 }} />
              工单（{tickets.length}）
            </button>
          </div>

          {mode === 'all' && (
            <div className="op-filters">
              <div className="op-status-filters">
                {FILTERS.map((f) => (
                  <button key={f.key} className={`mod-toggle ${status === f.key ? 'on' : ''}`}
                    onClick={() => setStatusFilter(f.key)}>{t(f.label)}</button>
                ))}
              </div>
              <div className="tb-search" style={{ marginTop: 8 }}>
                <Search size={13} />
                <input
                  placeholder={t('搜用户 / 会话 / 消息内容')}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') applyQuery()
                    if (e.key === 'Escape') clearQuery()
                  }}
                  aria-label={t('搜索会话')}
                />
                {appliedQuery && (
                  <button className="tb-search-clear" title={t('清除搜索')} onClick={clearQuery}>
                    <X size={11} />
                  </button>
                )}
              </div>
              {(accountsQ.data?.accounts?.length ?? 0) > 0 && (
                <select className="input sm" style={{ marginTop: 8, width: '100%' }}
                  aria-label={t('按账号筛选')} value={account}
                  onChange={(e) => { setAccount(e.target.value); setPage(0) }}>
                  <option value="">{t('全部账号')}</option>
                  {accountsQ.data.accounts.map((a) => {
                    const uid = a.id || a.account_id || a.platform_uid || ''
                    return (
                      <option key={`${a.channel}:${uid}`} value={uid}>
                        {a.display_name ? `${a.display_name}（${uid}）` : `${a.channel} · ${uid}`}
                      </option>
                    )
                  })}
                </select>
              )}
            </div>
          )}

          <div className="op-opid" style={{ marginTop: 8 }}>
            <Headset size={12} style={{ verticalAlign: '-1px' }} /> 真人 {opId || '…'}
          </div>
        </div>

        <div className={`op-list ${isMobile ? 'op-list-mobile' : ''}`}>
          {mode === 'all' && sessionsQ.isLoading && <Spinner label={t('加载会话…')} />}
          {mode === 'all' && sessionsQ.error && isAuthError(sessionsQ.error) && (
            <TokenGate error={sessionsQ.error} onAuthed={() => sessionsQ.refetch()} />
          )}
          {mode === 'all' && sessionsQ.error && !isAuthError(sessionsQ.error) && (
            <ErrorBanner message={sessionsQ.error?.message} onRetry={() => sessionsQ.refetch()} />
          )}
          {mode === 'all' && !sessionsQ.isLoading && items.length === 0 && (
            <div className="empty">{t('没有匹配的会话')}</div>
          )}

          {mode === 'all' && items.map((s) => (
            <div key={s.id} className={`op-card ${active?.id === s.id ? 'active' : ''}`} onClick={() => openDialog(s)}>
              <div className="op-card-title">
                <span><MessagesSquare size={13} style={{ verticalAlign: '-2px', marginRight: 4 }} /> 会话 #{String(s.id).slice(0, 8)}</span>
                <span className={`badge ${STATUS_TONE[s.status] || 'muted'}`}>{label(SESSION_STATUS, s.status)}</span>
              </div>
              <div className="op-card-meta">
                <span>{label(CHANNEL_LABEL, s.channel)}</span>
                <span>· {visitorLabel(s.visitor_id)}</span>
                <span>· {s.message_count} 条</span>
              </div>
              <div className="op-card-meta">{fmtDate(s.started_at)} · {label(ESCALATE_REASON, s.escalate_reason, '-')}</div>
              {s.status === 'pending_agent' && (
                <div className="op-actions">
                  <button className="btn sm" onClick={(e) => { e.stopPropagation(); take(s.id) }}>{t('接管并对话')}</button>
                </div>
              )}
            </div>
          ))}

          {mode === 'tickets' && queues.isLoading && <Spinner label={t('加载工单…')} />}
          {mode === 'tickets' && queues.isError && !isAuthError(queues.error) && (
            <ErrorBanner message={queues.error?.message} onRetry={() => queues.refetch()} />
          )}
          {mode === 'tickets' && !queues.isLoading && tickets.length === 0 && (
            <div className="empty">{t('暂无工单')}</div>
          )}
          {mode === 'tickets' && tickets.map((tk) => (
            <div key={tk.id} className={`op-card ${active?.id === tk.session_id ? 'active' : ''}`}
              onClick={() => {
                const row = sessionsQ.data?.items?.find((x) => x.id === tk.session_id)
                openDialog(row || {
                  id: tk.session_id,
                  status: 'pending_agent',
                  channel: 'onebot_v11',
                  visitor_id: '',
                  message_count: 0,
                  started_at: tk.created_at,
                  escalate_reason: null,
                })
              }}>
              <div className="op-card-title">
                <span><Ticket size={13} style={{ verticalAlign: '-2px', marginRight: 4 }} /> {tk.id} · #{String(tk.session_id).slice(0, 8)}</span>
                <span className="badge muted">{tk.priority}</span>
              </div>
              <div className="op-card-meta">{tk.status} · {new Date(tk.created_at).toLocaleDateString('zh-CN')}</div>
            </div>
          ))}
        </div>

        {mode === 'all' && total > PAGE_SIZE && (
          <div className="pager" style={{ padding: '0 10px 10px' }}>
            <span>{t('分页状态', { total, page: page + 1, pages: maxPage + 1 })}</span>
            <button className="btn ghost sm whitespace-nowrap" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>{t('上一页')}</button>
            <button className="btn ghost sm whitespace-nowrap" disabled={page >= maxPage} onClick={() => setPage((p) => Math.min(maxPage, p + 1))}>{t('下一页')}</button>
          </div>
        )}
      </section>

      <section className="op-pane op-right">
        <div className="op-right-head">
          <h3>
            {active ? `会话 #${active.id.slice(0, 8)} · ${label(CHANNEL_LABEL, active.channel)}` : '选择一个会话开始服务'}
          </h3>
          {active && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {active.status === 'pending_agent' && (
                <button className="btn sm" onClick={() => take(active.id)}>{t('接管并对话')}</button>
              )}
              <button className="btn ghost sm" onClick={exportSession} title={t('导出为 Markdown')}>
                <Download size={13} /> {t('导出')}
              </button>
              <button className="btn ghost sm" onClick={() => openDialog(active)}><RefreshCw size={13} /> {t('刷新')}</button>
              <button className="btn ghost sm" onClick={() => setNotesOpen((o) => !o)}>
                <StickyNote size={13} /> {t('备注')}
              </button>
              {active.status !== 'closed' && (
                <button className="btn secondary sm" onClick={closeSess} disabled={close.isPending}>
                  <X size={13} /> {close.isPending ? '关闭中…' : t('关闭')}
                </button>
              )}
              {isMobile && (
                <button className="btn ghost sm" onClick={() => { setActive(null); setDialog([]) }}>
                  <X size={13} /> {t('返回列表')}
                </button>
              )}
            </div>
          )}
        </div>

        {error && <div className="hint err" style={{ margin: '10px 20px 0' }}>{error}</div>}
        {active && notesOpen && <NotesPanel sid={active.id} />}

        <div className={`op-dialog ${isMobile ? 'op-dialog-mobile' : ''}`} ref={bodyRef}>
          {!active && <div className="empty" style={{ margin: 'auto' }}>{t('从左侧选择一个会话，接管后可直接以真人身份回复。')}</div>}
          {active && loadingDialog && <Spinner label={t('加载对话…')} />}
          {!loadingDialog && dialog.map((m, i) =>
            m.role === 'system' ? (
              <div key={i} className="msg-row system"><div className="system-line">{m.content}</div></div>
            ) : (
              <div key={i} className={`msg-row ${m.role}`}>
                <Avatar kind={m.role === 'visitor' ? 'visitor' : m.role === 'operator' ? 'operator' : 'agent'} size={30} />
                <div className="msg-body">
                  {m.role === 'agent' && m.thought && <ThoughtBlock text={m.thought} />}
                  <div className="bubble">
                    {m.role === 'visitor' ? m.content : <Markdown text={m.content} />}
                  </div>
                  <MsgMeta msg={m} />
                  {m.ts && <span className="msg-time">{formatTime(m.ts)}</span>}
                  {(m.role === 'agent' || m.role === 'operator') && (
                    <button
                      className="btn secondary sm"
                      style={{ marginTop: 4 }}
                      title={t('把这条回复沉淀为知识库条目，下次同样问题自动回答')}
                      onClick={() => {
                        const text = (m.content || '').trim()
                        if (!text) return
                        http.post('/api/kb', { text })
                          .then((d) => fb.toast.success(`已存入知识库：${d.entry.id}（共 ${d.total} 条）`))
                          .catch((e) => fb.toast.error(e.message || '保存失败'))
                      }}
                    >
                      存为知识库
                    </button>
                  )}
                </div>
              </div>
            ),
          )}
          {active && !loadingDialog && dialog.length === 0 && <div className="empty">{t('该会话暂无消息')}</div>}
        </div>

        {active && active.status === 'pending_agent' && (
          <div className="op-foot" style={{ justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>
            {t('先点上方「接管并对话」，再以真人身份回复。')}
          </div>
        )}
        {active && active.status !== 'closed' && active.status !== 'pending_agent' && (
          <div ref={footRef} className={`op-foot ${isMobile ? 'op-foot-mobile' : ''}`} style={isMobile ? { position: 'sticky', bottom: 0 } : undefined}>
            <CannedBar onPick={(text) => onReplyChange(reply ? reply + ' ' + text : text)} />
            <textarea
              rows={1}
              value={reply}
              placeholder={t('以真人身份回复…')}
              onChange={(e) => onReplyChange(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doReply() } }}
            />
            <button className="btn" onClick={doReply} disabled={!reply.trim()}>{t('回复')}</button>
          </div>
        )}
        {active && active.status === 'closed' && (
          <div className="op-foot" style={{ justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>
            {t('会话已关闭，不能继续回复。')}
          </div>
        )}
      </section>
    </div>
  )
}

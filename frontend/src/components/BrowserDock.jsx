import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ChevronLeft, ChevronRight, Globe, Camera, RefreshCw, X, Loader2, ArrowRight,
} from 'lucide-react'
import { useAppStore } from '../store/appStore'
import { http } from '../lib/queries'
import { t } from '../lib/t'

/**
 * 侧边栏浏览器面板（ZCode 式）：
 * - 收起时只占一行，展开后侧栏变宽，显示当前会话的独立浏览器上下文；
 * - 只展示截图 + URL，真正的点击/输入仍走聊天里的 browser_* 工具；
 * - 所有接口要求管理员令牌；不同 session_id 各自一个 BrowserContext。
 */
export default function BrowserDock({ open, onToggle }) {
  const sid = useAppStore((s) => s.sessionId)
  const adminToken = useAppStore((s) => s.adminToken)
  const [url, setUrl] = useState('')
  const [state, setState] = useState({ connected: false, url: '', title: '', sessions: 0 })
  const [shot, setShot] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const seq = useRef(0)

  const base = sid ? `/api/browser/sessions/${sid}` : ''

  const capture = useCallback(async () => {
    if (!base) return null
    setBusy('shot')
    try {
      const r = await http.post(`${base}/screenshot`)
      setShot(r.image_data_url || '')
      setState((s) => ({ ...s, connected: true, url: r.url || s.url, title: r.title || s.title }))
      setError('')
      return r
    } catch (e) {
      setError(e?.message || '截图失败')
      return null
    } finally {
      setBusy('')
    }
  }, [base])

  const load = useCallback(async () => {
    if (!base || !adminToken) return
    const n = ++seq.current
    setBusy('load')
    setError('')
    try {
      const r = await http.get(base)
      if (n !== seq.current) return
      setState(r)
      if (r.connected) {
        await capture()
      } else {
        setShot('')
      }
    } catch (e) {
      if (n === seq.current) setError(e?.message || '读取浏览器状态失败')
    } finally {
      if (n === seq.current) setBusy('')
    }
  }, [base, adminToken, capture])

  useEffect(() => {
    if (open && sid && adminToken) load()
    if (!open) return
    // 切换会话时先清掉上一会话的截图，避免把 A 的页面看成 B 的
    setShot('')
    setState({ connected: false, url: '', title: '', sessions: 0 })
  }, [open, sid, adminToken, load])

  const openUrl = async () => {
    const target = url.trim()
    if (!target) return
    setBusy('open')
    setError('')
    try {
      const r = await http.post(`${base}/open`, { url: target })
      setState({ connected: true, url: r.url || target, title: r.title || '', sessions: state.sessions })
      await capture()
      setUrl('')
    } catch (e) {
      setError(e?.message || '打开失败')
    } finally {
      setBusy('')
    }
  }

  const closeBrowser = async () => {
    setBusy('close')
    try {
      await http.post(`${base}/close`)
      setShot('')
      setState({ connected: false, url: '', title: '', sessions: 0 })
      setError('')
    } catch (e) {
      setError(e?.message || '关闭失败')
    } finally {
      setBusy('')
    }
  }

  const statusText = state.connected ? t('运行中') : t('未打开')

  return (
    <div className="browser-group">
      <div className="nav-group-label">{t('浏览器')}</div>
      <button
        className={`shell-item browser-toggle ${open ? 'active' : ''}`}
        onClick={() => onToggle(!open)}
        title={t('展开浏览器侧栏')}
      >
        <Globe size={16} />
        <span>{t('浏览器面板')}</span>
        <span className={`browser-dot ${state.connected ? 'on' : ''}`} />
        {open ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
      </button>

      {open && (
        <div className="browser-dock-card">
          <div className="browser-dock-head">
            <span className="browser-dock-title">
              <Globe size={13} /> {t('浏览器')}
            </span>
            <span className={`browser-state ${state.connected ? 'on' : ''}`}>{statusText}</span>
            <button className="browser-icon-btn" onClick={() => onToggle(false)} title={t('收起')}>
              <X size={14} />
            </button>
          </div>

          {!adminToken ? (
            <div className="browser-empty">{t('需要管理员令牌。到设置里填好 X-Admin-Token 后再用。')}</div>
          ) : !sid ? (
            <div className="browser-empty">{t('先在左边对话里发一条消息，建立会话后这里会自动绑定。')}</div>
          ) : (
            <>
              <div className="browser-session-line">
                <span>#{sid.slice(0, 8)}</span>
                <em>{t('独立上下文')}</em>
              </div>

              <div className="browser-url-row">
                <input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') openUrl() }}
                  placeholder="https://example.com"
                  spellCheck={false}
                />
                <button className="browser-go" onClick={openUrl} disabled={!!busy || !url.trim()} title={t('打开')}>
                  {busy === 'open' ? <Loader2 size={13} className="spin" /> : <ArrowRight size={13} />}
                </button>
              </div>

              <div className="browser-shot-wrap">
                {shot ? (
                  <a href={shot} target="_blank" rel="noreferrer" title={t('在新标签打开截图')}>
                    <img src={shot} alt={state.title || t('网页截图')} className="browser-shot" />
                  </a>
                ) : (
                  <div className="browser-shot-empty">
                    {state.connected ? t('正在截取页面…') : t('输入网址，或直接在对话里说「用浏览器打开 …」')}
                  </div>
                )}
              </div>

              <div className="browser-meta">
                <div className="browser-meta-title">{state.title || t('(无标题)')}</div>
                <div className="browser-meta-url" title={state.url}>{state.url || '—'}</div>
              </div>

              {error && <div className="browser-error">{error}</div>}

              <div className="browser-actions">
                <button onClick={() => capture()} disabled={!!busy || !state.connected}>
                  {busy === 'shot' ? <Loader2 size={12} className="spin" /> : <Camera size={12} />}
                  {t('截图')}
                </button>
                <button onClick={load} disabled={!!busy}>
                  {busy === 'load' ? <Loader2 size={12} className="spin" /> : <RefreshCw size={12} />}
                  {t('刷新')}
                </button>
                <button onClick={closeBrowser} disabled={!!busy || !state.connected} className="danger">
                  <X size={12} /> {t('关闭')}
                </button>
              </div>

              <div className="browser-hint">{t('点击、输入请在对话里说；每个会话独立 Cookie，最多保留 4 个。')}</div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

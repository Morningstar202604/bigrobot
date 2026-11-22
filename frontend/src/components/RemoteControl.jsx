import { useEffect, useRef, useState } from 'react'
import {
  Smartphone, X, Loader2, Copy, RefreshCw, ShieldAlert, Wifi, QrCode, Square,
} from 'lucide-react'
import { useAppStore } from '../store/appStore'
import { http } from '../lib/queries'
import { t } from '../lib/t'

/**
 * 手机远控入口（ZCode Remote Control 式）：
 * - 关闭弹窗不断开，必须点「停止」；
 * - 二维码短时有效、只用于配对；刷新后旧链接和旧手机立即失效；
 * - 手机拿到的是 12 小时临时令牌，只控制这一台程序，不新开运行环境。
 */
export default function RemoteControl() {
  const adminToken = useAppStore((s) => s.adminToken)
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState('auto')
  const [status, setStatus] = useState(null)
  const [qr, setQr] = useState('')
  const [url, setUrl] = useState('')
  const [warning, setWarning] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [copied, setCopied] = useState(false)
  const poll = useRef(null)

  const load = async () => {
    if (!adminToken) return
    try {
      const s = await http.get('/api/remote/status')
      setStatus(s)
    } catch (e) {
      setError(e?.message || '读取远控状态失败')
    }
  }

  useEffect(() => {
    if (!open) return
    setError('')
    load()
    poll.current = setInterval(load, 5000)
    return () => {
      clearInterval(poll.current)
      poll.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, adminToken])

  const start = async (refresh = false) => {
    setBusy(refresh ? 'refresh' : 'start')
    setError('')
    setCopied(false)
    try {
      const r = await http.post('/api/remote/start', { mode })
      setQr(r.qr || '')
      setUrl(r.url || '')
      setWarning(r.warning || '')
      setStatus(await http.get('/api/remote/status'))
    } catch (e) {
      setError(e?.message || '生成连接失败')
    } finally {
      setBusy('')
    }
  }

  const stop = async () => {
    setBusy('stop')
    try {
      await http.post('/api/remote/stop')
      setQr('')
      setUrl('')
      setWarning('')
      setStatus(await http.get('/api/remote/status'))
    } catch (e) {
      setError(e?.message || '停止失败')
    } finally {
      setBusy('')
    }
  }

  const copy = async () => {
    if (!url) return
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      window.prompt('复制这个链接发给手机：', url)
    }
  }

  const connected = status?.connected > 0
  const waiting = status?.waiting
  const left = status?.pair_expires_in || 0

  return (
    <>
      <div className="remote-group">
        <div className="nav-group-label">{t('远程')}</div>
        <button className="shell-item remote-toggle" onClick={() => setOpen(true)} title={t('手机远程控制')}>
          <Smartphone size={16} />
          <span>{t('远程控制')}</span>
          <span className={`browser-dot ${connected ? 'on' : ''}`} />
        </button>
      </div>

      {open && (
        <div className="remote-modal-mask" onClick={() => setOpen(false)}>
          <div className="remote-modal" onClick={(e) => e.stopPropagation()}>
            <div className="remote-modal-head">
              <div>
                <h3><Smartphone size={18} /> {t('手机远程控制')}</h3>
                <p>{t('手机接入整个控制台，不是只读镜像；关弹窗不会断开，点停止才结束。')}</p>
              </div>
              <button className="browser-icon-btn" onClick={() => setOpen(false)} title={t('关闭')}>
                <X size={16} />
              </button>
            </div>

            {!adminToken ? (
              <div className="remote-auth-empty">
                <ShieldAlert size={22} />
                <p>{t('需要管理员令牌。先在电脑上把令牌填进设置，再生成远控链接。')}</p>
              </div>
            ) : (
              <div className="remote-grid">
                <div className="remote-qr-col">
                  {connected ? (
                    <div className="remote-connected-card">
                      <Wifi size={30} />
                      <strong>{t('手机已连接')}</strong>
                      <span>{status.clients.map((c) => c.name).join(' / ')}</span>
                      <small>{t('刷新二维码会踢掉当前手机。')}</small>
                    </div>
                  ) : qr ? (
                    <>
                      <img src={qr} alt="remote qr" className="remote-qr" />
                      {left > 0
                        ? <div className="remote-countdown">{t('二维码还有')} {Math.floor(left / 60)}:{String(left % 60).padStart(2, '0')}</div>
                        : <div className="remote-countdown expired">{t('二维码已过期，请刷新')}</div>}
                    </>
                  ) : (
                    <div className="remote-qr-empty">
                      <QrCode size={36} />
                      <span>{waiting ? t('二维码只在生成时显示，刷新可重新生成。') : t('还没有生成连接二维码')}</span>
                    </div>
                  )}
                </div>

                <div className="remote-side">
                  <div className="remote-mode-row">
                    <label>{t('连接方式')}</label>
                    <select value={mode} onChange={(e) => setMode(e.target.value)} disabled={!!busy}>
                      <option value="auto">{t('自动（优先公网隧道）')}</option>
                      <option value="direct">{t('仅直连（局域网 / 自己的域名）')}</option>
                      <option value="tunnel">{t('强制公网隧道')}</option>
                    </select>
                  </div>

                  {url && !connected && (
                    <div className="remote-link-box">
                      <div className="remote-link-label">{t('连接地址')}</div>
                      <code>{url}</code>
                      <div className="remote-link-actions">
                        <button onClick={copy}>{copied ? t('已复制') : t('复制链接')} <Copy size={12} /></button>
                        <button onClick={() => start(true)} disabled={!!busy}>
                          {busy === 'refresh' ? <Loader2 size={12} className="spin" /> : <RefreshCw size={12} />}
                          {t('刷新')}
                        </button>
                      </div>
                    </div>
                  )}

                  {status?.active && (
                    <div className="remote-state-card">
                      <div className="remote-state-row"><span>{t('状态')}</span><strong>{connected ? t('已连接') : t('等待扫码')}</strong></div>
                      {status.clients.map((c) => (
                        <div className="remote-state-row" key={c.name + c.connected_at}>
                          <span>{c.name}</span><em>{c.ip || '—'}</em>
                        </div>
                      ))}
                      {status.base_url && <div className="remote-state-url" title={status.base_url}>{status.base_url}</div>}
                      {status.tunnel && <div className="remote-tunnel-tag">{t('公网隧道 · localhost.run')}</div>}
                    </div>
                  )}

                  {(warning || status?.warning) && (
                    <div className="remote-warning">
                      <ShieldAlert size={13} /> {warning || status.warning}
                    </div>
                  )}
                  {error && <div className="remote-error">{error}</div>}

                  <div className="remote-buttons">
                    {!status?.active || (!qr && !connected) ? (
                      <button className="primary" onClick={() => start(false)} disabled={!!busy}>
                        {busy === 'start' ? <Loader2 size={14} className="spin" /> : <QrCode size={14} />}
                        {busy === 'start' ? t('正在建立隧道…') : t('生成连接二维码')}
                      </button>
                    ) : null}
                    {status?.active && (
                      <button className="danger" onClick={stop} disabled={!!busy}>
                        {busy === 'stop' ? <Loader2 size={14} className="spin" /> : <Square size={13} />}
                        {t('停止远控')}
                      </button>
                    )}
                  </div>

                  <div className="remote-tips">
                    <p>{t('链接就是临时钥匙，别发群、别截图外传。怀疑泄露就点刷新。')}</p>
                    <p>{t('手机端只负责操作；命令、文件、浏览器仍在这台机器上跑。')}</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}

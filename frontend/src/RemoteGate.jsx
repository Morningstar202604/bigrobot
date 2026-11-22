import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, ShieldCheck, Smartphone, AlertTriangle } from 'lucide-react'
import Logo from './components/Logo'
import { useAppStore } from './store/appStore'
import { http } from './lib/queries'

function deviceName() {
  const ua = navigator.userAgent || ''
  if (/iPhone/i.test(ua)) return 'iPhone'
  if (/iPad/i.test(ua)) return 'iPad'
  if (/Android/i.test(ua)) return 'Android 手机'
  if (/Mac/i.test(ua)) return 'Mac'
  if (/Windows/i.test(ua)) return 'Windows'
  return '浏览器'
}

/**
 * 扫码落地页：只做一件事——把 URL fragment 里的一次性配对串换成临时令牌。
 * 配对串不放在 query，避免被服务端日志/Referer 带走；换完立即从地址栏抹掉。
 */
export default function RemoteGate() {
  const setAdminToken = useAppStore((s) => s.setAdminToken)
  const [state, setState] = useState('pairing')
  const [error, setError] = useState('')
  const [hasLocal, setHasLocal] = useState(false)
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true
    const hash = window.location.hash || ''
    const m = hash.match(/(?:^#|&)t=([^&]+)/)
    if (!m) {
      setHasLocal(Boolean(useAppStore.getState().adminToken))
      setState('idle')
      return
    }
    let token = ''
    try { token = decodeURIComponent(m[1]) } catch { token = m[1] }
    // 先去掉地址栏里的钥匙，再发请求；刷新不会重复使用已消费的配对串。
    window.history.replaceState(null, '', '/remote')
    setState('pairing')
    http.post('/api/remote/pair', { token, device_name: deviceName() })
      .then((r) => {
        setAdminToken(r.token || '')
        setState('ok')
        setTimeout(() => window.location.replace('/'), 500)
      })
      .catch((e) => {
        setError(e?.message || '配对失败')
        setState('error')
      })
  }, [setAdminToken])

  return (
    <div className="remote-gate">
      <div className="remote-gate-card">
        <Logo size={40} withText name="BigRobot" subtitle="手机远程控制" />
        {state === 'pairing' && (
          <div className="remote-gate-status">
            <Loader2 size={26} className="spin" />
            <h2>正在配对这台电脑</h2>
            <p>二维码只用于建立一次连接，完成后会换成本机临时令牌。</p>
          </div>
        )}
        {state === 'ok' && (
          <div className="remote-gate-status">
            <ShieldCheck size={30} />
            <h2>配对成功</h2>
            <p>正在打开控制台…</p>
          </div>
        )}
        {state === 'idle' && (
          <div className="remote-gate-status">
            <Smartphone size={30} />
            <h2>这是手机远控入口</h2>
            <p>请回到电脑上的「远程控制」面板，点「生成连接二维码」后重新扫码。</p>
            {hasLocal && <Link className="btn" to="/">本机已登录，直接打开控制台</Link>}
          </div>
        )}
        {state === 'error' && (
          <div className="remote-gate-status">
            <AlertTriangle size={30} />
            <h2>配对没有完成</h2>
            <p>{error}。二维码是一次性的，请回电脑上刷新后重扫。</p>
          </div>
        )}
        <div className="remote-gate-foot">
          <ShieldCheck size={13} />
          链接等同临时钥匙，不要转发给他人。手机只负责操作，程序仍在这台电脑上运行。
        </div>
      </div>
    </div>
  )
}

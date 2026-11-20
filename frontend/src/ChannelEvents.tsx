import { useState } from 'react'
import { Radio, RefreshCw } from 'lucide-react'
import { useChannelEvents, isAuthError } from './lib/queries'
import { Spinner, ErrorBanner } from './components/Spinner'
import { EmptyState, PageHead } from './ui'
import TokenGate from './components/TokenGate'
import './pages2.css'
import { t } from './lib/t'

const TYPES = [
  { key: '', label: t('全部') },
  { key: 'group_recall', label: t('群撤回') },
  { key: 'friend_recall', label: t('私聊撤回') },
  { key: 'group_increase', label: t('入群') },
  { key: 'group_decrease', label: t('退群') },
  { key: 'friend', label: t('好友请求') },
  { key: 'group', label: t('群请求') },
]

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
    })
  } catch {
    return iso
  }
}

const ACTION_TONE: Record<string, string> = {
  deleted: 'ok',
  recorded: 'muted',
  ignored: 'warn',
  error: 'danger',
}

export default function ChannelEvents() {
  const [type, setType] = useState('')
  const q = useChannelEvents(type)

  if (isAuthError(q.error)) return <TokenGate />

  const rows = q.data?.events ?? []

  return (
    <div className="p-4 md:p-6 max-w-[1400px] mx-auto w-full space-y-4 pb-24 md:pb-10">
      <PageHead
        title={t('渠道事件')}
        sub={t('入群、退群、撤回、好友请求只留档；撤回会真正从上下文移除消息')}
        right={
          <>
            {TYPES.map((x) => (
              <button key={x.key} onClick={() => setType(x.key)}
                className={`mod-toggle ${type === x.key ? 'on' : ''}`}>
                {x.label}
              </button>
            ))}
            <button className="btn ghost sm" onClick={() => q.refetch()} title={t('刷新')}>
              <RefreshCw size={13} />
            </button>
          </>
        }
      />

      {q.isLoading && <Spinner full label={t('加载事件…')} />}
      {q.error && !isAuthError(q.error) && (
        <ErrorBanner message={(q.error as Error).message} onRetry={() => q.refetch()} />
      )}

      {!q.isLoading && rows.length === 0 && (
        <EmptyState
          icon={<Radio size={22} />}
          title={t('暂无渠道事件')}
          desc={t('网关收到入群、退群、撤回或好友请求后会出现在这里。')}
        />
      )}

      {rows.length > 0 && (
        <div className="bg-panel border border-line-2 rounded-xl overflow-auto">
          <table className="dt w-full text-sm">
            <thead>
              <tr>
                <th>{t('时间')}</th>
                <th>{t('事件')}</th>
                <th>{t('渠道')}</th>
                <th>{t('群 / 用户')}</th>
                <th>{t('消息')}</th>
                <th>{t('结果')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id}>
                  <td className="whitespace-nowrap text-muted">{fmtTime(e.created_at)}</td>
                  <td><code>{e.kind}/{e.event_type}</code></td>
                  <td>{e.channel_type}{e.self_id ? ` · ${e.self_id}` : ''}</td>
                  <td>{e.group_id || e.channel_user_id || '-'}</td>
                  <td className="font-mono text-xs">{e.message_id || '-'}</td>
                  <td>
                    <span className={`badge ${ACTION_TONE[(e.result.split(':')[0] || '').trim()] || 'muted'}`}>
                      {e.result || '-'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

import { useEffect, useState } from 'react'
import { Search, Trash2, Images, Loader2 } from 'lucide-react'
import { useEmotes, useEmoteDelete, fetchEmoteBlob, isAuthError } from './lib/queries'
import type { EmoteItem } from './lib/queries'
import TokenGate from './components/TokenGate'
import { Spinner, ErrorBanner } from './components/Spinner'
import { EmptyState, PageHead } from './ui'
import { useFeedback } from './components/Feedback'
import { t } from './lib/t'
import './pages2.css'

/** 缩略图：blob URL 按需加载 + 卸载回收。 */
function EmoteThumb({ path }: { path: string }) {
  const [url, setUrl] = useState('')
  useEffect(() => {
    let alive = true
    let made = ''
    fetchEmoteBlob(path).then((u) => {
      if (!alive) { URL.revokeObjectURL(u); return }
      made = u
      setUrl(u)
    }).catch(() => {})
    return () => { alive = false; if (made) URL.revokeObjectURL(made) }
  }, [path])
  if (!url) return <div className="w-full h-full grid place-items-center text-[10px] text-muted">{t('加载中')}</div>
  return <img src={url} alt="" className="w-full h-full object-cover" loading="lazy" />
}

export default function EmoteCenter() {
  const fb = useFeedback()
  const [q, setQ] = useState('')
  const [group, setGroup] = useState('')
  // 121 张之后默认 60 会只显示一半；这里一次取完，靠分组和搜索收窄。
  const emotes = useEmotes(q, 300)
  const del = useEmoteDelete()
  // TS 收窄：早退之后 emotes.error 恒为 falsy，JSX 里再判会变 never。
  // 先解构出来再判。
  const emoteError = emotes.error
  const refetchEmotes = emotes.refetch
  const askDelete = async (it: EmoteItem) => {
    const label = it.summary || it.tags || t('这张表情')
    const ok = await fb.confirm(`删除表情「${label}」？`, { danger: true, confirmText: t('删除') })
    if (!ok) return
    del.mutate(String(it.ts), {
      onSuccess: () => fb.toast.success(t('已删除')),
      onError: (e) => fb.toast.error(`${t('删除失败')}: ${(e as Error).message}`),
    })
  }
  const allItems: EmoteItem[] = emotes.data?.items ?? []
  const groupCounts: Record<string, number> = {}
  for (const it of allItems) groupCounts[it.group] = (groupCounts[it.group] || 0) + 1
  const items = group ? allItems.filter((it) => it.group === group) : allItems

  if (emotes.error && isAuthError(emotes.error)) return <TokenGate error={emotes.error} onAuthed={() => emotes.refetch()} />
  if (emotes.error) return <div className="p-8"><ErrorBanner message={(emotes.error as Error).message} onRetry={() => emotes.refetch()} /></div>

  return (
    <div className="p-4 md:p-6 max-w-[1400px] mx-auto w-full space-y-4 pb-24 md:pb-10">
      <PageHead
        title={t('表情包库')}
        sub={t('机器人在群里自动学习的梗图：聊天时说「发个表情包」就从这里挑')}
        right={
          <>
            <div className="tb-search">
              <Search size={13} />
              <input
                placeholder={t('搜标签 / 摘要')}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                aria-label={t('搜索表情包')}
              />
            </div>
            <span className="badge muted">{group ? `${items.length}/${emotes.data?.total ?? 0}` : (emotes.data?.total ?? '…')}</span>
          </>
        }
      />

      <div className="flex flex-wrap gap-2">
        {[
          ['', '全部', allItems.length],
          ['opensource-tieba', '贴吧', groupCounts['opensource-tieba'] || 0],
          ['opensource-meme', '黑化 / 梗图', groupCounts['opensource-meme'] || 0],
          ['opensource-naiwa', '奶蛙', groupCounts['opensource-naiwa'] || 0],
          ['opensource-noto', 'Noto', groupCounts['opensource-noto'] || 0],
          ['builtin', '内置', groupCounts['builtin'] || 0],
        ].map(([key, label, n]) => (
          <button key={String(key)} className={`btn sm ${group === key ? '' : 'ghost'}`}
            onClick={() => setGroup(String(key))}>
            {t(String(label))} {n}
          </button>
        ))}
      </div>

      {emotes.isLoading && <Spinner full label={t('加载表情包…')} />}
      {emoteError && !isAuthError(emoteError) && (
        <ErrorBanner message={(emoteError as Error).message} onRetry={() => refetchEmotes()} />
      )}
      {!emotes.isLoading && !items.length && (
        <EmptyState icon={<Images size={22} />} title={t('还没有收藏的表情包')} desc={t('群友发的新梗图会被自动收藏到这里。')} />
      )}

      {items.length > 0 && (
        <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))' }}>
          {items.map((it) => (
            <div key={it.ts} className="bg-panel border border-line-2 rounded-xl overflow-hidden group">
              <div className="w-full aspect-square bg-[var(--panel-2)]">
                <EmoteThumb path={it.data} />
              </div>
              <div className="p-2 flex items-center justify-between gap-1">
                <span className="text-xs text-muted truncate" title={it.summary || it.tags || ''}>
                  {it.summary || it.tags || it.kind}
                </span>
                <button className="btn danger-ghost sm opacity-70 md:opacity-0 md:group-hover:opacity-100 transition-opacity"
                  title={t('删除这张')} aria-label={t('删除这张表情')}
                  disabled={del.isPending && del.variables === String(it.ts)}
                  onClick={() => void askDelete(it)}>
                  {del.isPending && del.variables === String(it.ts)
                    ? <Loader2 size={13} className="animate-spin" />
                    : <Trash2 size={13} />}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

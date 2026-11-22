import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { BookOpen, Boxes, Image, Library, MessageSquare, Puzzle, Server, Wrench } from 'lucide-react'
import { http } from './lib/queries'
import { EmptyState, PageHead, StatCard } from './ui'
import { Spinner, ErrorBanner } from './components/Spinner'
import { t } from './lib/t'
import './pages2.css'

type Item = {
  id: string
  name: string
  count: number
  summary: string
  source: string
  license: string
  detail: string
  files?: string[]
}

const ICONS: Record<string, ReactNode> = {
  tools: <Wrench size={18} />,
  images: <Image size={18} />,
  skills: <BookOpen size={18} />,
  emotes: <MessageSquare size={18} />,
  kb: <Library size={18} />,
  plugins: <Puzzle size={18} />,
  mcp: <Server size={18} />,
}

export default function OpenSourceCenter() {
  const [data, setData] = useState<{ items: Item[]; total: number } | null>(null)
  const [error, setError] = useState<Error | null>(null)

  const load = () => {
    setError(null)
    http.get<{ items: Item[]; total: number }>('/api/opensource/catalog')
      .then(setData)
      .catch((e) => setError(e as Error))
  }
  useEffect(load, [])

  return (
    <div className="p-4 md:p-6 max-w-[1400px] mx-auto w-full space-y-5 pb-24 md:pb-10">
      <PageHead
        title={t('开源资源')}
        sub={t('工具、图片、技能、表情、知识库、插件和 MCP 的来源与当前数量')}
        right={<span className="badge muted">{t('共')} {data?.total ?? '…'} {t('项')}</span>}
      />
      {error && <ErrorBanner message={error.message} onRetry={load} />}
      {!data && !error && <Spinner full label={t('清点开源资源…')} />}
      {data && !data.items.length && (
        <EmptyState icon={<Boxes size={22} />} title={t('还没有开源资源')} desc={t('运行 scripts/seed_opensource.py 再刷新。')} />
      )}
      {data && data.items.length > 0 && (
        <>
          <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
            {data.items.map((it) => (
              <StatCard key={it.id} icon={ICONS[it.id] || <Boxes size={18} />} value={it.count} label={it.name} tone={it.count ? 'brand' : 'muted'} />
            ))}
          </div>
          <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}>
            {data.items.map((it) => (
              <div key={it.id} className="card p-4 space-y-2">
                <div className="flex items-center gap-2">
                  {ICONS[it.id] || <Boxes size={16} />}
                  <b className="text-[15px]">{it.name}</b>
                  <span className="badge ok ml-auto">{it.count}</span>
                </div>
                <p className="text-[13px] text-muted">{it.summary}</p>
                <p className="text-[12px] text-muted">{it.detail}</p>
                {it.files && it.files.length > 0 && (
                  <div className="grid gap-1.5" style={{ gridTemplateColumns: 'repeat(6, minmax(0, 1fr))' }}>
                    {it.files.slice(0, 12).map((f) => (
                      <img key={f} src={`/opensource/avatars/${f}`} alt={f} loading="lazy"
                        style={{ width: '100%', aspectRatio: '1', objectFit: 'cover', borderRadius: 8, background: 'var(--panel-2)' }} />
                    ))}
                  </div>
                )}
                <div className="text-[11px] text-muted break-all">
                  <span className="badge muted mr-1">{it.license}</span>
                  {it.source.split(' / ').map((s, i) => (
                    <a key={i} href={s} target="_blank" rel="noreferrer" className="underline mr-2">{s}</a>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

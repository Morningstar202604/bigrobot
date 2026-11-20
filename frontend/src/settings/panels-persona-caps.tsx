import { useEffect, useMemo, useState } from 'react'
import { Save, RotateCcw, Wrench, Wand2, Server, Puzzle, Check } from 'lucide-react'
import { usePersonaCaps, usePersonaCapsMutations } from '../lib/queries'
import type { CapGroup, PersonaCaps, PersonaCapsOption } from '../lib/queries'
import { useFeedback } from '../components/Feedback'
import { Spinner, ErrorBanner } from '../components/Spinner'
import { EmptyState } from '../ui'
import { Grp } from './bits'
import { t as tr } from '../lib/t'

const EMPTY_GROUP: CapGroup = { mode: 'all', ids: [] }

function defaultCaps(): PersonaCaps {
  return {
    tools: { ...EMPTY_GROUP },
    skills: { ...EMPTY_GROUP },
    mcp: { ...EMPTY_GROUP },
    extensions: { ...EMPTY_GROUP },
  }
}

function CapBlock({ title, note, icon, group, options, onChange }: {
  title: string
  note: string
  icon: React.ReactNode
  group: CapGroup
  options: PersonaCapsOption[]
  onChange: (g: CapGroup) => void
}) {
  const allowed = group.mode === 'allow'
  const merged = useMemo(() => {
    const seen = new Set(options.map((o) => o.id))
    const extra: PersonaCapsOption[] = group.ids
      .filter((id) => !seen.has(id))
      .map((id) => ({ id, name: id }))
    return [...options, ...extra]
  }, [options, group.ids])

  const setMode = (mode: 'all' | 'allow') => {
    if (mode === 'all') onChange({ mode: 'all', ids: [] })
    else onChange({ mode: 'allow', ids: group.ids.length ? group.ids : options.map((o) => o.id) })
  }
  const toggle = (id: string) => {
    onChange({ mode: 'allow', ids: group.ids.includes(id)
      ? group.ids.filter((x) => x !== id)
      : [...group.ids, id] })
  }

  return (
    <div className="grp">
      <div className="grp-head">
        <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}>{icon}{title}</h3>
        <span className="gh-note">{note}</span>
      </div>
      <div className="grp-body">
        <div className="mod-row" style={{ marginBottom: 10 }}>
          <button className={`mod-toggle ${!allowed ? 'on' : ''}`} onClick={() => setMode('all')}>
            <Check size={12} /> {tr('继承全部')}
          </button>
          <button className={`mod-toggle ${allowed ? 'on' : ''}`} onClick={() => setMode('allow')}>
            {tr('只允许选中')}
          </button>
        </div>
        {allowed && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 6 }}>
            {merged.map((o) => (
              <label key={o.id} style={{ display: 'flex', gap: 7, alignItems: 'flex-start', padding: '6px 8px', border: '1px solid var(--line)', borderRadius: 8, cursor: 'pointer' }}>
                <input type="checkbox" checked={group.ids.includes(o.id)} onChange={() => toggle(o.id)} style={{ marginTop: 2 }} />
                <span style={{ minWidth: 0 }}>
                  <span style={{ display: 'block', fontWeight: 600 }}>{o.name}</span>
                  <span className="text-xs text-muted" style={{ display: 'block' }}>
                    {o.id}{o.category ? ` · ${o.category}` : ''}{o.error ? ` · ${o.error}` : ''}
                  </span>
                </span>
              </label>
            ))}
            {merged.length === 0 && <span className="text-xs text-muted">{tr('暂无可用项')}</span>}
          </div>
        )}
        {!allowed && <span className="text-xs text-muted">{tr('跟随全局开关，当前角色不额外限制。')}</span>}
      </div>
    </div>
  )
}

export default function PersonaCapsPanel() {
  const { data, isLoading, error, refetch } = usePersonaCaps()
  const m = usePersonaCapsMutations()
  const fb = useFeedback()
  const [selected, setSelected] = useState('')
  const [draft, setDraft] = useState<Record<string, PersonaCaps>>({})

  useEffect(() => {
    if (!data) return
    setDraft(JSON.parse(JSON.stringify(data.items || {})))
    if (!selected) setSelected(
      (data.options.personas.find((p) => p.id === 'zero') || data.options.personas[0])?.id || '',
    )
  }, [data, selected])

  if (isLoading) return <Spinner full label={tr('加载角色能力…')} />
  if (error) return <div className="p-4"><ErrorBanner message={(error as Error).message} onRetry={() => refetch()} /></div>
  if (!data) return null

  const personas = data.options.personas
  const caps = draft[selected] || defaultCaps()
  const configured = !!draft[selected]
  const setGroup = (kind: keyof PersonaCaps, g: CapGroup) => {
    setDraft((prev) => {
      const cur = prev[selected] ?? defaultCaps()
      return { ...prev, [selected]: { ...cur, [kind]: g } }
    })
  }

  const save = () => {
    m.save.mutate(draft, {
      onSuccess: () => fb.toast.success(tr('角色能力已保存')),
      onError: (e) => fb.toast.error((e as Error).message),
    })
  }
  const reset = () => {
    m.remove.mutate(selected, {
      onSuccess: () => {
        setDraft((prev) => { const next = { ...prev }; delete next[selected]; return next })
        fb.toast.success(tr('已恢复为继承全部'))
      },
      onError: (e) => fb.toast.error((e as Error).message),
    })
  }

  if (!personas.length) {
    return <EmptyState icon={<Wrench size={22} />} title={tr('没有可配置的预设角色')} desc={tr('先创建角色预设，再回来限制它的能力范围。')} />
  }

  return (
    <div className="space-y-3">
      <Grp id="persona-caps-pick" title={tr('选择角色')} note={tr('默认继承全部；只有显式配置的角色才会收缩')}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {personas.map((p) => (
            <button key={p.id} className={`btn sm ${selected === p.id ? '' : 'secondary'}`} onClick={() => setSelected(p.id)}>
              {p.name}
              {draft[p.id] && <span className="badge info" style={{ marginLeft: 6 }}>{tr('已限制')}</span>}
            </button>
          ))}
        </div>
        <div className="text-xs text-muted" style={{ marginTop: 8 }}>
          {configured ? tr('这个角色有自己的能力白名单。') : tr('这个角色当前继承全局能力。')}
        </div>
      </Grp>

      <CapBlock title={tr('工具')} icon={<Wrench size={15} />} group={caps.tools}
                options={data.options.tools} onChange={(g) => setGroup('tools', g)}
                note={tr('模型能直接调用的函数；未选中的工具不会出现在提示词里，执行层也会拒绝。')} />
      <CapBlock title={tr('技能')} icon={<Wand2 size={15} />} group={caps.skills}
                options={data.options.skills} onChange={(g) => setGroup('skills', g)}
                note={tr('告诉模型什么时候用哪个工具的说明书；扩展技能也在这里。')} />
      <CapBlock title={tr('MCP 服务')} icon={<Server size={15} />} group={caps.mcp}
                options={data.options.mcp} onChange={(g) => setGroup('mcp', g)}
                note={tr('限制这个角色能挂载的 MCP 服务器；服务器本身的启停仍在能力页管理。')} />
      <CapBlock title={tr('声明式扩展')} icon={<Puzzle size={15} />} group={caps.extensions}
                options={data.options.extensions} onChange={(g) => setGroup('extensions', g)}
                note={tr('限制这个角色能看到的扩展工具与扩展技能。')} />

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button className="btn secondary" onClick={reset} disabled={!configured || m.remove.isPending}>
          <RotateCcw size={14} /> {tr('恢复继承全部')}
        </button>
        <button className="btn" onClick={save} disabled={m.save.isPending}>
          <Save size={14} /> {m.save.isPending ? tr('保存中…') : tr('保存角色能力')}
        </button>
      </div>
      {m.save.isError && <ErrorBanner message={(m.save.error as Error).message} onRetry={save} />}
    </div>
  )
}

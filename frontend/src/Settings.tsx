import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  BookOpen, BarChart3, Brain, Save, Users, Wrench, KeyRound,
  Wand2, MessagesSquare, Cpu } from 'lucide-react'
import { SkillsPanel } from './ProviderCenter'
import {
  useConfig, useUpdateConfig,
  useProfiles, useProfileMutations, useLexicon, useLexiconMutations,
} from './lib/queries'
import { EmptyState } from './ui'
import type { Profile, LexiconEntry } from './lib/queries'
import { useShell } from './components/ResponsiveShell'
import { Spinner, ErrorBanner } from './components/Spinner'
import type { AgentConfig } from './types/api'
import { usePagination } from './lib/pagination'
import { Pager } from './settings/bits'
import { ToolsPanel } from './settings/panels-core'
import ModelWorkbench from './settings/panels-model'
import { KbPanel } from './settings/panels-kb'
import { DataPanel, MemPanel, TokenPanel } from './settings/panels-data'
import { isAuthError } from './lib/queries'
import TokenGate from './components/TokenGate'
import { useFeedback } from './components/Feedback'
import './pages2.css'
import { t as tr } from './lib/t'

const TAB_GROUPS: { group: string; items: { key: string; icon: React.ReactNode; label: string; sub: string }[] }[] = [
  {
    group: '模型与推理',
    items: [
      { key: 'model', icon: <Cpu size={15} />, label: '模型', sub: '厂商 / 本地模型 / 能力参数' },
    ],
  },
  {
    group: '工具与知识',
    items: [
      { key: 'skills', icon: <Wand2 size={15} />, label: '技能', sub: '什么时候用哪个工具' },
      { key: 'tools', icon: <Wrench size={15} />, label: '工具注册表', sub: '可自定义 Agent 能执行的动作' },
      { key: 'profiles', icon: <Users size={15} />, label: '档案', sub: '人物与群：备注/标签，机器人靠它认人' },
      { key: 'lexicon', icon: <MessagesSquare size={15} />, label: '黑话表', sub: '群里的梗与缩写，机器人靠它听懂黑话' },
      { key: 'mem', icon: <Brain size={15} />, label: '长期记忆', sub: '跨会话沉淀' },
    ],
  },
  {
    group: '数据与运维',
    items: [
      { key: 'data', icon: <BarChart3 size={15} />, label: '存储维护', sub: '数据库容量 / 180 天数据清理' },
      { key: 'token', icon: <KeyRound size={15} />, label: '访问令牌', sub: '控制台登录凭据' },
    ],
  },
]
// 平铺视图供 active 查找与页头：必须包含 kb（/settings/kb 是一级导航入口）。
// TAB_GROUPS 只决定侧栏展示，不含 kb —— 双入口去重只发生在侧栏，URL 与内容保留。
const KB_TAB = { key: 'kb', icon: <BookOpen size={15} />, label: '知识库', sub: 'RAG 语料增删改' }
// 一页只回答一个问题：能力（能做什么）/ 策略（什么必须我批）/ 设置（换模型改参数）。
// scope 决定这一页收哪些 tab，避免同一个能力在三个页面各出现一次。
const SCOPE_TABS: Record<string, { groups: string[]; keys: string[]; base: string; fallback: string }> = {
  capabilities: {
    groups: ['工具与知识'],
    keys: ['skills', 'tools', 'profiles', 'lexicon', 'mem', 'kb'],
    base: '/capabilities',
    fallback: 'tools',
  },
  settings: {
    groups: ['模型与推理', '数据与运维'],
    keys: ['model', 'data', 'token'],
    base: '/settings',
    fallback: 'model',
  },
}

export default function Settings({ scope }: { scope?: keyof typeof SCOPE_TABS } = {}) {
  const { tab: routeTab } = useParams()
  const navigate = useNavigate()
  const conf = scope ? SCOPE_TABS[scope] : null
  const groups = conf
    ? TAB_GROUPS.map((g) => ({ ...g, items: g.items.filter((i) => conf.keys.includes(i.key)) }))
        .filter((g) => g.items.length)
    : TAB_GROUPS
  const tabs = [
    ...groups.flatMap((g) => g.items),
    ...(conf && !conf.keys.includes('kb') ? [] : [KB_TAB]),
  ]
  const routeOk = tabs.some((t) => t.key === routeTab)
  const tab = routeOk ? (routeTab as string) : (conf?.fallback ?? 'params')
  const base = conf?.base ?? '/settings'
  const setTab = (k: string) => navigate(`${base}/${k}`)
  const { mobile } = useShell()
  const { data: cfgRes, isLoading, error, refetch } = useConfig()
  const cfg = cfgRes?.config
  const upd = useUpdateConfig()
  // 配置草稿：所有控件只改本地状态，点「保存配置」才落库。
  // 之前每个 onChange 都 PUT 整包，滑杆拖动=请求风暴，响应乱序还会覆盖新值。
  const [draft, setDraft] = useState<AgentConfig | null>(null)
  useEffect(() => {
    setDraft(cfgRes?.config ?? null)
  }, [cfgRes])
  const shown = draft ?? cfg

  if (isLoading) return <Spinner full label={tr('加载配置…')} />
  // 401/403/503 都以令牌门禁承接：以前这里渲染 ErrorBanner，用户无法就地登录
  if (error && isAuthError(error)) return <TokenGate error={error} onAuthed={() => refetch()} />
  if (error) return <div className="p-8"><ErrorBanner message={(error as Error).message} onRetry={() => refetch()} /></div>
  if (!cfg) return <TokenGate onAuthed={() => refetch()} />

  const active = tabs.find((t) => t.key === tab)!
  // scope 页面本身就是一级入口：侧栏再叫「管理中心」会和「设置」混淆，
  // 改成对应子项名，明确它只是当前页的二级导航。
  const sideTitle = scope === 'capabilities' ? tr('能力子项') : tr('管理中心')
  const sideSub = scope === 'capabilities' ? tr('工具、知识与记忆') : tr('Agent 运行时配置 · 即时生效')

  return (
    <div className={`set-app ${mobile ? 'set-app-mobile' : ''}`}>
      <aside className="set-side">
        <div className="ss-title">{sideTitle}</div>
        <div className="ss-sub">{sideSub}</div>
        {groups.map((g) => (
          <div key={g.group} className="set-group">
            <div className="set-group-label">{tr(g.group)}</div>
            {g.items.map((item) => (
              <button key={item.key} className={`set-item ${tab === item.key ? 'on' : ''}`} onClick={() => setTab(item.key)}>
                <span className="si-ico">{item.icon}</span>
                <span>{tr(item.label)}</span>
              </button>
            ))}
          </div>
        ))}
      </aside>

      <main className="set-main">
        <div className="set-main-head">
          <div>
            <h1>{tr(active.label)}</h1>
            <p>{tr(active.sub)}</p>
          </div>
          {tab === 'model' && (
            <button className="btn" onClick={() => shown && upd.mutate(shown)}
                    disabled={upd.isPending || !shown}>
              <Save size={14} />
              {upd.isPending ? '保存中…' : upd.isSuccess ? '已保存' : '保存配置'}
            </button>
          )}
        </div>

        {tab === 'model' && upd.isError && (
          <div className="mb-3">
            <ErrorBanner message={(upd.error as Error).message} onRetry={() => upd.mutate(shown!)} />
          </div>
        )}
        {tab === 'model' && shown && (
          <ModelWorkbench
            cfg={shown}
            setDraft={setDraft}
            upd={upd}
            onLocalActivated={() => void refetch()}
          />
        )}
        {tab === 'skills' && <SkillsPanel />}
        {tab === 'tools' && <ToolsPanel />}
        {tab === 'kb' && <KbPanel />}
        {tab === 'data' && <DataPanel />}
        {tab === 'mem' && <MemPanel />}
        {tab === 'profiles' && <ProfilesPanel />}
        {tab === 'lexicon' && <LexiconPanel />}
        {tab === 'token' && <TokenPanel />}
      </main>
    </div>
  )
}

/* ============ 参数配置（补齐 char_budget/react_steps/top_p + 引擎模式） ============ */
function ProfilesPanel() {
  const { data, isLoading } = useProfiles()
  const { save } = useProfileMutations()
  const fb = useFeedback()
  const items: Profile[] = data?.profiles ?? []
  const pg = usePagination(items)
  const [editing, setEditing] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [alias, setAlias] = useState('')

  if (isLoading) return <Spinner full label={tr('加载档案…')} />
  if (!items.length) return <EmptyState icon={<Users size={22} />} title={tr('还没有档案')} desc={tr('群里有人说话后自动建档；也可以手动添加备注。')} />

  const startEdit = (p: Profile) => {
    setEditing(p.key); setNote(p.note || ''); setAlias(p.alias || '')
  }
  const commit = (key: string) => {
    save.mutate({ key, note, alias }, {
      onSuccess: () => { setEditing(null); fb.toast.success(tr('档案已保存')) },
      onError: (e) => fb.toast.error(`${tr('保存失败')}: ${(e as Error).message}`),
    })
  }

  return (
    <>
      <div className="tbl-wrap">
        <table className="dt">
          <thead><tr><th>{tr('标识')}</th><th>{tr('类型')}</th><th>{tr('昵称')}</th><th>{tr('别名')}</th><th>{tr('互动')}</th><th>{tr('备注')}</th><th></th></tr></thead>
          <tbody>
            {pg.pageItems.map((p) => (
              <tr key={p.key}>
                <td className="raw" title={p.key}>{p.key}</td>
                <td><span className="badge">{p.kind}</span></td>
                <td>{p.display_name || '—'}</td>
                <td>
                  {editing === p.key
                    ? <input value={alias} onChange={(e) => setAlias(e.target.value)} style={{ width: 100 }} />
                    : (p.alias || '—')}
                </td>
                <td>{Object.values(p.stats || {}).reduce((a: number, b) => a + Number(b || 0), 0)}</td>
                <td>
                  {editing === p.key
                    ? <input value={note} onChange={(e) => setNote(e.target.value)} style={{ width: 160 }} />
                    : <span className="raw" title={p.note}>{p.note || '—'}</span>}
                </td>
                <td>
                  {editing === p.key
                    ? <>
                        <button className="btn sm" onClick={() => commit(p.key)} disabled={save.isPending}>{tr('存')}</button>
                        <button className="btn ghost sm" onClick={() => setEditing(null)}>{tr('取消')}</button>
                      </>
                    : <button className="btn ghost sm" onClick={() => startEdit(p)}>{tr('编辑')}</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pg.hasPages && <Pager page={pg.page} maxPage={pg.maxPage} total={pg.total} onChange={pg.setPage} label={tr('档案')} />}
    </>
  )
}

/* ============ 黑话表：后端 /api/lexicon ============ */
function LexiconPanel() {
  const { data, isLoading } = useLexicon()
  const { add } = useLexiconMutations()
  const fb = useFeedback()
  const items: LexiconEntry[] = data?.entries ?? []
  const pg = usePagination(items)
  const [term, setTerm] = useState('')
  const [meaning, setMeaning] = useState('')

  const submit = () => {
    if (!term.trim()) return
    add.mutate({ scope: 'global', term: term.trim(), meaning: meaning.trim() }, {
      onSuccess: () => { setTerm(''); setMeaning(''); fb.toast.success(tr('黑话已记录')) },
      onError: (e) => fb.toast.error(`${tr('保存失败')}: ${(e as Error).message}`),
    })
  }

  return (
    <>
      <div className="f-row" style={{ marginBottom: 10 }}>
        <span className="f-lb">{tr('新增')}</span>
        <div className="flex items-center gap-2 flex-wrap">
          <input value={term} onChange={(e) => setTerm(e.target.value)} placeholder={tr('黑话，如：绝绝子')} maxLength={40} style={{ width: 160 }} />
          <input value={meaning} onChange={(e) => setMeaning(e.target.value)} placeholder={tr('释义')} maxLength={120} style={{ width: 220 }} />
          <button className="btn sm" onClick={submit} disabled={!term.trim() || add.isPending}>{add.isPending ? tr('保存中…') : tr('添加')}</button>
        </div>
      </div>
      {isLoading ? <Spinner full label={tr('加载黑话表…')} /> : !items.length ? (
        <EmptyState icon={<MessagesSquare size={22} />} title={tr('黑话表还是空的')} desc={tr('群里出现的黑话会自动沉淀到这里待补充；也可以手动添加。')} />
      ) : (
        <>
          <div className="tbl-wrap">
            <table className="dt">
              <thead><tr><th>{tr('黑话')}</th><th>{tr('释义')}</th><th>{tr('出现次数')}</th><th>{tr('更新时间')}</th></tr></thead>
              <tbody>
                {pg.pageItems.map((e: LexiconEntry) => (
                  <tr key={e.id}>
                    <td><b>{e.term}</b></td>
                    <td className="raw">{e.meaning || tr('（待补充）')}</td>
                    <td>{e.hits}</td>
                    <td>{(e.updated_at || '').slice(0, 16).replace('T', ' ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pg.hasPages && <Pager page={pg.page} maxPage={pg.maxPage} total={pg.total} onChange={pg.setPage} label={tr('黑话表')} />}
        </>
      )}
    </>
  )
}


/* ============ 访问令牌（本机自动获取 + 可视化复制） ============ */

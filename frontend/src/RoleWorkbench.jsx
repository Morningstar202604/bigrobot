import { useSearchParams } from 'react-router-dom'
import BotPersona from './BotPersona'
import CardsPanel from './CardsPanel'
import PersonaCapsPanel from './settings/panels-persona-caps'
import { t } from './lib/t'

/**
 * 角色工作台：同一个“角色”对象的三个层面。
 * 人设=文案与预设，角色卡=卡库/绑定，角色能力=工具/技能/MCP/扩展授权。
 * 不再在能力页的侧栏里各放一个入口，避免三个地方来回找。
 */
const TABS = [
  { key: 'persona', label: '人设', render: () => <BotPersona /> },
  { key: 'cards', label: '角色卡', render: () => <CardsPanel /> },
  { key: 'caps', label: '角色能力', render: () => <PersonaCapsPanel /> },
]

export default function RoleWorkbench() {
  const [params, setParams] = useSearchParams()
  const role = params.get('role') || 'persona'
  const active = TABS.find((x) => x.key === role) || TABS[0]

  const choose = (key) => {
    const next = new URLSearchParams(params)
    if (key === 'persona') next.delete('role')
    else next.set('role', key)
    setParams(next, { replace: true })
  }

  return (
    <div className="role-workbench">
      <div
        role="tablist"
        aria-label={t('角色工作台')}
        style={{ display: 'flex', gap: 6, flexWrap: 'wrap', padding: '0 20px 8px' }}
      >
        {TABS.map((x) => (
          <button
            key={x.key}
            role="tab"
            aria-selected={x.key === active.key}
            className={`console-tab ${x.key === active.key ? 'on' : ''}`}
            onClick={() => choose(x.key)}
          >
            {t(x.label)}
          </button>
        ))}
      </div>
      <div>{active.render()}</div>
    </div>
  )
}

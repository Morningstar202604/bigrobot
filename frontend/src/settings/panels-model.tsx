import { useSearchParams } from 'react-router-dom'
import { ProviderPanel } from '../ProviderCenter'
import { LocalModelsPanel } from '../LocalModels'
import { ParamsPanel } from './panels-core'
import { useUpdateConfig } from '../lib/queries'
import type { AgentConfig } from '../types/api'
import { t } from '../lib/t'

/**
 * 模型工作台：一个“模型”对象的三个层面。
 * 厂商=接口/Key/模型检测，本地=本机权重，能力参数=采样/检索/上下文。
 * 以前三块在设置侧栏各占一个入口，换模型要来回找。
 */
const TABS = [
  { key: 'providers', label: '模型厂商' },
  { key: 'local', label: '本地模型' },
  { key: 'params', label: '能力参数' },
]

export default function ModelWorkbench({
  cfg,
  setDraft,
  upd,
  onLocalActivated,
}: {
  cfg: AgentConfig
  setDraft: React.Dispatch<React.SetStateAction<AgentConfig | null>>
  upd: ReturnType<typeof useUpdateConfig>
  onLocalActivated: () => void
}) {
  const [params, setParams] = useSearchParams()
  const sub = params.get('model') || 'providers'
  const active = TABS.find((x) => x.key === sub) || TABS[0]

  const choose = (key: string) => {
    const next = new URLSearchParams(params)
    if (key === 'providers') next.delete('model')
    else next.set('model', key)
    setParams(next, { replace: true })
  }

  return (
    <div className="model-workbench">
      <div
        role="tablist"
        aria-label={t('模型工作台')}
        style={{ display: 'flex', gap: 6, flexWrap: 'wrap', padding: '0 0 12px' }}
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

      {active.key === 'providers' && (
        <ProviderPanel
          cfg={cfg}
          setCfg={(next) => setDraft(next)}
          persist={(next) => upd.mutate(next)}
        />
      )}
      {active.key === 'local' && <LocalModelsPanel onActivated={onLocalActivated} />}
      {active.key === 'params' && (
        <ParamsPanel cfg={cfg} setDraft={setDraft} upd={upd} />
      )}
    </div>
  )
}

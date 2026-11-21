import { useSearchParams } from 'react-router-dom'
import { t as tr } from '../lib/t'

/**
 * 一个页内若干「视图」的最小壳：URL 用 ?view= 记住当前位置。
 *
 * 为什么不用二级路由：7 个一级入口是硬约束（见计划 §5），
 * 二级页面会让导航重新长出树来；用 query 参数既能直达、又不会多一层层级。
 */
export default function ConsoleTabs({ tabs, title, sub }) {
  const [params, setParams] = useSearchParams()
  const requested = params.get('view')
  // 兼容旧二级页的 view 名；新标签只保留一个规范 key，避免同一面板两个 URL。
  const current = tabs.find((x) => x.key === requested || (x.aliases || []).includes(requested)) || tabs[0]

  if (tabs.length === 1) {
    return <>{current.render()}</>
  }

  return (
    <div className="console-tabs">
      <div className="console-tabs-head">
        <div>
          <h1>{tr(title)}</h1>
          {sub ? <p className="text-sm text-muted">{tr(sub)}</p> : null}
        </div>
        <div className="console-tabbar" role="tablist">
          {tabs.map((x) => (
            <button
              key={x.key}
              role="tab"
              aria-selected={x.key === current.key}
              className={`console-tab ${x.key === current.key ? 'on' : ''}`}
              onClick={() => setParams(x.key === tabs[0].key ? {} : { view: x.key })}
            >
              {x.label ? tr(x.label) : null}
            </button>
          ))}
        </div>
      </div>
      <div className="console-tabs-body">{current.render()}</div>
    </div>
  )
}

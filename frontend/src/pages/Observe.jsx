import ConsoleTabs from '../components/ConsoleTabs'
import AgentRuns from '../AgentRuns'
import LogsCenter from '../LogsCenter'
import ChannelEvents from '../ChannelEvents'
import { t } from '../lib/t'

/** 观测：刚才发生了什么、慢在哪、谁改的。 */
export default function Observe() {
  return (
    <ConsoleTabs
      title={t('观测')}
      sub={t('任务轨迹、运行日志与审计')}
      tabs={[
        { key: 'runs', label: 'Agent 任务', render: () => <AgentRuns /> },
        { key: 'logs', label: '日志与审计', render: () => <LogsCenter /> },
        { key: 'events', label: '渠道事件', render: () => <ChannelEvents /> },
      ]}
    />
  )
}

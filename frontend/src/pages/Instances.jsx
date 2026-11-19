import ConsoleTabs from '../components/ConsoleTabs'
import Dashboard from '../Dashboard'
import QQScanPage from '../QQScanPage'
import { t } from '../lib/t'

/** 实例：机器人活着吗、连上没有、跑在哪个账号上。 */
export default function Instances() {
  return (
    <ConsoleTabs
      title={t('实例')}
      sub={t('引擎、账号与接入状态')}
      tabs={[
        { key: 'overview', label: '运行总览', render: () => <Dashboard /> },
        { key: 'scan', label: '扫码接入', render: () => <QQScanPage /> },
      ]}
    />
  )
}

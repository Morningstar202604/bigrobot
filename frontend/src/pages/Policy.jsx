import ConsoleTabs from '../components/ConsoleTabs'
import ActionsCenter from '../ActionsCenter'
import Settings from '../Settings'
import { t } from '../lib/t'

/** 策略：什么能自动做、什么必须我批——审批队列放第一位，别再藏到二级页。 */
export default function Policy() {
  return (
    <ConsoleTabs
      title={t('策略')}
      sub={t('权限、护栏与待批动作')}
      tabs={[
        { key: 'approvals', label: '待批与动作', render: () => <ActionsCenter /> },
        { key: 'rules', label: '权限与规则', render: () => <Settings scope="policy" /> },
      ]}
    />
  )
}

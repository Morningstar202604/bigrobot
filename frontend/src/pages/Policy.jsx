import ConsoleTabs from '../components/ConsoleTabs'
import ActionsCenter from '../ActionsCenter'
import { PermissionsPanel, HooksPanel } from '../ProviderCenter'
import { GuardrailPanel } from '../settings/panels-core'
import { InjPanel } from '../settings/panels-data'
import { t } from '../lib/t'

/**
 * 策略：待批动作、权限、护栏、钩子、注入日志平铺成一层。
 * 以前「权限与规则」还要再进一次二级侧栏，和「设置」互相抢“管理中心”的语义。
 */
export default function Policy() {
  return (
    <ConsoleTabs
      title={t('策略')}
      sub={t('什么能自动做、什么必须我批、什么必须被记录')}
      tabs={[
        { key: 'approvals', label: '待批与动作', render: () => <ActionsCenter /> },
        { key: 'permission', label: '权限', aliases: ['rules'], render: () => <PermissionsPanel /> },
        { key: 'guardrail', label: '注入规则', render: () => <GuardrailPanel /> },
        { key: 'hooks', label: '钩子', render: () => <HooksPanel /> },
        { key: 'inj', label: '注入日志', render: () => <InjPanel /> },
      ]}
    />
  )
}

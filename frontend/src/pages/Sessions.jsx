import ConsoleTabs from '../components/ConsoleTabs'
import OperatorDesk from '../OperatorDesk'
import SessionsCenter from '../SessionsCenter'
import AnnotationCenter from '../AnnotationCenter'
import { t } from '../lib/t'

/** 会话：默认进入列表+详情双栏工作台；历史档案保留群资料与导出工具；标注单独一页。 */
export default function Sessions() {
  return (
    <ConsoleTabs
      title={t('会话')}
      sub={t('列表、接管、回复与标注都在同一个会话对象上')}
      tabs={[
        { key: 'workbench', label: '会话工作台', render: () => <OperatorDesk /> },
        { key: 'archive', label: '历史档案', render: () => <SessionsCenter /> },
        { key: 'annotate', label: '标注', render: () => <AnnotationCenter /> },
      ]}
    />
  )
}

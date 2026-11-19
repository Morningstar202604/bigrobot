import ConsoleTabs from '../components/ConsoleTabs'
import SessionsCenter from '../SessionsCenter'
import OperatorDesk from '../OperatorDesk'
import AnnotationCenter from '../AnnotationCenter'
import { t } from '../lib/t'

/** 会话：看对话、接管、标注，三件事同一个对象（一次会话），不该分三个入口。 */
export default function Sessions() {
  return (
    <ConsoleTabs
      title={t('会话')}
      sub={t('对话记录、人工接管与回复标注')}
      tabs={[
        { key: 'list', label: '会话列表', render: () => <SessionsCenter /> },
        { key: 'desk', label: '协作台', render: () => <OperatorDesk /> },
        { key: 'annotate', label: '标注', render: () => <AnnotationCenter /> },
      ]}
    />
  )
}

import ConsoleTabs from '../components/ConsoleTabs'
import Settings from '../Settings'
import EmoteCenter from '../EmoteCenter'
import ExtensionsCenter from '../ExtensionsCenter'
import RoleWorkbench from '../RoleWorkbench'
import OpenSourceCenter from '../OpenSourceCenter'
import { t } from '../lib/t'

/** 能力：工具与知识、角色工作台、表情包、扩展。角色不再散落在三个入口。 */
export default function Capabilities() {
  return (
    <ConsoleTabs
      title={t('能力')}
      sub={t('工具与知识、角色、素材与扩展')}
      tabs={[
        { key: 'registry', label: '工具与知识', render: () => <Settings scope="capabilities" /> },
        { key: 'persona', label: '角色', render: () => <RoleWorkbench /> },
        { key: 'emotes', label: '表情包', render: () => <EmoteCenter /> },
        { key: 'extensions', label: '扩展', render: () => <ExtensionsCenter /> },
        { key: 'opensource', label: '开源资源', render: () => <OpenSourceCenter /> },
      ]}
    />
  )
}

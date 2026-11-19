import ConsoleTabs from '../components/ConsoleTabs'
import Settings from '../Settings'
import EmoteCenter from '../EmoteCenter'
import BotPersona from '../BotPersona'
import { t } from '../lib/t'

/** 能力：它能做什么（工具/技能/角色/档案/黑话/知识库）+ 表情包素材。 */
export default function Capabilities() {
  return (
    <ConsoleTabs
      title={t('能力')}
      sub={t('它能做什么、认识谁、懂哪些词')}
      tabs={[
        { key: 'registry', label: '能力与知识', render: () => <Settings scope="capabilities" /> },
        { key: 'persona', label: '人设', render: () => <BotPersona /> },
        { key: 'emotes', label: '表情包', render: () => <EmoteCenter /> },
      ]}
    />
  )
}

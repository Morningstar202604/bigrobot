import { Activity, BookOpen, FileText, Inbox, MessageSquare, ShieldAlert, Users } from 'lucide-react'
import { StatCard } from '../ui'

/** 总览指标卡：Dashboard 与「设置 · 数据」共用同一份，标签也必须一致。
 *  之前两处各写一遍，同一指标一个叫「总会话」一个叫「会话」，已统一。 */
export interface OverviewLike {
  sessions: number
  messages: number
  tickets: number
  pending: number
  kb_count: number
  injection: number
  feedback: { total: number; help_rate: number }
}

export default function OverviewStats({ ov, t }: { ov: OverviewLike; t: (s: string) => string }) {
  const rate = Math.round((ov.feedback?.help_rate ?? 0) * 100)
  return (
    <div className="stat-grid">
      <StatCard icon={<Inbox size={18} />} value={ov.sessions} label={t('会话')} tone="brand" />
      <StatCard icon={<MessageSquare size={18} />} value={ov.messages} label={t('消息')} tone="ok" />
      <StatCard icon={<FileText size={18} />} value={ov.tickets} label={t('工单')} tone="warn" />
      <StatCard icon={<Users size={18} />} value={ov.pending} label={t('待接管')} tone="danger" />
      <StatCard icon={<BookOpen size={18} />} value={ov.kb_count} label={t('知识库')} tone="brand" />
      <StatCard icon={<ShieldAlert size={18} />} value={ov.injection} label={t('注入拦截')} tone="danger" />
      <StatCard icon={<Activity size={18} />} value={`${rate}%`} label={t('好评率')} tone="ok" />
    </div>
  )
}

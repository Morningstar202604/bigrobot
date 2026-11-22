import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, Check, Cpu, Download, HardDrive, Loader2, Play,
  RefreshCw, Square, Trash2,
} from 'lucide-react'
import { useState } from 'react'
import { http } from './lib/queries'
import { useFeedback } from './components/Feedback'
import { qk } from './lib/queryClient'
import { t } from './lib/t'

/* 本地小模型：目录、下载、安装、启用。全部走本地磁盘与 llama.cpp，
   不把模型权重经云端转发，也不要求用户先去 HuggingFace 手动找文件。 */

export interface LocalModel {
  id: string
  name: string
  params_b: number
  quant: string
  context: number
  license: string
  tool_calling: boolean
  chinese: boolean
  test_only: boolean
  min_ram_gb: number
  fit: { state: 'ok' | 'no' | 'test' | string; label: string }
  released?: string
  badge: string
  tagline: string
  why: string
  best_for: string[]
  ram_gb: number
  repo: string
  file: string
  size: number
  default_ctx: number
  installed: boolean
  bytes: number
  size_label: string
  bytes_label: string
  active: boolean
  download_url: string
}

export interface LocalJob {
  job_id: string
  model_id: string
  status: string
  bytes: number
  total: number
  percent: number
  speed_bps: number
  eta_s: number
  error: string
  path: string
}

interface LocalOverview {
  models: LocalModel[]
  system: { os: string; arch: string; cpu: string; cpu_cores: number; ram_gb: number; gpu: string; vram_gb: number; unified_memory: boolean }
  server: { running?: boolean; model_id?: string; base_url?: string; n_ctx?: number; pid?: number }
  active_model_id: string
  jobs: LocalJob[]
  disk: { free: number; total: number; free_label: string }
  root: string
  llama_available: boolean
  install_hint: string
}

function fmtContext(n: number): string {
  if (n >= 1000) return `${Math.round(n / 1000)}K`
  return String(n)
}

function fmtSpeed(n: number): string {
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB/s`
  if (n >= 1024) return `${Math.round(n / 1024)} KB/s`
  return `${Math.round(n)} B/s`
}

function fmtEta(n: number): string {
  if (!n || n < 0) return ''
  if (n >= 60) return `${Math.floor(n / 60)} 分 ${n % 60} 秒`
  return `${n} 秒`
}

export function LocalModelsPanel({ onActivated }: { onActivated?: () => void }) {
  const qc = useQueryClient()
  const fb = useFeedback()
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['local-models'],
    queryFn: () => http.get<LocalOverview>('/api/local-models'),
    refetchInterval: 2500,
  })
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['local-models'] })
    qc.invalidateQueries({ queryKey: qk.config })
  }

  const download = useMutation({
    mutationFn: (id: string) => http.post<LocalJob>('/api/local-models/download', { model_id: id }),
    onSuccess: () => { setErr(''); setMsg('已加入下载队列'); invalidate() },
    onError: (e) => setErr((e as Error).message),
  })
  const cancel = useMutation({
    mutationFn: (jobId: string) => http.post<LocalJob>(`/api/local-models/jobs/${jobId}/cancel`),
    onSuccess: invalidate,
    onError: (e) => setErr((e as Error).message),
  })
  const activate = useMutation({
    mutationFn: (m: LocalModel) => http.post<{ ok: boolean; server: Record<string, unknown> }>(
      '/api/local-models/activate', { model_id: m.id, n_ctx: m.default_ctx },
    ),
    onSuccess: (r) => {
      setErr('')
      setMsg(`已启用 ${String(r.server?.model_id || '')}，本地服务在 ${String(r.server?.base_url || '')}`)
      invalidate()
      onActivated?.()
    },
    onError: (e) => setErr((e as Error).message),
  })
  const stop = useMutation({
    mutationFn: () => http.post<{ running: boolean }>('/api/local-models/stop'),
    onSuccess: () => { setMsg('本地模型已停止'); invalidate() },
    onError: (e) => setErr((e as Error).message),
  })
  const remove = useMutation({
    mutationFn: (id: string) => http.del<{ ok: boolean }>(`/api/local-models/${id}`),
    onSuccess: () => { setMsg('模型文件已删除'); invalidate() },
    onError: (e) => setErr((e as Error).message),
  })
  const askRemove = async (m: LocalModel) => {
    const ok = await fb.confirm(`删除模型文件「${m.name}」？已下载的权重会从本机磁盘移除。`, {
      danger: true, confirmText: '删除文件',
    })
    if (ok) remove.mutate(m.id)
  }

  const busy = download.isPending || activate.isPending || stop.isPending || remove.isPending

  if (isLoading) return <div className="p-4 text-sm text-muted"><Loader2 size={14} className="animate-spin" /> 读取本地模型…</div>
  if (error) return <div className="p-4 text-sm" style={{ color: 'var(--danger)' }}>{(error as Error).message}</div>
  if (!data) return null

  const production = data.models.filter((m) => !m.test_only)
  const tests = data.models.filter((m) => m.test_only)

  const renderCard = (m: LocalModel) => {
    const job = data.jobs.find((j) => j.model_id === m.id)
    const running = m.active
    const fitState = m.fit?.state || 'ok'
    const fitLabel = m.fit?.label || ''
    const isDownloading = Boolean(job && ['queued', 'downloading', 'verifying', 'cancelling'].includes(job.status))
    const tooBig = fitState === 'no'
    return (
      <article key={m.id} className={`lm-card ${tooBig ? 'disabled' : ''}`}>
        <div className="lm-card-top">
          <div>
            <div className="lm-title">
              {m.name}
              <span className={`badge ${m.test_only ? 'muted' : 'info'}`}>{m.badge}</span>
            </div>
            <div className="lm-sub">{m.params_b}B · {m.quant} · {fmtContext(m.context)} ctx · {m.license}{m.released ? ` · ${m.released} 发布` : ''} · 建议 ≥{m.ram_gb}GB 内存</div>
          </div>
          {running
            ? <span className="badge ok">使用中</span>
            : m.installed
              ? <span className="badge muted">已安装</span>
              : <span className="badge muted">{m.size_label}</span>}
        </div>

        <p className="lm-tagline">{m.tagline}</p>
        <p className="lm-why">{m.why}</p>

        <div className="lm-tags">
          {m.best_for.map((x) => <span key={x} className="badge muted">{x}</span>)}
          {m.tool_calling && <span className="badge ok">工具调用</span>}
          {m.chinese && <span className="badge muted">中文</span>}
          {fitLabel && <span className={`badge ${tooBig ? 'warn' : m.test_only ? 'muted' : 'ok'}`}>{fitLabel}</span>}
        </div>

        <div className="lm-foot">
          {isDownloading && job ? (
            <div className="lm-progress">
              <div className="lm-progress-line">
                <span>{job.status === 'verifying' ? '校验文件…' : `${job.percent}% · ${fmtSpeed(job.speed_bps)}${job.eta_s ? ` · 剩 ${fmtEta(job.eta_s)}` : ''}`}</span>
                <button className="btn ghost sm" onClick={() => cancel.mutate(job.job_id)}
                  disabled={cancel.isPending && cancel.variables === job.job_id}>
                  {cancel.isPending && cancel.variables === job.job_id
                    ? <><Loader2 size={12} className="animate-spin" /> 取消中…</>
                    : '取消'}
                </button>
              </div>
              <div className="lm-progress-track"><div style={{ width: `${job.percent}%` }} /></div>
            </div>
          ) : !m.installed ? (
            <button className="btn sm" onClick={() => download.mutate(m.id)}
              disabled={busy || tooBig}
              title={tooBig ? fitLabel : ''}>
              {download.isPending && download.variables === m.id
                ? <Loader2 size={13} className="animate-spin" />
                : <Download size={13} />}
              {download.isPending && download.variables === m.id ? ' 加入队列…'
                : tooBig ? ' 内存不足' : ` 下载 ${m.size_label}`}
            </button>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              {!running && (
                <button className="btn sm" onClick={() => activate.mutate(m)} disabled={busy || !data.llama_available || tooBig} title={tooBig ? fitLabel : ''}>
                  {activate.isPending ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} 启用
                </button>
              )}
              {running && (
                <button className="btn secondary sm" onClick={() => stop.mutate()} disabled={busy}>
                  {stop.isPending ? <Loader2 size={13} className="animate-spin" /> : <Square size={13} />}
                  {stop.isPending ? ' 停止中…' : ' 停止'}
                </button>
              )}
              <button className="btn danger-ghost sm" onClick={() => void askRemove(m)}
                disabled={busy || running}
                aria-label="删除模型文件" title="删除模型文件">
                {remove.isPending && remove.variables === m.id
                  ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
              </button>
            </div>
          )}
          <span className="text-xs text-muted">{m.installed ? m.bytes_label : ''}</span>
        </div>
      </article>
    )
  }

  return (
    <section className="bp-sec lm-panel">
      <div className="bp-sec-head">
        <h2><Cpu size={15} /> {t('本地模型')}</h2>
        <span>{t('模型由你自己选；程序只检测本机是否能跑，1B 以下归入测试区')}</span>
      </div>

      <div className="lm-bar">
        <span className="badge muted">
          <Cpu size={12} /> {data.system.cpu_cores} 核 · {data.system.ram_gb}GB 内存
          {data.system.gpu ? ` · ${data.system.gpu}` : ' · 无独显'}
        </span>
        <span className="badge muted"><HardDrive size={12} /> 剩余 {data.disk.free_label}</span>
        <code className="text-xs text-muted">{data.root}</code>
        <button className="btn ghost sm" onClick={() => void refetch()} disabled={isFetching}>
          <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} /> 刷新
        </button>
      </div>

      <div className="lm-note">
        <Cpu size={14} />
        <span>
          本机 {data.system.cpu_cores} 核 / {data.system.ram_gb}GB 内存 / {data.system.gpu || '无独显'}。
          下面只标「可运行 / 内存不足」，不替你选模型；想用哪个就下载哪个。
        </span>
      </div>
      {!data.llama_available && (
        <div className="lm-note warn">
          <AlertTriangle size={14} />
          <span>未安装 llama-cpp-python。先执行 <code>{data.install_hint}</code>，再点启用。</span>
        </div>
      )}
      {data.server?.running && (
        <div className="lm-note ok">
          <Check size={14} />
          <span>运行中：{data.server.model_id} · {data.server.base_url} · {fmtContext(data.server.n_ctx || 0)} ctx</span>
          <button className="btn secondary sm" onClick={() => stop.mutate()} disabled={busy}>
            <Square size={12} /> 停止
          </button>
        </div>
      )}
      {(msg || err) && (
        <div className={`lm-note ${err ? 'danger' : 'ok'}`}>
          {err ? <AlertTriangle size={14} /> : <Check size={14} />}
          <span>{err || msg}</span>
        </div>
      )}

      <div className="lm-grid">
        {production.map(renderCard)}
      </div>

      {tests.length > 0 && (
        <>
          <div className="lm-subhead">
            <h3>测试 / 低配模型</h3>
            <span className="text-xs text-muted">只用于工具链路、低配体验和回归测试，不进入可选目录。</span>
          </div>
          <div className="lm-grid">
            {tests.map(renderCard)}
          </div>
        </>
      )}

      <div className="lm-hint">
        程序只按本机内存标出「可运行 / 内存不足」，不自动替你选：4GB 可选 2B，8GB 可选 4B，16GB 可选 9B。
        当前默认 8K 运行上下文，模型本身支持更长上下文，可在「能力参数」里调整。
        下载走 HuggingFace 镜像，失败会自动回退官方源；半截文件保留，下次续传。
      </div>
    </section>
  )
}

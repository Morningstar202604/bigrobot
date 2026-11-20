import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, Check, Cpu, Download, HardDrive, Loader2, Play,
  RefreshCw, Square, Trash2,
} from 'lucide-react'
import { useState } from 'react'
import { http } from './lib/queries'
import { qk } from './lib/queryClient'
import { t } from './lib/t'

/* 本地小模型：推荐、下载、安装、启用。全部走本地磁盘与 llama.cpp，
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
  recommended: boolean
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
  recommendation: { model_id: string; name: string; reason: string }
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

  const busy = download.isPending || activate.isPending || stop.isPending || remove.isPending

  if (isLoading) return <div className="p-4 text-sm text-muted"><Loader2 size={14} className="animate-spin" /> 读取本地模型…</div>
  if (error) return <div className="p-4 text-sm" style={{ color: 'var(--danger)' }}>{(error as Error).message}</div>
  if (!data) return null

  const rec = data.recommendation.model_id
    ? data.models.find((m) => m.id === data.recommendation.model_id)
    : undefined
  const recJob = rec ? data.jobs.find((j) => j.model_id === rec.id) : undefined
  const recBusy = Boolean(recJob && ['queued', 'downloading', 'verifying', 'cancelling'].includes(recJob.status))
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
      <article key={m.id} className={`lm-card ${m.recommended ? 'best' : ''} ${tooBig ? 'disabled' : ''}`}>
        <div className="lm-card-top">
          <div>
            <div className="lm-title">
              {m.name}
              {m.recommended
                ? <span className="badge ok">本机推荐</span>
                : <span className={`badge ${m.test_only ? 'muted' : 'info'}`}>{m.badge}</span>}
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
                <button className="btn ghost sm" onClick={() => cancel.mutate(job.job_id)}>取消</button>
              </div>
              <div className="lm-progress-track"><div style={{ width: `${job.percent}%` }} /></div>
            </div>
          ) : !m.installed ? (
            <button className="btn sm" onClick={() => download.mutate(m.id)} disabled={busy || tooBig} title={tooBig ? fitLabel : ''}>
              <Download size={13} /> {tooBig ? '内存不足' : `下载 ${m.size_label}`}
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
                  <Square size={13} /> 停止
                </button>
              )}
              <button className="btn ghost sm" onClick={() => remove.mutate(m.id)} disabled={busy || running} title="删除模型文件">
                <Trash2 size={13} />
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
        <span>{t('按本机配置推荐；1B 以下只作为测试和低配体验，不再冒充默认推荐')}</span>
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

      {rec ? (
        <div className="lm-note ok">
          {rec.installed ? <Play size={14} /> : <Download size={14} />}
          <span>
            本机推荐 <b>{rec.name}</b>：{rec.params_b}B / {fmtContext(rec.context)} ctx。
            {data.recommendation.reason}
            {rec.installed && !rec.active ? ' 已装好，点右边启用。' : ''}
          </span>
          {!rec.installed && !recBusy && (
            <button className="btn sm" onClick={() => download.mutate(rec.id)} disabled={busy || rec.fit?.state === 'no'}>
              <Download size={12} /> 下载推荐
            </button>
          )}
          {rec.installed && !rec.active && (
            <button className="btn sm" onClick={() => activate.mutate(rec)} disabled={busy || !data.llama_available || rec.fit?.state === 'no'}>
              <Play size={12} /> 启用推荐
            </button>
          )}
        </div>
      ) : (
        <div className="lm-note warn">
          <AlertTriangle size={14} />
          <span>{data.recommendation.reason}</span>
        </div>
      )}
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
            <span className="text-xs text-muted">只用于工具链路、低配体验和回归测试，不参与“本机推荐”。</span>
          </div>
          <div className="lm-grid">
            {tests.map(renderCard)}
          </div>
        </>
      )}

      <div className="lm-hint">
        推荐只看本机内存：8GB 起步用 4B，16GB 起步用 9B；低于 8GB 不会硬推生产模型，只保留 1B 测试档。
        当前默认 8K 运行上下文，模型本身支持更长上下文，可在「能力参数」里调整。
        下载走 HuggingFace 镜像，失败会自动回退官方源；半截文件保留，下次续传。
      </div>
    </section>
  )
}

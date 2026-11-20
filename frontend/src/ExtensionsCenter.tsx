import { useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  AlertTriangle, CheckCircle2, Plug, Power, Puzzle, RefreshCw, Server, Trash2, Upload,
} from 'lucide-react'
import {
  isAuthError, useExtensionDelete, useExtensionInstallUrl, useExtensionRollback,
  useExtensions, useExtensionToggle, useExtensionUpload, useMcpCreate, useMcpDelete,
  useMcpServers, useMcpTest, useMcpToggle,
} from './lib/queries'
import type { ExtensionItem, McpServer } from './lib/queries'
import { EmptyState, PageHead } from './ui'
import { Spinner, ErrorBanner } from './components/Spinner'
import TokenGate from './components/TokenGate'
import { useFeedback } from './components/Feedback'
import { t } from './lib/t'
import './pages2.css'

function Badge({ children, tone = 'muted' }: { children: ReactNode; tone?: string }) {
  return <span className={`badge ${tone}`}>{children}</span>
}

function ExtensionCard({ item, onChanged }: { item: ExtensionItem; onChanged: () => void }) {
  const fb = useFeedback()
  const toggle = useExtensionToggle()
  const rollback = useExtensionRollback()
  const del = useExtensionDelete()

  const remove = async () => {
    const ok = await fb.confirm(`删除扩展「${item.name}」？会把它移到回收目录，不会立刻丢文件。`, { danger: true, confirmText: '删除' })
    if (!ok) return
    del.mutate(item.id, {
      onSuccess: () => { fb.toast.success('扩展已删除'); onChanged() },
      onError: (e) => fb.toast.error((e as Error).message),
    })
  }

  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Puzzle size={16} style={{ color: 'var(--brand)' }} />
            <b className="text-[15px]">{item.name}</b>
            {item.version && <Badge>v{item.version}</Badge>}
            {item.enabled ? <Badge tone="ok">已启用</Badge> : <Badge tone="warn">已停用</Badge>}
            {item.error && <Badge tone="danger">配置有问题</Badge>}
          </div>
          <p className="text-[13px] text-muted mt-1">{item.description || '（没有描述）'}</p>
          {item.source && <p className="text-[11px] text-muted mt-1 break-all">来源：{item.source}</p>}
          {item.error && <p className="text-[12px] mt-1" style={{ color: 'var(--danger)' }}>{item.error}</p>}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button className="btn ghost sm" title={item.enabled ? '停用' : '启用'}
            onClick={() => toggle.mutate({ id: item.id, enabled: !item.enabled }, {
              onSuccess: () => { fb.toast.success(item.enabled ? '已停用' : '已启用'); onChanged() },
              onError: (e) => fb.toast.error((e as Error).message),
            })}>
            <Power size={14} />
          </button>
          <button className="btn ghost sm" title="回滚到上一个版本"
            onClick={() => rollback.mutate(item.id, {
              onSuccess: (d) => { fb.toast.success(`已回滚到 v${d.item.version}`); onChanged() },
              onError: (e) => fb.toast.error((e as Error).message),
            })}>
            <RefreshCw size={14} />
          </button>
          <button className="btn ghost sm" title="删除扩展" onClick={remove}>
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1">
        {item.tools.map((tool) => (
          <span key={tool.name} className="badge info" title={tool.description}>
            {tool.name}{tool.risk === 'write' ? ' · 写' : ''}
          </span>
        ))}
        {item.skills.map((skill, i) => <span key={i} className="badge muted" title={skill.description}>技能 · {skill.name}</span>)}
        {item.permissions.map((perm) => <span key={perm} className="badge muted">{perm}</span>)}
      </div>
    </div>
  )
}

function McpCard({ server, onChanged }: { server: McpServer; onChanged: () => void }) {
  const fb = useFeedback()
  const toggle = useMcpToggle()
  const test = useMcpTest()
  const del = useMcpDelete()
  const [open, setOpen] = useState(false)
  const tools = server.tools ?? []

  const remove = async () => {
    const ok = await fb.confirm(`删除 MCP 服务器「${server.name}」？`, { danger: true, confirmText: '删除' })
    if (!ok) return
    del.mutate(server.id, {
      onSuccess: () => { fb.toast.success('已删除'); onChanged() },
      onError: (e) => fb.toast.error((e as Error).message),
    })
  }

  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Server size={16} style={{ color: 'var(--brand)' }} />
            <b className="text-[15px]">{server.name}</b>
            <Badge>{server.id}</Badge>
            {server.enabled ? <Badge tone="ok">已启用</Badge> : <Badge tone="warn">已停用</Badge>}
            {server.risk === 'write' && <Badge tone="danger">写权限</Badge>}
            <Badge>{tools.length} 个工具</Badge>
            {server.allow_untrusted && <Badge tone="warn">允许普通成员</Badge>}
          </div>
          <p className="text-[12px] text-muted mt-1 break-all">
            {server.command} {(server.args || []).join(' ')}
          </p>
          {server.last_error && <p className="text-[12px] mt-1" style={{ color: 'var(--danger)' }}>{server.last_error}</p>}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button className="btn ghost sm" title="测试并刷新工具"
            onClick={() => test.mutate(server.id, {
              onSuccess: (d) => {
                if (d.ok) { fb.toast.success(`连接成功，发现 ${d.tools.length} 个工具`); onChanged() }
                else fb.toast.error(d.error || '连接失败')
              },
              onError: (e) => fb.toast.error((e as Error).message),
            })}>
            <RefreshCw size={14} className={test.isPending ? 'animate-spin' : ''} />
          </button>
          <button className="btn ghost sm" title={server.enabled ? '停用' : '启用'}
            onClick={() => toggle.mutate({ id: server.id, enabled: !server.enabled }, {
              onSuccess: () => { fb.toast.success(server.enabled ? '已停用' : '已启用'); onChanged() },
              onError: (e) => fb.toast.error((e as Error).message),
            })}>
            <Power size={14} />
          </button>
          <button className="btn ghost sm" title="删除" onClick={remove}>
            <Trash2 size={14} />
          </button>
        </div>
      </div>
      {tools.length > 0 && (
        <div>
          <button className="text-[12px] text-muted" onClick={() => setOpen(!open)}>
            {open ? '收起工具' : '查看工具'}
          </button>
          {open && (
            <div className="mt-2 space-y-1">
              {tools.map((tool) => (
                <div key={tool.name} className="text-[12px] flex gap-2">
                  <CheckCircle2 size={12} style={{ color: 'var(--ok)', marginTop: 3 }} />
                  <span><b>{tool.name}</b> {tool.description}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function ExtensionsCenter() {
  const fb = useFeedback()
  const [tab, setTab] = useState<'extensions' | 'mcp'>('extensions')
  const [url, setUrl] = useState('')
  const [mcp, setMcp] = useState({ name: '', command: '', args: '', env: '', risk: 'read', allow_untrusted: false, timeout_s: 20 })
  const fileRef = useRef<HTMLInputElement>(null)

  const ext = useExtensions()
  const mcpList = useMcpServers()
  const installUrl = useExtensionInstallUrl()
  const upload = useExtensionUpload()
  const createMcp = useMcpCreate()

  const extError = ext.error
  const mcpError = mcpList.error

  const extItems = ext.data?.items ?? []
  const mcpItems = mcpList.data?.items ?? []

  const mcpEnv = useMemo(() => {
    const out: Record<string, string> = {}
    mcp.env.split('\n').forEach((line) => {
      const i = line.indexOf('=')
      if (i > 0) out[line.slice(0, i).trim()] = line.slice(i + 1).trim()
    })
    return out
  }, [mcp.env])

  if (extError && isAuthError(extError)) return <TokenGate error={extError} onAuthed={() => ext.refetch()} />
  if (mcpError && isAuthError(mcpError)) return <TokenGate error={mcpError} onAuthed={() => mcpList.refetch()} />
  if (extError) return <div className="p-8"><ErrorBanner message={(extError as Error).message} onRetry={() => ext.refetch()} /></div>

  const doInstallUrl = () => {
    if (!url.trim()) return
    installUrl.mutate(url.trim(), {
      onSuccess: (d) => { fb.toast.success(`已安装 ${d.item.name}`); setUrl('') },
      onError: (e) => fb.toast.error((e as Error).message),
    })
  }

  const doUpload = (f: File | undefined) => {
    if (!f) return
    upload.mutate(f, {
      onSuccess: (d) => fb.toast.success(`已安装 ${d.item.name}`),
      onError: (e) => fb.toast.error((e as Error).message),
    })
  }

  const doCreateMcp = () => {
    if (!mcp.name.trim() || !mcp.command.trim()) {
      fb.toast.error('名称和启动命令不能为空')
      return
    }
    createMcp.mutate({
      name: mcp.name.trim(),
      command: mcp.command.trim(),
      args: mcp.args.split(/\n| /).map((s) => s.trim()).filter(Boolean),
      env: mcpEnv,
      risk: mcp.risk,
      allow_untrusted: mcp.allow_untrusted,
      timeout_s: Number(mcp.timeout_s) || 20,
    }, {
      onSuccess: () => {
        fb.toast.success('已添加，点刷新按钮拉取工具')
        setMcp({ name: '', command: '', args: '', env: '', risk: 'read', allow_untrusted: false, timeout_s: 20 })
      },
      onError: (e) => fb.toast.error((e as Error).message),
    })
  }

  return (
    <div className="p-4 md:p-6 max-w-[1200px] mx-auto w-full space-y-4 pb-24 md:pb-10">
      <PageHead
        title={t('扩展与 MCP')}
        sub={t('把外部能力接进来：声明式 HTTP 扩展包，或直接连接 MCP 服务器。装完就在 Agent 的工具清单里。')}
        right={<div className="flex gap-2">
          <button className={`btn ${tab === 'extensions' ? '' : 'secondary'}`} onClick={() => setTab('extensions')}>
            <Puzzle size={14} className="inline mr-1" />扩展包
          </button>
          <button className={`btn ${tab === 'mcp' ? '' : 'secondary'}`} onClick={() => setTab('mcp')}>
            <Plug size={14} className="inline mr-1" />MCP
          </button>
        </div>}
      />

      {tab === 'extensions' && (
        <>
          <div className="card p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Upload size={15} style={{ color: 'var(--brand)' }} />
              <b className="text-[14px]">安装扩展</b>
              <span className="text-[12px] text-muted">只支持声明式 HTTP 扩展；zip 内要有 manifest.json</span>
            </div>
            <div className="flex flex-col md:flex-row gap-2">
              <input className="input flex-1" placeholder="https://example.com/extension.zip" value={url}
                onChange={(e) => setUrl(e.target.value)} />
              <button className="btn" disabled={installUrl.isPending || !url.trim()} onClick={doInstallUrl}>
                {installUrl.isPending ? '安装中…' : '从链接安装'}
              </button>
              <button className="btn secondary" disabled={upload.isPending} onClick={() => fileRef.current?.click()}>
                {upload.isPending ? '上传中…' : '上传 zip'}
              </button>
              <input ref={fileRef} type="file" accept=".zip,application/zip" className="hidden"
                onChange={(e) => { doUpload(e.target.files?.[0]); e.currentTarget.value = '' }} />
            </div>
            <p className="text-[11px] text-muted">
              安全边界：默认拒绝内网地址、不跟随重定向、写工具要求管理员；安装前可在仓库里先看 manifest。
            </p>
          </div>

          {ext.isLoading && <Spinner full label={t('加载扩展…')} />}
          {!ext.isLoading && !extItems.length && (
            <EmptyState icon={<Puzzle size={22} />} title="还没有扩展" desc="上传一个 zip，或从链接安装；装好后工具会直接出现在 Agent 的工具清单里。" />
          )}
          <div className="grid gap-3">
            {extItems.map((item) => <ExtensionCard key={item.id} item={item} onChanged={() => ext.refetch()} />)}
          </div>
        </>
      )}

      {tab === 'mcp' && (
        <>
          {mcpList.data && !mcpList.data.available && (
            <div className="card p-3 flex items-center gap-2 text-[13px]" style={{ color: 'var(--warn)' }}>
              <AlertTriangle size={15} />MCP 依赖未安装：先执行 pip install -r requirements-mcp.txt
            </div>
          )}

          <div className="card p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Server size={15} style={{ color: 'var(--brand)' }} />
              <b className="text-[14px]">添加 MCP 服务器</b>
              <span className="text-[12px] text-muted">stdio 启动命令；添加后点刷新拉取工具</span>
            </div>
            <div className="grid md:grid-cols-2 gap-2">
              <input className="input" placeholder="名称，如 文件系统" value={mcp.name}
                onChange={(e) => setMcp({ ...mcp, name: e.target.value })} />
              <input className="input" placeholder="命令，如 npx / uvx / python3" value={mcp.command}
                onChange={(e) => setMcp({ ...mcp, command: e.target.value })} />
            </div>
            <input className="input w-full" placeholder="参数，每行一个（如 -y / @modelcontextprotocol/server-filesystem / /path）"
              value={mcp.args} onChange={(e) => setMcp({ ...mcp, args: e.target.value })} />
            <input className="input w-full" placeholder="环境变量，每行 KEY=value（敏感值建议 env:NAME 引用环境变量）"
              value={mcp.env} onChange={(e) => setMcp({ ...mcp, env: e.target.value })} />
            <div className="flex flex-wrap items-center gap-3 text-[12px]">
              <label className="flex items-center gap-1">
                权限
                <select className="input" value={mcp.risk} onChange={(e) => setMcp({ ...mcp, risk: e.target.value })}>
                  <option value="read">只读</option>
                  <option value="write">可写</option>
                </select>
              </label>
              <label className="flex items-center gap-1">
                <input type="checkbox" checked={mcp.allow_untrusted}
                  onChange={(e) => setMcp({ ...mcp, allow_untrusted: e.target.checked })} />
                允许普通成员调用（仅只读）
              </label>
              <label className="flex items-center gap-1">
                超时
                <input className="input" style={{ width: 78 }} type="number" min={5} max={120}
                  value={mcp.timeout_s} onChange={(e) => setMcp({ ...mcp, timeout_s: Number(e.target.value) })} />秒
              </label>
              <button className="btn" disabled={createMcp.isPending} onClick={doCreateMcp}>
                {createMcp.isPending ? '添加中…' : '添加'}
              </button>
            </div>
          </div>

          {mcpList.isLoading && <Spinner full label={t('加载 MCP 服务器…')} />}
          {!mcpList.isLoading && !mcpItems.length && (
            <EmptyState icon={<Plug size={22} />} title="还没有 MCP 服务器" desc="本地 stdio 服务器、npx 工具、文件系统、数据库都可以接。" />
          )}
          <div className="grid gap-3">
            {mcpItems.map((server) => <McpCard key={server.id} server={server} onChanged={() => mcpList.refetch()} />)}
          </div>
        </>
      )}
    </div>
  )
}

import { useRef, useState } from 'react'
import { Pencil, Trash2, Upload, Download, Plus, Search, BookOpen, X, Save, Settings2, Power } from 'lucide-react'
import {
  useKb, useKbMutations, useKbImport, useKbTest, useKbDocImport,
  useKbCollectionMutations, usePersonaOptions, exportKb,
} from '../lib/queries'
import type { KbCollection, KbEntry } from '../types/api'
import { Spinner } from '../components/Spinner'
import { EmptyState } from '../ui'
import { useFeedback } from '../components/Feedback'
import { t as tr } from '../lib/t'

const DEFAULT_COLLECTION = 'default'

function collectionName(collections: KbCollection[], id?: string): string {
  return collections.find((c) => c.id === (id || DEFAULT_COLLECTION))?.name || id || '默认知识库'
}

export function KbPanel() {
  const fb = useFeedback()
  const [collection, setCollection] = useState('')
  const { data: kbRes, isLoading } = useKb(collection)
  const km = useKbMutations()
  const kbIo = useKbImport()
  const docIo = useKbDocImport()
  const kbTest = useKbTest()
  const [query, setQuery] = useState('')
  const [recallQuery, setRecallQuery] = useState('')
  const [editing, setEditing] = useState<KbEntry | 'new' | null>(null)
  const [importing, setImporting] = useState(false)
  const [managing, setManaging] = useState(false)
  const [importText, setImportText] = useState('')
  const [importReplace, setImportReplace] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const collections = kbRes?.collections ?? []
  const targetCollection = collection || DEFAULT_COLLECTION
  const targetName = collectionName(collections, targetCollection)

  const doImport = () => {
    kbIo.mutate(
      { text: importText, replace: importReplace, collection: targetCollection },
      {
        onSuccess: (d) => {
          fb.toast.success(tr('导入成功统计', { added: d.added, total: d.total }))
          setImporting(false)
          setImportText('')
          setImportReplace(false)
        },
        onError: (e) => fb.toast.error((e as Error).message),
      },
    )
  }

  if (isLoading) return <Spinner full label={tr('加载知识库…')} />
  const all = kbRes?.kb ?? []
  const q = query.toLowerCase()
  const kb = all.filter((e) =>
    !q || e.id.toLowerCase().includes(q) || e.title.toLowerCase().includes(q) ||
    e.text.toLowerCase().includes(q) || (e.tags || []).some((t) => t.toLowerCase().includes(q)),
  )

  return (
    <>
      <div className="kb-search">
        <div style={{ position: 'relative', flex: 1 }}>
          <Search size={15} style={{ position: 'absolute', left: 16, top: '50%', transform: 'translateY(-50%)', color: 'var(--muted)' }} />
          <input style={{ paddingLeft: 40 }} placeholder={tr('搜索 id / 标题 / 关键词…')} value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <select value={collection} onChange={(e) => setCollection(e.target.value)} style={{ minWidth: 150 }} title={tr('切换知识库')}>
          <option value="">全部知识库（{all.length}）</option>
          {collections.map((c) => (
            <option key={c.id} value={c.id}>{c.name}（{c.entry_count}）</option>
          ))}
        </select>
        {kbRes?.embedding && (
          <span
            className={`badge ${kbRes.embedding.available && kbRes.embedding.enabled !== 'off' ? 'ok' : 'info'}`}
            title={kbRes.embedding.available
              ? `向量后端 ${kbRes.embedding.model}：字面+语义混合检索`
              : '未安装 sentence-transformers，当前纯字面检索（可选装 requirements-embedding.txt）'}
          >
            {kbRes.embedding.enabled === 'off' ? '检索：纯字面（已关）' : kbRes.embedding.available ? '检索：字面+向量' : '检索：纯字面'}
          </span>
        )}
        <button className="btn secondary sm" title={tr('批量导入 Markdown')} onClick={() => setImporting(true)}><Upload size={13} /> {tr('导入')}</button>
        <button
          className="btn secondary sm"
          title={tr('上传 PDF / Word / Markdown / TXT，自动解析分块入库')}
          onClick={() => fileRef.current?.click()}
          disabled={docIo.isPending}
        >
          <Upload size={13} /> {docIo.isPending ? '解析中…' : '传文档'}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".md,.markdown,.txt,.pdf,.docx,.xlsx"
          style={{ display: 'none' }}
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (!f) return
            docIo.mutate({ file: f, collection: targetCollection }, {
              onSuccess: (d: { file: string; added: number; total: number }) => fb.toast.success(tr('文档导入统计', { file: d.file, added: d.added, total: d.total })),
              onError: (err: unknown) => fb.toast.error((err as Error).message),
            })
            e.target.value = ''
          }}
        />
        <button className="btn secondary sm" title={tr('导出当前知识库为 Markdown')} onClick={() => exportKb(collection).catch((e) => fb.toast.error((e as Error).message))}><Download size={13} /> {tr('导出')}</button>
        <button className="btn secondary sm" onClick={() => setManaging(true)}><Settings2 size={13} /> {tr('知识库管理')}</button>
        <button className="btn" onClick={() => setEditing('new')}><Plus size={14} /> {tr('新增条目')}</button>
      </div>

      {/* 试召回：按当前生效配置跑一次检索，调库调参的试错工具 */}
      <div className="kb-search" style={{ marginBottom: 10 }}>
        <input
          placeholder={tr('试召回：输入用户可能的问法，看命中条目与分数…')}
          value={recallQuery}
          onChange={(e) => setRecallQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && recallQuery.trim()) kbTest.mutate({ query: recallQuery.trim(), collection: collection || undefined }) }}
        />
        <button className="btn secondary sm" disabled={!recallQuery.trim() || kbTest.isPending} onClick={() => kbTest.mutate({ query: recallQuery.trim(), collection: collection || undefined })}>
          <Search size={13} /> {kbTest.isPending ? '检索中…' : '试召回'}
        </button>
      </div>
      {kbTest.isError && (
        <div style={{ color: 'var(--danger)', marginBottom: 12, fontSize: 13 }}>{(kbTest.error as Error).message}</div>
      )}
      {kbTest.data && (
        <div style={{ marginBottom: 12, fontSize: 13 }}>
          <div style={{ color: 'var(--muted)', marginBottom: 6 }}>
            top-K {kbTest.data.top_k} · 门槛 {kbTest.data.min_overlap} · 向量 {kbTest.data.embedding}
            {kbTest.data.collection ? ` · 知识库 ${collectionName(collections, kbTest.data.collection)}` : ' · 全部知识库'}
          </div>
          {kbTest.data.hits.length === 0 && <div style={{ color: 'var(--muted)' }}>{tr('无命中（会走兜底话术）')}</div>}
          {kbTest.data.hits.map((h: { id: string; title: string; score: number; answer: string }, i: number) => (
            <div key={h.id} className="f-row" style={{ justifyContent: 'flex-start', gap: 8, padding: '4px 0' }}>
              <span className={`badge ${i === 0 && h.score >= 0.3 ? 'ok' : 'info'}`}>{h.score.toFixed(2)}</span>
              <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{h.id}</span>
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={h.answer}>{h.title}</span>
            </div>
          ))}
        </div>
      )}

      {kb.length === 0 && <EmptyState icon={<BookOpen size={22} />} title={tr('没有匹配的知识库条目')} desc={tr('调整搜索词或新增一条')} />}

      <div className="kb-grid">
        {kb.map((e) => (
          <div className="kb-card" key={e.id}>
            <div className="kc-head">
              <span className="kc-id">{e.id}</span>
              <span className="kc-title">{e.title}</span>
              <div className="kc-actions" style={{ opacity: 1 }}>
                <button className="btn ghost sm" aria-label={tr('编辑条目')} title={tr('编辑条目')} onClick={() => setEditing(e)}><Pencil size={13} /></button>
                <button className="btn ghost sm" aria-label={tr('删除条目')} title={tr('删除条目')} style={{ color: 'var(--danger)' }} onClick={async () => {
                  const ok = await fb.confirm(`删除知识库条目 ${e.id}？删除后相关问答将失去依据。`, { confirmText: '删除' })
                  if (ok) km.remove.mutate(e.id)
                }}><Trash2 size={13} /></button>
              </div>
            </div>
            <div className="kc-tags">
              <em className="badge info" style={{ marginRight: 6 }}>{collectionName(collections, e.collection)}</em>
              {(e.tags || []).map((t) => <em key={t}>{t}</em>)}
            </div>
            <p className="kc-text">{e.text}</p>
            <p className="kc-answer">{e.answer}</p>
            {e.source && <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 6 }}>来源：{e.source}</div>}
          </div>
        ))}
      </div>

      {editing && (
        <div className="drawer-mask" onClick={() => setEditing(null)}>
          <div className="drawer" onClick={(ev) => ev.stopPropagation()}>
            <div className="drawer-head">
              <h3>{editing === 'new' ? '新增知识库条目' : '编辑 ' + (editing as KbEntry).id}</h3>
              <button className="btn ghost sm" onClick={() => setEditing(null)}><X size={14} /></button>
            </div>
            <div className="drawer-body">
              <KbForm
                key={editing === 'new' ? 'new' : (editing as KbEntry).id}
                initial={editing === 'new' ? null : (editing as KbEntry)}
                collections={collections}
                defaultCollection={targetCollection}
                onDone={() => setEditing(null)}
              />
            </div>
          </div>
        </div>
      )}

      {importing && (
        <div className="drawer-mask" onClick={() => setImporting(false)}>
          <div className="drawer" onClick={(ev) => ev.stopPropagation()}>
            <div className="drawer-head">
              <h3>{tr('批量导入知识库')}</h3>
              <button className="btn ghost sm" onClick={() => setImporting(false)}><X size={14} /></button>
            </div>
            <div className="drawer-body">
              <div className="d-field">
                <label>{tr('目标知识库')}</label>
                <span className="text-xs" style={{ color: 'var(--brand-2)' }}>{targetName}</span>
                {collection === '' && <div className="text-xs" style={{ color: 'var(--muted)', marginTop: 4 }}>当前是「全部」视图，导入会进入默认知识库；想进专属库请先在顶部切换。</div>}
              </div>
              <div className="d-field">
                <label>{tr('支持的格式（自动识别）')}</label>
                <span className="text-xs" style={{ color: 'var(--muted)' }}>
                  ① 每条以 <code>{tr('## 标题')}</code> 开头，其后为答案（可含空行）；② 空行分隔的块，首行=标题，其余=答案
                </span>
              </div>
              <div className="d-field">
                <label>{tr('粘贴文本，或选择 .md / .txt 文件')}</label>
                <textarea
                  rows={10}
                  value={importText}
                  onChange={(e) => setImportText(e.target.value)}
                  placeholder={'## 退货政策\n签收后 7 天内支持无理由退货退款…\n\n## 发货时效\n付款后 48 小时内发出'}
                />
                <input type="file" accept=".md,.txt,text/plain,text/markdown" style={{ marginTop: 8 }} onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) f.text().then((t) => setImportText(t))
                }} />
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input type="checkbox" checked={importReplace} onChange={(e) => setImportReplace(e.target.checked)} />
                <span className="text-xs" style={{ color: 'var(--danger)' }}>{tr('清空当前知识库后导入（其它库不受影响）')}</span>
              </label>
              <div className="drawer-foot">
                <button className="btn secondary" onClick={() => setImporting(false)}>{tr('取消')}</button>
                <button className="btn" onClick={doImport} disabled={!importText.trim() || kbIo.isPending}>
                  <Upload size={14} /> {kbIo.isPending ? '导入中…' : '开始导入'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {managing && (
        <KbCollectionsDrawer
          collections={collections}
          onClose={() => setManaging(false)}
        />
      )}
    </>
  )
}

export function KbForm({
  initial, collections, defaultCollection, onDone,
}: {
  initial: KbEntry | null
  collections: KbCollection[]
  defaultCollection: string
  onDone: () => void
}) {
  const km = useKbMutations()
  const fb = useFeedback()
  const [id, setId] = useState(initial?.id ?? '')
  const [title, setTitle] = useState(initial?.title ?? '')
  const [text, setText] = useState(initial?.text ?? '')
  const [answer, setAnswer] = useState(initial?.answer ?? '')
  const [tags, setTags] = useState(initial?.tags.join(',') ?? '')
  const [collection, setCollection] = useState(initial?.collection || defaultCollection)
  const isNew = !initial

  const save = () => {
    const e: KbEntry = {
      id: id.trim(), title, text, answer,
      tags: tags.split(',').map((s: string) => s.trim()).filter((s: string) => s.length > 0),
      collection,
    }
    const p = isNew ? km.create.mutateAsync(e) : km.update.mutateAsync(e)
    p.then(onDone).catch((err) => fb.toast.error((err as Error).message))
  }

  return (
    <>
      <div className="d-field"><label>{tr('条目 ID')}</label><input value={id} disabled={!isNew} onChange={(ev) => setId(ev.target.value)} placeholder="KB007（留空自动编号）" /></div>
      <div className="d-field"><label>{tr('标题')}</label><input value={title} onChange={(ev) => setTitle(ev.target.value)} /></div>
      <div className="d-field">
        <label>{tr('所属知识库')}</label>
        <select value={collection} onChange={(ev) => setCollection(ev.target.value)}>
          {collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>
      <div className="d-field"><label>{tr('检索关键词（空格分隔）')}</label><input value={text} onChange={(ev) => setText(ev.target.value)} /></div>
      <div className="d-field"><label>{tr('答案')}</label><textarea rows={5} value={answer} onChange={(ev) => setAnswer(ev.target.value)} /></div>
      <div className="d-field"><label>{tr('标签（逗号分隔）')}</label><input value={tags} onChange={(ev) => setTags(ev.target.value)} /></div>
      <div className="drawer-foot">
        <button className="btn secondary" onClick={onDone}>{tr('取消')}</button>
        <button className="btn" onClick={save} disabled={!title.trim()}><Save size={14} /> {tr('保存')}</button>
      </div>
    </>
  )
}

/* ============ 多知识库管理 ============ */

function KbCollectionsDrawer({ collections, onClose }: {
  collections: KbCollection[]
  onClose: () => void
}) {
  const fb = useFeedback()
  const cm = useKbCollectionMutations()
  const { data: personaRes } = usePersonaOptions()
  const [editing, setEditing] = useState<KbCollection | 'new' | null>(null)
  const personas = personaRes?.presets ?? []

  const remove = async (c: KbCollection) => {
    if (c.id === DEFAULT_COLLECTION) return
    const ok = await fb.confirm(`删除知识库「${c.name}」？其中 ${c.entry_count} 条会迁到默认知识库，不会丢失。`, { confirmText: '删除并迁移' })
    if (ok) cm.remove.mutate(c.id, { onError: (e) => fb.toast.error((e as Error).message) })
  }

  return (
    <div className="drawer-mask" onClick={onClose}>
      <div className="drawer" onClick={(ev) => ev.stopPropagation()} style={{ width: 'min(720px, 96vw)' }}>
        <div className="drawer-head">
          <h3>{tr('知识库管理')}</h3>
          <button className="btn ghost sm" onClick={onClose}><X size={14} /></button>
        </div>
        <div className="drawer-body">
          <div className="f-row" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
            <div style={{ color: 'var(--muted)', fontSize: 13 }}>
              知识库按集合隔离；不绑定角色 = 所有角色共用，绑定后只有对应预设能召回。
            </div>
            <button className="btn sm" style={{ whiteSpace: 'nowrap' }} onClick={() => setEditing('new')}><Plus size={13} /> 新建知识库</button>
          </div>
          <div className="kb-grid" style={{ marginBottom: 8 }}>
            {collections.map((c) => (
              <div className="kb-card" key={c.id}>
                <div className="kc-head">
                  <span className="kc-id">{c.id}</span>
                  <span className="kc-title">{c.name}</span>
                  <div className="kc-actions" style={{ opacity: 1 }}>
                    <button className="btn ghost sm" title={c.enabled ? '停用' : '启用'} onClick={() => cm.toggle.mutate({ id: c.id, enabled: !c.enabled })}><Power size={13} style={{ color: c.enabled ? 'var(--ok)' : 'var(--muted)' }} /></button>
                    <button className="btn ghost sm" title={tr('编辑知识库')} onClick={() => setEditing(c)}><Pencil size={13} /></button>
                    {c.id !== DEFAULT_COLLECTION && <button className="btn ghost sm" title={tr('删除知识库')} style={{ color: 'var(--danger)' }} onClick={() => remove(c)}><Trash2 size={13} /></button>}
                  </div>
                </div>
                <div className="kc-tags">
                  <em>{c.entry_count} 条</em>
                  {!c.enabled && <em className="badge info">已停用</em>}
                  {(c.persona_ids || []).map((pid) => <em key={pid} className="badge ok">{personas.find((p) => p.id === pid)?.name || pid}</em>)}
                  {(c.persona_ids || []).length === 0 && <em className="badge info">全角色共用</em>}
                </div>
                {c.description && <p className="kc-text">{c.description}</p>}
              </div>
            ))}
          </div>

          {editing && (
            <div style={{ borderTop: '1px solid var(--line)', paddingTop: 14, marginTop: 6 }}>
              <div className="drawer-head" style={{ padding: 0, border: 0 }}>
                <h3 style={{ fontSize: 15 }}>{editing === 'new' ? '新建知识库' : '编辑知识库'}</h3>
                <button className="btn ghost sm" onClick={() => setEditing(null)}><X size={14} /></button>
              </div>
              <KbCollectionForm
                key={editing === 'new' ? 'new' : editing.id}
                initial={editing === 'new' ? null : editing}
                personas={personas}
                onDone={() => setEditing(null)}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function KbCollectionForm({ initial, personas, onDone }: {
  initial: KbCollection | null
  personas: { id: string; name: string; category: string }[]
  onDone: () => void
}) {
  const cm = useKbCollectionMutations()
  const fb = useFeedback()
  const [id, setId] = useState(initial?.id ?? '')
  const [name, setName] = useState(initial?.name ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [personaIds, setPersonaIds] = useState<string[]>(initial?.persona_ids ?? [])
  const [enabled, setEnabled] = useState(initial?.enabled ?? true)
  const isNew = !initial

  const togglePersona = (pid: string) => {
    setPersonaIds((cur) => cur.includes(pid) ? cur.filter((x) => x !== pid) : [...cur, pid])
  }

  const save = () => {
    const payload = {
      id: id.trim() || undefined,
      name: name.trim(),
      description: description.trim(),
      persona_ids: personaIds,
      enabled,
    }
    const p = isNew
      ? cm.create.mutateAsync(payload)
      : cm.update.mutateAsync({ ...payload, id: initial!.id })
    p.then(onDone).catch((err) => fb.toast.error((err as Error).message))
  }

  return (
    <>
      <div className="f-row" style={{ alignItems: 'flex-start', gap: 12 }}>
        <div className="d-field" style={{ flex: 1 }}>
          <label>{tr('知识库 ID')}</label>
          <input value={id} disabled={!isNew} onChange={(e) => setId(e.target.value)} placeholder="如 char_lore（留空自动生成）" />
        </div>
        <div className="d-field" style={{ flex: 1 }}>
          <label>{tr('名称')}</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="如 零·群聊处置资料" />
        </div>
      </div>
      <div className="d-field">
        <label>{tr('说明')}</label>
        <textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="这个库放什么、给谁用" />
      </div>
      <div className="d-field">
        <label>绑定角色（不选 = 全角色共用）</label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {personas.map((p) => (
            <label key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 6, border: '1px solid var(--line)', borderRadius: 8, padding: '5px 9px', cursor: 'pointer', fontSize: 12 }}>
              <input type="checkbox" checked={personaIds.includes(p.id)} onChange={() => togglePersona(p.id)} />
              {p.name}
              <span style={{ color: 'var(--muted)' }}>{p.category}</span>
            </label>
          ))}
          {personas.length === 0 && <span className="text-xs" style={{ color: 'var(--muted)' }}>角色预设加载中…</span>}
        </div>
      </div>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', marginBottom: 10 }}>
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        <span className="text-xs">启用（停用后不会被任何角色召回）</span>
      </label>
      <div className="drawer-foot">
        <button className="btn secondary" onClick={onDone}>{tr('取消')}</button>
        <button className="btn" onClick={save} disabled={!name.trim()}><Save size={14} /> {tr('保存')}</button>
      </div>
    </>
  )
}

/* ============ 数据概览 ============ */

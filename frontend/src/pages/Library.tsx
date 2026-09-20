import { useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, FileText, ImagePlus, MoreHorizontal, Plus, Search, ShieldAlert, UserRound, UsersRound } from 'lucide-react'
import { toast } from 'sonner'
import type { LibraryCategory, LibraryItem, ObjectValidationStatus } from '../api/contracts'
import { api } from '../api/http'
import { useWorkspace } from '../app/WorkspaceContext'
import { BusinessPage, EmptyState, FilterSurface, PageHeader, SectionHeading } from '../components/business/BusinessPage'
import { ObjectStatusBadge } from '../components/business/StatusBadge'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../components/ui/Dialog'
import { Field, Input } from '../components/ui/Input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/Select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/Table'
import { Textarea } from '../components/ui/Textarea'

const pathCategory: Record<string, LibraryCategory> = { people: 'person', terms: 'text', content: 'content' }
const meta: Record<LibraryCategory, { title: string; description: string; singular: string; unavailable?: boolean; icon: typeof UsersRound }> = {
  person: { title: '人物库', description: '管理需要在媒资中核查的人物及其参考照片。', singular: '人物', icon: UsersRound },
  text: { title: '敏感词库', description: '管理文字和语音规则；当前检测通道尚未接入，规则不会参与任何生产任务。', singular: '敏感词规则', unavailable: true, icon: FileText },
  content: { title: '内容规则库', description: '管理场景、对象与行为规则；当前检测通道尚未接入，规则不会参与任何生产任务。', singular: '内容规则', unavailable: true, icon: ShieldAlert },
}
const validationLabels: Record<ObjectValidationStatus, string> = { not_started: '未记录', pending: '等待记录', passed: '已通过', failed: '未通过' }

function StatusSelect({ value, onValueChange }: { value: string; onValueChange: (value: string) => void }) {
  return <Select value={value} onValueChange={onValueChange}><SelectTrigger aria-label="筛选对象状态"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">全部状态</SelectItem><SelectItem value="draft">草稿</SelectItem><SelectItem value="ready_for_material">待补素材</SelectItem><SelectItem value="ready_for_validation">待验证</SelectItem><SelectItem value="active">已启用</SelectItem><SelectItem value="disabled">已停用</SelectItem></SelectContent></Select>
}

function ObjectDialog({ category, open, onOpenChange, item }: { category: LibraryCategory; open: boolean; onOpenChange: (value: boolean) => void; item?: LibraryItem }) {
  const { refresh } = useWorkspace()
  const [name, setName] = useState(item?.name ?? '')
  const [classification, setClassification] = useState(item?.classification ?? '')
  const [aliases, setAliases] = useState(item?.aliases.join('，') ?? '')
  const [definition, setDefinition] = useState(item?.definition ?? '')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const canSubmit = Boolean(name.trim() && classification.trim())
  const submit = async () => {
    if (!canSubmit) { setError('请填写显示名称和分类。'); return }
    setBusy(true); setError('')
    const body = { item_id: item?.item_id ?? `${category}.${crypto.randomUUID()}`, category, classification: classification.trim(), name: name.trim(), aliases: aliases.split(/[，,]/).map(value => value.trim()).filter(Boolean), definition: definition.trim(), status: item?.status ?? 'draft', materials: item?.materials ?? [] }
    try {
      if (item) await api.put(`/api/library-items/${encodeURIComponent(item.item_id)}`, body)
      else await api.post('/api/library-items', body)
      await refresh()
      toast.success(item ? '对象信息已保存' : '审核对象已创建为草稿')
      onOpenChange(false)
    } catch (caught) { setError(caught instanceof Error ? caught.message : '保存失败') } finally { setBusy(false) }
  }
  return <Dialog open={open} onOpenChange={value => { if (!busy) onOpenChange(value) }}><DialogContent><DialogHeader><DialogTitle>{item ? '编辑' : '新建'}{meta[category].singular}</DialogTitle><DialogDescription>{meta[category].unavailable ? '当前检测通道尚未接入；该规则可先维护为草稿，但不能启用到生产审核。' : '名称、分类和审核说明会展示给审核人员；启用状态须通过验证流程维护。'}</DialogDescription></DialogHeader><DialogBody className="space-y-4"><Field label="显示名称"><Input value={name} onChange={event => setName(event.target.value)} aria-invalid={Boolean(error && !name.trim())} /></Field><Field label="分类"><Input value={classification} onChange={event => setClassification(event.target.value)} placeholder={category === 'person' ? '例如：影视演员' : '例如：政治与公共事件'} aria-invalid={Boolean(error && !classification.trim())} /></Field><Field label="别名" hint="多个别名使用逗号分隔"><Input value={aliases} onChange={event => setAliases(event.target.value)} /></Field><Field label="审核说明"><Textarea value={definition} onChange={event => setDefinition(event.target.value)} placeholder="说明何时需要审核员关注" /></Field>{error && <p className="rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive" role="alert">{error}</p>}</DialogBody><DialogFooter><Button variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>取消</Button><Button disabled={busy || !canSubmit} onClick={() => void submit()}>{busy ? '正在保存…' : '保存草稿'}</Button></DialogFooter></DialogContent></Dialog>
}

export function LibraryCenter() {
  const { section = 'people' } = useParams()
  const category = pathCategory[section] ?? 'person'
  const { library } = useWorkspace()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<LibraryItem | null>(null)
  const config = meta[category]
  const rows = useMemo(() => library.filter(item => item.category === category && (status === 'all' || item.status === status) && `${item.name} ${item.aliases.join(' ')} ${item.classification}`.toLowerCase().includes(query.toLowerCase())), [library, category, status, query])
  return <BusinessPage>
    <PageHeader title="审核对象库" subtitle="人物、敏感词与内容规则分别管理；仅已接入且通过验证的人物可以进入生产审核。" actions={<Button onClick={() => setOpen(true)}><Plus />新建{config.singular}</Button>} />
    <nav className="inline-flex w-fit rounded-lg border border-border bg-card p-1 shadow-[0_1px_2px_hsl(var(--foreground)/0.025)]" aria-label="对象库分类">{[['people', '人物库'], ['terms', '敏感词库'], ['content', '内容规则库']].map(([value, label]) => <Button key={value} variant="ghost" size="sm" onClick={() => navigate(`/library/${value}`)} className={section === value ? 'bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground' : ''}>{label}</Button>)}</nav>
    <Card className="border-border/80 bg-muted/[.26]"><CardBody className="flex flex-col gap-3 py-4 sm:flex-row sm:items-start sm:justify-between"><div><h2 className="text-[15px] font-semibold">{config.title}</h2><p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">{config.description}</p>{config.unavailable && <p className="mt-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-amber-800">该能力尚未部署，当前规则不会影响生产审核，也不能被标记为已启用。</p>}</div><Badge variant={config.unavailable ? 'warning' : 'info'}>{config.unavailable ? '检测通道待接入' : '人物画面已接入'}</Badge></CardBody></Card>
    <FilterSurface><label className="relative min-w-64 flex-1"><Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" /><Input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索名称、别名或分类" className="pl-9" /></label><StatusSelect value={status} onValueChange={setStatus} /><span className="pb-2 text-sm text-muted-foreground">共 <strong className="font-semibold text-foreground tabular-nums">{rows.length}</strong> 项</span></FilterSurface>
    <Card>{rows.length ? <Table><TableHeader><TableRow><TableHead>{config.singular}</TableHead><TableHead>分类</TableHead><TableHead>{category === 'person' ? '参考照片' : '别名 / 标签'}</TableHead><TableHead>状态</TableHead><TableHead>审核说明</TableHead><TableHead className="text-right">操作</TableHead></TableRow></TableHeader><TableBody>{rows.map(item => { const photo = item.materials.find(material => material.kind === 'reference_image' && material.status !== 'disabled'); const referenceCount = item.materials.filter(material => material.kind === 'reference_image' && material.status !== 'disabled').length; const Icon = config.icon; return <TableRow key={item.item_id}><TableCell><div className="flex min-w-44 items-center gap-3">{category === 'person' ? (photo ? <img src={photo.local_uri} alt="" className="size-11 rounded-lg object-cover ring-1 ring-border" /> : <span className="grid size-11 place-items-center rounded-lg bg-muted"><UserRound className="size-5 text-muted-foreground" /></span>) : <span className="grid size-10 place-items-center rounded-lg bg-muted"><Icon className="size-5 text-muted-foreground" /></span>}<div>{category === 'person' ? <Link to={`/library/people/${encodeURIComponent(item.item_id)}`} className="font-semibold hover:text-primary hover:underline">{item.name}</Link> : <Button variant="link" className="h-auto p-0 font-semibold" onClick={() => setEditing(item)}>{item.name}</Button>}{item.aliases.length > 0 && <p className="mt-0.5 max-w-52 truncate text-xs text-muted-foreground">{item.aliases.join('、')}</p>}</div></div></TableCell><TableCell><span className="text-sm">{item.classification}</span></TableCell><TableCell><span className="text-sm">{category === 'person' ? `${referenceCount} 张可用照片` : item.aliases.slice(0, 3).join('、') || '—'}</span></TableCell><TableCell><ObjectStatusBadge status={item.status} /></TableCell><TableCell><p className="max-w-sm line-clamp-2 text-sm leading-5 text-muted-foreground">{item.definition || '暂无说明'}</p></TableCell><TableCell className="text-right">{category === 'person' ? <Button asChild variant="outline" size="sm"><Link to={`/library/people/${encodeURIComponent(item.item_id)}`}>管理</Link></Button> : <Button variant="outline" size="icon-sm" onClick={() => setEditing(item)} aria-label={`编辑${item.name}`}><MoreHorizontal /></Button>}</TableCell></TableRow> })}</TableBody></Table> : <EmptyState title="没有符合条件的对象" description="调整搜索或筛选条件，或者新建审核对象。" />}</Card>
    <ObjectDialog key={`${category}-${open}`} category={category} open={open} onOpenChange={setOpen} />
    {editing && <ObjectDialog key={`edit-${editing.item_id}`} category={category} item={editing} open onOpenChange={value => { if (!value) setEditing(null) }} />}
  </BusinessPage>
}

function ValidationDialog({ item, open, onOpenChange, onSaved }: { item: LibraryItem; open: boolean; onOpenChange: (value: boolean) => void; onSaved: () => Promise<void> }) {
  const [decision, setDecision] = useState<'passed' | 'failed'>('passed')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const save = async () => {
    if (!note.trim()) { setError('请记录本次验证的媒资范围或人工判断依据。'); return }
    setBusy(true); setError('')
    try { await api.post(`/api/library-items/${encodeURIComponent(item.item_id)}/validation`, { decision, note: note.trim() }); await onSaved(); toast.success(decision === 'passed' ? '已记录验证通过，可继续启用对象' : '已记录验证未通过，请补充或调整参考照片'); onOpenChange(false) } catch (caught) { setError(caught instanceof Error ? caught.message : '记录验证结论失败') } finally { setBusy(false) }
  }
  return <Dialog open={open} onOpenChange={value => { if (!busy) onOpenChange(value) }}><DialogContent><DialogHeader><DialogTitle>记录验证结论</DialogTitle><DialogDescription>这不是模型分数，而是对独立媒资验证的可追溯人工结论。</DialogDescription></DialogHeader><DialogBody className="space-y-4"><Field label="验证结论"><Select value={decision} onValueChange={value => setDecision(value as 'passed' | 'failed')}><SelectTrigger aria-label="验证结论"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="passed">通过，可进入启用流程</SelectItem><SelectItem value="failed">未通过，需要补充或调整素材</SelectItem></SelectContent></Select></Field><Field label="验证说明"><Textarea value={note} onChange={event => setNote(event.target.value)} placeholder="例如：使用《牧马人》片段盲测，人工复核候选后确认召回与误报可接受。" /></Field>{error && <p className="rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive" role="alert">{error}</p>}</DialogBody><DialogFooter><Button variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>取消</Button><Button disabled={busy || !note.trim()} onClick={() => void save()}>{busy ? '正在保存…' : '保存验证结论'}</Button></DialogFooter></DialogContent></Dialog>
}

export function PersonDetail() {
  const { itemId } = useParams()
  const { library, refresh } = useWorkspace()
  const item = library.find(value => value.item_id === itemId)
  const file = useRef<HTMLInputElement>(null)
  const [selectedFile, setSelectedFile] = useState('')
  const [editing, setEditing] = useState(false)
  const [validationOpen, setValidationOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [lifecycleBusy, setLifecycleBusy] = useState(false)
  if (!item) return <BusinessPage><EmptyState title="找不到该人物对象" action={<Button asChild><Link to="/library/people">返回人物库</Link></Button>} /></BusinessPage>
  const references = item.materials.filter(material => material.kind === 'reference_image')
  const usableReferences = references.filter(material => material.status !== 'disabled')
  const validation = item.validation?.status ?? 'not_started'
  const upload = async () => {
    const selected = file.current?.files?.[0]
    if (!selected) { toast.error('请先选择一张参考照片'); return }
    setBusy(true)
    const form = new FormData(); form.append('file', selected)
    try { await api.upload(`/api/library-items/${encodeURIComponent(item.item_id)}/upload-reference`, form); await refresh(); setSelectedFile(''); if (file.current) file.current.value = ''; toast.success('参考照片已导入，当前对象需要重新确认验证结论') } catch (caught) { toast.error(caught instanceof Error ? caught.message : '照片导入失败') } finally { setBusy(false) }
  }
  const changeStatus = async (materialId: string, disabled: boolean, note: string) => {
    try { await api.patch(`/api/library-items/${encodeURIComponent(item.item_id)}/materials/${encodeURIComponent(materialId)}`, { status: disabled ? 'disabled' : 'pending_validation', quality_note: note || '人工更新参考照片状态。' }); await refresh(); toast.success(disabled ? '照片已停用，对象需重新验证' : '照片已恢复待验证') } catch (caught) { toast.error(caught instanceof Error ? caught.message : '状态更新失败') }
  }
  const transition = async (action: 'submit_for_validation' | 'activate' | 'disable' | 'restore') => {
    setLifecycleBusy(true)
    try { await api.post(`/api/library-items/${encodeURIComponent(item.item_id)}/lifecycle`, { action }); await refresh(); toast.success(({ submit_for_validation: '已提交验证，请记录结论', activate: '对象已启用，可用于生产审核', disable: '对象已停用', restore: '对象已恢复到待治理状态' } as const)[action]) } catch (caught) { toast.error(caught instanceof Error ? caught.message : '状态更新失败') } finally { setLifecycleBusy(false) }
  }
  const primaryAction = item.status === 'active' ? <Button variant="outline" disabled={lifecycleBusy} onClick={() => void transition('disable')}>停用对象</Button> : item.status === 'disabled' ? <Button variant="outline" disabled={lifecycleBusy} onClick={() => void transition('restore')}>恢复对象</Button> : usableReferences.length < 2 ? <Button disabled>还需补充 {2 - usableReferences.length} 张参考照片</Button> : item.status === 'ready_for_material' || item.status === 'draft' ? <Button disabled={lifecycleBusy} onClick={() => void transition('submit_for_validation')}>提交算法验证</Button> : validation === 'passed' ? <Button disabled={lifecycleBusy} onClick={() => void transition('activate')}><CheckCircle2 />启用到生产审核</Button> : <Button disabled={lifecycleBusy} onClick={() => setValidationOpen(true)}>记录验证结论</Button>
  return <BusinessPage>
    <Button asChild variant="ghost" size="sm" className="-ml-2"><Link to="/library/people"><ArrowLeft />返回人物库</Link></Button>
    <PageHeader title={item.name} subtitle={item.classification} actions={<><ObjectStatusBadge status={item.status} />{primaryAction}<Button variant="outline" onClick={() => setEditing(true)}>编辑人物信息</Button></>} />
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]"><Card><CardHeader><SectionHeading title="参考照片" description="生产启用至少需要两张可用照片；增删或停用照片后，已通过的验证会自动失效。" /></CardHeader><CardBody>{references.length ? <div className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-3">{references.map(material => <article key={material.material_id} className="overflow-hidden rounded-xl border border-border bg-background"><img src={material.local_uri} alt={material.title} className="aspect-[4/3] w-full bg-muted object-contain" /><div className="space-y-2.5 p-3.5"><div className="flex items-start justify-between gap-2"><h3 className="text-sm font-semibold">{material.title}</h3><Badge variant={material.status === 'disabled' ? 'destructive' : 'warning'}>{material.status === 'disabled' ? '已停用' : '待验证'}</Badge></div><p className="line-clamp-3 text-xs leading-5 text-muted-foreground">{material.quality_note}</p><Button variant="outline" size="sm" className="w-full" onClick={() => void changeStatus(material.material_id, material.status !== 'disabled', material.quality_note)}>{material.status === 'disabled' ? '恢复照片' : '停用照片'}</Button></div></article>)}</div> : <EmptyState title="还没有参考照片" description="导入清晰、正面、单人的照片后才能创建检查任务。" />}</CardBody></Card><div className="space-y-5 xl:sticky xl:top-6 xl:self-start"><Card><CardHeader><SectionHeading title="对象状态" /></CardHeader><CardBody className="space-y-3.5"><div className="flex items-center justify-between"><span className="text-sm text-muted-foreground">当前状态</span><ObjectStatusBadge status={item.status} /></div><div className="flex items-center justify-between"><span className="text-sm text-muted-foreground">可用参考照片</span><strong className="text-sm">{usableReferences.length} / 2 张</strong></div><div className="flex items-center justify-between"><span className="text-sm text-muted-foreground">算法验证</span><Badge variant={validation === 'passed' ? 'success' : validation === 'failed' ? 'destructive' : validation === 'pending' ? 'warning' : 'secondary'}>{validationLabels[validation]}</Badge></div>{item.validation?.note && <p className="rounded-lg bg-muted p-3 text-xs leading-5 text-muted-foreground">{item.validation.note}</p>}</CardBody></Card><Card><CardHeader><SectionHeading title="添加参考照片" /></CardHeader><CardBody className="space-y-3"><Field label="选择本地照片" hint={selectedFile || '支持 JPEG、PNG；系统会先做单脸、清晰度和尺寸检查。'}><Input ref={file} type="file" accept=".jpg,.jpeg,.png,image/jpeg,image/png" onChange={event => setSelectedFile(event.target.files?.[0]?.name ?? '')} /></Field><Button className="w-full" disabled={busy || !selectedFile} onClick={() => void upload()}><ImagePlus />{busy ? '正在检查照片…' : '导入并检查'}</Button></CardBody></Card><Card><CardHeader><SectionHeading title="最近状态记录" /></CardHeader><CardBody>{item.lifecycle_history?.length ? <ol className="space-y-3">{item.lifecycle_history.slice(-3).reverse().map((entry, index) => <li key={`${entry.at}-${index}`} className="text-xs"><p className="font-medium">{entry.event}</p><p className="mt-1 text-muted-foreground">{entry.note || entry.at}</p></li>)}</ol> : <p className="text-sm text-muted-foreground">后续的素材、验证与启用操作会显示在这里。</p>}</CardBody></Card></div></div>
    <ObjectDialog key={`${item.item_id}-${editing}`} category="person" item={item} open={editing} onOpenChange={setEditing} />
    <ValidationDialog item={item} open={validationOpen} onOpenChange={setValidationOpen} onSaved={refresh} />
  </BusinessPage>
}

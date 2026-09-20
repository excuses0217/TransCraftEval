import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Download, Pencil, Play, RefreshCcw, RotateCcw } from 'lucide-react'
import { toast } from 'sonner'
import type { LibraryItem, MediaItem, ReviewTask } from '../api/contracts'
import { api, ApiError } from '../api/http'
import { useWorkspace } from '../app/WorkspaceContext'
import { BusinessPage, ErrorState, LoadingState, PageHeader, SectionHeading } from '../components/business/BusinessPage'
import { PurposeBadge, TaskStatusBadge } from '../components/business/StatusBadge'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Checkbox } from '../components/ui/Checkbox'
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../components/ui/Dialog'
import { Field, Input } from '../components/ui/Input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/Select'
import { eventCounts, pendingCount, peopleNames, taskMediaName } from '../features/tasks/taskModel'
import { formatDate } from '../lib/utils'

function EditTaskScope({ task, media, library, open, onOpenChange, onSaved }: { task: ReviewTask; media: MediaItem[]; library: LibraryItem[]; open: boolean; onOpenChange: (open: boolean) => void; onSaved: (task: ReviewTask) => void }) {
  const [name, setName] = useState(task.name)
  const [assetPath, setAssetPath] = useState(task.asset_path)
  const [selected, setSelected] = useState<Set<string>>(new Set(task.object_ids))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const people = library.filter(item => item.category === 'person')
  const usable = (item: LibraryItem) => item.status !== 'disabled' && (task.purpose !== 'production' || (item.status === 'active' && item.validation?.status === 'passed')) && item.materials.some(material => material.kind === 'reference_image' && material.status !== 'disabled')
  const toggle = (id: string) => setSelected(current => { const next = new Set(current); next.has(id) ? next.delete(id) : next.add(id); return next })
  const save = async () => {
    if (!name.trim() || !assetPath || !selected.size) { setError('请填写任务名称、媒资并选择至少一位人物。'); return }
    setBusy(true); setError('')
    try { const next = await api.put<ReviewTask>(`/api/review-tasks/${task.task_id}/scope`, { name: name.trim(), asset_path: assetPath, object_ids: [...selected], purpose: task.purpose ?? 'validation', capabilities: ['face'] }); onSaved(next); onOpenChange(false); toast.success('任务范围已保存') } catch (caught) { setError(caught instanceof Error ? caught.message : '任务范围保存失败') } finally { setBusy(false) }
  }
  return <Dialog open={open} onOpenChange={value => { if (!busy) onOpenChange(value) }}><DialogContent className="max-w-2xl"><DialogHeader><DialogTitle>编辑任务范围</DialogTitle><DialogDescription>任务开始前可以调整名称、媒资和核查人物；开始检查后范围将锁定。</DialogDescription></DialogHeader><DialogBody className="space-y-4"><Field label="任务名称"><Input value={name} onChange={event => setName(event.target.value)} maxLength={200} /></Field><Field label="审核媒资"><Select value={assetPath} onValueChange={setAssetPath}><SelectTrigger aria-label="审核媒资" className="w-full"><SelectValue placeholder="选择本地媒资" /></SelectTrigger><SelectContent>{media.map(item => <SelectItem key={item.media_id} value={item.path}>{item.name}</SelectItem>)}</SelectContent></Select></Field><fieldset><legend className="text-sm font-medium">核查人物 <span className="font-normal text-muted-foreground">· 已选 {selected.size} 人</span></legend><div className="mt-2 grid max-h-64 gap-2 overflow-y-auto sm:grid-cols-2">{people.map(item => { const enabled = usable(item); const isSelected = selected.has(item.item_id); return <div key={item.item_id} className={`flex items-center gap-3 rounded-md border p-3 text-sm ${enabled ? '' : 'opacity-50'}`}><Checkbox checked={isSelected} disabled={!enabled && !isSelected} aria-label={`选择${item.name}`} onCheckedChange={() => toggle(item.item_id)} /><span><strong className="block">{item.name}</strong><small className="text-muted-foreground">{item.classification}{!enabled && ' · 当前不可用于此任务'}</small></span></div> })}</div></fieldset>{error && <p className="rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive" role="alert">{error}</p>}</DialogBody><DialogFooter><Button variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>取消</Button><Button disabled={busy || !name.trim() || !assetPath || !selected.size} onClick={() => void save()}>{busy ? '正在保存…' : '保存任务范围'}</Button></DialogFooter></DialogContent></Dialog>
}

export function TaskDetail() {
  const { taskId } = useParams()
  const { library, media, setPurpose, refresh: refreshWorkspace } = useWorkspace()
  const navigate = useNavigate()
  const [task, setTask] = useState<ReviewTask | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const load = async () => {
    if (!taskId) return
    try { const next = await api.get<ReviewTask>(`/api/review-tasks/${taskId}`); setTask(next); if (next.purpose) setPurpose(next.purpose); setError(null) } catch (caught) { setError(caught instanceof Error ? caught : new Error('任务加载失败')) }
  }
  useEffect(() => { void load() }, [taskId])
  useEffect(() => { if (task?.status !== 'running') return; const timer = window.setInterval(() => void load(), 3000); return () => window.clearInterval(timer) }, [task?.status])
  const run = async () => {
    if (!taskId) return
    setBusy(true)
    try { await api.post(`/api/review-tasks/${taskId}/run`); toast.success('系统已开始检查'); await load(); await refreshWorkspace() } catch (caught) { toast.error(caught instanceof ApiError ? caught.message : '无法开始检查') } finally { setBusy(false) }
  }
  const retry = async () => {
    if (!taskId) return
    setBusy(true)
    try { const next = await api.post<ReviewTask>(`/api/review-tasks/${taskId}/retry`); toast.success('已创建新的检查任务'); await refreshWorkspace(); navigate(`/tasks/${next.task_id}`) } catch (caught) { toast.error(caught instanceof Error ? caught.message : '无法重新检查') } finally { setBusy(false) }
  }
  if (error) return <BusinessPage><ErrorState message={error.message} onRetry={() => void load()} /></BusinessPage>
  if (!task) return <BusinessPage><LoadingState /></BusinessPage>
  const counts = eventCounts(task)
  const people = peopleNames(task, library)
  const mainAction = task.status === 'ready' ? <Button disabled={busy} onClick={() => void run()}><Play />{busy ? '正在提交…' : '开始检查'}</Button> : task.status === 'running' ? <Button variant="outline" onClick={() => void load()}><RefreshCcw />刷新进度</Button> : task.status === 'needs_review' ? <Button asChild><Link to={`/tasks/${task.task_id}/review`}><Play />开始复核</Link></Button> : task.status === 'completed' ? <Button asChild><Link to={`/results/${task.task_id}`}>查看审核结果</Link></Button> : null
  return <BusinessPage><Button asChild variant="ghost" size="sm" className="-ml-2"><Link to="/tasks"><ArrowLeft />返回任务中心</Link></Button><PageHeader title={task.name} subtitle={taskMediaName(task, media)} actions={<>{task.status === 'ready' && <Button variant="outline" onClick={() => setEditing(true)}><Pencil />编辑范围</Button>}{mainAction}{task.result && task.status === 'completed' && <Button variant="outline" asChild><a href={`/api/review-tasks/${task.task_id}/report`}><Download />导出记录</a></Button>}</>} />
    {task.error && <div className="rounded-xl border border-critical/20 bg-critical/10 px-4 py-3 text-sm text-critical" role="alert">本次检查未完成：{task.error}</div>}
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]"><Card><CardHeader><SectionHeading title="任务范围" description="任务创建时确定的媒资与核查人物。" /></CardHeader><CardBody className="space-y-5"><div className="flex flex-wrap gap-2"><TaskStatusBadge status={task.status} /><PurposeBadge purpose={task.purpose} /></div><dl className="grid gap-5 sm:grid-cols-2"><div><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">审核能力</dt><dd className="mt-1.5 text-sm font-medium">人物画面</dd></div><div><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">任务创建</dt><dd className="mt-1.5 text-sm">{formatDate(task.created_at)}</dd></div><div className="sm:col-span-2"><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">核查人物</dt><dd className="mt-2 flex flex-wrap gap-2">{people.map(name => <span key={name} className="rounded-lg border border-border bg-muted/45 px-2.5 py-1 text-sm">{name}</span>)}</dd></div></dl></CardBody></Card><Card className="xl:self-start"><CardHeader><SectionHeading title="处理进度" /></CardHeader><CardBody><p className="text-[30px] font-semibold tracking-[-0.03em] tabular-nums">{task.status === 'running' ? `${Math.round((task.progress ?? 0) * 100)}%` : task.result ? `${counts.confirmed + counts.rejected}/${task.result.events.length}` : '—'}</p><p className="mt-2 text-sm leading-5 text-muted-foreground">{task.status === 'running' ? '系统正在分析视频' : task.result ? `${pendingCount(task)} 条仍需处理` : '开始检查后生成候选片段'}</p>{task.result && <div className="mt-5 grid grid-cols-2 gap-2 text-sm"><div className="rounded-lg bg-muted p-3"><span className="text-xs text-muted-foreground">确认出现</span><strong className="mt-1 block text-lg tabular-nums">{counts.confirmed}</strong></div><div className="rounded-lg bg-muted p-3"><span className="text-xs text-muted-foreground">已排除</span><strong className="mt-1 block text-lg tabular-nums">{counts.rejected}</strong></div></div>}</CardBody></Card></div>
    {task.result && <Card><CardHeader><SectionHeading title="检查结果摘要" description={task.result.metrics?.coverage_complete === false ? '视频覆盖不完整，需要重新检查' : '系统检查已完成，候选需人工判断。'} actions={task.status !== 'running' ? <Button variant="outline" size="sm" disabled={busy} onClick={() => void retry()}><RotateCcw />保留记录，重新检查</Button> : undefined} /></CardHeader><CardBody className="p-0"><div className="grid divide-y divide-border sm:grid-cols-4 sm:divide-x sm:divide-y-0"><div className="p-4"><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">候选片段</p><p className="mt-2 text-2xl font-semibold tabular-nums">{task.result.events.length}</p></div><div className="p-4"><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">未处理</p><p className="mt-2 text-2xl font-semibold tabular-nums">{counts.pending}</p></div><div className="p-4"><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">留待复核</p><p className="mt-2 text-2xl font-semibold tabular-nums">{counts.uncertain}</p></div><div className="p-4"><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">覆盖情况</p><p className="mt-2 text-sm font-semibold">{task.result.metrics?.coverage_complete === false ? '不完整' : '完整'}</p></div></div></CardBody></Card>}
    <EditTaskScope key={`${task.task_id}-${editing}`} task={task} media={media} library={library} open={editing} onOpenChange={setEditing} onSaved={next => { setTask(next); void refreshWorkspace() }} />
  </BusinessPage>
}

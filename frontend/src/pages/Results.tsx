import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, CheckCircle2, Download, Search, UserRound, XCircle } from 'lucide-react'
import { toast } from 'sonner'
import type { ReviewTask } from '../api/contracts'
import { api } from '../api/http'
import { useWorkspace } from '../app/WorkspaceContext'
import { BusinessPage, EmptyState, ErrorState, FilterSurface, LoadingState, MetricCard, PageHeader, SectionHeading } from '../components/business/BusinessPage'
import { PurposeBadge, ReviewStatusBadge, TaskStatusBadge } from '../components/business/StatusBadge'
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '../components/ui/AlertDialog'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Field, Input } from '../components/ui/Input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/Select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/Table'
import { Textarea } from '../components/ui/Textarea'
import { eventCounts, reviewStatus, taskMediaName } from '../features/tasks/taskModel'
import { formatDate, formatDuration } from '../lib/utils'

export function Results() {
  const { tasks, media } = useWorkspace()
  const [query, setQuery] = useState('')
  const rows = useMemo(() => tasks.filter(task => task.status === 'completed' && `${task.name} ${task.asset_path}`.toLowerCase().includes(query.toLowerCase())), [query, tasks])
  const confirmed = rows.reduce((sum, task) => sum + eventCounts(task).confirmed, 0)
  return <BusinessPage><PageHeader title="审核结果" subtitle="查看已完成任务的结论、版本记录与导出文件。" /><div className="grid gap-4 sm:grid-cols-2"><MetricCard label="已完成审核" value={rows.length} supportingText="当前工作空间已归档任务" tone="success" /><MetricCard label="确认出现片段" value={confirmed} supportingText="经人工确认的有效证据" tone="info" /></div><FilterSurface><label className="relative min-w-64 flex-1"><Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" /><Input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索任务或媒资" className="pl-9" /></label><span className="pb-2 text-sm text-muted-foreground">共 <strong className="font-semibold text-foreground tabular-nums">{rows.length}</strong> 条结果</span></FilterSurface><Card>{rows.length ? <Table><TableHeader><TableRow><TableHead>审核任务</TableHead><TableHead>审核结论</TableHead><TableHead>完成时间</TableHead><TableHead className="text-right">操作</TableHead></TableRow></TableHeader><TableBody>{rows.map(task => { const counts = eventCounts(task); return <TableRow key={task.task_id}><TableCell><Link to={`/results/${task.task_id}`} className="font-semibold hover:text-primary hover:underline">{task.name}</Link><p className="mt-1 max-w-md truncate text-xs text-muted-foreground">{taskMediaName(task, media)}</p><div className="mt-2"><PurposeBadge purpose={task.purpose} /></div></TableCell><TableCell><p className="font-semibold">确认出现 {counts.confirmed} 条</p><p className="mt-1 text-xs text-muted-foreground">已排除 {counts.rejected} 条 · 共处理 {(task.result?.events ?? []).length} 条</p></TableCell><TableCell className="text-sm text-muted-foreground">{formatDate(task.completed_at)}</TableCell><TableCell className="text-right"><Button asChild size="sm" variant="outline"><Link to={`/results/${task.task_id}`}>查看结果<ArrowRight /></Link></Button></TableCell></TableRow> })}</TableBody></Table> : <EmptyState title={tasks.some(task => task.result) ? '没有匹配的已完成结果' : '还没有已完成的审核'} description="完成所有候选片段的人工判断后，结果会保存到这里。" action={<Button asChild><Link to="/workbench">进入审核工作台</Link></Button>} />}</Card></BusinessPage>
}

function ReopenReviewDialog({ task, onReopened }: { task: ReviewTask; onReopened: (task: ReviewTask) => Promise<void> }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('correction')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const reopen = async () => {
    if (!note.trim()) { setError('请说明为什么需要重新打开已完成审核。'); return }
    setBusy(true); setError('')
    try { const next = await api.post<ReviewTask>(`/api/review-tasks/${task.task_id}/reopen`, { reason, note: note.trim() }); await onReopened(next); toast.success('审核已重新打开；原完成版本已保留'); setOpen(false) } catch (caught) { setError(caught instanceof Error ? caught.message : '重新打开失败') } finally { setBusy(false) }
  }
  return <AlertDialog open={open} onOpenChange={setOpen}><AlertDialogTrigger asChild><Button variant="outline">重新打开审核</Button></AlertDialogTrigger><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>重新打开已完成审核？</AlertDialogTitle><AlertDialogDescription>系统会保留当前完成版本，并把后续处理记录为新的审核周期。</AlertDialogDescription></AlertDialogHeader><div className="space-y-4"><Field label="重新打开原因"><Select value={reason} onValueChange={setReason}><SelectTrigger aria-label="重新打开原因"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="correction">更正人工判断</SelectItem><SelectItem value="new_evidence">补充新的证据</SelectItem><SelectItem value="scope_change">审核范围发生变化</SelectItem><SelectItem value="other">其他原因</SelectItem></SelectContent></Select></Field><Field label="说明"><Textarea value={note} onChange={event => setNote(event.target.value)} placeholder="说明需要更改的片段、依据或影响范围。" /></Field>{error && <p className="rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive" role="alert">{error}</p>}</div><AlertDialogFooter><AlertDialogCancel asChild><Button variant="outline" disabled={busy}>取消</Button></AlertDialogCancel><Button disabled={busy || !note.trim()} onClick={() => void reopen()}>{busy ? '正在重新打开…' : '保留版本并重新打开'}</Button></AlertDialogFooter></AlertDialogContent></AlertDialog>
}

export function ResultDetail() {
  const { taskId } = useParams()
  const { library, media, setPurpose, refresh } = useWorkspace()
  const navigate = useNavigate()
  const [task, setTask] = useState<ReviewTask | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { if (!taskId) return; void api.get<ReviewTask>(`/api/review-tasks/${taskId}`).then(next => { setTask(next); if (next.purpose) setPurpose(next.purpose) }).catch(caught => setError(caught instanceof Error ? caught.message : '结果加载失败')) }, [taskId, setPurpose])
  if (error) return <BusinessPage><ErrorState message={error} /></BusinessPage>
  if (!task) return <BusinessPage><LoadingState text="正在加载审核结果…" /></BusinessPage>
  if (!task.result) return <BusinessPage><EmptyState title="任务尚未生成审核结果" action={<Button asChild><Link to={`/tasks/${task.task_id}`}>查看任务</Link></Button>} /></BusinessPage>
  const counts = eventCounts(task)
  const libraryNames = new Map(library.map(item => [item.item_id, item.name]))
  const snapshotNames = new Map((task.result.reference_snapshot ?? []).map(item => [item.person_id, item.name]))
  const grouped = task.result.object_summaries ?? task.object_ids.map(objectId => {
    const events = task.result?.events.filter(event => event.person_id === objectId) ?? []
    const confirmed = events.filter(event => reviewStatus(event) === 'confirmed').length
    const rejected = events.filter(event => reviewStatus(event) === 'rejected').length
    const unresolved = events.length - confirmed - rejected
    const name = libraryNames.get(objectId) ?? snapshotNames.get(objectId) ?? events[0]?.person_name ?? '未知人物'
    const conclusion = confirmed > 0 ? 'confirmed' : unresolved > 0 ? 'unresolved' : task.result?.metrics?.coverage_complete === false ? 'incomplete' : events.length ? 'excluded' : 'not_found'
    return { object_id: objectId, name, candidate_count: events.length, confirmed, rejected, unresolved, conclusion } as const
  })
  const confirmed = task.result.events.filter(event => reviewStatus(event) === 'confirmed')
  const latestCompletedAt = task.completed_at ?? task.last_completed_at ?? task.analysis_completed_at
  const reopened = async (next: ReviewTask) => { setTask(next); await refresh(); navigate(`/tasks/${next.task_id}/review`) }
  return <BusinessPage>
    <Button asChild variant="ghost" size="sm" className="-ml-2"><Link to="/results"><ArrowLeft />返回审核结果</Link></Button>
    <PageHeader title={task.name} subtitle={`${taskMediaName(task, media)} · ${formatDate(latestCompletedAt)}`} actions={<><TaskStatusBadge status={task.status} />{task.status === 'completed' ? <ReopenReviewDialog task={task} onReopened={reopened} /> : <Button variant="outline" asChild><Link to={`/tasks/${task.task_id}/review`}>继续复核</Link></Button>}{task.status === 'completed' && <Button asChild><a href={`/api/review-tasks/${task.task_id}/report`}><Download />导出审核记录</a></Button>}</>} />
    {task.status !== 'completed' && <div className="rounded-xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-amber-800">这份任务已重新打开。下方保留当前工作版本，历史完成版本不会被覆盖。</div>}
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><MetricCard label="核查人物" value={task.object_ids.length} supportingText="覆盖任务全部审核对象" tone="neutral" /><MetricCard label="确认出现" value={counts.confirmed} tone="success" /><MetricCard label="已排除" value={counts.rejected} tone="neutral" /><MetricCard label="审核版本" value={task.audit_version ?? task.audit_versions?.length ?? 0} tone="info" /></div>
    {task.audit_versions?.length ? <Card><CardHeader><SectionHeading title="审核版本记录" description="完成时生成只读快照；重新打开不会覆盖既有结论。" /></CardHeader><Table><TableHeader><TableRow><TableHead>版本</TableHead><TableHead>完成时间</TableHead><TableHead>处理片段</TableHead><TableHead>状态</TableHead></TableRow></TableHeader><TableBody>{task.audit_versions.map(version => <TableRow key={version.version}><TableCell className="font-medium">V{version.version}</TableCell><TableCell>{formatDate(version.completed_at)}</TableCell><TableCell>{version.events.length} 条</TableCell><TableCell>已归档</TableCell></TableRow>)}</TableBody></Table></Card> : null}
    <Card><CardHeader><SectionHeading title="人物审核结论" description="覆盖任务选择的全部人物，区分确认出现、候选排除与系统未发现。" /></CardHeader><Table><TableHeader><TableRow><TableHead>核查人物</TableHead><TableHead>候选片段</TableHead><TableHead>确认出现</TableHead><TableHead>已排除</TableHead><TableHead>未解决</TableHead><TableHead>结论</TableHead></TableRow></TableHeader><TableBody>{grouped.map(person => <TableRow key={person.object_id}><TableCell className="font-medium"><span className="inline-flex items-center gap-2"><UserRound className="size-4 text-muted-foreground" />{person.name}</span></TableCell><TableCell>{person.candidate_count}</TableCell><TableCell>{person.confirmed}</TableCell><TableCell>{person.rejected}</TableCell><TableCell>{person.unresolved}</TableCell><TableCell><PersonConclusion conclusion={person.conclusion} /></TableCell></TableRow>)}</TableBody></Table></Card>
    <Card><CardHeader><SectionHeading title="确认出现的片段" description="仅展示经审核人员确认的证据片段。" /></CardHeader><CardBody>{confirmed.length ? <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{confirmed.map(event => <article key={event.event_id} className="overflow-hidden rounded-xl border border-border bg-background"><Link to={`/tasks/${task.task_id}/review?event=${event.event_id}`} className="media-poster block aspect-video">{event.evidence_image ? <img src={event.evidence_image} alt="" className="h-full w-full object-cover" /> : null}</Link><div className="p-3.5"><div className="flex items-center justify-between gap-2"><strong className="text-sm">{event.person_name}</strong><ReviewStatusBadge status="confirmed" /></div><p className="mt-2 text-xs text-muted-foreground">约 {formatDuration(event.start_seconds)}</p>{event.note && <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted-foreground">{event.note}</p>}</div></article>)}</div> : <EmptyState title="没有确认出现的片段" description="所有候选均已排除，或任务仍未完成复核。" />}</CardBody></Card>
    <Card><CardHeader><SectionHeading title="完整处理记录" description="每条候选的人工判断与备注均可追溯" /></CardHeader><Table><TableHeader><TableRow><TableHead>人物</TableHead><TableHead>片段位置</TableHead><TableHead>判断</TableHead><TableHead>原因与备注</TableHead><TableHead className="text-right">查看</TableHead></TableRow></TableHeader><TableBody>{task.result.events.map(event => <TableRow key={event.event_id}><TableCell className="font-medium">{event.person_name}</TableCell><TableCell>约 {formatDuration(event.start_seconds)}</TableCell><TableCell><ReviewStatusBadge status={reviewStatus(event)} /></TableCell><TableCell className="max-w-md text-sm text-muted-foreground">{[reasonLabel(event.reason), event.note].filter(Boolean).join('；') || '—'}</TableCell><TableCell className="text-right"><Button asChild variant="ghost" size="sm"><Link to={`/tasks/${task.task_id}/review?event=${event.event_id}`}>定位片段</Link></Button></TableCell></TableRow>)}</TableBody></Table></Card>
  </BusinessPage>
}

function PersonConclusion({ conclusion }: { conclusion: 'confirmed' | 'excluded' | 'not_found' | 'unresolved' | 'incomplete' }) {
  if (conclusion === 'confirmed') return <span className="inline-flex items-center gap-1 text-success"><CheckCircle2 className="size-4" />确认出现</span>
  if (conclusion === 'unresolved') return <span className="text-amber-700">尚未完成</span>
  if (conclusion === 'incomplete') return <span className="text-critical">覆盖不完整</span>
  if (conclusion === 'excluded') return <span className="inline-flex items-center gap-1 text-muted-foreground"><XCircle className="size-4" />候选均已排除</span>
  return <span className="inline-flex items-center gap-1 text-muted-foreground"><XCircle className="size-4" />系统未发现</span>
}

function reasonLabel(reason?: string) { return ({ appearance: '与参考照片相符', not_target: '不是核查对象', unclear: '画面不清楚', insufficient_context: '上下文不足', other: '其他原因' } as Record<string, string>)[reason ?? ''] ?? '' }

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Check, CheckCircle2, ChevronDown, CircleAlert, Download, ImageIcon, LoaderCircle, Pause, Play, RotateCcw, Search, X, ZoomIn } from 'lucide-react'
import { toast } from 'sonner'
import type { EvidenceEvent, ReferenceMaterial, ReviewStatus, ReviewTask } from '../api/contracts'
import { api, ApiError } from '../api/http'
import { useWorkspace } from '../app/WorkspaceContext'
import { ReviewStatusBadge, TaskStatusBadge } from '../components/business/StatusBadge'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Dialog, DialogContent } from '../components/ui/Dialog'
import { Input } from '../components/ui/Input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/Select'
import { Textarea } from '../components/ui/Textarea'
import { confidenceOf, eventCounts, reviewStatus } from '../features/tasks/taskModel'
import { cn, formatDuration } from '../lib/utils'

type Preview = { url: string; start_seconds: number; duration_seconds: number }
type ReviewFilter = 'unresolved' | 'all' | ReviewStatus

const confidenceDimensionLabels = {
  model_evidence: '模型判断',
  temporal_consistency: '多帧稳定',
  environment_quality: '画面环境',
  reference_coverage: '参考覆盖'
} as const

const previewCache = new Map<string, Promise<Preview>>()
let previewQueue: Promise<unknown> = Promise.resolve()

function delay(milliseconds: number) { return new Promise(resolve => window.setTimeout(resolve, milliseconds)) }

function preparePreview(taskId: string, eventId: string) {
  const key = `${taskId}/${eventId}`
  const cached = previewCache.get(key)
  if (cached) return cached
  const pending = previewQueue.catch(() => undefined).then(async () => {
    for (let attempt = 0; attempt < 8; attempt += 1) {
      try {
        return await api.post<Preview>(`/api/review-tasks/${taskId}/events/${eventId}/preview`)
      } catch (caught) {
        if (!(caught instanceof ApiError) || caught.status !== 409 || attempt === 7) throw caught
        await delay(700)
      }
    }
    throw new Error('片段暂时无法播放')
  })
  previewCache.set(key, pending)
  previewQueue = pending
  void pending.catch(() => previewCache.delete(key))
  if (previewCache.size > 30) previewCache.delete(previewCache.keys().next().value as string)
  return pending
}

const reasonOptions = [
  { value: '', label: '使用默认依据' },
  { value: 'appearance', label: '外貌特征与参考照片相符' },
  { value: 'not_target', label: '画面人物不是核查对象' },
  { value: 'unclear', label: '画面不清楚，无法判断' },
  { value: 'insufficient_context', label: '上下文不足，需要进一步核查' },
  { value: 'other', label: '其他原因' }
]

function reviewReason(status: ReviewStatus, current: string) {
  if (status === 'confirmed') return current === 'appearance' || current === 'other' ? current : 'appearance'
  if (status === 'rejected') return current === 'not_target' || current === 'other' ? current : 'not_target'
  if (status === 'uncertain') return ['unclear', 'insufficient_context', 'other'].includes(current) ? current : 'unclear'
  return ''
}

function filterEvents(events: EvidenceEvent[], filter: ReviewFilter) {
  if (filter === 'all') return events
  if (filter === 'unresolved') return events.filter(event => ['pending', 'uncertain'].includes(reviewStatus(event)))
  return events.filter(event => reviewStatus(event) === filter)
}

function evidenceDescription(event: EvidenceEvent) {
  if ((event.segment_count ?? 1) > 1) return `连续片段 · ${event.segment_count} 处画面`
  if ((event.support_frames ?? 0) >= 3) return '连续出现'
  if (event.ambiguous) return '人物相似，需仔细辨认'
  return '单个片段'
}

type GalleryMaterial = Pick<ReferenceMaterial, 'material_id' | 'local_uri'>

function ReferenceGallery({ materials, personName }: { materials: GalleryMaterial[]; personName: string }) {
  const [active, setActive] = useState<GalleryMaterial | null>(null)
  if (!materials.length) return <p className="rounded-md bg-muted p-3 text-sm text-muted-foreground">本次任务没有可展示的参考照片。</p>
  return <><div className="grid grid-cols-3 gap-2">{materials.slice(0, 6).map((material, index) => <Button key={material.material_id ?? material.local_uri ?? index} type="button" variant="ghost" onClick={() => setActive(material)} className="group relative h-auto aspect-square w-full overflow-hidden rounded-md border bg-muted p-0 focus-visible:ring-primary"><img src={material.local_uri} alt={`${personName}参考照片`} className="h-full w-full object-cover" /><span className="absolute inset-x-0 bottom-0 flex translate-y-full items-center justify-center gap-1 bg-black/65 py-1 text-[11px] text-white transition group-hover:translate-y-0"><ZoomIn className="size-3" />放大</span></Button>)}</div><Dialog open={Boolean(active)} onOpenChange={open => { if (!open) setActive(null) }}><DialogContent className="max-w-3xl overflow-hidden p-0"><div className="grid max-h-[85dvh] place-items-center bg-black"><img src={active?.local_uri} alt={`${personName}参考照片大图`} className="max-h-[85dvh] w-full object-contain" /></div></DialogContent></Dialog></>
}

function AppearanceOverview({
  events,
  selected,
  duration,
  onSelect
}: {
  events: EvidenceEvent[]
  selected: EvidenceEvent
  duration: number
  onSelect: (eventId: string) => void
}) {
  const personEvents = events.filter(event => event.person_id === selected.person_id)
  const occurrenceCount = personEvents.reduce((count, event) => count + Math.max(1, event.segments?.length ?? 0), 0)
  const ticks = [0, .25, .5, .75, 1]

  return <section className="shrink-0 rounded-lg border bg-background px-3 py-2.5 shadow-sm" aria-label={`${selected.person_name}在原片中的出现概览`}>
    <div className="mb-2 flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2">
        <span className="text-xs font-medium">原片出现概览</span>
        <span className="truncate text-[11px] text-muted-foreground">{selected.person_name} · {occurrenceCount} 处</span>
      </div>
      <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">总长 {formatDuration(duration)}</span>
    </div>
    <div className="relative h-3 rounded-full bg-muted shadow-inner">
      {personEvents.flatMap(event => {
        const segments = event.segments?.length ? event.segments : [{ start_seconds: event.start_seconds, end_seconds: event.end_seconds }]
        return segments.map((segment, index) => {
          const start = Math.max(0, Math.min(duration, segment.start_seconds))
          const end = Math.max(start, Math.min(duration, segment.end_seconds))
          const left = (start / duration) * 100
          const width = Math.max(.7, ((end - start) / duration) * 100)
          const active = event.event_id === selected.event_id
          return <button
            key={`${event.event_id}-${index}`}
            type="button"
            onClick={() => onSelect(event.event_id)}
            className={cn('absolute top-0 h-3 rounded-full border border-background/70 bg-primary/35 transition hover:bg-primary/60 focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2', active && 'z-[1] bg-primary shadow-[0_0_0_2px_hsl(var(--primary)/0.18)]')}
            style={{ left: `${left}%`, width: `${Math.min(width, 100 - left)}%`, minWidth: 6 }}
            aria-label={`${active ? '当前片段，' : ''}${formatDuration(start)}至${formatDuration(end)}`}
            title={`${formatDuration(start)}–${formatDuration(end)}${active ? ' · 当前片段' : ''}`}
          />
        })
      })}
    </div>
    <div className="mt-1.5 flex justify-between text-[10px] tabular-nums text-muted-foreground">
      {ticks.map(tick => <span key={tick}>{formatDuration(duration * tick)}</span>)}
    </div>
  </section>
}

export function Review() {
  const { taskId } = useParams()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const { library, setPurpose, refresh: refreshWorkspace } = useWorkspace()
  const [task, setTask] = useState<ReviewTask | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState<ReviewFilter>('unresolved')
  const [queueQuery, setQueueQuery] = useState('')
  const [selectedId, setSelectedId] = useState(params.get('event') ?? '')
  const [reason, setReason] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [previewDuration, setPreviewDuration] = useState<number | null>(null)
  const [previewError, setPreviewError] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [saveNotice, setSaveNotice] = useState('')
  const videoRef = useRef<HTMLVideoElement>(null)
  const eventButtonRefs = useRef(new Map<string, HTMLButtonElement>())
  const previewVersion = useRef(0)
  const requestedEvent = useRef(params.get('event'))
  const saveNoticeTimer = useRef<number | null>(null)

  const load = useCallback(async () => {
    if (!taskId) return
    try {
      const next = await api.get<ReviewTask>(`/api/review-tasks/${taskId}`)
      setTask(next)
      if (next.purpose) setPurpose(next.purpose)
      setError('')
    } catch (caught) { setError(caught instanceof Error ? caught.message : '任务加载失败') }
    finally { setLoading(false) }
  }, [taskId])

  useEffect(() => { void load() }, [load])
  const allEvents = useMemo(() => task?.result?.events ?? [], [task])
  useEffect(() => { if (task?.status === 'completed') setFilter('all') }, [task?.status])
  const visibleEvents = useMemo(() => {
    const filtered = filterEvents(allEvents, filter)
    const normalizedQuery = queueQuery.trim().toLocaleLowerCase('zh-CN')
    if (!normalizedQuery) return filtered
    return filtered.filter(event => event.person_name.toLocaleLowerCase('zh-CN').includes(normalizedQuery)
      || formatDuration(event.start_seconds).includes(normalizedQuery))
  }, [allEvents, filter, queueQuery])
  const selected = allEvents.find(event => event.event_id === selectedId) ?? null

  useEffect(() => {
    const requested = requestedEvent.current
    if (!requested || !allEvents.length) return
    const event = allEvents.find(item => item.event_id === requested)
    if (event && !['pending', 'uncertain'].includes(reviewStatus(event))) setFilter('all')
    requestedEvent.current = null
  }, [allEvents])

  useEffect(() => {
    if (!allEvents.length) return
    if (selectedId && allEvents.some(event => event.event_id === selectedId)) return
    const first = allEvents.find(event => ['pending', 'uncertain'].includes(reviewStatus(event))) ?? allEvents[0]
    setSelectedId(first.event_id)
  }, [allEvents, selectedId])

  useEffect(() => {
    if (!selected) return
    setReason(selected.reason ?? '')
    setNote(selected.note ?? '')
    setDetailsOpen(Boolean(selected.reason || selected.note))
    setParams(current => { const next = new URLSearchParams(current); next.set('event', selected.event_id); return next }, { replace: true })
  }, [selected?.event_id])

  useEffect(() => {
    eventButtonRefs.current.get(selectedId)?.scrollIntoView({ block: 'nearest' })
  }, [filter, queueQuery, selectedId, visibleEvents.length])

  const loadPreview = useCallback(async (event: EvidenceEvent) => {
    if (!taskId) return
    const version = ++previewVersion.current
    setPreview(null); setPreviewDuration(null); setPreviewError(''); setPreviewLoading(true)
    try {
      const next = await preparePreview(taskId, event.event_id)
      if (version !== previewVersion.current) return
      setPreview(next)
    } catch (caught) {
      if (version !== previewVersion.current) return
      setPreviewError(caught instanceof Error ? caught.message : '片段暂时无法播放')
    } finally { if (version === previewVersion.current) setPreviewLoading(false) }
  }, [taskId])

  useEffect(() => { if (selected) void loadPreview(selected); return () => { previewVersion.current += 1; videoRef.current?.pause() } }, [selected?.event_id, loadPreview])
  useEffect(() => () => { if (saveNoticeTimer.current) window.clearTimeout(saveNoticeTimer.current) }, [])

  const choose = (eventId: string) => { if (!busy) setSelectedId(eventId) }
  const move = useCallback((offset: number) => {
    if (!visibleEvents.length || !selectedId) return
    const index = visibleEvents.findIndex(event => event.event_id === selectedId)
    const next = visibleEvents[Math.max(0, Math.min(visibleEvents.length - 1, index + offset))]
    if (next) choose(next.event_id)
  }, [visibleEvents, selectedId, busy])

  const save = useCallback(async (status: ReviewStatus) => {
    if (!taskId || !selected || busy || task?.status === 'completed') return
    setBusy(true)
    const previousVisible = visibleEvents.map(event => event.event_id)
    const currentIndex = previousVisible.indexOf(selected.event_id)
    try {
      const next = await api.patch<ReviewTask>(`/api/review-tasks/${taskId}/events/${selected.event_id}`, { review_status: status, reason: reviewReason(status, reason), note })
      setTask(next)
      await refreshWorkspace()
      setSaveNotice(status === 'confirmed' ? '已确认并保存' : status === 'rejected' ? '已排除并保存' : status === 'uncertain' ? '已留待复核' : '已恢复为未处理')
      if (saveNoticeTimer.current) window.clearTimeout(saveNoticeTimer.current)
      saveNoticeTimer.current = window.setTimeout(() => setSaveNotice(''), 1600)
      const nextEvents = next.result?.events ?? []
      const unresolved = nextEvents.find(event => event.event_id !== selected.event_id && ['pending', 'uncertain'].includes(reviewStatus(event)))
      const adjacentId = previousVisible[currentIndex + 1] ?? previousVisible[currentIndex - 1]
      const target = unresolved ?? nextEvents.find(event => event.event_id === adjacentId)
      if (target) setSelectedId(target.event_id)
    } catch (caught) { toast.error(caught instanceof Error ? caught.message : '处理结果保存失败') }
    finally { setBusy(false) }
  }, [busy, note, reason, refreshWorkspace, selected, task?.status, taskId, visibleEvents])

  const finish = async () => {
    if (!taskId || busy) return
    setBusy(true)
    try { const next = await api.post<ReviewTask>(`/api/review-tasks/${taskId}/complete`); setTask(next); await refreshWorkspace(); toast.success('本次审核已完成'); navigate(`/results/${taskId}`) }
    catch (caught) { toast.error(caught instanceof Error ? caught.message : '暂时无法完成审核') }
    finally { setBusy(false) }
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!selected || busy || task?.status === 'completed' || event.repeat || event.ctrlKey || event.metaKey || event.altKey || ['INPUT', 'TEXTAREA', 'SELECT'].includes((event.target as HTMLElement).tagName)) return
      if (event.key === '1') { event.preventDefault(); void save('confirmed') }
      else if (event.key === '2') { event.preventDefault(); void save('rejected') }
      else if (event.key === '3') { event.preventDefault(); void save('uncertain') }
      else if (event.key === '0') { event.preventDefault(); void save('pending') }
      else if (event.key === 'ArrowLeft') { event.preventDefault(); move(-1) }
      else if (event.key === 'ArrowRight') { event.preventDefault(); move(1) }
      else if (event.key === ' ') { event.preventDefault(); const video = videoRef.current; if (video) video.paused ? void video.play().catch(() => undefined) : video.pause() }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [busy, move, save, selected, task?.status])

  if (loading) return <div className="grid h-[100dvh] place-items-center bg-muted/40 text-sm text-muted-foreground"><LoaderCircle className="mr-2 inline size-5 animate-spin"/>正在打开复核任务…</div>
  if (error || !task) return <div className="grid h-[100dvh] place-items-center bg-muted/40 p-6 text-center"><div><p className="font-medium">无法打开复核任务</p><p className="mt-1 text-sm text-muted-foreground">{error || '任务不存在'}</p><Button asChild variant="outline" className="mt-4"><Link to="/tasks">返回任务中心</Link></Button></div></div>
  if (!task.result) return <div className="grid h-[100dvh] place-items-center bg-muted/40 p-6 text-center"><div><p className="font-medium">任务尚未生成候选片段</p><p className="mt-1 text-sm text-muted-foreground">请返回任务详情查看检查进度。</p><Button asChild className="mt-4"><Link to={`/tasks/${task.task_id}`}>查看任务</Link></Button></div></div>

  const counts = eventCounts(task)
  const unresolvedCount = counts.pending + counts.uncertain
  const selectedIndex = visibleEvents.findIndex(event => event.event_id === selectedId)
  const selectedAllIndex = allEvents.findIndex(event => event.event_id === selectedId)
  const snapshot = task.result.reference_snapshot?.find(item => item.person_id === selected?.person_id)
  const currentPerson = library.find(item => item.item_id === selected?.person_id)
  const references = (snapshot?.materials ?? currentPerson?.materials ?? []).filter(material => material.kind === 'reference_image' && material.status !== 'disabled')
  const confidence = selected ? confidenceOf(selected) : null
  const confidenceUnavailable = task.result.confidence_available === false
  const readOnly = task.status === 'completed'
  const canFinish = unresolvedCount === 0 && task.result.metrics?.coverage_complete !== false && !['running', 'completed'].includes(task.status)
  const mediaDuration = Math.max(Number(task.result.metrics?.duration_seconds) || 0, ...allEvents.map(event => event.end_seconds || event.start_seconds), 1)

  if (!allEvents.length) return <div className="flex min-h-[100dvh] flex-col bg-muted/55">
    <header className="flex h-16 shrink-0 items-center gap-3 border-b bg-background px-4 sm:px-5">
      <Button asChild variant="ghost" size="icon-sm"><Link to={readOnly ? '/results' : '/workbench'} aria-label="返回"><ArrowLeft/></Link></Button>
      <div className="min-w-0 flex-1"><div className="flex items-center gap-2"><h1 className="truncate text-sm font-semibold sm:text-base">{task.name}</h1><TaskStatusBadge status={task.status}/></div><p className="mt-1 text-xs text-muted-foreground">核查 {task.object_ids.length} 个人物 · 0 条候选片段</p></div>
      <Button variant="outline" size="sm" asChild><a href={`/api/review-tasks/${task.task_id}/report`}><Download/>导出</a></Button>
      {readOnly ? <Button size="sm" asChild><Link to={`/results/${task.task_id}`}>查看审核结果<ArrowRight/></Link></Button> : canFinish ? <Button size="sm" disabled={busy} onClick={() => void finish()}><CheckCircle2/>生成审核结果</Button> : null}
    </header>
    <main className="grid flex-1 place-items-center p-6">
      <section className="w-full max-w-xl rounded-xl border bg-background p-8 text-center shadow-sm">
        <span className="mx-auto grid size-12 place-items-center rounded-full bg-success/10 text-success"><CheckCircle2 className="size-6" /></span>
        <h2 className="mt-4 text-lg font-semibold">系统未发现候选人物片段</h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted-foreground">本次检查已覆盖完整媒资，任务范围内的人物均会在结果中记录为“系统未发现”，不会进入人工复核队列。</p>
        {task.result.metrics?.coverage_complete === false && <p className="mt-4 rounded-lg border border-critical/20 bg-critical/10 p-3 text-sm text-critical">视频扫描覆盖不完整，当前不能形成完整审核结论，请返回任务详情重新检查。</p>}
        <div className="mt-6 flex justify-center gap-2"><Button variant="outline" asChild><Link to={`/tasks/${task.task_id}`}>查看任务详情</Link></Button>{readOnly && <Button asChild><Link to={`/results/${task.task_id}`}>查看完整结果</Link></Button>}</div>
      </section>
    </main>
  </div>

  return <div className="flex min-h-[100dvh] min-w-0 flex-col bg-muted/55 lg:h-[100dvh] lg:overflow-hidden">
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-3 border-b border-border/90 bg-background/95 px-3 shadow-[0_1px_2px_hsl(var(--foreground)/0.025)] backdrop-blur sm:px-5 lg:static">
      <Button asChild variant="ghost" size="icon-sm"><Link to={readOnly ? `/results/${task.task_id}` : '/workbench'} aria-label={readOnly ? '返回审核结果' : '返回审核工作台'}><ArrowLeft/></Link></Button>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2"><h1 className="truncate text-sm font-semibold sm:text-base">{task.name}</h1><TaskStatusBadge status={task.status}/></div>
        <div className="mt-1 flex items-center gap-2">
          <div className="hidden h-1.5 w-24 overflow-hidden rounded-full bg-muted sm:block"><div className="h-full rounded-full bg-primary" style={{ width: `${allEvents.length ? Math.round(((counts.confirmed + counts.rejected) / allEvents.length) * 100) : 0}%` }} /></div>
          <p className="truncate text-xs text-muted-foreground">已处理 {counts.confirmed + counts.rejected}/{allEvents.length} · 剩余 {unresolvedCount}{saveNotice && <span className="ml-1 text-success">· {saveNotice}</span>}</p>
        </div>
      </div>
      <Button variant="outline" size="sm" asChild><a href={`/api/review-tasks/${task.task_id}/report`}><Download/>导出</a></Button>
      {readOnly ? <Button size="sm" asChild><Link to={`/results/${task.task_id}`}>查看审核结果<ArrowRight/></Link></Button> : <Button size="sm" disabled={!canFinish || busy} onClick={() => void finish()} title={!canFinish ? '处理完所有候选片段后才能完成审核' : undefined}><CheckCircle2/>完成审核</Button>}
    </header>

    {task.result.metrics?.coverage_complete === false && <div className="shrink-0 border-b border-critical/20 bg-critical/10 px-4 py-2 text-sm text-critical">本次视频覆盖不完整，不能形成完整审核结论。请从任务详情重新检查。</div>}
    {readOnly && <div className="shrink-0 border-b border-success/20 bg-success/10 px-4 py-2 text-sm text-emerald-800">这是一份已完成审核的只读记录。如需更改判断，请先在审核结果页填写原因并重新打开。</div>}
    {confidenceUnavailable && <div className="shrink-0 border-b border-warning/25 bg-warning/10 px-4 py-2 text-sm text-amber-800">{task.result.confidence_unavailable_reason ?? '旧版任务不提供当前算法置信度。'}</div>}
    <div className="grid flex-1 grid-cols-1 lg:min-h-0 lg:grid-cols-[300px_minmax(0,1fr)_340px]">
      <aside className="order-2 flex flex-col border-t bg-background lg:order-1 lg:min-h-0 lg:border-r lg:border-t-0">
        <div className="shrink-0 space-y-3 border-b border-border/80 p-3.5">
          <div className="flex items-center justify-between gap-3">
            <div><h2 className="text-sm font-semibold">复核队列</h2><p className="mt-0.5 text-xs text-muted-foreground">按媒资时间顺序排列</p></div>
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs tabular-nums text-muted-foreground">{visibleEvents.length} 条</span>
          </div>
          <Select value={filter} onValueChange={value => { setFilter(value as ReviewFilter); setSelectedId('') }}>
            <SelectTrigger aria-label="筛选候选片段" className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="unresolved">待处理与留待复核</SelectItem><SelectItem value="all">全部片段</SelectItem><SelectItem value="confirmed">确认出现</SelectItem><SelectItem value="rejected">已排除</SelectItem><SelectItem value="uncertain">留待复核</SelectItem><SelectItem value="pending">未处理</SelectItem></SelectContent>
          </Select>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={queueQuery} onChange={event => setQueueQuery(event.target.value)} placeholder="搜索人物或时间" className="pl-9" aria-label="搜索人物或时间" />
          </div>
        </div>
        <div className="max-h-72 flex-1 overflow-y-auto p-2 lg:min-h-0 lg:max-h-none">
          {visibleEvents.length ? <div className="space-y-1">{visibleEvents.map(event => {
            const absoluteIndex = allEvents.findIndex(item => item.event_id === event.event_id)
            const active = selectedId === event.event_id
            const eventConfidence = confidenceOf(event)
            return <button
              key={event.event_id}
              ref={element => { if (element) eventButtonRefs.current.set(event.event_id, element); else eventButtonRefs.current.delete(event.event_id) }}
              type="button"
              onClick={() => choose(event.event_id)}
              aria-current={active ? 'true' : undefined}
              className={cn('grid w-full grid-cols-[64px_minmax(0,1fr)_auto] items-center gap-2 rounded-md border border-transparent p-1.5 text-left outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-primary/30', active && 'border-primary/25 bg-primary/[.055] hover:bg-primary/[.07]')}
            >
              <div className="relative h-11 w-16 shrink-0 overflow-hidden rounded bg-sidebar">{event.evidence_image ? <img src={event.evidence_image} alt="" loading="lazy" className="h-full w-full object-cover" /> : <ImageIcon className="m-auto size-5 text-white" />}<span className="absolute bottom-0 right-0 bg-black/70 px-1 py-0.5 text-[10px] text-white">{formatDuration(event.start_seconds)}</span></div>
              <span className="min-w-0"><strong className="block truncate text-sm font-medium">{event.person_name}</strong><small className="mt-0.5 block truncate text-[11px] text-muted-foreground">{(event.segment_count ?? 1) > 1 ? `连续片段 · ${event.segment_count} 处` : `第 ${absoluteIndex + 1} 条`} · {confidenceUnavailable ? '旧版结果' : eventConfidence.available ? `综合证据${eventConfidence.label}` : '证据待计算'}</small></span>
              <ReviewStatusBadge status={reviewStatus(event)} />
            </button>
          })}</div> : <div className="p-8 text-center text-sm text-muted-foreground">当前筛选下没有片段。</div>}
        </div>
      </aside>

      <main className="order-1 bg-muted/[.35] p-3 sm:p-5 lg:order-2 lg:min-h-0 lg:overflow-y-auto lg:p-6">
        {selected ? <div className="mx-auto flex h-full max-w-5xl flex-col gap-3">
          <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground"><span className="rounded-md border bg-background px-1.5 py-0.5 tabular-nums">第 {selectedAllIndex + 1}/{allEvents.length} 条</span><span>约 {formatDuration(selected.start_seconds)}</span><span aria-hidden="true">·</span><span>{evidenceDescription(selected)}</span></div>
              <p className="mt-1.5 text-base font-semibold">确认画面中是否出现「{selected.person_name}」</p>
            </div>
            <div className="flex gap-1"><Button variant="outline" size="icon-sm" disabled={selectedIndex <= 0} onClick={() => move(-1)} aria-label="上一条"><ArrowLeft/></Button><Button variant="outline" size="icon-sm" disabled={selectedIndex < 0 || selectedIndex >= visibleEvents.length - 1} onClick={() => move(1)} aria-label="下一条"><ArrowRight/></Button></div>
          </div>
          <div className="review-video relative min-h-[220px] flex-1 overflow-hidden rounded-xl border border-border bg-sidebar shadow-[0_6px_20px_hsl(var(--foreground)/0.08)] sm:min-h-[300px]">{preview ? <video ref={videoRef} key={preview.url} src={preview.url} poster={selected.evidence_image} controls muted playsInline preload="metadata" onLoadedMetadata={event => { const duration = event.currentTarget.duration; setPreviewDuration(Number.isFinite(duration) ? duration : null) }} className="h-full min-h-[220px] w-full object-contain sm:min-h-[300px]" /> : <img src={selected.evidence_image} alt="候选证据画面" className="h-full min-h-[220px] w-full object-contain sm:min-h-[300px]" />}{previewLoading && <div className="absolute inset-x-0 top-0 flex items-center justify-center gap-2 bg-black/65 py-2 text-xs text-white"><LoaderCircle className="size-3.5 animate-spin" />正在准备前后片段…</div>}{previewError && <div className="absolute inset-x-3 bottom-3 flex items-center justify-between gap-3 rounded-md bg-black/75 px-3 py-2 text-xs text-white"><span>{previewError}，已显示关键画面。</span><Button variant="ghost" size="sm" className="h-auto p-0 text-white underline" onClick={() => void loadPreview(selected)}><RotateCcw className="size-3" />重试</Button></div>}</div>
          <AppearanceOverview events={allEvents} selected={selected} duration={mediaDuration} onSelect={choose} />
          <div className="flex shrink-0 items-center justify-between text-xs text-muted-foreground"><span>{preview ? `片段起点 ${formatDuration(preview.start_seconds)} · 时长 ${formatDuration(previewDuration ?? preview.duration_seconds)}` : '关键画面'}</span><span className="hidden sm:inline">空格 播放/暂停 · ← → 切换</span></div>
        </div> : <div className="grid h-full place-items-center text-sm text-muted-foreground">请选择一个候选片段。</div>}
      </main>

      <aside className="order-3 border-t border-border/90 bg-background p-4 lg:min-h-0 lg:overflow-y-auto lg:border-l lg:border-t-0 lg:p-5">
        {selected ? <div className="space-y-4">
          {confidenceUnavailable ? <section className="rounded-lg border border-warning/25 bg-warning/10 p-3.5"><p className="text-sm font-semibold text-amber-800">当前置信度不可用</p><p className="mt-1.5 text-xs leading-5 text-amber-800/80">{task.result.confidence_unavailable_reason ?? '请使用当前算法重新检查该媒资。'}</p></section> : confidence && <section className="rounded-lg border bg-muted/35 p-3.5">
            <div className="flex items-start justify-between gap-3">
              <div><p className="text-xs font-medium text-muted-foreground">系统辅助判断</p><div className="mt-1 flex items-baseline gap-2"><strong className="text-2xl tabular-nums">{confidence.available ? confidence.score : '待计算'}</strong>{confidence.available && <span className="text-sm text-muted-foreground">/100</span>}<span className="text-sm text-muted-foreground">综合证据指数</span></div></div>
              <Badge variant={confidence.level === 'high' ? 'success' : confidence.level === 'medium' ? 'warning' : 'outline'}>{confidence.label}</Badge>
            </div>
            {confidence.available && <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-border"><div className={cn('h-full rounded-full', confidence.level === 'high' ? 'bg-success' : confidence.level === 'medium' ? 'bg-warning' : 'bg-muted-foreground')} style={{ width: `${confidence.score}%` }} /></div>}
            {confidence.dimensions && <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 border-t pt-3">
              {(Object.entries(confidenceDimensionLabels) as Array<[keyof typeof confidenceDimensionLabels, string]>).map(([key, label]) => <div key={key}>
                <div className="flex items-center justify-between gap-2 text-[11px]"><span className="text-muted-foreground">{label}</span><span className="font-medium tabular-nums">{confidence.dimensions?.[key] == null ? '—' : `${confidence.dimensions[key]}/100`}</span></div>
                <div className="mt-1 h-1 overflow-hidden rounded-full bg-border"><div className="h-full rounded-full bg-foreground/55" style={{ width: `${confidence.dimensions?.[key] ?? 0}%` }} /></div>
              </div>)}
            </div>}
            {(confidence.factors.length > 0 || confidence.cautions.length > 0) && <div className="mt-3 space-y-1.5 text-xs leading-5">
              {confidence.factors.map(factor => <p key={factor} className="flex gap-2 text-foreground/80"><Check className="mt-1 size-3 shrink-0 text-success" />{factor}</p>)}
              {confidence.cautions.map(caution => <p key={caution} className="flex gap-2 text-amber-700"><CircleAlert className="mt-1 size-3 shrink-0" />{caution}</p>)}
            </div>}
            <p className="mt-3 border-t pt-2.5 text-[11px] leading-4 text-muted-foreground">综合多帧一致性、参考图匹配、候选区分度与画面质量生成。分数表示证据充分程度，不是人物身份概率。</p>
          </section>}

          <section>
            <div className="mb-3"><p className="text-xs font-medium text-muted-foreground">人物对照</p><div className="mt-1 flex items-center justify-between gap-3"><h2 className="text-base font-semibold">{selected.person_name}</h2><span className="text-xs text-muted-foreground">{references.length} 张参考照片</span></div></div>
            <ReferenceGallery materials={references} personName={selected.person_name}/>
          </section>

          {readOnly ? <section className="rounded-lg border border-success/20 bg-success/10 p-3.5"><p className="text-sm font-semibold text-emerald-800">已保存审核结论</p><p className="mt-1 text-xs leading-5 text-emerald-800/80">当前片段为只读记录，判断结果和审核说明均已纳入本次审核版本。</p><div className="mt-3"><ReviewStatusBadge status={reviewStatus(selected)} /></div></section> : <section className="border-t pt-4">
            <p className="mb-3 text-sm font-semibold">做出判断</p>
            <div className="grid grid-cols-2 gap-2">
              <Button variant="success" className="justify-between" disabled={busy} onClick={() => void save('confirmed')}><span className="flex items-center gap-2"><Check />确认出现</span><kbd className="rounded bg-white/20 px-1.5 text-xs">1</kbd></Button>
              <Button variant="outline" className="justify-between" disabled={busy} onClick={() => void save('rejected')}><span className="flex items-center gap-2"><X />排除</span><kbd className="rounded border px-1.5 text-xs">2</kbd></Button>
              <Button variant="outline" className="col-span-2 justify-between text-amber-700" disabled={busy} onClick={() => void save('uncertain')}><span className="flex items-center gap-2"><Pause />留待复核</span><kbd className="rounded border px-1.5 text-xs">3</kbd></Button>
            </div>
            <p className="mt-2 text-center text-[11px] text-muted-foreground">选择后自动保存并进入下一条</p>
          </section>}

          {readOnly ? (selected.reason || selected.note) && <section className="border-t pt-4"><p className="text-sm font-semibold">审核说明</p><dl className="mt-3 space-y-3 text-sm"><div><dt className="text-xs text-muted-foreground">判定依据</dt><dd className="mt-1">{reasonOptions.find(option => option.value === selected.reason)?.label ?? '未填写'}</dd></div>{selected.note && <div><dt className="text-xs text-muted-foreground">审核备注</dt><dd className="mt-1 whitespace-pre-wrap leading-6">{selected.note}</dd></div>}</dl></section> : <section className="border-t pt-3">
            <Button type="button" variant="ghost" size="sm" className="w-full justify-between px-1 text-muted-foreground" onClick={() => setDetailsOpen(open => !open)} aria-expanded={detailsOpen}><span>补充审核说明</span><ChevronDown className={cn('size-4 transition-transform', detailsOpen && 'rotate-180')} /></Button>
            {detailsOpen && <div className="mt-3 space-y-3"><label className="grid gap-1.5 text-sm font-medium">判定依据<Select value={reason || 'none'} onValueChange={value => setReason(value === 'none' ? '' : value)}><SelectTrigger aria-label="判定依据" className="w-full"><SelectValue placeholder="选择判定依据" /></SelectTrigger><SelectContent>{reasonOptions.map(option => <SelectItem key={option.value || 'none'} value={option.value || 'none'}>{option.label}</SelectItem>)}</SelectContent></Select></label><label className="grid gap-1.5 text-sm font-medium">审核备注<Textarea value={note} onChange={event => setNote(event.target.value)} placeholder="记录遮挡、造型变化或上下文" className="min-h-20" /></label></div>}
          </section>}

          {!readOnly && reviewStatus(selected) !== 'pending' && <Button variant="ghost" className="w-full text-muted-foreground" disabled={busy} onClick={() => void save('pending')}><RotateCcw />恢复为未处理</Button>}
        </div> : null}
      </aside>
    </div>
  </div>
}

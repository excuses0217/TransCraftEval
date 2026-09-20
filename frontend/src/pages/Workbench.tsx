import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight, ChevronRight, CircleAlert, Clock3, ListFilter, Play, Plus, Search } from 'lucide-react'
import type { ReviewTask } from '../api/contracts'
import { useWorkspace } from '../app/WorkspaceContext'
import { BusinessPage, EmptyState, PageHeader } from '../components/business/BusinessPage'
import { Card, CardBody, CardDescription, CardHeader, CardTitle } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/Select'
import { eventsOf, isReviewableTask, reviewStatus, taskMediaName } from '../features/tasks/taskModel'
import { cn, formatDuration } from '../lib/utils'

type QueueRow = {
  task: ReviewTask
  events: ReturnType<typeof eventsOf>
  total: number
  handled: number
  uncertain: number
  progress: number
  mediaName: string
  poster?: string
}

export function Workbench() {
  const { tasks, purpose, media } = useWorkspace()
  const [params, setParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState('remaining')
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const filter = params.get('review') ?? 'open'

  const rows = useMemo<QueueRow[]>(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase('zh-CN')
    const nextRows = tasks
      .filter(isReviewableTask)
      .map(task => {
        const allEvents = eventsOf(task)
        const events = allEvents.filter(event => filter === 'uncertain'
          ? reviewStatus(event) === 'uncertain'
          : ['pending', 'uncertain'].includes(reviewStatus(event)))
        const uncertain = allEvents.filter(event => reviewStatus(event) === 'uncertain').length
        const handled = allEvents.filter(event => ['confirmed', 'rejected'].includes(reviewStatus(event))).length
        const mediaName = taskMediaName(task, media)
        const managedMedia = media.find(item => item.path === task.asset_path)
        return {
          task,
          events,
          total: allEvents.length,
          handled,
          uncertain,
          progress: allEvents.length ? Math.round((handled / allEvents.length) * 100) : 0,
          mediaName,
          poster: managedMedia?.poster || events[0]?.evidence_image,
        }
      })
      .filter(row => row.events.length > 0)
      .filter(row => !normalizedQuery
        || row.task.name.toLocaleLowerCase('zh-CN').includes(normalizedQuery)
        || row.mediaName.toLocaleLowerCase('zh-CN').includes(normalizedQuery))

    return nextRows.sort((left, right) => {
      if (sort === 'uncertain') return right.uncertain - left.uncertain || right.events.length - left.events.length
      if (sort === 'recent') {
        const rightTime = Date.parse(right.task.reopened_at || right.task.analysis_completed_at || right.task.created_at || '') || 0
        const leftTime = Date.parse(left.task.reopened_at || left.task.analysis_completed_at || left.task.created_at || '') || 0
        return rightTime - leftTime
      }
      return right.events.length - left.events.length || right.uncertain - left.uncertain
    })
  }, [filter, media, query, sort, tasks])

  const total = rows.reduce((sum, row) => sum + row.events.length, 0)
  const selected = rows.find(row => row.task.task_id === selectedTaskId) ?? rows[0]
  const nextEvent = selected?.events[0]

  function changeFilter(next: 'open' | 'uncertain') {
    const nextParams = new URLSearchParams(params)
    if (next === 'open') nextParams.delete('review')
    else nextParams.set('review', 'uncertain')
    setParams(nextParams, { replace: true })
    setSelectedTaskId(null)
  }

  return <BusinessPage className="space-y-4">
    <PageHeader
      title="审核工作台"
      subtitle={`${purpose === 'production' ? '生产审核' : '算法验证'} · ${rows.length} 个任务，${total} 条待复核`}
      actions={<Button asChild><Link to="/tasks/new"><Plus />新建审核任务</Link></Button>}
    />

    <Card>
      <CardBody className="flex flex-col gap-3 p-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row sm:items-center">
          <div className="inline-flex shrink-0 rounded-md bg-muted p-1" role="tablist" aria-label="待办类型">
            <Button variant="ghost" size="sm" aria-current={filter === 'open' ? 'page' : undefined} className={cn('h-7', filter === 'open' && 'bg-background text-foreground shadow-sm hover:bg-background')} onClick={() => changeFilter('open')}>全部待处理</Button>
            <Button variant="ghost" size="sm" aria-current={filter === 'uncertain' ? 'page' : undefined} className={cn('h-7', filter === 'uncertain' && 'bg-background text-foreground shadow-sm hover:bg-background')} onClick={() => changeFilter('uncertain')}>留待复核</Button>
          </div>
          <div className="relative min-w-0 flex-1 sm:max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索任务或媒资" className="pl-9" aria-label="搜索任务或媒资" />
          </div>
          <Select value={sort} onValueChange={setSort}>
            <SelectTrigger className="w-full sm:w-36" aria-label="队列排序">
              <ListFilter className="size-4 text-muted-foreground" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="remaining">待处理最多</SelectItem>
              <SelectItem value="uncertain">待定优先</SelectItem>
              <SelectItem value="recent">最近更新</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
          <Clock3 className="size-3.5" />
          <span>按时间顺序</span>
          <span aria-hidden="true">·</span>
          <span>自动保存</span>
        </div>
      </CardBody>
    </Card>

    {rows.length ? <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
      <Card className="min-w-0">
        <CardHeader className="items-center py-3.5">
          <div>
            <CardTitle>待复核任务</CardTitle>
            <CardDescription>选择任务后从上次位置继续处理</CardDescription>
          </div>
          <Badge variant="secondary" className="tabular-nums">{rows.length} 个任务</Badge>
        </CardHeader>
        <div className="max-h-[calc(100vh-310px)] min-h-[420px] overflow-y-auto overscroll-contain">
          {rows.map(row => {
            const active = row.task.task_id === selected?.task.task_id
            return <button
              key={row.task.task_id}
              type="button"
              onClick={() => setSelectedTaskId(row.task.task_id)}
              className={cn(
                'group grid w-full grid-cols-[72px_minmax(0,1fr)_auto] items-center gap-3 border-b px-4 py-3 text-left outline-none transition-colors last:border-b-0 hover:bg-muted/45 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/30',
                active && 'bg-primary/[.045] hover:bg-primary/[.06]',
              )}
              aria-pressed={active}
            >
              <div className="media-poster h-12 w-[72px] overflow-hidden rounded-md border bg-muted">
                {row.poster && <img src={row.poster} alt="" className="h-full w-full object-cover" />}
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-foreground">{row.task.name}</p>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">{row.mediaName} · {row.task.object_ids.length} 个审核对象</p>
                <div className="mt-2 flex items-center gap-2">
                  <div className="h-1.5 min-w-20 max-w-48 flex-1 overflow-hidden rounded-full bg-muted" aria-label={`已完成 ${row.progress}%`}>
                    <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${row.progress}%` }} />
                  </div>
                  <span className="text-[11px] tabular-nums text-muted-foreground">已处理 {row.handled}/{row.total}</span>
                </div>
              </div>
              <div className="flex items-center gap-3 pl-2">
                <div className="min-w-[58px] text-right">
                  <p className="text-sm font-semibold tabular-nums text-foreground">{row.events.length}</p>
                  <p className="text-[11px] text-muted-foreground">待处理</p>
                  {row.uncertain > 0 && <p className="mt-0.5 flex items-center justify-end gap-1 text-[11px] font-medium text-amber-700"><CircleAlert className="size-3" />{row.uncertain} 条待定</p>}
                </div>
                <ChevronRight className={cn('size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5', active && 'text-primary')} />
              </div>
            </button>
          })}
        </div>
      </Card>

      {selected && nextEvent && <Card className="xl:sticky xl:top-5">
        <CardHeader className="py-3.5">
          <div className="min-w-0">
            <p className="text-xs font-medium text-muted-foreground">当前任务</p>
            <CardTitle className="mt-1 truncate">{selected.task.name}</CardTitle>
            <CardDescription className="truncate">{selected.mediaName}</CardDescription>
          </div>
          {selected.uncertain > 0 && <Badge variant="warning">{selected.uncertain} 条待定</Badge>}
        </CardHeader>
        <CardBody className="space-y-4">
          <div className="grid grid-cols-3 divide-x rounded-lg border bg-muted/25 py-3 text-center">
            <div><p className="text-lg font-semibold tabular-nums">{selected.events.length}</p><p className="text-[11px] text-muted-foreground">待处理</p></div>
            <div><p className="text-lg font-semibold tabular-nums">{selected.handled}</p><p className="text-[11px] text-muted-foreground">已处理</p></div>
            <div><p className="text-lg font-semibold tabular-nums">{selected.progress}%</p><p className="text-[11px] text-muted-foreground">完成度</p></div>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between gap-3">
              <p className="text-xs font-medium text-muted-foreground">下一条待复核</p>
              <span className="text-xs tabular-nums text-muted-foreground">约 {formatDuration(nextEvent.evidence_seconds ?? nextEvent.start_seconds)}</span>
            </div>
            <div className="overflow-hidden rounded-lg border bg-muted/20">
              <div className="media-poster aspect-video w-full bg-muted">
                {nextEvent.evidence_image && <img src={nextEvent.evidence_image} alt="待复核画面" className="h-full w-full object-cover" />}
              </div>
              <div className="flex items-center justify-between gap-3 p-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{nextEvent.person_name}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">等待确认是否出现</p>
                </div>
                {reviewStatus(nextEvent) === 'uncertain' && <Badge variant="warning">留待复核</Badge>}
              </div>
            </div>
          </div>

          <Button asChild size="lg" className="w-full">
            <Link to={`/tasks/${selected.task.task_id}/review?event=${nextEvent.event_id}`}><Play />继续复核</Link>
          </Button>
          <Button asChild variant="ghost" size="sm" className="w-full text-muted-foreground">
            <Link to={`/tasks/${selected.task.task_id}`}>查看任务详情<ArrowRight /></Link>
          </Button>
        </CardBody>
      </Card>}
    </div> : <Card><EmptyState title={filter === 'uncertain' ? '没有留待复核的片段' : query ? '没有匹配的任务' : '当前没有待处理任务'} description={query ? '尝试更换搜索词或清除筛选条件。' : '新任务完成系统检查后，会在这里进入人工复核。'} action={<Button asChild><Link to="/tasks">查看任务中心<ArrowRight /></Link></Button>} /></Card>}
  </BusinessPage>
}

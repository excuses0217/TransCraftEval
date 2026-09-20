import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, CircleDotDashed } from 'lucide-react'
import type { LibraryItem, MediaItem, ReviewTask } from '../../api/contracts'
import { Button } from '../../components/ui/Button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../../components/ui/Table'
import { TaskStatusBadge } from '../../components/business/StatusBadge'
import { Checkbox } from '../../components/ui/Checkbox'
import { eventCounts, nextAction, pendingCount, peopleNames, taskMediaName } from './taskModel'
import { formatDate } from '../../lib/utils'

export function TaskTable({ tasks, library, media = [], compact = false }: { tasks: ReviewTask[]; library: LibraryItem[]; media?: MediaItem[]; compact?: boolean }) {
  const [selected, setSelected] = useState<string[]>([])
  const selectedOnPage = tasks.filter(task => selected.includes(task.task_id)).length
  const allSelected = tasks.length > 0 && selectedOnPage === tasks.length
  const toggleAll = (checked: boolean) => setSelected(checked ? tasks.map(task => task.task_id) : [])
  const toggleRow = (taskId: string, checked: boolean) => setSelected(value => checked ? [...value, taskId] : value.filter(id => id !== taskId))
  const taskTarget = (task: ReviewTask) => task.status === 'needs_review'
    ? `/tasks/${task.task_id}/review`
    : task.status === 'completed'
      ? `/results/${task.task_id}`
      : `/tasks/${task.task_id}`

  if (compact) return <div className="divide-y divide-border">
    {tasks.map(task => {
      const people = peopleNames(task, library)
      const counts = eventCounts(task)
      return <div key={task.task_id} className="grid grid-cols-[minmax(0,1fr)_76px_32px] items-center gap-3 px-5 py-3.5 transition-colors hover:bg-muted/30">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <Link to={`/tasks/${task.task_id}`} className="min-w-0 truncate text-sm font-medium text-foreground hover:underline">{task.name}</Link>
            <TaskStatusBadge status={task.status} />
          </div>
          <p className="mt-1 truncate text-xs text-muted-foreground">{taskMediaName(task, media)} · {task.purpose === 'production' ? '生产审核' : '算法验证'}</p>
          <p className="mt-1 truncate text-xs text-muted-foreground"><span className="text-foreground/80">人物画面</span> · {people.slice(0, 3).join('、')}{people.length > 3 ? ` 等 ${people.length} 人` : ''}</p>
        </div>
        <div className="text-right">
          {task.status === 'running' ? <>
            <p className="text-sm font-semibold tabular-nums">{Math.round((task.progress ?? 0) * 100)}%</p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">检查中</p>
          </> : task.result ? <>
            <p className="text-sm font-semibold tabular-nums">{pendingCount(task)}</p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">待处理</p>
            {(counts.confirmed > 0 || counts.rejected > 0) && <p className="mt-0.5 text-[10px] tabular-nums text-muted-foreground">{counts.confirmed} 确认 · {counts.rejected} 排除</p>}
          </> : <p className="text-xs text-muted-foreground">待检查</p>}
        </div>
        <Button asChild size="icon-sm" variant="ghost"><Link to={taskTarget(task)} aria-label={`${nextAction(task)}：${task.name}`}><ArrowUpRight /></Link></Button>
      </div>
    })}
  </div>

  return <Table>
    <TableHeader>
      <TableRow>
        {!compact && <TableHead className="w-11 pr-0"><Checkbox aria-label="选择全部任务" checked={allSelected ? true : selectedOnPage ? 'indeterminate' : false} onCheckedChange={value => toggleAll(Boolean(value))} /></TableHead>}
        <TableHead>任务</TableHead>
        <TableHead>审核范围</TableHead>
        <TableHead>处理进度</TableHead>
        {!compact && <TableHead>更新时间</TableHead>}
        <TableHead className="text-right">操作</TableHead>
      </TableRow>
    </TableHeader>
    <TableBody>
      {tasks.map(task => {
        const people = peopleNames(task, library)
        const counts = eventCounts(task)
        const isSelected = selected.includes(task.task_id)
        return <TableRow key={task.task_id} data-state={isSelected ? 'selected' : undefined}>
          {!compact && <TableCell className="w-11 pr-0"><Checkbox aria-label={`选择任务 ${task.name}`} checked={isSelected} onCheckedChange={value => toggleRow(task.task_id, Boolean(value))} /></TableCell>}
          <TableCell>
            <div className="min-w-52">
              <div className="flex min-w-0 flex-wrap items-center gap-1.5"><Link to={`/tasks/${task.task_id}`} className="min-w-0 break-words font-medium leading-5 text-foreground hover:underline">{task.name}</Link><TaskStatusBadge status={task.status} /></div>
              <p className="mt-1 max-w-72 truncate text-xs text-muted-foreground">{taskMediaName(task, media)} · {task.purpose === 'production' ? '生产审核' : '算法验证'}</p>
            </div>
          </TableCell>
          <TableCell>
            <div className="max-w-56">
              <p className="text-sm leading-5 text-foreground">{people.slice(0, 3).join('、')}{people.length > 3 ? ` 等 ${people.length} 人` : ''}</p>
              <p className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground"><CircleDotDashed className="size-3" />人物画面</p>
            </div>
          </TableCell>
          <TableCell>
            {task.status === 'running' ? <div className="min-w-28">
              <p className="text-sm font-semibold tabular-nums">{Math.round((task.progress ?? 0) * 100)}%</p>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-info transition-all" style={{ width: `${Math.round((task.progress ?? 0) * 100)}%` }} /></div>
            </div> : task.result ? <div>
              <p className="font-medium tabular-nums">{pendingCount(task)} 条待处理</p>
              <p className="mt-1 text-xs text-muted-foreground">确认 {counts.confirmed} · 排除 {counts.rejected}</p>
            </div> : <span className="text-sm text-muted-foreground">尚未开始检查</span>}
          </TableCell>
          {!compact && <TableCell className="text-xs text-muted-foreground">{formatDate(task.completed_at ?? task.analysis_completed_at ?? task.started_at ?? task.created_at)}</TableCell>}
          <TableCell className="text-right">
            <Button asChild size="sm" variant={task.status === 'needs_review' ? 'outline' : 'ghost'} className="ml-auto"><Link to={taskTarget(task)} aria-label={`${nextAction(task)}：${task.name}`}>{nextAction(task)}<ArrowUpRight /></Link></Button>
          </TableCell>
        </TableRow>
      })}
    </TableBody>
  </Table>
}

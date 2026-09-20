import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, CircleAlert, PackageOpen, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '../api/http'
import { useWorkspace } from '../app/WorkspaceContext'
import { BusinessPage, EmptyState, ErrorState, LoadingState, PageHeader, SectionHeading } from '../components/business/BusinessPage'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { eventCounts, eventsOf, isReviewableTask, pendingCount } from '../features/tasks/taskModel'

function WorkspaceSetupCard() {
  const { setup, refresh } = useWorkspace()
  const [busy, setBusy] = useState(false)
  if (!setup?.enabled || setup.initialized) return null
  const importDefaults = async () => {
    setBusy(true)
    try {
      const result = await api.post<{ added: Record<string, number> }>('/api/workspace/import-defaults')
      await refresh()
      const total = Object.values(result.added).reduce((sum, value) => sum + value, 0)
      toast.success(total ? `已导入 ${total} 项默认内容` : '默认内容已存在，未重复导入')
    } catch (caught) { toast.error(caught instanceof Error ? caught.message : '默认内容导入失败') } finally { setBusy(false) }
  }
  const skip = async () => {
    setBusy(true)
    try { await api.post('/api/workspace/skip'); await refresh() } catch (caught) { toast.error(caught instanceof Error ? caught.message : '暂时无法跳过初始化') } finally { setBusy(false) }
  }
  return <Card className="overflow-hidden border-primary/15 bg-gradient-to-r from-primary/[.055] via-card to-card"><CardBody className="flex flex-col items-start justify-between gap-5 p-5 md:flex-row md:items-center"><div className="flex items-start gap-4"><span className="grid size-11 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground shadow-sm"><PackageOpen className="size-5" /></span><div><h2 className="font-semibold tracking-tight">准备本地审核工作空间</h2><p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">可以导入系统内置的人物、媒资和历史验证记录快速体验完整流程，也可以直接导入自己的本地视频。所有内容仅保存在本机。</p></div></div><div className="flex shrink-0 flex-wrap gap-2"><Button variant="ghost" disabled={busy} onClick={() => void skip()}>暂不导入</Button><Button variant="outline" asChild><Link to="/media"><Upload />导入我的视频</Link></Button>{setup.bundle_available && <Button disabled={busy} onClick={() => void importDefaults()}><PackageOpen />{busy ? '正在导入…' : '导入默认内容'}</Button>}</div></CardBody></Card>
}

export function Dashboard() {
  const { tasks, loading, error, refresh, purpose } = useWorkspace()
  const data = useMemo(() => {
    const all = tasks.flatMap(eventsOf)
    const counts = { pending: 0, confirmed: 0, rejected: 0, uncertain: 0 }
    all.forEach(event => { counts[event.review_status ?? 'pending'] += 1 })
    const attention = tasks.filter(task => task.status === 'failed' || task.result?.metrics?.coverage_complete === false || eventCounts(task).uncertain > 0)
    return {
      counts,
      attention,
      totalEvents: all.length,
      queue: tasks.filter(isReviewableTask).sort((left, right) => pendingCount(right) - pendingCount(left)),
    }
  }, [tasks])
  if (loading && !tasks.length) return <BusinessPage><LoadingState text="正在准备审核大盘…" /></BusinessPage>
  if (error && !tasks.length) return <BusinessPage><ErrorState message={error.message} onRetry={() => void refresh()} /></BusinessPage>
  const running = tasks.filter(task => task.status === 'running').length
  const needs = tasks.filter(isReviewableTask).length
  const pending = tasks.reduce((sum, task) => sum + pendingCount(task), 0)
  const handled = data.counts.confirmed + data.counts.rejected
  const completion = data.totalEvents ? Math.round(handled / data.totalEvents * 100) : 0
  return <BusinessPage>
    <PageHeader title="审核概览" subtitle={purpose === 'production' ? '生产审核当前待办' : '算法验证当前待办'} />
    <WorkspaceSetupCard />
    {error && <div className="rounded-xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-amber-800" role="status">刷新失败，当前保留上次加载的数据。</div>}
    <Card className="overflow-hidden">
      <CardBody className="p-5 sm:p-6">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">当前待办</p>
            <div className="mt-2 flex items-baseline gap-2"><strong className="text-4xl font-semibold tracking-tight tabular-nums">{pending}</strong><span className="text-base text-muted-foreground">条待复核</span></div>
            <p className="mt-2 text-sm text-muted-foreground">分布在 {needs} 个任务中{running ? `，另有 ${running} 个任务正在检查` : ''}</p>
          </div>
          <Button asChild size="lg"><Link to="/workbench">继续复核<ArrowRight /></Link></Button>
        </div>
        {data.totalEvents > 0 && <div className="mt-6 border-t pt-4">
          <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground"><span>整体处理进度</span><span className="tabular-nums">已处理 {handled}/{data.totalEvents} · {completion}%</span></div>
          <div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${completion}%` }} /></div>
        </div>}
      </CardBody>
    </Card>

    {data.queue.length ? <Card className="min-w-0">
      <CardHeader><SectionHeading title="优先处理" description="待处理较多的任务排在前面" actions={<Button asChild variant="ghost" size="sm"><Link to="/workbench">全部任务<ArrowRight /></Link></Button>} /></CardHeader>
      <div className="divide-y">{data.queue.slice(0, 4).map(task => <div key={task.task_id} className="flex items-center gap-4 px-5 py-4 sm:px-6">
        <Link to={`/tasks/${task.task_id}`} className="min-w-0 flex-1 truncate text-sm font-medium hover:text-primary hover:underline">{task.name}</Link>
        <span className="shrink-0 text-sm tabular-nums text-muted-foreground">{pendingCount(task)} 条待处理</span>
        <Button asChild variant="outline" size="sm"><Link to={`/tasks/${task.task_id}/review`}>开始复核<ArrowRight /></Link></Button>
      </div>)}</div>
    </Card> : <Card><EmptyState title="当前没有待复核内容" description="新的审核任务完成检查后会出现在这里。" /></Card>}

    {data.attention.length > 0 && <Card className="border-warning/30 bg-warning/[.035]">
      <CardHeader><SectionHeading title="需要关注" description={`${data.attention.length} 个任务需要处理异常`} actions={<Button asChild variant="ghost" size="sm"><Link to="/tasks">前往任务中心<ArrowRight /></Link></Button>} /></CardHeader>
      <CardBody className="space-y-2 pt-0">{data.attention.slice(0, 3).map(task => <Link key={task.task_id} to={`/tasks/${task.task_id}`} className="flex items-center gap-3 rounded-lg border bg-background px-3 py-2.5 text-sm hover:bg-muted/50"><CircleAlert className="size-4 shrink-0 text-warning"/><span className="min-w-0 flex-1 truncate font-medium">{task.name}</span><span className="text-xs text-muted-foreground">{task.status === 'failed' ? '检查失败' : task.result?.metrics?.coverage_complete === false ? '覆盖不完整' : '留待复核'}</span></Link>)}</CardBody>
    </Card>}
  </BusinessPage>
}

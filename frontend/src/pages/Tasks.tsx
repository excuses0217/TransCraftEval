import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ListFilter, Plus, Search } from 'lucide-react'
import { useWorkspace } from '../app/WorkspaceContext'
import { BusinessPage, EmptyState, FilterSurface, PageHeader } from '../components/business/BusinessPage'
import { Button } from '../components/ui/Button'
import { Card, CardBody } from '../components/ui/Card'
import { Input } from '../components/ui/Input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/Select'
import { TaskTable } from '../features/tasks/TaskTable'

export function Tasks() {
  const { tasks, library, media, purpose } = useWorkspace()
  const [params, setParams] = useSearchParams()
  const [search, setSearch] = useState(params.get('q') ?? '')
  const status = params.get('status') ?? 'all'
  const filtered = useMemo(() => tasks.filter(task => (status === 'all' || task.status === status) && (!search || `${task.name} ${task.asset_path}`.toLowerCase().includes(search.toLowerCase()))), [tasks, status, search])
  const updateStatus = (value: string) => {
    const next = new URLSearchParams(params)
    value === 'all' ? next.delete('status') : next.set('status', value)
    setParams(next)
  }
  const counts = {
    running: tasks.filter(task => task.status === 'running').length,
    needs_review: tasks.filter(task => task.status === 'needs_review').length,
    completed: tasks.filter(task => task.status === 'completed').length,
    ready: tasks.filter(task => task.status === 'ready').length,
    failed: tasks.filter(task => task.status === 'failed').length,
  }
  const tabs = [
    { value: 'all', label: '全部任务', count: tasks.length },
    { value: 'needs_review', label: '待复核', count: counts.needs_review },
    { value: 'running', label: '检查中', count: counts.running },
    { value: 'ready', label: '待检查', count: counts.ready },
    { value: 'completed', label: '已完成', count: counts.completed },
    ...(counts.failed ? [{ value: 'failed', label: '失败', count: counts.failed }] : []),
  ]

  return <BusinessPage>
    <PageHeader title="任务中心" subtitle={`管理${purpose === 'production' ? '生产审核' : '算法验证'}任务的执行、复核与归档`} actions={<Button asChild><Link to="/tasks/new"><Plus />新建审核任务</Link></Button>} />
    <Card>
      <div className="border-b px-4 pt-1">
        <div className="flex min-w-max gap-1 overflow-x-auto" role="tablist" aria-label="任务状态">
          {tabs.map(tab => <button key={tab.value} type="button" role="tab" aria-selected={status === tab.value} onClick={() => updateStatus(tab.value)} className={`relative flex h-11 items-center gap-2 px-3 text-sm transition-colors ${status === tab.value ? 'font-medium text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
            {tab.label}<span className={`rounded-md px-1.5 py-0.5 text-[11px] tabular-nums ${status === tab.value ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>{tab.count}</span>
            {status === tab.value && <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-foreground" />}
          </button>)}
        </div>
      </div>
      <CardBody className="border-b p-3.5">
        <FilterSurface>
          <label className="relative min-w-64 max-w-md flex-1"><Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" /><Input value={search} onChange={event => { setSearch(event.target.value); const next = new URLSearchParams(params); event.target.value ? next.set('q', event.target.value) : next.delete('q'); setParams(next, { replace: true }) }} placeholder="搜索任务名称或媒资" className="pl-9" /></label>
          <Select value={status} onValueChange={updateStatus}><SelectTrigger aria-label="筛选任务状态" className="min-w-36"><ListFilter className="size-4 text-muted-foreground" /><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">全部状态</SelectItem><SelectItem value="ready">待检查</SelectItem><SelectItem value="running">检查中</SelectItem><SelectItem value="needs_review">待复核</SelectItem><SelectItem value="completed">已完成</SelectItem><SelectItem value="failed">检查失败</SelectItem></SelectContent></Select>
          <span className="ml-auto text-xs text-muted-foreground">显示 <strong className="font-medium text-foreground tabular-nums">{filtered.length}</strong> / {tasks.length} 个任务</span>
        </FilterSurface>
      </CardBody>
      {filtered.length ? <TaskTable tasks={filtered} library={library} media={media} /> : <EmptyState title="没有符合条件的任务" description="调整筛选条件，或创建新的审核任务。" />}
    </Card>
  </BusinessPage>
}

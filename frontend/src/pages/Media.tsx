import { useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Clapperboard, Film, Plus, Search, Upload } from 'lucide-react'
import { toast } from 'sonner'
import type { MediaItem } from '../api/contracts'
import { useWorkspace } from '../app/WorkspaceContext'
import { BusinessPage, EmptyState, FilterSurface, PageHeader, SectionHeading } from '../components/business/BusinessPage'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../components/ui/Dialog'
import { Field, Input } from '../components/ui/Input'
import { TaskTable } from '../features/tasks/TaskTable'
import { formatBytes, formatDuration } from '../lib/utils'

interface UploadItem {
  name: string
  progress: number
  status: 'waiting' | 'uploading' | 'checking' | 'done' | 'duplicate' | 'failed'
  message?: string
}

function uploadFile(file: File, onProgress: (value: number) => void): Promise<{ duplicate: boolean; media: MediaItem }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/media/import')
    xhr.upload.onprogress = event => { if (event.lengthComputable) onProgress(Math.round(event.loaded / event.total * 100)) }
    xhr.upload.onload = () => onProgress(100)
    xhr.onerror = () => reject(new Error('上传连接中断'))
    xhr.onload = () => {
      let data: unknown
      try { data = JSON.parse(xhr.responseText) } catch { data = null }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as { duplicate: boolean; media: MediaItem })
      else reject(new Error(data && typeof data === 'object' && 'detail' in data && typeof (data as { detail: unknown }).detail === 'string' ? (data as { detail: string }).detail : '视频导入失败'))
    }
    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
}

function ImportMediaDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { refresh } = useWorkspace()
  const input = useRef<HTMLInputElement>(null)
  const [items, setItems] = useState<UploadItem[]>([])
  const [selectedCount, setSelectedCount] = useState(0)
  const [busy, setBusy] = useState(false)

  const run = async () => {
    const files = [...(input.current?.files ?? [])]
    if (!files.length) { toast.error('请先选择至少一份本地视频'); return }
    setBusy(true)
    setItems(files.map(file => ({ name: file.name, progress: 0, status: 'waiting' })))
    for (let index = 0; index < files.length; index += 1) {
      const file = files[index]
      setItems(rows => rows.map((row, rowIndex) => rowIndex === index ? { ...row, status: 'uploading' } : row))
      try {
        const result = await uploadFile(file, progress => setItems(rows => rows.map((row, rowIndex) => rowIndex === index ? { ...row, progress, status: progress === 100 ? 'checking' : 'uploading' } : row)))
        setItems(rows => rows.map((row, rowIndex) => rowIndex === index ? { ...row, status: result.duplicate ? 'duplicate' : 'done', message: result.duplicate ? '已存在，未重复导入' : '导入完成' } : row))
      } catch (caught) {
        setItems(rows => rows.map((row, rowIndex) => rowIndex === index ? { ...row, status: 'failed', message: caught instanceof Error ? caught.message : '导入失败' } : row))
      }
    }
    await refresh()
    setBusy(false)
  }

  return <Dialog open={open} onOpenChange={value => { if (!busy) onOpenChange(value) }}>
    <DialogContent>
      <DialogHeader><DialogTitle>导入本地媒资</DialogTitle><DialogDescription>支持多选 MP4。视频保存在本机，不会上传到外部服务。</DialogDescription></DialogHeader>
      <DialogBody className="space-y-4">
        <Field label="选择本地视频" hint={selectedCount ? `已选择 ${selectedCount} 个文件` : '单个文件不超过 20 GB，建议 H.264 编码。'}>
          <Input ref={input} type="file" accept=".mp4,video/mp4" multiple disabled={busy} onChange={event => setSelectedCount(event.target.files?.length ?? 0)} className="h-auto cursor-pointer border-dashed bg-muted/30 p-5" />
        </Field>
        {items.length > 0 && <div className="space-y-2">{items.map((item, index) => <div key={`${item.name}-${index}`} className="rounded-lg border bg-muted/20 p-3"><div className="flex justify-between gap-3 text-sm"><span className="truncate font-medium">{item.name}</span><span className={item.status === 'failed' ? 'text-critical' : 'text-muted-foreground'}>{item.message ?? ({ waiting: '等待导入', uploading: `上传 ${item.progress}%`, checking: '正在校验', done: '导入完成', duplicate: '已存在', failed: '失败' }[item.status])}</span></div>{['uploading', 'checking'].includes(item.status) && <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ width: `${item.progress}%` }} /></div>}</div>)}</div>}
      </DialogBody>
      <DialogFooter><Button variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>取消</Button><Button disabled={busy || !selectedCount} onClick={() => void run()}>{busy ? '正在导入…' : '导入所选视频'}</Button></DialogFooter>
    </DialogContent>
  </Dialog>
}

export function MediaCenter() {
  const { media, tasks } = useWorkspace()
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const rows = media.filter(item => item.name.toLowerCase().includes(query.toLowerCase()))

  return <BusinessPage>
    <PageHeader title="媒资中心" subtitle="集中管理本地视频，并从媒资上下文发起审核任务。缩略图默认不叠加算法检测框。" actions={<Button onClick={() => setOpen(true)}><Upload />导入媒资</Button>} />
    <FilterSurface>
      <label className="relative min-w-64 flex-1"><Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" /><Input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索媒资名称" className="pl-9" /></label>
      <span className="pb-2 text-sm text-muted-foreground">共 <strong className="font-semibold text-foreground tabular-nums">{rows.length}</strong> 份媒资</span>
    </FilterSurface>
    {rows.length ? <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
      {rows.map(item => {
        const related = tasks.filter(task => task.asset_path === item.path)
        return <Card key={item.media_id} className="group flex min-w-0 flex-col transition-[border-color,box-shadow] hover:border-primary/25 hover:shadow-[0_6px_18px_hsl(var(--foreground)/0.06)]">
          <Link to={`/media/${item.media_id}`} className="media-poster block aspect-video overflow-hidden border-b border-border">
            {item.url ? <video src={item.url} muted preload="metadata" className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.015]" /> : <span className="grid h-full place-items-center text-sidebar-foreground"><Film className="size-8" /></span>}
          </Link>
          <CardBody className="flex flex-1 flex-col p-4">
            <div className="min-w-0"><Link to={`/media/${item.media_id}`} className="block truncate font-semibold text-foreground hover:text-primary hover:underline">{item.name}</Link><p className="mt-1 text-sm text-muted-foreground">{formatDuration(item.duration_seconds)} · {formatBytes(item.size_bytes)}</p></div>
            <div className="mt-4 flex items-center justify-between gap-2"><Badge variant={related.length ? 'info' : 'secondary'}>{related.length ? `${related.length} 个关联任务` : '未创建任务'}</Badge><span className="text-xs text-muted-foreground">本地存储</span></div>
            <div className="mt-4 flex gap-2 border-t border-border/70 pt-3"><Button asChild size="sm" variant="outline" className="flex-1"><Link to={`/media/${item.media_id}`}>查看媒资</Link></Button><Button asChild size="sm" className="flex-1"><Link to={`/tasks/new?media=${item.media_id}`}><Plus />新建任务</Link></Button></div>
          </CardBody>
        </Card>
      })}
    </div> : <Card><EmptyState title={media.length ? '没有匹配的媒资' : '还没有导入媒资'} description={media.length ? '尝试其他搜索词。' : '导入本地 MP4 后，即可选择人物发起审核。'} action={!media.length ? <Button onClick={() => setOpen(true)}><Upload />导入第一份媒资</Button> : undefined} /></Card>}
    <ImportMediaDialog open={open} onOpenChange={setOpen} />
  </BusinessPage>
}

export function MediaDetail() {
  const { media, tasks, library } = useWorkspace()
  const { mediaId } = useParams()
  const item = media.find(value => value.media_id === mediaId)
  if (!item) return <BusinessPage><EmptyState title="找不到这份媒资" description="媒资可能已移动，或当前工作空间尚未加载。" action={<Button asChild><Link to="/media">返回媒资中心</Link></Button>} /></BusinessPage>
  const related = tasks.filter(task => task.asset_path === item.path)
  const video = item.url ?? (related[0] ? `/api/review-tasks/${related[0].task_id}/video` : undefined)

  return <BusinessPage>
    <Button asChild variant="ghost" size="sm" className="-ml-2"><Link to="/media"><ArrowLeft />返回媒资中心</Link></Button>
    <PageHeader title={item.name} subtitle={`${formatDuration(item.duration_seconds)} · ${formatBytes(item.size_bytes)} · 本地媒资`} actions={<Button asChild><Link to={`/tasks/new?media=${item.media_id}`}><Plus />创建审核任务</Link></Button>} />
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
      <Card className="media-poster overflow-hidden"><div className="aspect-video">{video ? <video src={video} controls preload="metadata" className="h-full w-full object-contain" /> : <div className="grid h-full place-items-center text-sidebar-foreground"><Clapperboard className="size-10" /></div>}</div></Card>
      <Card><CardHeader><SectionHeading title="媒资信息" /></CardHeader><CardBody><dl className="space-y-5 text-sm"><div><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">文件名称</dt><dd className="mt-1.5 break-words font-medium">{item.name}</dd></div><div><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">关联审核</dt><dd className="mt-1.5 font-semibold tabular-nums">{related.length} 个任务</dd></div><div><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">说明</dt><dd className="mt-1.5 leading-6 text-muted-foreground">{item.selection_note ?? '本地媒资，可创建人物审核任务。'}</dd></div></dl></CardBody></Card>
    </div>
    <Card><CardHeader><SectionHeading title="关联审核任务" description="每个任务保留各自的审核范围与结果。" /></CardHeader>{related.length ? <TaskTable tasks={related} library={library} media={media} /> : <EmptyState title="还没有审核记录" description="创建任务后，检查进度和结果会显示在这里。" />}</Card>
  </BusinessPage>
}

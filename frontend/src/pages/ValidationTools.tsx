import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { FlaskConical, Play, RefreshCcw } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '../api/http'
import { useWorkspace } from '../app/WorkspaceContext'
import { BusinessPage, PageHeader, SectionHeading } from '../components/business/BusinessPage'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Field, Input } from '../components/ui/Input'

interface LegacyJob {
  job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  person_name: string
  progress: number
  events: Array<{ timestamp_seconds?: number; evidence_image?: string }>
  error?: string | null
}

interface Settings { video_path?: string; reference_image_path?: string; person_name?: string }

export function ValidationTools() {
  const { purpose } = useWorkspace()
  const [video, setVideo] = useState('')
  const [reference, setReference] = useState('')
  const [person, setPerson] = useState('')
  const [job, setJob] = useState<LegacyJob | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { void api.get<Settings>('/api/settings').then(settings => { setVideo(settings.video_path ?? ''); setReference(settings.reference_image_path ?? ''); setPerson(settings.person_name ?? '') }).catch(() => undefined) }, [])
  useEffect(() => {
    if (!job || !['queued', 'running'].includes(job.status)) return
    const timer = window.setInterval(() => void api.get<LegacyJob>(`/api/jobs/${job.job_id}`).then(setJob).catch(() => undefined), 1200)
    return () => window.clearInterval(timer)
  }, [job?.job_id, job?.status])

  const run = async () => {
    if (!video.trim() || !reference.trim() || !person.trim()) return
    setBusy(true)
    try {
      const created = await api.post<LegacyJob>('/api/jobs', { video_path: video.trim(), reference_image_path: reference.trim(), person_name: person.trim(), run_async: true })
      setJob(created)
      toast.success('单人物技术验证已启动')
    } catch (caught) { toast.error(caught instanceof Error ? caught.message : '验证任务启动失败') } finally { setBusy(false) }
  }

  if (purpose !== 'validation') return <Navigate to="/overview" replace />
  const statusLabel = job ? ({ queued: '排队中', running: '运行中', completed: '已完成', failed: '失败' } as const)[job.status] : ''
  const statusVariant = job?.status === 'completed' ? 'success' : job?.status === 'failed' ? 'destructive' : job?.status === 'running' ? 'info' : 'secondary'

  return <BusinessPage className="max-w-[1180px]">
    <PageHeader title="技术验证" subtitle="算法运营工作区。这里的单人物实验不会写入生产审核记录。" actions={<Badge variant="warning"><FlaskConical />非生产审核</Badge>} />
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
      <Card><CardHeader><SectionHeading title="单人物本地验证" description="使用本地文件路径检查模型和运行环境；正式审核请从任务中心创建。" /></CardHeader><CardBody className="space-y-5"><div className="grid gap-4"><Field label="本地视频路径" hint="仅支持本地已授权的媒资文件。"><Input value={video} onChange={event => setVideo(event.target.value)} placeholder="/absolute/path/video.mp4" /></Field><Field label="本地参考照片路径" hint="建议使用清晰、正面、无遮挡的单人照片。"><Input value={reference} onChange={event => setReference(event.target.value)} placeholder="/absolute/path/reference.jpg" /></Field><Field label="人物标记"><Input value={person} onChange={event => setPerson(event.target.value)} placeholder="例如：朱时茂" /></Field></div><div className="flex items-center justify-between border-t border-border pt-4"><p className="text-xs text-muted-foreground">验证结果仅用于算法验证空间。</p><Button disabled={busy || !video.trim() || !reference.trim() || !person.trim()} onClick={() => void run()}><Play />{busy ? '正在启动…' : '开始验证'}</Button></div></CardBody></Card>
      <Card className="xl:self-start"><CardHeader><SectionHeading title="运行状态" actions={job ? <Button variant="ghost" size="icon-sm" onClick={() => void api.get<LegacyJob>(`/api/jobs/${job.job_id}`).then(setJob)} aria-label="刷新运行状态"><RefreshCcw /></Button> : undefined} /></CardHeader><CardBody>{job ? <div className="space-y-5"><Badge variant={statusVariant}>{statusLabel}</Badge><div><div className="flex items-end justify-between"><p className="text-[30px] font-semibold tracking-[-0.03em] tabular-nums">{Math.round((job.progress ?? 0) * 100)}%</p><span className="text-xs text-muted-foreground">执行进度</span></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-info transition-all" style={{ width: `${Math.round((job.progress ?? 0) * 100)}%` }} /></div></div><dl className="space-y-4 border-t border-border pt-4 text-sm"><div><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">人物标记</dt><dd className="mt-1.5 font-medium">{job.person_name}</dd></div><div><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">原始候选</dt><dd className="mt-1.5 font-medium">{job.events?.length ?? 0} 条</dd></div></dl>{job.error && <p className="rounded-lg bg-critical/10 p-3 text-sm text-critical">{job.error}</p>}</div> : <div className="rounded-lg bg-muted/55 p-4 text-sm leading-6 text-muted-foreground">提交后会在这里显示真实运行进度。此入口不会写入生产审核记录。</div>}</CardBody></Card>
    </div>
  </BusinessPage>
}

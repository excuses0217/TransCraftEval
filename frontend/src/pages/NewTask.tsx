import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Check, Film, Search, UsersRound } from 'lucide-react'
import { toast } from 'sonner'
import type { ReviewTask, TaskDraft } from '../api/contracts'
import { api, ApiError } from '../api/http'
import { useWorkspace } from '../app/WorkspaceContext'
import { BusinessPage, EmptyState, PageHeader, SectionHeading } from '../components/business/BusinessPage'
import { ObjectStatusBadge } from '../components/business/StatusBadge'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader, CardTitle } from '../components/ui/Card'
import { Field, Input } from '../components/ui/Input'
import { formatBytes, formatDuration } from '../lib/utils'

const steps = [['1', '选择媒资'], ['2', '选择人物'], ['3', '核对并提交']] as const

export function NewTask() {
  const { purpose, media, library, refresh } = useWorkspace()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const initial = media.find(item => item.media_id === params.get('media'))
  const [step, setStep] = useState(initial ? 2 : 1)
  const [mediaId, setMediaId] = useState(initial?.media_id ?? '')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [name, setName] = useState(initial ? `${initial.name} · 人物审核` : '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const stepPanel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    stepPanel.current?.scrollIntoView({ block: 'start' })
    stepPanel.current?.focus({ preventScroll: true })
  }, [step])
  const people = library.filter(item => item.category === 'person')
  const visible = useMemo(() => people.filter(item => `${item.name} ${item.classification} ${item.aliases.join(' ')}`.toLowerCase().includes(search.toLowerCase())), [people, search])
  const chosenMedia = media.find(item => item.media_id === mediaId)
  const selectedPeople = people.filter(item => selected.has(item.item_id))
  const usable = (id: string) => {
    const item = people.find(person => person.item_id === id)
    if (!item) return false
    const hasReferences = item.materials.some(material => material.kind === 'reference_image' && material.status !== 'disabled')
    return hasReferences && item.status !== 'disabled' && (purpose === 'validation' || (item.status === 'active' && item.validation?.status === 'passed'))
  }
  const enabledPeople = visible.filter(item => usable(item.item_id))
  const toggle = (id: string) => setSelected(value => {
    const next = new Set(value)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })
  const submit = async () => {
    if (!chosenMedia || !selected.size || !name.trim()) { setError('请完成媒资、人物与任务名称的核对。'); return }
    setBusy(true)
    setError('')
    const draft: TaskDraft = { name: name.trim(), asset_path: chosenMedia.path, object_ids: [...selected], purpose, capabilities: ['face'] }
    try {
      const task = await api.post<ReviewTask>('/api/review-tasks', draft)
      try {
        await api.post(`/api/review-tasks/${task.task_id}/run`)
        toast.success('任务已创建，系统开始检查')
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 409) toast.info('任务已创建，当前有其他任务正在检查，可稍后启动')
        else throw caught
      }
      await refresh()
      navigate(`/tasks/${task.task_id}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '任务创建失败')
    } finally { setBusy(false) }
  }

  return <BusinessPage className="max-w-[1280px]">
    <Button asChild variant="ghost" size="sm" className="-ml-2"><Link to="/tasks"><ArrowLeft />返回任务中心</Link></Button>
    <PageHeader title="新建审核任务" subtitle={`${purpose === 'production' ? '生产审核' : '算法验证'} · 当前仅启用人物画面检查`} />
    <ol className="grid overflow-hidden rounded-xl border border-border bg-card text-sm shadow-[0_1px_2px_hsl(var(--foreground)/0.025)] sm:grid-cols-3">
      {steps.map(([index, label], offset) => <li key={index} className={`flex min-h-15 items-center gap-2.5 border-b px-4 py-3 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0 ${step === offset + 1 ? 'bg-primary text-primary-foreground' : step > offset + 1 ? 'bg-muted/65 text-foreground' : 'text-muted-foreground'}`}>
        <span className={`grid size-6 shrink-0 place-items-center rounded-full text-xs font-semibold ${step === offset + 1 ? 'bg-white/20' : step > offset + 1 ? 'bg-success text-white' : 'bg-muted text-muted-foreground'}`}>{step > offset + 1 ? <Check className="size-3.5" /> : index}</span>
        <span className="font-medium">{label}</span>
      </li>)}
    </ol>

    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_290px]">
      <div ref={stepPanel} tabIndex={-1} className="min-w-0 scroll-mt-5 outline-none">
        {step === 1 && <Card>
          <CardHeader><div><CardTitle>选择一份要审核的视频</CardTitle><p className="mt-1 text-sm text-muted-foreground">任务会保存这份媒资和当次核查范围。</p></div><Badge variant="outline">{media.length} 份可选媒资</Badge></CardHeader>
          <CardBody>{media.length ? <div className="grid gap-3 md:grid-cols-2">{media.map(item => <Button key={item.media_id} type="button" variant="outline" aria-pressed={mediaId === item.media_id} onClick={() => setMediaId(item.media_id)} className={`h-auto min-h-28 w-full justify-start p-3 text-left ${mediaId === item.media_id ? 'border-primary bg-primary/[.035] ring-1 ring-primary/25' : 'hover:bg-muted/40'}`}>
            {item.poster ? <img src={item.poster} alt="" className="h-20 w-32 shrink-0 rounded-lg object-cover" /> : <span className="media-poster grid h-20 w-32 shrink-0 place-items-center rounded-lg text-white"><Film /></span>}
            <span className="min-w-0 flex-1"><strong className="block truncate text-sm">{item.name}</strong><span className="mt-1 block text-xs text-muted-foreground">{formatDuration(item.duration_seconds)} · {formatBytes(item.size_bytes)}</span>{mediaId === item.media_id && <Badge className="mt-3">已选择</Badge>}</span>
          </Button>)}</div> : <EmptyState title="还没有可用媒资" description="先到媒资中心导入本地 MP4，再创建审核任务。" action={<Button asChild><Link to="/media">前往媒资中心</Link></Button>} />}</CardBody>
        </Card>}

        {step === 2 && <Card>
          <CardHeader><div><CardTitle>选择需要核查的人物</CardTitle><p className="mt-1 text-sm text-muted-foreground">可多选。生产审核只能选择已启用、已通过验证且有参考照片的人物。</p></div><Badge variant="info">已选 {selected.size} 人</Badge></CardHeader>
          <CardBody><div className="relative mb-4 max-w-md"><Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" /><Input value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索人物、分类或别名" className="pl-9" /></div>{purpose === 'production' && !enabledPeople.length ? <EmptyState title="当前没有可用于生产审核的人物" description="对象需拥有至少两张参考照片，并在算法验证中记录通过结论后才可启用。" action={<Button asChild><Link to="/library/people">前往人物库完成验证</Link></Button>} /> : <div className="grid gap-2.5 md:grid-cols-2">{visible.map(item => { const enabled = usable(item.item_id); const photo = item.materials.find(material => material.kind === 'reference_image' && material.status !== 'disabled'); return <Button key={item.item_id} type="button" variant="outline" disabled={!enabled} aria-pressed={selected.has(item.item_id)} onClick={() => toggle(item.item_id)} className={`h-auto min-h-20 w-full justify-start p-3 text-left ${selected.has(item.item_id) ? 'border-primary bg-primary/[.035] ring-1 ring-primary/25' : enabled ? 'hover:bg-muted/40' : 'cursor-not-allowed opacity-55'}`}>
            {photo ? <img src={photo.local_uri} alt="" className="size-12 rounded-lg object-cover" /> : <span className="grid size-12 place-items-center rounded-lg bg-muted"><UsersRound className="size-5 text-muted-foreground" /></span>}
            <span className="min-w-0 flex-1"><strong className="block truncate text-sm">{item.name}</strong><span className="mt-1 flex min-w-0 items-center gap-2"><ObjectStatusBadge status={item.status} /><small className="truncate text-muted-foreground">{item.classification}</small></span>{!enabled && <small className="mt-1 block text-critical">{purpose === 'production' ? '未启用、未通过验证或缺少照片' : '已停用或缺少可用照片'}</small>}</span>{selected.has(item.item_id) && <Check className="size-4 text-primary" />}
          </Button>})}</div>}</CardBody>
        </Card>}

        {step === 3 && <Card>
          <CardHeader><div><CardTitle>核对任务范围</CardTitle><p className="mt-1 text-sm text-muted-foreground">提交后系统会整理需要人工核查的候选片段。</p></div></CardHeader>
          <CardBody className="space-y-5"><Field label="任务名称"><Input value={name} onChange={event => setName(event.target.value)} placeholder="例如：牧马人复播人物审核" maxLength={200} /></Field><div className="rounded-xl border border-border bg-muted/35 p-4"><SectionHeading title="本次审核范围" /><dl className="mt-4 grid gap-4 sm:grid-cols-2"><div><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">媒资</dt><dd className="mt-1.5 font-medium">{chosenMedia?.name}</dd></div><div><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">工作空间</dt><dd className="mt-1.5 font-medium">{purpose === 'production' ? '生产审核' : '算法验证'}</dd></div><div className="sm:col-span-2"><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">核查人物</dt><dd className="mt-2 flex flex-wrap gap-2">{selectedPeople.map(item => <Badge key={item.item_id} variant="outline">{item.name}</Badge>)}</dd></div><div className="sm:col-span-2"><dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">本次能力</dt><dd className="mt-1.5 text-sm text-muted-foreground">人物画面。文字、语音和内容检测暂未启用。</dd></div></dl></div>{error && <p className="rounded-lg border border-critical/20 bg-critical/10 p-3 text-sm text-critical" role="alert">{error}</p>}</CardBody>
        </Card>}

        <div className="mt-5 flex items-center justify-between border-t border-border pt-4"><Button variant="outline" disabled={step === 1 || busy} onClick={() => setStep(value => value - 1)}><ArrowLeft />上一步</Button>{step < 3 ? <Button disabled={(step === 1 && !mediaId) || (step === 2 && !selected.size)} onClick={() => { if (step === 1 && chosenMedia && !name) setName(`${chosenMedia.name} · 人物审核`); setStep(value => value + 1) }}>下一步<ArrowRight /></Button> : <Button disabled={busy || !name.trim()} onClick={() => void submit()}>{busy ? '正在创建任务…' : '提交并开始检查'}</Button>}</div>
      </div>

      <aside className="hidden xl:block"><Card className="sticky top-6"><CardHeader><SectionHeading title="当前选择" /></CardHeader><CardBody className="space-y-5"><div><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">审核媒资</p><p className="mt-1.5 text-sm font-medium leading-5">{chosenMedia?.name ?? '尚未选择'}</p></div><div><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">核查人物</p>{selectedPeople.length ? <div className="mt-2 flex flex-wrap gap-1.5">{selectedPeople.map(item => <Badge key={item.item_id} variant="outline">{item.name}</Badge>)}</div> : <p className="mt-1.5 text-sm text-muted-foreground">尚未选择</p>}</div><div className="rounded-lg bg-muted p-3 text-xs leading-5 text-muted-foreground">正式提交前可随时返回上一步调整范围。提交后系统会开始检查并生成待复核片段。</div></CardBody></Card></aside>
    </div>
  </BusinessPage>
}

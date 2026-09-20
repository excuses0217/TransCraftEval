import { Badge } from '../ui/Badge'
import type { ReviewStatus, TaskStatus } from '../../api/contracts'
import { reviewLabel, statusLabel } from '../../features/tasks/taskModel'

export function TaskStatusBadge({ status }: { status: TaskStatus }) {
  const variant = status==='completed'?'success':status==='running'?'info':status==='needs_review'?'warning':status==='failed'?'destructive':'secondary'
  return <Badge variant={variant}>{statusLabel[status] ?? status}</Badge>
}
export function ReviewStatusBadge({ status }: { status: ReviewStatus }) {
  const variant = status==='confirmed'?'success':status==='rejected'?'secondary':status==='uncertain'?'warning':'outline'
  return <Badge variant={variant}>{reviewLabel[status]}</Badge>
}
export function PurposeBadge({ purpose }: { purpose?: 'production'|'validation' }) { return <Badge variant={purpose==='production'?'default':'outline'}>{purpose==='production'?'生产审核':'算法验证'}</Badge> }
export function ObjectStatusBadge({ status }: { status: string }) { const labels:Record<string,string>={draft:'草稿',ready_for_material:'待补素材',ready_for_validation:'待验证',active:'已启用',disabled:'已停用'}; const variant=status==='active'?'success':status==='disabled'?'destructive':status==='ready_for_validation'?'warning':'secondary'; return <Badge variant={variant}>{labels[status]??status}</Badge> }

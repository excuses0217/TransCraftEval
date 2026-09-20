import type { EvidenceEvent, LibraryItem, MediaItem, ReviewStatus, ReviewTask, TaskStatus } from '../../api/contracts'
import { basename } from '../../lib/utils'

export const statusLabel: Record<TaskStatus, string> = { draft:'草稿', ready:'待检查', running:'检查中', needs_review:'待复核', completed:'已完成', failed:'检查失败' }
export const reviewLabel: Record<ReviewStatus, string> = { pending:'未处理', confirmed:'确认出现', rejected:'已排除', uncertain:'留待复核' }

export function eventsOf(task: ReviewTask) { return task.result?.events ?? [] }
export function reviewStatus(event: EvidenceEvent): ReviewStatus { return event.review_status ?? 'pending' }
export function confidenceOf(event: EvidenceEvent) {
  const available = typeof event.confidence_score === 'number' && Number.isFinite(event.confidence_score)
  const score = available ? Math.max(0, Math.min(100, Math.round(event.confidence_score as number))) : null
  const level = event.confidence_level ?? (score !== null && score >= 80 ? 'high' : score !== null && score >= 60 ? 'medium' : 'low')
  return {
    available,
    score,
    level,
    label: available ? level === 'high' ? '较高' : level === 'medium' ? '中等' : '较低' : '待计算',
    factors: event.confidence_factors ?? [],
    cautions: event.confidence_cautions ?? [],
    dimensions: event.confidence_dimensions
  }
}
export function eventCounts(task: ReviewTask) { const counts: Record<ReviewStatus, number>={pending:0,confirmed:0,rejected:0,uncertain:0}; eventsOf(task).forEach(event=>counts[reviewStatus(event)]++); return counts }
export function pendingCount(task: ReviewTask) { const counts=eventCounts(task); return counts.pending+counts.uncertain }
export function isReviewableTask(task: ReviewTask) { return task.status === 'needs_review' && pendingCount(task) > 0 }
export function peopleNames(task: ReviewTask, items: LibraryItem[]) { const map=new Map(items.map(item=>[item.item_id,item.name])); return task.object_ids.map(id=>map.get(id)??'未知人物') }
export function taskMediaName(task: ReviewTask, media: MediaItem[] = []) {
  const managed = media.find(item => item.path === task.asset_path)
  if (managed) return managed.name
  const filename = basename(task.asset_path)
  return /^[0-9a-f]{16,64}\.mp4$/i.test(filename) ? '本地媒资' : filename
}
export function nextAction(task: ReviewTask) { if(task.status==='ready') return '开始检查'; if(task.status==='running') return '查看进度'; if(task.status==='needs_review') return '开始复核'; if(task.status==='completed') return '查看结果'; if(task.status==='failed') return '查看问题'; return '查看任务' }

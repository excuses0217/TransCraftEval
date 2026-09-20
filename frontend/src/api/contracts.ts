export type WorkspacePurpose = 'production' | 'validation'
export type TaskStatus = 'draft' | 'ready' | 'running' | 'needs_review' | 'completed' | 'failed'
export type ReviewStatus = 'pending' | 'confirmed' | 'rejected' | 'uncertain'
export type LibraryCategory = 'person' | 'text' | 'content'
export type ObjectValidationStatus = 'not_started' | 'pending' | 'passed' | 'failed'

export interface Material {
  material_id: string
  kind: 'reference_image' | 'reference_video' | 'rule_file'
  title: string
  local_uri: string
  quality_note: string
  status: 'imported' | 'pending_validation' | 'disabled'
}

export interface ReferenceMaterial {
  material_id?: string
  kind: 'reference_image'
  title?: string
  local_uri: string
  quality_note?: string
  status?: 'imported' | 'pending_validation' | 'disabled'
}

export interface LibraryItem {
  item_id: string
  category: LibraryCategory
  classification: string
  name: string
  aliases: string[]
  definition: string
  status: 'draft' | 'ready_for_material' | 'ready_for_validation' | 'active' | 'disabled'
  materials: Material[]
  validation?: { status: ObjectValidationStatus; note?: string; decided_at?: string | null }
  lifecycle_history?: Array<{ at: string; actor: string; event: string; note?: string }>
}

export interface EvidenceEvent {
  event_id: string
  person_id: string
  person_name: string
  start_seconds: number
  end_seconds: number
  evidence_seconds?: number
  evidence_image: string
  review_status?: ReviewStatus
  reason?: string
  note?: string
  ambiguous?: boolean
  support_frames?: number
  reference_count?: number
  confidence_score?: number
  confidence_level?: 'high' | 'medium' | 'low'
  confidence_factors?: string[]
  confidence_cautions?: string[]
  confidence_kind?: string
  confidence_is_probability?: boolean
  confidence_dimensions?: {
    model_evidence: number
    temporal_consistency: number
    environment_quality: number | null
    reference_coverage: number
  }
  best_score?: number
  track_score?: number
  topk_score?: number
  margin?: number
  quality?: number
  vote_ratio?: number
  score_median?: number
  score_p25?: number
  independent_support?: number
  early_late_consistent?: boolean
  segment_count?: number
  merged_event_ids?: string[]
  segments?: Array<{
    event_id?: string
    start_seconds: number
    end_seconds: number
    evidence_seconds?: number
    evidence_image?: string
    support_frames?: number
    review_status?: ReviewStatus
    scene_id?: number
    track_id?: string
  }>
  history?: Array<Record<string, unknown>>
}

export interface ReferenceSnapshot {
  person_id: string
  name: string
  reference_count: number
  materials?: ReferenceMaterial[]
  rejected_references?: Array<{ filename: string; reason: string }>
}

export interface ReviewResult {
  events: EvidenceEvent[]
  analysis_profile?: ReviewTask['analysis_profile']
  metrics?: {
    coverage_complete?: boolean
    duration_seconds?: number
    elapsed_seconds?: number
    [key: string]: unknown
  }
  reference_snapshot?: ReferenceSnapshot[]
  validation_note?: string
  confidence_available?: boolean
  confidence_unavailable_reason?: string
  object_summaries?: Array<{
    object_id: string
    name: string
    candidate_count: number
    confirmed: number
    rejected: number
    unresolved: number
    conclusion: 'confirmed' | 'excluded' | 'not_found' | 'unresolved' | 'incomplete'
  }>
}

export interface ReviewTask {
  task_id: string
  name: string
  asset_path: string
  object_ids: string[]
  purpose?: WorkspacePurpose
  capabilities?: string[]
  analysis_profile?: string
  status: TaskStatus
  progress?: number
  error?: string | null
  created_at?: string
  started_at?: string
  analysis_completed_at?: string
  failed_at?: string
  completed_at?: string
  last_completed_at?: string
  reopened_at?: string
  audit_version?: number
  audit_versions?: Array<{ version: number; completed_at: string; purpose: WorkspacePurpose; events: EvidenceEvent[]; metrics?: ReviewResult['metrics'] }>
  audit_history?: Array<Record<string, unknown>>
  previous_task_id?: string
  import_key?: string
  candidate_count?: number
  result?: ReviewResult
}

export interface MediaItem {
  media_id: string
  name: string
  path: string
  url?: string
  poster?: string
  size_bytes?: number
  duration_seconds?: number
  source_start_seconds?: number
  selection_note?: string
  task_id?: string
  sha256?: string
}

export interface Overview {
  task_count: number
  task_statuses: Record<string, number>
  library_counts: Record<LibraryCategory, number>
  tasks: ReviewTask[]
}

export interface WorkspaceSetup {
  enabled: boolean
  initialized: boolean
  bundle_available: boolean
  media_count: number
}

export interface TaskDraft {
  name: string
  asset_path: string
  object_ids: string[]
  purpose: WorkspacePurpose
  capabilities: ['face']
}

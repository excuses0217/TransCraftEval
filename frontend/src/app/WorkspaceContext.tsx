import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../api/http'
import type { LibraryItem, MediaItem, Overview, ReviewTask, WorkspacePurpose, WorkspaceSetup } from '../api/contracts'

interface WorkspaceState {
  purpose: WorkspacePurpose
  setPurpose: (purpose: WorkspacePurpose) => void
  tasks: ReviewTask[]
  library: LibraryItem[]
  media: MediaItem[]
  overview: Overview | null
  setup: WorkspaceSetup | null
  loading: boolean
  error: Error | null
  refreshedAt: Date | null
  refresh: () => Promise<void>
}

const Context = createContext<WorkspaceState | null>(null)

function initialPurpose(): WorkspacePurpose {
  const requested = new URLSearchParams(location.search).get('workspace')
  if (requested === 'validation' || requested === 'production') return requested
  const saved = localStorage.getItem('yingjian-workspace')
  return saved === 'validation' ? 'validation' : 'production'
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [purpose, setPurposeState] = useState<WorkspacePurpose>(initialPurpose)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [library, setLibrary] = useState<LibraryItem[]>([])
  const [media, setMedia] = useState<MediaItem[]>([])
  const [setup, setSetup] = useState<WorkspaceSetup | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null)

  const refresh = useCallback(async () => {
    setError(null)
    try {
      const [nextOverview, nextLibrary, nextMedia, nextSetup] = await Promise.all([
        api.get<Overview>(`/api/overview?purpose=${purpose}`), api.get<LibraryItem[]>('/api/library-items'),
        api.get<MediaItem[]>('/api/local-media'), api.get<WorkspaceSetup>('/api/workspace/setup')
      ])
      setOverview(nextOverview); setLibrary(nextLibrary); setMedia(nextMedia); setSetup(nextSetup); setRefreshedAt(new Date())
    } catch (caught) { setError(caught instanceof Error ? caught : new Error('数据加载失败')) }
    finally { setLoading(false) }
  }, [purpose])

  useEffect(() => { void refresh() }, [refresh])
  useEffect(() => {
    if (!overview?.tasks.some(task => task.status === 'running')) return
    const timer = window.setInterval(() => void refresh(), 3000)
    return () => window.clearInterval(timer)
  }, [overview, refresh])

  const setPurpose = useCallback((next: WorkspacePurpose) => {
    setPurposeState(next); localStorage.setItem('yingjian-workspace', next)
    const url = new URL(location.href); url.searchParams.set('workspace', next); history.replaceState(null, '', url)
  }, [])
  const tasks = useMemo(() => overview?.tasks ?? [], [overview])
  return <Context.Provider value={{ purpose,setPurpose,tasks,library,media,overview,setup,loading,error,refreshedAt,refresh }}>{children}</Context.Provider>
}

export function useWorkspace() { const value=useContext(Context); if(!value) throw new Error('WorkspaceProvider is missing'); return value }

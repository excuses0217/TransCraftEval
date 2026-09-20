import { useCallback, useEffect, useRef, useState } from 'react'

export interface ApiResource<T> { data: T | null; loading: boolean; error: Error | null; refetch: () => Promise<void> }

export function useApi<T>(fetcher: (signal: AbortSignal) => Promise<T>, deps: readonly unknown[] = []): ApiResource<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const version = useRef(0)
  const controller = useRef<AbortController | null>(null)
  const load = useCallback(async () => {
    controller.current?.abort()
    const current = new AbortController()
    controller.current = current
    const request = ++version.current
    setLoading(true); setError(null)
    try { const result = await fetcher(current.signal); if (request === version.current) setData(result) }
    catch (caught) { if (request === version.current && !current.signal.aborted) setError(caught instanceof Error ? caught : new Error('请求失败')) }
    finally { if (request === version.current) setLoading(false) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { void load(); return () => { version.current += 1; controller.current?.abort() } }, [load])
  return { data, loading, error, refetch: load }
}
